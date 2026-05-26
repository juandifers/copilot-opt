"""Claude Code subprocess backend.

Implements ModelBackend using the ``claude -p`` CLI (Max-plan OAuth).
All subprocess invocation details match the pre-registered behaviour
exactly: same command-line flags, same assertions, same retry semantics.

Retry policy (per preregistration-v1.1 spec):
- Retry once on: rc != 0, schema validation failure on first attempt.
- Halt immediately on: is_error=true, JSON parse failure, schema failure
  on retry, empty modelUsage.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import jsonschema

from .base import HaltError, ModelBackend, ModelResponse

_REPO = Path(__file__).resolve().parents[3]


def _resolve_claude_binary() -> str:
    b = shutil.which("claude")
    if not b:
        raise RuntimeError("`claude` CLI not found on PATH")
    return b


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git"] + args, cwd=_REPO, text=True).strip()


def _assert_no_bare(cmd: list[str]) -> None:
    if any(tok == "--bare" for tok in cmd):
        raise HaltError(
            f"--bare appeared in command line; locked configs require "
            f"bare:false. cmd={cmd!r}"
        )


def _run_subprocess(
    *,
    model: str,
    system_prompt_path: Path,
    json_schema: dict,
    user_message: str,
    timeout_s: float = 180,
) -> tuple[int, str, str, list[str], int]:
    """Execute claude CLI. Returns (rc, stdout, stderr, cmd, elapsed_ms)."""
    binary = _resolve_claude_binary()
    cmd = [
        binary, "-p",
        "--model", model,
        "--system-prompt-file", str(system_prompt_path),
        "--output-format", "json",
        "--json-schema", json.dumps(json_schema),
        "--allowedTools", "",
    ]
    _assert_no_bare(cmd)
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd, input=user_message, capture_output=True, text=True,
        timeout=timeout_s,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return proc.returncode, proc.stdout, proc.stderr, cmd, elapsed_ms


def _parse_payload(
    stdout: str, stderr: str, rc: int, cmd: list[str], prompt_id: str | None
) -> dict:
    if rc != 0:
        raise HaltError(
            f"claude rc={rc}: {stderr.strip()[:600]}",
            last_cmd=cmd, last_prompt_id=prompt_id,
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise HaltError(
            f"failed to parse claude JSON: {exc}; head: {stdout[:400]!r}",
            last_cmd=cmd, last_prompt_id=prompt_id,
        ) from exc
    if payload.get("is_error"):
        raise HaltError(
            f"claude is_error=true: {payload.get('result')!r}; "
            f"subtype={payload.get('subtype')!r}",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        )
    return payload


def _extract_model_version(payload: dict, cmd: list[str], prompt_id: str | None) -> str:
    """Return the model id that actually produced the response.

    Claude Code's auto-mode classifier adds a tiny-output prelude entry to
    modelUsage alongside the model that produced the answer. Selecting by
    largest outputTokens picks the responding model, not the classifier.
    Tie-break by longest key to prefer dated ids over base aliases when
    output-token counts are equal.

    Raises HaltError if modelUsage is empty.
    """
    usage = payload.get("modelUsage") or {}
    if not usage:
        raise HaltError(
            "claude response has empty modelUsage; cannot determine model version",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        )
    return sorted(
        usage.keys(),
        key=lambda k: (int((usage[k] or {}).get("outputTokens") or 0), len(k)),
        reverse=True,
    )[0]


def _extract_structured_output(
    payload: dict, cmd: list[str], prompt_id: str | None
) -> dict:
    so = payload.get("structured_output")
    if isinstance(so, dict):
        return so
    result_str = payload.get("result", "")
    try:
        parsed = json.loads(result_str) if result_str else None
    except json.JSONDecodeError as exc:
        raise HaltError(
            f"no structured_output and result not JSON: {exc}; "
            f"result head={result_str[:300]!r}",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        ) from exc
    if not isinstance(parsed, dict):
        raise HaltError(
            "structured_output absent and result is not a JSON object",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        )
    return parsed


class ClaudeCodeBackend(ModelBackend):
    """Backend using the ``claude -p`` subprocess via Max-plan OAuth."""

    def name(self) -> str:
        return "claude-code"

    def call(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        output_schema: dict,
        max_tokens: int,
        temperature: float = 0,
    ) -> ModelResponse:
        # Write system_prompt to a temp file; CLI requires --system-prompt-file.
        # max_tokens and temperature are not exposed via the claude CLI flags;
        # they're included in the interface for API-backend parity.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(system_prompt)
            sp_path = Path(tf.name)
        try:
            return self._call_with_retry(
                model=model, sp_path=sp_path,
                user_message=user_message, output_schema=output_schema,
                prompt_id=None,
            )
        finally:
            sp_path.unlink(missing_ok=True)

    def _call_with_retry(
        self,
        *,
        model: str,
        sp_path: Path,
        user_message: str,
        output_schema: dict,
        prompt_id: str | None,
    ) -> ModelResponse:
        rc, stdout, stderr, cmd, elapsed_ms = _run_subprocess(
            model=model, system_prompt_path=sp_path,
            json_schema=output_schema, user_message=user_message,
        )

        # Retry once on subprocess failure.
        if rc != 0:
            time.sleep(30)
            rc, stdout, stderr, cmd, elapsed_ms = _run_subprocess(
                model=model, system_prompt_path=sp_path,
                json_schema=output_schema, user_message=user_message,
            )

        payload = _parse_payload(stdout, stderr, rc, cmd, prompt_id)
        model_version = _extract_model_version(payload, cmd, prompt_id)
        structured = _extract_structured_output(payload, cmd, prompt_id)

        # Validate; retry the full call once on schema failure.
        try:
            jsonschema.validate(structured, output_schema)
        except jsonschema.ValidationError:
            time.sleep(30)
            rc2, stdout2, stderr2, cmd2, elapsed_ms2 = _run_subprocess(
                model=model, system_prompt_path=sp_path,
                json_schema=output_schema, user_message=user_message,
            )
            payload = _parse_payload(stdout2, stderr2, rc2, cmd2, prompt_id)
            model_version = _extract_model_version(payload, cmd2, prompt_id)
            structured = _extract_structured_output(payload, cmd2, prompt_id)
            try:
                jsonschema.validate(structured, output_schema)
            except jsonschema.ValidationError as exc:
                raise HaltError(
                    f"schema validation failed on retry: {exc.message}; "
                    f"path={list(exc.absolute_path)}",
                    last_cmd=cmd2, last_response=structured,
                    last_prompt_id=prompt_id,
                ) from exc
            elapsed_ms = elapsed_ms2
            cmd = cmd2

        usage = payload.get("usage") or {}
        raw = dict(payload)
        raw["command_line"] = cmd

        return ModelResponse(
            answer_text=(structured.get("answer_text") or ""),
            structured_output=structured,
            raw_response=raw,
            model_version=model_version,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            latency_ms=elapsed_ms,
            backend_name="claude-code",
        )

    def capture_environment(self) -> dict:
        info: dict = {"backend": "claude-code"}

        try:
            info["git_commit"] = _git(["rev-parse", "HEAD"])
        except Exception:
            info["git_commit"] = None

        try:
            tags = _git(["tag", "--points-at", "HEAD"]).splitlines()
            info["tags_at_head"] = tags
        except Exception:
            info["tags_at_head"] = None

        try:
            out = subprocess.run(
                ["claude", "--help"], capture_output=True, text=True, timeout=15,
            )
            info["claude_help_head"] = "\n".join(out.stdout.splitlines()[:40])
        except Exception as exc:
            info["claude_help_head"] = f"unavailable: {exc}"

        for label, p in [
            ("claude_md_repo", _REPO / "CLAUDE.md"),
            ("claude_md_user", Path.home() / ".claude" / "CLAUDE.md"),
        ]:
            p_obj = Path(str(p))
            info[label] = p_obj.read_text() if p_obj.exists() else None

        env_names = sorted(
            k for k in os.environ
            if k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_")
        )
        info["env_names_no_values"] = env_names

        return info

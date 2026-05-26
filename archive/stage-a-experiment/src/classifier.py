"""Claim-family classifier for the LLM-in-the-loop closing experiment.

Shells out to Claude Code in headless mode to classify a natural-language
operator question into one of {OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE}.

Auth is via the user's interactive Claude Code OAuth (Max plan). The
`--bare` flag is deliberately NOT used here so that OAuth/keychain auth
is permitted; the system prompt is supplied via --system-prompt-file
which overrides Claude Code's default dynamic system prompt, preserving
most of the reproducibility that `--bare` would have provided.

The module does NOT auto-source ``.env``: under OAuth no key is needed,
and the placeholder value in a stub ``.env`` would otherwise overwrite
the real auth path. If you switch back to ``--bare`` later, export the
key in the parent shell before invoking the classifier.

Every call is appended as one JSONL line to
``experiment/logs/classifier/<YYYY-MM-DD_HHMMSS>.jsonl`` so the full
response (including the model identifier from ``modelUsage``) is
recoverable post-hoc.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

FAMILIES = ("OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE")
Family = Literal["OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE"]

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "experiment" / "configs" / "classifier_system_prompt.txt"
LOG_DIR = REPO_ROOT / "experiment" / "logs" / "classifier"

EXPECTED_MODEL_PREFIX = "claude-haiku-4-5"
MODEL_ARG = "claude-haiku-4-5"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "family": {
            "type": "string",
            "enum": list(FAMILIES),
        }
    },
    "required": ["family"],
}


class ClassifierError(RuntimeError):
    """Any unrecoverable problem in the classifier call. Caller should halt."""


@dataclass(frozen=True)
class ClassifierResult:
    prompt_text: str
    family: Family
    model_served: str             # exact id reported by modelUsage (e.g. claude-haiku-4-5-20251001)
    duration_ms: int
    session_id: str
    raw_response: dict            # full claude -p JSON payload


def _resolve_claude_binary() -> str:
    binary = shutil.which("claude")
    if not binary:
        raise ClassifierError("`claude` CLI not found on PATH")
    return binary


def _extract_model_served(payload: dict) -> str:
    """Pull the dated model id from the ``modelUsage`` dict.

    Claude Code returns ``modelUsage`` keyed by served model strings;
    we pick the dated variant (e.g. ``claude-haiku-4-5-20251001``) if
    present, otherwise fall back to the alias.
    """
    usage = payload.get("modelUsage") or {}
    if not usage:
        return ""
    dated = [k for k in usage.keys() if k.startswith(EXPECTED_MODEL_PREFIX) and k != EXPECTED_MODEL_PREFIX]
    if dated:
        return dated[0]
    if EXPECTED_MODEL_PREFIX in usage:
        return EXPECTED_MODEL_PREFIX
    return next(iter(usage.keys()))


def _log_line(log_path: Path, record: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def classify_prompt(text: str, *, log_path: Path | None = None) -> ClassifierResult:
    """Classify a natural-language operator question into a claim family.

    Halts (raises ``ClassifierError``) on:
      - missing ``claude`` binary
      - non-zero exit from the headless call
      - JSON parse failure on the headless response
      - ``is_error: true`` flag in the response
      - served model not starting with ``claude-haiku-4-5``
      - parsed ``result`` not a JSON object matching the output schema
    """
    if not CONFIG_PATH.exists():
        raise ClassifierError(f"system prompt file missing: {CONFIG_PATH}")

    binary = _resolve_claude_binary()
    if log_path is None:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        log_path = LOG_DIR / f"{ts}.jsonl"

    cmd = [
        binary,
        "-p",
        "--model", MODEL_ARG,
        "--system-prompt-file", str(CONFIG_PATH),
        "--output-format", "json",
        "--json-schema", json.dumps(OUTPUT_SCHEMA),
        "--allowedTools", "",
    ]

    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        input=text,
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if proc.returncode != 0:
        raise ClassifierError(
            f"claude headless exited with code {proc.returncode}: {proc.stderr.strip()[:500]}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ClassifierError(
            f"failed to parse claude headless JSON: {exc}; raw stdout head: {proc.stdout[:300]!r}"
        ) from exc

    if payload.get("is_error"):
        raise ClassifierError(
            f"claude headless reported is_error=true: result={payload.get('result')!r}"
        )

    model_served = _extract_model_served(payload)
    if not model_served.startswith(EXPECTED_MODEL_PREFIX):
        raise ClassifierError(
            f"served model {model_served!r} does not start with expected prefix "
            f"{EXPECTED_MODEL_PREFIX!r}; halting"
        )

    structured = payload.get("structured_output")
    if isinstance(structured, dict) and "family" in structured:
        family = structured["family"]
    else:
        # Fallback: some Claude Code versions place the JSON object in
        # ``result`` instead of (or as well as) ``structured_output``.
        result_str = payload.get("result", "")
        try:
            parsed = json.loads(result_str) if result_str else {}
        except json.JSONDecodeError as exc:
            raise ClassifierError(
                f"no structured_output and result not parseable: {exc}; "
                f"raw result: {result_str!r}"
            ) from exc
        family = parsed.get("family") if isinstance(parsed, dict) else None

    if family not in FAMILIES:
        raise ClassifierError(
            f"family field {family!r} not in allowed set {FAMILIES}; "
            f"structured_output={structured!r} result={payload.get('result')!r}"
        )

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "prompt_text": text,
        "family": family,
        "model_served": model_served,
        "wallclock_ms": elapsed_ms,
        "session_id": payload.get("session_id"),
        "duration_ms_claude": payload.get("duration_ms"),
        "duration_api_ms_claude": payload.get("duration_api_ms"),
        "raw_response": payload,
    }
    _log_line(log_path, record)

    return ClassifierResult(
        prompt_text=text,
        family=family,
        model_served=model_served,
        duration_ms=elapsed_ms,
        session_id=payload.get("session_id", ""),
        raw_response=payload,
    )


if __name__ == "__main__":
    text = sys.stdin.read().strip() if not sys.stdin.isatty() else " ".join(sys.argv[1:])
    if not text:
        print("usage: classifier.py <prompt> | echo '<prompt>' | classifier.py", file=sys.stderr)
        sys.exit(2)
    try:
        result = classify_prompt(text)
    except ClassifierError as exc:
        print(f"classifier halted: {exc}", file=sys.stderr)
        sys.exit(1)
    print(result.family)

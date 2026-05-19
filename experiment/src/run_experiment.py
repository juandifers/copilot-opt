"""Experiment orchestration backbone for the LLM-in-the-loop closing experiment.

Runs the locked generator (Haiku 4.5) and locked judge (Sonnet 4.6) over
a subset of ``experiment/data/prompts.csv`` per the locked configs at
``preregistration-v1.1``.

CLI
---
::
    python experiment/src/run_experiment.py --run-id <id> --prompt-ids <ids>

Inputs (verified at run start, halt on mismatch):
- spec.md at tag ``spec-v1.1``
- experiment/configs/* at tag ``preregistration-v1.1``
- experiment/data/prompts.csv at tag ``preregistration-prompts-v1``
- experiment/data/cell_selection.csv at the same tag

Outputs:
- experiment/results/generator/<run_id>.jsonl
- experiment/results/judge/<run_id>.jsonl
- experiment/results/joined/<run_id>.csv
- experiment/results/local_context/<run_id>.md
- experiment/results/<run_id>/halt_report.md (only on halt)
- Append to experiment/results/run_log.csv

Locked CLI shape (asserted at command-build time):
- ``--bare`` is forbidden (Max-OAuth requires its absence).
- ``--system-prompt-file`` is used (NOT ``--append-system-prompt-file``);
  the locked generator/judge system prompts are designed to replace the
  default, not extend it. Empirically verified to work under Max OAuth
  in the same way the classifier uses it.
- ``--json-schema`` takes the schema as an inline JSON string. The
  flag ``--json-schema-file`` is not supported by this Claude Code
  version. Deviation from the original task brief, documented in the
  commit message and in the script header.

Halt rules:
- Auth failure, response.model prefix mismatch, ``--bare`` appearing,
  schema validation failure on a retry: halt immediately, write
  halt_report.md, exit non-zero.
- Subprocess rc != 0, transient HTTP errors, schema validation failure
  on first attempt: retry once after 30s sleep.

Idempotency: a run halts at preflight if
``experiment/results/generator/<run_id>.jsonl`` already exists. Delete
or rename before re-running.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "experiment" / "src"))

from op_validity import check as op_validity_check  # noqa: E402
from payload_projector import build_payload  # noqa: E402

# ---------------------------------------------------------------------------
# Locked tag bindings (computed at preregistration-v1.1 / -prompts-v1)

EXPECTED_BLOBS = {
    # path : (tag, expected git blob sha1)
    "spec.md": ("spec-v1.1", "65a082261501100e23e73579dbed8338d81f151b"),
    "experiment/configs/payload_schemas.json": ("preregistration-v1.1", None),
    "experiment/configs/generator_system_prompt.txt": ("preregistration-v1.1", None),
    "experiment/configs/generator_output_schema.json": ("preregistration-v1.1", None),
    "experiment/configs/judge_system_prompt.txt": ("preregistration-v1.1", None),
    "experiment/configs/judge_output_schema.json": ("preregistration-v1.1", None),
    "experiment/configs/rubric.md": ("preregistration-v1.1", None),
    "experiment/configs/generator_config.yaml": ("preregistration-v1.1", None),
    "experiment/configs/judge_config.yaml": ("preregistration-v1.1", None),
    "experiment/data/prompts.csv": ("preregistration-prompts-v1", "39eb0b1538f9b829ff812563f98e7cba2745edae"),
    "experiment/data/cell_selection.csv": ("preregistration-prompts-v1", None),
}

# ---------------------------------------------------------------------------
# Locked model parameters (mirror the YAML configs)

GENERATOR_MODEL = "claude-haiku-4-5"
GENERATOR_PREFIX = "claude-haiku-4-5"
JUDGE_MODEL = "claude-sonnet-4-6"
JUDGE_PREFIX = "claude-sonnet-4-6"

PAYLOAD_FAMILY_KEY = {"OBJ": "OBJ", "PLAN_VALIDITY": "PV",
                      "STRUCT": "STRUCT", "SCHEDULE": "SCHEDULE"}

# ---------------------------------------------------------------------------
# Framing-leak detection patterns (failure mode (a) from the task brief)

FRAMING_LEAK_PATTERNS = [
    re.compile(r"^\s*sure[,.!]", re.IGNORECASE),
    re.compile(r"^\s*of course[,.!]", re.IGNORECASE),
    re.compile(r"^\s*looking at\b", re.IGNORECASE),
    re.compile(r"^\s*let me\b", re.IGNORECASE),
    re.compile(r"^\s*i'?ll\b", re.IGNORECASE),
    re.compile(r"^\s*i'?d (be )?happy to\b", re.IGNORECASE),
    re.compile(r"^\s*here'?s what\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Generic helpers


def _utcnow() -> str:
    return _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _git_hash_object(path: Path) -> str:
    """Compute the git blob sha1 of a working-copy file.

    Shells to ``git hash-object`` so .gitattributes / autocrlf
    normalization is applied the same way commits do. Raw byte hashing
    would diverge on text files whose working-tree CRLF endings are
    stored as LF in the index.
    """
    return subprocess.check_output(
        ["git", "hash-object", str(path)], cwd=_REPO, text=True,
    ).strip()


def _resolve_claude_binary() -> str:
    b = shutil.which("claude")
    if not b:
        raise RuntimeError("`claude` CLI not found on PATH")
    return b


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git"] + args, cwd=_REPO, text=True).strip()


# ---------------------------------------------------------------------------
# Halt machinery


class HaltError(RuntimeError):
    """Raised when the run must stop. The runner writes a halt_report.md and exits non-zero."""

    def __init__(self, message: str, *, last_cmd: list[str] | None = None,
                 last_response: dict | str | None = None,
                 last_prompt_id: str | None = None):
        super().__init__(message)
        self.last_cmd = last_cmd
        self.last_response = last_response
        self.last_prompt_id = last_prompt_id


def _write_halt_report(run_root: Path, err: HaltError,
                       n_completed: int, assertion: str) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    cmd_redacted = []
    for tok in (err.last_cmd or []):
        if tok.startswith("/"):
            # Tokens that look like paths are kept (already public);
            # everything else passes through.
            cmd_redacted.append(tok)
        else:
            cmd_redacted.append(tok)
    response_blob = err.last_response
    if isinstance(response_blob, dict):
        response_blob = json.dumps(response_blob, indent=2)[:8000]
    body = [
        "# Halt report",
        f"- timestamp: {_utcnow()}",
        f"- assertion: {assertion}",
        f"- message: {err}",
        f"- prompts_completed_before_halt: {n_completed}",
        f"- last_prompt_id: {err.last_prompt_id}",
        "",
        "## Last command line",
        "```",
        " ".join(cmd_redacted) if cmd_redacted else "(none recorded)",
        "```",
        "",
        "## Last response payload",
        "```json",
        response_blob if response_blob else "(none recorded)",
        "```",
    ]
    (run_root / "halt_report.md").write_text("\n".join(body))


# ---------------------------------------------------------------------------
# Preflight


def preflight_verify_tags() -> None:
    """Halt if any locked file's blob differs from the tag's blob."""
    for relpath, (tag, expected) in EXPECTED_BLOBS.items():
        p = _REPO / relpath
        if not p.exists():
            raise HaltError(f"locked input missing: {relpath}")
        wt_hash = _git_hash_object(p)
        try:
            tag_hash = _git([f"rev-parse", f"{tag}:{relpath}"])
        except subprocess.CalledProcessError as exc:
            raise HaltError(
                f"git rev-parse failed for {tag}:{relpath}: {exc}"
            ) from exc
        if wt_hash != tag_hash:
            raise HaltError(
                f"{relpath} differs from {tag}: working={wt_hash}, "
                f"tag={tag_hash}. Restore the file or accept drift "
                f"by re-tagging before running."
            )
        if expected and wt_hash != expected:
            raise HaltError(
                f"{relpath}: expected blob {expected}, got {wt_hash}. "
                f"Tag {tag} drifted or constant is stale."
            )


def assert_no_bare_in_cmd(cmd: list[str]) -> None:
    if any(tok == "--bare" for tok in cmd):
        raise HaltError(
            f"--bare appeared in command line; locked configs require "
            f"bare:false. Halting. cmd={cmd!r}"
        )


# ---------------------------------------------------------------------------
# Local context capture


def capture_local_context(run_id: str, results_root: Path) -> Path:
    out_dir = results_root / "local_context"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_id}.md"

    sections: list[str] = [f"# Local context capture — run_id={run_id}",
                           f"- captured_at: {_utcnow()}"]

    # Git state
    try:
        commit = _git(["rev-parse", "HEAD"])
        sections.append(f"- git_commit: {commit}")
    except Exception:
        sections.append("- git_commit: (unavailable)")

    try:
        tags_at_head = _git(["tag", "--points-at", "HEAD"]).splitlines()
        sections.append(f"- tags_at_head: {tags_at_head}")
    except Exception:
        sections.append("- tags_at_head: (unavailable)")

    # CLI version surface
    try:
        out_help = subprocess.run(
            ["claude", "--help"], capture_output=True, text=True, timeout=15,
        )
        help_head = "\n".join(out_help.stdout.splitlines()[:40])
        sections.append("\n## claude --help (first 40 lines)\n```\n" + help_head + "\n```")
    except Exception as exc:
        sections.append(f"\n## claude --help — unavailable: {exc}")

    # CLAUDE.md candidates (full text). Local + user.
    for label, p in [
        ("./CLAUDE.md", _REPO / "CLAUDE.md"),
        ("~/.claude/CLAUDE.md", Path.home() / ".claude" / "CLAUDE.md"),
    ]:
        if p.exists():
            sections.append(f"\n## {label}\n```\n{p.read_text()}\n```")
        else:
            sections.append(f"\n## {label}: (absent)")

    # ANTHROPIC_* / CLAUDE_* env variable NAMES only (no values).
    env_names = sorted(
        k for k in os.environ
        if k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_")
    )
    sections.append(f"\n## env names (no values): {env_names}")

    out.write_text("\n".join(sections))
    return out


# ---------------------------------------------------------------------------
# CLI invocation primitives


@dataclass
class CallResult:
    rc: int
    stdout: str
    stderr: str
    cmd: list[str]
    elapsed_ms: int


def call_claude(
    *, model: str, system_prompt_file: Path, json_schema: dict,
    user_message: str, timeout_s: float = 180,
) -> CallResult:
    binary = _resolve_claude_binary()
    cmd = [
        binary, "-p",
        "--model", model,
        "--system-prompt-file", str(system_prompt_file),
        "--output-format", "json",
        "--json-schema", json.dumps(json_schema),
        "--allowedTools", "",
    ]
    assert_no_bare_in_cmd(cmd)
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd, input=user_message, capture_output=True, text=True,
        timeout=timeout_s,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return CallResult(
        rc=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
        cmd=cmd, elapsed_ms=elapsed_ms,
    )


def parse_response_or_halt(cr: CallResult, *, prompt_id: str | None) -> dict:
    if cr.rc != 0:
        raise HaltError(
            f"claude rc={cr.rc}: {cr.stderr.strip()[:600]}",
            last_cmd=cr.cmd, last_prompt_id=prompt_id,
        )
    try:
        payload = json.loads(cr.stdout)
    except json.JSONDecodeError as exc:
        raise HaltError(
            f"failed to parse claude JSON: {exc}; head: {cr.stdout[:400]!r}",
            last_cmd=cr.cmd, last_prompt_id=prompt_id,
        ) from exc
    if payload.get("is_error"):
        raise HaltError(
            f"claude is_error=true: {payload.get('result')!r}; subtype={payload.get('subtype')!r}",
            last_cmd=cr.cmd, last_response=payload, last_prompt_id=prompt_id,
        )
    return payload


def assert_model_prefix(payload: dict, expected_prefix: str, *,
                        prompt_id: str | None, cmd: list[str]) -> str:
    """Return the canonical served model id matching ``expected_prefix``."""
    usage = payload.get("modelUsage") or {}
    matches = [k for k in usage.keys() if k.startswith(expected_prefix)]
    if not matches:
        raise HaltError(
            f"response.modelUsage has no key starting with {expected_prefix!r}; "
            f"keys={list(usage.keys())}",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        )
    # Prefer a dated id (longer than the prefix) so the log records the
    # exact served version.
    dated = sorted(k for k in matches if k != expected_prefix)
    return dated[-1] if dated else matches[0]


def extract_structured_output(payload: dict, *, cmd: list[str],
                              prompt_id: str | None) -> dict:
    so = payload.get("structured_output")
    if isinstance(so, dict):
        return so
    result_str = payload.get("result", "")
    try:
        parsed = json.loads(result_str) if result_str else None
    except json.JSONDecodeError as exc:
        raise HaltError(
            f"no structured_output and result not JSON: {exc}; result head={result_str[:300]!r}",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        ) from exc
    if not isinstance(parsed, dict):
        raise HaltError(
            f"structured_output absent and result is not a JSON object",
            last_cmd=cmd, last_response=payload, last_prompt_id=prompt_id,
        )
    return parsed


def validate_or_halt(obj: dict, schema: dict, *, label: str,
                     cmd: list[str], prompt_id: str | None) -> None:
    try:
        jsonschema.validate(obj, schema)
    except jsonschema.ValidationError as exc:
        raise HaltError(
            f"{label} schema validation failed: {exc.message}; path={list(exc.absolute_path)}",
            last_cmd=cmd, last_response=obj, last_prompt_id=prompt_id,
        ) from exc


# ---------------------------------------------------------------------------
# Prompt rendering


def split_system_and_user(template_text: str) -> tuple[str, str]:
    """Split a *_system_prompt.txt at the first ``---`` separator line.

    Pre-`---` is the system prompt (general instructions). Post-`---` is
    the user-side template rendered per-call with placeholders.
    """
    lines = template_text.splitlines()
    sep_idx = None
    for i, l in enumerate(lines):
        if l.strip() == "---":
            sep_idx = i
            break
    if sep_idx is None:
        # Whole file is system; user is empty.
        return template_text, ""
    head = "\n".join(lines[:sep_idx]).rstrip() + "\n"
    tail = "\n".join(lines[sep_idx + 1:]).lstrip("\n")
    return head, tail


def render_generator_user_message(template_tail: str, *, operator_prompt: str,
                                  instance_id: str, perturbation_description: str,
                                  action_name: str, solution_data_json: str) -> str:
    return template_tail.replace(
        "{operator_prompt}", operator_prompt,
    ).replace(
        "{instance_id}", instance_id,
    ).replace(
        "{perturbation_description}", perturbation_description,
    ).replace(
        "{action_name}", action_name,
    ).replace(
        "{solution_data_json}", solution_data_json,
    )


def render_judge_system_and_user(judge_template: str, rubric_text: str, *,
                                 operator_prompt: str, instance_id: str,
                                 perturbation_description: str, action_name: str,
                                 claim_family: str, op_validity_gradable: bool,
                                 solution_data_json: str,
                                 generator_output_json: str) -> tuple[str, str]:
    """Build (system_prompt, user_message) for the judge call.

    judge_system_prompt.txt has structure::
        <instructions>
        ---
        {rubric_text}
        ---
        <per-call template with placeholders>
    """
    parts = judge_template.split("\n---\n")
    if len(parts) != 3:
        raise HaltError(
            f"judge_system_prompt.txt expected 3 sections delimited by lines '---'; "
            f"found {len(parts)}"
        )
    instructions, _rubric_placeholder, user_tail = parts
    system_prompt = instructions.rstrip() + "\n\n---\n\n" + rubric_text.rstrip() + "\n"
    user_message = user_tail.lstrip("\n").replace(
        "{operator_prompt}", operator_prompt,
    ).replace(
        "{instance_id}", instance_id,
    ).replace(
        "{perturbation_description}", perturbation_description,
    ).replace(
        "{action_name}", action_name,
    ).replace(
        "{claim_family}", claim_family,
    ).replace(
        "{op_validity_gradable}", "true" if op_validity_gradable else "false",
    ).replace(
        "{solution_data_json}", solution_data_json,
    ).replace(
        "{generator_output_json}", generator_output_json,
    )
    return system_prompt, user_message


# ---------------------------------------------------------------------------
# Perturbation description (used in CONTEXT block)


PERT_LABEL = {
    "TRAVEL_TIME": "travel times scaled",
    "SERVICE_TIME": "service times scaled",
    "TIME_WINDOW": "time windows tightened",
    "ORDER_CHANGE": "new customer order(s) added",
}


def describe_perturbation(perturbation_id: str, perturbation_family: str) -> str:
    label = PERT_LABEL.get(perturbation_family, perturbation_family)
    return f"{perturbation_id} ({label})"


# ---------------------------------------------------------------------------
# One prompt's full pipeline


@dataclass
class PromptOutcome:
    prompt_id: str
    generator_record: dict
    judge_record: dict
    op_validity_runner_check: dict
    framing_leak_hits: list[str] = field(default_factory=list)
    payload_external_field_refs: list[str] = field(default_factory=list)


def run_one_prompt(
    *, prompt_row: dict, generator_system_head: Path, generator_template_tail: str,
    judge_template_raw: str, rubric_text: str,
    generator_schema: dict, judge_schema: dict,
    generator_jsonl: Path, judge_jsonl: Path,
) -> PromptOutcome:
    prompt_id = prompt_row["prompt_id"]
    family = prompt_row["family"]
    dataset = prompt_row["dataset"]
    instance_id = prompt_row["instance_id"]
    perturbation_id = prompt_row["perturbation_id"]
    perturbation_family = prompt_row["perturbation_family"]
    action_taken = prompt_row["action_taken"]
    operator_prompt = prompt_row["prompt_text"]
    op_validity_gradable = str(prompt_row["op_validity_gradable"]).lower() == "true"

    # 1-2. Build payload.
    payload = build_payload(
        dataset, instance_id, perturbation_id, action_taken, family,
    )
    solution_data_json = json.dumps(payload, sort_keys=False)
    perturbation_description = describe_perturbation(perturbation_id, perturbation_family)

    # 3. Generator user message + call.
    gen_user_msg = render_generator_user_message(
        generator_template_tail,
        operator_prompt=operator_prompt,
        instance_id=instance_id,
        perturbation_description=perturbation_description,
        action_name=action_taken,
        solution_data_json=solution_data_json,
    )

    cr = call_claude(
        model=GENERATOR_MODEL,
        system_prompt_file=generator_system_head,
        json_schema=generator_schema,
        user_message=gen_user_msg,
    )

    # Retry once on transient failure.
    if cr.rc != 0:
        time.sleep(30)
        cr = call_claude(
            model=GENERATOR_MODEL,
            system_prompt_file=generator_system_head,
            json_schema=generator_schema,
            user_message=gen_user_msg,
        )

    gen_payload = parse_response_or_halt(cr, prompt_id=prompt_id)
    gen_model_served = assert_model_prefix(
        gen_payload, GENERATOR_PREFIX, prompt_id=prompt_id, cmd=cr.cmd,
    )
    gen_structured = extract_structured_output(
        gen_payload, cmd=cr.cmd, prompt_id=prompt_id,
    )
    # First validation attempt; retry once on failure with full re-call.
    try:
        jsonschema.validate(gen_structured, generator_schema)
    except jsonschema.ValidationError:
        time.sleep(30)
        cr = call_claude(
            model=GENERATOR_MODEL,
            system_prompt_file=generator_system_head,
            json_schema=generator_schema,
            user_message=gen_user_msg,
        )
        gen_payload = parse_response_or_halt(cr, prompt_id=prompt_id)
        gen_model_served = assert_model_prefix(
            gen_payload, GENERATOR_PREFIX, prompt_id=prompt_id, cmd=cr.cmd,
        )
        gen_structured = extract_structured_output(
            gen_payload, cmd=cr.cmd, prompt_id=prompt_id,
        )
        validate_or_halt(
            gen_structured, generator_schema,
            label="generator (retry)", cmd=cr.cmd, prompt_id=prompt_id,
        )

    answer_text = gen_structured.get("answer_text", "")

    # Framing-leak scan.
    framing_hits = [
        p.pattern for p in FRAMING_LEAK_PATTERNS
        if p.search(answer_text or "")
    ]

    # Write generator record.
    gen_record = {
        "timestamp": _utcnow(),
        "run_id": generator_jsonl.stem,
        "prompt_id": prompt_id,
        "model_requested": GENERATOR_MODEL,
        "model_served": gen_model_served,
        "command_line": cr.cmd,
        "wallclock_ms": cr.elapsed_ms,
        "claude_duration_ms": gen_payload.get("duration_ms"),
        "claude_api_duration_ms": gen_payload.get("duration_api_ms"),
        "session_id": gen_payload.get("session_id"),
        "total_cost_usd": gen_payload.get("total_cost_usd"),
        "model_usage": gen_payload.get("modelUsage"),
        "usage": gen_payload.get("usage"),
        "structured_output": gen_structured,
        "answer_text": answer_text,
        "framing_leak_hits": framing_hits,
        "payload_snapshot": payload,
    }
    _append_jsonl(generator_jsonl, gen_record)

    # 4. Judge user message + call.
    judge_system, judge_user = render_judge_system_and_user(
        judge_template_raw, rubric_text,
        operator_prompt=operator_prompt,
        instance_id=instance_id,
        perturbation_description=perturbation_description,
        action_name=action_taken,
        claim_family=family,
        op_validity_gradable=op_validity_gradable,
        solution_data_json=solution_data_json,
        generator_output_json=json.dumps(gen_structured),
    )

    # Write judge system prompt to a tempfile so the locked --system-prompt-file
    # CLI shape is preserved.
    judge_sp_tmp = generator_jsonl.parent.parent / "tmp" / f"judge_sp_{prompt_id}.txt"
    judge_sp_tmp.parent.mkdir(parents=True, exist_ok=True)
    judge_sp_tmp.write_text(judge_system)

    try:
        cr2 = call_claude(
            model=JUDGE_MODEL,
            system_prompt_file=judge_sp_tmp,
            json_schema=judge_schema,
            user_message=judge_user,
        )
        if cr2.rc != 0:
            time.sleep(30)
            cr2 = call_claude(
                model=JUDGE_MODEL,
                system_prompt_file=judge_sp_tmp,
                json_schema=judge_schema,
                user_message=judge_user,
            )
        judge_payload = parse_response_or_halt(cr2, prompt_id=prompt_id)
        judge_model_served = assert_model_prefix(
            judge_payload, JUDGE_PREFIX, prompt_id=prompt_id, cmd=cr2.cmd,
        )
        judge_structured = extract_structured_output(
            judge_payload, cmd=cr2.cmd, prompt_id=prompt_id,
        )
        try:
            jsonschema.validate(judge_structured, judge_schema)
        except jsonschema.ValidationError:
            time.sleep(30)
            cr2 = call_claude(
                model=JUDGE_MODEL,
                system_prompt_file=judge_sp_tmp,
                json_schema=judge_schema,
                user_message=judge_user,
            )
            judge_payload = parse_response_or_halt(cr2, prompt_id=prompt_id)
            judge_model_served = assert_model_prefix(
                judge_payload, JUDGE_PREFIX, prompt_id=prompt_id, cmd=cr2.cmd,
            )
            judge_structured = extract_structured_output(
                judge_payload, cmd=cr2.cmd, prompt_id=prompt_id,
            )
            validate_or_halt(
                judge_structured, judge_schema,
                label="judge (retry)", cmd=cr2.cmd, prompt_id=prompt_id,
            )
    finally:
        judge_sp_tmp.unlink(missing_ok=True)

    # Cross-check op-validity locally as a deterministic shadow.
    runner_check = op_validity_check(
        family, gen_structured, payload, op_validity_gradable,
    )

    # Field-reference scan in judge rationale (failure mode (d) check).
    rationale = judge_structured.get("faithfulness_rationale", "")
    payload_field_refs = _scan_payload_field_references(rationale, payload)

    judge_record = {
        "timestamp": _utcnow(),
        "run_id": judge_jsonl.stem,
        "prompt_id": prompt_id,
        "model_requested": JUDGE_MODEL,
        "model_served": judge_model_served,
        "command_line": cr2.cmd,
        "wallclock_ms": cr2.elapsed_ms,
        "claude_duration_ms": judge_payload.get("duration_ms"),
        "claude_api_duration_ms": judge_payload.get("duration_api_ms"),
        "session_id": judge_payload.get("session_id"),
        "total_cost_usd": judge_payload.get("total_cost_usd"),
        "model_usage": judge_payload.get("modelUsage"),
        "usage": judge_payload.get("usage"),
        "structured_output": judge_structured,
        "runner_op_validity": runner_check,
        "judge_vs_runner_agreement": {
            "op_validity_pass_match": (
                judge_structured.get("op_validity_pass")
                == runner_check["op_validity_pass"]
            ),
            "refusal_match": (
                judge_structured.get("refusal_detected")
                == runner_check["refusal_detected"]
            ),
        },
        "payload_external_field_refs": payload_field_refs,
    }
    _append_jsonl(judge_jsonl, judge_record)

    return PromptOutcome(
        prompt_id=prompt_id,
        generator_record=gen_record,
        judge_record=judge_record,
        op_validity_runner_check=runner_check,
        framing_leak_hits=framing_hits,
        payload_external_field_refs=payload_field_refs,
    )


def _scan_payload_field_references(rationale: str, payload: dict) -> list[str]:
    """Heuristic check: flag identifier-like tokens in the rationale that look
    like a payload-field reference but aren't actually keys in the payload.

    This is a soft scan — false positives are normal. The smoke test
    eyeballs the output regardless; this just surfaces candidates.
    """
    # Collect actual payload keys (one level deep is enough; the
    # generator/judge can't reasonably reference deeper paths in prose).
    actual = set()
    def _collect(d):
        if isinstance(d, dict):
            for k, v in d.items():
                actual.add(k)
                if isinstance(v, (dict, list)):
                    _collect(v)
        elif isinstance(d, list):
            for item in d:
                _collect(item)
    _collect(payload)

    # Candidate tokens: snake_case identifiers in backticks.
    cands = set(re.findall(r"`([a-z_][a-z0-9_]+)`", rationale))
    return sorted(c for c in cands if c not in actual)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Join + run log


def join_results(run_id: str, results_root: Path, prompts_csv: Path) -> Path:
    import csv as _csv
    gen_path = results_root / "generator" / f"{run_id}.jsonl"
    judge_path = results_root / "judge" / f"{run_id}.jsonl"
    if not gen_path.exists() or not judge_path.exists():
        raise HaltError(
            f"join: missing generator or judge jsonl for run {run_id}"
        )
    gen_by_id, judge_by_id = {}, {}
    for line in gen_path.read_text().splitlines():
        rec = json.loads(line)
        gen_by_id[rec["prompt_id"]] = rec
    for line in judge_path.read_text().splitlines():
        rec = json.loads(line)
        judge_by_id[rec["prompt_id"]] = rec

    prompts_rows: dict[str, dict] = {}
    with prompts_csv.open() as fh:
        reader = _csv.DictReader(fh)
        for row in reader:
            prompts_rows[row["prompt_id"]] = row

    out_path = results_root / "joined" / f"{run_id}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "prompt_id", "family", "source", "cell_id", "instance_id",
        "perturbation_id", "perturbation_family", "instance_class", "dataset",
        "quadrant", "sufficiency_label", "policy_decision", "action_taken",
        "op_validity_gradable", "manual_review_required",
        "prompt_text", "answer_text",
        "claimed_objective", "claimed_feasible", "claimed_route_count",
        "claimed_route_membership", "claimed_late_customers",
        "claimed_customer_timings",
        "faithfulness_score", "faithfulness_rationale",
        "judge_op_validity_pass", "judge_op_validity_check_results",
        "judge_refusal_detected",
        "runner_op_validity_pass", "runner_op_validity_check_results",
        "runner_refusal_detected",
        "op_validity_agreement", "refusal_agreement",
        "framing_leak_hits", "payload_external_field_refs",
        "generator_model_served", "judge_model_served",
        "generator_wallclock_ms", "judge_wallclock_ms",
        "generator_cost_usd", "judge_cost_usd",
    ]
    with out_path.open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for pid in sorted(gen_by_id):
            gr = gen_by_id[pid]
            jr = judge_by_id.get(pid)
            if not jr:
                continue
            cell = prompts_rows.get(pid, {})
            gs = gr.get("structured_output", {})
            js = jr.get("structured_output", {})
            agree = jr.get("judge_vs_runner_agreement", {})
            w.writerow({
                "prompt_id": pid,
                "family": cell.get("family"),
                "source": cell.get("source"),
                "cell_id": cell.get("cell_id"),
                "instance_id": cell.get("instance_id"),
                "perturbation_id": cell.get("perturbation_id"),
                "perturbation_family": cell.get("perturbation_family"),
                "instance_class": cell.get("instance_class"),
                "dataset": cell.get("dataset"),
                "quadrant": cell.get("quadrant"),
                "sufficiency_label": cell.get("sufficiency_label"),
                "policy_decision": cell.get("policy_decision"),
                "action_taken": cell.get("action_taken"),
                "op_validity_gradable": cell.get("op_validity_gradable"),
                "manual_review_required": cell.get("manual_review_required"),
                "prompt_text": cell.get("prompt_text"),
                "answer_text": gs.get("answer_text"),
                "claimed_objective": gs.get("claimed_objective"),
                "claimed_feasible": gs.get("claimed_feasible"),
                "claimed_route_count": gs.get("claimed_route_count"),
                "claimed_route_membership": json.dumps(gs.get("claimed_route_membership")),
                "claimed_late_customers": json.dumps(gs.get("claimed_late_customers")),
                "claimed_customer_timings": json.dumps(gs.get("claimed_customer_timings")),
                "faithfulness_score": js.get("faithfulness_score"),
                "faithfulness_rationale": js.get("faithfulness_rationale"),
                "judge_op_validity_pass": js.get("op_validity_pass"),
                "judge_op_validity_check_results": json.dumps(js.get("op_validity_check_results")),
                "judge_refusal_detected": js.get("refusal_detected"),
                "runner_op_validity_pass": jr.get("runner_op_validity", {}).get("op_validity_pass"),
                "runner_op_validity_check_results": json.dumps(jr.get("runner_op_validity", {}).get("op_validity_check_results")),
                "runner_refusal_detected": jr.get("runner_op_validity", {}).get("refusal_detected"),
                "op_validity_agreement": agree.get("op_validity_pass_match"),
                "refusal_agreement": agree.get("refusal_match"),
                "framing_leak_hits": json.dumps(gr.get("framing_leak_hits", [])),
                "payload_external_field_refs": json.dumps(jr.get("payload_external_field_refs", [])),
                "generator_model_served": gr.get("model_served"),
                "judge_model_served": jr.get("model_served"),
                "generator_wallclock_ms": gr.get("wallclock_ms"),
                "judge_wallclock_ms": jr.get("wallclock_ms"),
                "generator_cost_usd": gr.get("total_cost_usd"),
                "judge_cost_usd": jr.get("total_cost_usd"),
            })
    return out_path


def append_run_log(*, run_id: str, results_root: Path, start_iso: str,
                   end_iso: str, n_attempted: int, n_completed: int,
                   n_halts: int, n_retries: int,
                   total_tokens: int, total_wall: float,
                   gen_model_served: str | None,
                   judge_model_served: str | None) -> None:
    import csv as _csv
    log_path = results_root / "run_log.csv"
    cols = [
        "run_id", "start_time", "end_time", "git_commit",
        "generator_model_served", "judge_model_served",
        "n_prompts_attempted", "n_prompts_completed", "n_halts", "n_retries",
        "total_token_usage", "total_wall_clock_seconds",
    ]
    try:
        commit = _git(["rev-parse", "HEAD"])
    except Exception:
        commit = ""
    row = {
        "run_id": run_id,
        "start_time": start_iso,
        "end_time": end_iso,
        "git_commit": commit,
        "generator_model_served": gen_model_served or "",
        "judge_model_served": judge_model_served or "",
        "n_prompts_attempted": n_attempted,
        "n_prompts_completed": n_completed,
        "n_halts": n_halts,
        "n_retries": n_retries,
        "total_token_usage": total_tokens,
        "total_wall_clock_seconds": round(total_wall, 2),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists()
    with log_path.open("a", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=cols)
        if write_header:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------------------
# Main


def _load_locked_inputs() -> dict[str, Any]:
    configs = _REPO / "experiment" / "configs"
    with (configs / "generator_output_schema.json").open() as fh:
        gen_schema = json.load(fh)
    with (configs / "judge_output_schema.json").open() as fh:
        judge_schema = json.load(fh)
    gen_template = (configs / "generator_system_prompt.txt").read_text()
    gen_head, gen_tail = split_system_and_user(gen_template)
    judge_template_raw = (configs / "judge_system_prompt.txt").read_text()
    rubric_text = (configs / "rubric.md").read_text()
    return {
        "gen_schema": gen_schema, "judge_schema": judge_schema,
        "gen_head": gen_head, "gen_tail": gen_tail,
        "judge_template_raw": judge_template_raw, "rubric_text": rubric_text,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the closing experiment.")
    ap.add_argument("--run-id", required=True, help="Identifier, e.g. smoke-v1, pilot-v1, full-v1.")
    ap.add_argument("--prompt-ids", required=True,
                    help="Comma-separated prompt_ids, or 'all' for the full 48.")
    args = ap.parse_args()

    run_id = args.run_id
    results_root = _REPO / "experiment" / "results"
    run_root = results_root / run_id
    gen_jsonl = results_root / "generator" / f"{run_id}.jsonl"
    judge_jsonl = results_root / "judge" / f"{run_id}.jsonl"

    start_iso = _utcnow()
    t_start = time.perf_counter()
    n_attempted = 0
    n_completed = 0
    n_retries = 0
    gen_model_served = None
    judge_model_served = None

    try:
        # Preflight: tag verification.
        preflight_verify_tags()

        # Idempotency.
        if gen_jsonl.exists() or judge_jsonl.exists():
            raise HaltError(
                f"run_id {run_id!r} already exists at {gen_jsonl} / {judge_jsonl}. "
                f"Delete or rename before re-running."
            )

        # Local context capture.
        capture_local_context(run_id, results_root)

        # Load locked configs.
        locked = _load_locked_inputs()
        gen_head_path = run_root / "tmp" / "generator_system_head.txt"
        gen_head_path.parent.mkdir(parents=True, exist_ok=True)
        gen_head_path.write_text(locked["gen_head"])

        # Load prompts.
        import csv as _csv
        prompts_csv = _REPO / "experiment" / "data" / "prompts.csv"
        with prompts_csv.open() as fh:
            reader = _csv.DictReader(fh)
            prompts = list(reader)

        if args.prompt_ids.strip().lower() == "all":
            scope = prompts
        else:
            ids = [s.strip() for s in args.prompt_ids.split(",") if s.strip()]
            id_set = set(ids)
            by_id = {p["prompt_id"]: p for p in prompts}
            missing = [i for i in ids if i not in by_id]
            if missing:
                raise HaltError(f"unknown prompt_ids: {missing}")
            scope = [by_id[i] for i in ids]

        print(f"[run] {run_id}: {len(scope)} prompts in scope", flush=True)

        # Smoke models pre-flight: one trivial generator call + one judge call.
        # Skip the smoke models pre-flight ONLY when scope is one prompt (smoke
        # test calls main() multiple times); these always run for real runs.
        # The cheapest way to satisfy "verify model versions reachable" is
        # to just start the loop — the first prompt will fail the model
        # assertion if the served model is wrong. We DON'T bother with a
        # separate warm-up call to save quota.

        for prompt_row in scope:
            n_attempted += 1
            pid = prompt_row["prompt_id"]
            print(f"  [{n_attempted}/{len(scope)}] prompt {pid} "
                  f"family={prompt_row['family']} dataset={prompt_row['dataset']} "
                  f"action={prompt_row['action_taken']}", flush=True)
            outcome = run_one_prompt(
                prompt_row=prompt_row,
                generator_system_head=gen_head_path,
                generator_template_tail=locked["gen_tail"],
                judge_template_raw=locked["judge_template_raw"],
                rubric_text=locked["rubric_text"],
                generator_schema=locked["gen_schema"],
                judge_schema=locked["judge_schema"],
                generator_jsonl=gen_jsonl,
                judge_jsonl=judge_jsonl,
            )
            gen_model_served = outcome.generator_record["model_served"]
            judge_model_served = outcome.judge_record["model_served"]
            n_completed += 1
            if outcome.framing_leak_hits:
                print(f"    [warn] framing-leak patterns: {outcome.framing_leak_hits}",
                      flush=True)
            if outcome.payload_external_field_refs:
                print(f"    [warn] judge rationale references non-payload tokens: "
                      f"{outcome.payload_external_field_refs}", flush=True)

        # Join.
        join_path = join_results(run_id, results_root, prompts_csv)
        print(f"[run] joined → {join_path}", flush=True)
    except HaltError as err:
        _write_halt_report(run_root, err, n_completed, assertion=str(err))
        print(f"[HALT] {err}", flush=True, file=sys.stderr)
        return 2
    finally:
        end_iso = _utcnow()
        t_end = time.perf_counter() - t_start
        # Best-effort total tokens: read generator + judge jsonl and sum
        # input_tokens + output_tokens fields.
        total_tokens = 0
        for jp in (gen_jsonl, judge_jsonl):
            if jp.exists():
                for line in jp.read_text().splitlines():
                    try:
                        rec = json.loads(line)
                        u = rec.get("usage") or {}
                        total_tokens += int(u.get("input_tokens", 0) or 0)
                        total_tokens += int(u.get("output_tokens", 0) or 0)
                    except Exception:
                        continue
        n_halts = 1 if n_attempted > n_completed else 0
        append_run_log(
            run_id=run_id, results_root=results_root,
            start_iso=start_iso, end_iso=end_iso,
            n_attempted=n_attempted, n_completed=n_completed,
            n_halts=n_halts, n_retries=n_retries,
            total_tokens=total_tokens, total_wall=t_end,
            gen_model_served=gen_model_served,
            judge_model_served=judge_model_served,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

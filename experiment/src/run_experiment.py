"""Experiment orchestration backbone for the LLM-in-the-loop closing experiment.

Runs the locked generator (Haiku 4.5) and locked judge (Sonnet 4.6) over
a subset of ``experiment/data/prompts.csv`` per the locked configs at
``preregistration-v1.1``.

CLI
---
::
    python experiment/src/run_experiment.py --run-id <id> --prompt-ids <ids> \
        [--backend {claude-code,api}]

Inputs (verified at run start, halt on mismatch):
- spec.md at tag ``spec-v1.1``
- experiment/configs/* at tag ``preregistration-v1.1``
- experiment/data/prompts.csv at tag ``preregistration-prompts-v1``
- experiment/data/cell_selection.csv at the same tag

Outputs:
- experiment/results/generator/<run_id>.jsonl
- experiment/results/judge/<run_id>.jsonl
- experiment/results/joined/<run_id>.csv
- experiment/results/local_context/<run_id>.md        (claude-code backend)
- experiment/results/backend_environment/<run_id>.md  (api backend)
- experiment/results/<run_id>/halt_report.md (only on halt)
- Append to experiment/results/run_log.csv

Locked CLI shape for claude-code backend (asserted at command-build time):
- ``--bare`` is forbidden (Max-OAuth requires its absence).
- ``--system-prompt-file`` is used (NOT ``--append-system-prompt-file``);
  the locked generator/judge system prompts are designed to replace the
  default, not extend it.
- ``--json-schema`` takes the schema as an inline JSON string.

Halt rules:
- Auth failure, response.model prefix mismatch, ``--bare`` appearing,
  schema validation failure on a retry: halt immediately, write
  halt_report.md, exit non-zero.
- Subprocess rc != 0, transient HTTP errors, schema validation failure
  on first attempt: retry once after 30s sleep.

Idempotency: a run halts at preflight if
``experiment/results/generator/<run_id>.jsonl`` already exists.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "experiment" / "src"))

from backends.base import HaltError, ModelBackend, ModelResponse  # noqa: E402
from backends import get_backend  # noqa: E402
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

# max_tokens from generator_config.yaml; judge has no explicit limit so use
# a safe ceiling for Sonnet's rationale output.
GENERATOR_MAX_TOKENS = 1500
JUDGE_MAX_TOKENS = 2048

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
    """Compute the git blob sha1 of a working-copy file."""
    return subprocess.check_output(
        ["git", "hash-object", str(path)], cwd=_REPO, text=True,
    ).strip()


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git"] + args, cwd=_REPO, text=True).strip()


# ---------------------------------------------------------------------------
# Halt machinery


def _write_halt_report(run_root: Path, err: HaltError,
                       n_completed: int, assertion: str) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
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
        " ".join(err.last_cmd) if err.last_cmd else "(none recorded)",
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


# ---------------------------------------------------------------------------
# Environment capture


def _format_env_dict(run_id: str, env: dict) -> str:
    """Serialise a capture_environment() dict to a markdown document."""
    lines = [
        f"# Environment capture — run_id={run_id}",
        f"- captured_at: {_utcnow()}",
    ]
    for k, v in env.items():
        if isinstance(v, (dict, list)):
            lines.append(f"\n## {k}\n```json\n{json.dumps(v, indent=2)}\n```")
        elif isinstance(v, str) and "\n" in v:
            lines.append(f"\n## {k}\n```\n{v}\n```")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def write_environment_artifact(
    backend: ModelBackend, run_id: str, results_root: Path
) -> Path:
    env_info = backend.capture_environment()
    subdir = "local_context" if backend.name() == "claude-code" else "backend_environment"
    out_dir = results_root / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_id}.md"
    out.write_text(_format_env_dict(run_id, env_info))
    return out


# ---------------------------------------------------------------------------
# Prompt rendering


def split_system_and_user(template_text: str) -> tuple[str, str]:
    """Split a *_system_prompt.txt at the first ``---`` separator line."""
    lines = template_text.splitlines()
    sep_idx = None
    for i, l in enumerate(lines):
        if l.strip() == "---":
            sep_idx = i
            break
    if sep_idx is None:
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
    """Build (system_prompt, user_message) for the judge call."""
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
# Perturbation description


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
# Model version assertion (backend-agnostic)


def assert_model_version(
    response: ModelResponse,
    expected_prefix: str,
    *,
    prompt_id: str | None,
    role: str,
) -> None:
    """Halt if response.model_version does not start with expected_prefix."""
    if not response.model_version.startswith(expected_prefix):
        raise HaltError(
            f"{role} model version {response.model_version!r} does not start "
            f"with expected prefix {expected_prefix!r}",
            last_response=response.raw_response,
            last_prompt_id=prompt_id,
        )


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
    *,
    prompt_row: dict,
    backend: ModelBackend,
    generator_system_head: str,
    generator_template_tail: str,
    judge_template_raw: str,
    rubric_text: str,
    generator_schema: dict,
    judge_schema: dict,
    generator_jsonl: Path,
    judge_jsonl: Path,
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

    # 3. Generator call.
    gen_user_msg = render_generator_user_message(
        generator_template_tail,
        operator_prompt=operator_prompt,
        instance_id=instance_id,
        perturbation_description=perturbation_description,
        action_name=action_taken,
        solution_data_json=solution_data_json,
    )

    try:
        gen_response = backend.call(
            model=GENERATOR_MODEL,
            system_prompt=generator_system_head,
            user_message=gen_user_msg,
            output_schema=generator_schema,
            max_tokens=GENERATOR_MAX_TOKENS,
        )
    except HaltError as exc:
        if exc.last_prompt_id is None:
            exc.last_prompt_id = prompt_id
        raise

    assert_model_version(gen_response, GENERATOR_PREFIX, prompt_id=prompt_id, role="generator")

    gen_structured = gen_response.structured_output or {}
    answer_text = gen_response.answer_text

    # Framing-leak scan.
    framing_hits = [
        p.pattern for p in FRAMING_LEAK_PATTERNS
        if p.search(answer_text or "")
    ]

    # Write generator record.
    raw_gen = gen_response.raw_response
    gen_record = {
        "timestamp": _utcnow(),
        "run_id": generator_jsonl.stem,
        "prompt_id": prompt_id,
        "backend": backend.name(),
        "model_requested": GENERATOR_MODEL,
        "model_served": gen_response.model_version,
        "command_line": raw_gen.get("command_line"),
        "wallclock_ms": gen_response.latency_ms,
        "claude_duration_ms": raw_gen.get("duration_ms"),
        "claude_api_duration_ms": raw_gen.get("duration_api_ms"),
        "session_id": raw_gen.get("session_id"),
        "total_cost_usd": raw_gen.get("total_cost_usd"),
        "model_usage": raw_gen.get("modelUsage"),
        "usage": raw_gen.get("usage") or {
            "input_tokens": gen_response.input_tokens,
            "output_tokens": gen_response.output_tokens,
        },
        "structured_output": gen_structured,
        "answer_text": answer_text,
        "framing_leak_hits": framing_hits,
        "payload_snapshot": payload,
    }
    _append_jsonl(generator_jsonl, gen_record)

    # 4. Judge call.
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

    try:
        judge_response = backend.call(
            model=JUDGE_MODEL,
            system_prompt=judge_system,
            user_message=judge_user,
            output_schema=judge_schema,
            max_tokens=JUDGE_MAX_TOKENS,
        )
    except HaltError as exc:
        if exc.last_prompt_id is None:
            exc.last_prompt_id = prompt_id
        raise

    assert_model_version(judge_response, JUDGE_PREFIX, prompt_id=prompt_id, role="judge")

    judge_structured = judge_response.structured_output or {}

    # Cross-check op-validity locally as a deterministic shadow.
    runner_check = op_validity_check(
        family, gen_structured, payload, op_validity_gradable,
    )

    # Field-reference scan in judge rationale (failure mode (d) check).
    rationale = judge_structured.get("faithfulness_rationale", "")
    payload_field_refs = _scan_payload_field_references(rationale, payload)

    raw_judge = judge_response.raw_response
    judge_record = {
        "timestamp": _utcnow(),
        "run_id": judge_jsonl.stem,
        "prompt_id": prompt_id,
        "backend": backend.name(),
        "model_requested": JUDGE_MODEL,
        "model_served": judge_response.model_version,
        "command_line": raw_judge.get("command_line"),
        "wallclock_ms": judge_response.latency_ms,
        "claude_duration_ms": raw_judge.get("duration_ms"),
        "claude_api_duration_ms": raw_judge.get("duration_api_ms"),
        "session_id": raw_judge.get("session_id"),
        "total_cost_usd": raw_judge.get("total_cost_usd"),
        "model_usage": raw_judge.get("modelUsage"),
        "usage": raw_judge.get("usage") or {
            "input_tokens": judge_response.input_tokens,
            "output_tokens": judge_response.output_tokens,
        },
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
    """Heuristic: flag backtick-quoted tokens in rationale not in payload keys."""
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
        "backend",
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
                "backend": gr.get("backend", "claude-code"),
            })
    return out_path


def append_run_log(
    *,
    run_id: str,
    results_root: Path,
    start_iso: str,
    end_iso: str,
    n_attempted: int,
    n_completed: int,
    n_halts: int,
    n_retries: int,
    total_tokens: int,
    total_wall: float,
    gen_model_served: str | None,
    judge_model_served: str | None,
    backend_name: str = "claude-code",
) -> None:
    import csv as _csv
    log_path = results_root / "run_log.csv"
    cols = [
        "run_id", "start_time", "end_time", "git_commit",
        "backend",
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
        "backend": backend_name,
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
    ap.add_argument("--run-id", required=True,
                    help="Identifier, e.g. smoke-v1, pilot-v1, full-v1.")
    ap.add_argument("--prompt-ids", required=True,
                    help="Comma-separated prompt_ids, or 'all' for the full 48.")
    ap.add_argument("--backend", default="claude-code",
                    choices=["claude-code", "api"],
                    help="Execution backend (default: claude-code).")
    args = ap.parse_args()

    # Pre-flight: API key check for API backend.
    if args.backend == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[HALT] --backend api requires ANTHROPIC_API_KEY env var. "
            "Set it with: export ANTHROPIC_API_KEY='sk-ant-...'",
            file=sys.stderr,
        )
        return 2

    backend = get_backend(args.backend)

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

        # Capture environment.
        env_out = write_environment_artifact(backend, run_id, results_root)
        print(f"[run] environment captured → {env_out}", flush=True)

        # Load locked configs.
        locked = _load_locked_inputs()

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

        print(
            f"[run] {run_id}: {len(scope)} prompts in scope "
            f"(backend={backend.name()})",
            flush=True,
        )

        for prompt_row in scope:
            n_attempted += 1
            pid = prompt_row["prompt_id"]
            print(
                f"  [{n_attempted}/{len(scope)}] prompt {pid} "
                f"family={prompt_row['family']} dataset={prompt_row['dataset']} "
                f"action={prompt_row['action_taken']}",
                flush=True,
            )
            outcome = run_one_prompt(
                prompt_row=prompt_row,
                backend=backend,
                generator_system_head=locked["gen_head"],
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
                print(
                    f"    [warn] framing-leak patterns: {outcome.framing_leak_hits}",
                    flush=True,
                )
            if outcome.payload_external_field_refs:
                print(
                    f"    [warn] judge rationale references non-payload tokens: "
                    f"{outcome.payload_external_field_refs}",
                    flush=True,
                )

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
            backend_name=backend.name(),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

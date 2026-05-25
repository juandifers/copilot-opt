"""Run a Run 2 model baseline (System B prompt-only JSON).

CLI:

    python -m product.evaluation.run2_model_baseline_runner \\
      --cases product/evaluation/run2_benchmark_cases.csv \\
      --system B \\
      --provider openai \\
      --run-id run2-b-openai-gpt54mini-smoke \\
      --model gpt-5.4-mini \\
      --temperature 0 \\
      --max-cases 5

Outputs (under `product/evaluation/model_outputs/<run-id>/`):

    raw.jsonl       — one row per case: provider, model strings, raw
                       response text, token usage, latency, retry count,
                       error (if any), prompt hash.
    parsed.jsonl    — one row per case: parse_status, parser_notes,
                       predicted_* contract fields, answer_text.
    run_log.md      — summary of the run: model lock, counts, errors.

Idempotency: if any output file already exists the runner halts at
preflight. Delete or rename the run-id directory before re-running.

No locked experiment files are read or modified. No gold labels are
passed to the model. The model's API key is read from .env via
python-dotenv (or from the process environment); the key is never
printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from product.evaluation.model_clients.openai_client import (
    OpenAIKeyMissingError,
    call_openai_contract_model,
    load_openai_client,
)
from product.evaluation.run2_case_loader import (
    Run2Case,
    load_run2_cases,
    validate_all_cases,
)
from product.evaluation.run2_model_output_adapter import (
    parse_model_contract_json,
    parsed_output_to_dict,
)
from product.evaluation.run2_model_prompts import (
    build_prompt_only_json_prompt,
    build_system_a_prior_prompt,
)
from product.evaluation.run2_payloads import materialize_all_cases
from product.evaluation.run2_system_a_prior import build_system_a_prior


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run2_model_baseline_runner",
        description=(
            "Run a Run 2 model baseline (System B prompt-only JSON contract emitter)."
        ),
    )
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--system", required=True, choices=["A", "B"])
    p.add_argument("--provider", required=True, choices=["openai"])
    p.add_argument("--run-id", required=True, type=str)
    p.add_argument("--model", required=True, type=str)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-output-tokens", type=int, default=2048)
    p.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Smoke runs: only attempt the first N cases (after stable case-id sort).",
    )
    p.add_argument(
        "--case-ids",
        type=str,
        default=None,
        help=(
            "Comma-separated case IDs to attempt (overrides --max-cases). "
            "Used by the smoke task to pin a representative mix."
        ),
    )
    p.add_argument(
        "--outputs-dir",
        type=Path,
        default=Path("product/evaluation/model_outputs"),
        help="Parent directory for per-run output folders.",
    )
    p.add_argument(
        "--env-path",
        type=Path,
        default=None,
        help="Optional explicit path to a .env file (defaults to dotenv search).",
    )
    p.add_argument(
        "--no-response-format-json",
        action="store_true",
        help=(
            "If set, do NOT request response_format=json_object. Use only if "
            "the model rejects that knob."
        ),
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Per-call retry budget for transient OpenAI errors.",
    )
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class RunPaths:
    root: Path
    raw_jsonl: Path
    parsed_jsonl: Path
    run_log_md: Path


def _build_run_paths(outputs_dir: Path, run_id: str) -> RunPaths:
    root = outputs_dir / run_id
    return RunPaths(
        root=root,
        raw_jsonl=root / "raw.jsonl",
        parsed_jsonl=root / "parsed.jsonl",
        run_log_md=root / "run_log.md",
    )


def _hash_prompt(messages: list[dict]) -> str:
    encoded = json.dumps(messages, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _select_cases(
    cases: list[Run2Case],
    *,
    max_cases: Optional[int],
    case_ids_csv: Optional[str],
) -> list[Run2Case]:
    if case_ids_csv:
        wanted = {cid.strip() for cid in case_ids_csv.split(",") if cid.strip()}
        by_id = {c.case_id: c for c in cases}
        missing = sorted(wanted - by_id.keys())
        if missing:
            raise ValueError(f"--case-ids contains unknown ids: {missing}")
        selected = [by_id[cid] for cid in sorted(wanted)]
    else:
        # Stable case-id sort so a smoke run of N cases is reproducible.
        sorted_cases = sorted(cases, key=lambda c: c.case_id)
        selected = sorted_cases if max_cases is None else sorted_cases[:max_cases]
    return selected


def _preflight(paths: RunPaths) -> Optional[str]:
    for p in (paths.raw_jsonl, paths.parsed_jsonl, paths.run_log_md):
        if p.exists():
            return (
                f"output file already exists: {p}. "
                "Delete or rename the run-id directory before re-running."
            )
    return None


def _write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
            n += 1
    return n


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Per-case driver
# ---------------------------------------------------------------------------


def _build_messages_for_system(
    system: str, case: Run2Case, payload: dict
) -> tuple[list[dict], Optional[dict]]:
    """Dispatch the prompt builder by system label.

    Returns (messages, prior_dict_or_None). The prior dict is returned
    for System A only so the runner can record it on the raw row;
    System B returns None.
    """
    if system == "B":
        return build_prompt_only_json_prompt(case, payload), None
    if system == "A":
        prior = build_system_a_prior(case, payload)
        return build_system_a_prior_prompt(case, payload, prior), prior
    raise ValueError(f"unknown --system value: {system!r}")


def _run_one_case(
    *,
    client,
    case: Run2Case,
    payload: Optional[dict],
    materialization_status: str,
    materialization_warnings: list[str],
    system: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
    response_format_json: bool,
    max_retries: int,
) -> tuple[dict, dict]:
    """Run one case end-to-end and return (raw_row, parsed_row).

    Cases whose payload could not be materialised are recorded as raw
    rows with `materialization_status` != "materialized" and skipped
    on the model side; their parsed row carries `parse_status="error"`
    with a note explaining the skip.
    """
    if materialization_status != "materialized" or payload is None:
        raw_row = {
            "case_id": case.case_id,
            "provider": "openai",
            "system": system,
            "requested_model": model,
            "response_model": "",
            "materialization_status": materialization_status,
            "materialization_warnings": materialization_warnings,
            "skipped": True,
            "skip_reason": f"materialization_status={materialization_status}",
            "prompt_hash": "",
            "raw_response_text": "",
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "latency_seconds": None,
            "retry_count": 0,
            "finish_reason": None,
            "error": None,
            "prior_summary": None,
        }
        parsed_row = {
            "case_id": case.case_id,
            "parse_status": "error",
            "parser_notes": [
                f"skipped: materialization_status={materialization_status}"
            ],
            "predicted_intent": "",
            "predicted_answerability": "",
            "predicted_evidence_paths": [],
            "predicted_missing_fields": [],
            "predicted_warnings": [],
            "predicted_next_actions": [],
            "predicted_behavior_class": "",
            "answer_text": "",
            "prior_disagreement": False,
            "adapter_notes": "",
        }
        return raw_row, parsed_row

    messages, prior = _build_messages_for_system(system, case, payload)
    prompt_hash = _hash_prompt(messages)
    call = call_openai_contract_model(
        client,
        model=model,
        messages=messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_format_json_object=response_format_json,
        max_retries=max_retries,
    )
    # Compact snapshot of the prior we sent (System A only); useful for
    # downstream disagreement analysis without re-running the prior.
    prior_summary = None
    if prior is not None:
        prior_summary = {
            "intent_prior": prior.get("intent_prior"),
            "answerability_prior": prior.get("answerability_prior"),
            "behavior_class_prior": prior.get("behavior_class_prior"),
            "warnings_prior": prior.get("warnings_prior"),
            "missing_fields_prior": prior.get("missing_fields_prior"),
            "next_actions_prior": prior.get("next_actions_prior"),
        }

    raw_row = {
        "case_id": case.case_id,
        "provider": "openai",
        "system": system,
        "requested_model": call.requested_model,
        "response_model": call.response_model,
        "materialization_status": materialization_status,
        "materialization_warnings": materialization_warnings,
        "skipped": False,
        "skip_reason": "",
        "prompt_hash": prompt_hash,
        "raw_response_text": call.raw_response_text,
        "prompt_tokens": call.prompt_tokens,
        "completion_tokens": call.completion_tokens,
        "total_tokens": call.total_tokens,
        "latency_seconds": round(call.latency_seconds, 4),
        "retry_count": call.retry_count,
        "finish_reason": call.finish_reason,
        "error": call.error,
        "prior_summary": prior_summary,
    }

    if call.error or not call.raw_response_text:
        parsed_row = {
            "case_id": case.case_id,
            "parse_status": "error",
            "parser_notes": [call.error] if call.error else ["empty_response"],
            "predicted_intent": "",
            "predicted_answerability": "",
            "predicted_evidence_paths": [],
            "predicted_missing_fields": [],
            "predicted_warnings": [],
            "predicted_next_actions": [],
            "predicted_behavior_class": "",
            "answer_text": "",
            "prior_disagreement": False,
            "adapter_notes": "",
        }
        return raw_row, parsed_row

    parsed = parse_model_contract_json(call.raw_response_text, case_id=case.case_id)
    return raw_row, parsed_output_to_dict(parsed)


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------


def _write_run_log(
    *,
    paths: RunPaths,
    args: argparse.Namespace,
    case_count_attempted: int,
    case_count_materialized: int,
    parse_status_counts: dict[str, int],
    response_models: dict[str, int],
    error_count: int,
    total_latency_seconds: float,
    total_prompt_tokens: int,
    total_completion_tokens: int,
    started_iso: str,
    finished_iso: str,
) -> None:
    lines: list[str] = []
    lines.append("# Run 2 model baseline — run log")
    lines.append("")
    lines.append(f"- run_id: {args.run_id}")
    lines.append(f"- system: {args.system}")
    lines.append(f"- provider: {args.provider}")
    lines.append(f"- requested_model: {args.model}")
    lines.append(f"- temperature: {args.temperature}")
    lines.append(f"- max_output_tokens: {args.max_output_tokens}")
    lines.append(f"- response_format_json_object: {not args.no_response_format_json}")
    lines.append(f"- max_retries: {args.max_retries}")
    lines.append(f"- cases_csv: {args.cases}")
    if args.case_ids:
        lines.append(f"- case_ids: {args.case_ids}")
    if args.max_cases is not None:
        lines.append(f"- max_cases: {args.max_cases}")
    lines.append(f"- started_utc: {started_iso}")
    lines.append(f"- finished_utc: {finished_iso}")
    lines.append("")
    lines.append("## Counts")
    lines.append(f"- attempted: {case_count_attempted}")
    lines.append(f"- materialized (model called): {case_count_materialized}")
    lines.append(f"- errors (api/empty): {error_count}")
    lines.append("")
    lines.append("### parse_status")
    for k in sorted(parse_status_counts):
        lines.append(f"- {k}: {parse_status_counts[k]}")
    lines.append("")
    lines.append("### response_model strings observed")
    for k, v in sorted(response_models.items()):
        lines.append(f"- {k!r}: {v}")
    lines.append("")
    lines.append("## Aggregate latency / tokens")
    lines.append(f"- total_latency_seconds: {round(total_latency_seconds, 2)}")
    lines.append(f"- total_prompt_tokens: {total_prompt_tokens}")
    lines.append(f"- total_completion_tokens: {total_completion_tokens}")
    lines.append("")
    lines.append("## Output files")
    lines.append(f"- raw: `{paths.raw_jsonl}`")
    lines.append(f"- parsed: `{paths.parsed_jsonl}`")
    lines.append("")
    paths.run_log_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    # --- Load and validate cases (fail fast on a malformed CSV).
    cases = load_run2_cases(args.cases)
    report = validate_all_cases(cases)
    if report.n_errors:
        sys.stderr.write(
            f"cases CSV {args.cases} failed schema validation "
            f"({report.n_errors} error(s)); aborting before any API call.\n"
        )
        for cid, errs in sorted(report.errors_by_case.items()):
            for e in errs:
                sys.stderr.write(f"  {cid}: {e}\n")
        return 2

    # --- Select case subset.
    selected = _select_cases(
        cases, max_cases=args.max_cases, case_ids_csv=args.case_ids
    )
    if not selected:
        sys.stderr.write("no cases selected; nothing to do\n")
        return 2

    # --- Materialise payloads (deterministic; no model needed).
    selected_ids = {c.case_id for c in selected}
    mats_all, _ = materialize_all_cases(cases)
    mat_by_id = {m.case_id: m for m in mats_all if m.case_id in selected_ids}

    # --- Output directory setup + idempotency check.
    paths = _build_run_paths(args.outputs_dir, args.run_id)
    paths.root.mkdir(parents=True, exist_ok=True)
    err = _preflight(paths)
    if err:
        sys.stderr.write(f"preflight halt: {err}\n")
        return 3

    # --- Client construction (key required).
    try:
        client = load_openai_client(
            env_path=str(args.env_path) if args.env_path else None
        )
    except OpenAIKeyMissingError as exc:
        sys.stderr.write(f"{exc}\n")
        return 4

    started_iso = _utc_now_iso()

    raw_rows: list[dict] = []
    parsed_rows: list[dict] = []
    parse_status_counts: dict[str, int] = {}
    response_models: dict[str, int] = {}
    error_count = 0
    total_latency = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    materialised_count = 0

    for case in selected:
        mat = mat_by_id.get(case.case_id)
        if mat is None:
            mat_status = "skipped_no_seed"
            mat_warnings: list[str] = ["materializer returned no record"]
            payload = None
        else:
            mat_status = mat.materialization_status
            mat_warnings = list(mat.warnings)
            payload = mat.payload

        raw_row, parsed_row = _run_one_case(
            client=client,
            case=case,
            payload=payload,
            materialization_status=mat_status,
            materialization_warnings=mat_warnings,
            system=args.system,
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            response_format_json=not args.no_response_format_json,
            max_retries=args.max_retries,
        )
        raw_rows.append(raw_row)
        parsed_rows.append(parsed_row)

        status = parsed_row["parse_status"]
        parse_status_counts[status] = parse_status_counts.get(status, 0) + 1
        if not raw_row["skipped"]:
            materialised_count += 1
            if raw_row["response_model"]:
                response_models[raw_row["response_model"]] = (
                    response_models.get(raw_row["response_model"], 0) + 1
                )
            if raw_row["error"]:
                error_count += 1
            if raw_row["latency_seconds"]:
                total_latency += raw_row["latency_seconds"]
            if raw_row["prompt_tokens"]:
                total_prompt_tokens += raw_row["prompt_tokens"]
            if raw_row["completion_tokens"]:
                total_completion_tokens += raw_row["completion_tokens"]

        # Best-effort heartbeat so a long run shows progress.
        sys.stderr.write(
            f"[{case.case_id}] mat={mat_status} parse={status} "
            f"resp_model={raw_row.get('response_model', '')!r}\n"
        )

    _write_jsonl(paths.raw_jsonl, raw_rows)
    _write_jsonl(paths.parsed_jsonl, parsed_rows)

    finished_iso = _utc_now_iso()
    _write_run_log(
        paths=paths,
        args=args,
        case_count_attempted=len(selected),
        case_count_materialized=materialised_count,
        parse_status_counts=parse_status_counts,
        response_models=response_models,
        error_count=error_count,
        total_latency_seconds=total_latency,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        started_iso=started_iso,
        finished_iso=finished_iso,
    )

    sys.stderr.write(
        f"done: {len(selected)} attempted, {materialised_count} materialized, "
        f"{error_count} errors, parse_status={parse_status_counts}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Pass^k reliability runner for Run 2 model baselines.

Stage R2-5. Runs k independent OpenAI calls per case on a narrow
subset, records per-replicate raw and parsed outputs, scores each
replicate with the existing `run2_scoring.score_case`, and emits a
per-case + aggregate reliability report.

CLI:

    python -m product.evaluation.run2_passk_runner \\
      --cases product/evaluation/run2_benchmark_cases.csv \\
      --case-ids R2-008,R2-012,R2-015,R2-048,R2-058,R2-040,R2-051,R2-055,R2-060,R2-027 \\
      --provider openai \\
      --model gpt-5.4-mini \\
      --system B \\
      --k 5 \\
      --run-id run2-b-openai-gpt54mini-passk-v1

Outputs (under `product/evaluation/model_outputs/<run-id>/`):

    raw.jsonl     — one row per (case_id, replicate_id) call
    parsed.jsonl  — one row per (case_id, replicate_id) parsed contract
    scored.jsonl  — one row per (case_id, replicate_id) with the
                    component scores from `run2_scoring.score_case`
    run_log.md    — counts, model strings, latency, tokens

Idempotency: halts at preflight if any of the output files already
exists. The pass^k report is written by `run2_passk_report.py`.

No locked files read or modified. No gold labels sent to the model.
The OPENAI_API_KEY is loaded from .env via the existing client
wrapper and is never echoed.
"""
from __future__ import annotations

import argparse
import dataclasses
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
from product.evaluation.run2_scoring import score_case
from product.evaluation.run2_system_a_prior import build_system_a_prior


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run2_passk_runner",
        description=(
            "Pass^k reliability runner for Run 2 System B baselines. "
            "Runs k independent calls per case on a narrow subset."
        ),
    )
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--case-ids", required=True, type=str,
                   help="Comma-separated case IDs (R2-NNN,…).")
    p.add_argument("--provider", required=True, choices=["openai"])
    p.add_argument("--model", required=True, type=str)
    p.add_argument("--system", required=True, choices=["A", "B"])
    p.add_argument("--k", required=True, type=int)
    p.add_argument("--run-id", required=True, type=str)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-output-tokens", type=int, default=2048)
    p.add_argument(
        "--outputs-dir",
        type=Path,
        default=Path("product/evaluation/model_outputs"),
    )
    p.add_argument(
        "--env-path",
        type=Path,
        default=None,
        help="Optional explicit .env path; defaults to dotenv search.",
    )
    p.add_argument(
        "--no-response-format-json",
        action="store_true",
        help="Disable response_format=json_object (use only if model rejects).",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Per-call transient-error retry budget.",
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
    scored_jsonl: Path
    run_log_md: Path


def _build_run_paths(outputs_dir: Path, run_id: str) -> RunPaths:
    root = outputs_dir / run_id
    return RunPaths(
        root=root,
        raw_jsonl=root / "raw.jsonl",
        parsed_jsonl=root / "parsed.jsonl",
        scored_jsonl=root / "scored.jsonl",
        run_log_md=root / "run_log.md",
    )


def _hash_prompt(messages: list[dict]) -> str:
    encoded = json.dumps(messages, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _preflight(paths: RunPaths) -> Optional[str]:
    for p in (paths.raw_jsonl, paths.parsed_jsonl, paths.scored_jsonl, paths.run_log_md):
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


def _resolve_cases(
    all_cases: list[Run2Case], case_ids_csv: str
) -> list[Run2Case]:
    wanted = [cid.strip() for cid in case_ids_csv.split(",") if cid.strip()]
    by_id = {c.case_id: c for c in all_cases}
    missing = [cid for cid in wanted if cid not in by_id]
    if missing:
        raise ValueError(f"unknown case_ids in --case-ids: {missing}")
    return [by_id[cid] for cid in wanted]


# ---------------------------------------------------------------------------
# Per-replicate driver
# ---------------------------------------------------------------------------


def _run_one_replicate(
    *,
    client,
    case: Run2Case,
    payload: Optional[dict],
    materialization_status: str,
    materialization_warnings: list[str],
    replicate_id: int,
    prompt_hash: str,
    messages: list[dict],
    system: str,
    prior: Optional[dict],
    model: str,
    temperature: float,
    max_output_tokens: int,
    response_format_json: bool,
    max_retries: int,
) -> tuple[dict, dict]:
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

    if materialization_status != "materialized" or payload is None:
        raw_row = {
            "case_id": case.case_id,
            "replicate_id": replicate_id,
            "provider": "openai",
            "system": system,
            "requested_model": model,
            "response_model": "",
            "materialization_status": materialization_status,
            "materialization_warnings": materialization_warnings,
            "skipped": True,
            "skip_reason": f"materialization_status={materialization_status}",
            "prompt_hash": prompt_hash,
            "raw_response_text": "",
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "latency_seconds": None,
            "retry_count": 0,
            "finish_reason": None,
            "error": None,
            "prior_summary": prior_summary,
        }
        parsed_row = {
            "case_id": case.case_id,
            "replicate_id": replicate_id,
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

    call = call_openai_contract_model(
        client,
        model=model,
        messages=messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_format_json_object=response_format_json,
        max_retries=max_retries,
    )
    raw_row = {
        "case_id": case.case_id,
        "replicate_id": replicate_id,
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
        "latency_seconds": None if call.latency_seconds is None else round(call.latency_seconds, 4),
        "retry_count": call.retry_count,
        "finish_reason": call.finish_reason,
        "error": call.error,
        "prior_summary": prior_summary,
    }
    if call.error or not call.raw_response_text:
        parsed_row = {
            "case_id": case.case_id,
            "replicate_id": replicate_id,
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
    parsed_row = parsed_output_to_dict(parsed)
    parsed_row["replicate_id"] = replicate_id
    return raw_row, parsed_row


# ---------------------------------------------------------------------------
# Per-replicate scoring
# ---------------------------------------------------------------------------


def _score_replicate(case: Run2Case, parsed_row: dict) -> dict:
    """Run the existing scorer on a parsed.jsonl row.

    Returns a JSON-serialisable row including the boolean
    `all_components_pass` (strict: every applicable component check
    at 1.0 / True).
    """
    from product.evaluation.run2_model_output_adapter import parsed_output_from_dict

    parsed = parsed_output_from_dict(parsed_row)
    base = {
        "case_id": case.case_id,
        "replicate_id": parsed_row.get("replicate_id"),
        "parse_status": parsed_row.get("parse_status", ""),
    }
    if parsed.predicted is None:
        base.update(
            {
                "intent_correct": False,
                "answerability_correct": False,
                "behavior_class_correct": False,
                "evidence_precision": 0.0,
                "evidence_recall": 0.0,
                "warning_precision": 0.0,
                "warning_recall": 0.0,
                "missing_field_recall": 0.0,
                "useful_refusal_correct": (
                    False if case.expected_behavior_class == "useful_refusal" else None
                ),
                "partial_answer_correct": (
                    False
                    if case.expected_behavior_class == "partial_answer_with_warning"
                    else None
                ),
                "all_components_pass": False,
            }
        )
        return base

    s = score_case(case, parsed.predicted)
    all_pass = (
        s.intent_correct
        and s.answerability_correct
        and s.behavior_class_correct
        and s.evidence_precision >= 0.9999
        and s.evidence_recall >= 0.9999
        and s.warning_precision >= 0.9999
        and s.warning_recall >= 0.9999
        and s.missing_field_recall >= 0.9999
    )
    if case.expected_behavior_class == "useful_refusal":
        all_pass = all_pass and (s.useful_refusal_correct is True)
    if case.expected_behavior_class == "partial_answer_with_warning":
        all_pass = all_pass and (s.partial_answer_correct is True)

    base.update(
        {
            "intent_correct": bool(s.intent_correct),
            "answerability_correct": bool(s.answerability_correct),
            "behavior_class_correct": bool(s.behavior_class_correct),
            "evidence_precision": round(s.evidence_precision, 4),
            "evidence_recall": round(s.evidence_recall, 4),
            "warning_precision": round(s.warning_precision, 4),
            "warning_recall": round(s.warning_recall, 4),
            "missing_field_recall": round(s.missing_field_recall, 4),
            "useful_refusal_correct": (
                None if s.useful_refusal_correct is None else bool(s.useful_refusal_correct)
            ),
            "partial_answer_correct": (
                None if s.partial_answer_correct is None else bool(s.partial_answer_correct)
            ),
            "all_components_pass": bool(all_pass),
        }
    )
    return base


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------


def _write_run_log(
    *,
    paths: RunPaths,
    args: argparse.Namespace,
    n_cases: int,
    n_replicates_per_case: int,
    total_calls_attempted: int,
    total_calls_completed: int,
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
    lines.append("# Run 2 pass^k baseline — run log")
    lines.append("")
    lines.append(f"- run_id: {args.run_id}")
    lines.append(f"- system: {args.system}")
    lines.append(f"- provider: {args.provider}")
    lines.append(f"- requested_model: {args.model}")
    lines.append(f"- k: {args.k}")
    lines.append(f"- temperature: {args.temperature}")
    lines.append(f"- max_output_tokens: {args.max_output_tokens}")
    lines.append(f"- response_format_json_object: {not args.no_response_format_json}")
    lines.append(f"- max_retries: {args.max_retries}")
    lines.append(f"- cases_csv: {args.cases}")
    lines.append(f"- case_ids: {args.case_ids}")
    lines.append(f"- started_utc: {started_iso}")
    lines.append(f"- finished_utc: {finished_iso}")
    lines.append("")
    lines.append("## Counts")
    lines.append(f"- cases: {n_cases}")
    lines.append(f"- replicates_per_case: {n_replicates_per_case}")
    lines.append(f"- calls_attempted: {total_calls_attempted}")
    lines.append(f"- calls_completed (response received): {total_calls_completed}")
    lines.append(f"- errors (api/empty): {error_count}")
    lines.append("")
    lines.append("### parse_status (across all replicate rows)")
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
    lines.append(f"- scored: `{paths.scored_jsonl}`")
    lines.append("")
    paths.run_log_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.k < 1:
        sys.stderr.write("--k must be >= 1\n")
        return 2

    all_cases = load_run2_cases(args.cases)
    validation = validate_all_cases(all_cases)
    if validation.n_errors:
        sys.stderr.write(
            f"cases CSV {args.cases} failed schema validation "
            f"({validation.n_errors} error(s)); aborting before any API call.\n"
        )
        return 2

    try:
        selected = _resolve_cases(all_cases, args.case_ids)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    mats_all, _ = materialize_all_cases(all_cases)
    mat_by_id = {m.case_id: m for m in mats_all}

    paths = _build_run_paths(args.outputs_dir, args.run_id)
    paths.root.mkdir(parents=True, exist_ok=True)
    err = _preflight(paths)
    if err:
        sys.stderr.write(f"preflight halt: {err}\n")
        return 3

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
    scored_rows: list[dict] = []
    parse_status_counts: dict[str, int] = {}
    response_models: dict[str, int] = {}
    error_count = 0
    total_latency = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_calls_completed = 0

    total_calls_attempted = len(selected) * args.k

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

        # Build the prompt once per case (identical across replicates).
        # System A also builds the deterministic prior once per case.
        prior: Optional[dict] = None
        if payload is not None:
            if args.system == "A":
                prior = build_system_a_prior(case, payload)
                messages = build_system_a_prior_prompt(case, payload, prior)
            else:
                messages = build_prompt_only_json_prompt(case, payload)
            prompt_hash = _hash_prompt(messages)
        else:
            messages = []
            prompt_hash = ""

        for rep in range(args.k):
            raw_row, parsed_row = _run_one_replicate(
                client=client,
                case=case,
                payload=payload,
                materialization_status=mat_status,
                materialization_warnings=mat_warnings,
                replicate_id=rep,
                prompt_hash=prompt_hash,
                messages=messages,
                system=args.system,
                prior=prior,
                model=args.model,
                temperature=args.temperature,
                max_output_tokens=args.max_output_tokens,
                response_format_json=not args.no_response_format_json,
                max_retries=args.max_retries,
            )
            raw_rows.append(raw_row)
            parsed_rows.append(parsed_row)

            scored_row = _score_replicate(case, parsed_row)
            scored_rows.append(scored_row)

            ps = parsed_row.get("parse_status", "error")
            parse_status_counts[ps] = parse_status_counts.get(ps, 0) + 1
            if not raw_row["skipped"]:
                total_calls_completed += 1
                if raw_row.get("response_model"):
                    rm = raw_row["response_model"]
                    response_models[rm] = response_models.get(rm, 0) + 1
                if raw_row.get("error"):
                    error_count += 1
                if raw_row.get("latency_seconds"):
                    total_latency += raw_row["latency_seconds"]
                if raw_row.get("prompt_tokens"):
                    total_prompt_tokens += raw_row["prompt_tokens"]
                if raw_row.get("completion_tokens"):
                    total_completion_tokens += raw_row["completion_tokens"]
            sys.stderr.write(
                f"[{case.case_id}#{rep}] mat={mat_status} parse={ps} "
                f"all_pass={scored_row.get('all_components_pass')}\n"
            )

    _write_jsonl(paths.raw_jsonl, raw_rows)
    _write_jsonl(paths.parsed_jsonl, parsed_rows)
    _write_jsonl(paths.scored_jsonl, scored_rows)

    finished_iso = _utc_now_iso()
    _write_run_log(
        paths=paths,
        args=args,
        n_cases=len(selected),
        n_replicates_per_case=args.k,
        total_calls_attempted=total_calls_attempted,
        total_calls_completed=total_calls_completed,
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
        f"done: cases={len(selected)} k={args.k} attempted={total_calls_attempted} "
        f"completed={total_calls_completed} errors={error_count}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

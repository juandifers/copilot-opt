"""R2-S1 semantic-intent stress runner — System C0 baseline.

Orchestrates: load stress CSV → materialize payload (locked Run 1
seeds) → run System C0 → score against the stress gold (inherited
from the locked Run 2 benchmark) → emit per-case CSV + Markdown.

Usage:

    python -m product.evaluation.run2_stress.axis3_semantic.runner
        [--cases <path>] [--run-id <run-id>] [--require-head <sha>]

Defaults:
- `--cases`: `cases.csv` next to this module.
- `--run-id`: `full-run-v1` (the canonical Run 1 generator run used
  throughout R2-0).
- `--require-head`: the frozen-baseline commit `18b4811`. The runner
  warns (does not fail) if HEAD differs; warnings appear in the run
  log and the report's caveats section.

No solver calls. No model calls. No locked Run 2 file is modified.
Systems B / A are deliberately not invoked here — see
`run_system_b_stub` / `run_system_a_stub` below.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from product.evaluation.run2_payloads import (
    MaterializedPayload,
    materialize_case_payload,
)
from product.evaluation.run2_scoring import CaseScore, score_case
from product.evaluation.run2_system_c import (
    PredictedContract,
    run_system_c_on_materialized,
)
from product.evaluation.run2_stress.axis3_semantic.loader import (
    Run2StressCase,
    default_cases_path,
    load_stress_cases,
    validate_all_stress_cases,
)
from product.evaluation.run2_stress.shared.scatter import (
    ScatterContext,
    to_scatter_rows,
    write_scatter_csv,
)


FROZEN_BASELINE = "18b4811"
DEFAULT_RUN_ID = "full-run-v1"


# ---------------------------------------------------------------------------
# Result aggregation type
# ---------------------------------------------------------------------------


@dataclass
class StressCaseResult:
    """One row of the per-case results CSV."""

    case_id: str
    split: str
    stress_subtype: str
    base_case_id: str
    family: str
    expected_intent: str
    predicted_intent: str
    expected_answerability: str
    predicted_answerability: str
    expected_behavior_class: str
    predicted_behavior_class: str
    intent_correct: bool
    answerability_correct: bool
    behavior_class_correct: bool
    evidence_precision: float
    evidence_recall: float
    warning_precision: float
    warning_recall: float
    missing_field_recall: float
    materialization_status: str
    score_present: bool
    notes: str = ""


@dataclass
class RunArtifacts:
    """All artefacts the runner produces for one system."""

    cases: list[Run2StressCase]
    materializations: list[MaterializedPayload]
    predictions: list[Optional[PredictedContract]]
    scores: list[Optional[CaseScore]]
    results: list[StressCaseResult]
    head_sha: str
    run_id: str
    system_label: str
    started_at: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_head_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        return out
    except Exception as exc:  # noqa: BLE001 — diagnostic surface
        return f"unknown:{exc!r}"


def _check_head(required: str) -> Optional[str]:
    head = _git_head_sha()
    if head.startswith(required) or required in head:
        return None
    return (
        f"HEAD={head!r} does not match frozen baseline {required!r}. "
        f"R2-S1 C0 metrics are only comparable at the frozen baseline."
    )


def _build_result(
    case: Run2StressCase,
    mat: MaterializedPayload,
    pred: Optional[PredictedContract],
    score: Optional[CaseScore],
) -> StressCaseResult:
    notes_parts: list[str] = []
    if mat.warnings:
        notes_parts.append("mat_warnings=" + " | ".join(mat.warnings))
    if pred is not None and pred.notes:
        notes_parts.append("pred_notes=" + " | ".join(pred.notes))
    return StressCaseResult(
        case_id=case.case_id,
        split=case.split,
        stress_subtype=case.stress_subtype,
        base_case_id=case.base_case_id,
        family=case.family,
        expected_intent=case.expected_intent,
        predicted_intent=pred.predicted_intent if pred else "",
        expected_answerability=case.expected_answerability,
        predicted_answerability=pred.predicted_answerability if pred else "",
        expected_behavior_class=case.expected_behavior_class,
        predicted_behavior_class=pred.predicted_behavior_class if pred else "",
        intent_correct=score.intent_correct if score else False,
        answerability_correct=score.answerability_correct if score else False,
        behavior_class_correct=score.behavior_class_correct if score else False,
        evidence_precision=score.evidence_precision if score else 0.0,
        evidence_recall=score.evidence_recall if score else 0.0,
        warning_precision=score.warning_precision if score else 0.0,
        warning_recall=score.warning_recall if score else 0.0,
        missing_field_recall=score.missing_field_recall if score else 0.0,
        materialization_status=mat.materialization_status,
        score_present=score is not None,
        notes=" ; ".join(notes_parts),
    )


# ---------------------------------------------------------------------------
# Per-system entry points
# ---------------------------------------------------------------------------


def run_system_c0(
    cases_path: str | Path | None = None,
    run_id: str = DEFAULT_RUN_ID,
    required_head: str = FROZEN_BASELINE,
) -> RunArtifacts:
    """Run System C0 across the full 24-case stress split.

    Returns a `RunArtifacts` bundle; the caller (CLI or report module)
    is responsible for serialising to disk."""
    cases = load_stress_cases(cases_path)
    val = validate_all_stress_cases(cases)
    if val.n_errors:
        raise ValueError(
            f"stress CSV validation failed with {val.n_errors} error(s): "
            f"{val.errors_by_case!r}"
        )

    warnings: list[str] = []
    head_warning = _check_head(required_head)
    head_sha = _git_head_sha()
    if head_warning:
        warnings.append(head_warning)

    materializations: list[MaterializedPayload] = []
    predictions: list[Optional[PredictedContract]] = []
    scores: list[Optional[CaseScore]] = []
    results: list[StressCaseResult] = []

    for case in cases:
        run2_case = case.as_run2_case()
        mat = materialize_case_payload(run2_case, run_id=run_id)
        materializations.append(mat)

        pred: Optional[PredictedContract] = None
        score: Optional[CaseScore] = None
        if mat.materialization_status == "materialized":
            pred = run_system_c_on_materialized(run2_case, mat)
            if pred is not None:
                score = score_case(run2_case, pred)

        predictions.append(pred)
        scores.append(score)
        results.append(_build_result(case, mat, pred, score))

    return RunArtifacts(
        cases=cases,
        materializations=materializations,
        predictions=predictions,
        scores=scores,
        results=results,
        head_sha=head_sha,
        run_id=run_id,
        system_label="C0",
        started_at=dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        warnings=warnings,
    )


def run_system_b_stub(*_args, **_kwargs) -> None:
    """System B (prompt-only model) stress run.

    Not implemented at R2-S1 baseline. The existing
    `run2_model_baseline_runner.py` already knows how to drive Run 2
    cases through OpenAI; the wiring required here is:
      1. Materialize stress payloads via this module's helpers.
      2. Call `build_prompt_only_json_prompt` from
         `run2_model_prompts.py` per stress case.
      3. Parse the raw response with `run2_model_output_adapter.parse_model_contract_json`.
      4. Map to `PredictedContract`-shape and score with
         `run2_scoring.score_case`.

    Wiring is deferred because it requires an OPENAI_API_KEY in the
    environment and network access; both are out of scope for this
    baseline."""
    raise NotImplementedError(
        "R2-S1 System B runner is deferred. See run2_model_baseline_runner."
    )


def run_system_a_stub(*_args, **_kwargs) -> None:
    """System A (deterministic-prior + model fallback) stress run.

    Not implemented at R2-S1 baseline. Same hook shape as
    `run_system_b_stub`; the prior is built via
    `run2_system_a_prior.build_system_a_prior` and the model call uses
    `run2_model_prompts.build_system_a_prior_prompt`."""
    raise NotImplementedError(
        "R2-S1 System A runner is deferred. See run2_model_baseline_runner."
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


_RESULTS_CSV_FIELDS = [
    "case_id",
    "split",
    "stress_subtype",
    "base_case_id",
    "family",
    "expected_intent",
    "predicted_intent",
    "expected_answerability",
    "predicted_answerability",
    "expected_behavior_class",
    "predicted_behavior_class",
    "intent_correct",
    "answerability_correct",
    "behavior_class_correct",
    "evidence_precision",
    "evidence_recall",
    "warning_precision",
    "warning_recall",
    "missing_field_recall",
    "materialization_status",
    "score_present",
    "notes",
]


def _count_routes(payload: Optional[dict]) -> Optional[int]:
    """Return `len(payload.get('routes'))` when `routes` is a list, else None.

    The Run 1 payload schema (`run2_payloads.py`) uses `routes` as a
    list of route dicts. We treat any other shape as "n_routes is not
    meaningful for this case" and return `None`.
    """
    if not isinstance(payload, dict):
        return None
    routes = payload.get("routes")
    if isinstance(routes, list):
        return len(routes)
    return None


def _payload_chars(payload: Optional[dict]) -> Optional[int]:
    """Return the character length of `payload` serialized as JSON.

    Uses `sort_keys=True` and the default `json.dumps` separators so
    the count is deterministic and reproducible across runs."""
    if payload is None:
        return None
    import json as _json

    return len(_json.dumps(payload, sort_keys=True))


def build_scatter_rows(artifacts: RunArtifacts) -> list[dict]:
    """Convert a `RunArtifacts` bundle into shared-schema scatter rows.

    Per `shared/scatter_schema.md`:
      - axis = "axis3_semantic"
      - system = "c0"
      - band = the case's `stress_subtype`
      - intent = the case's `expected_intent` (gold)
      - n_routes / payload_chars come from the materialized payload
        when present, else null.

    Cases whose materialization failed (`materialization_status !=
    "materialized"`) are skipped — the shared scatter is for scored
    cases. The wider per-case CSV (`c0_baseline.csv`) records the
    skip.
    """
    scored_pairs: list[tuple[Run2StressCase, Any]] = []
    payload_ctx: dict[str, ScatterContext] = {}
    for case, mat, score in zip(
        artifacts.cases, artifacts.materializations, artifacts.scores
    ):
        if score is None:
            continue
        scored_pairs.append((case, score))
        payload_ctx[case.case_id] = ScatterContext(
            band=case.stress_subtype,
            n_routes=_count_routes(mat.payload),
            payload_chars=_payload_chars(mat.payload),
        )

    return to_scatter_rows(
        scored_pairs,
        axis="axis3_semantic",
        system="c0",
        payload_metadata_lookup=payload_ctx,
    )


def write_results_csv(artifacts: RunArtifacts, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RESULTS_CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in artifacts.results:
            row = asdict(r)
            row["intent_correct"] = "true" if row["intent_correct"] else "false"
            row["answerability_correct"] = (
                "true" if row["answerability_correct"] else "false"
            )
            row["behavior_class_correct"] = (
                "true" if row["behavior_class_correct"] else "false"
            )
            row["score_present"] = "true" if row["score_present"] else "false"
            for k in (
                "evidence_precision",
                "evidence_recall",
                "warning_precision",
                "warning_recall",
                "missing_field_recall",
            ):
                row[k] = f"{row[k]:.4f}"
            writer.writerow(row)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axis3_semantic.runner",
        description=(
            "Run R2-S1 semantic-intent stress on System C0 and emit "
            "reports/c0_baseline.{csv,md}."
        ),
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Path to cases.csv (defaults to the module-local file).",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=DEFAULT_RUN_ID,
        help="Run 1 generator run_id used to source seed payloads.",
    )
    parser.add_argument(
        "--require-head",
        type=str,
        default=FROZEN_BASELINE,
        help="Required HEAD SHA prefix (default: frozen-baseline commit).",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "reports",
        help="Where to write the c0_baseline.{csv,md} artefacts.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = run_system_c0(
        cases_path=args.cases,
        run_id=args.run_id,
        required_head=args.require_head,
    )
    # Import locally to avoid a circular dependency when report.py is
    # itself the entry point.
    from product.evaluation.run2_stress.axis3_semantic.report import (
        write_baseline_markdown,
    )

    csv_path = args.reports_dir / "c0_baseline.csv"
    md_path = args.reports_dir / "c0_baseline.md"
    scatter_path = args.reports_dir / "scatter.csv"
    write_results_csv(artifacts, csv_path)
    write_baseline_markdown(artifacts, md_path)
    write_scatter_csv(build_scatter_rows(artifacts), scatter_path)

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print(f"wrote {scatter_path}")
    if artifacts.warnings:
        for w in artifacts.warnings:
            print(f"WARN: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

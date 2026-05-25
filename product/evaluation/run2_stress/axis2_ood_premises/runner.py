"""R2-S Axis 2 OOD-false-premises stress runner — System C0 baseline.

Orchestrates: load stress CSV → materialize payload (locked Run 1
seeds) → run System C0 → score against the stress gold (authored per
case, not inherited) → emit per-case CSV + Markdown + shared scatter.

Usage:

    python -m product.evaluation.run2_stress.axis2_ood_premises.runner
        [--cases <path>] [--run-id <run-id>] [--require-head <sha>]

Defaults mirror Axis 1 / Axis 3:
- `--cases`: `cases.csv` next to this module.
- `--run-id`: `full-run-v1` (canonical Run 1 generator run).
- `--require-head`: the frozen-baseline commit `18b4811`.

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
from product.evaluation.run2_stress.axis2_ood_premises.loader import (
    Run2OodPremiseCase,
    default_cases_path,
    load_ood_cases,
    validate_all_ood_cases,
)
from product.evaluation.run2_stress.shared.scatter import (
    ScatterContext,
    to_scatter_rows,
    write_scatter_csv,
)


FROZEN_BASELINE = "18b4811"
DEFAULT_RUN_ID = "full-run-v1"


# ---------------------------------------------------------------------------
# Failure-taxonomy bucket assignment
# ---------------------------------------------------------------------------


REFUSAL_OR_PARTIAL_CLASSES: frozenset[str] = frozenset(
    {"useful_refusal", "partial_answer_with_warning"}
)
DIRECT_ANSWER_CLASSES: frozenset[str] = frozenset(
    {"direct_answer", "direct_answer_with_warning"}
)


def assign_failure_bucket(
    expected_intent: str,
    predicted_intent: str,
    expected_behavior_class: str,
    predicted_behavior_class: str,
    expected_warnings: set[str],
    predicted_warnings: set[str],
    intent_correct: bool,
    behavior_class_correct: bool,
    useful_refusal_correct: Optional[bool],
    partial_answer_correct: Optional[bool],
    evidence_precision: float,
    evidence_recall: float,
    warning_precision: float,
    warning_recall: float,
    missing_field_recall: float,
    schema_gap_flag: bool,
) -> str:
    """Map a scored Axis 2 case to one of the nine buckets.

    Mutually exclusive (first matching wins). Precedence per
    `design.md` §8:

      schema_gap_or_unrepresentable_gold
        → correct_refusal_or_partial
        → unknown_intent
        → wrong_intent
        → missed_false_premise
        → missed_missing_comparator
        → over_answered_unsupported_premise
        → downstream_evidence_mismatch
        → guard_protected
    """
    if schema_gap_flag:
        return "schema_gap_or_unrepresentable_gold"

    if expected_behavior_class in REFUSAL_OR_PARTIAL_CLASSES:
        if expected_behavior_class == "useful_refusal":
            if useful_refusal_correct:
                return "correct_refusal_or_partial"
        elif expected_behavior_class == "partial_answer_with_warning":
            if partial_answer_correct:
                return "correct_refusal_or_partial"

    if predicted_intent == "unknown" and not intent_correct:
        return "unknown_intent"

    if not intent_correct:
        return "wrong_intent"

    # intent_correct == True from here on
    gold_w = set(expected_warnings)
    pred_w = set(predicted_warnings)

    if "false_premise_detected" in gold_w and "false_premise_detected" not in pred_w:
        return "missed_false_premise"

    missing_comparator_warns = {
        "comparison_referent_ambiguity",
        "unsupported_comparison",
    }
    if (gold_w & missing_comparator_warns) and not (
        pred_w & missing_comparator_warns
    ):
        return "missed_missing_comparator"

    if (
        expected_behavior_class in REFUSAL_OR_PARTIAL_CLASSES
        and predicted_behavior_class in DIRECT_ANSWER_CLASSES
    ):
        return "over_answered_unsupported_premise"

    downstream_perfect = (
        behavior_class_correct
        and evidence_precision == 1.0
        and evidence_recall == 1.0
        and warning_precision == 1.0
        and warning_recall == 1.0
        and missing_field_recall == 1.0
    )
    if not downstream_perfect:
        return "downstream_evidence_mismatch"
    return "guard_protected"


# ---------------------------------------------------------------------------
# Result aggregation type
# ---------------------------------------------------------------------------


@dataclass
class StressCaseResult:
    """One row of the per-case results CSV."""

    case_id: str
    split: str
    band: str
    stress_subtype: str
    premise_type: str
    expected_failure_mode: str
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
    useful_refusal_correct: str  # "" | "true" | "false"
    partial_answer_correct: str  # "" | "true" | "false"
    materialization_status: str
    score_present: bool
    bucket: str
    notes: str = ""


@dataclass
class RunArtifacts:
    """All artefacts the runner produces for one system."""

    cases: list[Run2OodPremiseCase]
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
    except Exception as exc:  # noqa: BLE001
        return f"unknown:{exc!r}"


def _check_head(required: str) -> Optional[str]:
    head = _git_head_sha()
    if head.startswith(required) or required in head:
        return None
    return (
        f"HEAD={head!r} does not match frozen baseline {required!r}. "
        f"Axis 2 C0 metrics are only comparable at the frozen baseline."
    )


_SCHEMA_GAP_PHRASES: tuple[str, ...] = (
    "schema gap",
    "schema cannot express",
    "schema has no",
)


def _detect_schema_gap_flag(case: Run2OodPremiseCase) -> bool:
    """A case's ambiguity_notes may declare that the most faithful
    refusal is unrepresentable under the current schema and was
    downgraded to the closest supported behavior. The bucket
    `schema_gap_or_unrepresentable_gold` is reserved for those cases."""
    text = (case.ambiguity_notes or "").lower()
    return any(p in text for p in _SCHEMA_GAP_PHRASES)


def _build_result(
    case: Run2OodPremiseCase,
    mat: MaterializedPayload,
    pred: Optional[PredictedContract],
    score: Optional[CaseScore],
) -> StressCaseResult:
    notes_parts: list[str] = []
    if mat.warnings:
        notes_parts.append("mat_warnings=" + " | ".join(mat.warnings))
    if pred is not None and pred.notes:
        notes_parts.append("pred_notes=" + " | ".join(pred.notes))

    def _opt_bool(value: Optional[bool]) -> str:
        if value is None:
            return ""
        return "true" if value else "false"

    if score is None:
        bucket = "score_missing"
        useful_refusal_str = ""
        partial_answer_str = ""
    else:
        bucket = assign_failure_bucket(
            expected_intent=case.expected_intent,
            predicted_intent=pred.predicted_intent if pred else "unknown",
            expected_behavior_class=case.expected_behavior_class,
            predicted_behavior_class=(
                pred.predicted_behavior_class if pred else ""
            ),
            expected_warnings=set(case.expected_warnings),
            predicted_warnings=set(pred.predicted_warnings if pred else []),
            intent_correct=score.intent_correct,
            behavior_class_correct=score.behavior_class_correct,
            useful_refusal_correct=score.useful_refusal_correct,
            partial_answer_correct=score.partial_answer_correct,
            evidence_precision=score.evidence_precision,
            evidence_recall=score.evidence_recall,
            warning_precision=score.warning_precision,
            warning_recall=score.warning_recall,
            missing_field_recall=score.missing_field_recall,
            schema_gap_flag=_detect_schema_gap_flag(case),
        )
        useful_refusal_str = _opt_bool(score.useful_refusal_correct)
        partial_answer_str = _opt_bool(score.partial_answer_correct)

    return StressCaseResult(
        case_id=case.case_id,
        split=case.split,
        band=case.band,
        stress_subtype=case.stress_subtype,
        premise_type=case.premise_type,
        expected_failure_mode=case.expected_failure_mode,
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
        useful_refusal_correct=useful_refusal_str,
        partial_answer_correct=partial_answer_str,
        materialization_status=mat.materialization_status,
        score_present=score is not None,
        bucket=bucket,
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
    """Run System C0 across the full 24-case Axis 2 stress split."""
    cases = load_ood_cases(cases_path)
    val = validate_all_ood_cases(cases)
    if val.n_errors:
        raise ValueError(
            f"axis2 stress CSV validation failed with {val.n_errors} "
            f"error(s): {val.errors_by_case!r}"
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
    """System B (prompt-only model) — deferred at Axis 2 closeout."""
    raise NotImplementedError(
        "Axis 2 System B runner is deferred. See run2_model_baseline_runner."
    )


def run_system_a_stub(*_args, **_kwargs) -> None:
    """System A (prior + model fallback) — deferred at Axis 2 closeout."""
    raise NotImplementedError(
        "Axis 2 System A runner is deferred. See run2_model_baseline_runner."
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


_RESULTS_CSV_FIELDS = [
    "case_id",
    "split",
    "band",
    "stress_subtype",
    "premise_type",
    "expected_failure_mode",
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
    "useful_refusal_correct",
    "partial_answer_correct",
    "materialization_status",
    "score_present",
    "bucket",
    "notes",
]


def _count_routes(payload: Optional[dict]) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    routes = payload.get("routes")
    if isinstance(routes, list):
        return len(routes)
    return None


def _payload_chars(payload: Optional[dict]) -> Optional[int]:
    if payload is None:
        return None
    import json as _json

    return len(_json.dumps(payload, sort_keys=True))


def build_scatter_rows(artifacts: RunArtifacts) -> list[dict]:
    """Convert a `RunArtifacts` bundle into shared-schema scatter rows.

    Per `shared/scatter_schema.md`:
      - axis = "axis2_ood_premises"
      - system = "c0"
      - band = the case's `ood_premise_band` (== `band`)
      - intent = the case's `expected_intent` (gold)
      - n_routes / payload_chars come from the materialized payload
        when present, else null.
    """
    scored_pairs: list[tuple[Run2OodPremiseCase, Any]] = []
    payload_ctx: dict[str, ScatterContext] = {}
    for case, mat, score in zip(
        artifacts.cases, artifacts.materializations, artifacts.scores
    ):
        if score is None:
            continue
        scored_pairs.append((case, score))
        payload_ctx[case.case_id] = ScatterContext(
            band=case.ood_premise_band,
            n_routes=_count_routes(mat.payload),
            payload_chars=_payload_chars(mat.payload),
        )

    return to_scatter_rows(
        scored_pairs,
        axis="axis2_ood_premises",
        system="c0",
        payload_metadata_lookup=payload_ctx,
    )


def write_results_csv(artifacts: RunArtifacts, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=_RESULTS_CSV_FIELDS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        for r in artifacts.results:
            row = asdict(r)
            for bool_field in (
                "intent_correct",
                "answerability_correct",
                "behavior_class_correct",
                "score_present",
            ):
                row[bool_field] = "true" if row[bool_field] else "false"
            for float_field in (
                "evidence_precision",
                "evidence_recall",
                "warning_precision",
                "warning_recall",
                "missing_field_recall",
            ):
                row[float_field] = f"{row[float_field]:.4f}"
            writer.writerow(row)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axis2_ood_premises.runner",
        description=(
            "Run R2-S Axis 2 OOD-false-premises stress on System C0 and "
            "emit reports/c0_baseline.{csv,md} + reports/scatter.csv."
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
        help="Where to write c0_baseline.{csv,md} and scatter.csv.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = run_system_c0(
        cases_path=args.cases,
        run_id=args.run_id,
        required_head=args.require_head,
    )
    # Local import to avoid circular dependency.
    from product.evaluation.run2_stress.axis2_ood_premises.report import (
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

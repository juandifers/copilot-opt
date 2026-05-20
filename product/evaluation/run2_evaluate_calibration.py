"""CLI: end-to-end calibration evaluator for the Run 2 contract benchmark.

Usage:

    python -m product.evaluation.run2_evaluate_calibration \
        --cases product/evaluation/run2_calibration_cases.csv \
        --system C \
        --report-dir product/evaluation/reports

Wires together the four R2-1 modules:

    load_run2_cases (loader)            +  validate_all_cases (validator)
    materialize_all_cases (materializer)
    run_system_c_on_materialized (System C adapter)
    score_case + aggregate_scores (scoring)

Produces (and writes to disk):
    - schema validation summary
    - payload materialization summary
    - per-case predictions and scores
    - aggregate scores split by implementation_status / family /
      behavior_class / difficulty
    - lists of failing rows, separated current vs target_extension
    - markdown report at <report-dir>/run2_calibration_eval_system_<sys>.md
    - per-case CSV    at <report-dir>/run2_calibration_eval_system_<sys>.csv

No model calls. No solver calls. No composite metric.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import sys
from pathlib import Path
from typing import Iterable, Optional

from product.evaluation.run2_case_loader import (
    Run2Case,
    default_cases_path,
    load_run2_cases,
    validate_all_cases,
)
from product.evaluation.run2_payloads import (
    MaterializedPayload,
    MaterializationSummary,
    materialize_all_cases,
)
from product.evaluation.run2_scoring import CaseScore, aggregate_scores, score_case
from product.evaluation.run2_system_c import (
    PredictedContract,
    run_system_c_on_materialized,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the System C contract on the Run 2 calibration set "
            "and produce a markdown / CSV report. Reads-only; no model "
            "or solver calls."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=default_cases_path(),
        help="Path to run2_calibration_cases.csv.",
    )
    parser.add_argument(
        "--system",
        choices=("C",),
        default="C",
        help=(
            "Which system to evaluate. Only System C (the existing "
            "product contract layer) is supported in R2-1. Systems "
            "A and B are scheduled for R2-2."
        ),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "reports",
        help="Directory to write markdown + CSV reports into.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing report files; only print the summary.",
    )
    parser.add_argument(
        "--report-stem",
        type=str,
        default=None,
        help=(
            "Override the output filename stem. If omitted, the stem is "
            "derived from the input cases CSV basename: "
            "`run2_calibration_cases.csv` → "
            "`run2_calibration_eval_system_<sys>.{md,csv}`; "
            "`run2_benchmark_cases.csv` → "
            "`run2_benchmark_eval_system_<sys>.{md,csv}`."
        ),
    )
    return parser.parse_args(argv)


def _derive_report_stem(cases_path: Path, sys_label: str) -> str:
    """Derive `<stem>_eval_system_<sys>` from the cases file basename.

    Examples:
        run2_calibration_cases.csv → run2_calibration_eval_system_c
        run2_benchmark_cases.csv   → run2_benchmark_eval_system_c
        anything_else.csv          → anything_else_eval_system_c
    """
    base = cases_path.stem
    base = base.removesuffix("_cases")
    return f"{base}_eval_system_{sys_label.lower()}"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _score_all(
    cases: list[Run2Case],
    mats: list[MaterializedPayload],
) -> tuple[
    list[CaseScore],
    dict[str, Optional[PredictedContract]],
    list[str],
]:
    """Return (scores, predictions_by_case_id, skipped_case_ids).

    Skipped cases (no materialized payload) are excluded from scoring;
    their case_ids are returned separately so the report can mark them
    as un-scoreable rather than zero-scored.
    """
    by_id = {c.case_id: c for c in cases}
    mats_by_id = {m.case_id: m for m in mats}
    predictions: dict[str, Optional[PredictedContract]] = {}
    scores: list[CaseScore] = []
    skipped: list[str] = []

    for case in cases:
        mat = mats_by_id[case.case_id]
        pred = run_system_c_on_materialized(case, mat)
        predictions[case.case_id] = pred
        if pred is None:
            skipped.append(case.case_id)
            continue
        scores.append(score_case(case, pred))
    return scores, predictions, skipped


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _format_metric(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}"


def _format_group_row(name: str, group: dict[str, Optional[float]]) -> str:
    if not group:
        return f"| {name} | 0 | — | — | — | — | — | — | — |"
    return (
        f"| {name} | {group.get('n', 0)} "
        f"| {_format_metric(group.get('intent_accuracy'))} "
        f"| {_format_metric(group.get('answerability_accuracy'))} "
        f"| {_format_metric(group.get('behavior_class_accuracy'))} "
        f"| {_format_metric(group.get('evidence_precision'))}/"
        f"{_format_metric(group.get('evidence_recall'))} "
        f"| {_format_metric(group.get('warning_precision'))}/"
        f"{_format_metric(group.get('warning_recall'))} "
        f"| {_format_metric(group.get('missing_field_recall'))} "
        f"| {_format_metric(group.get('useful_refusal_correct_rate'))} "
        f"({group.get('useful_refusal_correct_n', 0)}) |"
    )


def _aggregate_table(title: str, groups: dict[str, dict]) -> list[str]:
    lines = [
        "",
        f"### {title}",
        "",
        "| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in sorted(groups.keys()):
        lines.append(_format_group_row(name, groups[name]))
    return lines


def _per_case_table(
    cases: list[Run2Case],
    predictions: dict[str, Optional[PredictedContract]],
    scores_by_id: dict[str, CaseScore],
) -> list[str]:
    lines = [
        "",
        "## Per-case predictions and scores",
        "",
        "| case | status | family | gold intent | pred intent | gold ans | pred ans | gold beh | pred beh | intent ✓ | ans ✓ | ev P/R | warn P/R | miss R |",
        "|---|---|---|---|---|---|---|---|---|:---:|:---:|---:|---:|---:|",
    ]
    for case in cases:
        pred = predictions.get(case.case_id)
        s = scores_by_id.get(case.case_id)
        if pred is None or s is None:
            lines.append(
                f"| {case.case_id} | {case.implementation_status} "
                f"| {case.family} | {case.expected_intent} | _skipped_ "
                f"| {case.expected_answerability} | — "
                f"| {case.expected_behavior_class} | — | — | — | — | — | — |"
            )
            continue
        lines.append(
            f"| {case.case_id} | {case.implementation_status} | {case.family} "
            f"| {case.expected_intent} | {pred.predicted_intent} "
            f"| {case.expected_answerability} | {pred.predicted_answerability} "
            f"| {case.expected_behavior_class} | {pred.predicted_behavior_class} "
            f"| {'✓' if s.intent_correct else '✗'} "
            f"| {'✓' if s.answerability_correct else '✗'} "
            f"| {_format_metric(s.evidence_precision)}/"
            f"{_format_metric(s.evidence_recall)} "
            f"| {_format_metric(s.warning_precision)}/"
            f"{_format_metric(s.warning_recall)} "
            f"| {_format_metric(s.missing_field_recall)} |"
        )
    return lines


def _failure_list(
    cases: list[Run2Case],
    scores_by_id: dict[str, CaseScore],
    status_filter: str,
) -> list[str]:
    """List case_ids whose contract metrics diverge from gold, filtered by
    implementation_status."""
    failing: list[str] = []
    for case in cases:
        if case.implementation_status != status_filter:
            continue
        s = scores_by_id.get(case.case_id)
        if s is None:
            continue
        reasons: list[str] = []
        if not s.intent_correct:
            reasons.append("intent")
        if not s.answerability_correct:
            reasons.append("answerability")
        if not s.behavior_class_correct:
            reasons.append("behavior_class")
        if (
            case.expected_behavior_class in {"direct_answer", "direct_answer_with_warning"}
            and s.warning_recall < 1.0
        ):
            reasons.append("warning_recall<1")
        if (
            case.expected_behavior_class in {"direct_answer", "direct_answer_with_warning"}
            and s.evidence_recall < 1.0
            and case.expected_evidence_paths
        ):
            reasons.append("evidence_recall<1")
        # For refusal- and partial-shaped golds, the per-shape
        # composite is the right failure signal.
        if (
            case.expected_behavior_class == "useful_refusal"
            and s.useful_refusal_correct is False
        ):
            reasons.append("useful_refusal_correct")
        if (
            case.expected_behavior_class == "partial_answer_with_warning"
            and s.partial_answer_correct is False
        ):
            reasons.append("partial_answer_correct")
        if reasons:
            failing.append(f"{case.case_id} ({', '.join(reasons)})")
    return failing


def build_markdown_report(
    cases: list[Run2Case],
    validation,
    mats: list[MaterializedPayload],
    mat_summary: MaterializationSummary,
    scores: list[CaseScore],
    predictions: dict[str, Optional[PredictedContract]],
    system_label: str,
) -> str:
    scores_by_id = {s.case_id: s for s in scores}
    agg = aggregate_scores(scores)

    lines: list[str] = []
    lines.append(f"# Run 2 calibration evaluation — System {system_label}")
    lines.append("")
    lines.append(
        "_Generated by `product.evaluation.run2_evaluate_calibration`. "
        "Contract-only mode; no generator answer_text. R2-1 stage._"
    )
    lines.append("")

    # 1. Schema validation
    lines.append("## 1. Schema validation")
    lines.append("")
    lines.append(f"- rows: {validation.n_cases}")
    lines.append(f"- errors: {validation.n_errors}")
    if validation.n_errors == 0:
        lines.append("- result: **pass**")
    else:
        lines.append("- result: **fail**")
        for cid, errs in sorted(validation.errors_by_case.items()):
            lines.append(f"  - `{cid}`:")
            for e in errs:
                lines.append(f"    - {e}")
    lines.append("")
    lines.append("### Distributions")
    for dist_name, dist in sorted(validation.distributions.items()):
        items = ", ".join(f"{k}={v}" for k, v in sorted(dist.items()))
        lines.append(f"- {dist_name}: {items}")
    lines.append("")

    # 2. Materialization summary
    lines.append("## 2. Payload materialization summary")
    lines.append("")
    for status, n in sorted(mat_summary.counts.items()):
        lines.append(f"- {status}: {n}")
    if mat_summary.skipped_no_seed_cases:
        lines.append(
            f"- skipped_no_seed cases: {mat_summary.skipped_no_seed_cases}"
        )
    if mat_summary.error_cases:
        lines.append(f"- error cases: {mat_summary.error_cases}")
    if mat_summary.recommendations:
        lines.append("")
        lines.append("### Materialization recommendations")
        for r in mat_summary.recommendations:
            lines.append(f"- {r}")
    # Per-case materialization warnings (e.g. inferred seed)
    mat_with_warnings = [m for m in mats if m.warnings]
    if mat_with_warnings:
        lines.append("")
        lines.append("### Per-case materialization warnings")
        for m in mat_with_warnings:
            lines.append(f"- `{m.case_id}` ({m.materialization_status}):")
            for w in m.warnings:
                lines.append(f"  - {w}")
    lines.append("")

    # 3. Per-case predictions
    lines.extend(_per_case_table(cases, predictions, scores_by_id))
    lines.append("")

    # 4. Aggregate scores
    lines.append("## 3. Aggregate scores (component metrics only — no composite)")
    lines.append("")
    lines.append("### Overall")
    lines.append("")
    if agg["overall"]:
        lines.append(
            "| n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |"
        )
        lines.append(
            "|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        overall = agg["overall"]
        lines.append(
            f"| {overall.get('n', 0)} "
            f"| {_format_metric(overall.get('intent_accuracy'))} "
            f"| {_format_metric(overall.get('answerability_accuracy'))} "
            f"| {_format_metric(overall.get('behavior_class_accuracy'))} "
            f"| {_format_metric(overall.get('evidence_precision'))}/"
            f"{_format_metric(overall.get('evidence_recall'))} "
            f"| {_format_metric(overall.get('warning_precision'))}/"
            f"{_format_metric(overall.get('warning_recall'))} "
            f"| {_format_metric(overall.get('missing_field_recall'))} "
            f"| {_format_metric(overall.get('useful_refusal_correct_rate'))} "
            f"({overall.get('useful_refusal_correct_n', 0)}) |"
        )

    lines.extend(_aggregate_table("By implementation_status", agg["by_implementation_status"]))
    lines.extend(_aggregate_table("By family", agg["by_family"]))
    lines.extend(_aggregate_table("By expected_behavior_class", agg["by_behavior_class"]))
    lines.extend(_aggregate_table("By difficulty", agg["by_difficulty"]))

    # 5. Failure lists, split by implementation_status
    lines.append("")
    lines.append("## 4. Failing cases")
    lines.append("")
    current_failures = _failure_list(cases, scores_by_id, "current")
    target_failures = _failure_list(cases, scores_by_id, "target_extension")
    lines.append(
        f"**current rows that fail (treat as regressions):** "
        f"{len(current_failures)}"
    )
    for f in current_failures:
        lines.append(f"- {f}")
    lines.append("")
    lines.append(
        f"**target_extension rows that fail (expected contract gaps; "
        f"not regressions):** {len(target_failures)}"
    )
    for f in target_failures:
        lines.append(f"- {f}")
    lines.append("")

    # 6. Recommendation
    lines.append("## 5. Recommendation")
    lines.append("")
    if mat_summary.skipped_no_seed_cases or current_failures:
        lines.append(
            "**Fix evaluator / payload materialization issues before "
            "proceeding to R2-2.**"
        )
        if mat_summary.skipped_no_seed_cases:
            lines.append(
                f"- {len(mat_summary.skipped_no_seed_cases)} case(s) "
                f"need explicit `source_prompt_id` values added to the CSV."
            )
        if current_failures:
            lines.append(
                f"- {len(current_failures)} `current` row(s) failed: "
                f"investigate before R2-2 expansion — these are regressions "
                f"against the existing contract, not policy gaps."
            )
    else:
        lines.append(
            "**Proceed to R2-2 expansion** — the calibration "
            "instrument is executable, current rows all pass, and "
            "target_extension failures are recorded as expected "
            "contract gaps."
        )

    return "\n".join(lines) + "\n"


def write_per_case_csv(
    path: Path,
    cases: list[Run2Case],
    predictions: dict[str, Optional[PredictedContract]],
    scores: list[CaseScore],
) -> None:
    scores_by_id = {s.case_id: s for s in scores}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "case_id",
                "implementation_status",
                "family",
                "difficulty",
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
            ]
        )
        for case in cases:
            pred = predictions.get(case.case_id)
            s = scores_by_id.get(case.case_id)
            if pred is None or s is None:
                writer.writerow(
                    [
                        case.case_id,
                        case.implementation_status,
                        case.family,
                        case.difficulty,
                        case.expected_intent,
                        "",
                        case.expected_answerability,
                        "",
                        case.expected_behavior_class,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                continue
            writer.writerow(
                [
                    case.case_id,
                    case.implementation_status,
                    case.family,
                    case.difficulty,
                    case.expected_intent,
                    pred.predicted_intent,
                    case.expected_answerability,
                    pred.predicted_answerability,
                    case.expected_behavior_class,
                    pred.predicted_behavior_class,
                    int(s.intent_correct),
                    int(s.answerability_correct),
                    int(s.behavior_class_correct),
                    f"{s.evidence_precision:.4f}",
                    f"{s.evidence_recall:.4f}",
                    f"{s.warning_precision:.4f}",
                    f"{s.warning_recall:.4f}",
                    f"{s.missing_field_recall:.4f}",
                    "" if s.useful_refusal_correct is None else int(s.useful_refusal_correct),
                    "" if s.partial_answer_correct is None else int(s.partial_answer_correct),
                ]
            )


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------


def _print_console_summary(
    validation,
    mat_summary: MaterializationSummary,
    scores: list[CaseScore],
    cases: list[Run2Case],
    predictions: dict[str, Optional[PredictedContract]],
    system_label: str,
) -> None:
    scores_by_id = {s.case_id: s for s in scores}
    agg = aggregate_scores(scores)
    print()
    print(f"=== Run 2 calibration eval (System {system_label}) ===")
    print(f"schema validation: rows={validation.n_cases} errors={validation.n_errors}")
    print(f"materialization counts: {mat_summary.counts}")
    if mat_summary.skipped_no_seed_cases:
        print(f"skipped_no_seed: {mat_summary.skipped_no_seed_cases}")
    print()
    print("Overall:", agg["overall"])
    for k, v in sorted(agg["by_implementation_status"].items()):
        print(f"  status={k}: {v}")
    print()

    current_failures = _failure_list(cases, scores_by_id, "current")
    target_failures = _failure_list(cases, scores_by_id, "target_extension")
    print(f"current rows failing (regressions): {len(current_failures)}")
    for f in current_failures:
        print(f"  - {f}")
    print(f"target_extension rows failing (expected gaps): {len(target_failures)}")
    for f in target_failures:
        print(f"  - {f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    cases = load_run2_cases(args.cases)
    validation = validate_all_cases(cases)

    mats, mat_summary = materialize_all_cases(cases)
    scores, predictions, _skipped = _score_all(cases, mats)

    _print_console_summary(
        validation, mat_summary, scores, cases, predictions, args.system
    )

    if not args.no_write:
        report_dir = args.report_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        stem = args.report_stem or _derive_report_stem(args.cases, args.system)
        md_path = report_dir / f"{stem}.md"
        csv_path = report_dir / f"{stem}.csv"
        markdown = build_markdown_report(
            cases=cases,
            validation=validation,
            mats=mats,
            mat_summary=mat_summary,
            scores=scores,
            predictions=predictions,
            system_label=args.system,
        )
        md_path.write_text(markdown, encoding="utf-8")
        write_per_case_csv(csv_path, cases, predictions, scores)
        print()
        print(f"wrote markdown report: {md_path}")
        print(f"wrote per-case CSV:    {csv_path}")

    # Exit code: 0 on clean schema validation; non-zero only when
    # something blocking happens (schema errors, materialization errors).
    # `current`-row scoring failures are reported but do not error the
    # CLI — R2-1 is a calibration shakedown, not a CI gate.
    if validation.n_errors > 0 or mat_summary.error_cases:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

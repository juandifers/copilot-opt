"""Score a model baseline's `parsed.jsonl` against the Run 2 gold.

CLI:

    python -m product.evaluation.run2_score_model_outputs \\
      --cases product/evaluation/run2_benchmark_cases.csv \\
      --parsed product/evaluation/model_outputs/<run-id>/parsed.jsonl \\
      --system B \\
      --provider openai \\
      --model gpt-5.4-mini \\
      --run-id <run-id>

Reuses `product.evaluation.run2_scoring.score_case` end-to-end — there
is no separate scoring definition for model outputs. Cases whose
`parse_status` is not `parsed` (or `invalid_enum`, which still
populates a `PredictedContract` for grading-what's-there) are recorded
as scoring skips and surfaced in the report.

Output report compares against a baseline run's per-case CSV if one is
provided via `--baseline-csv` (the per-case CSV emitted by
`run2_evaluate_calibration` for C-extended, by default). The comparison
table lists cases where the baseline passes and the model misses.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from product.evaluation.run2_case_loader import (
    Run2Case,
    load_run2_cases,
    validate_all_cases,
)
from product.evaluation.run2_model_output_adapter import (
    ParsedModelOutput,
    parsed_output_from_dict,
)
from product.evaluation.run2_scoring import (
    CaseScore,
    aggregate_scores,
    score_case,
)
from product.evaluation.run2_system_c import PredictedContract


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run2_score_model_outputs",
        description=(
            "Score a model baseline parsed.jsonl against the Run 2 gold using "
            "the existing run2_scoring.score_case."
        ),
    )
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--parsed", required=True, type=Path)
    p.add_argument("--system", required=True, choices=["A", "B"])
    p.add_argument("--provider", required=True, choices=["openai"])
    p.add_argument("--model", required=True, type=str)
    p.add_argument("--run-id", required=True, type=str)
    p.add_argument(
        "--report-dir",
        type=Path,
        default=Path("product/evaluation/reports"),
    )
    p.add_argument(
        "--baseline-csv",
        type=Path,
        default=Path(
            "product/evaluation/reports/run2_benchmark_eval_system_c_extended.csv"
        ),
        help=(
            "Per-case CSV of the deterministic reference baseline "
            "(default: C-extended). Used to compute B-vs-baseline deltas."
        ),
    )
    p.add_argument(
        "--baseline-label",
        type=str,
        default="C-extended",
    )
    p.add_argument(
        "--report-stem",
        type=str,
        default=None,
        help=(
            "Override output filename stem. Default: "
            "`run2_model_baseline_{system}_{provider}_{model_slug}_{run_id_tail}`."
        ),
    )
    return p


# ---------------------------------------------------------------------------
# parsed.jsonl loading
# ---------------------------------------------------------------------------


def _load_parsed_jsonl(path: Path) -> dict[str, ParsedModelOutput]:
    out: dict[str, ParsedModelOutput] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            parsed = parsed_output_from_dict(row)
            out[parsed.case_id] = parsed
    return out


# ---------------------------------------------------------------------------
# Baseline CSV loading
# ---------------------------------------------------------------------------


def _load_baseline_csv(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cid = row.get("case_id", "")
            if cid:
                out[cid] = row
    return out


# ---------------------------------------------------------------------------
# Scoring driver
# ---------------------------------------------------------------------------


def _score_all(
    cases: list[Run2Case], parsed_by_id: dict[str, ParsedModelOutput]
) -> tuple[
    list[CaseScore],
    dict[str, Optional[PredictedContract]],
    dict[str, ParsedModelOutput],
    list[str],
]:
    """Return (scores, predictions_by_case_id, parsed_by_id, unscored_ids)."""
    predictions: dict[str, Optional[PredictedContract]] = {}
    scores: list[CaseScore] = []
    unscored: list[str] = []
    for case in cases:
        parsed = parsed_by_id.get(case.case_id)
        if parsed is None or parsed.predicted is None:
            predictions[case.case_id] = None
            unscored.append(case.case_id)
            continue
        predictions[case.case_id] = parsed.predicted
        scores.append(score_case(case, parsed.predicted))
    return scores, predictions, parsed_by_id, unscored


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------


_TAXON_KEYS: tuple[str, ...] = (
    "intent_miss",
    "answerability_miss",
    "behavior_class_miss",
    "missing_field_miss",
    "evidence_precision_miss",
    "evidence_recall_miss",
    "warning_precision_miss",
    "warning_recall_miss",
    "useful_refusal_composite_miss",
    "partial_answer_composite_miss",
)


def _classify_failures(case: Run2Case, s: CaseScore) -> list[str]:
    out: list[str] = []
    if not s.intent_correct:
        out.append("intent_miss")
    if not s.answerability_correct:
        out.append("answerability_miss")
    if not s.behavior_class_correct:
        out.append("behavior_class_miss")
    if case.expected_missing_fields and s.missing_field_recall < 1.0:
        out.append("missing_field_miss")
    if case.expected_evidence_paths and s.evidence_recall < 1.0:
        out.append("evidence_recall_miss")
    if case.expected_evidence_paths and s.evidence_precision < 1.0:
        out.append("evidence_precision_miss")
    if case.expected_warnings and s.warning_recall < 1.0:
        out.append("warning_recall_miss")
    if case.expected_warnings and s.warning_precision < 1.0:
        out.append("warning_precision_miss")
    if s.useful_refusal_correct is False:
        out.append("useful_refusal_composite_miss")
    if s.partial_answer_correct is False:
        out.append("partial_answer_composite_miss")
    return out


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _fmt(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def _format_group_row(name: str, group: dict[str, Optional[float]]) -> str:
    if not group:
        return f"| {name} | 0 | — | — | — | — | — | — | — |"
    return (
        f"| {name} | {group.get('n', 0)} "
        f"| {_fmt(group.get('intent_accuracy'))} "
        f"| {_fmt(group.get('answerability_accuracy'))} "
        f"| {_fmt(group.get('behavior_class_accuracy'))} "
        f"| {_fmt(group.get('evidence_precision'))}/"
        f"{_fmt(group.get('evidence_recall'))} "
        f"| {_fmt(group.get('warning_precision'))}/"
        f"{_fmt(group.get('warning_recall'))} "
        f"| {_fmt(group.get('missing_field_recall'))} "
        f"| {_fmt(group.get('useful_refusal_correct_rate'))} "
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


def _baseline_compare_table(
    cases: list[Run2Case],
    scores: dict[str, CaseScore],
    baseline_rows: dict[str, dict[str, str]],
    baseline_label: str,
) -> list[str]:
    """List cases where the baseline scores 1.0 on a component but the model
    misses it. Limited to the top-N most distinctive."""
    lines = [
        "",
        f"## 5. Comparison vs {baseline_label}",
        "",
    ]
    if not baseline_rows:
        lines.append(
            f"_Baseline CSV not found; skipping per-case comparison._"
        )
        return lines

    misses: list[tuple[str, list[str]]] = []
    for case in cases:
        s = scores.get(case.case_id)
        if s is None:
            continue
        b = baseline_rows.get(case.case_id)
        if not b:
            continue
        case_misses: list[str] = []
        # Each axis: baseline passes (==1) and model misses.
        if b.get("intent_correct") == "1" and not s.intent_correct:
            case_misses.append("intent")
        if b.get("answerability_correct") == "1" and not s.answerability_correct:
            case_misses.append("answerability")
        if b.get("behavior_class_correct") == "1" and not s.behavior_class_correct:
            case_misses.append("behavior_class")
        try:
            if (
                float(b.get("evidence_recall", "0") or 0) >= 0.999
                and s.evidence_recall < 0.999
            ):
                case_misses.append("evidence_recall")
        except ValueError:
            pass
        try:
            if (
                float(b.get("warning_recall", "0") or 0) >= 0.999
                and s.warning_recall < 0.999
            ):
                case_misses.append("warning_recall")
        except ValueError:
            pass
        try:
            if (
                float(b.get("missing_field_recall", "0") or 0) >= 0.999
                and s.missing_field_recall < 0.999
            ):
                case_misses.append("missing_field_recall")
        except ValueError:
            pass
        # composite shape checks
        if (
            b.get("useful_refusal_correct") == "1"
            and s.useful_refusal_correct is False
        ):
            case_misses.append("useful_refusal_composite")
        if (
            b.get("partial_answer_correct") == "1"
            and s.partial_answer_correct is False
        ):
            case_misses.append("partial_answer_composite")
        if case_misses:
            misses.append((case.case_id, case_misses))

    lines.append(
        f"**Cases where {baseline_label} passes a component metric but the "
        f"model misses it:** {len(misses)}"
    )
    lines.append("")
    if misses:
        lines.append("| case | misses |")
        lines.append("|---|---|")
        for cid, ms in misses:
            lines.append(f"| {cid} | {', '.join(ms)} |")
    return lines


def _per_case_table(
    cases: list[Run2Case],
    predictions: dict[str, Optional[PredictedContract]],
    scores_by_id: dict[str, CaseScore],
    parsed_by_id: dict[str, ParsedModelOutput],
) -> list[str]:
    lines = [
        "",
        "## Per-case predictions and scores",
        "",
        "| case | status | family | gold intent | pred intent | gold ans | pred ans | gold beh | pred beh | parse | intent ✓ | ans ✓ | ev P/R | warn P/R | miss R |",
        "|---|---|---|---|---|---|---|---|---|---|:---:|:---:|---:|---:|---:|",
    ]
    for case in cases:
        pred = predictions.get(case.case_id)
        s = scores_by_id.get(case.case_id)
        parsed = parsed_by_id.get(case.case_id)
        parse_status = parsed.parse_status if parsed else "missing"
        if pred is None or s is None:
            lines.append(
                f"| {case.case_id} | {case.implementation_status} "
                f"| {case.family} | {case.expected_intent} | _unscored_ "
                f"| {case.expected_answerability} | — "
                f"| {case.expected_behavior_class} | — | {parse_status} "
                f"| — | — | — | — | — |"
            )
            continue
        lines.append(
            f"| {case.case_id} | {case.implementation_status} | {case.family} "
            f"| {case.expected_intent} | {pred.predicted_intent} "
            f"| {case.expected_answerability} | {pred.predicted_answerability} "
            f"| {case.expected_behavior_class} | {pred.predicted_behavior_class} "
            f"| {parse_status} "
            f"| {'✓' if s.intent_correct else '✗'} "
            f"| {'✓' if s.answerability_correct else '✗'} "
            f"| {_fmt(s.evidence_precision)}/{_fmt(s.evidence_recall)} "
            f"| {_fmt(s.warning_precision)}/{_fmt(s.warning_recall)} "
            f"| {_fmt(s.missing_field_recall)} |"
        )
    return lines


def _failure_examples(
    cases: list[Run2Case],
    scores_by_id: dict[str, CaseScore],
    predictions: dict[str, Optional[PredictedContract]],
    limit: int = 10,
) -> list[str]:
    examples: list[str] = []
    for case in cases:
        s = scores_by_id.get(case.case_id)
        if s is None:
            continue
        miss_kinds = _classify_failures(case, s)
        if not miss_kinds:
            continue
        pred = predictions.get(case.case_id)
        bits = [
            f"### {case.case_id} ({case.implementation_status}, {case.family}, {case.difficulty})",
            "",
            f"- prompt: {case.prompt_text}",
            f"- payload_condition: {case.payload_condition}",
            f"- miss_kinds: {', '.join(miss_kinds)}",
            f"- gold intent / ans / beh: {case.expected_intent} / {case.expected_answerability} / {case.expected_behavior_class}",
        ]
        if pred is not None:
            bits.append(
                f"- pred intent / ans / beh: {pred.predicted_intent} / "
                f"{pred.predicted_answerability} / {pred.predicted_behavior_class}"
            )
            bits.append(f"- gold evidence: {case.expected_evidence_paths}")
            bits.append(f"- pred evidence: {pred.predicted_evidence_paths}")
            if case.expected_missing_fields or pred.predicted_missing_fields:
                bits.append(
                    f"- gold missing / pred missing: "
                    f"{case.expected_missing_fields} / {pred.predicted_missing_fields}"
                )
            if case.expected_warnings or pred.predicted_warnings:
                bits.append(
                    f"- gold warnings / pred warnings: "
                    f"{case.expected_warnings} / {pred.predicted_warnings}"
                )
            if case.expected_next_actions or pred.predicted_next_actions:
                bits.append(
                    f"- gold actions / pred actions: "
                    f"{case.expected_next_actions} / {pred.predicted_next_actions}"
                )
        bits.append("")
        examples.append("\n".join(bits))
        if len(examples) >= limit:
            break
    return examples


# ---------------------------------------------------------------------------
# Markdown / CSV writers
# ---------------------------------------------------------------------------


def build_markdown_report(
    *,
    cases: list[Run2Case],
    validation,
    scores: list[CaseScore],
    predictions: dict[str, Optional[PredictedContract]],
    parsed_by_id: dict[str, ParsedModelOutput],
    unscored: list[str],
    system_label: str,
    provider: str,
    model: str,
    run_id: str,
    baseline_rows: dict[str, dict[str, str]],
    baseline_label: str,
) -> str:
    scores_by_id = {s.case_id: s for s in scores}
    agg = aggregate_scores(scores)

    parse_counts = Counter(p.parse_status for p in parsed_by_id.values())
    family_taxon: defaultdict[str, Counter] = defaultdict(Counter)
    overall_taxon: Counter = Counter()
    for case in cases:
        s = scores_by_id.get(case.case_id)
        if s is None:
            continue
        for kind in _classify_failures(case, s):
            overall_taxon[kind] += 1
            family_taxon[case.family][kind] += 1

    lines: list[str] = []
    lines.append(f"# Run 2 model baseline — System {system_label} ({provider} {model})")
    lines.append("")
    lines.append(f"- run_id: {run_id}")
    lines.append(f"- provider: {provider}")
    lines.append(f"- requested_model: {model}")
    lines.append(f"- cases: {len(cases)}")
    lines.append(f"- scored: {len(scores)}")
    lines.append(f"- unscored (parse/skip): {len(unscored)}")
    lines.append("")

    # 1. Parse success
    lines.append("## 1. Parse success")
    lines.append("")
    for k in sorted(parse_counts):
        lines.append(f"- {k}: {parse_counts[k]}")
    lines.append("")

    # 2. Schema validation
    lines.append("## 2. Cases schema validation")
    lines.append(f"- rows: {validation.n_cases}")
    lines.append(f"- errors: {validation.n_errors}")
    lines.append("")

    # 3. Aggregate scores
    lines.append("## 3. Aggregate scores (component metrics only — no composite)")
    lines.append("")
    if agg.get("overall"):
        lines.append("### Overall")
        lines.append("")
        lines.append(
            "| n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |"
        )
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
        overall = agg["overall"]
        lines.append(
            f"| {overall.get('n', 0)} "
            f"| {_fmt(overall.get('intent_accuracy'))} "
            f"| {_fmt(overall.get('answerability_accuracy'))} "
            f"| {_fmt(overall.get('behavior_class_accuracy'))} "
            f"| {_fmt(overall.get('evidence_precision'))}/"
            f"{_fmt(overall.get('evidence_recall'))} "
            f"| {_fmt(overall.get('warning_precision'))}/"
            f"{_fmt(overall.get('warning_recall'))} "
            f"| {_fmt(overall.get('missing_field_recall'))} "
            f"| {_fmt(overall.get('useful_refusal_correct_rate'))} "
            f"({overall.get('useful_refusal_correct_n', 0)}) |"
        )
    lines.extend(
        _aggregate_table("By implementation_status", agg.get("by_implementation_status", {}))
    )
    lines.extend(_aggregate_table("By family", agg.get("by_family", {})))
    lines.extend(
        _aggregate_table("By expected_behavior_class", agg.get("by_behavior_class", {}))
    )
    lines.extend(_aggregate_table("By difficulty", agg.get("by_difficulty", {})))

    # 4. Failure taxonomy
    lines.append("")
    lines.append("## 4. Failure taxonomy")
    lines.append("")
    lines.append("| kind | overall |")
    lines.append("|---|---:|")
    for k in _TAXON_KEYS:
        lines.append(f"| {k} | {overall_taxon.get(k, 0)} |")
    lines.append("")
    if family_taxon:
        fams = sorted(family_taxon.keys())
        header = "| kind | " + " | ".join(fams) + " |"
        sep = "|---|" + "|".join(["---:"] * len(fams)) + "|"
        lines.append("### Failure taxonomy by family")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        for k in _TAXON_KEYS:
            row = [f"| {k} "] + [f"| {family_taxon[f].get(k, 0)} " for f in fams]
            row.append("|")
            lines.append("".join(row))

    # 5. Baseline comparison
    lines.extend(
        _baseline_compare_table(
            cases, scores_by_id, baseline_rows, baseline_label
        )
    )

    # 6. Top illustrative failures
    lines.append("")
    lines.append("## 6. Top 10 illustrative failures")
    lines.append("")
    examples = _failure_examples(cases, scores_by_id, predictions, limit=10)
    if not examples:
        lines.append("_No scoring failures._")
    else:
        lines.extend(examples)

    # 7. Per-case table
    lines.extend(_per_case_table(cases, predictions, scores_by_id, parsed_by_id))
    lines.append("")

    if unscored:
        lines.append("## 7. Unscored cases")
        lines.append("")
        for cid in unscored:
            p = parsed_by_id.get(cid)
            ps = p.parse_status if p else "missing"
            notes = "; ".join(p.parser_notes) if p else "no parsed row"
            lines.append(f"- `{cid}` parse_status={ps} notes={notes}")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_per_case_csv(
    path: Path,
    cases: list[Run2Case],
    predictions: dict[str, Optional[PredictedContract]],
    scores: list[CaseScore],
    parsed_by_id: dict[str, ParsedModelOutput],
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
                "parse_status",
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
            parsed = parsed_by_id.get(case.case_id)
            parse_status = parsed.parse_status if parsed else "missing"
            if pred is None or s is None:
                writer.writerow(
                    [
                        case.case_id,
                        case.implementation_status,
                        case.family,
                        case.difficulty,
                        parse_status,
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
                    parse_status,
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
# Entry point
# ---------------------------------------------------------------------------


def _model_slug(model: str) -> str:
    return model.replace("-", "").replace(".", "").lower()


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    cases = load_run2_cases(args.cases)
    validation = validate_all_cases(cases)
    if validation.n_errors:
        sys.stderr.write(
            f"cases CSV {args.cases} failed schema validation ({validation.n_errors} error(s))\n"
        )
        return 2

    parsed_by_id = _load_parsed_jsonl(args.parsed)
    scores, predictions, parsed_by_id, unscored = _score_all(cases, parsed_by_id)
    baseline_rows = _load_baseline_csv(args.baseline_csv)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    if args.report_stem:
        stem = args.report_stem
    else:
        run_tail = args.run_id.replace("/", "_")
        stem = (
            f"run2_model_baseline_{args.system.lower()}_{args.provider}_"
            f"{_model_slug(args.model)}_{run_tail}"
        )

    md_path = args.report_dir / f"{stem}.md"
    csv_path = args.report_dir / f"{stem}.csv"

    markdown = build_markdown_report(
        cases=cases,
        validation=validation,
        scores=scores,
        predictions=predictions,
        parsed_by_id=parsed_by_id,
        unscored=unscored,
        system_label=args.system,
        provider=args.provider,
        model=args.model,
        run_id=args.run_id,
        baseline_rows=baseline_rows,
        baseline_label=args.baseline_label,
    )
    md_path.write_text(markdown, encoding="utf-8")
    write_per_case_csv(csv_path, cases, predictions, scores, parsed_by_id)
    print(f"wrote markdown report: {md_path}")
    print(f"wrote per-case CSV:    {csv_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

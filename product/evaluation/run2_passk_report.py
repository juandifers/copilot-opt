"""Compute pass^k reliability metrics from a passk runner output.

CLI:

    python -m product.evaluation.run2_passk_report \\
      --cases product/evaluation/run2_benchmark_cases.csv \\
      --scored product/evaluation/model_outputs/<run-id>/scored.jsonl \\
      --raw    product/evaluation/model_outputs/<run-id>/raw.jsonl \\
      --run-id <run-id> \\
      --model gpt-5.4-mini \\
      --provider openai \\
      --system B

Reads the `scored.jsonl` written by `run2_passk_runner.py` and emits:

    product/evaluation/reports/<stem>.md
    product/evaluation/reports/<stem>.csv

where `<stem>` defaults to `run2_passk_<model-slug>_<run_id_tail>`.

No locked files read or modified. No model calls. Pure aggregation.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from product.evaluation.run2_case_loader import (
    Run2Case,
    load_run2_cases,
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class CaseReliability:
    """Aggregate reliability stats for one case across its k replicates."""

    case_id: str
    family: str
    implementation_status: str
    payload_condition: str
    expected_intent: str
    expected_behavior_class: str
    expected_answerability: str

    n_replicates: int
    n_parsed: int

    intent_correct_rate: float
    answerability_correct_rate: float
    behavior_class_correct_rate: float

    evidence_precision_mean: float
    evidence_recall_mean: float
    warning_precision_mean: float
    warning_recall_mean: float
    missing_field_recall_mean: float

    useful_refusal_correct_rate: Optional[float]
    partial_answer_correct_rate: Optional[float]

    all_components_pass_rate: float
    pass_at_k_any: bool
    pass_to_the_k_all: bool


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run2_passk_report",
        description=(
            "Compute pass^k reliability metrics from a passk runner's "
            "scored.jsonl and emit a markdown + CSV report."
        ),
    )
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--scored", required=True, type=Path)
    p.add_argument("--raw", type=Path, default=None,
                   help="raw.jsonl path (used for cost/token rollup; optional).")
    p.add_argument("--run-id", required=True, type=str)
    p.add_argument("--model", required=True, type=str)
    p.add_argument("--provider", required=True, choices=["openai"])
    p.add_argument("--system", required=True, choices=["A", "B"])
    p.add_argument(
        "--report-dir",
        type=Path,
        default=Path("product/evaluation/reports"),
    )
    p.add_argument(
        "--report-stem",
        type=str,
        default=None,
    )
    p.add_argument(
        "--target-extension-ids",
        type=str,
        default="R2-008,R2-012,R2-015,R2-048,R2-058",
        help="Comma-separated case IDs that count toward the target-extension subset.",
    )
    p.add_argument(
        "--current-failure-ids",
        type=str,
        default="R2-040,R2-051,R2-055,R2-060,R2-027",
        help="Comma-separated case IDs that count toward the current-row failure subset.",
    )
    return p


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Per-case reliability
# ---------------------------------------------------------------------------


def _fraction_true(rows: list[dict], key: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get(key)) / len(rows)


def _mean(rows: list[dict], key: str) -> float:
    vals: list[float] = []
    for r in rows:
        v = r.get(key)
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return statistics.fmean(vals) if vals else 0.0


def _opt_fraction_true(rows: list[dict], key: str) -> Optional[float]:
    applicable = [r for r in rows if r.get(key) is not None]
    if not applicable:
        return None
    return sum(1 for r in applicable if r.get(key) is True) / len(applicable)


def compute_case_reliability(
    case: Run2Case, replicate_scores: list[dict]
) -> CaseReliability:
    """Aggregate one case's k replicate scores into a `CaseReliability`."""
    n = len(replicate_scores)
    n_parsed = sum(1 for r in replicate_scores if r.get("parse_status") == "parsed")
    n_pass = sum(1 for r in replicate_scores if r.get("all_components_pass") is True)

    return CaseReliability(
        case_id=case.case_id,
        family=case.family,
        implementation_status=case.implementation_status,
        payload_condition=case.payload_condition,
        expected_intent=case.expected_intent,
        expected_behavior_class=case.expected_behavior_class,
        expected_answerability=case.expected_answerability,
        n_replicates=n,
        n_parsed=n_parsed,
        intent_correct_rate=_fraction_true(replicate_scores, "intent_correct"),
        answerability_correct_rate=_fraction_true(
            replicate_scores, "answerability_correct"
        ),
        behavior_class_correct_rate=_fraction_true(
            replicate_scores, "behavior_class_correct"
        ),
        evidence_precision_mean=_mean(replicate_scores, "evidence_precision"),
        evidence_recall_mean=_mean(replicate_scores, "evidence_recall"),
        warning_precision_mean=_mean(replicate_scores, "warning_precision"),
        warning_recall_mean=_mean(replicate_scores, "warning_recall"),
        missing_field_recall_mean=_mean(replicate_scores, "missing_field_recall"),
        useful_refusal_correct_rate=_opt_fraction_true(
            replicate_scores, "useful_refusal_correct"
        ),
        partial_answer_correct_rate=_opt_fraction_true(
            replicate_scores, "partial_answer_correct"
        ),
        all_components_pass_rate=(n_pass / n) if n else 0.0,
        pass_at_k_any=(n_pass >= 1),
        pass_to_the_k_all=(n_pass == n and n > 0),
    )


# ---------------------------------------------------------------------------
# Stability classification (used for §8–10 of the report)
# ---------------------------------------------------------------------------


def classify_stability(c: CaseReliability) -> str:
    """One of stable_success / stable_failure / flaky."""
    if c.pass_to_the_k_all:
        return "stable_success"
    if c.all_components_pass_rate == 0.0:
        return "stable_failure"
    return "flaky"


# ---------------------------------------------------------------------------
# Cost / token rollup from raw.jsonl
# ---------------------------------------------------------------------------


@dataclass
class CostSummary:
    total_calls: int
    total_latency_seconds: float
    total_prompt_tokens: int
    total_completion_tokens: int


def _summarize_costs(raw_rows: list[dict]) -> CostSummary:
    calls = [r for r in raw_rows if not r.get("skipped")]
    return CostSummary(
        total_calls=len(calls),
        total_latency_seconds=sum(r.get("latency_seconds") or 0.0 for r in calls),
        total_prompt_tokens=sum(int(r.get("prompt_tokens") or 0) for r in calls),
        total_completion_tokens=sum(int(r.get("completion_tokens") or 0) for r in calls),
    )


# ---------------------------------------------------------------------------
# Markdown / CSV writers
# ---------------------------------------------------------------------------


def _fmt_rate(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x:.2f}"


def _fmt_mean(x: float) -> str:
    return f"{x:.3f}"


def _per_case_table(reliabilities: list[CaseReliability]) -> list[str]:
    lines = [
        "| case | status | family | intent rate | ans rate | beh rate | ev P (mean) | ev R (mean) | warn P (mean) | warn R (mean) | miss R (mean) | useful_refusal rate | partial rate | all-pass rate | pass@k_any | pass^k_all |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|",
    ]
    for c in reliabilities:
        lines.append(
            f"| {c.case_id} | {c.implementation_status} | {c.family} "
            f"| {_fmt_rate(c.intent_correct_rate)} "
            f"| {_fmt_rate(c.answerability_correct_rate)} "
            f"| {_fmt_rate(c.behavior_class_correct_rate)} "
            f"| {_fmt_mean(c.evidence_precision_mean)} "
            f"| {_fmt_mean(c.evidence_recall_mean)} "
            f"| {_fmt_mean(c.warning_precision_mean)} "
            f"| {_fmt_mean(c.warning_recall_mean)} "
            f"| {_fmt_mean(c.missing_field_recall_mean)} "
            f"| {_fmt_rate(c.useful_refusal_correct_rate)} "
            f"| {_fmt_rate(c.partial_answer_correct_rate)} "
            f"| {_fmt_rate(c.all_components_pass_rate)} "
            f"| {'✓' if c.pass_at_k_any else '✗'} "
            f"| {'✓' if c.pass_to_the_k_all else '✗'} |"
        )
    return lines


def _subset_aggregate(
    reliabilities: list[CaseReliability], subset_ids: set[str]
) -> dict:
    members = [c for c in reliabilities if c.case_id in subset_ids]
    if not members:
        return {
            "n_cases": 0,
            "stable_success": 0,
            "stable_failure": 0,
            "flaky": 0,
            "mean_all_components_pass_rate": 0.0,
            "fraction_pass_to_the_k_all": 0.0,
            "fraction_pass_at_k_any": 0.0,
        }
    succ = sum(1 for c in members if classify_stability(c) == "stable_success")
    fail = sum(1 for c in members if classify_stability(c) == "stable_failure")
    flaky = sum(1 for c in members if classify_stability(c) == "flaky")
    return {
        "n_cases": len(members),
        "stable_success": succ,
        "stable_failure": fail,
        "flaky": flaky,
        "mean_all_components_pass_rate": (
            sum(c.all_components_pass_rate for c in members) / len(members)
        ),
        "fraction_pass_to_the_k_all": (
            sum(1 for c in members if c.pass_to_the_k_all) / len(members)
        ),
        "fraction_pass_at_k_any": (
            sum(1 for c in members if c.pass_at_k_any) / len(members)
        ),
    }


def build_markdown_report(
    *,
    reliabilities: list[CaseReliability],
    raw_rows: list[dict],
    n_replicates_per_case: int,
    target_subset: set[str],
    current_subset: set[str],
    run_id: str,
    provider: str,
    model: str,
    system_label: str,
) -> str:
    overall = _subset_aggregate(reliabilities, {c.case_id for c in reliabilities})
    target_agg = _subset_aggregate(reliabilities, target_subset)
    current_agg = _subset_aggregate(reliabilities, current_subset)
    costs = _summarize_costs(raw_rows)

    stable_success = [c.case_id for c in reliabilities if classify_stability(c) == "stable_success"]
    stable_failure = [c.case_id for c in reliabilities if classify_stability(c) == "stable_failure"]
    flaky = [c.case_id for c in reliabilities if classify_stability(c) == "flaky"]

    lines: list[str] = []
    lines.append(f"# Run 2 pass^k — System {system_label} ({provider} {model})")
    lines.append("")
    if system_label == "A":
        lines.append("_Stage R2-6 reliability instrument for System A (deterministic-prior + GPT-5.4-mini hybrid). Same 10-case subset as the R2-5 System B pass^k; direct comparison made in the final R2-6 report._")
    else:
        lines.append("_Stage R2-5 reliability instrument. Layered on top of the 60-case R2-4A benchmark; measures whether the model's per-case successes and failures are stable across repeated independent calls. Not a replacement for the 60-case benchmark._")
    lines.append("")

    # 1. Model lock info
    lines.append("## 1. Model lock")
    lines.append("")
    lines.append(f"- run_id: `{run_id}`")
    lines.append(f"- provider: {provider}")
    lines.append(f"- requested_model: `{model}`")
    response_models = sorted({r.get("response_model") for r in raw_rows if r.get("response_model")})
    for rm in response_models:
        lines.append(f"- response_model observed: `{rm}`")
    lines.append("- system prompt + payload projection: unchanged from R2-4A (see `run2_model_prompts.py`)")
    lines.append("")

    # 2. Case subset
    lines.append("## 2. Case subset")
    lines.append("")
    lines.append(f"- total cases: {len(reliabilities)}")
    lines.append(f"- target-extension success-stability subset: {sorted(target_subset)}")
    lines.append(f"- current-row failure-stability subset: {sorted(current_subset)}")
    lines.append("- pre-registered in `product/evaluation/reports/run2_passk_subset.md`")
    lines.append("")

    # 3. k
    lines.append("## 3. k")
    lines.append("")
    lines.append(f"- k = {n_replicates_per_case}")
    lines.append(f"- total calls attempted: {len(reliabilities) * n_replicates_per_case}")
    lines.append("")

    # 4. Total calls
    lines.append("## 4. Total calls attempted")
    lines.append("")
    lines.append(f"- calls_attempted: {len(reliabilities) * n_replicates_per_case}")
    lines.append(f"- calls_completed (response received, non-skip): {costs.total_calls}")
    lines.append("")

    # 5. Parse success
    lines.append("## 5. Parse success")
    lines.append("")
    parse_counts: dict[str, int] = {}
    for c in reliabilities:
        parse_counts["parsed"] = parse_counts.get("parsed", 0) + c.n_parsed
        parse_counts["not_parsed"] = parse_counts.get("not_parsed", 0) + (
            c.n_replicates - c.n_parsed
        )
    for k in sorted(parse_counts):
        lines.append(f"- {k}: {parse_counts[k]}")
    lines.append("")

    # 6. Per-case reliability table
    lines.append("## 6. Per-case reliability")
    lines.append("")
    lines.extend(_per_case_table(reliabilities))
    lines.append("")

    # 7. Subset aggregate
    lines.append("## 7. Subset aggregate")
    lines.append("")
    lines.append("| subset | n | stable_success | stable_failure | flaky | mean all-pass | pass^k_all fraction | pass@k_any fraction |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label, agg in [
        ("overall", overall),
        ("target-extension success-stability", target_agg),
        ("current-row failure-stability", current_agg),
    ]:
        lines.append(
            f"| {label} | {agg['n_cases']} "
            f"| {agg['stable_success']} | {agg['stable_failure']} | {agg['flaky']} "
            f"| {agg['mean_all_components_pass_rate']:.3f} "
            f"| {agg['fraction_pass_to_the_k_all']:.3f} "
            f"| {agg['fraction_pass_at_k_any']:.3f} |"
        )
    lines.append("")

    # 8. Stable successes
    lines.append("## 8. Stable success cases (pass^k_all == true)")
    lines.append("")
    if stable_success:
        for cid in stable_success:
            c = next(r for r in reliabilities if r.case_id == cid)
            lines.append(
                f"- `{cid}` ({c.implementation_status}, {c.family}, "
                f"{c.expected_behavior_class}) — all {c.n_replicates} "
                f"replicates fully pass."
            )
    else:
        lines.append("- _none_")
    lines.append("")

    # 9. Stable failures
    lines.append("## 9. Stable failure cases (all_components_pass_rate == 0.0)")
    lines.append("")
    if stable_failure:
        for cid in stable_failure:
            c = next(r for r in reliabilities if r.case_id == cid)
            failing_axes = []
            if c.intent_correct_rate < 0.999:
                failing_axes.append(f"intent {c.intent_correct_rate:.2f}")
            if c.answerability_correct_rate < 0.999:
                failing_axes.append(f"ans {c.answerability_correct_rate:.2f}")
            if c.behavior_class_correct_rate < 0.999:
                failing_axes.append(f"beh {c.behavior_class_correct_rate:.2f}")
            if c.evidence_precision_mean < 0.999:
                failing_axes.append(f"evP {c.evidence_precision_mean:.2f}")
            if c.evidence_recall_mean < 0.999:
                failing_axes.append(f"evR {c.evidence_recall_mean:.2f}")
            if c.warning_precision_mean < 0.999:
                failing_axes.append(f"warnP {c.warning_precision_mean:.2f}")
            if c.warning_recall_mean < 0.999:
                failing_axes.append(f"warnR {c.warning_recall_mean:.2f}")
            if c.missing_field_recall_mean < 0.999:
                failing_axes.append(f"missR {c.missing_field_recall_mean:.2f}")
            lines.append(
                f"- `{cid}` ({c.implementation_status}, {c.family}, "
                f"{c.expected_behavior_class}) — 0/{c.n_replicates} pass; "
                f"failing axes: {', '.join(failing_axes) if failing_axes else 'composite-only'}."
            )
    else:
        lines.append("- _none_")
    lines.append("")

    # 10. Flaky cases
    lines.append("## 10. Flaky cases (some replicates pass, some do not)")
    lines.append("")
    if flaky:
        for cid in flaky:
            c = next(r for r in reliabilities if r.case_id == cid)
            lines.append(
                f"- `{cid}` ({c.implementation_status}, {c.family}, "
                f"{c.expected_behavior_class}) — all-pass rate "
                f"{c.all_components_pass_rate:.2f}; pass@k_any={c.pass_at_k_any} "
                f"pass^k_all={c.pass_to_the_k_all}"
            )
    else:
        lines.append("- _none_")
    lines.append("")

    # 11. Interpretation vs C-extended
    lines.append("## 11. Interpretation vs C-extended")
    lines.append("")
    lines.append(
        "The deterministic C-extended reference is stable on every case in this "
        "subset by construction: it is a rule-based contract emitter; replicate "
        "variance is zero. Every metric for C-extended on these 10 cases is the "
        "same as in the R2-3 closeout (all current rows clean modulo "
        "evidence_precision; all target_extension rows 1.000)."
    )
    lines.append("")
    lines.append(
        "B-GPT-5.4-mini's pass^k_all rate is therefore a strict reliability "
        "score: each case is either 1.0 (replicate-stable correct under the "
        "rubric) or strictly less. Stable failures are the cases where the "
        "model's R2-4A miss was *systematic*; flaky cases are the cases where "
        "R2-4A's single sample landed on a particular side of an unstable "
        "distribution."
    )
    lines.append("")

    # 12. Cost summary
    lines.append("## 12. Cost / token summary")
    lines.append("")
    lines.append(f"- total calls (non-skip): {costs.total_calls}")
    lines.append(f"- total latency (seconds): {costs.total_latency_seconds:.2f}")
    lines.append(f"- total prompt tokens: {costs.total_prompt_tokens}")
    lines.append(f"- total completion tokens: {costs.total_completion_tokens}")
    if costs.total_calls:
        lines.append(
            f"- mean latency / call: "
            f"{costs.total_latency_seconds / costs.total_calls:.2f} s"
        )
    lines.append("")

    return "\n".join(lines) + "\n"


def write_per_case_csv(
    path: Path, reliabilities: list[CaseReliability]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "case_id",
            "implementation_status",
            "family",
            "payload_condition",
            "expected_intent",
            "expected_behavior_class",
            "expected_answerability",
            "n_replicates",
            "n_parsed",
            "intent_correct_rate",
            "answerability_correct_rate",
            "behavior_class_correct_rate",
            "evidence_precision_mean",
            "evidence_recall_mean",
            "warning_precision_mean",
            "warning_recall_mean",
            "missing_field_recall_mean",
            "useful_refusal_correct_rate",
            "partial_answer_correct_rate",
            "all_components_pass_rate",
            "pass_at_k_any",
            "pass_to_the_k_all",
            "stability_class",
        ])
        for c in reliabilities:
            writer.writerow([
                c.case_id,
                c.implementation_status,
                c.family,
                c.payload_condition,
                c.expected_intent,
                c.expected_behavior_class,
                c.expected_answerability,
                c.n_replicates,
                c.n_parsed,
                f"{c.intent_correct_rate:.4f}",
                f"{c.answerability_correct_rate:.4f}",
                f"{c.behavior_class_correct_rate:.4f}",
                f"{c.evidence_precision_mean:.4f}",
                f"{c.evidence_recall_mean:.4f}",
                f"{c.warning_precision_mean:.4f}",
                f"{c.warning_recall_mean:.4f}",
                f"{c.missing_field_recall_mean:.4f}",
                "" if c.useful_refusal_correct_rate is None else f"{c.useful_refusal_correct_rate:.4f}",
                "" if c.partial_answer_correct_rate is None else f"{c.partial_answer_correct_rate:.4f}",
                f"{c.all_components_pass_rate:.4f}",
                int(c.pass_at_k_any),
                int(c.pass_to_the_k_all),
                classify_stability(c),
            ])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _model_slug(model: str) -> str:
    return model.replace("-", "").replace(".", "").lower()


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    cases = load_run2_cases(args.cases)
    by_id = {c.case_id: c for c in cases}

    scored_rows = _load_jsonl(args.scored)
    if not scored_rows:
        sys.stderr.write(f"no scored rows found at {args.scored}\n")
        return 2

    raw_rows = _load_jsonl(args.raw) if args.raw else []

    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in scored_rows:
        by_case[r["case_id"]].append(r)

    # Preserve insertion order to keep the subset memo's order in the report.
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for r in scored_rows:
        cid = r["case_id"]
        if cid in seen:
            continue
        seen.add(cid)
        ordered_ids.append(cid)

    reliabilities: list[CaseReliability] = []
    n_replicates = 0
    for cid in ordered_ids:
        case = by_id.get(cid)
        if case is None:
            sys.stderr.write(f"unknown case_id in scored.jsonl: {cid}\n")
            return 2
        replicate_scores = by_case[cid]
        n_replicates = max(n_replicates, len(replicate_scores))
        reliabilities.append(compute_case_reliability(case, replicate_scores))

    target_subset = {x.strip() for x in args.target_extension_ids.split(",") if x.strip()}
    current_subset = {x.strip() for x in args.current_failure_ids.split(",") if x.strip()}

    args.report_dir.mkdir(parents=True, exist_ok=True)
    if args.report_stem:
        stem = args.report_stem
    else:
        run_tail = args.run_id.replace("/", "_")
        stem = f"run2_passk_{_model_slug(args.model)}_{run_tail}"

    md_path = args.report_dir / f"{stem}.md"
    csv_path = args.report_dir / f"{stem}.csv"

    markdown = build_markdown_report(
        reliabilities=reliabilities,
        raw_rows=raw_rows,
        n_replicates_per_case=n_replicates,
        target_subset=target_subset,
        current_subset=current_subset,
        run_id=args.run_id,
        provider=args.provider,
        model=args.model,
        system_label=args.system,
    )
    md_path.write_text(markdown, encoding="utf-8")
    write_per_case_csv(csv_path, reliabilities)
    print(f"wrote markdown report: {md_path}")
    print(f"wrote per-case CSV:    {csv_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

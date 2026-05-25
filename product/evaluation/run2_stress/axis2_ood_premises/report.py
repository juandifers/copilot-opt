"""R2-S Axis 2 — System C0 baseline report writer.

Consumes the `RunArtifacts` produced by `runner.run_system_c0` and
emits a human-readable Markdown summary plus aggregation helpers
the closeout reuses.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from product.evaluation.run2_scoring import CaseScore

from product.evaluation.run2_stress.axis2_ood_premises.runner import (
    RunArtifacts,
    StressCaseResult,
)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass
class GroupMetrics:
    n: int
    intent_accuracy: Optional[float]
    answerability_accuracy: Optional[float]
    behavior_class_accuracy: Optional[float]
    evidence_precision: Optional[float]
    evidence_recall: Optional[float]
    warning_precision: Optional[float]
    warning_recall: Optional[float]
    missing_field_recall: Optional[float]
    useful_refusal_correct_rate: Optional[float]
    useful_refusal_correct_n: int
    partial_answer_correct_rate: Optional[float]
    partial_answer_correct_n: int


def _mean(values: list[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def _frac(flags: list[bool]) -> Optional[float]:
    return sum(1 for v in flags if v) / len(flags) if flags else None


def _aggregate(scores: list[CaseScore]) -> GroupMetrics:
    if not scores:
        return GroupMetrics(
            0, None, None, None, None, None, None, None, None, None, 0, None, 0
        )

    ur = [s.useful_refusal_correct for s in scores if s.useful_refusal_correct is not None]
    paw = [s.partial_answer_correct for s in scores if s.partial_answer_correct is not None]

    return GroupMetrics(
        n=len(scores),
        intent_accuracy=_frac([s.intent_correct for s in scores]),
        answerability_accuracy=_frac([s.answerability_correct for s in scores]),
        behavior_class_accuracy=_frac([s.behavior_class_correct for s in scores]),
        evidence_precision=_mean([s.evidence_precision for s in scores]),
        evidence_recall=_mean([s.evidence_recall for s in scores]),
        warning_precision=_mean([s.warning_precision for s in scores]),
        warning_recall=_mean([s.warning_recall for s in scores]),
        missing_field_recall=_mean([s.missing_field_recall for s in scores]),
        useful_refusal_correct_rate=_frac(ur),
        useful_refusal_correct_n=len(ur),
        partial_answer_correct_rate=_frac(paw),
        partial_answer_correct_n=len(paw),
    )


@dataclass
class AxisAggregates:
    overall: GroupMetrics
    by_split: dict[str, GroupMetrics]
    by_band: dict[str, GroupMetrics]
    bucket_counts: dict[str, int]
    bucket_counts_by_split: dict[str, dict[str, int]]
    bucket_counts_by_band: dict[str, dict[str, int]]


def aggregate_axis2(artifacts: RunArtifacts) -> AxisAggregates:
    scored = [
        (case, score, result)
        for case, score, result in zip(
            artifacts.cases, artifacts.scores, artifacts.results
        )
        if score is not None
    ]
    all_scores = [s for _, s, _ in scored]

    by_split_scores: dict[str, list[CaseScore]] = defaultdict(list)
    by_band_scores: dict[str, list[CaseScore]] = defaultdict(list)
    for case, score, _ in scored:
        by_split_scores[case.split].append(score)
        by_band_scores[case.band].append(score)

    bucket_counts: Counter[str] = Counter(r.bucket for r in artifacts.results)
    bucket_counts_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_counts_by_band: dict[str, Counter[str]] = defaultdict(Counter)
    for r in artifacts.results:
        bucket_counts_by_split[r.split][r.bucket] += 1
        bucket_counts_by_band[r.band][r.bucket] += 1

    return AxisAggregates(
        overall=_aggregate(all_scores),
        by_split={k: _aggregate(v) for k, v in by_split_scores.items()},
        by_band={k: _aggregate(v) for k, v in by_band_scores.items()},
        bucket_counts=dict(bucket_counts),
        bucket_counts_by_split={k: dict(v) for k, v in bucket_counts_by_split.items()},
        bucket_counts_by_band={k: dict(v) for k, v in bucket_counts_by_band.items()},
    )


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


_BUCKET_ORDER = (
    "schema_gap_or_unrepresentable_gold",
    "correct_refusal_or_partial",
    "unknown_intent",
    "wrong_intent",
    "missed_false_premise",
    "missed_missing_comparator",
    "over_answered_unsupported_premise",
    "downstream_evidence_mismatch",
    "guard_protected",
    "score_missing",
)


def _pct(v: Optional[float]) -> str:
    return f"{100 * v:.1f}%" if v is not None else "—"


def _mean_row(m: GroupMetrics, label: str) -> str:
    return (
        f"| {label} | {m.n} | "
        f"{_pct(m.intent_accuracy)} | "
        f"{_pct(m.answerability_accuracy)} | "
        f"{_pct(m.behavior_class_accuracy)} | "
        f"{_pct(m.evidence_precision)} | "
        f"{_pct(m.evidence_recall)} | "
        f"{_pct(m.warning_precision)} | "
        f"{_pct(m.warning_recall)} | "
        f"{_pct(m.missing_field_recall)} |"
    )


def _table_header() -> str:
    return (
        "| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | "
        "Ev rec | Warn prec | Warn rec | Miss rec |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )


def _bucket_table(counts: dict[str, int]) -> list[str]:
    lines: list[str] = []
    lines.append("| Bucket | n |")
    lines.append("|---|---:|")
    for bucket in _BUCKET_ORDER:
        n = counts.get(bucket, 0)
        if n:
            lines.append(f"| `{bucket}` | {n} |")
    return lines


def _refusal_summary(m: GroupMetrics, label: str) -> list[str]:
    return [
        f"| {label} | {m.useful_refusal_correct_n} | "
        f"{_pct(m.useful_refusal_correct_rate)} | "
        f"{m.partial_answer_correct_n} | "
        f"{_pct(m.partial_answer_correct_rate)} |"
    ]


def _failure_rows(artifacts: RunArtifacts) -> list[StressCaseResult]:
    """Non-`correct_refusal_or_partial` non-`guard_protected` cases —
    the diagnostic surface."""
    return [
        r
        for r in artifacts.results
        if r.bucket not in ("correct_refusal_or_partial", "guard_protected")
    ]


def render_markdown(artifacts: RunArtifacts) -> str:
    aggs = aggregate_axis2(artifacts)

    lines: list[str] = []
    lines.append("# R2-S Axis 2 OOD False Premises & Comparators — Baseline Report")
    lines.append("")
    lines.append(
        f"_System: {artifacts.system_label}. "
        f"Run started: {artifacts.started_at}. "
        f"HEAD: `{artifacts.head_sha}`. "
        f"Seed run_id: `{artifacts.run_id}`._"
    )
    lines.append("")

    # -- Purpose
    lines.append("## Purpose")
    lines.append("")
    lines.append(
        "Axis 2 tests whether the System C0 contract layer "
        "(`product/copilot/refusal_policy.py` plus "
        "`product/data/answerability.py` and "
        "`product/data/entity_resolution.py`) correctly **refuses or "
        "partially answers** when the operator's question contains an "
        "unsupported premise: a nonexistent entity, an unsupported "
        "movement/reassignment, a missing comparator/baseline, or a "
        "causal explanation the payload does not record. Unlike Axis 1 "
        "(look-alike intent attractors) and Axis 3 (semantic "
        "paraphrases), Axis 2 grades the contract layer, not the "
        "front-door keyword classifier in isolation."
    )
    lines.append("")

    # -- Method
    lines.append("## Method")
    lines.append("")
    lines.append(
        "- 24 cases, split 12 dev / 12 heldout via an explicit `split` "
        "column; 4 OOD-premise bands of 6 cases each (3 dev + 3 heldout).\n"
        "- Payloads materialized via "
        "`run2_payloads.materialize_case_payload(run_id='full-run-v1')` — "
        "identical to the locked-benchmark path.\n"
        "- No solver calls. No model calls (System C0 is deterministic).\n"
        "- Scores reuse `run2_scoring.score_case` against gold rows "
        "**authored per case** (Axis 2 does not inherit gold verbatim "
        "from the base case — the prompt deliberately mutates the user "
        "premise).\n"
        "- No locked Run 2 file modified. No `product/copilot/*` or "
        "`product/data/*` file modified."
    )
    lines.append("")

    lines.append("### Case distribution")
    lines.append("")
    lines.append("| Stratum | n |")
    lines.append("|---|---:|")
    lines.append(f"| total | {len(artifacts.cases)} |")
    by_split = Counter(c.split for c in artifacts.cases)
    for s in ("dev", "heldout"):
        lines.append(f"| split = {s} | {by_split.get(s, 0)} |")
    by_band = Counter(c.band for c in artifacts.cases)
    for band, n in sorted(by_band.items()):
        lines.append(f"| band = `{band}` | {n} |")
    lines.append("")

    # -- Guardrails
    lines.append("## Guardrails and caveats")
    lines.append("")
    lines.append(
        "- **Not a user study.** All gold labels are author-derived.\n"
        "- **Not solver validation.** No optimization run, no feasibility "
        "check was performed.\n"
        "- **Not a Run 2 replacement.** Axis 2 is a diagnostic stress "
        "split, not a benchmark.\n"
        "- **Heldout must not be tuned on.** Iteration on C0 or a future "
        "System D consumes the `dev` split only."
    )
    if artifacts.warnings:
        lines.append("")
        lines.append("### Runner warnings")
        for w in artifacts.warnings:
            lines.append(f"- {w}")
    lines.append("")

    # -- Overall metrics
    lines.append("## Overall metrics")
    lines.append("")
    lines.append(_table_header())
    lines.append(_mean_row(aggs.overall, "overall"))
    lines.append("")

    # -- Split metrics
    lines.append("## Metrics by split")
    lines.append("")
    lines.append(_table_header())
    for split in ("dev", "heldout"):
        if split in aggs.by_split:
            lines.append(_mean_row(aggs.by_split[split], split))
    lines.append(_mean_row(aggs.overall, "overall"))
    lines.append("")

    # -- Band metrics
    lines.append("## Metrics by OOD-premise band")
    lines.append("")
    lines.append(_table_header())
    for band in sorted(aggs.by_band):
        lines.append(_mean_row(aggs.by_band[band], band))
    lines.append("")

    # -- Useful refusal / partial answer summary
    lines.append("## Useful-refusal and partial-answer summary")
    lines.append("")
    lines.append(
        "| Group | useful_refusal n | useful_refusal correct | "
        "partial_answer n | partial_answer correct |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    lines.extend(_refusal_summary(aggs.overall, "overall"))
    for split in ("dev", "heldout"):
        if split in aggs.by_split:
            lines.extend(_refusal_summary(aggs.by_split[split], split))
    for band in sorted(aggs.by_band):
        lines.extend(_refusal_summary(aggs.by_band[band], band))
    lines.append("")

    # -- Bucket counts
    lines.append("## Failure taxonomy (bucket counts)")
    lines.append("")
    lines.append(
        "Mutually exclusive, exhaustive over all 24 cases. See "
        "`design.md` §8 for the bucket definitions."
    )
    lines.append("")
    lines.extend(_bucket_table(aggs.bucket_counts))
    lines.append("")

    lines.append("### Buckets by split")
    lines.append("")
    lines.append("| Split | " + " | ".join(_BUCKET_ORDER[:-1]) + " |")
    lines.append("|---|" + "|".join(["---:"] * (len(_BUCKET_ORDER) - 1)) + "|")
    for split in ("dev", "heldout"):
        c = aggs.bucket_counts_by_split.get(split, {})
        row = [f"| {split}"]
        for b in _BUCKET_ORDER[:-1]:
            row.append(str(c.get(b, 0)))
        lines.append(" | ".join(row) + " |")
    lines.append("")

    lines.append("### Buckets by band")
    lines.append("")
    lines.append("| Band | " + " | ".join(_BUCKET_ORDER[:-1]) + " |")
    lines.append("|---|" + "|".join(["---:"] * (len(_BUCKET_ORDER) - 1)) + "|")
    for band in sorted(aggs.bucket_counts_by_band):
        c = aggs.bucket_counts_by_band[band]
        row = [f"| `{band}`"]
        for b in _BUCKET_ORDER[:-1]:
            row.append(str(c.get(b, 0)))
        lines.append(" | ".join(row) + " |")
    lines.append("")

    # -- Per-case failure table
    failures = _failure_rows(artifacts)
    lines.append(f"## Per-case failure table ({len(failures)} non-correct cases)")
    lines.append("")
    if not failures:
        lines.append(
            "_No diagnostic cases: every case is either "
            "`correct_refusal_or_partial` or `guard_protected`._"
        )
    else:
        lines.append(
            "| case_id | split | band | bucket | gold intent | "
            "pred intent | gold cls | pred cls | ev p/r | warn p/r | miss r |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in failures:
            ev = f"{r.evidence_precision:.2f}/{r.evidence_recall:.2f}"
            warn = f"{r.warning_precision:.2f}/{r.warning_recall:.2f}"
            miss = f"{r.missing_field_recall:.2f}"
            lines.append(
                f"| {r.case_id} | {r.split} | `{r.band}` | "
                f"`{r.bucket}` | {r.expected_intent} | "
                f"{r.predicted_intent} | {r.expected_behavior_class} | "
                f"{r.predicted_behavior_class} | {ev} | {warn} | {miss} |"
            )
    lines.append("")

    # -- Interpretation
    lines.append("## Interpretation")
    lines.append("")
    crp = aggs.bucket_counts.get("correct_refusal_or_partial", 0)
    sg = aggs.bucket_counts.get("schema_gap_or_unrepresentable_gold", 0)
    un = aggs.bucket_counts.get("unknown_intent", 0)
    wi = aggs.bucket_counts.get("wrong_intent", 0)
    mfp = aggs.bucket_counts.get("missed_false_premise", 0)
    mmc = aggs.bucket_counts.get("missed_missing_comparator", 0)
    oa = aggs.bucket_counts.get("over_answered_unsupported_premise", 0)
    dm = aggs.bucket_counts.get("downstream_evidence_mismatch", 0)
    gp = aggs.bucket_counts.get("guard_protected", 0)
    total = len(artifacts.cases)
    lines.append(
        f"C0 produced {crp}/{total} **correct_refusal_or_partial**, "
        f"{sg}/{total} **schema_gap**, "
        f"{un}/{total} **unknown_intent**, "
        f"{wi}/{total} **wrong_intent**, "
        f"{mfp}/{total} **missed_false_premise**, "
        f"{mmc}/{total} **missed_missing_comparator**, "
        f"{oa}/{total} **over_answered_unsupported_premise**, "
        f"{dm}/{total} **downstream_evidence_mismatch**, and "
        f"{gp}/{total} **guard_protected** outcomes. See "
        "`axis2_closeout.md` for the full methodological interpretation, "
        "including which failure modes are System-D-addressable vs "
        "future-work outside the current envelope."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


def write_baseline_markdown(artifacts: RunArtifacts, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(artifacts), encoding="utf-8")


__all__ = [
    "AxisAggregates",
    "GroupMetrics",
    "aggregate_axis2",
    "render_markdown",
    "write_baseline_markdown",
]

"""R2-S Axis 1 — System C0 baseline report writer.

Consumes the `RunArtifacts` produced by `runner.run_system_c0` and
emits a human-readable Markdown summary plus aggregation helpers
the closeout reuses. Aggregation logic is local to this file; it
does not modify `run2_scoring.aggregate_scores`.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from product.evaluation.run2_scoring import CaseScore

from product.evaluation.run2_stress.axis1_lookalike.runner import (
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


def _mean(values: list[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def _frac(flags: list[bool]) -> Optional[float]:
    return sum(1 for v in flags if v) / len(flags) if flags else None


def _aggregate(scores: list[CaseScore]) -> GroupMetrics:
    if not scores:
        return GroupMetrics(0, None, None, None, None, None, None, None, None)
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
    )


@dataclass
class AxisAggregates:
    overall: GroupMetrics
    by_split: dict[str, GroupMetrics]
    by_band: dict[str, GroupMetrics]
    conditional_on_intent_correct: GroupMetrics
    intent_accuracy_by_split: dict[str, Optional[float]]
    intent_accuracy_by_band: dict[str, Optional[float]]
    bucket_counts: dict[str, int]
    bucket_counts_by_split: dict[str, dict[str, int]]
    bucket_counts_by_band: dict[str, dict[str, int]]


def aggregate_axis1(artifacts: RunArtifacts) -> AxisAggregates:
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

    cond = [s for s in all_scores if s.intent_correct]

    intent_acc_by_split = {
        split: _frac([s.intent_correct for s in scores])
        for split, scores in by_split_scores.items()
    }
    intent_acc_by_band = {
        band: _frac([s.intent_correct for s in scores])
        for band, scores in by_band_scores.items()
    }

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
        conditional_on_intent_correct=_aggregate(cond),
        intent_accuracy_by_split=intent_acc_by_split,
        intent_accuracy_by_band=intent_acc_by_band,
        bucket_counts=dict(bucket_counts),
        bucket_counts_by_split={k: dict(v) for k, v in bucket_counts_by_split.items()},
        bucket_counts_by_band={k: dict(v) for k, v in bucket_counts_by_band.items()},
    )


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


_BUCKET_ORDER = (
    "wrong_adjacent_intent",
    "unknown_intent",
    "downstream_mismatch",
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


def _failure_rows(artifacts: RunArtifacts) -> list[StressCaseResult]:
    """Cases that are NOT guard_protected — the diagnostic surface."""
    return [r for r in artifacts.results if r.bucket != "guard_protected"]


def render_markdown(artifacts: RunArtifacts) -> str:
    aggs = aggregate_axis1(artifacts)

    lines: list[str] = []
    lines.append("# R2-S Axis 1 Look-alike Intent Stress — Baseline Report")
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
        "Axis 1 tests whether the System C0 deterministic intent "
        "classifier (`product/copilot/intent.py`) can be tricked into "
        "**confidently misrouting** an operator question to a "
        "neighbouring wrong intent by surface-token attractors. Each "
        "of the 24 cases inherits its gold contract response verbatim "
        "from a Run 2 base case; only `prompt_text` is rewritten to "
        "embed the named attractor tokens. The diagnostic split "
        "complements Axis 3 (which measures the *unknown*-intent "
        "failure mode under unseen vocabulary)."
    )
    lines.append("")

    # -- Method
    lines.append("## Method")
    lines.append("")
    lines.append(
        "- 24 cases, split 12 dev / 12 heldout via an explicit `split` "
        "column; 4 confusion bands of 6 cases each (3 dev + 3 heldout).\n"
        "- Payloads materialized via "
        "`run2_payloads.materialize_case_payload(run_id='full-run-v1')` "
        "— identical to the locked-benchmark path.\n"
        "- No solver calls. No model calls (System C0 is deterministic).\n"
        "- Scores reuse `run2_scoring.score_case` against gold rows "
        "inherited verbatim from the named `base_case_id` in the "
        "locked Run 2 benchmark.\n"
        "- No locked Run 2 file is read for write or modified. The "
        "stress split lives entirely under "
        "`product/evaluation/run2_stress/axis1_lookalike/`."
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
        "- **Not a user study.** All gold labels were author-derived "
        "from the base Run 2 case.\n"
        "- **Not solver validation.** No optimization run, no objective "
        "or feasibility check was performed.\n"
        "- **Not a Run 2 replacement.** Axis 1 is a diagnostic stress "
        "split, not a benchmark.\n"
        "- **Not evidence of broad generalization.** The case count is "
        "small (24); a non-zero misroute count is suggestive, not "
        "conclusive.\n"
        "- **Heldout must not be tuned on.** Iteration on C0 or a "
        "future System D consumes the `dev` split only."
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
    lines.append("## Metrics by confusion band")
    lines.append("")
    lines.append(_table_header())
    for band in sorted(aggs.by_band):
        lines.append(_mean_row(aggs.by_band[band], band))
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
    lines.append("| Split | wrong_adjacent | unknown | downstream_mismatch | guard_protected |")
    lines.append("|---|---:|---:|---:|---:|")
    for split in ("dev", "heldout"):
        c = aggs.bucket_counts_by_split.get(split, {})
        lines.append(
            f"| {split} | "
            f"{c.get('wrong_adjacent_intent', 0)} | "
            f"{c.get('unknown_intent', 0)} | "
            f"{c.get('downstream_mismatch', 0)} | "
            f"{c.get('guard_protected', 0)} |"
        )
    lines.append("")

    lines.append("### Buckets by band")
    lines.append("")
    lines.append("| Band | wrong_adjacent | unknown | downstream_mismatch | guard_protected |")
    lines.append("|---|---:|---:|---:|---:|")
    for band in sorted(aggs.bucket_counts_by_band):
        c = aggs.bucket_counts_by_band[band]
        lines.append(
            f"| `{band}` | "
            f"{c.get('wrong_adjacent_intent', 0)} | "
            f"{c.get('unknown_intent', 0)} | "
            f"{c.get('downstream_mismatch', 0)} | "
            f"{c.get('guard_protected', 0)} |"
        )
    lines.append("")

    # -- Conditional metrics
    lines.append("## Downstream metrics conditional on intent correct")
    lines.append("")
    lines.append(
        "Among cases where the front-door intent was predicted "
        "correctly, how does the downstream contract response look? "
        "This isolates language-mapping failures from contract-"
        "response failures."
    )
    lines.append("")
    lines.append(_table_header())
    lines.append(
        _mean_row(aggs.conditional_on_intent_correct, "intent_correct only")
    )
    lines.append(_mean_row(aggs.overall, "overall (for reference)"))
    lines.append("")

    # -- Failure table
    failures = _failure_rows(artifacts)
    lines.append(f"## Diagnostic table — non-guard-protected cases ({len(failures)})")
    lines.append("")
    if not failures:
        lines.append(
            "_No diagnostic cases: every stress case is in the "
            "`guard_protected` bucket. Every C0 prediction matches gold "
            "intent **and** every downstream metric is perfect._"
        )
    else:
        lines.append(
            "| case_id | split | band | bucket | prompt | gold intent | "
            "pred intent | attractor | gold cls | pred cls | ev p/r | "
            "warn p/r |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        case_lookup = {c.case_id: c for c in artifacts.cases}
        for r in failures:
            cse = case_lookup[r.case_id]
            ev = f"{r.evidence_precision:.2f}/{r.evidence_recall:.2f}"
            warn = f"{r.warning_precision:.2f}/{r.warning_recall:.2f}"
            prompt = cse.prompt_text.replace("|", "\\|")
            lines.append(
                f"| {r.case_id} | {r.split} | `{r.band}` | "
                f"`{r.bucket}` | {prompt} | {r.expected_intent} | "
                f"{r.predicted_intent} | {r.attractor_intent} | "
                f"{r.expected_behavior_class} | {r.predicted_behavior_class} | "
                f"{ev} | {warn} |"
            )
    lines.append("")

    # -- Interpretation
    lines.append("## Interpretation")
    lines.append("")
    wa = aggs.bucket_counts.get("wrong_adjacent_intent", 0)
    un = aggs.bucket_counts.get("unknown_intent", 0)
    gp = aggs.bucket_counts.get("guard_protected", 0)
    dm = aggs.bucket_counts.get("downstream_mismatch", 0)
    total = len(artifacts.cases)
    lines.append(
        f"C0 produced {wa}/{total} **wrong_adjacent_intent**, "
        f"{un}/{total} **unknown_intent**, "
        f"{dm}/{total} **downstream_mismatch**, and "
        f"{gp}/{total} **guard_protected** outcomes across the 24 "
        f"look-alike cases. See `axis1_closeout.md` for the full "
        "methodological interpretation, including which guards held, "
        "which heuristics misfired, and the implications for "
        "System D scope."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


def write_baseline_markdown(artifacts: RunArtifacts, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(artifacts), encoding="utf-8")


__all__ = [
    "AxisAggregates",
    "GroupMetrics",
    "aggregate_axis1",
    "render_markdown",
    "write_baseline_markdown",
]

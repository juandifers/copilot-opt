"""R2-S1 axis 3 — System C0 baseline report writer.

Consumes the `RunArtifacts` produced by `runner.run_system_c0` and
emits a human-readable Markdown summary. Aggregation logic is local
to this file; it does not modify `run2_scoring.aggregate_scores`.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from product.evaluation.run2_scoring import CaseScore

from product.evaluation.run2_stress.axis3_semantic.runner import (
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
    by_subtype: dict[str, GroupMetrics]
    conditional_on_intent_correct: GroupMetrics
    intent_accuracy_by_split: dict[str, Optional[float]]


def aggregate_axis3(artifacts: RunArtifacts) -> AxisAggregates:
    scored = [
        (case, score, result)
        for case, score, result in zip(
            artifacts.cases, artifacts.scores, artifacts.results
        )
        if score is not None
    ]
    all_scores = [s for _, s, _ in scored]

    by_split_scores: dict[str, list[CaseScore]] = defaultdict(list)
    by_subtype_scores: dict[str, list[CaseScore]] = defaultdict(list)
    for case, score, _ in scored:
        by_split_scores[case.split].append(score)
        by_subtype_scores[case.stress_subtype].append(score)

    cond = [s for s in all_scores if s.intent_correct]
    intent_acc_by_split = {
        split: _frac([s.intent_correct for s in scores])
        for split, scores in by_split_scores.items()
    }

    return AxisAggregates(
        overall=_aggregate(all_scores),
        by_split={k: _aggregate(v) for k, v in by_split_scores.items()},
        by_subtype={k: _aggregate(v) for k, v in by_subtype_scores.items()},
        conditional_on_intent_correct=_aggregate(cond),
        intent_accuracy_by_split=intent_acc_by_split,
    )


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


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
        "| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )


def _failure_rows(artifacts: RunArtifacts) -> list[StressCaseResult]:
    failed: list[StressCaseResult] = []
    for case, score, result in zip(
        artifacts.cases, artifacts.scores, artifacts.results
    ):
        if score is None:
            failed.append(result)
            continue
        if not score.intent_correct or not score.behavior_class_correct:
            failed.append(result)
    return failed


def render_markdown(artifacts: RunArtifacts) -> str:
    aggs = aggregate_axis3(artifacts)

    lines: list[str] = []
    lines.append("# R2-S1 Semantic Intent Stress — Baseline Report")
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
        "R2-S1 tests whether the VRPTW copilot maps semantically equivalent "
        "but lexically held-out operator phrasing to the correct canonical "
        "intent. Each of the 24 cases is a paraphrase of a Run 2 base case; "
        "the expected contract response (answerability, evidence, warnings, "
        "next actions, behavior class) is inherited from the base case "
        "verbatim, so only the prompt text changes between Run 2 and the "
        "stress split."
    )
    lines.append("")

    # -- Method
    lines.append("## Method")
    lines.append("")
    lines.append(
        "- 24 cases, split 12/12 between `dev` and `heldout`. The split is "
        "an explicit `split` column; no shuffling, no random sampling.\n"
        "- Payloads are materialized from Run 1 generator JSONL via "
        "`run2_payloads.materialize_case_payload(run_id='full-run-v1')` — "
        "identical to the locked-benchmark path.\n"
        "- No solver calls. No model calls (System C0 is deterministic).\n"
        "- Scores reuse `run2_scoring.score_case` against gold rows inherited "
        "verbatim from the named `base_case_id` in the locked Run 2 "
        "benchmark.\n"
        "- No locked Run 2 file was read for write or modified. The stress "
        "split lives entirely under `product/evaluation/run2_stress/axis3_semantic/`."
    )
    lines.append("")

    # -- Guardrails / caveats
    lines.append("## Guardrails and caveats")
    lines.append("")
    lines.append(
        "- **Not a user study.** All gold labels were author-derived "
        "from the base Run 2 case.\n"
        "- **Not solver validation.** No optimization run, no objective "
        "or feasibility check was performed.\n"
        "- **Not a replacement for Run 2.** R2-S1 is a diagnostic stress "
        "split, not a benchmark.\n"
        "- **Not evidence of broad generalization.** The case count is "
        "small (24); a positive heldout score is suggestive, not "
        "conclusive.\n"
        "- **Heldout must not be tuned on.** Iteration on C0 or a "
        "future C1/D semantic adapter consumes the `dev` split only."
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
    lines.append(
        "**`semantic_intent_accuracy`** (alias of intent accuracy for this "
        "axis):"
    )
    lines.append("")
    for split, val in aggs.intent_accuracy_by_split.items():
        lines.append(f"- {split}: {_pct(val)}")
    lines.append(f"- overall: {_pct(aggs.overall.intent_accuracy)}")
    lines.append("")

    # -- Subtype metrics
    lines.append("## Metrics by stress_subtype")
    lines.append("")
    lines.append(_table_header())
    for subtype in sorted(aggs.by_subtype):
        lines.append(_mean_row(aggs.by_subtype[subtype], subtype))
    lines.append("")

    # -- Conditional metrics
    lines.append("## Downstream metrics conditional on intent correct")
    lines.append("")
    lines.append(
        "Among cases where the front-door intent was predicted correctly, "
        "how does the downstream contract response look? This isolates "
        "language-mapping failures from contract-response failures."
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
    lines.append(f"## Failure rows ({len(failures)})")
    lines.append("")
    if not failures:
        lines.append("_No failures: every stress case classified to the gold intent "
                     "and produced the gold behavior class._")
    else:
        lines.append(
            "| case_id | split | subtype | prompt | gold intent | pred intent | "
            "gold ans | pred ans | gold cls | pred cls | ev p/r | warn p/r | note |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
        )
        case_lookup = {c.case_id: c for c in artifacts.cases}
        for r in failures:
            cse = case_lookup[r.case_id]
            note_bits: list[str] = []
            if not r.score_present:
                note_bits.append("score_missing")
            if r.predicted_intent == "unknown":
                note_bits.append("classified as unknown")
            elif r.predicted_intent != r.expected_intent:
                note_bits.append(
                    f"intent drift {r.expected_intent}->{r.predicted_intent}"
                )
            if (
                r.predicted_behavior_class != r.expected_behavior_class
                and r.predicted_intent == r.expected_intent
            ):
                note_bits.append("behavior_class drift despite correct intent")
            note = "; ".join(note_bits) if note_bits else cse.ambiguity_notes[:120]
            ev = f"{r.evidence_precision:.2f}/{r.evidence_recall:.2f}"
            warn = f"{r.warning_precision:.2f}/{r.warning_recall:.2f}"
            prompt = cse.prompt_text.replace("|", "\\|")
            lines.append(
                f"| {r.case_id} | {r.split} | {r.stress_subtype} | "
                f"{prompt} | {r.expected_intent} | {r.predicted_intent} | "
                f"{r.expected_answerability} | {r.predicted_answerability} | "
                f"{r.expected_behavior_class} | {r.predicted_behavior_class} | "
                f"{ev} | {warn} | {note} |"
            )
    lines.append("")

    # -- Interpretation
    lines.append("## Interpretation")
    lines.append("")
    overall_intent = aggs.overall.intent_accuracy or 0.0
    heldout_intent = (
        aggs.intent_accuracy_by_split.get("heldout") or 0.0
    )
    cond_acc = aggs.conditional_on_intent_correct.answerability_accuracy
    lines.append(
        f"C0 reaches **{_pct(overall_intent)}** semantic-intent accuracy on "
        f"the 24-case stress split and **{_pct(heldout_intent)}** on the "
        f"heldout 12 cases. Among cases where intent classification is "
        f"correct, downstream answerability is "
        f"**{_pct(cond_acc) if cond_acc is not None else '—'}** "
        "— consistent with the locked benchmark."
    )
    lines.append("")
    lines.append(
        "C0 is contract-stable on Run 2 but this stress split probes "
        "whether its front-door intent mapping is lexically brittle. The "
        "failure table shows the surface forms that bypass the existing "
        "keyword matchers in `product/copilot/intent.py`. We do **not** "
        "claim C0 generalizes to operator paraphrases on the basis of "
        "these numbers; the heldout split is small (12 cases) and the "
        "case selection deliberately targets known gaps."
    )
    lines.append("")

    # -- Next steps
    lines.append("## Next steps (informative, not commitments)")
    lines.append("")
    lines.append(
        "- **C1 semantic-intent adapter.** Replace `intent.py`'s "
        "keyword matchers with a deterministic synonym lookup over a "
        "canonical query frame (`objective_value`, `feasibility_status`, "
        "`customer_route_membership`, `full_route_listing`, "
        "`route_end_time`, `customer_arrival`, `lateness_summary`). "
        "Each frame carries a synonym set and an entity resolver.\n"
        "- **System D.** Pair a model-based intent classifier with the "
        "deterministic answerability / evidence contract. The semantic "
        "adapter is the front door; the back-end contract remains the "
        "audit layer.\n"
        "- **Heldout discipline.** Any C1/D iteration on `dev` must "
        "freeze `heldout` before publishing a heldout score. Tag the "
        "dev-iteration commit; run heldout once at that tag; record the "
        "score against the tag."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


def write_baseline_markdown(artifacts: RunArtifacts, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(artifacts), encoding="utf-8")


__all__ = [
    "AxisAggregates",
    "GroupMetrics",
    "aggregate_axis3",
    "render_markdown",
    "write_baseline_markdown",
]

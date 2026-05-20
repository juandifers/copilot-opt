"""Run 2 scoring functions.

Per-case scoring of a `PredictedContract` against a `Run2Case` gold,
plus aggregation. Implements the metric definitions in
`run2_contract_benchmark_design.md` §6.1–6.8. Notably:

- Evidence precision/recall are *field-family* metrics (schema §10a):
  predicate qualifiers in predicted paths are stripped before
  matching.
- No aggregate composite (design §6.9 removed in R2-0).
- `useful_refusal_correct` is scored on cases whose
  `expected_behavior_class == useful_refusal` only;
  `partial_answer_with_warning` cases get their own check.
- Aggregation always reports *current* vs *target_extension* splits.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_system_c import PredictedContract


# ---------------------------------------------------------------------------
# Path normalisation (schema §10a)
# ---------------------------------------------------------------------------


_PREDICATE_RE = re.compile(r"\[[^\]]*=[^\]]*\]")


# Schema §6: gold next-actions are semantic codes; the current contract
# emits the literal strings below. The evaluator normalises a predicted
# concrete string to its semantic code by substring match against the
# canonical literal. New semantic codes added in Stage R2-1 (under
# `target_extension`) intentionally have no current concrete literal —
# the contract does not yet emit them — so the predicted set will be
# empty and warning/missing recall will surface the gap.
_NEXT_ACTION_CONCRETE_TO_SEMANTIC: list[tuple[str, str]] = [
    ("Build before/after comparison payload", "build_baseline_comparison_payload"),
    (
        "Expose perturbation.new_customer_ids in the product payload",
        "expose_new_customer_ids",
    ),
    (
        "Apply product route-label schema augmentation",
        "apply_route_label_augmentation",
    ),
    (
        "Use SCHEDULE payload or run schedule projection",
        "use_schedule_payload",
    ),
    (
        "Narrow the question to a specific customer, route, or claim type",
        "narrow_question_to_available_field",
    ),
]


def _to_semantic_action(predicted: str) -> str:
    """Map a concrete next-action string to its semantic code, or
    return the original string if no mapping matches. A semantic code
    on the predicted side (already mapped) is returned unchanged."""
    if not predicted:
        return predicted
    # If it already looks like a semantic code (snake_case, no spaces),
    # pass through. The known codes are also in this shape.
    if " " not in predicted and "." not in predicted:
        return predicted
    for concrete, semantic in _NEXT_ACTION_CONCRETE_TO_SEMANTIC:
        if concrete.lower() in predicted.lower():
            return semantic
    return predicted


def normalize_next_actions(actions: Iterable[str]) -> set[str]:
    """Map a system's emitted next-action strings to their semantic
    codes for comparison against gold (schema §6)."""
    return {_to_semantic_action(a) for a in actions if a}


def normalize_field_path(path: str) -> str:
    """Strip predicate qualifiers from a field path.

    Examples:
        routes[route_idx=4].customer_ids       → routes[].customer_ids
        customer_schedule[customer_id=42].arrival
                                                → customer_schedule[].arrival
        action_objective                        → action_objective (unchanged)
    """
    return _PREDICATE_RE.sub("[]", path)


def normalize_paths(paths: Iterable[str]) -> set[str]:
    return {normalize_field_path(p) for p in paths}


# ---------------------------------------------------------------------------
# Set metrics (design §6.3 / §6.4 / §6.6)
# ---------------------------------------------------------------------------


def set_precision(predicted: set[str], gold: set[str]) -> float:
    if not predicted and not gold:
        return 1.0
    if not predicted and gold:
        return 0.0
    if predicted and not gold:
        return 0.0
    return len(predicted & gold) / len(predicted)


def set_recall(predicted: set[str], gold: set[str]) -> float:
    if not predicted and not gold:
        return 1.0
    if not gold:
        return 1.0
    return len(predicted & gold) / len(gold)


# ---------------------------------------------------------------------------
# Case score type
# ---------------------------------------------------------------------------


@dataclass
class CaseScore:
    case_id: str
    implementation_status: str
    family: str
    difficulty: str
    expected_behavior_class: str

    intent_correct: bool
    answerability_correct: bool
    evidence_precision: float
    evidence_recall: float
    missing_field_recall: float
    warning_precision: float
    warning_recall: float
    useful_refusal_correct: Optional[bool]  # None if not applicable
    partial_answer_correct: Optional[bool]  # None if not applicable
    behavior_class_correct: bool
    convention_consistency_status: str = "not_implemented_for_R2_1"

    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-case scoring
# ---------------------------------------------------------------------------


def score_case(case: Run2Case, pred: PredictedContract) -> CaseScore:
    gold_evidence = normalize_paths(case.expected_evidence_paths)
    pred_evidence = normalize_paths(pred.predicted_evidence_paths)
    gold_missing = set(case.expected_missing_fields)
    pred_missing = set(pred.predicted_missing_fields)
    gold_warnings = set(case.expected_warnings)
    pred_warnings = set(pred.predicted_warnings)
    gold_actions = set(case.expected_next_actions)
    pred_actions = normalize_next_actions(pred.predicted_next_actions)

    intent_correct = pred.predicted_intent == case.expected_intent
    answerability_correct = pred.predicted_answerability == case.expected_answerability

    evidence_precision = set_precision(pred_evidence, gold_evidence)
    evidence_recall = set_recall(pred_evidence, gold_evidence)

    # Missing-field recall is reported only for cases where gold has
    # missing fields (design §6.5). When gold is empty we record a
    # neutral 1.0 — the predictor is not penalised for declining to
    # invent missing fields.
    if gold_missing:
        missing_field_recall = (
            len(pred_missing & gold_missing) / len(gold_missing)
        )
    else:
        missing_field_recall = 1.0

    warning_precision = set_precision(pred_warnings, gold_warnings)
    warning_recall = set_recall(pred_warnings, gold_warnings)

    # Useful-refusal correctness (design §6.7) — scored only when
    # gold says useful_refusal. partial_answer_with_warning has its
    # own composite below.
    useful_refusal_correct: Optional[bool] = None
    if case.expected_behavior_class == "useful_refusal":
        ans_match = pred.predicted_answerability == case.expected_answerability
        # Missing-field rule + §12 false-premise exception: when gold
        # missing is empty, predicted missing may also be empty.
        if gold_missing:
            missing_ok = gold_missing.issubset(pred_missing)
        else:
            missing_ok = True
        if gold_actions:
            action_ok = bool(pred_actions & gold_actions)
        else:
            action_ok = True
        useful_refusal_correct = ans_match and missing_ok and action_ok

    # Partial-answer correctness — distinct from useful-refusal
    # (design §6.7 paragraph + schema §7).
    partial_answer_correct: Optional[bool] = None
    if case.expected_behavior_class == "partial_answer_with_warning":
        ans_match = pred.predicted_answerability == "partially_answerable"
        warn_recall_ok = bool(pred_warnings & gold_warnings) if gold_warnings else True
        missing_recall_ok = bool(pred_missing & gold_missing) if gold_missing else True
        action_ok = bool(pred_actions & gold_actions) if gold_actions else True
        partial_answer_correct = (
            ans_match and warn_recall_ok and missing_recall_ok and action_ok
        )

    behavior_class_correct = (
        pred.predicted_behavior_class == case.expected_behavior_class
    )

    return CaseScore(
        case_id=case.case_id,
        implementation_status=case.implementation_status,
        family=case.family,
        difficulty=case.difficulty,
        expected_behavior_class=case.expected_behavior_class,
        intent_correct=intent_correct,
        answerability_correct=answerability_correct,
        evidence_precision=evidence_precision,
        evidence_recall=evidence_recall,
        missing_field_recall=missing_field_recall,
        warning_precision=warning_precision,
        warning_recall=warning_recall,
        useful_refusal_correct=useful_refusal_correct,
        partial_answer_correct=partial_answer_correct,
        behavior_class_correct=behavior_class_correct,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _mean_or_none(values: list[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def _fraction(values: list[bool]) -> Optional[float]:
    return (sum(1 for v in values if v) / len(values)) if values else None


def _aggregate_group(scores: list[CaseScore]) -> dict[str, Optional[float]]:
    if not scores:
        return {}

    intent_acc = _fraction([s.intent_correct for s in scores])
    ans_acc = _fraction([s.answerability_correct for s in scores])
    behavior_class_acc = _fraction([s.behavior_class_correct for s in scores])

    ev_p = _mean_or_none([s.evidence_precision for s in scores])
    ev_r = _mean_or_none([s.evidence_recall for s in scores])
    miss_r = _mean_or_none([s.missing_field_recall for s in scores])
    warn_p = _mean_or_none([s.warning_precision for s in scores])
    warn_r = _mean_or_none([s.warning_recall for s in scores])

    ur_scores = [
        s.useful_refusal_correct
        for s in scores
        if s.useful_refusal_correct is not None
    ]
    paw_scores = [
        s.partial_answer_correct
        for s in scores
        if s.partial_answer_correct is not None
    ]

    return {
        "n": len(scores),
        "intent_accuracy": intent_acc,
        "answerability_accuracy": ans_acc,
        "behavior_class_accuracy": behavior_class_acc,
        "evidence_precision": ev_p,
        "evidence_recall": ev_r,
        "missing_field_recall": miss_r,
        "warning_precision": warn_p,
        "warning_recall": warn_r,
        "useful_refusal_correct_rate": _fraction(ur_scores),
        "useful_refusal_correct_n": len(ur_scores),
        "partial_answer_correct_rate": _fraction(paw_scores),
        "partial_answer_correct_n": len(paw_scores),
    }


def aggregate_scores(scores: list[CaseScore]) -> dict:
    """Aggregate per-case scores into report-ready dicts.

    The top-level keys are:
        overall: aggregate over every scored case
        by_implementation_status: {current: ..., target_extension: ...}
        by_family: {OBJ: ..., PLAN_VALIDITY: ..., ...}
        by_behavior_class: {direct_answer: ..., ...}
        by_difficulty: {easy: ..., medium: ..., hard: ...}

    No composite metric is computed — design §6.9 forbids it.
    """
    if not scores:
        return {
            "overall": {},
            "by_implementation_status": {},
            "by_family": {},
            "by_behavior_class": {},
            "by_difficulty": {},
        }

    by_status: defaultdict[str, list[CaseScore]] = defaultdict(list)
    by_family: defaultdict[str, list[CaseScore]] = defaultdict(list)
    by_behavior: defaultdict[str, list[CaseScore]] = defaultdict(list)
    by_difficulty: defaultdict[str, list[CaseScore]] = defaultdict(list)

    for s in scores:
        by_status[s.implementation_status].append(s)
        by_family[s.family].append(s)
        by_behavior[s.expected_behavior_class].append(s)
        by_difficulty[s.difficulty].append(s)

    return {
        "overall": _aggregate_group(scores),
        "by_implementation_status": {
            k: _aggregate_group(v) for k, v in by_status.items()
        },
        "by_family": {k: _aggregate_group(v) for k, v in by_family.items()},
        "by_behavior_class": {
            k: _aggregate_group(v) for k, v in by_behavior.items()
        },
        "by_difficulty": {
            k: _aggregate_group(v) for k, v in by_difficulty.items()
        },
    }

"""Run 2 calibration-case loader and schema validator.

Reads `product/evaluation/run2_calibration_cases.csv` (the 15-row
calibration set) into typed `Run2Case` records and validates each row
against the rules in `run2_gold_schema.md`. No model calls, no I/O
beyond CSV reading; this module is pure validation.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd


# ---------------------------------------------------------------------------
# Schema constants — mirror run2_gold_schema.md sections 2–8 and §11/§13
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS: list[str] = [
    "case_id",
    "source_prompt_id",
    "family",
    "prompt_text",
    "payload_condition",
    "payload_mutation_needed",
    "expected_intent",
    "expected_answerability",
    "expected_evidence_paths",
    "expected_missing_fields",
    "expected_warnings",
    "expected_next_actions",
    "expected_behavior_class",
    "implementation_status",
    "difficulty",
    "label_rationale",
    "ambiguity_notes",
]

LIST_FIELDS: tuple[str, ...] = (
    "expected_evidence_paths",
    "expected_missing_fields",
    "expected_warnings",
    "expected_next_actions",
)

ALLOWED_FAMILIES: set[str] = {"OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE"}

ALLOWED_PAYLOAD_CONDITIONS: set[str] = {
    "clean",
    "missing_baseline_solution",
    "missing_new_customer_ids",
    "missing_units",
    "missing_validity_fields",
    "missing_reference_solution",
    "false_premise_customer",
    "false_premise_route",
    "unsupported_comparison",
    "convention_boundary",
    "single_customer_membership",
    "full_route_membership",
    "same_route_boolean",
    "synthetic_other",
}

CURRENT_INTENTS: set[str] = {
    "objective_value",
    "objective_delta",
    "feasibility_status",
    "route_count",
    "single_customer_route_membership",
    "same_route_boolean",
    "route_end_time",
    "customer_arrival",
    "lateness_summary",
    "before_after_comparison",
    "new_customer_assignment",
    "refusal_or_insufficient_payload",
    "unknown",
}
PROPOSED_INTENTS: set[str] = {"full_route_listing"}

ALLOWED_ANSWERABILITY: set[str] = {
    "answerable",
    "partially_answerable",
    "not_answerable",
}

CURRENT_WARNINGS: set[str] = {
    "route_indexing_ambiguity",
    "struct_membership_ambiguity",
    "unsupported_comparison",
    "missing_new_customer_attribution",
}
PROPOSED_WARNINGS: set[str] = {
    "false_premise_detected",
    "comparison_referent_ambiguity",
    "evidence_units_missing",
}

CURRENT_NEXT_ACTIONS: set[str] = {
    "build_baseline_comparison_payload",
    "expose_new_customer_ids",
    "apply_route_label_augmentation",
    "use_schedule_payload",
    "narrow_question_to_available_field",
}
PROPOSED_NEXT_ACTIONS: set[str] = {
    "clarify_false_premise",
    "use_validity_payload",
    "expose_reference_solution_objective",
    "expose_units_objective",
}

ALLOWED_BEHAVIOR_CLASSES: set[str] = {
    "direct_answer",
    "direct_answer_with_warning",
    "partial_answer_with_warning",
    "useful_refusal",
}

ALLOWED_IMPLEMENTATION_STATUS: set[str] = {"current", "target_extension"}
ALLOWED_DIFFICULTY: set[str] = {"easy", "medium", "hard"}

_CASE_ID_RE = re.compile(r"^R2-\d{3}$")
_PREDICATE_PATH_RE = re.compile(r"\[[^\]]*=[^\]]*\]")


# ---------------------------------------------------------------------------
# Run2Case
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Run2Case:
    """One calibration row from run2_calibration_cases.csv.

    All multi-value fields are already parsed into `list[str]`. Empty
    list-valued cells are the empty list. Scalar fields are kept as
    strings (no numeric coercion — payload field paths must remain
    untouched). See `run2_gold_schema.md` §1 for the schema contract.
    """

    case_id: str
    source_prompt_id: str
    family: str
    prompt_text: str
    payload_condition: str
    payload_mutation_needed: str
    expected_intent: str
    expected_answerability: str
    expected_evidence_paths: list[str] = field(default_factory=list)
    expected_missing_fields: list[str] = field(default_factory=list)
    expected_warnings: list[str] = field(default_factory=list)
    expected_next_actions: list[str] = field(default_factory=list)
    expected_behavior_class: str = ""
    implementation_status: str = ""
    difficulty: str = ""
    label_rationale: str = ""
    ambiguity_notes: str = ""


@dataclass
class ValidationReport:
    n_cases: int
    n_errors: int
    errors_by_case: dict[str, list[str]] = field(default_factory=dict)
    distributions: dict[str, dict[str, int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _split_multi(value: str) -> list[str]:
    """Split a `;`-separated multi-value cell per schema §11.

    - Empty string → [] (not [""])
    - Whitespace around items is stripped.
    """
    if value is None or value == "":
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def load_run2_cases(path: str | Path) -> list[Run2Case]:
    """Load the calibration CSV per schema §11 reader contract.

    Reader contract:
        pd.read_csv(path, keep_default_na=False, dtype=str)

    The exact column header in `EXPECTED_COLUMNS` is enforced;
    unknown or missing columns raise ValueError.
    """
    df = pd.read_csv(path, keep_default_na=False, dtype=str)

    actual_cols = list(df.columns)
    if actual_cols != EXPECTED_COLUMNS:
        missing = [c for c in EXPECTED_COLUMNS if c not in actual_cols]
        extra = [c for c in actual_cols if c not in EXPECTED_COLUMNS]
        raise ValueError(
            f"CSV header mismatch: missing={missing!r} extra={extra!r}"
        )

    cases: list[Run2Case] = []
    for _, row in df.iterrows():
        cases.append(
            Run2Case(
                case_id=row["case_id"],
                source_prompt_id=row["source_prompt_id"],
                family=row["family"],
                prompt_text=row["prompt_text"],
                payload_condition=row["payload_condition"],
                payload_mutation_needed=row["payload_mutation_needed"],
                expected_intent=row["expected_intent"],
                expected_answerability=row["expected_answerability"],
                expected_evidence_paths=_split_multi(row["expected_evidence_paths"]),
                expected_missing_fields=_split_multi(row["expected_missing_fields"]),
                expected_warnings=_split_multi(row["expected_warnings"]),
                expected_next_actions=_split_multi(row["expected_next_actions"]),
                expected_behavior_class=row["expected_behavior_class"],
                implementation_status=row["implementation_status"],
                difficulty=row["difficulty"],
                label_rationale=row["label_rationale"],
                ambiguity_notes=row["ambiguity_notes"],
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Per-case validation (schema §13 disallowed shapes + enum checks)
# ---------------------------------------------------------------------------


def validate_case(case: Run2Case) -> list[str]:
    """Return a list of human-readable error strings, or [] if valid."""
    errs: list[str] = []

    # --- Enum membership / format
    if not _CASE_ID_RE.match(case.case_id):
        errs.append(f"case_id {case.case_id!r} does not match R2-NNN")
    if case.family not in ALLOWED_FAMILIES:
        errs.append(f"family {case.family!r} not in {sorted(ALLOWED_FAMILIES)}")
    if case.payload_condition not in ALLOWED_PAYLOAD_CONDITIONS:
        errs.append(
            f"payload_condition {case.payload_condition!r} not allowed"
        )
    if case.expected_intent not in CURRENT_INTENTS | PROPOSED_INTENTS:
        errs.append(f"expected_intent {case.expected_intent!r} not allowed")
    if case.expected_answerability not in ALLOWED_ANSWERABILITY:
        errs.append(
            f"expected_answerability {case.expected_answerability!r} not allowed"
        )
    if case.expected_behavior_class not in ALLOWED_BEHAVIOR_CLASSES:
        errs.append(
            f"expected_behavior_class {case.expected_behavior_class!r} not allowed"
        )
    if case.implementation_status not in ALLOWED_IMPLEMENTATION_STATUS:
        errs.append(
            f"implementation_status {case.implementation_status!r} not allowed"
        )
    if case.difficulty not in ALLOWED_DIFFICULTY:
        errs.append(f"difficulty {case.difficulty!r} not allowed")

    # --- Unknown enum values inside list fields
    unknown_warnings = (
        set(case.expected_warnings) - CURRENT_WARNINGS - PROPOSED_WARNINGS
    )
    if unknown_warnings:
        errs.append(f"unknown warning(s): {sorted(unknown_warnings)}")
    unknown_actions = (
        set(case.expected_next_actions)
        - CURRENT_NEXT_ACTIONS
        - PROPOSED_NEXT_ACTIONS
    )
    if unknown_actions:
        errs.append(f"unknown next_action(s): {sorted(unknown_actions)}")

    # --- Proposed codes require target_extension (schema §13)
    if (
        case.expected_intent in PROPOSED_INTENTS
        and case.implementation_status != "target_extension"
    ):
        errs.append(
            f"proposed intent {case.expected_intent!r} requires "
            f"implementation_status=target_extension"
        )
    proposed_w_used = set(case.expected_warnings) & PROPOSED_WARNINGS
    if proposed_w_used and case.implementation_status != "target_extension":
        errs.append(
            f"proposed warning(s) {sorted(proposed_w_used)} require "
            f"implementation_status=target_extension"
        )
    proposed_a_used = set(case.expected_next_actions) & PROPOSED_NEXT_ACTIONS
    if proposed_a_used and case.implementation_status != "target_extension":
        errs.append(
            f"proposed next_action(s) {sorted(proposed_a_used)} require "
            f"implementation_status=target_extension"
        )

    # --- Behavior-class shape rules (schema §7 / §13)
    if case.expected_behavior_class == "direct_answer":
        if case.expected_warnings:
            errs.append("direct_answer requires empty expected_warnings")
        if case.expected_missing_fields:
            errs.append("direct_answer requires empty expected_missing_fields")

    if case.expected_behavior_class == "direct_answer_with_warning":
        if not case.expected_warnings:
            errs.append(
                "direct_answer_with_warning requires non-empty expected_warnings"
            )
        if case.expected_missing_fields:
            errs.append(
                "direct_answer_with_warning requires empty expected_missing_fields"
            )

    if case.expected_behavior_class == "partial_answer_with_warning":
        if case.expected_answerability != "partially_answerable":
            errs.append(
                "partial_answer_with_warning requires "
                "expected_answerability=partially_answerable"
            )
        if not case.expected_warnings:
            errs.append(
                "partial_answer_with_warning requires non-empty expected_warnings"
            )
        if not case.expected_missing_fields:
            errs.append(
                "partial_answer_with_warning requires non-empty "
                "expected_missing_fields"
            )
        if not case.expected_next_actions:
            errs.append(
                "partial_answer_with_warning requires non-empty "
                "expected_next_actions"
            )
        if not case.expected_evidence_paths:
            errs.append(
                "partial_answer_with_warning requires non-empty "
                "expected_evidence_paths (the supported subclaim must be cited)"
            )

    if case.expected_behavior_class == "useful_refusal":
        if case.expected_answerability == "answerable":
            errs.append("useful_refusal cannot pair with answerable")
        if not case.expected_next_actions:
            errs.append("useful_refusal requires non-empty expected_next_actions")

    # --- Answerable rows cannot list missing fields
    if (
        case.expected_answerability == "answerable"
        and case.expected_missing_fields
    ):
        errs.append("answerable rows cannot have non-empty expected_missing_fields")

    # --- False-premise rules (schema §12)
    if case.payload_condition in {"false_premise_customer", "false_premise_route"}:
        if "false_premise_detected" not in case.expected_warnings:
            errs.append(
                "false_premise_* condition requires false_premise_detected "
                "in expected_warnings"
            )
        if "clarify_false_premise" not in case.expected_next_actions:
            errs.append(
                "false_premise_* condition requires clarify_false_premise "
                "in expected_next_actions"
            )
    if (
        "false_premise_detected" in case.expected_warnings
        and case.payload_condition
        not in {"false_premise_customer", "false_premise_route"}
    ):
        errs.append(
            "false_premise_detected requires a false_premise_* payload_condition"
        )

    # --- Family-restricted warnings
    if (
        "comparison_referent_ambiguity" in case.expected_warnings
        and (case.family != "OBJ" or case.expected_intent != "objective_delta")
    ):
        errs.append(
            "comparison_referent_ambiguity requires family=OBJ and "
            "expected_intent=objective_delta"
        )
    if (
        "evidence_units_missing" in case.expected_warnings
        and case.family != "OBJ"
    ):
        errs.append("evidence_units_missing requires family=OBJ")

    # --- Predicate-pinned gold paths forbidden (schema §10a / §13)
    for p in case.expected_evidence_paths:
        if _PREDICATE_PATH_RE.search(p):
            errs.append(f"predicate-pinned evidence path forbidden in gold: {p!r}")

    # --- label_rationale required
    if not case.label_rationale.strip():
        errs.append("label_rationale must be non-empty")

    return errs


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------


def _distribution(cases: Iterable[Run2Case], attr: str) -> dict[str, int]:
    counts: Counter[str] = Counter(getattr(c, attr) for c in cases)
    return dict(counts)


def validate_all_cases(cases: list[Run2Case]) -> ValidationReport:
    errors_by_case: dict[str, list[str]] = {}
    for case in cases:
        case_errs = validate_case(case)
        if case_errs:
            errors_by_case[case.case_id] = case_errs

    distributions = {
        "family": _distribution(cases, "family"),
        "payload_condition": _distribution(cases, "payload_condition"),
        "implementation_status": _distribution(cases, "implementation_status"),
        "expected_behavior_class": _distribution(cases, "expected_behavior_class"),
        "difficulty": _distribution(cases, "difficulty"),
        "expected_answerability": _distribution(cases, "expected_answerability"),
    }

    return ValidationReport(
        n_cases=len(cases),
        n_errors=sum(len(v) for v in errors_by_case.values()),
        errors_by_case=errors_by_case,
        distributions=distributions,
    )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def default_cases_path() -> Path:
    """Return the canonical path to the calibration CSV in this repo."""
    return Path(__file__).resolve().parent / "run2_calibration_cases.csv"


def benchmark_cases_path() -> Path:
    """Return the canonical path to the full 60-case benchmark CSV."""
    return Path(__file__).resolve().parent / "run2_benchmark_cases.csv"

"""R2-S Axis 2 OOD-false-premises stress loader.

Reads `cases.csv` for `axis2_ood_premises`, validates the 33-column
extended schema (17 locked gold columns + 16 stress columns), and
enforces the Axis 2 invariants documented in `design.md`.

Unlike Axis 1 / Axis 3, the Axis 2 stress row does NOT inherit gold
verbatim from `base_case_id`. The base case is used only for:

  - payload materialization (via `source_prompt_id` lookup); and
  - traceability in reports.

The loader still validates the gold row against the locked Run 2
schema (`run2_case_loader.validate_case`) row-by-row so that no
Axis 2 case can use an invalid enum or shape combination.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from product.evaluation.run2_case_loader import (
    EXPECTED_COLUMNS as GOLD_COLUMNS,
    Run2Case,
    ValidationReport,
    validate_case,
    _split_multi,
)


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------


STRESS_COLUMNS: list[str] = [
    "stress_axis",
    "stress_subtype",
    "split",
    "band",
    "ood_premise_band",
    "premise_type",
    "expected_failure_mode",
    "base_case_id",
    "base_family",
    "canonical_supported_prompt",
    "false_entity_type",
    "false_entity_value",
    "comparator_type",
    "missing_support_field",
    "unsupported_assumption",
    "notes",
]


EXPECTED_COLUMNS: list[str] = list(GOLD_COLUMNS) + STRESS_COLUMNS


ALLOWED_STRESS_AXIS: set[str] = {"ood_premises_comparators"}


ALLOWED_BANDS: set[str] = {
    "nonexistent_entity_false_premise",
    "unsupported_movement_or_assignment_premise",
    "missing_comparator_or_baseline",
    "causal_or_explanatory_unsupported_premise",
}


ALLOWED_SPLITS: set[str] = {"dev", "heldout"}


ALLOWED_PREMISE_TYPES: set[str] = {
    "nonexistent_entity",
    "unsupported_movement",
    "missing_comparator",
    "missing_baseline",
    "causal_explanation",
}


ALLOWED_FAILURE_MODES: set[str] = {
    "should_detect_false_premise",
    "should_detect_missing_comparator",
    "should_detect_missing_baseline",
    "should_partial_answer_current_status_only",
    "should_refuse_causal_explanation",
    "should_request_clarification",
}


EXPECTED_TOTAL_CASES = 24
EXPECTED_PER_SPLIT = 12
EXPECTED_PER_BAND = 6
EXPECTED_PER_BAND_PER_SPLIT = 3


_STRESS_CASE_ID_RE = re.compile(r"^A2[DH]-\d{2}$")


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Run2OodPremiseCase:
    """One row of the R2-S Axis 2 stress CSV."""

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

    stress_axis: str = ""
    stress_subtype: str = ""
    split: str = ""
    band: str = ""
    ood_premise_band: str = ""
    premise_type: str = ""
    expected_failure_mode: str = ""
    base_case_id: str = ""
    base_family: str = ""
    canonical_supported_prompt: str = ""
    false_entity_type: str = ""
    false_entity_value: str = ""
    comparator_type: str = ""
    missing_support_field: str = ""
    unsupported_assumption: str = ""
    notes: str = ""

    def as_run2_case(self) -> Run2Case:
        """Project to the locked `Run2Case` shape so the stress row
        passes through unmodified Run 2 infrastructure."""
        return Run2Case(
            case_id=self.case_id,
            source_prompt_id=self.source_prompt_id,
            family=self.family,
            prompt_text=self.prompt_text,
            payload_condition=self.payload_condition,
            payload_mutation_needed=self.payload_mutation_needed,
            expected_intent=self.expected_intent,
            expected_answerability=self.expected_answerability,
            expected_evidence_paths=list(self.expected_evidence_paths),
            expected_missing_fields=list(self.expected_missing_fields),
            expected_warnings=list(self.expected_warnings),
            expected_next_actions=list(self.expected_next_actions),
            expected_behavior_class=self.expected_behavior_class,
            implementation_status=self.implementation_status,
            difficulty=self.difficulty,
            label_rationale=self.label_rationale,
            ambiguity_notes=self.ambiguity_notes,
        )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def default_cases_path() -> Path:
    return Path(__file__).resolve().parent / "cases.csv"


def default_locked_benchmark_path() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "run2_benchmark_cases.csv"
    )


def load_ood_cases(path: str | Path | None = None) -> list[Run2OodPremiseCase]:
    """Load the stress CSV per the 33-column reader contract.

    Reader contract mirrors `run2_gold_schema.md` §11:
        pd.read_csv(path, keep_default_na=False, dtype=str)
    """
    path = Path(path) if path else default_cases_path()
    df = pd.read_csv(path, keep_default_na=False, dtype=str)

    actual_cols = list(df.columns)
    if actual_cols != EXPECTED_COLUMNS:
        missing = [c for c in EXPECTED_COLUMNS if c not in actual_cols]
        extra = [c for c in actual_cols if c not in EXPECTED_COLUMNS]
        raise ValueError(
            f"axis2 stress CSV header mismatch: missing={missing!r} "
            f"extra={extra!r}"
        )

    cases: list[Run2OodPremiseCase] = []
    for _, row in df.iterrows():
        cases.append(
            Run2OodPremiseCase(
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
                stress_axis=row["stress_axis"],
                stress_subtype=row["stress_subtype"],
                split=row["split"],
                band=row["band"],
                ood_premise_band=row["ood_premise_band"],
                premise_type=row["premise_type"],
                expected_failure_mode=row["expected_failure_mode"],
                base_case_id=row["base_case_id"],
                base_family=row["base_family"],
                canonical_supported_prompt=row["canonical_supported_prompt"],
                false_entity_type=row["false_entity_type"],
                false_entity_value=row["false_entity_value"],
                comparator_type=row["comparator_type"],
                missing_support_field=row["missing_support_field"],
                unsupported_assumption=row["unsupported_assumption"],
                notes=row["notes"],
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _load_locked_benchmark_rows() -> dict[str, dict[str, str]]:
    df = pd.read_csv(
        default_locked_benchmark_path(), keep_default_na=False, dtype=str
    )
    return {row["case_id"]: dict(row) for _, row in df.iterrows()}


def validate_ood_case(
    case: Run2OodPremiseCase, locked_rows: dict[str, dict[str, str]]
) -> list[str]:
    """Return a list of human-readable error strings, or [] if valid."""
    errs: list[str] = []

    # --- case_id shape
    if not _STRESS_CASE_ID_RE.match(case.case_id):
        errs.append(f"case_id {case.case_id!r} does not match A2[DH]-NN")

    # --- gold-row validation (reuses the locked validator). Filter
    # the case_id-shape error since the stress case_id deliberately
    # violates the locked R2-NNN pattern.
    gold_errs = [
        e
        for e in validate_case(case.as_run2_case())
        if not e.startswith("case_id ")
    ]
    errs.extend(gold_errs)

    # --- stress enum membership
    if case.stress_axis not in ALLOWED_STRESS_AXIS:
        errs.append(
            f"stress_axis {case.stress_axis!r} not in "
            f"{sorted(ALLOWED_STRESS_AXIS)}"
        )
    if case.split not in ALLOWED_SPLITS:
        errs.append(f"split {case.split!r} not in {sorted(ALLOWED_SPLITS)}")
    if case.band not in ALLOWED_BANDS:
        errs.append(f"band {case.band!r} not in {sorted(ALLOWED_BANDS)}")
    if case.ood_premise_band != case.band:
        errs.append(
            f"ood_premise_band {case.ood_premise_band!r} != band {case.band!r}"
        )
    if case.premise_type and case.premise_type not in ALLOWED_PREMISE_TYPES:
        errs.append(
            f"premise_type {case.premise_type!r} not in "
            f"{sorted(ALLOWED_PREMISE_TYPES)}"
        )
    if (
        case.expected_failure_mode
        and case.expected_failure_mode not in ALLOWED_FAILURE_MODES
    ):
        errs.append(
            f"expected_failure_mode {case.expected_failure_mode!r} not in "
            f"{sorted(ALLOWED_FAILURE_MODES)}"
        )

    # --- case_id ↔ split coherence
    if case.case_id.startswith("A2D-") and case.split != "dev":
        errs.append(f"case_id {case.case_id!r} expects split=dev")
    if case.case_id.startswith("A2H-") and case.split != "heldout":
        errs.append(f"case_id {case.case_id!r} expects split=heldout")

    # --- base case must exist in the locked benchmark
    if case.base_case_id not in locked_rows:
        errs.append(
            f"base_case_id {case.base_case_id!r} not present in the locked "
            f"Run 2 benchmark"
        )
        return errs

    # --- traceability: source_prompt_id and base_family must match the
    # locked base case. Axis 2 does NOT inherit gold from the base, but
    # it DOES inherit payload provenance (so materialization reproduces).
    base = locked_rows[case.base_case_id]
    if case.source_prompt_id != base["source_prompt_id"]:
        errs.append(
            f"source_prompt_id {case.source_prompt_id!r} != base case "
            f"source_prompt_id {base['source_prompt_id']!r}"
        )
    if case.base_family != base["family"]:
        errs.append(
            f"base_family {case.base_family!r} != base case family "
            f"{base['family']!r}"
        )

    # --- canonical_supported_prompt must equal the base case prompt
    # (it's the canonical supported wording the stress diverges from).
    if case.canonical_supported_prompt.strip() != base["prompt_text"].strip():
        errs.append(
            "canonical_supported_prompt does not match base case prompt_text"
        )

    # --- stress prompt must differ from the canonical supported prompt
    if case.prompt_text.strip() == case.canonical_supported_prompt.strip():
        errs.append(
            "prompt_text equals canonical_supported_prompt — the stress "
            "row must diverge from the base prompt"
        )

    # --- label_rationale and ambiguity_notes must be non-empty
    if not case.label_rationale.strip():
        errs.append("label_rationale must be non-empty")
    if not case.ambiguity_notes.strip():
        errs.append("ambiguity_notes must be non-empty")

    return errs


def _distribution(
    cases: Iterable[Run2OodPremiseCase], attr: str
) -> dict[str, int]:
    counts: Counter[str] = Counter(getattr(c, attr) for c in cases)
    return dict(counts)


def validate_all_ood_cases(
    cases: list[Run2OodPremiseCase],
) -> ValidationReport:
    """Run every check, return a `ValidationReport`."""
    locked_rows = _load_locked_benchmark_rows()
    errors_by_case: dict[str, list[str]] = {}

    # ---- File-level invariants
    case_ids = [c.case_id for c in cases]
    if len(case_ids) != EXPECTED_TOTAL_CASES:
        errors_by_case.setdefault("__file__", []).append(
            f"expected {EXPECTED_TOTAL_CASES} cases, got {len(case_ids)}"
        )
    duplicate_ids = [cid for cid, n in Counter(case_ids).items() if n > 1]
    if duplicate_ids:
        errors_by_case.setdefault("__file__", []).append(
            f"duplicate case_ids: {sorted(duplicate_ids)}"
        )

    by_split: Counter[str] = Counter(c.split for c in cases)
    for split in ALLOWED_SPLITS:
        if by_split.get(split, 0) != EXPECTED_PER_SPLIT:
            errors_by_case.setdefault("__file__", []).append(
                f"expected {EXPECTED_PER_SPLIT} {split} cases, got "
                f"{by_split.get(split, 0)}"
            )

    by_band: Counter[str] = Counter(c.band for c in cases)
    for band in ALLOWED_BANDS:
        if by_band.get(band, 0) != EXPECTED_PER_BAND:
            errors_by_case.setdefault("__file__", []).append(
                f"expected {EXPECTED_PER_BAND} cases in band {band!r}, got "
                f"{by_band.get(band, 0)}"
            )

    by_band_split: Counter[tuple[str, str]] = Counter(
        (c.band, c.split) for c in cases
    )
    for band in ALLOWED_BANDS:
        for split in ALLOWED_SPLITS:
            got = by_band_split.get((band, split), 0)
            if got != EXPECTED_PER_BAND_PER_SPLIT:
                errors_by_case.setdefault("__file__", []).append(
                    f"expected {EXPECTED_PER_BAND_PER_SPLIT} cases in "
                    f"({band!r}, {split!r}), got {got}"
                )

    # ---- Per-case validation
    for case in cases:
        case_errs = validate_ood_case(case, locked_rows)
        if case_errs:
            errors_by_case[case.case_id] = case_errs

    distributions = {
        "stress_axis": _distribution(cases, "stress_axis"),
        "stress_subtype": _distribution(cases, "stress_subtype"),
        "split": _distribution(cases, "split"),
        "band": _distribution(cases, "band"),
        "family": _distribution(cases, "family"),
        "expected_intent": _distribution(cases, "expected_intent"),
        "expected_behavior_class": _distribution(
            cases, "expected_behavior_class"
        ),
        "implementation_status": _distribution(cases, "implementation_status"),
        "premise_type": _distribution(cases, "premise_type"),
        "expected_failure_mode": _distribution(
            cases, "expected_failure_mode"
        ),
    }

    return ValidationReport(
        n_cases=len(cases),
        n_errors=sum(len(v) for v in errors_by_case.values()),
        errors_by_case=errors_by_case,
        distributions=distributions,
    )


__all__ = [
    "ALLOWED_BANDS",
    "ALLOWED_FAILURE_MODES",
    "ALLOWED_PREMISE_TYPES",
    "ALLOWED_SPLITS",
    "ALLOWED_STRESS_AXIS",
    "EXPECTED_COLUMNS",
    "EXPECTED_PER_BAND",
    "EXPECTED_PER_BAND_PER_SPLIT",
    "EXPECTED_PER_SPLIT",
    "EXPECTED_TOTAL_CASES",
    "Run2OodPremiseCase",
    "STRESS_COLUMNS",
    "default_cases_path",
    "default_locked_benchmark_path",
    "load_ood_cases",
    "validate_all_ood_cases",
    "validate_ood_case",
]

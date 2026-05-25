"""R2-S1 semantic-intent stress loader.

Reads `cases.csv` for axis3_semantic, validates the 26-column extended
schema (17 locked gold columns + 9 stress columns), and asserts that
every stress row inherits its base case's gold contract response
verbatim. No model calls; no I/O beyond CSV reading.

The locked Run 2 enums and gold-row validator are imported from
`product.evaluation.run2_case_loader` — the stress split is defined to
*inherit* rather than redefine the gold schema.
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
    load_run2_cases,
    validate_case,
    _split_multi,
)


# ---------------------------------------------------------------------------
# Stress schema constants
# ---------------------------------------------------------------------------


STRESS_COLUMNS: list[str] = [
    "stress_axis",
    "stress_subtype",
    "split",
    "base_case_id",
    "base_family",
    "canonical_prompt",
    "paraphrase_notes",
    "forbidden_keywords_removed",
    "notes",
]

EXPECTED_COLUMNS: list[str] = list(GOLD_COLUMNS) + STRESS_COLUMNS

ALLOWED_STRESS_AXIS: set[str] = {"semantic_intent"}
ALLOWED_STRESS_SUBTYPES: set[str] = {
    "paraphrase",
    "synonym",
    "operator_colloquial",
    "entity_synonym",
    "schedule_synonym",
    "cost_synonym",
    "feasibility_synonym",
}
ALLOWED_SPLITS: set[str] = {"dev", "heldout"}

EXPECTED_TOTAL_CASES = 24
EXPECTED_PER_SPLIT = 12

_STRESS_CASE_ID_RE = re.compile(r"^S1[DH]-\d{2}$")

LIST_FIELDS_STRESS: tuple[str, ...] = ("forbidden_keywords_removed",)

# Inheritance contract — these 9 columns of the stress row must equal
# the named base case's row, character-for-character. The stress row
# may **only** change `prompt_text`, `difficulty` (cap from `hard` to
# `medium`), `label_rationale`, `ambiguity_notes`, and `case_id` —
# plus the 9 appended stress columns.
INHERITED_COLUMNS: tuple[str, ...] = (
    "source_prompt_id",
    "family",
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
)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Run2StressCase:
    """One row of the R2-S1 stress CSV.

    The first 17 fields mirror `Run2Case` (gold contract row); the last
    9 fields are stress metadata.
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
    stress_axis: str = ""
    stress_subtype: str = ""
    split: str = ""
    base_case_id: str = ""
    base_family: str = ""
    canonical_prompt: str = ""
    paraphrase_notes: str = ""
    forbidden_keywords_removed: list[str] = field(default_factory=list)
    notes: str = ""

    def as_run2_case(self) -> Run2Case:
        """Project to the locked `Run2Case` shape (17 gold columns) so
        the stress row can be passed through unmodified Run 2
        infrastructure (`run2_payloads`, `run2_system_c`,
        `run2_scoring`)."""
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


def load_stress_cases(path: str | Path | None = None) -> list[Run2StressCase]:
    """Load the stress CSV per the 26-column reader contract.

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
            f"stress CSV header mismatch: missing={missing!r} extra={extra!r}"
        )

    cases: list[Run2StressCase] = []
    for _, row in df.iterrows():
        cases.append(
            Run2StressCase(
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
                base_case_id=row["base_case_id"],
                base_family=row["base_family"],
                canonical_prompt=row["canonical_prompt"],
                paraphrase_notes=row["paraphrase_notes"],
                forbidden_keywords_removed=_split_multi(
                    row["forbidden_keywords_removed"]
                ),
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
    out: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        out[row["case_id"]] = dict(row)
    return out


def _inheritance_errors(
    case: Run2StressCase, base_row: dict[str, str]
) -> list[str]:
    """Verify the stress row inherits the base case's gold contract
    response verbatim on the columns in `INHERITED_COLUMNS`."""
    errs: list[str] = []
    base_run2 = {
        "source_prompt_id": base_row["source_prompt_id"],
        "family": base_row["family"],
        "payload_condition": base_row["payload_condition"],
        "payload_mutation_needed": base_row["payload_mutation_needed"],
        "expected_intent": base_row["expected_intent"],
        "expected_answerability": base_row["expected_answerability"],
        "expected_evidence_paths": base_row["expected_evidence_paths"],
        "expected_missing_fields": base_row["expected_missing_fields"],
        "expected_warnings": base_row["expected_warnings"],
        "expected_next_actions": base_row["expected_next_actions"],
        "expected_behavior_class": base_row["expected_behavior_class"],
        "implementation_status": base_row["implementation_status"],
    }
    stress_run2 = {
        "source_prompt_id": case.source_prompt_id,
        "family": case.family,
        "payload_condition": case.payload_condition,
        "payload_mutation_needed": case.payload_mutation_needed,
        "expected_intent": case.expected_intent,
        "expected_answerability": case.expected_answerability,
        "expected_evidence_paths": ";".join(case.expected_evidence_paths),
        "expected_missing_fields": ";".join(case.expected_missing_fields),
        "expected_warnings": ";".join(case.expected_warnings),
        "expected_next_actions": ";".join(case.expected_next_actions),
        "expected_behavior_class": case.expected_behavior_class,
        "implementation_status": case.implementation_status,
    }
    for col in INHERITED_COLUMNS:
        if base_run2[col] != stress_run2[col]:
            errs.append(
                f"inheritance violated on column {col!r}: "
                f"base={base_run2[col]!r} stress={stress_run2[col]!r}"
            )
    if case.base_family != base_row["family"]:
        errs.append(
            f"base_family {case.base_family!r} != base case family "
            f"{base_row['family']!r}"
        )
    if case.canonical_prompt != base_row["prompt_text"]:
        errs.append(
            "canonical_prompt does not match base case prompt_text "
            f"(base case {case.base_case_id})"
        )
    return errs


def validate_stress_case(
    case: Run2StressCase, locked_rows: dict[str, dict[str, str]]
) -> list[str]:
    """Return a list of human-readable error strings, or [] if valid."""
    errs: list[str] = []

    # --- case_id shape
    if not _STRESS_CASE_ID_RE.match(case.case_id):
        errs.append(f"case_id {case.case_id!r} does not match S1[DH]-NN")

    # --- gold-row validation (reuses the locked validator).
    # The locked validator enforces case_id == R2-NNN, which the stress
    # case_id `S1[DH]-NN` deliberately violates — filter that one error
    # out and rely on _STRESS_CASE_ID_RE above for the stress shape.
    gold_errs = [
        e
        for e in validate_case(case.as_run2_case())
        if not e.startswith("case_id ")
    ]
    errs.extend(gold_errs)

    # --- stress enum membership
    if case.stress_axis not in ALLOWED_STRESS_AXIS:
        errs.append(
            f"stress_axis {case.stress_axis!r} not in {sorted(ALLOWED_STRESS_AXIS)}"
        )
    if case.stress_subtype not in ALLOWED_STRESS_SUBTYPES:
        errs.append(
            f"stress_subtype {case.stress_subtype!r} not in "
            f"{sorted(ALLOWED_STRESS_SUBTYPES)}"
        )
    if case.split not in ALLOWED_SPLITS:
        errs.append(f"split {case.split!r} not in {sorted(ALLOWED_SPLITS)}")

    # --- case_id ↔ split coherence
    if case.case_id.startswith("S1D-") and case.split != "dev":
        errs.append(f"case_id {case.case_id!r} expects split=dev")
    if case.case_id.startswith("S1H-") and case.split != "heldout":
        errs.append(f"case_id {case.case_id!r} expects split=heldout")

    # --- base case must exist in the locked benchmark
    if case.base_case_id not in locked_rows:
        errs.append(
            f"base_case_id {case.base_case_id!r} not present in the locked "
            f"Run 2 benchmark"
        )
        return errs

    # --- inheritance check
    errs.extend(_inheritance_errors(case, locked_rows[case.base_case_id]))

    if not case.paraphrase_notes.strip():
        errs.append("paraphrase_notes must be non-empty")
    if not case.ambiguity_notes.strip():
        errs.append("ambiguity_notes must be non-empty (records expected C0 behavior)")

    if case.prompt_text.strip() == case.canonical_prompt.strip():
        errs.append(
            "prompt_text equals canonical_prompt — the stress row must "
            "paraphrase the base case prompt"
        )

    return errs


def _distribution(cases: Iterable[Run2StressCase], attr: str) -> dict[str, int]:
    counts: Counter[str] = Counter(getattr(c, attr) for c in cases)
    return dict(counts)


def validate_all_stress_cases(cases: list[Run2StressCase]) -> ValidationReport:
    locked_rows = _load_locked_benchmark_rows()
    errors_by_case: dict[str, list[str]] = {}

    # ---- File-level invariants
    case_ids = [c.case_id for c in cases]
    if len(case_ids) != EXPECTED_TOTAL_CASES:
        errors_by_case.setdefault("__file__", []).append(
            f"expected {EXPECTED_TOTAL_CASES} cases, got {len(case_ids)}"
        )
    duplicate_ids = [
        cid for cid, n in Counter(case_ids).items() if n > 1
    ]
    if duplicate_ids:
        errors_by_case.setdefault("__file__", []).append(
            f"duplicate case_ids: {sorted(duplicate_ids)}"
        )

    by_split: Counter[str] = Counter(c.split for c in cases)
    if by_split.get("dev", 0) != EXPECTED_PER_SPLIT:
        errors_by_case.setdefault("__file__", []).append(
            f"expected {EXPECTED_PER_SPLIT} dev cases, got {by_split.get('dev', 0)}"
        )
    if by_split.get("heldout", 0) != EXPECTED_PER_SPLIT:
        errors_by_case.setdefault("__file__", []).append(
            f"expected {EXPECTED_PER_SPLIT} heldout cases, got "
            f"{by_split.get('heldout', 0)}"
        )

    # ---- Per-case validation
    for case in cases:
        case_errs = validate_stress_case(case, locked_rows)
        if case_errs:
            errors_by_case[case.case_id] = case_errs

    distributions = {
        "stress_axis": _distribution(cases, "stress_axis"),
        "stress_subtype": _distribution(cases, "stress_subtype"),
        "split": _distribution(cases, "split"),
        "family": _distribution(cases, "family"),
        "expected_intent": _distribution(cases, "expected_intent"),
        "implementation_status": _distribution(cases, "implementation_status"),
        "expected_behavior_class": _distribution(cases, "expected_behavior_class"),
    }

    return ValidationReport(
        n_cases=len(cases),
        n_errors=sum(len(v) for v in errors_by_case.values()),
        errors_by_case=errors_by_case,
        distributions=distributions,
    )


__all__ = [
    "ALLOWED_SPLITS",
    "ALLOWED_STRESS_AXIS",
    "ALLOWED_STRESS_SUBTYPES",
    "EXPECTED_COLUMNS",
    "EXPECTED_PER_SPLIT",
    "EXPECTED_TOTAL_CASES",
    "INHERITED_COLUMNS",
    "Run2StressCase",
    "STRESS_COLUMNS",
    "default_cases_path",
    "default_locked_benchmark_path",
    "load_stress_cases",
    "validate_all_stress_cases",
    "validate_stress_case",
]

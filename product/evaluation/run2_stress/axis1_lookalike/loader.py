"""R2-S Axis 1 look-alike-intent stress loader.

Reads `cases.csv` for `axis1_lookalike`, validates the 30-column
extended schema (17 locked gold columns + 13 stress columns), and
enforces that every stress row inherits its base case's gold
contract response verbatim. No model calls; no I/O beyond CSV
reading.

The locked Run 2 enums and gold-row validator are imported from
`product.evaluation.run2_case_loader` — the stress split is defined
to *inherit* rather than redefine the gold schema.
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
    CURRENT_INTENTS,
    PROPOSED_INTENTS,
    Run2Case,
    ValidationReport,
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
    "band",
    "confusion_pair",
    "gold_intent",
    "attractor_intent",
    "attractor_tokens",
    "base_case_id",
    "base_family",
    "canonical_prompt",
    "paraphrase_notes",
    "notes",
]

EXPECTED_COLUMNS: list[str] = list(GOLD_COLUMNS) + STRESS_COLUMNS

ALLOWED_STRESS_AXIS: set[str] = {"lookalike_intent"}

ALLOWED_STRESS_SUBTYPES: set[str] = {
    "membership_lookalike",
    "feasibility_lookalike",
    "route_end_lookalike",
    "comparative_lookalike",
}

ALLOWED_BANDS: set[str] = {
    "membership_vs_new_customer_assignment",
    "lateness_vs_feasibility_status",
    "route_listing_vs_route_end_time",
    "comparison_vs_status_or_objective",
}

ALLOWED_SPLITS: set[str] = {"dev", "heldout"}

ALLOWED_ATTRACTOR_INTENTS: set[str] = CURRENT_INTENTS | PROPOSED_INTENTS

EXPECTED_TOTAL_CASES = 24
EXPECTED_PER_SPLIT = 12
EXPECTED_PER_BAND = 6
EXPECTED_PER_BAND_PER_SPLIT = 3

_STRESS_CASE_ID_RE = re.compile(r"^A1[DH]-\d{2}$")

# Columns the stress row inherits verbatim from the named base case
# (string-for-string equality, including the `;`-joined list cells).
# The stress row may diverge only on `case_id`, `prompt_text`,
# `difficulty` (cap from `hard` to `medium`), `label_rationale`,
# `ambiguity_notes`, plus the 13 appended stress columns.
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
class Run2LookalikeCase:
    """One row of the R2-S Axis 1 stress CSV.

    The first 17 fields mirror `Run2Case` (gold contract row); the
    last 13 fields are stress metadata.
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
    band: str = ""
    confusion_pair: str = ""
    gold_intent: str = ""
    attractor_intent: str = ""
    attractor_tokens: str = ""
    base_case_id: str = ""
    base_family: str = ""
    canonical_prompt: str = ""
    paraphrase_notes: str = ""
    notes: str = ""

    def as_run2_case(self) -> Run2Case:
        """Project to the locked `Run2Case` shape so the stress row
        passes through unmodified Run 2 infrastructure (`run2_payloads`,
        `run2_system_c`, `run2_scoring`)."""
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


def load_lookalike_cases(path: str | Path | None = None) -> list[Run2LookalikeCase]:
    """Load the stress CSV per the 30-column reader contract.

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
            f"axis1 stress CSV header mismatch: missing={missing!r} "
            f"extra={extra!r}"
        )

    cases: list[Run2LookalikeCase] = []
    for _, row in df.iterrows():
        cases.append(
            Run2LookalikeCase(
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
                confusion_pair=row["confusion_pair"],
                gold_intent=row["gold_intent"],
                attractor_intent=row["attractor_intent"],
                attractor_tokens=row["attractor_tokens"],
                base_case_id=row["base_case_id"],
                base_family=row["base_family"],
                canonical_prompt=row["canonical_prompt"],
                paraphrase_notes=row["paraphrase_notes"],
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


def _inheritance_errors(
    case: Run2LookalikeCase, base_row: dict[str, str]
) -> list[str]:
    """Verify the stress row inherits the base case's gold contract
    response verbatim on the columns in `INHERITED_COLUMNS`."""
    errs: list[str] = []
    stress_serialized = {
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
        if base_row[col] != stress_serialized[col]:
            errs.append(
                f"inheritance violated on column {col!r}: "
                f"base={base_row[col]!r} stress={stress_serialized[col]!r}"
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
    if case.gold_intent != base_row["expected_intent"]:
        errs.append(
            f"gold_intent {case.gold_intent!r} != base expected_intent "
            f"{base_row['expected_intent']!r}"
        )
    return errs


def validate_lookalike_case(
    case: Run2LookalikeCase, locked_rows: dict[str, dict[str, str]]
) -> list[str]:
    """Return a list of human-readable error strings, or [] if valid."""
    errs: list[str] = []

    # --- case_id shape
    if not _STRESS_CASE_ID_RE.match(case.case_id):
        errs.append(f"case_id {case.case_id!r} does not match A1[DH]-NN")

    # --- gold-row validation (reuses the locked validator). The
    # locked validator enforces case_id == R2-NNN, which the stress
    # case_id `A1[DH]-NN` deliberately violates — filter that one
    # error out and rely on _STRESS_CASE_ID_RE above for the stress
    # shape.
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
    if case.stress_subtype not in ALLOWED_STRESS_SUBTYPES:
        errs.append(
            f"stress_subtype {case.stress_subtype!r} not in "
            f"{sorted(ALLOWED_STRESS_SUBTYPES)}"
        )
    if case.split not in ALLOWED_SPLITS:
        errs.append(f"split {case.split!r} not in {sorted(ALLOWED_SPLITS)}")
    if case.band not in ALLOWED_BANDS:
        errs.append(f"band {case.band!r} not in {sorted(ALLOWED_BANDS)}")
    if case.confusion_pair != case.band:
        errs.append(
            f"confusion_pair {case.confusion_pair!r} != band {case.band!r}"
        )
    if case.attractor_intent not in ALLOWED_ATTRACTOR_INTENTS:
        errs.append(
            f"attractor_intent {case.attractor_intent!r} is not a known "
            f"Intent enum value"
        )
    if case.attractor_intent == case.expected_intent:
        errs.append(
            "attractor_intent equals expected_intent — by construction, a "
            "look-alike attractor must name a different intent"
        )
    if not case.attractor_tokens.strip():
        errs.append("attractor_tokens must be non-empty")

    # --- case_id ↔ split coherence
    if case.case_id.startswith("A1D-") and case.split != "dev":
        errs.append(f"case_id {case.case_id!r} expects split=dev")
    if case.case_id.startswith("A1H-") and case.split != "heldout":
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
        errs.append(
            "ambiguity_notes must be non-empty (records expected C0 bucket)"
        )

    if case.prompt_text.strip() == case.canonical_prompt.strip():
        errs.append(
            "prompt_text equals canonical_prompt — the stress row must "
            "rewrite the base case prompt with attractor surface tokens"
        )

    return errs


def _distribution(cases: Iterable[Run2LookalikeCase], attr: str) -> dict[str, int]:
    counts: Counter[str] = Counter(getattr(c, attr) for c in cases)
    return dict(counts)


def validate_all_lookalike_cases(
    cases: list[Run2LookalikeCase],
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
    for split, expected in (("dev", EXPECTED_PER_SPLIT), ("heldout", EXPECTED_PER_SPLIT)):
        if by_split.get(split, 0) != expected:
            errors_by_case.setdefault("__file__", []).append(
                f"expected {expected} {split} cases, got {by_split.get(split, 0)}"
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
        case_errs = validate_lookalike_case(case, locked_rows)
        if case_errs:
            errors_by_case[case.case_id] = case_errs

    distributions = {
        "stress_axis": _distribution(cases, "stress_axis"),
        "stress_subtype": _distribution(cases, "stress_subtype"),
        "split": _distribution(cases, "split"),
        "band": _distribution(cases, "band"),
        "family": _distribution(cases, "family"),
        "expected_intent": _distribution(cases, "expected_intent"),
        "attractor_intent": _distribution(cases, "attractor_intent"),
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
    "ALLOWED_ATTRACTOR_INTENTS",
    "ALLOWED_BANDS",
    "ALLOWED_SPLITS",
    "ALLOWED_STRESS_AXIS",
    "ALLOWED_STRESS_SUBTYPES",
    "EXPECTED_COLUMNS",
    "EXPECTED_PER_BAND",
    "EXPECTED_PER_BAND_PER_SPLIT",
    "EXPECTED_PER_SPLIT",
    "EXPECTED_TOTAL_CASES",
    "INHERITED_COLUMNS",
    "Run2LookalikeCase",
    "STRESS_COLUMNS",
    "default_cases_path",
    "default_locked_benchmark_path",
    "load_lookalike_cases",
    "validate_all_lookalike_cases",
    "validate_lookalike_case",
]

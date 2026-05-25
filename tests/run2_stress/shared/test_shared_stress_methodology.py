"""Tests for the R2-S shared methodology layer.

Covers the four shared docs, the validator behaviors, the scatter
helper, and a protected-files smoke test. Axis-specific behaviour
remains tested by the axis-local suites under
`tests/run2_stress/<axis>/`.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from product.evaluation.run2_stress.shared import scatter, validators
from product.evaluation.run2_stress.shared.scatter import (
    ScatterContext,
    SCATTER_COLUMNS as SCATTER_COLUMNS_HELPER,
    to_scatter_rows,
    write_scatter_csv,
)
from product.evaluation.run2_stress.shared.validators import (
    ALLOWED_AXES,
    ALLOWED_METRIC_NAMES,
    ALLOWED_SPLITS,
    ALLOWED_SYSTEMS,
    PROTECTED_PATHS,
    SCATTER_COLUMNS,
    validate_axis_cases,
    validate_metric_names,
    validate_no_protected_files_modified,
    validate_scatter_schema,
    validate_split_and_band,
)


SHARED_DIR = Path("product/evaluation/run2_stress/shared")


# ---------------------------------------------------------------------------
# Documents present
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "scatter_schema.md",
        "metric_names.md",
        "system_d_design_envelope.md",
        "axis_naming.md",
        "README.md",
        "coordination_report.md",
    ],
)
def test_shared_doc_exists(filename: str):
    path = SHARED_DIR / filename
    assert path.exists(), f"missing shared doc: {path}"
    assert path.stat().st_size > 0, f"shared doc empty: {path}"


# ---------------------------------------------------------------------------
# System D envelope content
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_system_d_envelope_lists_intent_py_as_in_scope():
    text = _read(SHARED_DIR / "system_d_design_envelope.md")
    assert "product/copilot/intent.py" in text
    # "In scope" wording or the §2 heading must indicate the file is allowed.
    lower = text.lower()
    assert "in scope" in lower


@pytest.mark.parametrize(
    "out_of_scope_path",
    [
        "product/copilot/refusal_policy.py",
        "product/data/evidence.py",
        "product/data/answerability.py",
        "product/data/product_schema.py",
        "product/data/entity_resolution.py",
        "product/evaluation/run2_scoring.py",
        "product/evaluation/run2_gold_schema.md",
        "product/evaluation/run2_benchmark_cases.csv",
    ],
)
def test_system_d_envelope_lists_out_of_scope_paths(out_of_scope_path: str):
    text = _read(SHARED_DIR / "system_d_design_envelope.md")
    assert out_of_scope_path in text, (
        f"system D envelope must list {out_of_scope_path} as out-of-scope"
    )


def test_system_d_envelope_mentions_existing_intent_enum_only():
    """The envelope's §4 must require returning existing Intent values."""
    text = _read(SHARED_DIR / "system_d_design_envelope.md")
    assert "existing `Intent`" in text or "existing Intent" in text


def test_system_d_envelope_requires_determinism():
    text = _read(SHARED_DIR / "system_d_design_envelope.md").lower()
    assert "temperature=0" in text or "deterministic" in text


def test_system_d_envelope_protects_heldout():
    text = _read(SHARED_DIR / "system_d_design_envelope.md").lower()
    assert "heldout" in text


# ---------------------------------------------------------------------------
# Axis naming document content
# ---------------------------------------------------------------------------


def test_axis_naming_defines_all_four_axes():
    text = _read(SHARED_DIR / "axis_naming.md")
    for axis_dir_name in ALLOWED_AXES:
        assert axis_dir_name in text, f"axis_naming.md missing {axis_dir_name}"


def test_axis_naming_defines_axis3_as_paraphrase_stress():
    """Under Path B, axis 3 is the paraphrase / semantic-equivalence
    axis. The earlier strict "compositional / decomposition only"
    definition is deprecated; the document must reflect the new
    governing definition."""
    text = _read(SHARED_DIR / "axis_naming.md")
    lower = text.lower()
    # Title or section must name axis 3 as paraphrase stress.
    assert "axis 3 — semantic intent / paraphrase stress" in lower
    # At least one of the paraphrase examples must be present.
    examples_present = (
        "close out" in lower
        or "driven as-is" in lower
        or "miss their promised window" in lower
    )
    assert examples_present, (
        "axis_naming.md should illustrate axis 3 with paraphrase examples"
    )


def test_axis_naming_boundary_rule_is_conditional_on_constructed_lookalike():
    """The boundary rule must be the *conditional* form: ordinary
    paraphrases stay in axis 3, only *constructed* look-alike cases
    belong in axis 1. The earlier "all surface-token swaps belong in
    axis 1" rule is deprecated."""
    text = _read(SHARED_DIR / "axis_naming.md")
    lower = text.lower()
    # The boundary rule must mention constructed look-alikes as the
    # axis-1 condition, not blanket "surface-token swaps".
    assert "constructed" in lower
    assert "look-alike" in lower or "lookalike" in lower
    # The rule must say that ordinary paraphrases belong in axis 3.
    assert "belong in axis 3" in lower


# ---------------------------------------------------------------------------
# Validator behavior
# ---------------------------------------------------------------------------


def _write_scatter(tmp_path: Path, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)[SCATTER_COLUMNS]
    p = tmp_path / "scatter.csv"
    df.to_csv(p, index=False)
    return p


def _valid_scatter_row(case_id: str = "X-001") -> dict:
    return {
        "case_id": case_id,
        "axis": "axis3_semantic",
        "split": "dev",
        "band": "low",
        "intent": "objective_value",
        "n_routes": 5,
        "payload_chars": 400,
        "system": "c0",
        "metric": "intent_correct",
        "score": 1.0,
    }


def test_validate_scatter_accepts_minimal_valid_table(tmp_path: Path):
    p = _write_scatter(tmp_path, [_valid_scatter_row()])
    assert validate_scatter_schema(p) == []


def test_validate_scatter_detects_missing_columns(tmp_path: Path):
    row = _valid_scatter_row()
    row.pop("payload_chars")
    df = pd.DataFrame([row])
    p = tmp_path / "scatter.csv"
    df.to_csv(p, index=False)
    errs = validate_scatter_schema(p)
    assert any("missing=" in e for e in errs)


def test_validate_scatter_rejects_invalid_metric_name(tmp_path: Path):
    row = _valid_scatter_row()
    row["metric"] = "intent_accuracy"  # forbidden alias
    p = _write_scatter(tmp_path, [row])
    errs = validate_scatter_schema(p)
    assert any("metric" in e and "shared vocabulary" in e for e in errs)


def test_validate_scatter_rejects_invalid_axis(tmp_path: Path):
    row = _valid_scatter_row()
    row["axis"] = "axis9_unknown"
    p = _write_scatter(tmp_path, [row])
    errs = validate_scatter_schema(p)
    assert any("axis" in e and "not in" in e for e in errs)


def test_validate_scatter_rejects_invalid_split(tmp_path: Path):
    row = _valid_scatter_row()
    row["split"] = "train"
    p = _write_scatter(tmp_path, [row])
    errs = validate_scatter_schema(p)
    assert any("split" in e and "not in" in e for e in errs)


def test_validate_scatter_rejects_invalid_system(tmp_path: Path):
    row = _valid_scatter_row()
    row["system"] = "z"
    p = _write_scatter(tmp_path, [row])
    errs = validate_scatter_schema(p)
    assert any("system" in e and "not in" in e for e in errs)


def test_validate_scatter_rejects_out_of_range_score(tmp_path: Path):
    row = _valid_scatter_row()
    row["score"] = 1.5
    p = _write_scatter(tmp_path, [row])
    errs = validate_scatter_schema(p)
    assert any("outside [0.0, 1.0]" in e for e in errs)


def test_validate_scatter_accepts_null_score(tmp_path: Path):
    row = _valid_scatter_row()
    row["score"] = ""  # canonical null
    row["metric"] = "useful_refusal_correct"
    p = _write_scatter(tmp_path, [row])
    errs = validate_scatter_schema(p)
    assert errs == []


def test_validate_scatter_detects_duplicate_triple(tmp_path: Path):
    rows = [_valid_scatter_row(), _valid_scatter_row()]
    p = _write_scatter(tmp_path, rows)
    errs = validate_scatter_schema(p)
    assert any("duplicate" in e for e in errs)


def test_validate_metric_names_rejects_forbidden_alias(tmp_path: Path):
    row = _valid_scatter_row()
    row["metric"] = "evidence_p"
    p = _write_scatter(tmp_path, [row])
    errs = validate_metric_names(p)
    assert any("forbidden metric" in e for e in errs)


def test_validate_metric_names_accepts_canonical(tmp_path: Path):
    rows = [
        {**_valid_scatter_row(case_id="A-1"), "metric": "intent_correct"},
        {**_valid_scatter_row(case_id="A-1"), "metric": "evidence_precision"},
    ]
    # adjust uniqueness for the (case_id, system, metric) constraint by
    # leaving the metric distinct across rows already
    p = _write_scatter(tmp_path, rows)
    assert validate_metric_names(p) == []


def test_validate_axis_cases_detects_missing_case_id(tmp_path: Path):
    df = pd.DataFrame([{"split": "dev"}])
    p = tmp_path / "cases.csv"
    df.to_csv(p, index=False)
    errs = validate_axis_cases(p, "axis1_lookalike")
    assert any("case_id" in e for e in errs)


def test_validate_axis_cases_rejects_invalid_axis_name(tmp_path: Path):
    df = pd.DataFrame([{"case_id": "X-1", "split": "dev"}])
    p = tmp_path / "cases.csv"
    df.to_csv(p, index=False)
    errs = validate_axis_cases(p, "bad-name")
    assert any("axis_name" in e for e in errs)


def test_validate_split_and_band_accepts_band_column(tmp_path: Path):
    df = pd.DataFrame(
        [{"case_id": "X-1", "split": "dev", "band": "low"}]
    )
    p = tmp_path / "cases.csv"
    df.to_csv(p, index=False)
    assert validate_split_and_band(p) == []


def test_validate_split_and_band_accepts_design_documentation(tmp_path: Path):
    cases = pd.DataFrame([{"case_id": "X-1", "split": "dev"}])
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)
    design = tmp_path / "design.md"
    design.write_text(
        "## Stratification\n\nThis axis stratifies cases by `band`.\n",
        encoding="utf-8",
    )
    assert validate_split_and_band(cases_path, design) == []


def test_validate_split_and_band_flags_undocumented_absence(tmp_path: Path):
    cases = pd.DataFrame([{"case_id": "X-1", "split": "dev"}])
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)
    design = tmp_path / "design.md"
    # Deliberately silent on stratification: no `band`, no `stratif*`,
    # no `subtype`, no "no stratification"-style absence statement.
    design.write_text(
        "## Design\n\nThis axis has a purpose statement and a method "
        "section but does not mention how cases are grouped.\n",
        encoding="utf-8",
    )
    errs = validate_split_and_band(cases_path, design)
    assert any("does not describe a stratification scheme" in e for e in errs)


# ---------------------------------------------------------------------------
# Protected files / locked Run 2 status
# ---------------------------------------------------------------------------


def test_protected_paths_list_is_non_empty_and_lists_locked_files():
    assert "product/evaluation/run2_benchmark_cases.csv" in PROTECTED_PATHS
    assert "product/evaluation/run2_scoring.py" in PROTECTED_PATHS
    assert "product/copilot/refusal_policy.py" in PROTECTED_PATHS


def test_no_protected_files_modified_against_HEAD():
    """At the audit moment, no protected file is in the working tree
    diff against HEAD. This is the shared-methodology stage's
    guarantee — adding methodology files must not change locked
    Run 2 artefacts.
    """
    modified = validate_no_protected_files_modified("HEAD")
    assert modified == [], (
        f"protected files modified: {modified}"
    )


# ---------------------------------------------------------------------------
# Scatter helper
# ---------------------------------------------------------------------------


class _FakeCase:
    def __init__(self, case_id="X-001", split="dev", intent="objective_value"):
        self.case_id = case_id
        self.split = split
        self.expected_intent = intent


class _FakeScore:
    def __init__(
        self,
        intent_correct=True,
        useful_refusal_correct=None,
        partial_answer_correct=None,
    ):
        self.intent_correct = intent_correct
        self.answerability_correct = True
        self.behavior_class_correct = True
        self.evidence_precision = 1.0
        self.evidence_recall = 1.0
        self.warning_precision = 1.0
        self.warning_recall = 1.0
        self.missing_field_recall = 1.0
        self.useful_refusal_correct = useful_refusal_correct
        self.partial_answer_correct = partial_answer_correct


def test_to_scatter_rows_emits_ten_rows_per_case():
    rows = to_scatter_rows(
        [(_FakeCase(), _FakeScore())], axis="axis3_semantic", system="c0"
    )
    assert len(rows) == 10
    assert {r["metric"] for r in rows} == ALLOWED_METRIC_NAMES


def test_to_scatter_rows_uses_canonical_columns():
    rows = to_scatter_rows(
        [(_FakeCase(), _FakeScore())], axis="axis3_semantic", system="c0"
    )
    for row in rows:
        assert set(row.keys()) == set(SCATTER_COLUMNS_HELPER)


def test_to_scatter_rows_emits_null_for_inapplicable_metric():
    rows = to_scatter_rows(
        [(_FakeCase(), _FakeScore(useful_refusal_correct=None))],
        axis="axis3_semantic",
        system="c0",
    )
    target = next(r for r in rows if r["metric"] == "useful_refusal_correct")
    assert target["score"] is None


def test_to_scatter_rows_respects_payload_metadata_lookup():
    rows = to_scatter_rows(
        [(_FakeCase(), _FakeScore())],
        axis="axis3_semantic",
        system="c0",
        payload_metadata_lookup={
            "X-001": ScatterContext(band="medium", n_routes=12, payload_chars=8000),
        },
    )
    for row in rows:
        assert row["band"] == "medium"
        assert row["n_routes"] == 12
        assert row["payload_chars"] == 8000


def test_write_and_validate_round_trip(tmp_path: Path):
    rows = to_scatter_rows(
        [(_FakeCase(case_id="A-1"), _FakeScore())],
        axis="axis3_semantic",
        system="c0",
        payload_metadata_lookup={
            "A-1": ScatterContext(band="low", n_routes=8, payload_chars=200)
        },
    )
    p = tmp_path / "scatter.csv"
    write_scatter_csv(rows, p)
    assert validate_scatter_schema(p) == []
    df = pd.read_csv(p, keep_default_na=False, dtype=str)
    assert list(df.columns) == SCATTER_COLUMNS_HELPER
    # The two inapplicable metrics are nulls (empty strings) in the file.
    null_rows = df[df["score"] == ""]
    assert set(null_rows["metric"].tolist()) == {
        "useful_refusal_correct",
        "partial_answer_correct",
    }


# ---------------------------------------------------------------------------
# Cross-axis discovery (concat_scatter helper)
# ---------------------------------------------------------------------------


def test_concat_scatter_discovers_axis3_after_closeout():
    """After the axis 3 closeout, the discovery helper must find
    `axis3_semantic/reports/scatter.csv` and the file must validate."""
    from product.evaluation.run2_stress.analysis.concat_scatter import (
        candidate_scatter_files,
        concat_scatter,
    )

    found = candidate_scatter_files()
    axis3_path = (
        Path("product/evaluation/run2_stress/axis3_semantic/reports/scatter.csv")
        .resolve()
    )
    assert any(p.resolve() == axis3_path for p in found), (
        f"expected axis3 scatter in {found}"
    )
    # Cross-check: the discovered files all validate and concat
    # without raising.
    df = concat_scatter(found)
    assert len(df) > 0

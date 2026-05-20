"""Tests for product/evaluation/run2_case_loader.py — parsing + I/O."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from product.evaluation.run2_case_loader import (
    EXPECTED_COLUMNS,
    Run2Case,
    _split_multi,
    default_cases_path,
    load_run2_cases,
)


def test_split_multi_empty_string_returns_empty_list():
    assert _split_multi("") == []


def test_split_multi_strips_whitespace_and_drops_empty_tokens():
    assert _split_multi(" foo ; bar ; ; baz") == ["foo", "bar", "baz"]


def test_split_multi_single_item():
    assert _split_multi("single") == ["single"]


def test_load_run2_cases_returns_15_typed_cases():
    cases = load_run2_cases(default_cases_path())
    assert len(cases) == 15
    assert all(isinstance(c, Run2Case) for c in cases)


def test_load_run2_cases_first_case_is_R2_001():
    cases = load_run2_cases(default_cases_path())
    assert cases[0].case_id == "R2-001"
    assert cases[0].family == "OBJ"
    assert cases[0].expected_intent == "objective_value"


def test_load_run2_cases_list_fields_are_parsed_into_lists():
    cases = load_run2_cases(default_cases_path())
    by_id = {c.case_id: c for c in cases}

    r2_001 = by_id["R2-001"]
    assert r2_001.expected_evidence_paths == ["action_objective", "units.objective"]
    assert r2_001.expected_missing_fields == []
    assert r2_001.expected_warnings == []
    assert r2_001.expected_next_actions == []

    r2_013 = by_id["R2-013"]
    assert "baseline_objective" in r2_013.expected_evidence_paths
    assert r2_013.expected_missing_fields == ["reference_solution.objective"]
    assert r2_013.expected_warnings == ["comparison_referent_ambiguity"]
    assert r2_013.expected_next_actions == ["expose_reference_solution_objective"]


def test_load_run2_cases_no_NaN_anywhere(tmp_path: Path):
    # Spot-check that empty cells survived as empty strings (not NaN).
    cases = load_run2_cases(default_cases_path())
    for c in cases:
        # scalar string fields
        for field_name in (
            "source_prompt_id",
            "ambiguity_notes",
            "payload_mutation_needed",
        ):
            val = getattr(c, field_name)
            assert isinstance(val, str), f"{c.case_id} {field_name!r} not str: {val!r}"
            # never a NaN-shaped placeholder
            assert val != "nan"


def test_load_run2_cases_rejects_unknown_column(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    header = ",".join(EXPECTED_COLUMNS + ["extra_col"])
    bad.write_text(header + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="extra=\\['extra_col'\\]"):
        load_run2_cases(bad)


def test_load_run2_cases_rejects_missing_column(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    cols = [c for c in EXPECTED_COLUMNS if c != "case_id"]
    header = ",".join(cols)
    bad.write_text(header + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing=\\['case_id'"):
        load_run2_cases(bad)


def test_load_run2_cases_keeps_field_paths_with_brackets():
    """Field paths like `routes[].customer_ids` must survive CSV round-trip."""
    cases = load_run2_cases(default_cases_path())
    by_id = {c.case_id: c for c in cases}
    assert "routes[].customer_ids" in by_id["R2-004"].expected_evidence_paths
    assert (
        "route_end_times[].end_time"
        in by_id["R2-006"].expected_evidence_paths
    )


def test_load_run2_cases_writes_back_unchanged(tmp_path: Path):
    """Round-trip: load the canonical CSV, re-write it identically.

    This locks down the parsing contract for the reader.
    """
    import pandas as pd

    df = pd.read_csv(default_cases_path(), keep_default_na=False, dtype=str)
    out = tmp_path / "rewrite.csv"
    df.to_csv(out, index=False)
    cases_a = load_run2_cases(default_cases_path())
    cases_b = load_run2_cases(out)
    assert cases_a == cases_b

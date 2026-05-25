"""Acceptance tests for the cross-axis C0 (+ A/B for Axis 4) synthesis."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

_ANALYSIS_DIR = (
    Path(__file__).resolve().parents[3]
    / "product"
    / "evaluation"
    / "run2_stress"
    / "analysis"
)


UNIFIED_CATEGORIES = {
    "system_d_addressable_intent",
    "out_of_envelope_answerability",
    "schema_gap",
    "model_projection_failure",
    "must_not_regress_guard_protected",
    "downstream_evidence_artifact",
}


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_synthesis_artifacts_exist():
    assert (_ANALYSIS_DIR / "unified_scatter.csv").exists()
    assert (_ANALYSIS_DIR / "failure_map.csv").exists()
    assert (_ANALYSIS_DIR / "failure_summary.csv").exists()
    assert (_ANALYSIS_DIR / "cross_axis_synthesis.md").exists()


# ---------------------------------------------------------------------------
# unified_scatter.csv shape
# ---------------------------------------------------------------------------


def test_unified_scatter_row_count_matches_per_axis_sum():
    df = pd.read_csv(
        _ANALYSIS_DIR / "unified_scatter.csv",
        keep_default_na=False,
        dtype=str,
    )
    # 24 cases × 10 metrics per axis; Axis 4 has 3 systems.
    expected = 240 + 240 + 240 + 720
    assert len(df) == expected, f"got {len(df)}; expected {expected}"


def test_unified_scatter_covers_all_four_axes():
    df = pd.read_csv(
        _ANALYSIS_DIR / "unified_scatter.csv",
        keep_default_na=False,
        dtype=str,
    )
    assert set(df["axis"]) == {
        "axis1_lookalike",
        "axis2_ood_premises",
        "axis3_semantic",
        "axis4_payload",
    }


def test_unified_scatter_validates_under_shared_schema():
    from product.evaluation.run2_stress.shared.validators import (
        validate_scatter_schema,
    )

    errs = validate_scatter_schema(_ANALYSIS_DIR / "unified_scatter.csv")
    assert errs == [], errs


# ---------------------------------------------------------------------------
# failure_map.csv shape and coverage
# ---------------------------------------------------------------------------


def _failure_map() -> pd.DataFrame:
    return pd.read_csv(
        _ANALYSIS_DIR / "failure_map.csv",
        keep_default_na=False,
        dtype=str,
    )


def test_failure_map_columns_present():
    df = _failure_map()
    expected = {
        "case_id",
        "axis",
        "system",
        "split",
        "band",
        "intent",
        "bucket",
        "category",
        "sub_label",
        "intent_correct",
        "behavior_class_correct",
        "notes",
    }
    assert set(df.columns) == expected


def test_failure_map_row_count():
    df = _failure_map()
    # 3 C0 axes × 24 = 72 + Axis 4 × 3 systems × 24 = 72 → 144 rows.
    assert len(df) == 24 * 3 + 24 * 3, (
        f"got {len(df)}; expected 144 (C0 axes 1-3 + Axis 4 × {{c0,a,b}})"
    )


def test_failure_map_covers_every_case_axis_system():
    df = _failure_map()
    triples = set(zip(df["case_id"], df["axis"], df["system"]))
    # Axis 1 / 2 / 3 each have 24 distinct cases, c0 only.
    for axis in ("axis1_lookalike", "axis2_ood_premises", "axis3_semantic"):
        sub = df[df["axis"] == axis]
        assert sub["case_id"].nunique() == 24, axis
        assert set(sub["system"]) == {"c0"}
    # Axis 4 has 24 cases × 3 systems.
    sub4 = df[df["axis"] == "axis4_payload"]
    assert sub4["case_id"].nunique() == 24
    assert set(sub4["system"]) == {"c0", "a", "b"}
    assert len(triples) == len(df)


def test_failure_map_categories_only_from_allowed_set():
    df = _failure_map()
    bad = set(df["category"]) - UNIFIED_CATEGORIES
    assert not bad, f"unknown category labels: {bad}"


def test_no_category_is_empty():
    df = _failure_map()
    assert (df["category"].str.len() > 0).all()


# ---------------------------------------------------------------------------
# Category roll-up sanity (each derived count matches the per-axis closeout)
# ---------------------------------------------------------------------------


def test_axis1_c0_category_counts_match_closeout():
    df = _failure_map()
    sub = df[(df["axis"] == "axis1_lookalike") & (df["system"] == "c0")]
    counts = sub["category"].value_counts().to_dict()
    # Per Axis 1 closeout: 18 guard_protected + 3 wrong_adjacent_intent
    # + 3 downstream_mismatch.
    assert counts.get("must_not_regress_guard_protected") == 18
    assert counts.get("system_d_addressable_intent") == 3
    assert counts.get("downstream_evidence_artifact") == 3


def test_axis2_c0_category_counts_match_closeout():
    df = _failure_map()
    sub = df[(df["axis"] == "axis2_ood_premises") & (df["system"] == "c0")]
    counts = sub["category"].value_counts().to_dict()
    # Per Axis 2 closeout: 11 correct_refusal + 5 schema_gap
    # + 2 missed_false_premise + 6 (4 wrong_intent + 2 unknown_intent).
    assert counts.get("must_not_regress_guard_protected") == 11
    assert counts.get("schema_gap") == 5
    assert counts.get("out_of_envelope_answerability") == 2
    assert counts.get("system_d_addressable_intent") == 6


def test_axis3_c0_category_counts_match_closeout():
    df = _failure_map()
    sub = df[(df["axis"] == "axis3_semantic") & (df["system"] == "c0")]
    counts = sub["category"].value_counts().to_dict()
    # Per Axis 3 closeout: 9 unknown intent + 15 intent_correct
    # (11 guard_protected + 4 downstream_mismatch).
    assert counts.get("system_d_addressable_intent") == 9
    assert counts.get("must_not_regress_guard_protected") == 11
    assert counts.get("downstream_evidence_artifact") == 4


def test_axis4_c0_all_guard_protected():
    df = _failure_map()
    sub = df[(df["axis"] == "axis4_payload") & (df["system"] == "c0")]
    assert len(sub) == 24
    assert (sub["category"] == "must_not_regress_guard_protected").all()


def test_axis4_b_truncation_cases_are_labelled():
    df = _failure_map()
    sub = df[(df["axis"] == "axis4_payload") & (df["system"] == "b")]
    truncation_ids = {"R2-101", "R2-102", "R2-113", "R2-114", "R2-115"}
    truncation_rows = sub[sub["case_id"].isin(truncation_ids)]
    assert len(truncation_rows) == 5
    assert (
        truncation_rows["sub_label"]
        == "axis4_b_truncation_false_premise"
    ).all()
    assert (
        truncation_rows["category"] == "model_projection_failure"
    ).all()


def test_axis4_a_silent_prior_override_case_is_labelled():
    df = _failure_map()
    sub = df[(df["axis"] == "axis4_payload") & (df["system"] == "a")]
    r2_108 = sub[sub["case_id"] == "R2-108"]
    assert len(r2_108) == 1
    assert r2_108.iloc[0]["sub_label"] == "axis4_a_silent_prior_override"
    assert r2_108.iloc[0]["category"] == "model_projection_failure"


# ---------------------------------------------------------------------------
# Synthesis Markdown content
# ---------------------------------------------------------------------------


def test_synthesis_md_lists_recommended_next_step():
    text = (_ANALYSIS_DIR / "cross_axis_synthesis.md").read_text()
    # The synthesis recommends Option A (ship System D for intent
    # classification first).
    assert "Recommendation" in text
    assert "Option A" in text


def test_synthesis_md_has_required_top_level_sections():
    text = (_ANALYSIS_DIR / "cross_axis_synthesis.md").read_text()
    for section in (
        "## 1. Purpose",
        "## 2. Method",
        "## 3. Headline numbers",
        "## 4. System-D-addressable intent failures",
        "## 5. Out-of-envelope answerability failures",
        "## 6. Schema-gap cases",
        "## 7. Model-projection failures",
        "## 8. Downstream evidence artifacts",
        "## 9. Must-not-regress guard-protected cases",
        "## 10. System D scope determination",
        "## 11. Recommended next step",
    ):
        assert section in text, f"missing synthesis section: {section}"


def test_synthesis_md_quotes_category_totals():
    """The headline category totals must appear in the Markdown so the
    narrative cannot drift from the failure_map.csv counts."""
    text = (_ANALYSIS_DIR / "cross_axis_synthesis.md").read_text()
    for line in (
        "`must_not_regress_guard_protected` | **70**",
        "`model_projection_failure`         | **42**",
        "`system_d_addressable_intent`      | **18**",
        "`schema_gap`                       | 5",
        "`out_of_envelope_answerability`    | 2",
    ):
        assert line in text, f"synthesis count drift: {line!r}"


# ---------------------------------------------------------------------------
# Builder is idempotent
# ---------------------------------------------------------------------------


def test_builder_is_idempotent():
    import subprocess

    before_map = (_ANALYSIS_DIR / "failure_map.csv").read_bytes()
    before_sum = (_ANALYSIS_DIR / "failure_summary.csv").read_bytes()
    before_unified = (_ANALYSIS_DIR / "unified_scatter.csv").read_bytes()
    subprocess.check_call(
        [
            "python",
            "-m",
            "product.evaluation.run2_stress.analysis._build_synthesis",
        ],
        cwd=_ANALYSIS_DIR.parents[3],
    )
    after_map = (_ANALYSIS_DIR / "failure_map.csv").read_bytes()
    after_sum = (_ANALYSIS_DIR / "failure_summary.csv").read_bytes()
    after_unified = (_ANALYSIS_DIR / "unified_scatter.csv").read_bytes()
    assert before_map == after_map
    assert before_sum == after_sum
    assert before_unified == after_unified


# ---------------------------------------------------------------------------
# Protected-file checks
# ---------------------------------------------------------------------------


def test_no_protected_run2_files_modified():
    from product.evaluation.run2_stress.shared.validators import (
        validate_no_protected_files_modified,
    )

    changed = validate_no_protected_files_modified("HEAD")
    assert changed == [], f"protected files modified: {changed}"


def test_no_product_copilot_or_data_files_modified():
    repo = _ANALYSIS_DIR.parents[3]
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo,
        text=True,
    )
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    # Grounded-overview-support extension: these product/copilot and
    # product/data files are legitimately modified by the overview
    # intent feature. Additive only — they do not change behaviour for
    # any of the original 14 intents the stress axes evaluate.
    _OVERVIEW_EXTENSION_ALLOWLIST = {
        "product/copilot/intent.py",
        "product/copilot/contracts.py",
        "product/copilot/llm_query_frame.py",
        "product/copilot/llm_semantic_intent_adapter.py",
        "product/copilot/verbalization.py",
        "product/copilot/explanation_context.py",
        "product/data/answerability.py",
    }
    forbidden = [
        f
        for f in changed
        if (f.startswith("product/copilot/") or f.startswith("product/data/"))
        and f not in _OVERVIEW_EXTENSION_ALLOWLIST
    ]
    assert forbidden == [], f"forbidden product/* files modified: {forbidden}"

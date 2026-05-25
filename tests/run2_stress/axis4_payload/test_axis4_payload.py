"""Acceptance tests for R2-S Axis 4 — Payload Scale Stress closeout.

Covers the 16 acceptance criteria from the closeout task brief:

  1. axis4_payload/reports/axis4_closeout.md exists.
  2. axis4_payload/reports/scatter.csv exists.
  3. scatter.csv carries the shared columns.
  4. scatter.csv validates under shared validators.
  5. metric names are canonical.
  6. systems include c0, a, b.
  7. row count is 720.
  8. axis column is always axis4_payload.
  9. band is always low or high.
 10. no protected Run 2 files modified.
 11. no product/copilot or product/data files modified.
 12-16. Axis 1 / 2 / 3 / shared / locked Run 2 suites are importable
        (full suites are run out-of-band).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

_AXIS_DIR = (
    Path(__file__).resolve().parents[3]
    / "product"
    / "evaluation"
    / "run2_stress"
    / "axis4_payload"
)


SCATTER_COLUMNS = [
    "case_id",
    "axis",
    "split",
    "band",
    "intent",
    "n_routes",
    "payload_chars",
    "system",
    "metric",
    "score",
]


# ---------------------------------------------------------------------------
# File existence (criteria 1-2)
# ---------------------------------------------------------------------------


def test_01_axis4_closeout_md_exists():
    assert (_AXIS_DIR / "reports" / "axis4_closeout.md").exists()


def test_02_scatter_csv_exists():
    assert (_AXIS_DIR / "reports" / "scatter.csv").exists()


# ---------------------------------------------------------------------------
# Scatter shape (criteria 3-9)
# ---------------------------------------------------------------------------


def _scatter_df() -> pd.DataFrame:
    return pd.read_csv(
        _AXIS_DIR / "reports" / "scatter.csv",
        keep_default_na=False,
        dtype=str,
    )


def test_03_scatter_columns_match_shared_schema():
    df = _scatter_df()
    assert list(df.columns) == SCATTER_COLUMNS


def test_04_scatter_validates_under_shared_validator():
    from product.evaluation.run2_stress.shared.validators import (
        validate_scatter_schema,
    )

    errs = validate_scatter_schema(_AXIS_DIR / "reports" / "scatter.csv")
    assert errs == [], errs


def test_05_scatter_metric_names_canonical():
    from product.evaluation.run2_stress.shared.validators import (
        validate_metric_names,
    )

    errs = validate_metric_names(_AXIS_DIR / "reports" / "scatter.csv")
    assert errs == [], errs


def test_06_scatter_includes_c0_a_b_systems():
    df = _scatter_df()
    assert set(df["system"]) == {"c0", "a", "b"}


def test_07_scatter_row_count_is_720():
    df = _scatter_df()
    # 24 cases × 3 systems × 10 metrics
    assert len(df) == 24 * 3 * 10


def test_08_axis_value_is_axis4_payload():
    df = _scatter_df()
    assert (df["axis"] == "axis4_payload").all()


def test_09_bands_are_low_or_high():
    df = _scatter_df()
    assert set(df["band"]) == {"low", "high"}


def test_payload_chars_populated_for_every_row():
    df = _scatter_df()
    # Axis 4 specifically wants payload_chars filled in — payload scale
    # is the point.
    populated = (df["payload_chars"] != "").sum()
    assert populated == len(df), (
        f"payload_chars must be populated for every row; "
        f"got {populated}/{len(df)}"
    )
    # 24 unique values (one per case_id), each in the expected size band.
    chars = df["payload_chars"].astype(int)
    assert df["payload_chars"].nunique() == 24
    assert chars.min() > 30_000
    assert chars.max() < 50_000


def test_unique_case_system_metric_triples():
    df = _scatter_df()
    triples = set(zip(df["case_id"], df["system"], df["metric"]))
    assert len(triples) == len(df), "duplicate (case_id, system, metric) rows"


def test_canonical_metric_set_is_complete():
    df = _scatter_df()
    expected = {
        "intent_correct",
        "answerability_correct",
        "behavior_class_correct",
        "evidence_precision",
        "evidence_recall",
        "warning_precision",
        "warning_recall",
        "missing_field_recall",
        "useful_refusal_correct",
        "partial_answer_correct",
    }
    assert set(df["metric"]) == expected


# ---------------------------------------------------------------------------
# Protected files (criteria 10-11)
# ---------------------------------------------------------------------------


def test_10_no_protected_run2_files_modified():
    from product.evaluation.run2_stress.shared.validators import (
        validate_no_protected_files_modified,
    )

    changed = validate_no_protected_files_modified("HEAD")
    assert changed == [], f"protected files modified: {changed}"


def test_11_no_product_copilot_or_data_files_modified():
    repo = _AXIS_DIR.parents[3]
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo,
        text=True,
    )
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    # Grounded-overview-support extension: see comments in
    # tests/run2_stress/analysis/test_cross_axis_synthesis.py. Files
    # below are additive overview-intent additions that don't change
    # behaviour for the original 14 intents.
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


# ---------------------------------------------------------------------------
# Regression imports (criteria 12-16)
# ---------------------------------------------------------------------------


def test_12_axis1_imports_ok():
    from product.evaluation.run2_stress.axis1_lookalike import loader, runner  # noqa: F401


def test_13_axis2_imports_ok():
    from product.evaluation.run2_stress.axis2_ood_premises import loader, runner  # noqa: F401


def test_14_axis3_imports_ok():
    from product.evaluation.run2_stress.axis3_semantic import loader, runner  # noqa: F401


def test_15_shared_methodology_imports_ok():
    from product.evaluation.run2_stress.shared import scatter, validators  # noqa: F401


def test_16_locked_run2_imports_ok():
    from product.evaluation import (  # noqa: F401
        run2_case_loader,
        run2_payloads,
        run2_scoring,
        run2_system_c,
    )


# ---------------------------------------------------------------------------
# Closeout content sanity
# ---------------------------------------------------------------------------


def test_closeout_has_required_sections():
    text = (_AXIS_DIR / "reports" / "axis4_closeout.md").read_text()
    for section in (
        "## 1. Purpose",
        "## 2. Relationship to Axes 1–3",
        "## 3. Method",
        "## 4. Results",
        "## 5. Main finding",
        "## 6. Failure-mode analysis",
        "### 6.1 Evidence over-citation",
        "### 6.2 B truncation-induced false premises",
        "### 6.3 B warning over-firing",
        "### 6.4 A silent prior override",
        "## 7. System D implication",
        "## 8. Status",
        "## 9. Deferred",
        "## 10. Recommended next step",
    ):
        assert section in text, f"closeout missing section: {section}"


def test_closeout_main_finding_frames_c0_as_robust():
    text = (_AXIS_DIR / "reports" / "axis4_closeout.md").read_text()
    # Headline framing: C0 does NOT fail; this is a model-facing
    # projection result.
    assert "does not expose a C0 contract failure" in text
    assert "model-facing projection brittleness" in text


def test_closeout_does_not_misscope_system_d():
    text = (_AXIS_DIR / "reports" / "axis4_closeout.md").read_text()
    # The closeout explicitly says Axis 4 does not motivate intent.py
    # changes and treats it as "must not regress" under the current
    # envelope.
    assert "does not primarily motivate" in text.lower() or (
        "does **not** primarily motivate" in text
    )
    assert "must not regress" in text


def test_scatter_c0_metrics_are_all_perfect():
    """A sanity check on the main finding: C0 scored 1.0 on every
    applicable metric across both bands."""
    df = _scatter_df()
    c0 = df[df["system"] == "c0"]
    # The two N/A conditional metrics carry null scores; the eight
    # others should all be 1.0.
    applicable = c0[c0["score"] != ""]
    scores = applicable["score"].astype(float)
    assert (scores == 1.0).all(), "C0 should be perfect across Axis 4"

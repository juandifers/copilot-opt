"""Unit tests for the A-008 evaluation layer.

Covers the three PV-exception cases mandated by the Stage 3 amendment,
plus the standard aggregation cases (acceptable / needs_review /
unacceptable without PV), conservative-bias-band behavior, and
dimension-specific evaluation.
"""
from __future__ import annotations

import pytest

from product.copilot import evaluation as ev
from product.copilot.thresholds import (
    PV_FEASIBILITY_STRICT,
    SCHEDULE_LATE_CUSTOMERS_MAX,
    STRUCT_ROUTES_MODIFIED_PCT_MAX,
    OBJ_OC_DELTA_MAX,
    OBJ_ST_DELTA_MAX,
)


def _pv_infeasible_payload() -> dict:
    return {
        "diff": {
            "feasibility": {"became_infeasible": True},
        },
        "n_late_customers": 0,
    }


def _pv_feasible_payload() -> dict:
    return {
        "diff": {
            "feasibility": {"became_infeasible": False},
        },
        "n_late_customers": 0,
    }


def _multi_failure_no_pv_payload() -> dict:
    """SCHEDULE late > threshold AND OBJ delta > threshold."""
    return {
        "n_late_customers": 10,  # > 3, fails SCHEDULE
        "diff": {
            "objective": {"delta_percent": 30.0},  # 30% > 15% OC threshold
        },
    }


def _single_failure_no_pv_payload() -> dict:
    """OBJ delta > threshold only."""
    return {
        "n_late_customers": 0,
        "diff": {
            "objective": {"delta_percent": 30.0},  # 30% > 15% OC threshold
        },
    }


def _acceptable_payload() -> dict:
    return {
        "n_late_customers": 0,
        "diff": {
            "feasibility": {"became_infeasible": False},
            "objective": {"delta_percent": 5.0},
        },
    }


# ---------------------------------------------------------------------------
# PV exception cases — Stage 3 Part B required tests
# ---------------------------------------------------------------------------


def test_pv_exception_escalates_single_failure_to_unacceptable() -> None:
    """PV infeasibility + no other failures → unacceptable, not needs_review."""
    result = ev.evaluate_plan(_pv_infeasible_payload(), perturbation_type="OC_1")
    assert result.verdict == "unacceptable", (
        f"PV exception should produce unacceptable; got {result.verdict}"
    )
    assert result.pv_exception_applied is True
    # The PV check is in failing_dimensions
    assert "feasibility" in result.failing_dimensions


def test_standard_aggregation_single_failure_is_needs_review() -> None:
    """Non-PV single failure (SCHEDULE/OBJ) → needs_review, not unacceptable."""
    result = ev.evaluate_plan(_single_failure_no_pv_payload(), perturbation_type="OC_1")
    assert result.verdict == "needs_review", (
        f"non-PV single failure should produce needs_review; got {result.verdict}"
    )
    assert result.pv_exception_applied is False


def test_pv_exception_with_other_failures_still_unacceptable() -> None:
    """PV infeasibility + other failures → unacceptable (single verdict, not double-counted)."""
    payload = {
        "n_late_customers": 10,  # > 3, fails SCHEDULE
        "diff": {
            "feasibility": {"became_infeasible": True},   # PV fails
            "objective": {"delta_percent": 30.0},          # OBJ fails
        },
    }
    result = ev.evaluate_plan(payload, perturbation_type="OC_1")
    assert result.verdict == "unacceptable"
    assert result.pv_exception_applied is True
    # PV failure is present in failing_dimensions
    assert "feasibility" in result.failing_dimensions


# ---------------------------------------------------------------------------
# Standard aggregation cases
# ---------------------------------------------------------------------------


def test_all_pass_is_acceptable() -> None:
    result = ev.evaluate_plan(_acceptable_payload(), perturbation_type="OC_1")
    assert result.verdict == "acceptable"
    assert result.pv_exception_applied is False
    assert result.failing_dimensions == []


def test_multi_non_pv_failure_is_unacceptable() -> None:
    """Two or more non-PV checks fail → unacceptable, no PV exception."""
    result = ev.evaluate_plan(
        _multi_failure_no_pv_payload(), perturbation_type="OC_1"
    )
    assert result.verdict == "unacceptable"
    assert result.pv_exception_applied is False
    assert len(result.failing_dimensions) >= 2


def test_empty_payload_returns_acceptable_with_no_checks() -> None:
    """No checkable metrics → acceptable (degenerate but documented)."""
    result = ev.evaluate_plan({}, perturbation_type=None)
    assert result.verdict == "acceptable"
    assert result.checks == []


# ---------------------------------------------------------------------------
# Dimension-specific evaluation
# ---------------------------------------------------------------------------


def test_dimension_lateness_pass() -> None:
    result = ev.evaluate_dimension(
        {"n_late_customers": 0}, perturbation_type=None, dimension="lateness"
    )
    assert result.verdict == "acceptable"


def test_dimension_lateness_fail() -> None:
    result = ev.evaluate_dimension(
        {"n_late_customers": 10}, perturbation_type=None, dimension="lateness"
    )
    assert result.verdict == "needs_review"


def test_dimension_pv_failure_escalates_to_unacceptable() -> None:
    """PV exception applies to single-dimension PV queries too."""
    result = ev.evaluate_dimension(
        {"diff": {"feasibility": {"became_infeasible": True}}},
        perturbation_type=None,
        dimension="feasibility",
    )
    assert result.verdict == "unacceptable"
    assert result.pv_exception_applied is True


def test_dimension_objective_per_perturbation_threshold() -> None:
    # OC threshold = 15%; observe 10% → acceptable
    payload = {"diff": {"objective": {"delta_percent": 10.0}}}
    result = ev.evaluate_dimension(payload, "OC_1", "objective")
    assert result.verdict == "acceptable"
    # OC threshold = 15%; observe 20% → needs_review (non-PV single failure)
    payload = {"diff": {"objective": {"delta_percent": 20.0}}}
    result = ev.evaluate_dimension(payload, "OC_1", "objective")
    assert result.verdict == "needs_review"


# ---------------------------------------------------------------------------
# Conservative bias band
# ---------------------------------------------------------------------------


def test_conservative_bias_band_lateness() -> None:
    """SCHEDULE late=3 (= threshold, in band) should fail check and set bias flag."""
    payload = {"n_late_customers": 3}
    result = ev.evaluate_dimension(payload, None, "lateness")
    # The single-check verdict should be needs_review with bias flagged
    assert result.verdict == "needs_review"
    assert result.conservative_bias_applied is True


def test_pv_no_conservative_bias_band() -> None:
    """PV is a categorical gate; no bias band applies."""
    payload = {"diff": {"feasibility": {"became_infeasible": False}}}
    result = ev.evaluate_dimension(payload, None, "feasibility")
    assert result.verdict == "acceptable"
    assert result.conservative_bias_applied is False


# ---------------------------------------------------------------------------
# Detect dimension
# ---------------------------------------------------------------------------


def test_detect_dimension_lateness() -> None:
    assert ev.detect_dimension("Is the lateness OK?") == "lateness"


def test_detect_dimension_objective() -> None:
    assert ev.detect_dimension("Is the cost change acceptable?") == "objective"


def test_detect_dimension_feasibility() -> None:
    assert ev.detect_dimension("Are we still feasible?") == "feasibility"


def test_detect_dimension_none_for_general_query() -> None:
    assert ev.detect_dimension("Is this plan acceptable?") is None

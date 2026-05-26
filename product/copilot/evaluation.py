"""A-008 — Plan acceptability evaluation against documented thresholds.

Translates observed payload metrics into operator-facing verdicts
(``acceptable`` / ``needs_review`` / ``unacceptable``) backed by the
per-family, per-perturbation thresholds defined in
``product.copilot.thresholds`` and rationale-documented in
``docs/threshold_rationale.md``.

Aggregation rule (general "is this plan acceptable?" queries):
1. All checks pass → ``acceptable``
2. Exactly one non-PV check fails → ``needs_review``
3. PV-feasibility check fails (regardless of other checks) →
   ``unacceptable`` (the **PV exception**, see
   docs/threshold_rationale.md#multi-family-aggregation-rule)
4. Two or more non-PV checks fail → ``unacceptable``

Dimension-specific queries ("is the lateness OK?") run only the
relevant family check. They cannot escalate to ``unacceptable`` unless
the PV exception fires.

Conservative bias: when an observed value falls within ±10% of its
threshold, the check is marked ``passes=False`` with
``conservative_bias_applied=True`` — biases borderline cases toward
``needs_review`` rather than ``acceptable``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from product.copilot.thresholds import (
    CONSERVATIVE_BIAS_BAND,
    FamilyThreshold,
    OBJ_THRESHOLDS_BY_PERT,
    PV_FEASIBILITY_STRICT,
    SCHEDULE_LATE_CUSTOMERS_MAX,
    STRUCT_ROUTES_MODIFIED_PCT_MAX,
    normalize_perturbation_prefix,
)


Verdict = Literal["acceptable", "needs_review", "unacceptable"]


@dataclass(frozen=True)
class ThresholdCheck:
    """One threshold check result.

    Attributes
    ----------
    threshold : FamilyThreshold
        The check definition.
    observed_value : Any
        The value pulled from the payload.
    passes : bool
        True when the observed value satisfies the threshold AND is
        outside the conservative bias band (for soft thresholds).
        For PV's strict threshold, passes=False iff
        ``became_infeasible=True``.
    margin_pct : Optional[float]
        Signed percent margin to the threshold. Positive = within
        threshold; negative = exceeded. None for strict (binary)
        thresholds.
    conservative_bias_applied : bool
        True when the value would have passed strictly but fell in the
        ±10% bias band; the check is marked ``passes=False``.
    rationale_skipped : bool
        True when the relevant payload field was missing so the check
        was skipped (e.g. evaluating a SCHEDULE threshold on an
        OBJ-only payload).
    """

    threshold: FamilyThreshold
    observed_value: Any
    passes: bool
    margin_pct: Optional[float] = None
    conservative_bias_applied: bool = False
    rationale_skipped: bool = False


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregated verdict across one or more threshold checks.

    ``pv_exception_applied`` is True when the PV-feasibility check
    failed and the verdict was escalated to ``unacceptable`` regardless
    of how many other checks failed. This is the documented PV
    exception (see docs/threshold_rationale.md#multi-family-aggregation-rule).
    """

    verdict: Verdict
    checks: list[ThresholdCheck]
    failing_dimensions: list[str]
    conservative_bias_applied: bool
    pv_exception_applied: bool


# ---------------------------------------------------------------------------
# Per-family check runners
# ---------------------------------------------------------------------------


def _check_schedule_late(payload: dict) -> Optional[ThresholdCheck]:
    """SCHEDULE late_customers_max check.

    Returns None when the payload lacks ``n_late_customers``.
    """
    n_late = payload.get("n_late_customers")
    if n_late is None:
        return ThresholdCheck(
            threshold=SCHEDULE_LATE_CUSTOMERS_MAX,
            observed_value=None,
            passes=False,
            margin_pct=None,
            conservative_bias_applied=False,
            rationale_skipped=True,
        )
    threshold = SCHEDULE_LATE_CUSTOMERS_MAX.threshold_value
    n_late = int(n_late)
    # Conservative bias band: ±10% of threshold. Any value within the
    # band fails the check with bias_applied=True, regardless of
    # strict-pass direction (the band biases verdicts toward review).
    band_lo = threshold * (1 - CONSERVATIVE_BIAS_BAND)
    band_hi = threshold * (1 + CONSERVATIVE_BIAS_BAND)
    strictly_passes = n_late < threshold
    in_band = band_lo <= n_late <= band_hi
    passes = strictly_passes and not in_band
    bias_applied = in_band
    margin_pct = ((threshold - n_late) / threshold * 100.0) if threshold else None
    return ThresholdCheck(
        threshold=SCHEDULE_LATE_CUSTOMERS_MAX,
        observed_value=n_late,
        passes=passes,
        margin_pct=margin_pct,
        conservative_bias_applied=bias_applied,
    )


def _check_obj_delta(
    payload: dict, perturbation_type: Optional[str]
) -> Optional[ThresholdCheck]:
    """OBJ relative-delta check (per-perturbation threshold)."""
    diff = payload.get("diff") or {}
    obj_diff = diff.get("objective") or {}
    delta_pct_raw = obj_diff.get("delta_percent")
    if delta_pct_raw is None:
        # Skip: no diff to evaluate
        prefix = normalize_perturbation_prefix(perturbation_type) or "OC"
        threshold_def = OBJ_THRESHOLDS_BY_PERT.get(prefix, OBJ_THRESHOLDS_BY_PERT["OC"])
        return ThresholdCheck(
            threshold=threshold_def,
            observed_value=None,
            passes=False,
            margin_pct=None,
            conservative_bias_applied=False,
            rationale_skipped=True,
        )
    prefix = normalize_perturbation_prefix(perturbation_type)
    if prefix is None:
        return None  # no per-pert threshold; skip
    threshold_def = OBJ_THRESHOLDS_BY_PERT.get(prefix)
    if threshold_def is None:
        return None
    threshold = float(threshold_def.threshold_value)
    observed_abs = abs(float(delta_pct_raw)) / 100.0  # delta_percent stored as %, convert to fraction
    band_lo = threshold * (1 - CONSERVATIVE_BIAS_BAND)
    band_hi = threshold * (1 + CONSERVATIVE_BIAS_BAND)
    strictly_passes = observed_abs < threshold
    in_band = band_lo <= observed_abs <= band_hi
    passes = strictly_passes and not in_band
    bias_applied = in_band
    margin_pct = (threshold - observed_abs) / threshold * 100.0 if threshold else None
    return ThresholdCheck(
        threshold=threshold_def,
        observed_value=round(float(delta_pct_raw), 2),
        passes=passes,
        margin_pct=margin_pct,
        conservative_bias_applied=bias_applied,
    )


def _check_pv_feasibility(payload: dict) -> Optional[ThresholdCheck]:
    """PV strict feasibility check.

    PV is binary: ``became_infeasible=True`` fails the check
    categorically. No conservative bias band (the gate is categorical,
    not numeric).
    """
    diff = payload.get("diff") or {}
    feas = diff.get("feasibility") or {}
    became_inf = feas.get("became_infeasible")
    if became_inf is None:
        return ThresholdCheck(
            threshold=PV_FEASIBILITY_STRICT,
            observed_value=None,
            passes=False,
            margin_pct=None,
            conservative_bias_applied=False,
            rationale_skipped=True,
        )
    passes = (became_inf is False)
    return ThresholdCheck(
        threshold=PV_FEASIBILITY_STRICT,
        observed_value=bool(became_inf),
        passes=passes,
        margin_pct=None,
        conservative_bias_applied=False,
    )


def _check_struct_routes_modified(payload: dict) -> Optional[ThresholdCheck]:
    """STRUCT routes_modified_pct check."""
    diff = payload.get("diff") or {}
    routes_diff = diff.get("routes") or {}
    added = routes_diff.get("added") or []
    removed = routes_diff.get("removed") or []
    modified = routes_diff.get("modified") or []
    if not isinstance(added, list) and not isinstance(removed, list) and not isinstance(modified, list):
        return ThresholdCheck(
            threshold=STRUCT_ROUTES_MODIFIED_PCT_MAX,
            observed_value=None,
            passes=False,
            margin_pct=None,
            conservative_bias_applied=False,
            rationale_skipped=True,
        )
    total = (
        payload.get("n_routes")
        or len(payload.get("routes") or [])
    )
    if not total:
        return ThresholdCheck(
            threshold=STRUCT_ROUTES_MODIFIED_PCT_MAX,
            observed_value=None,
            passes=False,
            margin_pct=None,
            conservative_bias_applied=False,
            rationale_skipped=True,
        )
    n_changed = (
        (len(added) if isinstance(added, list) else 0)
        + (len(removed) if isinstance(removed, list) else 0)
        + (len(modified) if isinstance(modified, list) else 0)
    )
    pct = n_changed / total
    threshold = float(STRUCT_ROUTES_MODIFIED_PCT_MAX.threshold_value)
    band_lo = threshold * (1 - CONSERVATIVE_BIAS_BAND)
    band_hi = threshold * (1 + CONSERVATIVE_BIAS_BAND)
    strictly_passes = pct < threshold
    in_band = band_lo <= pct <= band_hi
    passes = strictly_passes and not in_band
    bias_applied = in_band
    margin_pct = (threshold - pct) / threshold * 100.0 if threshold else None
    return ThresholdCheck(
        threshold=STRUCT_ROUTES_MODIFIED_PCT_MAX,
        observed_value=round(pct, 4),
        passes=passes,
        margin_pct=margin_pct,
        conservative_bias_applied=bias_applied,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_DIMENSION_TO_CHECK = {
    "lateness": _check_schedule_late,
    "schedule": _check_schedule_late,
    "objective": _check_obj_delta,
    "cost": _check_obj_delta,
    "feasibility": _check_pv_feasibility,
    "pv": _check_pv_feasibility,
    "structure": _check_struct_routes_modified,
    "routes": _check_struct_routes_modified,
    "struct": _check_struct_routes_modified,
}


def _all_applicable_checks(
    payload: dict, perturbation_type: Optional[str]
) -> list[ThresholdCheck]:
    """Run every check whose required field is present in the payload."""
    checks: list[ThresholdCheck] = []
    for runner in (
        _check_schedule_late,
        _check_pv_feasibility,
        _check_struct_routes_modified,
    ):
        check = runner(payload)
        if check is not None and not check.rationale_skipped:
            checks.append(check)
    obj_check = _check_obj_delta(payload, perturbation_type)
    if obj_check is not None and not obj_check.rationale_skipped:
        checks.append(obj_check)
    return checks


def _resolve_verdict(checks: list[ThresholdCheck]) -> EvaluationResult:
    """Apply the aggregation rule including the PV exception.

    See docs/threshold_rationale.md#multi-family-aggregation-rule.
    """
    failed = [c for c in checks if not c.passes]
    failing_dimensions = [c.threshold.metric for c in failed]
    bias_applied = any(c.conservative_bias_applied for c in checks)

    pv_failed = any(
        c.threshold.family == "PLAN_VALIDITY"
        and c.threshold.metric == "feasibility"
        and not c.passes
        for c in checks
    )
    if pv_failed:
        return EvaluationResult(
            verdict="unacceptable",
            checks=checks,
            failing_dimensions=failing_dimensions,
            conservative_bias_applied=bias_applied,
            pv_exception_applied=True,
        )

    if not failed:
        verdict: Verdict = "acceptable"
    elif len(failed) == 1:
        verdict = "needs_review"
    else:
        verdict = "unacceptable"

    return EvaluationResult(
        verdict=verdict,
        checks=checks,
        failing_dimensions=failing_dimensions,
        conservative_bias_applied=bias_applied,
        pv_exception_applied=False,
    )


def evaluate_plan(
    payload: dict,
    perturbation_type: Optional[str],
) -> EvaluationResult:
    """General "is this plan acceptable?" — run every applicable check.

    The PV exception escalates a failed PV-feasibility check to
    ``unacceptable`` regardless of other check outcomes. See
    docs/threshold_rationale.md#multi-family-aggregation-rule.
    """
    checks = _all_applicable_checks(payload, perturbation_type)
    if not checks:
        # Nothing checkable — return acceptable-with-skipped
        return EvaluationResult(
            verdict="acceptable",
            checks=[],
            failing_dimensions=[],
            conservative_bias_applied=False,
            pv_exception_applied=False,
        )
    return _resolve_verdict(checks)


def evaluate_dimension(
    payload: dict,
    perturbation_type: Optional[str],
    dimension: str,
) -> EvaluationResult:
    """Dimension-specific "is the lateness OK?" / "is the cost increase acceptable?".

    Single-dimension queries can still escalate to ``unacceptable``
    via the PV exception (when the dimension is feasibility/PV).
    """
    runner = _DIMENSION_TO_CHECK.get(dimension.lower())
    if runner is None:
        return EvaluationResult(
            verdict="acceptable",
            checks=[],
            failing_dimensions=[],
            conservative_bias_applied=False,
            pv_exception_applied=False,
        )
    if runner is _check_obj_delta:
        check = runner(payload, perturbation_type)
    else:
        check = runner(payload)
    if check is None or check.rationale_skipped:
        return EvaluationResult(
            verdict="acceptable",
            checks=[],
            failing_dimensions=[],
            conservative_bias_applied=False,
            pv_exception_applied=False,
        )
    return _resolve_verdict([check])


# Map prompt language to dimension keyword
_DIMENSION_KEYWORDS = {
    "lateness": ("late", "lateness", "delay", "tardy"),
    "objective": ("cost", "objective", "expensive", "savings"),
    "feasibility": ("feasible", "feasibility", "infeasible", "unserved"),
    "structure": ("routes", "vehicles", "structure"),
}


def detect_dimension(prompt: str) -> Optional[str]:
    """Pick the dimension keyword a prompt asks about (or None if general)."""
    if not prompt:
        return None
    p = prompt.lower()
    for dim, keywords in _DIMENSION_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return dim
    return None


__all__ = [
    "Verdict",
    "ThresholdCheck",
    "EvaluationResult",
    "evaluate_plan",
    "evaluate_dimension",
    "detect_dimension",
]

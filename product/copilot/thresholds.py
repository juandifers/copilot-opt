"""Per-family, per-perturbation thresholds for the B2 evaluation layer.

Every threshold below is documented in ``docs/threshold_rationale.md``
under the cited rationale_ref. The values are deliberately mid-tier
defaults; a production deployment would calibrate per operational
context. The thesis defends the structure (per-family,
per-perturbation, PV-categorical, conservative-bias-on-borderline),
not the specific numbers.

Conservative bias band: ±10% of the threshold value. When an observed
value falls within the band, the check is marked ``passes=False`` with
``conservative_bias_applied=True``. The bias biases verdicts toward
``needs_review`` rather than ``acceptable`` for borderline cases — the
operator-safety direction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


# Conservative bias band (±10% of threshold value)
CONSERVATIVE_BIAS_BAND = 0.10


@dataclass(frozen=True)
class FamilyThreshold:
    """One threshold check definition.

    Attributes
    ----------
    family : str
        Payload family this threshold applies to: SCHEDULE / OBJ /
        PLAN_VALIDITY / STRUCT. (PV is written as PLAN_VALIDITY for
        consistency with the registry; both forms are accepted.)
    metric : str
        Logical field name that gets checked (e.g. ``"late_customers_count"``,
        ``"objective_relative_delta"``, ``"feasibility"``,
        ``"routes_modified_pct"``).
    threshold_value : Any
        The cutoff value. Numeric for soft thresholds; ``"strict"`` for
        the PV-feasibility categorical gate.
    perturbation_type : Optional[str]
        When set, the threshold is OBJ-style perturbation-specific and
        only applies when the scenario's perturbation matches.
    rationale_ref : str
        Anchor in ``docs/threshold_rationale.md``; used in evidence
        items so reviewers can trace each judgment to its rationale.
    """

    family: str
    metric: str
    threshold_value: Any
    perturbation_type: Optional[str]
    rationale_ref: str


# ---------------------------------------------------------------------------
# Concrete thresholds (values per docs/threshold_rationale.md)
# ---------------------------------------------------------------------------

SCHEDULE_LATE_CUSTOMERS_MAX = FamilyThreshold(
    family="SCHEDULE",
    metric="late_customers_count",
    threshold_value=3,
    perturbation_type=None,
    rationale_ref="docs/threshold_rationale.md#schedule-late_customers_max",
)

OBJ_OC_DELTA_MAX = FamilyThreshold(
    family="OBJ",
    metric="objective_relative_delta",
    threshold_value=0.15,
    perturbation_type="OC",
    rationale_ref="docs/threshold_rationale.md#oc-order_change-15",
)

OBJ_TT_DELTA_MAX = FamilyThreshold(
    family="OBJ",
    metric="objective_relative_delta",
    threshold_value=0.20,
    perturbation_type="TT",
    rationale_ref="docs/threshold_rationale.md#tt-travel_time-20",
)

OBJ_ST_DELTA_MAX = FamilyThreshold(
    family="OBJ",
    metric="objective_relative_delta",
    threshold_value=0.10,
    perturbation_type="ST",
    rationale_ref="docs/threshold_rationale.md#st-service_time-10",
)

OBJ_TW_DELTA_MAX = FamilyThreshold(
    family="OBJ",
    metric="objective_relative_delta",
    threshold_value=0.10,
    perturbation_type="TW",
    rationale_ref="docs/threshold_rationale.md#tw-time_window-10",
)

PV_FEASIBILITY_STRICT = FamilyThreshold(
    family="PLAN_VALIDITY",
    metric="feasibility",
    threshold_value="strict",
    perturbation_type=None,
    rationale_ref="docs/threshold_rationale.md#pv-feasibility",
)

STRUCT_ROUTES_MODIFIED_PCT_MAX = FamilyThreshold(
    family="STRUCT",
    metric="routes_modified_pct",
    threshold_value=0.50,
    perturbation_type=None,
    rationale_ref="docs/threshold_rationale.md#struct-routes_modified_pct",
)


# OBJ thresholds keyed by perturbation prefix for easy lookup
OBJ_THRESHOLDS_BY_PERT: dict[str, FamilyThreshold] = {
    "OC": OBJ_OC_DELTA_MAX,
    "TT": OBJ_TT_DELTA_MAX,
    "ST": OBJ_ST_DELTA_MAX,
    "TW": OBJ_TW_DELTA_MAX,
}


def normalize_perturbation_prefix(perturbation_id_or_type: Optional[str]) -> Optional[str]:
    """Normalize a perturbation_id (e.g. 'TT_4') to its prefix ('TT')."""
    if not perturbation_id_or_type:
        return None
    s = str(perturbation_id_or_type).upper()
    if s.startswith("OC"):
        return "OC"
    if s.startswith("TT"):
        return "TT"
    if s.startswith("ST"):
        return "ST"
    if s.startswith("TW"):
        return "TW"
    return None


__all__ = [
    "CONSERVATIVE_BIAS_BAND",
    "FamilyThreshold",
    "SCHEDULE_LATE_CUSTOMERS_MAX",
    "OBJ_OC_DELTA_MAX",
    "OBJ_TT_DELTA_MAX",
    "OBJ_ST_DELTA_MAX",
    "OBJ_TW_DELTA_MAX",
    "PV_FEASIBILITY_STRICT",
    "STRUCT_ROUTES_MODIFIED_PCT_MAX",
    "OBJ_THRESHOLDS_BY_PERT",
    "normalize_perturbation_prefix",
]

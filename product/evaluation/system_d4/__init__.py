"""System D4 — Compute Decision / Recompute Policy Layer.

D4 sits after the D3 answerability/warning pipeline and enriches the
copilot response with a ``compute_decision`` object that tells the
frontend/operator whether the current payload is sufficient, or whether
a comparison payload, a cheap recomputation, or a solver escalation is
required.

D4 is the contract layer only — it never runs a solver, never trains a
model, and never modifies the locked Run 2 artifacts. The deployable
action ladder is intentionally limited to::

    run_reuse_direct
    run_nearest_neighbor
    run_clarke_wright
    run_pyvrp_10s

``pyvrp_60s`` is the historical reference-generation action from the
benchmark and is NOT exposed by D4 as a deployable choice.
"""
from __future__ import annotations

from product.evaluation.system_d4.compute_decision import (
    ALL_ACTIONS,
    ALL_MODES,
    ALL_QUERY_FAMILIES,
    ComputeDecision,
    ComputeMode,
    DEPLOYABLE_RECOMPUTE_ACTIONS,
    POLICY_SOURCE,
    QueryFamily,
    RecommendedAction,
    decide_compute,
    extract_available_fields,
    intent_to_query_family,
)
from product.evaluation.system_d4.d4_system_c import (
    PredictedContractD4,
    run_system_d4_on_case,
    run_system_d4_on_materialized,
)

__all__ = [
    "ALL_ACTIONS",
    "ALL_MODES",
    "ALL_QUERY_FAMILIES",
    "ComputeDecision",
    "ComputeMode",
    "DEPLOYABLE_RECOMPUTE_ACTIONS",
    "POLICY_SOURCE",
    "QueryFamily",
    "RecommendedAction",
    "decide_compute",
    "extract_available_fields",
    "intent_to_query_family",
    "PredictedContractD4",
    "run_system_d4_on_case",
    "run_system_d4_on_materialized",
]

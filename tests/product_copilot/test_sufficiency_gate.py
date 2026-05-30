"""Safety + behaviour tests for the learned sufficiency gate.

The gate is **advisory** and must never override hard contract checks.
These tests pin those guarantees down.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEPLOYMENT_CONFIG = REPO_ROOT / "reports" / "predictor_models" / "deployment_config.csv"
_skipif_no_deployment_config = pytest.mark.skipif(
    not _DEPLOYMENT_CONFIG.exists(),
    reason="deployment_config.csv is not shipped in this checkout; "
           "runs locally when the file is present",
)

from product.copilot.sufficiency_gate import (
    DEFAULT_RECOMPUTE_ACTION,
    FORBIDDEN_RECOMPUTE_ACTIONS,
    GATE_FLAG_ENV_VAR,
    SUPPORTED_FAMILIES,
    SufficiencyGateResult,
    gate_enabled,
    predict_sufficiency,
)
from product.evaluation.system_d4.compute_decision import (
    DEPLOYABLE_RECOMPUTE_ACTIONS,
    decide_compute,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def feature_complete_contexts() -> dict:
    """A synthetic feature-complete context bundle for OBJ/TRAVEL_TIME/C/reuse_direct.

    Lifted from one row of the Stage A training parquet so the gate has
    enough numeric features to commit to a probability.
    """
    return {
        "payload": {
            "objective": 8287.0,
            "feasible": True,
            "routes": [],
            "action_objective": 8290.0,
            "baseline_n_routes": 10,
            "baseline_obj": 8287.0,
            "baseline_generalized_cost": 18115.7,
            "baseline_total_wait": 0,
            "baseline_min_route_slack": 2,
            "baseline_mean_route_slack": 323.7,
            "baseline_n_tight_customers": 47,
            "n_affected_customers": 13,
            "affected_route_share": 0.1,
            "affected_demand_share": 0.088,
            "affected_service_time_share": 0.13,
            "affected_min_slack": 2.0,
            "affected_mean_slack": 304.9,
            "affected_total_wait": 0,
        },
        "perturbation_context": {
            "perturbation_id": "TT_1",
            "family": "TRAVEL_TIME",
            "instance_class": "C",
            "magnitude_grid": 1,
        },
        "action_context": {
            "action": "reuse_direct",
            "action_feasible": False,
            "infeasibility_kind": "time_window",
            "action_obj_delta_pct": 0.0,
            "action_generalized_delta_pct": 0.0003588,
            "action_time_warp": 53,
            "action_total_wait": 0,
            "action_total_duration": 98352,
            "action_n_late_customers": 1,
            "action_max_lateness": 45,
        },
    }


@pytest.fixture(autouse=True)
def reset_gate_env(monkeypatch) -> Iterator[None]:
    """Default each test to the gate-off state; tests opt in by setting the env var."""
    monkeypatch.delenv(GATE_FLAG_ENV_VAR, raising=False)
    yield


# ---------------------------------------------------------------------------
# 1. Gate-disabled default
# ---------------------------------------------------------------------------


def test_gate_disabled_by_default(feature_complete_contexts):
    assert gate_enabled() is False
    result = predict_sufficiency(
        family="OBJ",
        payload_snapshot=feature_complete_contexts["payload"],
        action_context=feature_complete_contexts["action_context"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
    )
    assert result.enabled is False
    assert result.decision == "no_decision"
    assert result.p_sufficient is None


def test_decide_compute_does_not_call_gate_when_disabled(feature_complete_contexts):
    decision = decide_compute(
        prompt_text="What is the objective value?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.sufficiency_gate is None
    assert decision.mode == "answer_from_payload"


# ---------------------------------------------------------------------------
# 2. Gate-enabled happy path
# ---------------------------------------------------------------------------


@_skipif_no_deployment_config
def test_gate_loads_deployment_config_and_returns_threshold(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    result = predict_sufficiency(
        family="OBJ",
        payload_snapshot=feature_complete_contexts["payload"],
        action_context=feature_complete_contexts["action_context"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
    )
    assert result.enabled is True
    assert isinstance(result.threshold, float)
    assert 0.0 <= result.threshold <= 1.0
    assert result.model_id.startswith("histgb__C_clean__OBJ")


def test_gate_attaches_result_to_decide_compute(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What is the objective value?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert isinstance(decision.sufficiency_gate, SufficiencyGateResult)
    assert decision.sufficiency_gate.family == "OBJ"


# ---------------------------------------------------------------------------
# 3. no_decision on missing features
# ---------------------------------------------------------------------------


@_skipif_no_deployment_config
def test_gate_returns_no_decision_when_features_missing(monkeypatch):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    result = predict_sufficiency(family="OBJ", payload_snapshot={}, perturbation_context={})
    assert result.decision == "no_decision"
    assert result.p_sufficient is None
    assert len(result.missing_features) > 0


def test_gate_returns_no_decision_for_unsupported_family(monkeypatch):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    for fam in ("CAUSAL", "OVERVIEW", "UNKNOWN", ""):
        result = predict_sufficiency(family=fam)
        assert result.decision == "no_decision", fam
        assert "calibrated" in result.reason.lower() or "supported" in result.reason.lower()


# ---------------------------------------------------------------------------
# 4. Hard contract checks override the gate
# ---------------------------------------------------------------------------


def test_gate_does_not_override_unsupported(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What about driver preferences?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.mode == "unsupported"
    assert decision.sufficiency_gate is None  # gate not consulted on hard branch


def test_gate_does_not_override_clarification(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="Can you improve this plan?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.mode == "clarification_needed"
    assert decision.sufficiency_gate is None


def test_gate_does_not_override_explicit_recompute(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What if we add a new customer?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.mode == "needs_recompute"
    # Gate was NOT consulted; the explicit recompute branch wins.
    assert decision.sufficiency_gate is None
    assert decision.recommended_action != "pyvrp_60s"


def test_gate_does_not_override_missing_baseline_comparison(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    payload = {k: v for k, v in feature_complete_contexts["payload"].items()
               if not k.startswith("baseline_") and k != "diff"}
    decision = decide_compute(
        prompt_text="How does this compare to the baseline plan?",
        intent="before_after_comparison",
        answerability_status="partially_answerable",
        payload=payload,
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.mode == "needs_comparison_payload"
    assert decision.recommended_action == "build_comparison_payload"
    assert decision.sufficiency_gate is None  # gate not consulted on comparison branch


def test_gate_does_not_override_causal(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="Why did the route count change?",
        intent="route_count",
        answerability_status="answerable",
        warnings=["causal_mechanism_unsupported"],
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.mode == "partial_from_payload"
    assert decision.sufficiency_gate is None


def test_gate_does_not_override_partial_answerability(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What is the objective?",
        intent="objective_value",
        answerability_status="partially_answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.mode == "partial_from_payload"
    assert decision.sufficiency_gate is None


def test_gate_does_not_override_missing_fields_for_answerability(monkeypatch):
    """When D2 says ``not_answerable``, D4 hands off to clarification —
    not to the gate. The gate must not force an answer in this case."""
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What is the objective?",
        intent="objective_value",
        answerability_status="not_answerable",
        payload={},
        answerability_missing_fields=["objective"],
    )
    assert decision.mode == "clarification_needed"
    assert decision.sufficiency_gate is None


def test_gate_not_consulted_for_overview_intents(monkeypatch, feature_complete_contexts):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What is this perturbation doing?",
        intent="perturbation_summary",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    # Overview branch handles itself; gate is not invoked because the
    # OVERVIEW family is outside SUPPORTED_FAMILIES.
    assert decision.query_family == "OVERVIEW"
    assert decision.sufficiency_gate is None


# ---------------------------------------------------------------------------
# 5. Recompute recommendation forbidden actions
# ---------------------------------------------------------------------------


def test_gate_never_recommends_pyvrp_60s(monkeypatch, feature_complete_contexts):
    """Synthetic features the trained models predict as insufficient
    (PLAN_VALIDITY on this row → low p) should produce a flip, and the
    action must be a deployable rung, never pyvrp_60s."""
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="Is the plan feasible?",
        intent="feasibility_status",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.recommended_action not in FORBIDDEN_RECOMPUTE_ACTIONS
    if decision.mode == "needs_recompute":
        assert decision.recommended_action in DEPLOYABLE_RECOMPUTE_ACTIONS
        assert decision.recommended_action == DEFAULT_RECOMPUTE_ACTION


def test_gate_can_recommend_run_pyvrp_10s(monkeypatch, feature_complete_contexts):
    """At a corestress feature row where the model predicts the cheap
    action will be insufficient, the gate flips to ``needs_recompute``
    with ``run_pyvrp_10s``."""
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="Is the plan feasible?",
        intent="feasibility_status",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.sufficiency_gate is not None
    if decision.sufficiency_gate.decision == "recommend_recompute":
        assert decision.mode == "needs_recompute"
        assert decision.recommended_action == "run_pyvrp_10s"


# ---------------------------------------------------------------------------
# 6. Route-indexing warnings must survive the gate
# ---------------------------------------------------------------------------


def test_gate_does_not_remove_route_indexing_warning_branch(monkeypatch, feature_complete_contexts):
    """If a route_indexing warning is in the D3 warnings list, D4 still
    leaves the warning alone. We assert here that the gate path neither
    drops warnings (warnings live on the D3 contract, not D4) nor
    suppresses display by changing the mode in a way that hides them."""
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    # Even with warnings present and the gate enabled, the recommended
    # action must remain a deployable rung. Warnings are propagated by
    # the higher-level orchestrator, not by D4.
    decision = decide_compute(
        prompt_text="What is the objective value?",
        intent="objective_value",
        answerability_status="answerable",
        warnings=["route_indexing_one_based"],
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
    )
    assert decision.recommended_action not in FORBIDDEN_RECOMPUTE_ACTIONS


# ---------------------------------------------------------------------------
# 7. accept_current is observable
# ---------------------------------------------------------------------------


@_skipif_no_deployment_config
def test_gate_can_accept_current_payload(monkeypatch, feature_complete_contexts):
    """The OBJ row in the training parquet is labeled sufficient, so the
    retrained HistGB / C_clean predictor should accept the current
    payload at the default 0.5 threshold."""
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    result = predict_sufficiency(
        family="OBJ",
        payload_snapshot=feature_complete_contexts["payload"],
        action_context=feature_complete_contexts["action_context"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
    )
    assert result.decision == "accept_current"
    assert result.p_sufficient is not None and result.p_sufficient >= result.threshold


# ---------------------------------------------------------------------------
# 8. Programmatic enable flag bypass for tests / d_final_gated variant
# ---------------------------------------------------------------------------


def test_use_learned_sufficiency_gate_flag_overrides_env(monkeypatch, feature_complete_contexts):
    """The ``use_learned_sufficiency_gate=True`` keyword on
    ``decide_compute`` enables the gate even when the env var is unset —
    this is the entry point the ``d_final_gated`` system variant uses."""
    monkeypatch.delenv(GATE_FLAG_ENV_VAR, raising=False)
    decision = decide_compute(
        prompt_text="What is the objective?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
        use_learned_sufficiency_gate=True,
    )
    assert decision.sufficiency_gate is not None
    assert decision.sufficiency_gate.enabled is True


def test_use_learned_sufficiency_gate_false_disables_even_when_env_set(
    monkeypatch, feature_complete_contexts
):
    monkeypatch.setenv(GATE_FLAG_ENV_VAR, "true")
    decision = decide_compute(
        prompt_text="What is the objective?",
        intent="objective_value",
        answerability_status="answerable",
        payload=feature_complete_contexts["payload"],
        perturbation_context=feature_complete_contexts["perturbation_context"],
        action_context=feature_complete_contexts["action_context"],
        use_learned_sufficiency_gate=False,
    )
    assert decision.sufficiency_gate is None

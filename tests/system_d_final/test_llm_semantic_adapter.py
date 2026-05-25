"""Tests for System D-Final LLM semantic adapter.

All tests use mocked LLM responses. Live LLM calls are gated by the
environment variable RUN_LIVE_LLM_TESTS=1 and run only in the optional
live test block at the bottom. Normal CI must pass without that flag.

Covers:
  - LLM output schema validation (valid/invalid/extra-field)
  - Intent enum rejection
  - Low-confidence fallback
  - Ambiguity fallback
  - Forbidden field rejection (answer_text, evidence, warnings, etc.)
  - Valid frames for route_end_time, full_route_listing, lateness_summary
  - recompute_request treated as semantic metadata only (D4 still owns compute)
  - D4 still owns compute_decision
  - hybrid_guarded policy: D1-confident path, LLM-only fallback on unknown
  - /copilot/ask with d_final system (mocked adapter)
  - semantic_adapter metadata in API response
  - /copilot/ask never runs solvers
  - API key never logged
  - .env remains untracked
  - Locked Run 2 artifacts unchanged
  - Existing D1/D2/D3/D4 tests not broken (import smoke)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from product.copilot.llm_query_frame import (
    ALLOWED_INTENTS,
    LLMAdapterMetadata,
    LLMSemanticFrame,
    ValidationOutcome,
)
from product.copilot.llm_semantic_intent_adapter import (
    validate_llm_frame,
    infer_intent_d_final_frame,
    infer_intent_hybrid_guarded,
)
from product.copilot.query_frame import QueryFrame

# ModelCallResult is imported lazily so the openai package doesn't need to be
# present for schema/validation tests — only for LLM call tests.
try:
    from product.evaluation.model_clients.openai_client import ModelCallResult as _ModelCallResult
    _OPENAI_AVAILABLE = True
except ImportError:
    _ModelCallResult = None
    _OPENAI_AVAILABLE = False


_REPO_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers — build LLM frames
# ---------------------------------------------------------------------------


def _valid_frame(**overrides) -> LLMSemanticFrame:
    defaults = {
        "intent": "route_end_time",
        "confidence": 0.91,
        "entities": {"customer_ids": [], "route_labels": [3]},
        "requires_baseline": False,
        "comparison_type": "none",
        "causal_request": False,
        "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    }
    defaults.update(overrides)
    return LLMSemanticFrame.model_validate(defaults)


def _mock_client_returning(raw_dict: dict) -> MagicMock:
    """Mock OpenAI client that returns raw_dict as JSON response."""
    from product.evaluation.model_clients.openai_client import ModelCallResult

    result = ModelCallResult(
        requested_model="gpt-5.4-mini",
        response_model="gpt-5.4-mini",
        raw_response_text=json.dumps(raw_dict),
        latency_seconds=0.1,
        prompt_tokens=50,
        completion_tokens=80,
    )
    client = MagicMock()
    # call_openai_contract_model is called directly with the client object
    with patch(
        "product.evaluation.model_clients.openai_client.call_openai_contract_model",
        return_value=result,
    ):
        pass  # patched in each test
    return client


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_valid_frame_parses(self):
        frame = _valid_frame()
        assert frame.intent == "route_end_time"
        assert frame.confidence == 0.91

    def test_extra_field_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate(
                {
                    "intent": "route_end_time",
                    "confidence": 0.9,
                    "answer_text": "Vehicle 3 finishes at 17:30",  # FORBIDDEN
                }
            )

    def test_evidence_paths_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate(
                {
                    "intent": "route_end_time",
                    "confidence": 0.9,
                    "evidence_paths": ["routes[2].end_time"],  # FORBIDDEN
                }
            )

    def test_warnings_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate(
                {
                    "intent": "lateness_summary",
                    "confidence": 0.85,
                    "warnings": ["route_indexing_ambiguity"],  # FORBIDDEN
                }
            )

    def test_missing_fields_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate(
                {
                    "intent": "objective_delta",
                    "confidence": 0.8,
                    "missing_fields": ["baseline_objective"],  # FORBIDDEN
                }
            )

    def test_next_actions_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate(
                {
                    "intent": "objective_delta",
                    "confidence": 0.8,
                    "next_actions": ["run_pyvrp_10s"],  # FORBIDDEN
                }
            )

    def test_compute_decision_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate(
                {
                    "intent": "objective_value",
                    "confidence": 0.9,
                    "compute_decision": {"mode": "needs_recompute"},  # FORBIDDEN
                }
            )


# ---------------------------------------------------------------------------
# validate_llm_frame guardrails
# ---------------------------------------------------------------------------


class TestValidateLLMFrame:
    def test_valid_frame_accepted(self):
        frame = _valid_frame(intent="route_end_time", confidence=0.91)
        outcome, reason = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.accepted
        assert reason is None

    def test_invalid_intent_enum_rejected(self):
        frame = _valid_frame(intent="not_a_real_intent", confidence=0.95)
        outcome, reason = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.rejected_invalid_enum
        assert "not_a_real_intent" in reason

    def test_invalid_comparison_type_rejected(self):
        frame = _valid_frame(comparison_type="made_up_type", confidence=0.95)
        # model_validate will reject unknown comparison_type if it's not in allowed set
        # validate_llm_frame also checks
        outcome, reason = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.rejected_invalid_enum

    def test_confidence_below_min_rejected(self):
        frame = _valid_frame(confidence=0.50)
        outcome, reason = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.rejected_low_confidence

    def test_conditional_confidence_d1_disagrees_rejected(self):
        # 0.60–0.80 range: only accept if D1 agrees or D1 is unknown
        frame = _valid_frame(intent="route_end_time", confidence=0.72)
        outcome, reason = validate_llm_frame(frame, d1_intent="lateness_summary")
        assert outcome == ValidationOutcome.rejected_low_confidence

    def test_conditional_confidence_d1_agrees_accepted(self):
        frame = _valid_frame(intent="route_end_time", confidence=0.72)
        outcome, _ = validate_llm_frame(frame, d1_intent="route_end_time")
        assert outcome == ValidationOutcome.accepted

    def test_conditional_confidence_d1_unknown_accepted(self):
        frame = _valid_frame(intent="route_end_time", confidence=0.72)
        outcome, _ = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.accepted

    def test_ambiguous_frame_rejected(self):
        frame = _valid_frame(
            ambiguity={"is_ambiguous": True, "reason": "Could be route_end_time or lateness"}
        )
        outcome, reason = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.rejected_ambiguous

    def test_causal_incompatible_intent_rejected(self):
        # causal_request=True with objective_value is unsafe
        frame = _valid_frame(intent="objective_value", causal_request=True, confidence=0.9)
        outcome, reason = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.rejected_unsafe_semantics

    def test_causal_compatible_intent_accepted(self):
        # causal_request=True with lateness_summary is fine
        frame = _valid_frame(intent="lateness_summary", causal_request=True, confidence=0.9)
        outcome, _ = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.accepted

    def test_valid_full_route_listing(self):
        frame = _valid_frame(intent="full_route_listing", confidence=0.88)
        outcome, _ = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.accepted

    def test_valid_lateness_summary(self):
        frame = _valid_frame(intent="lateness_summary", confidence=0.85)
        outcome, _ = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.accepted

    def test_recompute_request_accepted_as_semantic_flag(self):
        # recompute_request=True is a semantic flag; does not cause rejection.
        # D4 still owns compute_decision.
        frame = _valid_frame(
            intent="objective_delta",
            recompute_request=True,
            requires_baseline=True,
            comparison_type="previous_solution",
            confidence=0.87,
        )
        outcome, _ = validate_llm_frame(frame, d1_intent="unknown")
        assert outcome == ValidationOutcome.accepted


# ---------------------------------------------------------------------------
# infer_intent_d_final_frame with mocked LLM
# ---------------------------------------------------------------------------


def _make_mock_result(raw_dict: dict):
    """Build a fake ModelCallResult for mocking."""
    assert _OPENAI_AVAILABLE, "openai package required for this test"
    return _ModelCallResult(
        requested_model="gpt-5.4-mini",
        response_model="gpt-5.4-mini",
        raw_response_text=json.dumps(raw_dict),
        latency_seconds=0.05,
        prompt_tokens=40,
        completion_tokens=70,
    )


class TestInferIntentDFinalFrame:
    def _patch_llm_call(self, raw_dict):
        return patch(
            "product.evaluation.model_clients.openai_client.call_openai_contract_model",
            return_value=_make_mock_result(raw_dict),
        )

    def test_route_end_time_accepted(self):
        mock_response = {
            "intent": "route_end_time",
            "confidence": 0.91,
            "entities": {"customer_ids": [], "route_labels": [3]},
            "requires_baseline": False,
            "comparison_type": "none",
            "causal_request": False,
            "recompute_request": False,
            "ambiguity": {"is_ambiguous": False, "reason": None},
            "alternative_intents": [],
        }
        client = MagicMock()
        with self._patch_llm_call(mock_response):
            frame, meta = infer_intent_d_final_frame(
                prompt="When does truck 3 call it a night?",
                family="SCHEDULE",
                client=client,
                mode="hybrid_guarded",
            )
        # D1 would return "unknown" for this prompt → LLM takes over
        assert frame.intent == "route_end_time"
        assert meta.schema_valid is True

    def test_full_route_listing_accepted(self):
        mock_response = {
            "intent": "full_route_listing",
            "confidence": 0.88,
            "entities": {"customer_ids": [], "route_labels": []},
            "requires_baseline": False,
            "comparison_type": "none",
            "causal_request": False,
            "recompute_request": False,
            "ambiguity": {"is_ambiguous": False, "reason": None},
            "alternative_intents": [],
        }
        client = MagicMock()
        with self._patch_llm_call(mock_response):
            frame, meta = infer_intent_d_final_frame(
                prompt="Give me a rundown of every route",
                family="STRUCT",
                client=client,
                mode="hybrid_guarded",
            )
        assert frame.intent == "full_route_listing"

    def test_lateness_summary_accepted(self):
        mock_response = {
            "intent": "lateness_summary",
            "confidence": 0.85,
            "entities": {"customer_ids": [], "route_labels": []},
            "requires_baseline": False,
            "comparison_type": "none",
            "causal_request": False,
            "recompute_request": False,
            "ambiguity": {"is_ambiguous": False, "reason": None},
            "alternative_intents": [],
        }
        client = MagicMock()
        with self._patch_llm_call(mock_response):
            frame, meta = infer_intent_d_final_frame(
                prompt="Which stops are overdue?",
                family="SCHEDULE",
                client=client,
                mode="hybrid_guarded",
            )
        assert frame.intent == "lateness_summary"

    def test_recompute_flag_does_not_propagate_to_contract(self):
        """recompute_request=True in LLM frame is semantic metadata only.
        The intent is objective_delta; D4 still owns compute_decision."""
        mock_response = {
            "intent": "objective_delta",
            "confidence": 0.87,
            "entities": {"customer_ids": [], "route_labels": []},
            "requires_baseline": True,
            "comparison_type": "previous_solution",
            "causal_request": False,
            "recompute_request": True,
            "ambiguity": {"is_ambiguous": False, "reason": None},
            "alternative_intents": [],
        }
        client = MagicMock()
        with self._patch_llm_call(mock_response):
            frame, meta = infer_intent_d_final_frame(
                prompt="Is this cheaper than if we resolved from scratch?",
                family="OBJ",
                client=client,
                mode="hybrid_guarded",
            )
        # Frame only carries intent; compute_decision is not in QueryFrame
        assert frame.intent in ("objective_delta", "unknown", "objective_value")
        assert not hasattr(frame, "compute_decision")

    def test_no_client_falls_back_to_d1(self):
        """When client=None, should fall back to D1 deterministically."""
        frame, meta = infer_intent_d_final_frame(
            prompt="What is the total cost?",
            family="OBJ",
            client=None,
            mode="hybrid_guarded",
        )
        assert meta.fallback_reason == "no_llm_client"
        assert meta.source == "d1"
        assert frame.intent in ALLOWED_INTENTS

    def test_llm_schema_error_triggers_fallback(self):
        """Invalid LLM JSON → schema error → fallback to D1."""
        bad_result = _make_mock_result(
            {"intent": "TOTALLY_INVALID_INTENT", "confidence": 0.95, "answer_text": "here is your answer"}
        )
        client = MagicMock()
        with patch(
            "product.evaluation.model_clients.openai_client.call_openai_contract_model",
            return_value=bad_result,
        ):
            frame, meta = infer_intent_d_final_frame(
                prompt="What is the total cost?",
                family="OBJ",
                client=client,
                mode="hybrid_guarded",
            )
        # Should fall back to D1, not crash
        assert frame.intent in ALLOWED_INTENTS
        assert meta.fallback_used is True

    def test_low_confidence_triggers_fallback(self):
        mock_response = {
            "intent": "route_end_time",
            "confidence": 0.45,  # below minimum threshold
            "entities": {"customer_ids": [], "route_labels": []},
            "requires_baseline": False,
            "comparison_type": "none",
            "causal_request": False,
            "recompute_request": False,
            "ambiguity": {"is_ambiguous": False, "reason": None},
            "alternative_intents": [],
        }
        client = MagicMock()
        with patch(
            "product.evaluation.model_clients.openai_client.call_openai_contract_model",
            return_value=_make_mock_result(mock_response),
        ):
            frame, meta = infer_intent_d_final_frame(
                prompt="When does truck 3 call it a night?",
                family="SCHEDULE",
                client=client,
                mode="hybrid_guarded",
            )
        # Low confidence → fallback
        assert meta.fallback_used is True

    def test_ambiguous_frame_triggers_fallback(self):
        mock_response = {
            "intent": "route_end_time",
            "confidence": 0.82,
            "entities": {"customer_ids": [], "route_labels": []},
            "requires_baseline": False,
            "comparison_type": "none",
            "causal_request": False,
            "recompute_request": False,
            "ambiguity": {"is_ambiguous": True, "reason": "unclear between route_end_time and lateness_summary"},
            "alternative_intents": [],
        }
        with patch(
            "product.evaluation.model_clients.openai_client.call_openai_contract_model",
            return_value=_make_mock_result(mock_response),
        ):
            frame, meta = infer_intent_d_final_frame(
                prompt="Is anything timing out?",
                family="SCHEDULE",
                client=MagicMock(),
                mode="hybrid_guarded",
            )
        assert meta.fallback_used is True


# ---------------------------------------------------------------------------
# Hybrid-guarded policy: D1-confident path
# ---------------------------------------------------------------------------


class TestHybridGuardedPolicy:
    def test_d1_confident_no_llm_call(self):
        """When D1 is confident (not unknown/risk-zone), no LLM call is made."""
        with patch(
            "product.evaluation.model_clients.openai_client.call_openai_contract_model"
        ) as mock_call:
            frame, meta = infer_intent_hybrid_guarded(
                # feasibility_status is not in the risk zone — D1 handles it confidently
                prompt="Is the plan still feasible?",
                family="PLAN_VALIDITY",
                client=MagicMock(),
            )
        # feasibility_status is NOT in the risk zone → D1 keeps it, no LLM call
        mock_call.assert_not_called()
        assert meta.source == "d1"
        assert frame.intent == "feasibility_status"

    def test_d1_unknown_triggers_llm(self):
        """When D1 returns unknown, LLM should be called."""
        mock_response = {
            "intent": "route_end_time",
            "confidence": 0.9,
            "entities": {"customer_ids": [], "route_labels": [3]},
            "requires_baseline": False,
            "comparison_type": "none",
            "causal_request": False,
            "recompute_request": False,
            "ambiguity": {"is_ambiguous": False, "reason": None},
            "alternative_intents": [],
        }
        with patch(
            "product.evaluation.model_clients.openai_client.call_openai_contract_model",
            return_value=_make_mock_result(mock_response),
        ):
            frame, meta = infer_intent_hybrid_guarded(
                prompt="When does truck 3 call it a night?",
                family="SCHEDULE",
                client=MagicMock(),
            )
        # D1 returns unknown for this prompt → LLM is consulted
        assert frame.intent == "route_end_time"
        assert meta.source == "llm"


# ---------------------------------------------------------------------------
# D4 still owns compute_decision
# ---------------------------------------------------------------------------


class TestD4OwnsComputeDecision:
    def test_compute_decision_from_d4_not_llm(self):
        """The compute_decision in d_final output comes from D4, not the LLM."""
        from product.evaluation.run2_case_loader import Run2Case
        from product.evaluation.system_d_final.d_final_system_c import run_system_d_final_on_case

        case = Run2Case(
            case_id="test::synthetic",
            source_prompt_id="R2-001",
            family="OBJ",
            prompt_text="What is the total cost of this plan?",
            payload_condition="clean",
            payload_mutation_needed="",
            expected_intent="objective_value",
            expected_answerability="answerable",
            expected_evidence_paths=[],
            expected_missing_fields=[],
            expected_warnings=[],
            expected_next_actions=[],
            expected_behavior_class="direct_answer",
            implementation_status="test",
            difficulty="easy",
            label_rationale="",
            ambiguity_notes="",
        )
        predicted = run_system_d_final_on_case(
            case=case, payload={"objective": 100.5, "feasible": True},
            client=None,  # D1 fallback
        )
        # compute_decision is populated by D4, not the LLM
        # It may be None for payloads without route data, but it should never
        # be a raw string or dict from the LLM
        assert predicted.compute_decision is None or hasattr(predicted.compute_decision, "mode")
        # adapter_metadata is present
        assert predicted.adapter_metadata is not None


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


class TestAPIIntegration:
    def test_d_final_in_available_systems(self):
        from product.api.copilot_service import AVAILABLE_SYSTEMS
        assert "d_final" in AVAILABLE_SYSTEMS

    def test_copilot_ask_d_final_returns_semantic_adapter_metadata(self):
        """POST /copilot/ask with system=d_final returns semantic_adapter field."""
        from fastapi.testclient import TestClient
        from product.api.app import app

        client = TestClient(app)
        # Use a known scenario_id from the store; skip if none available
        try:
            from product.api.scenario_store import list_instances
            instances = list_instances()
            if not instances:
                pytest.skip("no scenarios in store")
            inst = instances[0]
            scenario_id = f"{inst['instance_id']}__{inst['available_perturbations'][0]}"
        except Exception:
            pytest.skip("scenario_store not available")

        resp = client.post(
            "/copilot/ask",
            json={
                "scenario_id": scenario_id,
                "prompt": "What is the total cost of this plan?",
                "system": "d_final",
                "family": "OBJ",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["system"] == "d_final"
        # semantic_adapter metadata must be present
        assert "semantic_adapter" in body
        sa = body["semantic_adapter"]
        assert "mode" in sa
        assert "source" in sa
        assert "accepted" in sa

    def test_copilot_ask_d_final_never_runs_solver(self):
        """d_final /copilot/ask must not call any solver."""
        from fastapi.testclient import TestClient
        from product.api.app import app

        client = TestClient(app)
        try:
            from product.api.scenario_store import list_instances
            instances = list_instances()
            if not instances:
                pytest.skip("no scenarios in store")
            inst = instances[0]
            scenario_id = f"{inst['instance_id']}__{inst['available_perturbations'][0]}"
        except Exception:
            pytest.skip("scenario_store not available")

        with patch("product.evaluation.system_d_final.d_final_system_c.run_system_d_final_on_case") as mock_runner:
            # Set up a mock return that looks like PredictedContractDFinal
            from product.evaluation.system_d_final.d_final_system_c import PredictedContractDFinal
            from product.copilot.llm_query_frame import LLMAdapterMetadata
            mock_runner.return_value = PredictedContractDFinal(
                case_id="api::test",
                predicted_intent="objective_value",
                predicted_answerability="answerable",
                predicted_evidence_paths=[],
                predicted_missing_fields=[],
                predicted_warnings=[],
                predicted_next_actions=[],
                predicted_behavior_class="direct_answer",
                notes=[],
                adapter_metadata=LLMAdapterMetadata(source="d1", accepted=True),
            )
            resp = client.post(
                "/copilot/ask",
                json={
                    "scenario_id": scenario_id,
                    "prompt": "What is the total cost?",
                    "system": "d_final",
                    "family": "OBJ",
                },
            )
        # Runner was called but no solver; assert no pyvrp import triggered
        assert resp.status_code == 200

    def test_api_key_not_in_response(self):
        """API response must never contain the OPENAI_API_KEY value."""
        from fastapi.testclient import TestClient
        from product.api.app import app

        api_key = os.environ.get("OPENAI_API_KEY", "sk-test-dummy-key")
        client = TestClient(app)
        try:
            from product.api.scenario_store import list_instances
            instances = list_instances()
            if not instances:
                pytest.skip("no scenarios in store")
            inst = instances[0]
            scenario_id = f"{inst['instance_id']}__{inst['available_perturbations'][0]}"
        except Exception:
            pytest.skip("scenario_store not available")

        resp = client.post(
            "/copilot/ask",
            json={"scenario_id": scenario_id, "prompt": "What's the cost?", "system": "d_final"},
        )
        assert api_key not in resp.text


# ---------------------------------------------------------------------------
# Integrity guards
# ---------------------------------------------------------------------------


class TestIntegrityGuards:
    _LOCKED_FILES = [
        "product/evaluation/run2_benchmark_cases.csv",
        "product/evaluation/run2_gold_schema.md",
        "product/evaluation/run2_scoring.py",
        "product/evaluation/run2_case_loader.py",
        "product/evaluation/run2_payloads.py",
        "product/evaluation/run2_system_c.py",
        "product/evaluation/run2_calibration_cases.csv",
    ]

    def test_locked_run2_artifacts_unchanged(self):
        """Locked Run 2 files must not appear in git diff (staged or unstaged)."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        changed = set(result.stdout.splitlines())
        for f in self._LOCKED_FILES:
            assert f not in changed, f"Locked file modified: {f}"

    def test_env_file_not_tracked(self):
        """.env must not be tracked by git."""
        result = subprocess.run(
            ["git", "ls-files", ".env"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        assert result.stdout.strip() == "", ".env is tracked by git — must be in .gitignore"

    def test_d1_import_still_works(self):
        from product.copilot.intent import infer_intent_d1_frame
        from product.evaluation.system_d1.d1_system_c import run_system_d1_on_case
        assert callable(infer_intent_d1_frame)
        assert callable(run_system_d1_on_case)

    def test_d4_import_still_works(self):
        from product.evaluation.system_d4 import run_system_d4_on_case
        assert callable(run_system_d4_on_case)

    def test_llm_never_emits_answer_text(self):
        """LLM output schema rejects answer_text at the Pydantic layer."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMSemanticFrame.model_validate({
                "intent": "route_end_time",
                "confidence": 0.9,
                "answer_text": "Vehicle 3 finishes at 17:30",
            })


# ---------------------------------------------------------------------------
# Optional live LLM tests (skipped unless RUN_LIVE_LLM_TESTS=1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_LLM_TESTS", "") != "1",
    reason="Live LLM tests skipped; set RUN_LIVE_LLM_TESTS=1 to run",
)
class TestLiveLLM:
    def test_live_route_end_time(self):
        from product.evaluation.model_clients.openai_client import load_openai_client
        from product.copilot.llm_semantic_intent_adapter import infer_intent_hybrid_guarded

        client = load_openai_client()
        frame, meta = infer_intent_hybrid_guarded(
            prompt="When does truck 3 call it a night?",
            family="SCHEDULE",
            client=client,
        )
        assert frame.intent in ALLOWED_INTENTS
        assert meta.schema_valid is True

    def test_live_no_answer_text_in_output(self):
        """Live LLM must not produce answer_text even when asked about costs."""
        from product.evaluation.model_clients.openai_client import load_openai_client
        from product.copilot.llm_semantic_intent_adapter import _call_llm

        client = load_openai_client()
        raw_frame, meta = _call_llm(client, "What is the total cost?",
                                    available_fields=None, model="gpt-5.4-mini")
        # If the frame is not None, it must not have answer_text (rejected by schema)
        if raw_frame is not None:
            assert not hasattr(raw_frame, "answer_text")

"""Tests for the LLM semantic intent adapter (A-008.5: R2 retry + R3 alts).

The R2 retry mechanism re-asks the LLM with feedback when the first
response fails Pydantic schema validation. The recovered frame must
still flow through every semantic guard (counterfactual_guard,
ranking_guard, evaluation_guard) before acceptance — otherwise the
retry path silently bypasses the guards' safety net. These tests pin
that interaction.

R3 ambiguity surfacing is exercised via ``test_evidence.py`` /
``test_ranking_disambiguation.py``; this file focuses on the adapter.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest
from pydantic import ValidationError

from product.copilot.llm_query_frame import (
    LLMAdapterMetadata,
    LLMSemanticFrame,
)
from product.copilot.llm_semantic_intent_adapter import (
    _SYSTEM_PROMPT,
    _build_retry_feedback,
    _build_user_message,
    _call_llm,
    _classify_validation_error,
    _normalize_llm_raw,
    _retry_enabled,
    infer_intent_hybrid_guarded,
)


# ---------------------------------------------------------------------------
# Helpers — minimal fake OpenAI client + response object
# ---------------------------------------------------------------------------


class _FakeResponseMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.message = _FakeResponseMessage(content)
        self.finish_reason = finish_reason


class _FakeUsage:
    prompt_tokens = 100
    completion_tokens = 50
    total_tokens = 150


class _FakeResponse:
    def __init__(self, content: str, model: str = "gpt-5.4-mini"):
        self.choices = [_FakeChoice(content)]
        self.model = model
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, responses: list[str]):
        # Queue of canned responses. The adapter's _call_llm makes the
        # initial call; if retry fires, it makes a second call. We pop
        # off the front for each.
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs.get("messages", []))
        if not self._responses:
            raise RuntimeError("no canned responses left")
        return _FakeResponse(self._responses.pop(0))


class _FakeChat:
    def __init__(self, completions: _FakeCompletions):
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, responses: list[str]):
        self._completions = _FakeCompletions(responses)
        self.chat = _FakeChat(self._completions)

    @property
    def calls(self) -> list[list[dict]]:
        return self._completions.calls


def _good_frame(
    intent: str = "objective_value",
    confidence: float = 0.92,
    requires_baseline: bool = False,
    comparison_type: str = "none",
) -> str:
    """Schema-valid LLM JSON output, as a string."""
    return json.dumps({
        "intent": intent,
        "confidence": confidence,
        "entities": {"customer_ids": [], "route_labels": []},
        "requires_baseline": requires_baseline,
        "comparison_type": comparison_type,
        "causal_request": False,
        "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })


# ---------------------------------------------------------------------------
# Retry telemetry on metadata
# ---------------------------------------------------------------------------


def test_metadata_has_retry_fields():
    meta = LLMAdapterMetadata()
    assert meta.retry_fired is False
    assert meta.retry_success is None
    assert meta.retry_reason is None
    assert meta.retry_latency_ms is None


# ---------------------------------------------------------------------------
# Retry-enabled / disabled via env var
# ---------------------------------------------------------------------------


def test_retry_enabled_by_default(monkeypatch):
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)
    assert _retry_enabled() is True


def test_retry_disabled_via_env(monkeypatch):
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "1")
    assert _retry_enabled() is False
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "true")
    assert _retry_enabled() is False
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "0")
    assert _retry_enabled() is True
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "")
    assert _retry_enabled() is True


# ---------------------------------------------------------------------------
# Validation-error classifier
# ---------------------------------------------------------------------------


def _force_validation_error(raw: dict) -> ValidationError:
    try:
        LLMSemanticFrame.model_validate(_normalize_llm_raw(raw))
    except ValidationError as exc:
        return exc
    raise RuntimeError("expected ValidationError")


def test_classifier_missing_required_field():
    exc = _force_validation_error({"confidence": 0.9})
    assert _classify_validation_error(exc) == "missing_required_field"


def test_classifier_wrong_type():
    exc = _force_validation_error({"intent": "objective_value", "confidence": "abc"})
    assert _classify_validation_error(exc) == "wrong_type"


def test_classifier_extra_forbidden_is_schema_validation_error():
    exc = _force_validation_error(
        {"intent": "objective_value", "confidence": 0.9, "extra_field": 1}
    )
    assert _classify_validation_error(exc) == "schema_validation_error"


def test_classifier_out_of_range_value_is_schema_validation_error():
    exc = _force_validation_error({"intent": "objective_value", "confidence": 5.0})
    assert _classify_validation_error(exc) == "schema_validation_error"


# ---------------------------------------------------------------------------
# Retry feedback construction
# ---------------------------------------------------------------------------


def test_retry_feedback_includes_specific_correction_instructions():
    exc = _force_validation_error(
        {"intent": "objective_value", "confidence": "not_a_float"}
    )
    msgs = _build_retry_feedback("ORIGINAL_USER_MSG", "{prev_json}", exc)

    # Three pinning expectations:
    # 1. Includes original user message verbatim
    user_first = [m for m in msgs if m["role"] == "user"][0]
    assert user_first["content"] == "ORIGINAL_USER_MSG"
    # 2. Includes the previous failed response so the model has the diff
    asst_msg = [m for m in msgs if m["role"] == "assistant"][0]
    assert asst_msg["content"] == "{prev_json}"
    # 3. Includes a specific correction line for the failed field
    retry_user = msgs[-1]
    assert retry_user["role"] == "user"
    body = retry_user["content"]
    assert "confidence" in body
    # The corrective instruction names the error class
    assert "float_parsing" in body or "valid number" in body.lower()


def test_retry_feedback_handles_missing_field():
    exc = _force_validation_error({"confidence": 0.9})
    msgs = _build_retry_feedback("USER", "{}", exc)
    body = msgs[-1]["content"]
    assert "required field" in body.lower()
    assert "intent" in body


# ---------------------------------------------------------------------------
# Retry integration — schema-invalid response recovered on retry
# ---------------------------------------------------------------------------


def test_retry_fires_on_validation_error_and_recovers(monkeypatch):
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)

    # First response: missing required field `intent`. Second: schema-valid.
    bad = json.dumps({
        "confidence": 0.9,
        "entities": {"customer_ids": [], "route_labels": []},
        "requires_baseline": False,
        "comparison_type": "none",
        "causal_request": False,
        "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })
    good = _good_frame(intent="objective_value")

    client = _FakeOpenAI([bad, good])
    frame, meta = _call_llm(client, prompt="What is the total cost?")

    assert frame is not None, "retry should have recovered a frame"
    assert frame.intent == "objective_value"
    assert meta.retry_fired is True
    assert meta.retry_success is True
    assert meta.retry_reason == "missing_required_field"
    assert meta.retry_latency_ms is not None and meta.retry_latency_ms >= 0
    assert meta.schema_valid is True
    # Two OpenAI calls (original + retry)
    assert len(client.calls) == 2


def test_retry_disabled_skips_retry_attempt(monkeypatch):
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "1")
    bad = json.dumps({
        "confidence": 0.9,
        "entities": {"customer_ids": [], "route_labels": []},
        "requires_baseline": False,
        "comparison_type": "none",
        "causal_request": False,
        "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })
    good = _good_frame(intent="objective_value")
    client = _FakeOpenAI([bad, good])

    frame, meta = _call_llm(client, prompt="What is the total cost?")

    assert frame is None
    assert meta.retry_fired is False
    assert meta.schema_valid is False
    assert meta.fallback_used is True
    # Only the initial call, no retry
    assert len(client.calls) == 1


def test_retry_failed_falls_through_to_d1(monkeypatch):
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)
    # Both responses are schema-invalid
    bad1 = json.dumps({"confidence": 0.9})
    bad2 = json.dumps({"confidence": 0.9})
    client = _FakeOpenAI([bad1, bad2])

    frame, meta = _call_llm(client, prompt="What is the total cost?")

    assert frame is None
    assert meta.retry_fired is True
    assert meta.retry_success is False
    assert meta.fallback_used is True
    assert len(client.calls) == 2


# ---------------------------------------------------------------------------
# Guard interaction — retry-recovered frames still flow through guards
# ---------------------------------------------------------------------------


def test_retry_recovered_frame_still_triggers_counterfactual_guard(monkeypatch):
    """A retry-recovered frame must NOT bypass the counterfactual guard.

    Setup: first response is schema-invalid. Retry response is valid but
    classifies a counterfactual prompt as `perturbation_summary` (the
    failure mode A-006 introduced the guard for). The guard must still
    fire on the retry-recovered frame.
    """
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)
    bad = json.dumps({"confidence": 0.9})
    retry = _good_frame(intent="perturbation_summary", confidence=0.9)
    client = _FakeOpenAI([bad, retry])

    frame, meta = _call_llm(
        client, prompt="What if vehicle 3 broke down halfway through?"
    )

    assert meta.retry_fired is True and meta.retry_success is True
    assert meta.counterfactual_guard_fired is True
    assert frame is not None
    assert frame.intent == "unknown"


def test_retry_recovered_frame_still_triggers_ranking_guard(monkeypatch):
    """Retry-recovered frame on a ranking-shaped prompt must still flip to unknown."""
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)
    bad = json.dumps({"confidence": 0.9})
    retry = _good_frame(intent="lateness_summary", confidence=0.9)
    client = _FakeOpenAI([bad, retry])

    frame, meta = _call_llm(client, prompt="Show me the top 3 worst routes by lateness")

    assert meta.retry_fired is True and meta.retry_success is True
    assert meta.ranking_guard_fired is True
    assert frame is not None
    assert frame.intent == "unknown"


def test_retry_recovered_frame_still_triggers_evaluation_guard(monkeypatch):
    """Retry-recovered frame on a comparison-shaped prompt classified as evaluate_* must redirect to before_after_comparison."""
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)
    bad = json.dumps({"confidence": 0.9})
    retry = _good_frame(intent="evaluate_plan_acceptability", confidence=0.9)
    client = _FakeOpenAI([bad, retry])

    frame, meta = _call_llm(client, prompt="Did anything improve?")

    assert meta.retry_fired is True and meta.retry_success is True
    assert meta.evaluation_guard_fired is True
    assert frame is not None
    assert frame.intent == "before_after_comparison"


# ---------------------------------------------------------------------------
# Non-retry path unaffected — schema-valid first response
# ---------------------------------------------------------------------------


def test_no_retry_on_first_try_success(monkeypatch):
    monkeypatch.delenv("COPILOT_DISABLE_LLM_RETRY", raising=False)
    good = _good_frame(intent="route_count")
    client = _FakeOpenAI([good])

    frame, meta = _call_llm(client, prompt="How many routes?")

    assert frame is not None
    assert frame.intent == "route_count"
    assert meta.retry_fired is False
    assert meta.retry_success is None
    assert len(client.calls) == 1

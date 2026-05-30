"""Self-consistency aggregator tests (Lever 3).

The LLM still only proposes intent + entities. Aggregation across N
samples and tie-handling are deterministic:

  * Strict majority on intent (count > N/2) wins.
  * No strict majority → frame.intent='unknown' AND tie_break=True
    (honest-refusal posture; refuse rather than guess).
  * Sample failures are skipped from the vote but the threshold stays
    at N/2 — a 1-of-5 winner with 4 failures is NOT promoted.
  * All N samples fail → behavior matches the existing single-call
    all-fail path (frame=None, fallback_used=True).

These tests mock the LLM client end-to-end so nothing hits the network.
"""
from __future__ import annotations

import json
from typing import Iterable

import pytest

from product.copilot import llm_semantic_intent_adapter as adapter
from product.copilot.llm_query_frame import (
    LLMAdapterMetadata,
    LLMSemanticFrame,
)


# ---------------------------------------------------------------------------
# Minimal fake OpenAI client — drains a list of canned response strings,
# one per chat.completions.create() call. Mirrors the helper in
# tests/test_llm_adapter.py so failure modes look identical.
# ---------------------------------------------------------------------------


class _FakeResponseMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeResponseMessage(content)
        self.finish_reason = "stop"


class _FakeUsage:
    prompt_tokens = 100
    completion_tokens = 50
    total_tokens = 150


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.model = "gpt-5.4-mini"
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, responses: Iterable[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("no canned responses left")
        return _FakeResponse(self._responses.pop(0))


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, responses: Iterable[str]) -> None:
        self._completions = _FakeCompletions(responses)
        self.chat = _FakeChat(self._completions)

    @property
    def calls(self) -> list[dict]:
        return self._completions.calls


def _good_json(intent: str = "objective_value", confidence: float = 0.92) -> str:
    return json.dumps({
        "intent": intent,
        "confidence": confidence,
        "entities": {"customer_ids": [], "route_labels": []},
        "requires_baseline": False,
        "comparison_type": "none",
        "causal_request": False,
        "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })


def _frame(intent: str, confidence: float = 0.92) -> LLMSemanticFrame:
    return LLMSemanticFrame.model_validate(json.loads(_good_json(intent, confidence)))


# ---------------------------------------------------------------------------
# _aggregate_frames — direct unit tests
# ---------------------------------------------------------------------------


def test_majority_wins_3_of_3():
    frames = [_frame("objective_value"), _frame("objective_value"), _frame("route_count")]
    f, tel = adapter._aggregate_frames(frames, n_configured=3)
    assert f is not None
    assert f.intent == "objective_value"
    assert f.tie_break is False
    assert tel["chose"] == "objective_value"
    assert tel["tie_break"] is False
    assert tel["n_samples"] == 3
    assert tel["sample_intents"] == ["objective_value", "objective_value", "route_count"]


def test_tie_to_unknown_3_distinct():
    frames = [_frame("objective_value"), _frame("route_count"), _frame("feasibility_status")]
    f, tel = adapter._aggregate_frames(frames, n_configured=3)
    assert f is not None
    assert f.intent == "unknown"
    assert f.tie_break is True
    # Confidence stays above the validate_llm_frame conditional gate so the
    # honest-refusal unknown actually flows through downstream.
    assert f.confidence >= 0.80
    assert tel["chose"] == "unknown"
    assert tel["tie_break"] is True


def test_winner_takes_first_matching_sample_entities():
    a = LLMSemanticFrame.model_validate({
        "intent": "objective_value", "confidence": 0.91,
        "entities": {"customer_ids": [11], "route_labels": [3]},
        "requires_baseline": False, "comparison_type": "none",
        "causal_request": False, "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })
    b = LLMSemanticFrame.model_validate({
        "intent": "objective_value", "confidence": 0.91,
        "entities": {"customer_ids": [22], "route_labels": [9]},
        "requires_baseline": False, "comparison_type": "none",
        "causal_request": False, "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })
    c = _frame("route_count")
    f, _tel = adapter._aggregate_frames([a, b, c], n_configured=3)
    # First matching sample wins for entity carryover — deterministic.
    assert f is not None
    assert list(f.entities.customer_ids) == [11]
    assert list(f.entities.route_labels) == [3]


def test_partial_failures_majority_on_valid():
    # 2 valid + 1 failure (None) → majority across the 2 valid survives.
    frames = [_frame("objective_value"), _frame("objective_value"), None]
    f, tel = adapter._aggregate_frames(frames, n_configured=3)
    assert f is not None
    assert f.intent == "objective_value"
    assert f.tie_break is False
    assert tel["sample_intents"] == ["objective_value", "objective_value", None]
    assert tel["chose"] == "objective_value"


def test_all_fail_returns_none_with_telemetry():
    f, tel = adapter._aggregate_frames([None, None, None], n_configured=3)
    assert f is None
    assert tel["n_samples"] == 3
    assert tel["sample_intents"] == [None, None, None]
    assert tel["chose"] is None
    assert tel["tie_break"] is False


def test_winner_confidence_is_vote_share_not_donor_confidence():
    """The aggregated winner frame should use vote_count/N as confidence,
    not the donor sample's per-call confidence — so a clear consensus
    is not invalidated by a single weak sample.
    """
    # Donor sample has confidence=0.61 (conditional zone); two others agree.
    low_conf_donor = LLMSemanticFrame.model_validate({
        "intent": "objective_value", "confidence": 0.61,
        "entities": {"customer_ids": [], "route_labels": []},
        "requires_baseline": False, "comparison_type": "none",
        "causal_request": False, "recompute_request": False,
        "ambiguity": {"is_ambiguous": False, "reason": None},
        "alternative_intents": [],
    })
    other = _frame("objective_value", confidence=0.91)
    frames = [low_conf_donor, other, other]  # 3/3 agree, N=3

    f, _tel = adapter._aggregate_frames(frames, n_configured=3)
    assert f is not None
    # vote_confidence = 3/3 = 1.0, not 0.61
    assert f.confidence == pytest.approx(1.0)
    assert f.ambiguity.is_ambiguous is False


def test_winner_ambiguity_cleared_even_when_donor_was_ambiguous():
    """An ambiguous donor sample must not make the aggregated frame
    ambiguous — the majority vote resolves the ambiguity.
    """
    ambig_donor = LLMSemanticFrame.model_validate({
        "intent": "objective_value", "confidence": 0.90,
        "entities": {"customer_ids": [], "route_labels": []},
        "requires_baseline": False, "comparison_type": "none",
        "causal_request": False, "recompute_request": False,
        "ambiguity": {"is_ambiguous": True, "reason": "could be objective_delta"},
        "alternative_intents": [],
    })
    other = _frame("objective_value")
    frames = [ambig_donor, other, other]  # 3/3 agree

    f, _tel = adapter._aggregate_frames(frames, n_configured=3)
    assert f is not None
    assert f.ambiguity.is_ambiguous is False
    assert f.ambiguity.reason is None


def test_strict_majority_threshold_is_configured_N_not_success_count():
    # Configured N=5, only 2 successful samples both 'A'. Threshold stays
    # at 5/2 = 2.5 → 2 successes is NOT a strict majority → tie_break.
    a = _frame("objective_value")
    frames = [a, a, None, None, None]
    f, tel = adapter._aggregate_frames(frames, n_configured=5)
    assert f is not None
    assert f.intent == "unknown"
    assert f.tie_break is True
    assert tel["chose"] == "unknown"


# ---------------------------------------------------------------------------
# Env var parsing
# ---------------------------------------------------------------------------


def test_default_n_is_one(monkeypatch):
    monkeypatch.delenv("SELF_CONSISTENCY_N", raising=False)
    assert adapter._get_self_consistency_n() == 1


def test_default_temperature(monkeypatch):
    monkeypatch.delenv("SELF_CONSISTENCY_TEMPERATURE", raising=False)
    assert adapter._get_self_consistency_temperature() == pytest.approx(0.5)


def test_invalid_n_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SELF_CONSISTENCY_N", "not_an_int")
    assert adapter._get_self_consistency_n() == 1


def test_n_clamped_to_minimum_one(monkeypatch):
    monkeypatch.setenv("SELF_CONSISTENCY_N", "0")
    assert adapter._get_self_consistency_n() == 1


# ---------------------------------------------------------------------------
# Integration: _call_llm under N=1 vs N>1, with mocked client.
# ---------------------------------------------------------------------------


def test_default_is_unchanged_single_call(monkeypatch):
    """With SELF_CONSISTENCY_N unset, _call_llm makes exactly ONE LLM call
    and does NOT populate the self_consistency telemetry block — proving
    the default path is untouched.
    """
    monkeypatch.delenv("SELF_CONSISTENCY_N", raising=False)
    client = _FakeOpenAI([_good_json("objective_value")])

    frame, meta = adapter._call_llm(client, "How is the cost?")

    assert frame is not None
    assert frame.intent == "objective_value"
    # The default path NEVER touches the self_consistency block.
    assert meta.self_consistency is None
    # Exactly one underlying LLM call was issued.
    assert len(client.calls) == 1


def test_n3_majority_routes_through_aggregator(monkeypatch):
    monkeypatch.setenv("SELF_CONSISTENCY_N", "3")
    # Three samples: two say objective_value, one says route_count.
    client = _FakeOpenAI([
        _good_json("objective_value"),
        _good_json("objective_value"),
        _good_json("route_count"),
    ])

    frame, meta = adapter._call_llm(client, "How is the cost?")

    assert frame is not None
    assert frame.intent == "objective_value"
    assert frame.tie_break is False
    assert meta.self_consistency is not None
    assert meta.self_consistency["n_samples"] == 3
    assert meta.self_consistency["chose"] == "objective_value"
    assert meta.self_consistency["tie_break"] is False
    # Three samples → three underlying LLM calls.
    assert len(client.calls) == 3


def test_n3_tie_forces_unknown_with_tie_break(monkeypatch):
    monkeypatch.setenv("SELF_CONSISTENCY_N", "3")
    client = _FakeOpenAI([
        _good_json("objective_value"),
        _good_json("route_count"),
        _good_json("feasibility_status"),
    ])

    frame, meta = adapter._call_llm(client, "How does this look?")

    assert frame is not None
    assert frame.intent == "unknown"
    assert frame.tie_break is True
    assert meta.self_consistency["tie_break"] is True
    assert meta.self_consistency["chose"] == "unknown"


def test_n3_partial_failures_majority_on_two_valid(monkeypatch):
    """One of three samples returns invalid JSON; the retry path also
    fails. The other two agree on objective_value, so majority should
    still be 2/3 > 1.5 — A wins.
    """
    monkeypatch.setenv("SELF_CONSISTENCY_N", "3")
    # Disable the per-sample retry so the bad sample stays bad.
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "1")

    bad = "this is not json at all"
    client = _FakeOpenAI([
        _good_json("objective_value"),
        bad,
        _good_json("objective_value"),
    ])

    frame, meta = adapter._call_llm(client, "How is the cost?")

    assert frame is not None
    assert frame.intent == "objective_value"
    assert meta.self_consistency["chose"] == "objective_value"
    # One sample failure shows up as a None in sample_intents.
    intents = meta.self_consistency["sample_intents"]
    assert intents.count("objective_value") == 2
    assert intents.count(None) == 1


def test_n3_all_fail_matches_single_call_all_fail_semantics(monkeypatch):
    """When every sample fails validation, the aggregator returns
    frame=None with meta.fallback_used=True — the same contract the
    single-call path already exposes when its one call fails. Downstream
    modes (infer_intent_hybrid_guarded, etc.) already handle frame=None.
    """
    monkeypatch.setenv("SELF_CONSISTENCY_N", "3")
    monkeypatch.setenv("COPILOT_DISABLE_LLM_RETRY", "1")
    client = _FakeOpenAI(["nope", "still nope", "even more nope"])

    frame, meta = adapter._call_llm(client, "How is the cost?")

    assert frame is None
    assert meta.fallback_used is True
    assert meta.fallback_reason is not None
    assert "all_samples_failed" in meta.fallback_reason
    # Telemetry block still populated so the log shows N attempts.
    assert meta.self_consistency is not None
    assert meta.self_consistency["n_samples"] == 3
    assert meta.self_consistency["sample_intents"] == [None, None, None]
    assert meta.self_consistency["chose"] is None


def test_guards_apply_post_aggregation(monkeypatch):
    """Counterfactual guard must fire AFTER the aggregator picks a
    winner — the guard rewrites intent to 'unknown' even when the
    sampled majority agreed on a descriptive intent. This pins that the
    per-sample-then-aggregate order does not bypass guards.
    """
    monkeypatch.setenv("SELF_CONSISTENCY_N", "3")
    # All three samples agree on perturbation_summary — a descriptive
    # intent. But the prompt is subjunctive, so the counterfactual guard
    # should rewrite the aggregated frame to 'unknown'.
    client = _FakeOpenAI([
        _good_json("perturbation_summary"),
        _good_json("perturbation_summary"),
        _good_json("perturbation_summary"),
    ])

    frame, meta = adapter._call_llm(client, "What if vehicle 3 broke down?")

    assert frame is not None
    assert frame.intent == "unknown"  # counterfactual guard fired post-aggregation
    assert meta.counterfactual_guard_fired is True
    # The aggregator still saw the agreement — chose=perturbation_summary
    # in the telemetry block, even though the guard ultimately overrode it.
    assert meta.self_consistency["chose"] == "perturbation_summary"

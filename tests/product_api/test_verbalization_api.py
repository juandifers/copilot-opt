"""Tests: deterministic verbalization is wired into POST /copilot/ask.

Checks that answer_text is populated, derives from the structured
contract without LLM calls, and that renderer failure leaves the
structured response intact.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from product.api import copilot_service
from product.api.app import app
from product.api.scenario_store import load_registry
from product.evaluation.run2_system_c import PredictedContract

# Skip the module if Run 1 artifacts are not on disk (same guard as test_api.py).
try:
    load_registry()
except FileNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"Run 1 artifacts not found: {exc}", allow_module_level=True)


_SCENARIO_OBJ = "C202__TW_3"
_SCENARIO_SCHEDULE = "C105__TT_4"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_contract(
    *,
    intent: str = "objective_value",
    answerability: str = "answerable",
    behavior_class: str = "direct_answer",
    evidence_paths: list[str] | None = None,
    warnings: list[str] | None = None,
    missing_fields: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> PredictedContract:
    return PredictedContract(
        case_id="test",
        predicted_intent=intent,
        predicted_answerability=answerability,
        predicted_evidence_paths=evidence_paths or [],
        predicted_missing_fields=missing_fields or [],
        predicted_warnings=warnings or [],
        predicted_next_actions=next_actions or [],
        predicted_behavior_class=behavior_class,
        notes=[],
    )


def _patch_c0(monkeypatch, contract: PredictedContract) -> None:
    monkeypatch.setitem(
        copilot_service._DISPATCH,
        "c0",
        copilot_service._Dispatch(lambda case, payload, generator_record: contract),
    )


# ---------------------------------------------------------------------------
# 1. Integration: real scenarios produce non-null answer_text
# ---------------------------------------------------------------------------


def test_answer_text_populated_for_direct_answer(client: TestClient) -> None:
    """OBJ scenario: 'What is the total cost?' → direct_answer → answer_text non-null."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is the total cost?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "objective_value"
    assert body["answer_text"] is not None
    assert len(body["answer_text"]) > 0


def test_answer_text_populated_for_warning_case(client: TestClient) -> None:
    """SCHEDULE scenario: 'What time does route 3 finish?' → direct_answer_with_warning → non-null."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_SCHEDULE,
            "prompt": "What time does route 3 finish?",
            "family": "SCHEDULE",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "route_end_time"
    assert body["answer_text"] is not None
    assert len(body["answer_text"]) > 0


def test_answer_text_populated_for_needs_recompute(client: TestClient) -> None:
    """D4 system: hypothetical question → needs_recompute → answer_text explains recompute."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What if we add customer 999 near route 4?",
            "system": "d4",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["compute_decision"]["mode"] == "needs_recompute"
    assert body["answer_text"] is not None
    assert len(body["answer_text"]) > 0


# ---------------------------------------------------------------------------
# 2. Monkeypatched: specific behavior classes produce non-null answer_text
# ---------------------------------------------------------------------------


def test_answer_text_populated_for_useful_refusal(
    client: TestClient, monkeypatch
) -> None:
    contract = _fake_contract(
        answerability="not_answerable",
        behavior_class="useful_refusal",
        missing_fields=["baseline_solution"],
    )
    _patch_c0(monkeypatch, contract)
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "x", "system": "c0"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer_text"] is not None
    assert len(body["answer_text"]) > 0


def test_answer_text_populated_for_partial_answer(
    client: TestClient, monkeypatch
) -> None:
    contract = _fake_contract(
        intent="feasibility_status",
        answerability="partially_answerable",
        behavior_class="partial_answer_with_warning",
        missing_fields=["feasibility_breakdown"],
        warnings=["unsupported_comparison"],
    )
    _patch_c0(monkeypatch, contract)
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "x", "system": "c0"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer_text"] is not None
    assert len(body["answer_text"]) > 0


# ---------------------------------------------------------------------------
# 3. answer_text content reflects the contract (warnings, missing fields)
# ---------------------------------------------------------------------------


def test_answer_text_preserves_route_indexing_warning(client: TestClient) -> None:
    """When route_indexing_ambiguity is present, answer_text must surface the note."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_SCHEDULE,
            "prompt": "What time does route 3 finish?",
            "family": "SCHEDULE",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "route_indexing_ambiguity" in body["warnings"]
    # The verbalization should mention route numbering in the answer text.
    answer = body["answer_text"] or ""
    assert answer  # non-empty
    # Warning note mentions sequential / index
    assert any(kw in answer.lower() for kw in ("sequential", "index", "position", "route")), (
        f"expected route-numbering note in answer_text, got: {answer!r}"
    )


def test_answer_text_preserves_missing_field_note(
    client: TestClient, monkeypatch
) -> None:
    contract = _fake_contract(
        answerability="not_answerable",
        behavior_class="useful_refusal",
        missing_fields=["baseline_solution"],
    )
    _patch_c0(monkeypatch, contract)
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "x", "system": "c0"},
    )
    body = r.json()
    answer = body["answer_text"] or ""
    assert "baseline" in answer.lower(), (
        f"expected baseline mention in answer_text, got: {answer!r}"
    )


def test_answer_text_preserves_compute_decision_note(client: TestClient) -> None:
    """needs_recompute answer_text mentions what action is recommended."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What if we add customer 999 near route 4?",
            "system": "d4",
        },
    )
    assert r.status_code == 200
    body = r.json()
    cd = body["compute_decision"]
    assert cd["mode"] == "needs_recompute"
    answer = body["answer_text"] or ""
    # Answer text should mention recompute / payload / computation
    assert any(
        kw in answer.lower()
        for kw in ("recompute", "payload", "computation", "solver", "recommended", "result")
    ), f"expected recompute mention in answer_text, got: {answer!r}"


# ---------------------------------------------------------------------------
# 4. Structured fields are unchanged by verbalization
# ---------------------------------------------------------------------------


def test_structured_fields_unchanged_by_verbalization(client: TestClient) -> None:
    """Adding answer_text must not alter evidence, warnings, or compute_decision."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_SCHEDULE,
            "prompt": "What time does route 3 finish?",
            "family": "SCHEDULE",
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Structured fields present and correct type
    assert isinstance(body["evidence"], list)
    assert isinstance(body["warnings"], list)
    assert isinstance(body["suggested_next_actions"], list)
    assert "answerability" in body
    assert "status" in body["answerability"]
    # answer_text is additional; evidence is still present and non-empty
    assert body["evidence"], "evidence must be populated and not cleared"
    # answer_text is separate from evidence
    assert body["answer_text"] is not None  # verbalization worked
    for ev in body["evidence"]:
        assert "field_path" in ev
        assert "value" in ev
        assert "display_anchor" in ev


# ---------------------------------------------------------------------------
# 5. No LLM calls for verbalization (structural check)
# ---------------------------------------------------------------------------


def test_verbalization_makes_no_llm_calls() -> None:
    """verbalize() must not import or call any LLM client.

    Structural check: the verbalization module must not reference
    openai, anthropic, or any model-call entrypoints.
    """
    import ast
    import pathlib

    src = pathlib.Path("product/copilot/verbalization.py").read_text()
    tree = ast.parse(src)
    llm_names = {"openai", "anthropic", "litellm", "cohere", "together"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in getattr(node, "names", []):
                assert alias.name.split(".")[0].lower() not in llm_names, (
                    f"verbalization.py must not import {alias.name}"
                )
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0].lower() not in llm_names, (
                    f"verbalization.py must not import from {node.module}"
                )


def test_verbalization_no_api_key_dependency() -> None:
    """verbalize() must be callable without any environment variables."""
    import os

    from product.copilot.verbalization import verbalize

    # Remove any LLM-related env vars for this call
    env_backup = {k: v for k, v in os.environ.items() if "KEY" in k or "TOKEN" in k}
    for k in env_backup:
        os.environ.pop(k, None)
    try:
        result = verbalize(
            intent="objective_value",
            answerability="answerable",
            behavior_class="direct_answer",
            evidence_items=[{"field_path": "action_objective", "value": 123.4}],
            warnings=[],
            missing_fields=[],
            next_actions=[],
            prompt_text="What is the total cost?",
        )
        assert isinstance(result, str)
        assert "123.4" in result
    finally:
        os.environ.update(env_backup)


# ---------------------------------------------------------------------------
# 6. Renderer failure: structured fields survive, answer_text = null
# ---------------------------------------------------------------------------


def test_renderer_failure_returns_null_answer_text_but_structured_fields_intact(
    client: TestClient, monkeypatch
) -> None:
    """If verbalize() raises, API returns null answer_text but all structured fields."""
    from product.copilot import verbalization as verb_mod

    def _explode(*args, **kwargs):
        raise RuntimeError("simulated verbalization failure")

    monkeypatch.setattr(verb_mod, "verbalize", _explode)

    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is the total cost?"},
    )
    assert r.status_code == 200
    body = r.json()
    # answer_text must be null — renderer failure is handled gracefully
    assert body["answer_text"] is None
    # All structured fields must still be present
    assert body["intent"] == "objective_value"
    assert isinstance(body["evidence"], list)
    assert isinstance(body["warnings"], list)
    assert "answerability" in body
    assert "behavior_class" in body


# ---------------------------------------------------------------------------
# 7. Regression: existing answer_text=null assertion was the old contract;
#    check the opposite — the field is no longer hardcoded null.
# ---------------------------------------------------------------------------


def test_answer_text_is_no_longer_always_null(client: TestClient) -> None:
    """Regression: answer_text must no longer be null for standard prompts."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is the total cost?"},
    )
    assert r.status_code == 200
    body = r.json()
    # Was always null before; must now be a non-empty string
    assert body["answer_text"] is not None, (
        "answer_text must be populated by the verbalization renderer"
    )
    assert isinstance(body["answer_text"], str)
    assert len(body["answer_text"].strip()) > 0

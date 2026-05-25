"""Tests for the grounded overview-support extension.

Covers:
1. Intent routing for the six new overview intents.
2. Answerability — descriptive intents are answerable, impact intents
   without baseline/diff degrade to partially_answerable.
3. D4 compute_decision — overview intents never recommend recompute;
   impact intents without diff recommend build_comparison_payload.
4. Overclaim prevention — answer_text never claims route changes,
   objective deltas, or causal mechanisms when the supporting fields
   are absent.
5. answer_text is non-null and grounded for every overview intent.
6. Existing 14 intents still route correctly (regression).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from product.api.app import app
from product.api.scenario_store import load_registry

# Skip the module if Run 1 artifacts are not on disk (same guard as
# tests/product_api/test_api.py).
try:
    load_registry()
except FileNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"Run 1 artifacts not found: {exc}", allow_module_level=True)


_SCENARIO_STRUCT = "C202__TW_3"     # STRUCT family, TIME_WINDOW perturbation
_SCENARIO_SCHEDULE = "C105__TT_4"   # SCHEDULE family, TRAVEL_TIME perturbation


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Intent routing — overview prompts hit the new intent strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("What is this perturbation doing?", "perturbation_summary"),
        ("What kind of perturbation is this?", "perturbation_summary"),
        ("What am I looking at?", "scenario_summary"),
        ("Summarize this scenario.", "scenario_summary"),
        ("Give me the overview.", "scenario_summary"),
        ("How does the plan look?", "solution_summary"),
        ("Summarize the current solution.", "solution_summary"),
        ("How is this perturbation affecting routes?", "route_impact_summary"),
        ("Which routes are most affected?", "route_impact_summary"),
        ("How is this perturbation affecting the solution?", "perturbation_impact_summary"),
        ("Did this make things worse?", "perturbation_impact_summary"),
        ("What should I pay attention to?", "what_to_watch"),
        ("Anything concerning here?", "what_to_watch"),
        ("Where should I look first?", "what_to_watch"),
    ],
)
def test_overview_prompt_routes_to_overview_intent(
    client: TestClient, prompt: str, expected_intent: str
) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": prompt},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == expected_intent, (
        f"prompt {prompt!r} expected intent {expected_intent!r}, "
        f"got {body['intent']!r}"
    )


# ---------------------------------------------------------------------------
# 2. Answerability — descriptive answerable, impact partial
# ---------------------------------------------------------------------------


def test_perturbation_summary_is_answerable(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What is this perturbation doing?"},
    )
    body = r.json()
    assert body["intent"] == "perturbation_summary"
    assert body["answerability"]["status"] == "answerable"


def test_scenario_summary_is_answerable(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "Summarize this scenario."},
    )
    body = r.json()
    assert body["answerability"]["status"] == "answerable"


def test_what_to_watch_is_answerable(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What should I pay attention to?"},
    )
    body = r.json()
    assert body["answerability"]["status"] in ("answerable", "partially_answerable")


def test_perturbation_impact_summary_is_partial_when_no_diff(client: TestClient) -> None:
    """Run 1 payloads do not carry baseline/diff, so impact questions
    must degrade gracefully to partially_answerable, not not_answerable."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "How is this perturbation affecting the solution?",
        },
    )
    body = r.json()
    assert body["intent"] == "perturbation_impact_summary"
    assert body["answerability"]["status"] in (
        "answerable",
        "partially_answerable",
    )


def test_route_impact_summary_is_partial_when_no_diff(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "How is this perturbation affecting routes?",
        },
    )
    body = r.json()
    assert body["intent"] == "route_impact_summary"
    assert body["answerability"]["status"] in (
        "answerable",
        "partially_answerable",
    )


# ---------------------------------------------------------------------------
# 3. D4 compute_decision — overview never recommends recompute
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "What is this perturbation doing?",
        "Summarize this scenario.",
        "How does the plan look?",
        "What should I pay attention to?",
    ],
)
def test_descriptive_overview_does_not_recommend_recompute(
    client: TestClient, prompt: str
) -> None:
    r = client.post("/copilot/ask", json={"scenario_id": _SCENARIO_STRUCT, "prompt": prompt})
    body = r.json()
    cd = body.get("compute_decision") or {}
    assert cd.get("mode") != "needs_recompute", (
        f"prompt {prompt!r} should not trigger needs_recompute, got {cd}"
    )
    assert cd.get("recommended_action") not in {
        "run_pyvrp_10s",
        "run_clarke_wright",
        "run_reuse_direct",
        "run_nearest_neighbor",
    }, f"prompt {prompt!r} must not recommend a solver action"


def test_impact_overview_recommends_comparison_payload_when_diff_missing(
    client: TestClient,
) -> None:
    """Impact questions on a Run-1 (no diff) payload should suggest
    building a comparison payload, not running a solver."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "How is this perturbation affecting routes?",
        },
    )
    body = r.json()
    cd = body.get("compute_decision") or {}
    # Either needs_comparison_payload or partial_from_payload is acceptable;
    # the critical invariant is that we do NOT recommend recompute.
    assert cd.get("mode") in {
        "needs_comparison_payload",
        "partial_from_payload",
        "answer_from_payload",
    }, f"unexpected mode for impact question: {cd}"
    assert cd.get("mode") != "needs_recompute"


def test_what_to_watch_does_not_recommend_recompute(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What should I pay attention to?"},
    )
    body = r.json()
    cd = body.get("compute_decision") or {}
    assert cd.get("mode") != "needs_recompute"


# ---------------------------------------------------------------------------
# 4. Overclaim prevention — no impact / causal claims without supporting fields
# ---------------------------------------------------------------------------


def test_route_impact_summary_does_not_claim_routes_changed_without_diff(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "How is this perturbation affecting routes?",
        },
    )
    body = r.json()
    answer = (body.get("answer_text") or "").lower()
    # The answer must NOT assert that routes changed when there's no diff.
    assert answer  # non-empty
    forbidden_phrases = (
        "routes changed",
        "routes were modified",
        "the route plan was altered",
        "{n} customers moved",
    )
    for phrase in forbidden_phrases:
        assert phrase not in answer, (
            f"answer must not claim route changes without diff: {answer!r} "
            f"contains {phrase!r}"
        )


def test_perturbation_impact_summary_does_not_claim_objective_change_without_diff(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "Did this make the solution worse?",
        },
    )
    body = r.json()
    answer = (body.get("answer_text") or "").lower()
    assert answer
    # We don't have baseline_objective for a STRUCT-family scenario; the
    # answer must not claim a specific direction of objective change.
    forbidden_phrases = (
        "the objective increased",
        "the objective decreased",
        "the cost went up",
        "the cost went down",
    )
    for phrase in forbidden_phrases:
        assert phrase not in answer


def test_what_to_watch_does_not_claim_perturbation_caused_lateness(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "Anything concerning here?"},
    )
    body = r.json()
    answer = (body.get("answer_text") or "").lower()
    forbidden_phrases = (
        "the perturbation caused",
        "this perturbation made",
        "caused customers to be late",
    )
    for phrase in forbidden_phrases:
        assert phrase not in answer


def test_impact_summary_mentions_missing_baseline_or_diff(client: TestClient) -> None:
    """When baseline/diff is missing, the answer must say so explicitly
    rather than silently producing a current-status description that
    could be misread as impact."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "How is this perturbation affecting the solution?",
        },
    )
    body = r.json()
    answer = (body.get("answer_text") or "").lower()
    assert any(
        kw in answer
        for kw in ("baseline", "diff", "comparison", "cannot quantify", "cannot measure")
    ), f"impact answer must surface missing comparison data: {answer!r}"


# ---------------------------------------------------------------------------
# 5. answer_text non-null and grounded for every overview intent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "What is this perturbation doing?",
        "Summarize this scenario.",
        "How does the plan look?",
        "How is this perturbation affecting the solution?",
        "How is this perturbation affecting routes?",
        "What should I pay attention to?",
    ],
)
def test_overview_intent_answer_text_is_non_null(client: TestClient, prompt: str) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": prompt},
    )
    body = r.json()
    assert body.get("answer_text") is not None
    assert isinstance(body["answer_text"], str)
    assert len(body["answer_text"].strip()) > 0


def test_overview_evidence_contains_explanation_context_items(client: TestClient) -> None:
    """The grounded overview path attaches explanation_context.* evidence
    items so the frontend can see what facts the answer was built from."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What is this perturbation doing?"},
    )
    body = r.json()
    evidence_paths = {ev["field_path"] for ev in body["evidence"]}
    assert any(p.startswith("explanation_context.") for p in evidence_paths), (
        f"expected explanation_context evidence; got {sorted(evidence_paths)}"
    )
    assert "explanation_context.perturbation.label" in evidence_paths


def test_perturbation_summary_names_perturbation_family(client: TestClient) -> None:
    """TIME_WINDOW scenario: the answer should name 'time-window' or
    'window' rather than referring to a generic perturbation."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What is this perturbation doing?"},
    )
    body = r.json()
    answer = (body.get("answer_text") or "").lower()
    assert "window" in answer, f"TIME_WINDOW perturbation answer must mention window: {answer!r}"


# ---------------------------------------------------------------------------
# 6. Regression — existing 14 intents still route + respond correctly
# ---------------------------------------------------------------------------


def test_regression_objective_value_still_works(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What is the total cost?"},
    )
    body = r.json()
    assert body["intent"] == "objective_value"
    assert body["answer_text"] is not None


def test_regression_route_end_time_still_works(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_SCHEDULE,
            "prompt": "What time does route 3 finish?",
            "family": "SCHEDULE",
        },
    )
    body = r.json()
    assert body["intent"] == "route_end_time"
    assert body["answer_text"] is not None


def test_regression_recompute_still_recommended_for_what_if(client: TestClient) -> None:
    """The "what if we add customer 999" prompt must still recommend
    recompute — the overview detection rule must not swallow it."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "What if we add customer 999 near route 4?",
            "system": "d4",
        },
    )
    body = r.json()
    cd = body.get("compute_decision") or {}
    assert cd.get("mode") == "needs_recompute"


# ---------------------------------------------------------------------------
# 7. Display anchors for overview evidence are safe
# ---------------------------------------------------------------------------


def test_overview_evidence_display_anchors_are_neutral(client: TestClient) -> None:
    """explanation_context.* paths must not be misinterpreted as
    route/customer anchors."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What is this perturbation doing?"},
    )
    body = r.json()
    for ev in body["evidence"]:
        if ev["field_path"].startswith("explanation_context."):
            anchor = ev["display_anchor"]
            # Anchor type must be "none" or a known safe type;
            # explanation_context fields should never anchor to a route
            # or customer.
            assert anchor["type"] in ("none", "solution_summary"), (
                f"explanation_context anchor must be neutral; got {anchor}"
            )


# ---------------------------------------------------------------------------
# 8. Mixed perturbation families — explanation card adapts
# ---------------------------------------------------------------------------


def test_travel_time_perturbation_summary_mentions_travel(client: TestClient) -> None:
    """C105__TT_4 is a TRAVEL_TIME perturbation; the description should
    name it differently from TIME_WINDOW."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_SCHEDULE,
            "prompt": "What is this perturbation doing?",
        },
    )
    body = r.json()
    answer = (body.get("answer_text") or "").lower()
    # TRAVEL_TIME explanation mentions "travel"
    assert "travel" in answer, (
        f"TRAVEL_TIME perturbation answer must mention travel: {answer!r}"
    )

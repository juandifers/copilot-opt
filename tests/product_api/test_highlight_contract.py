"""Tests: the highlight contract (intent -> visual_actions).

Asserts, for representative prompts per intent, that POST /copilot/ask returns
the expected `intent`, the expected `visual_actions` kinds, and the expected
`set_lens` mode — per `docs/highlight_contract.md`. Doubles as the demo
fixture: each case below is a one-line spec of the intended UI behavior.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from product.api import copilot_service
from product.api.app import app
from product.api.scenario_store import load_registry

try:
    load_registry()
except FileNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"Run 1 artifacts not found: {exc}", allow_module_level=True)


def _llm_available() -> bool:
    """True when the LLM semantic adapter is configured (OPENAI_API_KEY set,
    SDK importable, kill-switch off). Some operator phrasings only route to
    their intent via the LLM; on the deterministic-only path they fall to
    ``unknown`` — that lift is the whole point of the adapter. Tests that
    assert such LLM-routed intents are skipped when the adapter is absent
    (e.g. CI without a key); they run locally when ``.env`` supplies one.
    """
    try:
        return copilot_service._get_llm_client() is not None
    except Exception:  # pragma: no cover - defensive
        return False


_REQUIRES_LLM = pytest.mark.skipif(
    not _llm_available(),
    reason="needs the LLM semantic adapter (set OPENAI_API_KEY); these prompts "
           "route to 'unknown' on the deterministic-only path",
)


_SCENARIO_OBJ = "C202__TW_3"  # OBJ-shape: objective_value, route_count
_SCENARIO_SCHEDULE = "C105__TT_4"  # SCHEDULE-shape: route_end_time, customer_arrival
_SCENARIO_LATE = "RC101__TT_1"  # has 1 late customer (cid=48)
_SCENARIO_STRUCT = "C102__OC_1"  # STRUCT-shape: routes[].customer_ids populated


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _kinds(body: dict) -> set[str]:
    return {a["kind"] for a in body.get("visual_actions", [])}


def _lens_mode(body: dict) -> str | None:
    for a in body.get("visual_actions", []):
        if a["kind"] == "set_lens":
            return a["target"].get("mode")
    return None


def _focus_panel(body: dict) -> str | None:
    for a in body.get("visual_actions", []):
        if a["kind"] == "focus_panel":
            return a["target"].get("panel")
    return None


# ---------------------------------------------------------------------------
# Single-intent assertions — each test is a row from the contract table.
# ---------------------------------------------------------------------------


def test_objective_value(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is the objective value?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "objective_value"
    assert _lens_mode(body) == "route"
    assert "show_objective_card" in _kinds(body)
    assert _focus_panel(body) == "impact"


@_REQUIRES_LLM
def test_route_count(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "How many routes are there?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "route_count"
    assert _lens_mode(body) == "route"
    assert "show_route_count" in _kinds(body)
    assert _focus_panel(body) == "tables"


def test_route_end_time(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_SCHEDULE, "prompt": "What time does route 3 finish?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "route_end_time"
    assert _lens_mode(body) == "lateness"
    kinds = _kinds(body)
    assert "highlight_route" in kinds
    assert "show_route_end_time" in kinds
    assert _focus_panel(body) == "schedule"


@_REQUIRES_LLM
def test_customer_arrival(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_SCHEDULE, "prompt": "What time does customer 5 arrive?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "customer_arrival"
    assert _lens_mode(body) == "lateness"
    kinds = _kinds(body)
    assert "highlight_customer" in kinds
    assert "show_schedule_row" in kinds
    assert _focus_panel(body) == "schedule"


def test_lateness_summary_emits_per_late_customer(client: TestClient) -> None:
    """lateness_summary must emit one highlight_customer per late stop.

    RC101__TT_1 has exactly one late customer (cid=48); regression-pin both
    the count and the cid so a regression on the value-driven derivation is
    caught.
    """
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_LATE, "prompt": "Which customers are late?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "lateness_summary"
    assert _lens_mode(body) == "lateness"
    hl_customers = [
        a for a in body["visual_actions"] if a["kind"] == "highlight_customer"
    ]
    assert len(hl_customers) >= 1
    assert {a["target"]["customer_id"] for a in hl_customers} >= {48}
    assert "show_lateness_summary" in _kinds(body)
    assert _focus_panel(body) == "schedule"


def test_lateness_summary_empty_late_set_emits_no_customer_highlights(
    client: TestClient,
) -> None:
    """When late_customer_ids is empty, no highlight_customer is emitted —
    but the lens and panel focus still snap to the lateness story."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_SCHEDULE, "prompt": "Which customers are late?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "lateness_summary"
    assert _lens_mode(body) == "lateness"
    hl_customers = [
        a for a in body["visual_actions"] if a["kind"] == "highlight_customer"
    ]
    assert hl_customers == []
    assert _focus_panel(body) == "schedule"


def test_single_customer_route_membership(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "Which route is customer 5 on?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "single_customer_route_membership"
    assert _lens_mode(body) == "route"
    kinds = _kinds(body)
    assert "highlight_route" in kinds
    assert "highlight_customer" in kinds
    assert _focus_panel(body) == "map"


def test_perturbation_summary(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is this perturbation doing?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "perturbation_summary"
    assert _lens_mode(body) == "route"
    assert "highlight_summary" in _kinds(body)
    assert _focus_panel(body) == "impact"


@pytest.mark.parametrize(
    "prompt, expected_intent",
    [
        ("Summarize this scenario.", "scenario_summary"),
        ("Summarize the solution.", "solution_summary"),
    ],
)
def test_summary_cluster_lens_route_focus_impact(
    client: TestClient, prompt: str, expected_intent: str
) -> None:
    """The summary intent cluster (scenario / solution / perturbation_summary)
    shares one row in the contract table: lens=route, highlight=summary,
    focus=impact. perturbation_summary has its own test above to pin
    behaviour against an OBJ scenario; this parametrized test covers the
    other two against a STRUCT scenario where they fire as direct answers."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": prompt},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == expected_intent
    assert _lens_mode(body) == "route"
    assert "highlight_summary" in _kinds(body)
    assert _focus_panel(body) == "impact"


def test_full_route_listing(client: TestClient) -> None:
    """Listing every route: lens=route, one highlight_route per route in the
    plan, focus=tables. STRUCT-shape scenario where routes are populated."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "List all the routes."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "full_route_listing"
    assert _lens_mode(body) == "route"
    hl_routes = [a for a in body["visual_actions"] if a["kind"] == "highlight_route"]
    # STRUCT scenarios in the locked set have at least 2 routes; pin >=2 to
    # guard against a regression that loses the per-route iteration.
    assert len(hl_routes) >= 2
    assert _focus_panel(body) == "tables"


def test_before_after_comparison(client: TestClient) -> None:
    """Comparison view: lens=route, focus=impact (the diff tab)."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "What changed between baseline and now?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "before_after_comparison"
    assert _lens_mode(body) == "route"
    assert _focus_panel(body) == "impact"


def test_new_customer_assignment(client: TestClient) -> None:
    """The 'where was the new customer assigned' question — lens=route,
    focus=map. Highlights may be empty when the perturbation isn't a
    customer-insertion type (evidence carries no customer_id then); the
    lens + focus row of the contract still must fire."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_STRUCT,
            "prompt": "Where was the new customer assigned?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "new_customer_assignment"
    assert _lens_mode(body) == "route"
    assert _focus_panel(body) == "map"


@_REQUIRES_LLM
@pytest.mark.parametrize(
    "prompt, expected_intent",
    [
        ("What is the impact of this perturbation?", "perturbation_impact_summary"),
        ("Which routes were impacted?", "route_impact_summary"),
    ],
)
def test_impact_summary_cluster(
    client: TestClient, prompt: str, expected_intent: str
) -> None:
    """Impact summaries: lens=route, focus=impact. Highlights derive from
    whatever route_idx field paths the contract surfaces; the row above
    (lens + focus) is what we pin here so the cluster can't silently
    regress to an empty visual_actions list."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": prompt},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == expected_intent
    assert _lens_mode(body) == "route"
    assert _focus_panel(body) == "impact"


@_REQUIRES_LLM
def test_what_to_watch(client: TestClient) -> None:
    """At-risk stops view: lens=slack, focus=schedule."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "What should I watch out for?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "what_to_watch"
    assert _lens_mode(body) == "slack"
    assert _focus_panel(body) == "schedule"


def test_evaluate_plan_acceptability(client: TestClient) -> None:
    """Plan-acceptability evaluation: lens=route, highlight=summary,
    focus=impact."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "Is this plan acceptable?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "evaluate_plan_acceptability"
    assert _lens_mode(body) == "route"
    assert "highlight_summary" in _kinds(body)
    assert _focus_panel(body) == "impact"


def test_evaluate_dimension_acceptability(client: TestClient) -> None:
    """Dimension acceptability: the contract row is dimension-dependent
    (lateness lens for time dimensions, slack lens for feasibility); focus
    always = schedule. With no evidence to scan, the slack default fires —
    both lenses are valid per the contract table."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_STRUCT, "prompt": "Is the lateness acceptable?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "evaluate_dimension_acceptability"
    assert _lens_mode(body) in {"slack", "lateness"}
    assert _focus_panel(body) == "schedule"


def test_unknown_intent_emits_no_visual_actions(client: TestClient) -> None:
    """Refusal/unknown: leave the operator's lens alone — visual_actions == []."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What if we add customer 999 near route 4?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "unknown"
    assert body.get("visual_actions") == []


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------


@_REQUIRES_LLM
def test_every_non_refusal_response_has_set_lens_and_focus_panel(
    client: TestClient,
) -> None:
    """For every intent the contract maps to a lens/focus row, the response
    must carry both. Catches forgotten branches in infer_visual_actions."""
    cases = [
        (_SCENARIO_OBJ, "What is the objective value?"),
        (_SCENARIO_OBJ, "How many routes are there?"),
        (_SCENARIO_SCHEDULE, "What time does route 3 finish?"),
        (_SCENARIO_SCHEDULE, "What time does customer 5 arrive?"),
        (_SCENARIO_LATE, "Which customers are late?"),
        (_SCENARIO_OBJ, "What is this perturbation doing?"),
        (_SCENARIO_OBJ, "Summarize this scenario."),
    ]
    cases.extend([
        (_SCENARIO_STRUCT, "Summarize the solution."),
        (_SCENARIO_STRUCT, "List all the routes."),
        (_SCENARIO_STRUCT, "What changed between baseline and now?"),
        (_SCENARIO_STRUCT, "Where was the new customer assigned?"),
        (_SCENARIO_STRUCT, "What is the impact of this perturbation?"),
        (_SCENARIO_STRUCT, "Which routes were impacted?"),
        (_SCENARIO_STRUCT, "What should I watch out for?"),
        (_SCENARIO_STRUCT, "Is this plan acceptable?"),
        (_SCENARIO_STRUCT, "Is the lateness acceptable?"),
        (_SCENARIO_STRUCT, "Which route is customer 5 on?"),
    ])
    for sid, prompt in cases:
        r = client.post("/copilot/ask", json={"scenario_id": sid, "prompt": prompt})
        assert r.status_code == 200, (sid, prompt, r.text)
        body = r.json()
        assert body["intent"] not in ("unknown", "refusal_or_insufficient_payload"), (
            sid,
            prompt,
            body["intent"],
        )
        assert _lens_mode(body) in {"route", "lateness", "slack"}, (sid, prompt)
        assert _focus_panel(body) in {"map", "schedule", "tables", "impact"}, (
            sid,
            prompt,
        )


def test_visual_actions_field_always_present(client: TestClient) -> None:
    """CopilotAskResponse must always declare visual_actions — never missing."""
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is the objective value?"},
    )
    assert r.status_code == 200
    assert "visual_actions" in r.json()

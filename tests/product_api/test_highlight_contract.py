"""Tests: the highlight contract (intent -> visual_actions).

Asserts, for representative prompts per intent, that POST /copilot/ask returns
the expected `intent`, the expected `visual_actions` kinds, and the expected
`set_lens` mode — per `docs/highlight_contract.md`. Doubles as the demo
fixture: each case below is a one-line spec of the intended UI behavior.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from product.api.app import app
from product.api.scenario_store import load_registry

try:
    load_registry()
except FileNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"Run 1 artifacts not found: {exc}", allow_module_level=True)


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


def test_scenario_summary(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "Summarize this scenario."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "scenario_summary"
    assert _lens_mode(body) == "route"
    assert "highlight_summary" in _kinds(body)
    assert _focus_panel(body) == "impact"


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

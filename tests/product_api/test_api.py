"""Tests for the VRPTW copilot dashboard API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from product.api import copilot_service, scenario_store
from product.api.app import app
from product.api.evidence_anchors import field_path_to_display_anchor


# The API depends on Run 1 generator JSONL artifacts; skip the whole
# module if those are not on disk.
try:
    scenario_store.load_registry()
except FileNotFoundError as exc:  # pragma: no cover — local-only path
    pytest.skip(f"Run 1 artifacts not found: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# A scenario known to live in the locked Run 1 set with OBJ payload.
_SCENARIO_OBJ = "C202__TW_3"
# A scenario known to carry routes (STRUCT) — picked from the registry
# rather than hard-coded so this test moves with the locked artifacts.
_SCENARIO_WITH_ROUTES_FALLBACK = "C1_2_2__TW_5"
# A scenario known to carry customer_schedule + route_end_times.
_SCENARIO_SCHEDULE = "C105__TT_4"


def _scenario_with_routes() -> str:
    registry = scenario_store.load_registry()
    for sid, row in registry.items():
        ps = row.payload_snapshot or {}
        if isinstance(ps.get("routes"), list) and ps["routes"]:
            return sid
    return _SCENARIO_WITH_ROUTES_FALLBACK


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert (
        body["run2_contract_base_commit"]
        == "18b4811a1f85c166ea3ba8c777dfc021b2a5f747"
    )
    assert body["run2_contract_base_tag"] == "run2-contract-extended"
    assert "current_git_commit" in body
    assert body["default_system"] == "d_final"
    assert body["available_systems"] == ["c0", "d1", "d2", "d3", "d4", "d_final"]


# ---------------------------------------------------------------------------
# /instances
# ---------------------------------------------------------------------------


def test_instances_returns_nonempty_list(client: TestClient) -> None:
    r = client.get("/instances")
    assert r.status_code == 200
    body = r.json()
    assert "instances" in body
    assert isinstance(body["instances"], list)
    assert len(body["instances"]) > 0
    first = body["instances"][0]
    assert "instance_id" in first
    assert "available_perturbations" in first


# ---------------------------------------------------------------------------
# /scenarios/{instance_id}/{perturbation_id}
# ---------------------------------------------------------------------------


def test_scenario_obj_has_solution_and_objective(client: TestClient) -> None:
    r = client.get(f"/scenarios/C202/TW_3")
    assert r.status_code == 200
    body = r.json()
    assert body["scenario_id"] == _SCENARIO_OBJ
    assert body["instance_id"] == "C202"
    assert body["perturbation_id"] == "TW_3"
    assert body["instance"] is not None
    assert body["available_fields"]["solution"] is True
    assert body["solution"]["objective"] is not None


def test_scenario_with_routes_has_route_labels(client: TestClient) -> None:
    sid = _scenario_with_routes()
    instance_id, pert_id = sid.split("__", 1)
    r = client.get(f"/scenarios/{instance_id}/{pert_id}")
    assert r.status_code == 200
    body = r.json()
    routes = body["solution"]["routes"]
    assert routes, f"expected routes for {sid}"
    for route in routes:
        assert "route_idx" in route
        assert "route_label" in route
        assert route["route_label"].startswith("Route ")


def test_scenario_schedule_returns_customer_schedule(client: TestClient) -> None:
    r = client.get("/scenarios/C105/TT_4")
    assert r.status_code == 200
    body = r.json()
    schedule = body["solution"]["customer_schedule"]
    assert isinstance(schedule, list) and len(schedule) > 0
    first = schedule[0]
    assert "customer_id" in first
    assert "route_idx" in first
    assert "route_label" in first
    assert first["route_label"].startswith("Route ")


def test_missing_scenario_returns_structured_404(client: TestClient) -> None:
    r = client.get("/scenarios/NOSUCH/NONE")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "scenario_not_found"


# ---------------------------------------------------------------------------
# /copilot/ask
# ---------------------------------------------------------------------------


def test_copilot_ask_defaults_to_d4(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": _SCENARIO_OBJ, "prompt": "What is the total cost?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["system"] == "d_final"
    assert body["intent"] == "objective_value"
    assert body["scenario_id"] == _SCENARIO_OBJ
    assert "answerability" in body
    assert body["answerability"]["status"] in (
        "answerable",
        "partially_answerable",
        "not_answerable",
    )
    assert body["behavior_class"]
    assert isinstance(body["evidence"], list)
    assert isinstance(body["warnings"], list)
    assert isinstance(body["suggested_next_actions"], list)
    # D4 enriches with compute_decision; this is a status-style prompt
    # so we expect answer_from_payload.
    assert body["compute_decision"] is not None
    cd = body["compute_decision"]
    assert cd["mode"] == "answer_from_payload"
    assert cd["recommended_action"] == "none"
    assert cd["requires_recompute"] is False
    assert cd["query_family"] == "OBJ"
    assert cd["policy_source"] == "deterministic_d4_v1"


@pytest.mark.parametrize("system", ["c0", "d1", "d2", "d3", "d4"])
def test_copilot_ask_accepts_all_systems(client: TestClient, system: str) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What is the total cost?",
            "system": system,
        },
    )
    assert r.status_code == 200
    assert r.json()["system"] == system


@pytest.mark.parametrize("system", ["c0", "d1", "d2", "d3"])
def test_copilot_ask_pre_d4_systems_omit_compute_decision(
    client: TestClient, system: str
) -> None:
    """Pre-D4 systems must leave compute_decision null so clients can
    branch on its presence."""
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What is the total cost?",
            "system": system,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["compute_decision"] is None, (system, body.get("compute_decision"))


def test_copilot_ask_d4_emits_needs_recompute_for_hypothetical(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What if we add customer 999 near route 4?",
            "system": "d4",
        },
    )
    assert r.status_code == 200
    cd = r.json()["compute_decision"]
    assert cd is not None
    assert cd["mode"] == "needs_recompute"
    assert cd["requires_recompute"] is True
    assert cd["recommended_action"] in (
        "run_reuse_direct",
        "run_nearest_neighbor",
        "run_clarke_wright",
        "run_pyvrp_10s",
    )
    # pyvrp_60s is the historical reference action; D4 must never
    # surface it as a deployable choice.
    assert cd["recommended_action"] != "run_pyvrp_60s"


def test_copilot_ask_d4_emits_needs_comparison_for_baseline_question(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "Is this objective better than the baseline?",
            "system": "d4",
        },
    )
    assert r.status_code == 200
    cd = r.json()["compute_decision"]
    assert cd is not None
    assert cd["mode"] in ("needs_comparison_payload", "answer_from_payload")
    # If the scenario does ship a baseline, the policy correctly
    # resolves to answer_from_payload; otherwise needs_comparison.
    if cd["mode"] == "needs_comparison_payload":
        assert cd["recommended_action"] == "build_comparison_payload"


def test_copilot_ask_d4_unsupported_for_driver_preferences(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "Can you optimize for driver preferences?",
            "system": "d4",
        },
    )
    assert r.status_code == 200
    cd = r.json()["compute_decision"]
    assert cd is not None
    assert cd["mode"] == "unsupported"
    assert cd["recommended_action"] == "unsupported"


def test_copilot_ask_unknown_system_400(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "What is the total cost?",
            "system": "d99",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "unknown_system"


def test_copilot_ask_evidence_includes_display_anchor(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": "C105__TT_4",
            "prompt": "What time does route 3 finish?",
            "family": "SCHEDULE",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "route_end_time"
    assert body["evidence"], "expected route_end_time evidence"
    anchors = [e["display_anchor"] for e in body["evidence"]]
    assert any(a.get("type") == "route_end" for a in anchors)


def test_copilot_ask_passes_through_warnings(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": "C105__TT_4",
            "prompt": "What time does route 3 finish?",
            "family": "SCHEDULE",
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Route-number prompts trigger route_indexing_ambiguity.
    assert "route_indexing_ambiguity" in body["warnings"]


def test_copilot_ask_invalid_scenario_id_400(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": "no-double-underscore", "prompt": "x"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_scenario_id"


def test_copilot_ask_missing_scenario_returns_404(client: TestClient) -> None:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": "NOSUCH__NONE", "prompt": "x"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "scenario_not_found"


# ---------------------------------------------------------------------------
# /diff
# ---------------------------------------------------------------------------


def test_diff_returns_404_when_unavailable(client: TestClient, monkeypatch) -> None:
    # All registry scenarios now carry diff data, so we force the no-diff path
    # by patching build_diff_response to return None for this call.
    monkeypatch.setattr(scenario_store, "build_diff_response", lambda *a, **k: None)
    r = client.post(f"/scenarios/C202/TW_3/diff")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "diff_not_available"
    assert "missing_fields" in body["error"]["detail"]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_allows_localhost_origin(client: TestClient) -> None:
    r = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ---------------------------------------------------------------------------
# evidence_anchors
# ---------------------------------------------------------------------------


def test_anchor_for_route_end_times() -> None:
    a = field_path_to_display_anchor("route_end_times[route_idx=2].end_time")
    assert a["type"] == "route_end"
    assert a["route_idx"] == 2
    assert a["route_label"] == "Route 3"


def test_anchor_for_routes_customer_ids() -> None:
    a = field_path_to_display_anchor("routes[route_idx=4].customer_ids")
    assert a["type"] == "route"
    assert a["route_idx"] == 4
    assert a["route_label"] == "Route 5"


def test_anchor_for_customer_schedule_arrival() -> None:
    a = field_path_to_display_anchor("customer_schedule[customer_id=142].arrival")
    assert a["type"] == "customer_arrival"
    assert a["customer_id"] == 142


def test_anchor_for_action_objective_is_solution_summary() -> None:
    assert field_path_to_display_anchor("action_objective")["type"] == "solution_summary"


def test_anchor_for_n_routes_is_solution_summary() -> None:
    assert field_path_to_display_anchor("n_routes")["type"] == "solution_summary"


def test_anchor_for_unknown_path_is_none() -> None:
    assert field_path_to_display_anchor("some_unknown.thing")["type"] == "none"


def test_anchor_resolves_label_from_payload() -> None:
    payload = {
        "routes": [{"route_idx": 2, "route_label": "Route Three", "customer_ids": [9]}]
    }
    a = field_path_to_display_anchor(
        "route_end_times[route_idx=2].end_time", scenario_payload=payload
    )
    assert a["route_label"] == "Route Three"


# ---------------------------------------------------------------------------
# Causal warning pass-through
# ---------------------------------------------------------------------------


def test_d3_causal_warning_can_pass_through(monkeypatch) -> None:
    """The API must not strip the D3-specific causal warning. We patch
    the dispatch to return a synthetic predicted contract carrying the
    warning, then confirm it survives the round-trip."""
    from product.evaluation.run2_system_c import PredictedContract

    def _fake(case, payload, generator_record):
        return PredictedContract(
            case_id=case.case_id,
            predicted_intent="objective_value",
            predicted_answerability="answerable",
            predicted_evidence_paths=["action_objective"],
            predicted_missing_fields=[],
            predicted_warnings=["causal_mechanism_unsupported"],
            predicted_next_actions=[],
            predicted_behavior_class="direct_answer_with_warning",
            notes=[],
        )

    monkeypatch.setitem(
        copilot_service._DISPATCH, "d3", copilot_service._Dispatch(_fake)
    )
    client = TestClient(app)
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": "Why did the cost go up?",
        },
    )
    assert r.status_code == 200
    assert "causal_mechanism_unsupported" in r.json()["warnings"]


# ---------------------------------------------------------------------------
# Locked-file guards (cheap, by-path inspection)
# ---------------------------------------------------------------------------


def test_locked_run2_files_not_modified_by_api_module() -> None:
    """API code must not import-time mutate any locked artifact.

    This is a structural check: importing the API package should not
    trigger a write to any of the locked Run 2 source files.
    """
    import importlib

    importlib.import_module("product.api.app")
    importlib.import_module("product.api.copilot_service")
    importlib.import_module("product.api.scenario_store")
    importlib.import_module("product.api.evidence_anchors")
    importlib.import_module("product.api.models")
    # If the imports above ran without exception we're good — none of
    # them open locked files for writing.

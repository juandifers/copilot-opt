"""D5 — tests for ui_actions on /copilot/ask and /scenarios/.../recompute.

Two layers of invariants:

1. ``/copilot/ask`` emits a recompute UI action when D4 says
   ``needs_recompute`` and never calls a solver.
2. ``/scenarios/{scenario_id}/recompute`` validates everything, refuses
   the ``pyvrp_60s`` family, returns a structured 501 for unimplemented
   deployable actions, and only proceeds when ``confirm == true``.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from product.api import copilot_service, recompute_service, scenario_store
from product.api.app import app


try:
    scenario_store.load_registry()
except FileNotFoundError as exc:  # pragma: no cover — local-only path
    pytest.skip(f"Run 1 artifacts not found: {exc}", allow_module_level=True)


_SCENARIO_OBJ = "C202__TW_3"            # answer_from_payload
_SCENARIO_RECOMPUTE = "C105__TT_4"      # used as the recompute target
# A scenario with routes in the payload — required for run_reuse_direct
# to have something to re-evaluate.
_SCENARIO_WITH_ROUTES = "C1_2_2__TW_5"


# Prompts that should be classified deterministically by D4.
_PROMPT_ANSWERABLE = "What is the objective value?"
_PROMPT_NEEDS_RECOMPUTE = "Find a better plan that reduces lateness."
_PROMPT_RECOMPUTE_REUSE = (
    "What happens if capacity drops by 10%? "
    "Is the current solution still feasible?"
)
# Triggers ``run_clarke_wright`` (implemented in this backend).
_PROMPT_RECOMPUTE_CW = "Run a cheap savings heuristic."
# Triggers ``run_nearest_neighbor`` (still unimplemented in this backend).
_PROMPT_RECOMPUTE_NN = (
    "Use a nearest-neighbor heuristic to reroute the plan."
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /copilot/ask — ui_actions
# ---------------------------------------------------------------------------


def test_ask_with_answerable_prompt_emits_empty_ui_actions(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_OBJ,
            "prompt": _PROMPT_ANSWERABLE,
            "system": "d4",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compute_decision"]["mode"] != "needs_recompute"
    assert body["ui_actions"] == []


def test_ask_with_recompute_prompt_emits_recompute_ui_action(
    client: TestClient,
) -> None:
    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_RECOMPUTE,
            "prompt": _PROMPT_NEEDS_RECOMPUTE,
            "system": "d4",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compute_decision"]["mode"] == "needs_recompute"

    actions = body["ui_actions"]
    assert isinstance(actions, list) and len(actions) == 1, actions
    action = actions[0]
    assert action["type"] == "recompute"
    assert action["label"]
    assert action["action"] == body["compute_decision"]["recommended_action"]
    assert action["enabled"] is True
    assert action["requires_confirmation"] is True
    assert action["method"] == "POST"
    assert action["endpoint"] == f"/scenarios/{_SCENARIO_RECOMPUTE}/recompute"
    # expected_runtime_seconds is a float when the action is one of the
    # deployable rungs.
    assert isinstance(action["expected_runtime_seconds"], (int, float))


# ---------------------------------------------------------------------------
# Solver-execution invariant
# ---------------------------------------------------------------------------


def test_ask_does_not_call_solver_even_on_recompute_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``/copilot/ask`` endpoint MUST NOT run a solver.

    We patch the recompute-service execution entry points and assert
    none are invoked while we hit ``/copilot/ask`` with a recompute-
    triggering prompt.
    """
    calls: list[str] = []

    def _boom(*args: Any, **kwargs: Any):
        calls.append("execute_recompute_action")
        raise AssertionError("/copilot/ask must not run a solver")

    monkeypatch.setattr(
        recompute_service, "execute_recompute_action", _boom
    )
    monkeypatch.setattr(
        recompute_service, "run_recompute", _boom
    )

    r = client.post(
        "/copilot/ask",
        json={
            "scenario_id": _SCENARIO_RECOMPUTE,
            "prompt": _PROMPT_NEEDS_RECOMPUTE,
            "system": "d4",
        },
    )
    assert r.status_code == 200
    assert calls == [], "no solver path may execute under /copilot/ask"


# ---------------------------------------------------------------------------
# /recompute — validation
# ---------------------------------------------------------------------------


def _post_recompute(client: TestClient, scenario_id: str, **body) -> Any:
    instance_id, perturbation_id = scenario_id.split("__", 1)
    return client.post(
        f"/scenarios/{instance_id}/{perturbation_id}/recompute",
        json=body,
    )


def test_recompute_missing_confirm_returns_400(client: TestClient) -> None:
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_pyvrp_10s",
        confirm=False,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "confirmation_required"


def test_recompute_unknown_scenario_returns_404(client: TestClient) -> None:
    r = client.post(
        "/scenarios/NOPE_INSTANCE/TW_999/recompute",
        json={
            "prompt": _PROMPT_NEEDS_RECOMPUTE,
            "requested_action": "run_pyvrp_10s",
            "confirm": True,
        },
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "scenario_not_found"


def test_recompute_invalid_action_returns_400(client: TestClient) -> None:
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_made_up_action",
        confirm=True,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid_action"


def test_recompute_forbidden_pyvrp_60s_returns_400(client: TestClient) -> None:
    for forbidden in ("pyvrp_60s", "run_pyvrp_60s", "pyvrp_60s_seed2"):
        r = _post_recompute(
            client,
            _SCENARIO_RECOMPUTE,
            prompt=_PROMPT_NEEDS_RECOMPUTE,
            requested_action=forbidden,
            confirm=True,
        )
        assert r.status_code == 400, (forbidden, r.text)
        assert r.json()["error"]["code"] == "forbidden_action", forbidden


def test_recompute_action_mismatch_returns_409(client: TestClient) -> None:
    # D4 recommends run_pyvrp_10s for "find a better plan". Asking for
    # run_clarke_wright instead must be rejected.
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_clarke_wright",
        confirm=True,
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"]["code"] == "action_mismatch"
    assert body["error"]["detail"]["requested_action"] == "run_clarke_wright"
    assert body["error"]["detail"]["recommended_action"] == "run_pyvrp_10s"


def test_recompute_not_recommended_for_answerable_prompt_returns_409(
    client: TestClient,
) -> None:
    r = _post_recompute(
        client,
        _SCENARIO_OBJ,
        prompt=_PROMPT_ANSWERABLE,
        requested_action="run_pyvrp_10s",
        confirm=True,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "recompute_not_recommended"


def test_recompute_invalid_perturbation_returns_400(client: TestClient) -> None:
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_pyvrp_10s",
        perturbation={"type": "made_up_perturbation"},
        confirm=True,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid_perturbation"


def test_recompute_perturbation_missing_required_fields_returns_400(
    client: TestClient,
) -> None:
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_pyvrp_10s",
        perturbation={"type": "insert_customer"},
        confirm=True,
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "invalid_perturbation"
    assert "customer" in body["error"]["detail"]["missing"]


def test_recompute_unimplemented_action_returns_501(client: TestClient) -> None:
    # ``run_nearest_neighbor`` is on the deployable ladder but is not
    # implemented in this local-dev backend.
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_RECOMPUTE_NN,
        requested_action="run_nearest_neighbor",
        confirm=True,
    )
    assert r.status_code == 501, r.text
    body = r.json()
    assert body["error"]["code"] == "action_not_implemented"
    assert "run_nearest_neighbor" in body["error"]["detail"]["allowed_actions"]
    assert "run_pyvrp_10s" in body["error"]["detail"]["implemented_actions"]
    assert "run_reuse_direct" in body["error"]["detail"]["implemented_actions"]
    assert "run_clarke_wright" in body["error"]["detail"]["implemented_actions"]


def test_recompute_reuse_direct_without_routes_returns_400(
    client: TestClient,
) -> None:
    """``run_reuse_direct`` needs routes to re-evaluate.

    ``C105__TT_4`` has customer_schedule but no routes block, so the
    executor must refuse with a structured 400 rather than crashing.
    """
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_RECOMPUTE_REUSE,
        requested_action="run_reuse_direct",
        confirm=True,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "payload_missing_routes"


# ---------------------------------------------------------------------------
# Solver-execution invariant on validation-only paths
# ---------------------------------------------------------------------------


def test_validation_errors_do_not_call_executor(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def _boom(*args: Any, **kwargs: Any):
        calls.append("execute_recompute_action")
        raise AssertionError("executor must not run on validation errors")

    monkeypatch.setattr(
        recompute_service, "execute_recompute_action", _boom
    )

    # Each of these is a pre-execute validation failure.
    _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_pyvrp_10s",
        confirm=False,
    )
    _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="pyvrp_60s",
        confirm=True,
    )
    _post_recompute(
        client,
        _SCENARIO_OBJ,
        prompt=_PROMPT_ANSWERABLE,
        requested_action="run_pyvrp_10s",
        confirm=True,
    )

    assert calls == []


# ---------------------------------------------------------------------------
# /recompute — success path (skip if solver dependencies missing)
# ---------------------------------------------------------------------------


_PYVRP_AVAILABLE = True
try:
    import pyvrp  # noqa: F401
    import vrplib  # noqa: F401
except Exception:  # noqa: BLE001
    _PYVRP_AVAILABLE = False


@pytest.mark.skipif(
    not _PYVRP_AVAILABLE,
    reason="pyvrp / vrplib not installed; cannot evaluate routes",
)
def test_recompute_clarke_wright_success(client: TestClient) -> None:
    """``run_clarke_wright`` constructs a new plan and evaluates it.

    The evaluator may report VRPTW infeasibility (the savings heuristic
    is CVRP-style and ignores time windows during construction); the
    response must surface that honestly rather than hiding it.
    """
    r = _post_recompute(
        client,
        _SCENARIO_WITH_ROUTES,
        prompt=_PROMPT_RECOMPUTE_CW,
        requested_action="run_clarke_wright",
        confirm=True,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["source_scenario_id"] == _SCENARIO_WITH_ROUTES
    assert body["action_used"] == "run_clarke_wright"
    assert body["new_scenario_id"].startswith(
        f"{_SCENARIO_WITH_ROUTES}__run_clarke_wright__"
    )

    summary = body["summary"]
    assert isinstance(summary.get("feasible"), bool)
    assert isinstance(summary.get("objective"), (int, float))
    assert summary["n_routes"] >= 1
    # CW response surfaces the same feasibility breakdown as reuse_direct
    # so the operator can see *which* constraint failed.
    assert "feasible_capacity_only" in summary
    assert "feasible_tw_only" in summary
    assert "n_unserved_customers" in summary

    # Runtime artifacts live under the gitignored runtime directory.
    scenario_path = body["artifacts"]["scenario_path"]
    assert "product/api/runtime/recompute_runs" in scenario_path

    # Runtime scenario is loadable and carries route assignments.
    new_id = body["new_scenario_id"]
    r2 = client.get(f"/recompute_runs/{new_id}")
    assert r2.status_code == 200, r2.text
    doc = r2.json()
    assert doc["scenario_id"] == new_id
    solution = doc.get("solution") or {}
    routes = solution.get("routes") or []
    assert routes, "CW must produce at least one route"
    assert all("customer_ids" in r for r in routes)


@pytest.mark.skipif(
    not _PYVRP_AVAILABLE,
    reason="pyvrp / vrplib not installed; cannot evaluate routes",
)
def test_recompute_clarke_wright_reports_infeasibility_honestly(
    client: TestClient,
) -> None:
    """When the CW plan violates VRPTW time windows, the response must
    report it — no silent feasibility-flag fudging.

    The Solomon C-series is tight on time windows; the CVRP-style CW
    construction reliably trips the TW constraint on C1_2_2.
    """
    r = _post_recompute(
        client,
        _SCENARIO_WITH_ROUTES,
        prompt=_PROMPT_RECOMPUTE_CW,
        requested_action="run_clarke_wright",
        confirm=True,
    )
    assert r.status_code == 200, r.text
    summary = r.json()["summary"]
    # If the plan happens to be feasible, great — but if it is NOT
    # feasible overall, the per-constraint flags must back that up.
    if summary["feasible"] is False:
        assert (
            summary["feasible_tw_only"] is False
            or summary["feasible_capacity_only"] is False
            or summary["n_unserved_customers"] > 0
        ), (
            "feasible=False must have a per-constraint cause; "
            f"summary={summary}"
        )
    # Either way, late_customers is a non-negative int.
    assert isinstance(summary["n_late_customers"], int)
    assert summary["n_late_customers"] >= 0


def test_recompute_clarke_wright_rejects_perturbation_overlay(
    client: TestClient,
) -> None:
    """Request-level perturbation overlay is not implemented for any
    executor; the CW path must surface the same 501."""
    r = _post_recompute(
        client,
        _SCENARIO_WITH_ROUTES,
        prompt=_PROMPT_RECOMPUTE_CW,
        requested_action="run_clarke_wright",
        perturbation={"type": "capacity_drop", "new_capacity": 180},
        confirm=True,
    )
    assert r.status_code == 501, r.text
    assert (
        r.json()["error"]["code"]
        == "perturbation_application_not_implemented"
    )


@pytest.mark.skipif(
    not _PYVRP_AVAILABLE,
    reason="pyvrp / vrplib not installed; cannot evaluate routes",
)
def test_recompute_reuse_direct_success(client: TestClient) -> None:
    """``run_reuse_direct`` re-evaluates the source payload's routes
    against the loaded VRPTW instance and materializes a new scenario.

    The source scenario must have routes in its payload.
    """
    r = _post_recompute(
        client,
        _SCENARIO_WITH_ROUTES,
        prompt=_PROMPT_RECOMPUTE_REUSE,
        requested_action="run_reuse_direct",
        confirm=True,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["source_scenario_id"] == _SCENARIO_WITH_ROUTES
    assert body["action_used"] == "run_reuse_direct"
    assert body["new_scenario_id"].startswith(
        f"{_SCENARIO_WITH_ROUTES}__run_reuse_direct__"
    )

    summary = body["summary"]
    assert "feasible" in summary
    assert "objective" in summary
    assert summary["n_routes"] >= 1
    # reuse_direct exposes capacity/TW breakdown for diagnostic display.
    assert "feasible_capacity_only" in summary
    assert "feasible_tw_only" in summary
    assert "n_unserved_customers" in summary

    # The runtime scenario can be loaded back.
    new_id = body["new_scenario_id"]
    r2 = client.get(f"/recompute_runs/{new_id}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["scenario_id"] == new_id


@pytest.mark.skipif(
    not _PYVRP_AVAILABLE,
    reason="pyvrp / vrplib not installed; cannot run a real solve",
)
def test_recompute_success_writes_runtime_artifacts(
    client: TestClient,
) -> None:
    r = _post_recompute(
        client,
        _SCENARIO_RECOMPUTE,
        prompt=_PROMPT_NEEDS_RECOMPUTE,
        requested_action="run_pyvrp_10s",
        confirm=True,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["source_scenario_id"] == _SCENARIO_RECOMPUTE
    assert body["new_scenario_id"].startswith(
        f"{_SCENARIO_RECOMPUTE}__run_pyvrp_10s__"
    )
    assert body["action_used"] == "run_pyvrp_10s"
    assert body["runtime_seconds"] > 0.0
    assert body["summary"]["n_routes"] >= 1
    assert "objective" in body["summary"]

    # Artifacts written under the runtime directory.
    scenario_path = body["artifacts"]["scenario_path"]
    payload_path = body["artifacts"]["payload_path"]
    assert "product/api/runtime/recompute_runs" in scenario_path
    assert "product/api/runtime/recompute_runs" in payload_path

    # The runtime scenario can be loaded back by id.
    new_id = body["new_scenario_id"]
    r2 = client.get(f"/recompute_runs/{new_id}")
    assert r2.status_code == 200, r2.text
    scenario_doc = r2.json()
    assert scenario_doc["scenario_id"] == new_id


# ---------------------------------------------------------------------------
# Service-layer unit tests — independent of FastAPI
# ---------------------------------------------------------------------------


def test_allowed_actions_match_d4_deployable_set() -> None:
    from product.evaluation.system_d4 import DEPLOYABLE_RECOMPUTE_ACTIONS

    assert recompute_service.ALLOWED_ACTIONS == DEPLOYABLE_RECOMPUTE_ACTIONS


def test_implemented_actions_include_clarke_wright() -> None:
    assert "run_clarke_wright" in recompute_service.IMPLEMENTED_ACTIONS
    assert "run_pyvrp_10s" in recompute_service.IMPLEMENTED_ACTIONS
    assert "run_reuse_direct" in recompute_service.IMPLEMENTED_ACTIONS
    # Nearest-neighbor is still unimplemented; pinning this keeps the
    # 501 test honest.
    assert (
        "run_nearest_neighbor" not in recompute_service.IMPLEMENTED_ACTIONS
    )


def test_pyvrp_60s_family_is_forbidden() -> None:
    forbidden = recompute_service.FORBIDDEN_ACTIONS
    for name in (
        "pyvrp_60s",
        "run_pyvrp_60s",
        "pyvrp_60s_seed2",
        "pyvrp_60s_seed3",
    ):
        assert name in forbidden, name


def test_validate_request_rejects_pyvrp_60s_directly() -> None:
    with pytest.raises(recompute_service.RecomputeError) as exc:
        recompute_service.validate_recompute_request(
            scenario_id=_SCENARIO_RECOMPUTE,
            prompt=_PROMPT_NEEDS_RECOMPUTE,
            requested_action="pyvrp_60s",
            perturbation=None,
            confirm=True,
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "forbidden_action"

"""D5 — Operator-authorized recompute execution.

D5 sits behind the explicit ``POST /scenarios/{scenario_id}/recompute``
endpoint. It validates an operator-authorized recompute request, runs
the requested deployable action, and materializes the result as a new
runtime scenario the dashboard can load.

D4 *recommends* compute. D5 *executes* compute. Execution NEVER happens
inside ``/copilot/ask``; it only happens behind this endpoint and only
when the request carries ``confirm == true``.

The deployable ladder is closed::

    run_reuse_direct
    run_nearest_neighbor
    run_clarke_wright
    run_pyvrp_10s

``pyvrp_60s`` (and its seed-variants) is a benchmark reference solver
and is explicitly forbidden here — see ``FORBIDDEN_ACTIONS``.

Runtime artifacts are written under
``product/api/runtime/recompute_runs/<new_scenario_id>/`` and are
considered local-dev artifacts only: they are gitignored, safe to
delete, and not a source of benchmark truth.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from product.api import scenario_store
from product.evaluation.system_d4 import (
    DEPLOYABLE_RECOMPUTE_ACTIONS,
    decide_compute,
)


# ---------------------------------------------------------------------------
# Public action whitelists / blacklists
# ---------------------------------------------------------------------------


#: Deployable recompute actions per D4 §7. Closed set; the D5 endpoint
#: refuses anything outside this set.
ALLOWED_ACTIONS: frozenset[str] = frozenset(DEPLOYABLE_RECOMPUTE_ACTIONS)


#: Actions explicitly forbidden by D5. ``pyvrp_60s`` and seed variants
#: were the benchmark's reference label generator, never a deployable
#: rung. The frontend must never receive a UI action for these; the
#: backend rejects them even if the request body asks for them.
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    [
        "pyvrp_60s",
        "run_pyvrp_60s",
        "pyvrp_60s_seed2",
        "pyvrp_60s_seed3",
        "run_pyvrp_60s_seed2",
        "run_pyvrp_60s_seed3",
    ]
)


#: Subset of ALLOWED_ACTIONS that this local-dev backend can actually
#: execute. Other deployable actions return a structured 501.
IMPLEMENTED_ACTIONS: frozenset[str] = frozenset(
    ["run_pyvrp_10s", "run_reuse_direct", "run_clarke_wright"]
)


#: Policy source tag stamped into runtime metadata.
POLICY_SOURCE: str = "operator_authorized_d5_v1"


#: Hard upper bound on per-action runtime budget. Used to defend the
#: endpoint against being asked for arbitrarily long solves.
MAX_RUNTIME_SECONDS: float = 30.0


_RUNTIME_BUDGET_BY_ACTION: dict[str, float] = {
    "run_reuse_direct": 2.0,
    "run_nearest_neighbor": 2.0,
    "run_clarke_wright": 5.0,
    "run_pyvrp_10s": 12.0,
}


_EXECUTION_SEMANTICS: dict[str, str] = {
    "run_reuse_direct": "reuse_source_routes_and_evaluate_vrptw",
    "run_clarke_wright": (
        "construct_new_plan_with_clarke_wright_then_evaluate_vrptw"
    ),
    "run_pyvrp_10s": "fresh_pyvrp_solve_seed_1_10s_then_evaluate_vrptw",
}


# ---------------------------------------------------------------------------
# Runtime artifact location
# ---------------------------------------------------------------------------


_API_DIR = Path(__file__).resolve().parent


def runtime_root() -> Path:
    """Return the runtime root directory, creating it lazily.

    Lives at ``product/api/runtime/recompute_runs/`` by default. The
    directory is gitignored and may be deleted between runs.
    """
    root = _API_DIR / "runtime" / "recompute_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RecomputeError(Exception):
    """Structured recompute error.

    ``status_code`` is the HTTP status the API layer should emit;
    ``code`` is the stable machine-readable error code surfaced in the
    ``error.code`` envelope field.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_envelope(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": dict(self.detail),
            }
        }


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------


@dataclass
class RecomputeResponse:
    status: str
    source_scenario_id: str
    new_scenario_id: str
    action_used: str
    runtime_seconds: float
    summary: dict
    artifacts: dict
    next_actions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source_scenario_id": self.source_scenario_id,
            "new_scenario_id": self.new_scenario_id,
            "action_used": self.action_used,
            "runtime_seconds": float(self.runtime_seconds),
            "summary": dict(self.summary),
            "artifacts": dict(self.artifacts),
            "next_actions": list(self.next_actions),
        }


# ---------------------------------------------------------------------------
# Perturbation validation
# ---------------------------------------------------------------------------


_PERTURBATION_TYPES = frozenset(
    [
        "insert_customer",
        "remove_customer",
        "change_demand",
        "tighten_time_window",
        "relax_time_window",
        "capacity_drop",
    ]
)

_REQUIRED_FIELDS_BY_PERT_TYPE: dict[str, tuple[str, ...]] = {
    "insert_customer": ("customer",),
    "remove_customer": ("customer_id",),
    "change_demand": ("customer_id", "new_demand"),
    "tighten_time_window": ("customer_id",),
    "relax_time_window": ("customer_id",),
    "capacity_drop": ("new_capacity",),
}


def _validate_perturbation(perturbation: Optional[dict]) -> Optional[dict]:
    """Validate a perturbation dict; raise RecomputeError if malformed."""
    if perturbation is None:
        return None
    if not isinstance(perturbation, dict):
        raise RecomputeError(
            400,
            "invalid_perturbation",
            "perturbation must be an object.",
            {"got_type": type(perturbation).__name__},
        )
    ptype = perturbation.get("type")
    if not isinstance(ptype, str) or ptype not in _PERTURBATION_TYPES:
        raise RecomputeError(
            400,
            "invalid_perturbation",
            "perturbation.type is missing or unknown.",
            {
                "type": ptype,
                "allowed_types": sorted(_PERTURBATION_TYPES),
            },
        )
    missing = [
        f for f in _REQUIRED_FIELDS_BY_PERT_TYPE[ptype]
        if f not in perturbation
    ]
    if missing:
        raise RecomputeError(
            400,
            "invalid_perturbation",
            f"perturbation of type {ptype!r} is missing required fields.",
            {"missing": missing},
        )
    return dict(perturbation)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _normalize_action(name: Optional[str]) -> str:
    if not isinstance(name, str) or not name:
        raise RecomputeError(
            400,
            "invalid_action",
            "requested_action is required.",
            {"requested_action": name},
        )
    n = name.strip()
    if n in FORBIDDEN_ACTIONS:
        raise RecomputeError(
            400,
            "forbidden_action",
            (
                f"Action {n!r} is forbidden. The pyvrp_60s family is a "
                "benchmark reference solver and is never deployable."
            ),
            {
                "requested_action": n,
                "forbidden_actions": sorted(FORBIDDEN_ACTIONS),
            },
        )
    if n not in ALLOWED_ACTIONS:
        raise RecomputeError(
            400,
            "invalid_action",
            f"Action {n!r} is not a deployable recompute action.",
            {
                "requested_action": n,
                "allowed_actions": sorted(ALLOWED_ACTIONS),
            },
        )
    return n


@dataclass
class ValidatedRequest:
    """Outcome of ``validate_recompute_request``."""

    scenario_row: scenario_store.ScenarioRow
    payload: Optional[dict]
    prompt: str
    action: str
    perturbation: Optional[dict]
    d4_recommended_action: str
    d4_mode: str
    budget_seconds: float


def validate_recompute_request(
    scenario_id: str,
    prompt: str,
    requested_action: str,
    perturbation: Optional[dict],
    confirm: bool,
    *,
    require_d4_match: bool = True,
) -> ValidatedRequest:
    """Validate a recompute request without executing anything.

    Raises ``RecomputeError`` with an appropriate status code on any
    rule violation. Returns a ``ValidatedRequest`` on success.

    The default ``require_d4_match=True`` rejects requests whose
    ``requested_action`` does not match D4's ``recommended_action``;
    set ``require_d4_match=False`` to allow overriding (currently not
    exposed by the API).
    """
    if confirm is not True:
        raise RecomputeError(
            400,
            "confirmation_required",
            (
                "Recompute is an explicit operator-authorized action. "
                "Send confirm=true to acknowledge."
            ),
            {"confirm": confirm},
        )

    if not isinstance(scenario_id, str) or "__" not in scenario_id:
        raise RecomputeError(
            400,
            "invalid_scenario_id",
            "scenario_id must be '<instance_id>__<perturbation_id>'.",
            {"scenario_id": scenario_id},
        )
    instance_id, perturbation_id = scenario_id.split("__", 1)

    try:
        row = scenario_store.get_scenario_row(instance_id, perturbation_id)
    except scenario_store.ScenarioNotFound as exc:
        raise RecomputeError(
            404,
            "scenario_not_found",
            f"Scenario {scenario_id!r} is not in the registry.",
            {"scenario_id": scenario_id},
        ) from exc

    payload = scenario_store.augmented_payload(row)

    action = _normalize_action(requested_action)
    pert = _validate_perturbation(perturbation)

    if not isinstance(prompt, str) or not prompt.strip():
        raise RecomputeError(
            400,
            "invalid_prompt",
            "prompt is required for a recompute request.",
            {"prompt": prompt},
        )

    # Re-run D4 on the prompt + current payload. D4 is deterministic
    # and cheap; running it here means a frontend cannot trick the
    # backend into calling a solver on a prompt D4 would have refused.
    decision = decide_compute(
        prompt_text=prompt,
        intent=None,
        answerability_status=None,
        warnings=[],
        payload=payload,
    )
    if decision.mode != "needs_recompute":
        raise RecomputeError(
            409,
            "recompute_not_recommended",
            (
                "The current D4 policy does not recommend recomputation "
                "for this prompt."
            ),
            {
                "mode": decision.mode,
                "recommended_action": decision.recommended_action,
            },
        )

    if require_d4_match and action != decision.recommended_action:
        raise RecomputeError(
            409,
            "action_mismatch",
            "Requested action does not match the D4 recommended action.",
            {
                "requested_action": action,
                "recommended_action": decision.recommended_action,
            },
        )

    budget = _RUNTIME_BUDGET_BY_ACTION.get(action, MAX_RUNTIME_SECONDS)
    if budget > MAX_RUNTIME_SECONDS:
        budget = MAX_RUNTIME_SECONDS

    return ValidatedRequest(
        scenario_row=row,
        payload=payload,
        prompt=prompt,
        action=action,
        perturbation=pert,
        d4_recommended_action=decision.recommended_action,
        d4_mode=decision.mode,
        budget_seconds=budget,
    )


# ---------------------------------------------------------------------------
# Execution adapters
# ---------------------------------------------------------------------------


def _pyvrp_10s_executor(req: ValidatedRequest) -> dict:
    """Execute ``run_pyvrp_10s`` against the loaded VRPTW instance.

    This local-dev demo solves the underlying *unperturbed* VRPTW
    instance fresh with PyVRP, 10-second time limit, seed=1. Applying
    a request-level perturbation on top of the loaded instance is not
    yet implemented and will return a 501 if requested; the future
    perturbation editor is documented as D5 follow-up work.
    """
    if req.perturbation is not None:
        raise RecomputeError(
            501,
            "perturbation_application_not_implemented",
            (
                "Applying a request-level perturbation on top of the "
                "loaded VRPTW instance is not implemented in this local "
                "demo backend."
            ),
            {"perturbation_type": req.perturbation.get("type")},
        )

    try:
        from product.data.instance_geom import _resolve_instance_dir  # noqa: WPS450
        from vrp_copilot_bench.vrptw_instances import load_vrptw_instance
        from vrp_copilot_bench.vrptw.solver import SolveConfig, solve_vrptw
    except Exception as exc:  # noqa: BLE001 — dependencies are optional in CI
        raise RecomputeError(
            501,
            "action_not_implemented",
            (
                "Solver dependencies are not available in this "
                "environment; cannot execute run_pyvrp_10s."
            ),
            {
                "requested_action": req.action,
                "import_error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc

    instance_id = req.scenario_row.instance_id
    try:
        inst_dir = _resolve_instance_dir(instance_id)
        instance = load_vrptw_instance(instance_id, instance_dir=inst_dir)
    except FileNotFoundError as exc:
        raise RecomputeError(
            404,
            "instance_geometry_not_found",
            f"VRPTW instance geometry not found for {instance_id!r}.",
            {"instance_id": instance_id},
        ) from exc

    config = SolveConfig(time_limit_seconds=10.0, seed=1)
    t0 = time.perf_counter()
    result = solve_vrptw(instance, config)
    runtime = time.perf_counter() - t0

    n_routes = result.n_routes
    n_late = 0
    for rs in getattr(result, "route_summaries", []) or []:
        n_late += int(getattr(rs, "n_late_customers", 0) or 0)

    summary = {
        "feasible": bool(result.feasible),
        "objective": float(result.objective),
        "n_routes": int(n_routes),
        "n_late_customers": int(n_late),
    }
    solution_block = _solution_block_from_vrptw_result(result, instance)
    return {
        "summary": summary,
        "runtime_seconds": float(runtime),
        "solution_block": solution_block,
    }


def _clarke_wright_executor(req: ValidatedRequest) -> dict:
    """Execute ``run_clarke_wright`` against the loaded VRPTW instance.

    Pipeline:

    1. Load the underlying VRPTW instance from disk.
    2. Build the unmasked integer Euclidean distance matrix via the
       existing CVRP helper (the matrix is fed to the constructive
       savings heuristic only — the VRPTW evaluator builds its own
       scaled matrix downstream).
    3. Call the existing ``clarke_wright.construct`` (which only needs
       ``n_customers``, ``capacity``, ``demands`` — fields the
       VRPTW instance exposes) to produce a CVRP-style route plan.
    4. Pass the routes through ``evaluate_vrptw_solution`` so the
       reported objective and feasibility honor time windows and
       service times. Routes that violate time windows still
       materialize — the response surface them as
       ``feasible_tw_only == False`` rather than hiding the result.

    Returns 501 if a request-level perturbation is provided, matching
    the convention used by the other executors.
    """
    if req.perturbation is not None:
        raise RecomputeError(
            501,
            "perturbation_application_not_implemented",
            (
                "Applying a request-level perturbation on top of the "
                "loaded VRPTW instance is not implemented in this local "
                "demo backend."
            ),
            {"perturbation_type": req.perturbation.get("type")},
        )

    try:
        from product.data.instance_geom import _resolve_instance_dir  # noqa: WPS450
        from vrp_copilot_bench.actions.evaluate import (
            build_perturbed_distance_matrix,
        )
        from vrp_copilot_bench.solvers.heuristics import (
            clarke_wright as cw_module,
        )
        from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import (
            SCALING_FACTOR,
        )
        from vrp_copilot_bench.vrptw.solver import evaluate_vrptw_solution
        from vrp_copilot_bench.vrptw_instances import load_vrptw_instance
    except Exception as exc:  # noqa: BLE001 — dependencies are optional in CI
        raise RecomputeError(
            501,
            "action_not_implemented",
            (
                "Solver dependencies are not available in this "
                "environment; cannot execute run_clarke_wright."
            ),
            {
                "requested_action": req.action,
                "import_error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc

    instance_id = req.scenario_row.instance_id
    try:
        inst_dir = _resolve_instance_dir(instance_id)
        instance = load_vrptw_instance(instance_id, instance_dir=inst_dir)
    except FileNotFoundError as exc:
        raise RecomputeError(
            404,
            "instance_geometry_not_found",
            f"VRPTW instance geometry not found for {instance_id!r}.",
            {"instance_id": instance_id},
        ) from exc

    t0 = time.perf_counter()
    try:
        distance_matrix = build_perturbed_distance_matrix(instance)
        routes = cw_module.construct(instance, distance_matrix)
    except Exception as exc:  # noqa: BLE001
        # The CVRP CW raises ActionFailure only on truly pathological
        # inputs (e.g. capacity == 0). Surface it as a structured 500
        # rather than crashing the worker.
        raise RecomputeError(
            500,
            "heuristic_failed",
            (
                "Clarke-Wright savings construction failed before "
                "producing any plan."
            ),
            {
                "instance_id": instance_id,
                "error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc

    if not routes:
        raise RecomputeError(
            500,
            "heuristic_empty_plan",
            "Clarke-Wright returned no routes.",
            {"instance_id": instance_id},
        )

    evaluation = evaluate_vrptw_solution(instance, routes)
    runtime = time.perf_counter() - t0

    summary = {
        "feasible": bool(evaluation.feasible),
        "objective": float(evaluation.objective) / SCALING_FACTOR,
        "n_routes": len(evaluation.routes),
        "n_late_customers": int(evaluation.n_late_customers),
        "feasible_capacity_only": bool(evaluation.feasible_capacity_only),
        "feasible_tw_only": bool(evaluation.feasible_tw_only),
        "n_unserved_customers": len(evaluation.unserved_customers),
    }
    solution_block = _solution_block_from_evaluated_vrptw(evaluation, instance)
    return {
        "summary": summary,
        "runtime_seconds": float(runtime),
        "solution_block": solution_block,
    }


def _reuse_direct_executor(req: ValidatedRequest) -> dict:
    """Execute ``run_reuse_direct`` against the loaded VRPTW instance.

    Re-evaluates the routes already present in the source payload
    against the underlying VRPTW instance using
    ``evaluate_vrptw_solution`` — no solving. Returns objective,
    feasibility (overall, capacity-only, TW-only), per-route schedule,
    and lateness counts.

    Returns 400 ``payload_missing_routes`` if the source payload has
    no routes to re-evaluate (e.g. an OBJ-only or schedule-only
    scenario), and 501 if a perturbation overlay is requested
    (perturbation application is not implemented in this backend).
    """
    if req.perturbation is not None:
        raise RecomputeError(
            501,
            "perturbation_application_not_implemented",
            (
                "Applying a request-level perturbation on top of the "
                "loaded VRPTW instance is not implemented in this local "
                "demo backend."
            ),
            {"perturbation_type": req.perturbation.get("type")},
        )

    payload = req.payload or {}
    routes_in_payload = payload.get("routes")
    if not isinstance(routes_in_payload, list) or not routes_in_payload:
        raise RecomputeError(
            400,
            "payload_missing_routes",
            (
                "run_reuse_direct re-evaluates the current routes, but "
                "the source payload does not carry a routes block."
            ),
            {
                "source_scenario_id": (
                    f"{req.scenario_row.instance_id}__"
                    f"{req.scenario_row.perturbation_id}"
                ),
            },
        )

    fixed_routes: list[list[int]] = []
    for r in routes_in_payload:
        if not isinstance(r, dict):
            continue
        cids = r.get("customer_ids") or []
        try:
            route = [int(c) for c in cids]
        except (TypeError, ValueError):
            continue
        if route:
            fixed_routes.append(route)
    if not fixed_routes:
        raise RecomputeError(
            400,
            "payload_missing_routes",
            (
                "run_reuse_direct re-evaluates the current routes, but "
                "the source payload routes carry no customer ids."
            ),
            {},
        )

    try:
        from product.data.instance_geom import _resolve_instance_dir  # noqa: WPS450
        from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import SCALING_FACTOR
        from vrp_copilot_bench.vrptw.solver import evaluate_vrptw_solution
        from vrp_copilot_bench.vrptw_instances import load_vrptw_instance
    except Exception as exc:  # noqa: BLE001 — dependencies are optional in CI
        raise RecomputeError(
            501,
            "action_not_implemented",
            (
                "Solver dependencies are not available in this "
                "environment; cannot execute run_reuse_direct."
            ),
            {
                "requested_action": req.action,
                "import_error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc

    instance_id = req.scenario_row.instance_id
    try:
        inst_dir = _resolve_instance_dir(instance_id)
        instance = load_vrptw_instance(instance_id, instance_dir=inst_dir)
    except FileNotFoundError as exc:
        raise RecomputeError(
            404,
            "instance_geometry_not_found",
            f"VRPTW instance geometry not found for {instance_id!r}.",
            {"instance_id": instance_id},
        ) from exc

    t0 = time.perf_counter()
    result = evaluate_vrptw_solution(instance, fixed_routes)
    runtime = time.perf_counter() - t0

    summary = {
        "feasible": bool(result.feasible),
        "objective": float(result.objective) / SCALING_FACTOR,
        "n_routes": len(result.routes),
        "n_late_customers": int(result.n_late_customers),
        "feasible_capacity_only": bool(result.feasible_capacity_only),
        "feasible_tw_only": bool(result.feasible_tw_only),
        "n_unserved_customers": len(result.unserved_customers),
    }
    solution_block = _solution_block_from_evaluated_vrptw(result, instance)
    return {
        "summary": summary,
        "runtime_seconds": float(runtime),
        "solution_block": solution_block,
    }


def _solution_block_from_evaluated_vrptw(result: Any, instance: Any) -> dict:
    """Reshape an ``EvaluatedVRPTW`` into the dashboard solution block.

    Mirrors ``_solution_block_from_vrptw_result`` but reads per-route
    cost from ``route_summaries[].distance`` because
    ``EvaluatedVRPTW`` does not carry a ``route_costs`` dict.
    """
    from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import SCALING_FACTOR

    end_time_by_idx: dict[int, float] = {}
    distance_by_idx: dict[int, float] = {}
    for rs in getattr(result, "route_summaries", []) or []:
        try:
            idx = int(rs.route_idx)
        except Exception:  # noqa: BLE001
            continue
        end_time_by_idx[idx] = float(rs.end_time) / SCALING_FACTOR
        distance_by_idx[idx] = float(rs.distance) / SCALING_FACTOR

    routes_out: list[dict] = []
    for route_idx, route_customers in enumerate(result.routes):
        cids = [int(c) for c in route_customers]
        routes_out.append(
            {
                "route_idx": route_idx,
                "route_label": f"Route {route_idx + 1}",
                "customer_ids": cids,
                "load": None,
                "capacity": None,
                "distance": distance_by_idx.get(route_idx),
                "end_time": end_time_by_idx.get(route_idx),
            }
        )

    schedule_out: list[dict] = []
    per_cust = getattr(result, "per_customer_schedule", {}) or {}
    for cid, visit in per_cust.items():
        try:
            route_idx = int(visit.route_idx)
            tw_late = float(visit.tw_late)
            start = float(visit.start_service)
        except Exception:  # noqa: BLE001
            continue
        is_late = start > tw_late
        schedule_out.append(
            {
                "customer_id": int(cid),
                "route_idx": route_idx,
                "route_label": f"Route {route_idx + 1}",
                "position_in_route": 0,
                "arrival": float(visit.arrival),
                "service_start": float(visit.start_service),
                "service_end": float(visit.end_service),
                "time_window_start": float(visit.tw_early),
                "time_window_end": float(visit.tw_late),
                "is_late": bool(is_late),
                "lateness_minutes": float(max(0.0, start - tw_late)),
                "waiting_minutes": float(visit.wait_duration),
            }
        )

    return {
        "feasible": bool(result.feasible),
        "objective": float(result.objective) / SCALING_FACTOR,
        "n_routes": len(result.routes),
        "routes": routes_out,
        "customer_schedule": schedule_out or None,
    }


def _solution_block_from_vrptw_result(result: Any, instance: Any) -> dict:
    """Reshape a VRPTW solve result into the dashboard solution block.

    Mirrors ``scenario_store._build_solution_block`` shape. Fields not
    available in the solver output are emitted as ``null`` rather than
    fabricated.
    """
    from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import SCALING_FACTOR

    routes_out: list[dict] = []
    end_time_by_idx: dict[int, float] = {}
    for rs in getattr(result, "route_summaries", []) or []:
        end_time_by_idx[int(rs.route_idx)] = float(rs.end_time) / SCALING_FACTOR

    for route_idx, route_customers in enumerate(result.routes):
        cids = [int(c) for c in route_customers]
        routes_out.append(
            {
                "route_idx": route_idx,
                "route_label": f"Route {route_idx + 1}",
                "customer_ids": cids,
                "load": None,
                "capacity": None,
                "distance": float(result.route_costs.get(route_idx, 0.0))
                / SCALING_FACTOR,
                "end_time": end_time_by_idx.get(route_idx),
            }
        )

    schedule_out: list[dict] = []
    per_cust = getattr(result, "per_customer_schedule", {}) or {}
    for cid, visit in per_cust.items():
        try:
            route_idx = int(visit.route_idx)
        except Exception:  # noqa: BLE001
            continue
        try:
            tw_late = float(visit.tw_late)
            start = float(visit.start_service)
        except Exception:  # noqa: BLE001
            tw_late = 0.0
            start = 0.0
        is_late = start > tw_late
        schedule_out.append(
            {
                "customer_id": int(cid),
                "route_idx": route_idx,
                "route_label": f"Route {route_idx + 1}",
                "position_in_route": 0,
                "arrival": float(visit.arrival),
                "service_start": float(visit.start_service),
                "service_end": float(visit.end_service),
                "time_window_start": float(visit.tw_early),
                "time_window_end": float(visit.tw_late),
                "is_late": bool(is_late),
                "lateness_minutes": float(max(0.0, start - tw_late)),
                "waiting_minutes": float(visit.wait_duration),
            }
        )

    return {
        "feasible": bool(result.feasible),
        "objective": float(result.objective) / SCALING_FACTOR,
        "n_routes": int(result.n_routes),
        "routes": routes_out,
        "customer_schedule": schedule_out or None,
    }


def _not_implemented_executor(req: ValidatedRequest) -> dict:
    raise RecomputeError(
        501,
        "action_not_implemented",
        (
            "The requested recompute action is recognized but not "
            "implemented in this local demo backend."
        ),
        {
            "requested_action": req.action,
            "allowed_actions": sorted(ALLOWED_ACTIONS),
            "implemented_actions": sorted(IMPLEMENTED_ACTIONS),
        },
    )


_EXECUTORS: dict[str, Any] = {
    "run_pyvrp_10s": _pyvrp_10s_executor,
    "run_reuse_direct": _reuse_direct_executor,
    "run_clarke_wright": _clarke_wright_executor,
    "run_nearest_neighbor": _not_implemented_executor,
}


def execute_recompute_action(req: ValidatedRequest) -> dict:
    """Execute ``req.action`` and return ``{summary, runtime_seconds, ...}``.

    Implemented actions return a dict with ``summary`` and
    ``runtime_seconds``. Unimplemented deployable actions raise a 501
    ``RecomputeError`` carrying the structured envelope.
    """
    executor = _EXECUTORS.get(req.action)
    if executor is None:
        raise RecomputeError(
            500,
            "action_dispatch_missing",
            "No executor registered for this action.",
            {"requested_action": req.action},
        )
    return executor(req)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _build_diff(
    source_payload: Optional[dict], new_solution: Optional[dict]
) -> Optional[dict]:
    """Build a basic objective+feasibility diff if both sides have one.

    Returns ``None`` (signalling ``available_fields.diff == False``)
    when objects on either side are missing.
    """
    if not isinstance(source_payload, dict) or not isinstance(new_solution, dict):
        return None
    src_obj = source_payload.get("action_objective")
    if src_obj is None:
        src_obj = source_payload.get("objective")
    src_feasible = source_payload.get("feasible")
    new_obj = new_solution.get("objective")
    new_feasible = new_solution.get("feasible")
    if src_obj is None or new_obj is None:
        return None
    delta_abs = float(new_obj) - float(src_obj)
    delta_pct = (
        (delta_abs / float(src_obj) * 100.0)
        if float(src_obj) not in (0.0,)
        else None
    )
    feasibility_changed = None
    if src_feasible is not None and new_feasible is not None:
        feasibility_changed = bool(src_feasible) != bool(new_feasible)
    return {
        "objective_delta_absolute": delta_abs,
        "objective_delta_percent": delta_pct,
        "feasibility_changed": feasibility_changed,
        "customer_changes": [],
        "route_changes": [],
    }


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def _new_scenario_id(source: str, action: str, when: datetime) -> str:
    ts = when.strftime("%Y%m%d_%H%M%S")
    return f"{source}__{action}__{ts}"


def materialize_recompute_result(
    req: ValidatedRequest,
    execution: dict,
) -> RecomputeResponse:
    """Write runtime artifacts and assemble the response object."""
    now = datetime.now(timezone.utc)
    source_scenario_id = (
        f"{req.scenario_row.instance_id}__{req.scenario_row.perturbation_id}"
    )
    new_scenario_id = _new_scenario_id(source_scenario_id, req.action, now)

    out_dir = runtime_root() / new_scenario_id
    out_dir.mkdir(parents=True, exist_ok=True)

    solution_block = execution.get("solution_block")
    summary = dict(execution.get("summary") or {})
    runtime_seconds = float(execution.get("runtime_seconds", 0.0))

    diff_block = _build_diff(req.payload, solution_block)

    payload_doc = {
        "scenario_id": new_scenario_id,
        "source_scenario_id": source_scenario_id,
        "action_used": req.action,
        "solution": solution_block,
        "diff": diff_block,
        "summary": summary,
    }
    scenario_doc = {
        "scenario_id": new_scenario_id,
        "instance_id": req.scenario_row.instance_id,
        "perturbation_id": (
            f"{req.scenario_row.perturbation_id}__{req.action}"
        ),
        "source_scenario_id": source_scenario_id,
        "solution": solution_block,
        "available_fields": {
            "solution": solution_block is not None,
            "routes": bool(
                solution_block and solution_block.get("routes")
            ),
            "customer_schedule": bool(
                solution_block and solution_block.get("customer_schedule")
            ),
            "route_end_times": bool(
                solution_block and solution_block.get("routes")
                and any(
                    r.get("end_time") is not None
                    for r in (solution_block.get("routes") or [])
                )
            ),
            "baseline_solution": False,
            "diff": diff_block is not None,
            "objective_delta": diff_block is not None,
            "causal_diagnostics": False,
        },
    }
    metadata_doc = {
        "source_scenario_id": source_scenario_id,
        "new_scenario_id": new_scenario_id,
        "prompt": req.prompt,
        "requested_action": req.action,
        "action_used": req.action,
        "runtime_seconds": runtime_seconds,
        "created_at": now.isoformat(),
        "policy_source": POLICY_SOURCE,
        "execution_semantics": _EXECUTION_SEMANTICS.get(req.action),
        "d4_mode": req.d4_mode,
        "d4_recommended_action": req.d4_recommended_action,
        "perturbation": req.perturbation,
    }

    _atomic_write_json(out_dir / "metadata.json", metadata_doc)
    _atomic_write_json(out_dir / "payload.json", payload_doc)
    _atomic_write_json(out_dir / "scenario.json", scenario_doc)
    if diff_block is not None:
        _atomic_write_json(out_dir / "diff.json", diff_block)

    return RecomputeResponse(
        status="completed",
        source_scenario_id=source_scenario_id,
        new_scenario_id=new_scenario_id,
        action_used=req.action,
        runtime_seconds=runtime_seconds,
        summary=summary,
        artifacts={
            "scenario_path": str(out_dir / "scenario.json"),
            "payload_path": str(out_dir / "payload.json"),
        },
        next_actions=[
            {
                "type": "load_scenario",
                "scenario_id": new_scenario_id,
                "label": "Open recomputed scenario",
            },
            {
                "type": "ask_again",
                "scenario_id": new_scenario_id,
                "label": "Ask the original question on the recomputed scenario",
            },
        ],
    )


def _atomic_write_json(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Runtime scenario loader
# ---------------------------------------------------------------------------


def load_runtime_scenario(new_scenario_id: str) -> dict:
    """Return the materialized scenario doc for a runtime new_scenario_id.

    Raises ``RecomputeError(404)`` if the scenario directory does not
    exist.
    """
    out_dir = runtime_root() / new_scenario_id
    scenario_path = out_dir / "scenario.json"
    if not scenario_path.exists():
        raise RecomputeError(
            404,
            "runtime_scenario_not_found",
            f"No runtime scenario for id {new_scenario_id!r}.",
            {"new_scenario_id": new_scenario_id},
        )
    return json.loads(scenario_path.read_text(encoding="utf-8"))


def list_runtime_scenarios() -> list[str]:
    """Return all materialized runtime scenario ids (sorted)."""
    root = runtime_root()
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "scenario.json").exists()
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def run_recompute(
    scenario_id: str,
    prompt: str,
    requested_action: str,
    perturbation: Optional[dict],
    confirm: bool,
) -> RecomputeResponse:
    """Validate → execute → materialize. Raises ``RecomputeError`` on failure."""
    req = validate_recompute_request(
        scenario_id=scenario_id,
        prompt=prompt,
        requested_action=requested_action,
        perturbation=perturbation,
        confirm=confirm,
    )
    execution = execute_recompute_action(req)
    return materialize_recompute_result(req, execution)


__all__ = [
    "ALLOWED_ACTIONS",
    "FORBIDDEN_ACTIONS",
    "IMPLEMENTED_ACTIONS",
    "POLICY_SOURCE",
    "RecomputeError",
    "RecomputeResponse",
    "ValidatedRequest",
    "execute_recompute_action",
    "list_runtime_scenarios",
    "load_runtime_scenario",
    "materialize_recompute_result",
    "run_recompute",
    "runtime_root",
    "validate_recompute_request",
]

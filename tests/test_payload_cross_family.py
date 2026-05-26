"""Tests for cross-family payload fields and baseline_solution / diff."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiment" / "src"))

from payload_projector import (
    ProjectedAction,
    _compute_diff,
    _cross_family_fields,
    _project_baseline_solution,
)
from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import (
    SCALING_FACTOR,
    EvaluatedVRPTW,
    RouteSummary,
    VisitSchedule,
)


def _make_visit(
    customer_id: int, route_idx: int, *,
    time_warp: int = 0, start_service: int = 0,
    arrival: int = 0, end_service: int = 0,
    tw_early: int = 0, tw_late: int = 1000,
) -> VisitSchedule:
    return VisitSchedule(
        customer_id=customer_id, route_idx=route_idx,
        arrival=arrival, start_service=start_service, end_service=end_service,
        wait_duration=0, service_duration=0, time_warp=time_warp,
        tw_early=tw_early, tw_late=tw_late, slack_to_tw_late=100,
    )


def _make_route_summary(
    route_idx: int, n_customers: int, *, end_time: int = 0, has_time_warp: bool = False,
) -> RouteSummary:
    return RouteSummary(
        route_idx=route_idx, n_customers=n_customers,
        start_time=0, end_time=end_time, distance=0, duration=0,
        wait_duration=0, service_duration=0, travel_duration=0,
        time_warp=0, slack=0, is_feasible=True, has_time_warp=has_time_warp,
        has_excess_load=False, min_slack_to_tw_late=0,
        mean_slack_to_tw_late=0.0, n_late_customers=0,
    )


def _make_eval(
    objective: float,
    schedule: dict[int, VisitSchedule],
    route_summaries: list[RouteSummary] | None = None,
    *,
    feasible: bool = True,
    feasible_capacity_only: bool = True,
    feasible_tw_only: bool = True,
    is_complete: bool = True,
) -> EvaluatedVRPTW:
    routes_by_idx: dict[int, list[int]] = {}
    for cid, vs in schedule.items():
        routes_by_idx.setdefault(int(vs.route_idx), []).append(int(cid))
    routes = [sorted(cids) for _, cids in sorted(routes_by_idx.items())]
    assignment = {int(c): int(vs.route_idx) for c, vs in schedule.items()}
    if route_summaries is None:
        route_summaries = [
            _make_route_summary(ridx, len(cids))
            for ridx, cids in sorted(routes_by_idx.items())
        ]
    return EvaluatedVRPTW(
        objective=objective, feasible=feasible,
        feasible_capacity_only=feasible_capacity_only,
        feasible_tw_only=feasible_tw_only,
        is_complete=is_complete, has_time_warp=False,
        total_time_warp=0, total_duration=100, total_wait=0,
        total_distance=100, n_late_customers=0, max_lateness=0,
        routes=routes, assignment=assignment,
        route_summaries=route_summaries,
        per_customer_schedule=schedule,
        unserved_customers=[],
    )


def _make_projected(
    perturbation_family: str,
    affected_customers: tuple[int, ...],
    schedule: dict[int, VisitSchedule],
    baseline_evaluation: EvaluatedVRPTW | None = None,
) -> ProjectedAction:
    ev = _make_eval(1000.0, schedule)
    return ProjectedAction(
        family="", evaluation=ev, baseline_objective=100.0,
        routes=[[10, 20], [30]],
        perturbation_family=perturbation_family,
        affected_customers=affected_customers,
        baseline_evaluation=baseline_evaluation,
    )


class TestCrossFamilyFields:
    def test_assignment_shape(self):
        schedule = {
            10: _make_visit(10, 0),
            20: _make_visit(20, 0),
            30: _make_visit(30, 1),
        }
        proj = _make_projected("TRAVEL_TIME", (), schedule)
        fields = _cross_family_fields(proj)
        assert fields["assignment"] == {"10": 0, "20": 0, "30": 1}

    def test_new_customer_ids_order_change(self):
        schedule = {
            10: _make_visit(10, 0),
            20: _make_visit(20, 0),
            30: _make_visit(30, 1),
        }
        proj = _make_projected("ORDER_CHANGE", (20, 30), schedule)
        fields = _cross_family_fields(proj)
        assert fields["new_customer_ids"] == [20, 30]

    def test_new_customer_ids_non_oc(self):
        schedule = {10: _make_visit(10, 0)}
        proj = _make_projected("TIME_WINDOW", (), schedule)
        fields = _cross_family_fields(proj)
        assert fields["new_customer_ids"] == []

    def test_assignment_keys_are_strings(self):
        schedule = {42: _make_visit(42, 2)}
        proj = _make_projected("SERVICE_TIME", (), schedule)
        fields = _cross_family_fields(proj)
        assert all(isinstance(k, str) for k in fields["assignment"])
        assert all(isinstance(v, int) for v in fields["assignment"].values())


class TestBaselineSolution:
    def test_obj_family_has_objective(self):
        sched = {10: _make_visit(10, 0)}
        bev = _make_eval(5000.0, sched)
        proj = ProjectedAction(
            family="", evaluation=_make_eval(6000.0, sched),
            baseline_objective=500.0, routes=[[10]],
            baseline_evaluation=bev,
        )
        bs = _project_baseline_solution("OBJ", proj)
        assert bs["objective"] == round(5000.0 / SCALING_FACTOR, 2)

    def test_pv_family_has_feasibility(self):
        sched = {10: _make_visit(10, 0)}
        bev = _make_eval(5000.0, sched, feasible=True)
        proj = ProjectedAction(
            family="", evaluation=_make_eval(6000.0, sched),
            baseline_objective=500.0, routes=[[10]],
            baseline_evaluation=bev,
        )
        bs = _project_baseline_solution("PLAN_VALIDITY", proj)
        assert bs["feasible"] is True
        assert "feasibility_breakdown" in bs

    def test_struct_family_has_routes(self):
        sched = {
            10: _make_visit(10, 0, start_service=10),
            20: _make_visit(20, 0, start_service=20),
            30: _make_visit(30, 1, start_service=10),
        }
        bev = _make_eval(5000.0, sched)
        proj = ProjectedAction(
            family="", evaluation=_make_eval(6000.0, sched),
            baseline_objective=500.0, routes=[[10, 20], [30]],
            baseline_evaluation=bev,
        )
        bs = _project_baseline_solution("STRUCT", proj)
        assert bs["n_routes"] == 2
        assert len(bs["routes"]) == 2

    def test_schedule_family_has_customer_schedule(self):
        sched = {
            10: _make_visit(10, 0, time_warp=50),
            20: _make_visit(20, 0),
        }
        bev = _make_eval(5000.0, sched)
        proj = ProjectedAction(
            family="", evaluation=_make_eval(6000.0, sched),
            baseline_objective=500.0, routes=[[10, 20]],
            baseline_evaluation=bev,
        )
        bs = _project_baseline_solution("SCHEDULE", proj)
        assert bs["n_late_customers"] == 1
        assert bs["late_customer_ids"] == [10]
        assert len(bs["customer_schedule"]) == 2

    def test_none_baseline_returns_empty(self):
        sched = {10: _make_visit(10, 0)}
        proj = ProjectedAction(
            family="", evaluation=_make_eval(6000.0, sched),
            baseline_objective=500.0, routes=[[10]],
            baseline_evaluation=None,
        )
        assert _project_baseline_solution("OBJ", proj) == {}


class TestDiff:
    def test_obj_diff(self):
        sched = {10: _make_visit(10, 0)}
        bev = _make_eval(5000.0, sched)
        aev = _make_eval(6000.0, sched)
        proj = ProjectedAction(
            family="", evaluation=aev,
            baseline_objective=500.0, routes=[[10]],
            baseline_evaluation=bev,
        )
        d = _compute_diff("OBJ", proj)
        b_obj = 5000.0 / SCALING_FACTOR
        a_obj = 6000.0 / SCALING_FACTOR
        assert d["objective"]["delta_absolute"] == round(a_obj - b_obj, 2)
        assert d["objective"]["delta_percent"] == round(
            100.0 * (a_obj - b_obj) / b_obj, 2
        )

    def test_pv_diff_became_infeasible(self):
        sched = {10: _make_visit(10, 0)}
        bev = _make_eval(5000.0, sched, feasible=True)
        aev = _make_eval(6000.0, sched, feasible=False)
        proj = ProjectedAction(
            family="", evaluation=aev,
            baseline_objective=500.0, routes=[[10]],
            baseline_evaluation=bev,
        )
        d = _compute_diff("PLAN_VALIDITY", proj)
        assert d["feasibility"]["became_infeasible"] is True
        assert d["feasibility"]["became_feasible"] is False

    def test_struct_diff_customer_moved(self):
        b_sched = {
            10: _make_visit(10, 0, start_service=10),
            20: _make_visit(20, 0, start_service=20),
            30: _make_visit(30, 1, start_service=10),
        }
        a_sched = {
            10: _make_visit(10, 0, start_service=10),
            20: _make_visit(20, 1, start_service=20),
            30: _make_visit(30, 1, start_service=10),
        }
        bev = _make_eval(5000.0, b_sched)
        aev = _make_eval(6000.0, a_sched)
        proj = ProjectedAction(
            family="", evaluation=aev,
            baseline_objective=500.0, routes=[[10], [20, 30]],
            baseline_evaluation=bev,
        )
        d = _compute_diff("STRUCT", proj)
        assert d["routes"]["added"] == []
        assert d["routes"]["removed"] == []
        assert len(d["routes"]["modified"]) > 0
        mod_r0 = next(m for m in d["routes"]["modified"] if m["route_idx"] == 0)
        assert 20 in mod_r0["customers_removed"]

    def test_schedule_diff_new_late(self):
        b_sched = {
            10: _make_visit(10, 0, time_warp=0),
            20: _make_visit(20, 0, time_warp=50),
        }
        a_sched = {
            10: _make_visit(10, 0, time_warp=30),
            20: _make_visit(20, 0, time_warp=0),
        }
        bev = _make_eval(5000.0, b_sched)
        aev = _make_eval(6000.0, a_sched)
        proj = ProjectedAction(
            family="", evaluation=aev,
            baseline_objective=500.0, routes=[[10, 20]],
            baseline_evaluation=bev,
        )
        d = _compute_diff("SCHEDULE", proj)
        assert d["schedule"]["new_late_customer_ids"] == [10]
        assert d["schedule"]["no_longer_late_customer_ids"] == [20]

    def test_none_baseline_returns_empty(self):
        sched = {10: _make_visit(10, 0)}
        proj = ProjectedAction(
            family="", evaluation=_make_eval(6000.0, sched),
            baseline_objective=500.0, routes=[[10]],
            baseline_evaluation=None,
        )
        assert _compute_diff("OBJ", proj) == {}

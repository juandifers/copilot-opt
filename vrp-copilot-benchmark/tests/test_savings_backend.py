"""Phase 2 Clarke-Wright savings backend tests.

Correctness invariants:
  - each customer is visited exactly once
  - every route's cumulative demand <= capacity
  - objective equals the sum of route distances
  - solver is deterministic: two calls on the same instance give the same result
  - result is at least as good as nearest-neighbor on non-trivial instances
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vrpbench.backends.cheap_savings import solve_savings
from vrpbench.backends.nearest_neighbor import solve_nearest_neighbor
from vrpbench.data.instance import VRPInstance, load_instance


@pytest.fixture
def toy_instance(tmp_path: Path) -> VRPInstance:
    """A tiny synthetic VRP instance: 1 depot + 5 customers on a line.

    Coordinates chosen so that the optimal structure is obvious: two
    clusters of three with the depot in between, capacity forces split.
    """
    content = (
        "NAME : toy5\n"
        "TYPE : CVRP\n"
        "DIMENSION : 6\n"
        "EDGE_WEIGHT_TYPE : EUC_2D\n"
        "CAPACITY : 10\n"
        "NODE_COORD_SECTION\n"
        " 1 50 50\n"
        " 2 10 50\n"
        " 3 20 50\n"
        " 4 30 50\n"
        " 5 70 50\n"
        " 6 90 50\n"
        "DEMAND_SECTION\n"
        " 1 0\n"
        " 2 3\n"
        " 3 4\n"
        " 4 3\n"
        " 5 5\n"
        " 6 5\n"
        "DEPOT_SECTION\n"
        " 1\n"
        " -1\n"
        "EOF\n"
    )
    p = tmp_path / "toy5.vrp"
    p.write_text(content)
    return load_instance(p)


def test_savings_visits_every_customer(toy_instance):
    art = solve_savings(toy_instance)
    assert art.status == "ok"
    visited = [c for r in art.routes for c in r]
    assert sorted(visited) == list(range(1, toy_instance.n_customers + 1))


def test_savings_respects_capacity(toy_instance):
    art = solve_savings(toy_instance)
    demand = np.asarray(toy_instance.raw["demand"], dtype=float)
    for r, load in zip(art.routes, art.route_loads):
        actual = float(sum(demand[c] for c in r))
        assert actual <= toy_instance.capacity + 1e-9
        assert abs(load - actual) < 1e-6


def test_savings_objective_matches_route_distances(toy_instance):
    art = solve_savings(toy_instance)
    assert art.objective == pytest.approx(sum(art.route_distances))


def test_savings_is_deterministic(toy_instance):
    a = solve_savings(toy_instance)
    b = solve_savings(toy_instance)
    assert a.routes == b.routes
    assert a.objective == pytest.approx(b.objective)


def test_savings_beats_or_matches_nn(toy_instance):
    """CW savings is generally stronger than pure nearest-neighbor.

    We only require <= to allow edge cases where NN happens to find the
    same tour on degenerate geometries.
    """
    cw = solve_savings(toy_instance)
    nn = solve_nearest_neighbor(toy_instance)
    assert cw.objective is not None and nn.objective is not None
    assert cw.objective <= nn.objective + 1e-6

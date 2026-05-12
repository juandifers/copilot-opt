"""Tests for solvers/marginal_costs.py."""
from __future__ import annotations

import numpy as np
import pytest

from vrp_copilot_bench.solvers.marginal_costs import compute_customer_costs


def _square_dist(coords: np.ndarray) -> np.ndarray:
    """Helper: integer-rounded Euclidean distance matrix."""
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    return np.round(np.sqrt((diff ** 2).sum(-1))).astype(np.int64)


class TestCustomerCosts:
    def test_single_customer_route_round_trip(self) -> None:
        """Route [c]: marginal = d[depot,c] + d[c,depot] − d[depot,depot] = 2·d[depot,c]."""
        # 1-D layout: depot at 0, customer 1 at 10
        coords = np.array([[0.0, 0.0], [10.0, 0.0]])
        dist = _square_dist(coords)
        out = compute_customer_costs(routes=[[1]], distance_matrix=dist, depot_id=0)
        assert out == {1: 20.0}, out

    def test_two_customer_route_uses_correct_formula(self) -> None:
        """Hand-computed marginals for [c1, c2].

        Triangle with depot=0, c1=1, c2=2; d[0,1]=10, d[0,2]=15, d[1,2]=8.
        marginal[1] = d[0,1] + d[1,2] − d[0,2] = 10 + 8 − 15 = 3
        marginal[2] = d[1,2] + d[2,0] − d[1,0] = 8 + 15 − 10 = 13
        """
        dist = np.array([
            [0, 10, 15],
            [10, 0, 8],
            [15, 8, 0],
        ], dtype=np.int64)
        out = compute_customer_costs(routes=[[1, 2]], distance_matrix=dist, depot_id=0)
        assert out == {1: 3.0, 2: 13.0}

    def test_three_customer_interior_uses_neighbor_shortcut(self) -> None:
        """For an interior customer, prev/next are its route neighbors, not the depot."""
        dist = np.array([
            [0, 5, 7, 9],
            [5, 0, 4, 11],
            [7, 4, 0, 3],
            [9, 11, 3, 0],
        ], dtype=np.int64)
        out = compute_customer_costs(routes=[[1, 2, 3]], distance_matrix=dist, depot_id=0)
        # marginal[1] = d[0,1] + d[1,2] − d[0,2] = 5 + 4 − 7 = 2
        # marginal[2] = d[1,2] + d[2,3] − d[1,3] = 4 + 3 − 11 = −4   (negative is fine: a "shortcut" customer)
        # marginal[3] = d[2,3] + d[3,0] − d[2,0] = 3 + 9 − 7 = 5
        assert out == {1: 2.0, 2: -4.0, 3: 5.0}

    def test_multi_route_concatenates_costs_into_one_dict(self) -> None:
        """Two routes processed independently; output covers both."""
        dist = np.array([
            [0, 4, 5, 6, 7],
            [4, 0, 3, 5, 8],
            [5, 3, 0, 4, 6],
            [6, 5, 4, 0, 5],
            [7, 8, 6, 5, 0],
        ], dtype=np.int64)
        out = compute_customer_costs(
            routes=[[1, 2], [3, 4]], distance_matrix=dist, depot_id=0
        )
        # route 1: [1, 2]
        #   marginal[1] = 4 + 3 − 5 = 2
        #   marginal[2] = 3 + 5 − 4 = 4
        # route 2: [3, 4]
        #   marginal[3] = 6 + 5 − 7 = 4
        #   marginal[4] = 5 + 7 − 6 = 6
        assert out == {1: 2.0, 2: 4.0, 3: 4.0, 4: 6.0}
        assert set(out.keys()) == {1, 2, 3, 4}

    def test_empty_routes_skipped(self) -> None:
        """Empty (zero-customer) routes are silently skipped."""
        dist = np.array([[0, 5], [5, 0]], dtype=np.int64)
        out = compute_customer_costs(routes=[[1], [], []], distance_matrix=dist)
        assert out == {1: 10.0}

    def test_empty_routes_list_returns_empty_dict(self) -> None:
        dist = np.zeros((2, 2), dtype=np.int64)
        assert compute_customer_costs(routes=[], distance_matrix=dist) == {}

    def test_non_default_depot_id(self) -> None:
        """depot_id=5 should be used as prev/next at route boundaries, not 0."""
        # 6 nodes; depot at index 5; customers at 0, 1, 2.
        dist = np.array([
            [0, 4, 5, 99, 99, 7],
            [4, 0, 3, 99, 99, 8],
            [5, 3, 0, 99, 99, 6],
            [99, 99, 99, 0, 99, 99],
            [99, 99, 99, 99, 0, 99],
            [7, 8, 6, 99, 99, 0],
        ], dtype=np.int64)
        out = compute_customer_costs(routes=[[0, 1, 2]], distance_matrix=dist, depot_id=5)
        # marginal[0] = d[5,0] + d[0,1] − d[5,1] = 7 + 4 − 8 = 3
        # marginal[1] = d[0,1] + d[1,2] − d[0,2] = 4 + 3 − 5 = 2
        # marginal[2] = d[1,2] + d[2,5] − d[1,5] = 3 + 6 − 8 = 1
        assert out == {0: 3.0, 1: 2.0, 2: 1.0}

    def test_customer_ids_returned_as_python_ints(self) -> None:
        """JSON-serialization works only with Python ints; numpy ints break json.dumps."""
        dist = np.array([[0, 5], [5, 0]], dtype=np.int64)
        out = compute_customer_costs(
            routes=[[np.int64(1)]], distance_matrix=dist
        )
        assert all(isinstance(k, int) and not isinstance(k, bool) for k in out)
        assert all(type(k) is int for k in out)

    def test_costs_are_python_floats(self) -> None:
        dist = np.array([[0, 5], [5, 0]], dtype=np.int64)
        out = compute_customer_costs(routes=[[1]], distance_matrix=dist)
        assert all(type(v) is float for v in out.values())

    def test_deterministic_on_same_input(self) -> None:
        dist = np.array([
            [0, 4, 5, 6],
            [4, 0, 3, 7],
            [5, 3, 0, 4],
            [6, 7, 4, 0],
        ], dtype=np.int64)
        a = compute_customer_costs(routes=[[1, 2, 3]], distance_matrix=dist)
        b = compute_customer_costs(routes=[[1, 2, 3]], distance_matrix=dist)
        assert a == b

    def test_single_customer_marginal_equals_route_cost(self) -> None:
        """Sanity invariant: for a 1-customer route, marginal IS the route cost."""
        coords = np.array([[100.0, 100.0], [200.0, 250.0]])
        dist = _square_dist(coords)
        # Route [1]; route cost = 2 * d[0,1].
        route_cost = 2 * int(dist[0, 1])
        out = compute_customer_costs(routes=[[1]], distance_matrix=dist)
        assert out[1] == route_cost

    def test_handles_int_keys_and_float_dist_matrix(self) -> None:
        """Distance matrix can be float; the function must coerce sums to Python float."""
        dist = np.array([
            [0.0, 5.5, 7.5],
            [5.5, 0.0, 3.0],
            [7.5, 3.0, 0.0],
        ], dtype=np.float64)
        out = compute_customer_costs(routes=[[1, 2]], distance_matrix=dist)
        # marginal[1] = 5.5 + 3.0 − 7.5 = 1.0
        # marginal[2] = 3.0 + 7.5 − 5.5 = 5.0
        assert out == {1: 1.0, 2: 5.0}

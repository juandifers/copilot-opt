"""Tests for ``vrp_copilot_bench.vrptw.evaluation.reference_stability``.

Specifically covers the PREREG v1.1 amendment to §8.2/§12.3:
``struct_unstable`` is ``None`` (stability-undefined) when no reference
seed is feasible. Before v1.1 the function reported ``True`` for such
cells because PyVRP returns a penalty-bounded "best" assignment even
when infeasible, so ``ari_min`` was computable.
"""
from __future__ import annotations

import pytest

from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult
from vrp_copilot_bench.vrptw.evaluation import reference_stability


def _make(
    *,
    objective: float,
    feasible: bool,
    assignment: dict[int, int],
    n_routes: int = 1,
) -> VRPTWSolveResult:
    return VRPTWSolveResult(
        objective=objective,
        feasible=feasible,
        routes=[[c for c in assignment.keys()]],
        assignment=dict(assignment),
        route_costs={0: 0.0},
        runtime_seconds=0.0,
        pyvrp_version="test",
        n_routes=n_routes,
    )


def test_all_seeds_feasible_stable_partition_struct_stable() -> None:
    """All-feasible + identical partitions → struct_unstable is False (not None)."""
    a = {1: 0, 2: 0, 3: 1, 4: 1}
    s = _make(objective=100.0, feasible=True, assignment=a)
    stab = reference_stability(s, s, s)
    assert stab.struct_unstable is False
    assert stab.ari_min == 1.0


def test_all_seeds_feasible_differing_partitions_struct_unstable() -> None:
    """All-feasible + low ARI → struct_unstable is True."""
    s1 = _make(objective=100.0, feasible=True, assignment={1: 0, 2: 0, 3: 1, 4: 1})
    s2 = _make(objective=101.0, feasible=True, assignment={1: 0, 2: 1, 3: 0, 4: 1})
    s3 = _make(objective=102.0, feasible=True, assignment={1: 1, 2: 0, 3: 1, 4: 0})
    stab = reference_stability(s1, s2, s3)
    assert stab.struct_unstable is True
    assert stab.ari_min < 0.90


def test_no_feasible_seed_struct_unstable_is_none_v11_amendment() -> None:
    """PREREG v1.1 amendment: all-infeasible cell → struct_unstable is None.

    Before v1.1 this returned ``True`` (ari_min was still computable on
    PyVRP's penalty-bounded best assignments). After v1.1, stability is
    undefined when no seed is feasible — the §8.3 n/a policy owns these
    cells and the §12.3 rate excludes them from both numerator and
    denominator.
    """
    # Differing infeasible "best" partitions across seeds — would have
    # produced ari_min < 0.90 and struct_unstable=True under the v1.0 rule.
    s1 = _make(objective=float("inf"), feasible=False,
               assignment={1: 0, 2: 0, 3: 1, 4: 1})
    s2 = _make(objective=float("inf"), feasible=False,
               assignment={1: 0, 2: 1, 3: 0, 4: 1})
    s3 = _make(objective=float("inf"), feasible=False,
               assignment={1: 1, 2: 0, 3: 1, 4: 0})
    stab = reference_stability(s1, s2, s3)
    assert stab.struct_unstable is None
    assert stab.failure_kind == "all_infeasible"
    assert not stab.any_feasible


def test_partial_feasibility_struct_unstable_defined() -> None:
    """At least one seed feasible → struct_unstable is defined (True/False)."""
    s1 = _make(objective=100.0, feasible=True, assignment={1: 0, 2: 0, 3: 1, 4: 1})
    s2 = _make(objective=float("inf"), feasible=False,
               assignment={1: 0, 2: 1, 3: 0, 4: 1})
    s3 = _make(objective=float("inf"), feasible=False,
               assignment={1: 0, 2: 0, 3: 1, 4: 1})
    stab = reference_stability(s1, s2, s3)
    assert stab.struct_unstable in (True, False)
    assert stab.any_feasible is True

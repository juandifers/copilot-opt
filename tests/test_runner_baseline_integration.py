"""End-to-end runner integration tests.

These tests verify the Phase C wiring against real solver data:

1. :func:`run_one_action` loads the baseline, applies the perturbation
   (with baseline passed through), runs the action, and writes a
   checkpoint that round-trips through :class:`ActionResult.from_dict`.
2. The runner now passes baselines into :func:`apply_perturbation` —
   without that, DEMAND, DIST_4, and INSERTION specs would fail at the
   perturbation layer with "missing baseline".
3. The :func:`load_baseline_solution` LRU cache amortises baseline
   reads across the 16-perturbation × 5-action work plan for one
   instance. We verify it directly via ``cache_info()``.

These tests use a real cached baseline + real instance to prove the
integration works end-to-end on real solver data. The action used is
:func:`reuse_direct` so the test stays fast (no PyVRP solve needed).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.baselines import load_baseline_solution
from vrp_copilot_bench.checkpoint import (
    ActionRunKey,
    has_checkpoint,
    list_failures,
    load_result,
)
from vrp_copilot_bench.runner import run_one_action


_REAL_INSTANCE_ID = "X-n101-k25"


def _have_real_baseline() -> bool:
    return (
        Path("data/baselines") / f"{_REAL_INSTANCE_ID}.json"
    ).exists() and (
        Path("data/instances") / f"{_REAL_INSTANCE_ID}.vrp"
    ).exists()


requires_real_baseline = pytest.mark.skipif(
    not _have_real_baseline(),
    reason=f"requires cached baseline for {_REAL_INSTANCE_ID}",
)


# ---------------------------------------------------------------------------
# End-to-end run_one_action


@requires_real_baseline
def test_run_one_action_writes_checkpoint(tmp_path: Path) -> None:
    """The full happy path: baseline loaded, perturbation applied,
    action run, checkpoint written."""
    key = ActionRunKey(_REAL_INSTANCE_ID, "CAP_2", "reuse_direct")
    outcome = run_one_action(key, tmp_path)
    assert outcome is None  # success → None
    assert has_checkpoint(tmp_path, key)
    # The checkpoint round-trips through ActionResult.
    result = load_result(tmp_path, key)
    assert isinstance(result, ActionResult)
    assert result.action == "reuse_direct"
    assert result.objective is not None
    # Any reuse_direct on CAP_2 produces a valid plan; its objective
    # equals the baseline objective (route plan unchanged).
    assert result.objective > 0
    # No failure record written.
    assert list_failures(tmp_path) == {}


@requires_real_baseline
def test_run_one_action_demand_perturbation_with_baseline(tmp_path: Path) -> None:
    """DEM_1 (DEMAND family) requires a baseline to select the affected
    route. Pre-Phase C this would have failed with "missing baseline";
    Phase C's runner update fixes it."""
    key = ActionRunKey(_REAL_INSTANCE_ID, "DEM_1", "reuse_direct")
    outcome = run_one_action(key, tmp_path)
    assert outcome is None
    assert has_checkpoint(tmp_path, key)


@requires_real_baseline
def test_run_one_action_dist_4_with_baseline(tmp_path: Path) -> None:
    """DIST_4 (highest-cost route) needs the baseline; same coverage
    test as DEM_1."""
    key = ActionRunKey(_REAL_INSTANCE_ID, "DIST_4", "reuse_direct")
    outcome = run_one_action(key, tmp_path)
    assert outcome is None
    assert has_checkpoint(tmp_path, key)


@requires_real_baseline
def test_run_one_action_insertion_with_baseline(tmp_path: Path) -> None:
    """INSERTION needs the baseline (selects clusters / routes from it)."""
    key = ActionRunKey(_REAL_INSTANCE_ID, "INS_2", "reuse_direct")
    outcome = run_one_action(key, tmp_path)
    assert outcome is None
    assert has_checkpoint(tmp_path, key)
    result = load_result(tmp_path, key)
    # Inserted customers should be unassigned in reuse_direct's output.
    n_unassigned = sum(1 for v in result.assignment.values() if v == -1)
    assert n_unassigned > 0
    assert result.meta.get("partial_coverage") is True


# ---------------------------------------------------------------------------
# Baseline cache amortisation


@requires_real_baseline
def test_load_baseline_solution_is_lru_cached() -> None:
    """The :func:`load_baseline_solution` symbol exposes a cache_info
    interface, indicating ``functools.lru_cache`` is wrapping it."""
    assert hasattr(load_baseline_solution, "cache_info")
    assert hasattr(load_baseline_solution, "cache_clear")


@requires_real_baseline
def test_baseline_cache_amortises_repeated_reads() -> None:
    """16 calls to ``load_baseline_solution`` for the same instance trigger
    one disk read; the cache absorbs the rest."""
    # Clear any prior state from earlier tests.
    load_baseline_solution.cache_clear()

    # Drive 16 calls (matches one instance's perturbation count).
    for _ in range(16):
        _ = load_baseline_solution(_REAL_INSTANCE_ID)

    info = load_baseline_solution.cache_info()
    # First call is a miss; the next 15 are hits.
    assert info.misses == 1
    assert info.hits == 15
    # Clean up so other tests start with a fresh cache.
    load_baseline_solution.cache_clear()


@requires_real_baseline
def test_runner_uses_cached_baseline_within_process(tmp_path: Path) -> None:
    """Two run_one_action calls against the same instance hit the cache
    on the second call. We verify by inspecting cache_info before/after."""
    load_baseline_solution.cache_clear()

    key1 = ActionRunKey(_REAL_INSTANCE_ID, "CAP_1", "reuse_direct")
    key2 = ActionRunKey(_REAL_INSTANCE_ID, "CAP_2", "reuse_direct")
    run_one_action(key1, tmp_path)
    info_after_first = load_baseline_solution.cache_info()
    run_one_action(key2, tmp_path)
    info_after_second = load_baseline_solution.cache_info()

    # First call: 1 miss; second call: cache hit (no extra miss).
    assert info_after_first.misses == 1
    assert info_after_second.misses == 1
    assert info_after_second.hits == info_after_first.hits + 1
    load_baseline_solution.cache_clear()


# Failure-path coverage on real data is exercised in :mod:`tests.test_runner`
# (synthetic monkeypatched fakes for the runner's downstream deps) and in
# :mod:`tests.test_run_action_dispatcher` (ActionFailure propagates from
# run_action). Both layers' failure paths are tested; we don't need a
# real-data variant here. ``ActionRunKey`` itself rejects unknown action
# names at construction time, so the only way to reach the runner's
# failure path on real data would be to engineer a cell that genuinely
# fails — which is not the goal of this integration test file.

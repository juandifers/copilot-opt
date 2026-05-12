"""Tests for the Stage A work-plan enumeration (Phase 2)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from vrp_copilot_bench.actions import ACTIONS, AUDIT_ACTIONS, BASE_ACTIONS, ActionResult
from vrp_copilot_bench.checkpoint import ActionRunKey as CheckpointActionRunKey
from vrp_copilot_bench.checkpoint import save_failure, save_result
from vrp_copilot_bench.instances import (
    list_stage_a_instances,
    n_customers_for,
)
from vrp_copilot_bench.perturbations import PERTURBATION_IDS, enumerate_perturbations
from vrp_copilot_bench.work_plan import (
    AUDIT_FRACTION,
    AUDIT_RNG_SEED,
    CLAIM_FAMILIES,
    DEFAULT_LARGE_THRESHOLD,
    ActionRunKey,
    enumerate_stage_a,
    filter_completed,
    is_large_instance,
    order_by_size,
    select_audit_subset,
)


# ---------------------------------------------------------------------------
# Helpers


def _make_result() -> ActionResult:
    return ActionResult(
        action="reuse_direct",
        objective=1.0,
        feasible=True,
        runtime_seconds=0.01,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={1: 0},
        route_costs={0: 1.0},
        customer_costs={1: 1.0},
    )


# ---------------------------------------------------------------------------
# Re-export


class TestActionRunKeyReExport:
    def test_work_plan_action_run_key_is_checkpoint_action_run_key(self) -> None:
        """The prompt requires `from vrp_copilot_bench.work_plan import ActionRunKey`
        to work. The class must be the same object as the checkpoint one so
        equality and isinstance checks hold across module boundaries."""
        assert ActionRunKey is CheckpointActionRunKey


# ---------------------------------------------------------------------------
# Stub sanity (so subsequent tests have known cardinalities)


#: Roster-size derived expected counts (prereg §5.1 v0.5).
_N_INSTANCES = len(list_stage_a_instances())
_N_PAIRS = _N_INSTANCES * len(PERTURBATION_IDS)            # instances × 16 perts
_N_PAIRS_PER_FAMILY = _N_PAIRS // 4                        # 4 perturbation families
_EXPECTED_AUDIT_PAIRS_PER_FAMILY = int(_N_PAIRS_PER_FAMILY * AUDIT_FRACTION)
_EXPECTED_AUDIT_PAIRS = _EXPECTED_AUDIT_PAIRS_PER_FAMILY * 4
_EXPECTED_AUDIT_KEYS = _EXPECTED_AUDIT_PAIRS * len(AUDIT_ACTIONS)
_EXPECTED_BASE_KEYS = _N_INSTANCES * len(PERTURBATION_IDS) * len(BASE_ACTIONS)
_EXPECTED_TOTAL_KEYS = _EXPECTED_BASE_KEYS + _EXPECTED_AUDIT_KEYS


class TestStubSanity:
    def test_stage_a_roster_is_distinct(self) -> None:
        ids = list_stage_a_instances()
        # Prereg §5.1 v0.5: target 68 (the full eligible pool after the
        # n_customers ≤ 500 filter).
        assert len(ids) == 68
        assert len(set(ids)) == 68, "Stage A roster has duplicates"

    def test_perturbations_has_16_ids(self) -> None:
        assert len(PERTURBATION_IDS) == 16
        assert len(enumerate_perturbations("X-n101-k25")) == 16

    def test_n_customers_parses_correctly(self) -> None:
        assert n_customers_for("X-n101-k25") == 100
        assert n_customers_for("X-n502-k39") == 501

    def test_n_customers_rejects_bad_id(self) -> None:
        with pytest.raises(ValueError):
            n_customers_for("not-an-uchoa-id")


# ---------------------------------------------------------------------------
# select_audit_subset (prereg §8.2, pair-level sampling)


class TestSelectAuditSubset:
    def test_count_matches_audit_fraction(self) -> None:
        """20% of (instance, pert) pairs, stratified by 4 perturbation families."""
        subset = select_audit_subset()
        assert len(subset) == _EXPECTED_AUDIT_PAIRS

    def test_is_deterministic(self) -> None:
        """Same RNG seed → exact same set of pairs."""
        a = select_audit_subset()
        b = select_audit_subset()
        assert a == b

    def test_returns_pairs(self) -> None:
        subset = select_audit_subset()
        for pair in subset:
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            instance_id, perturbation_id = pair
            assert instance_id in set(list_stage_a_instances())
            assert perturbation_id in set(PERTURBATION_IDS)

    def test_stratification_by_perturbation_family(self) -> None:
        """Every perturbation family contributes the same number of pairs."""
        from collections import Counter

        subset = select_audit_subset()
        per_family = Counter(pid.split("_", 1)[0] for (_, pid) in subset)
        assert len(per_family) == 4
        assert set(per_family.keys()) == {"CAP", "DIST", "DEM", "INS"}
        for family, count in per_family.items():
            assert count == _EXPECTED_AUDIT_PAIRS_PER_FAMILY, (
                f"family {family} has {count} pairs, "
                f"expected {_EXPECTED_AUDIT_PAIRS_PER_FAMILY}"
            )

    def test_no_claim_family_dependency(self) -> None:
        """The audit subset is keyed by (instance, perturbation) only —
        claim_family is not part of the sample. CLAIM_FAMILIES still exists
        for consolidation but does not influence audit selection."""
        subset = select_audit_subset()
        # No element should look like a 3-tuple with a claim family.
        for pair in subset:
            assert len(pair) == 2

    def test_different_seed_gives_different_subset(self) -> None:
        a = select_audit_subset(seed=AUDIT_RNG_SEED)
        b = select_audit_subset(seed=AUDIT_RNG_SEED + 1)
        assert a != b
        assert len(a) == len(b) == _EXPECTED_AUDIT_PAIRS  # same cardinality

    def test_fraction_parameter(self) -> None:
        """A 10% fraction halves the subset (default is 20%)."""
        subset = select_audit_subset(fraction=0.10)
        expected_per_family = int(_N_PAIRS_PER_FAMILY * 0.10)
        assert len(subset) == 4 * expected_per_family
        assert AUDIT_FRACTION == 0.20  # default unchanged

    def test_returns_frozen_set(self) -> None:
        """Frozen for safety: callers must not mutate the audit subset."""
        subset = select_audit_subset()
        assert isinstance(subset, frozenset)


# ---------------------------------------------------------------------------
# enumerate_stage_a


class TestEnumerateStageA:
    def test_base_grid_size_matches_roster(self) -> None:
        keys = enumerate_stage_a()
        base_keys = [k for k in keys if k.action in BASE_ACTIONS]
        assert len(base_keys) == _EXPECTED_BASE_KEYS

    def test_audit_keys_count_matches_audit_pairs(self) -> None:
        keys = enumerate_stage_a()
        audit_keys = [k for k in keys if k.action in AUDIT_ACTIONS]
        assert len(audit_keys) == _EXPECTED_AUDIT_KEYS

    def test_total_count_matches_base_plus_audit(self) -> None:
        keys = enumerate_stage_a()
        assert len(keys) == _EXPECTED_TOTAL_KEYS

    def test_no_duplicates(self) -> None:
        keys = enumerate_stage_a()
        assert len(set(keys)) == len(keys)

    def test_full_cartesian_product(self) -> None:
        keys = enumerate_stage_a()
        instances = {k.instance_id for k in keys}
        perturbations = {k.perturbation_id for k in keys}
        actions = {k.action for k in keys}

        assert instances == set(list_stage_a_instances())
        assert perturbations == set(PERTURBATION_IDS)
        # All 7 actions appear: 5 base + 2 audit (audit subset is non-empty).
        assert actions == set(ACTIONS)

    def test_base_coverage_is_uniform(self) -> None:
        """Every (instance, pert) has all 5 base actions; every (instance, base
        action) has all 16 perturbations. Audit actions appear only on the
        audit subset and are excluded from this uniformity check."""
        from collections import Counter

        keys = enumerate_stage_a()
        base_keys = [k for k in keys if k.action in BASE_ACTIONS]

        per_cell = Counter((k.instance_id, k.perturbation_id) for k in base_keys)
        per_ia = Counter((k.instance_id, k.action) for k in base_keys)

        assert all(c == 5 for c in per_cell.values()), "every cell needs 5 base actions"
        assert len(per_cell) == _N_INSTANCES * len(PERTURBATION_IDS)
        assert all(c == 16 for c in per_ia.values()), "every (instance, base action) needs 16 perts"
        assert len(per_ia) == _N_INSTANCES * len(BASE_ACTIONS)

    def test_audit_actions_match_audit_subset(self) -> None:
        """Every audit (instance, pert) pair in keys is an audit-subset pair,
        and vice versa."""
        keys = enumerate_stage_a()
        audit_keys_pairs = {
            (k.instance_id, k.perturbation_id) for k in keys if k.action in AUDIT_ACTIONS
        }
        assert audit_keys_pairs == set(select_audit_subset())

    def test_each_audit_pair_has_both_seeds(self) -> None:
        """Every audit (instance, pert) pair must have both seed2 and seed3 keys."""
        from collections import Counter

        keys = enumerate_stage_a()
        per_pair = Counter(
            (k.instance_id, k.perturbation_id) for k in keys if k.action in AUDIT_ACTIONS
        )
        assert all(c == 2 for c in per_pair.values()), "audit pair missing a seed"
        assert len(per_pair) == _EXPECTED_AUDIT_PAIRS


# ---------------------------------------------------------------------------
# order_by_size


class TestOrderBySize:
    def test_smallest_instance_first(self) -> None:
        keys = order_by_size(enumerate_stage_a())
        first_n = n_customers_for(keys[0].instance_id)
        last_n = n_customers_for(keys[-1].instance_id)
        assert first_n <= last_n
        # Smallest/largest derived from the roster (resilient to roster changes).
        roster_ns = [n_customers_for(iid) for iid in list_stage_a_instances()]
        assert first_n == min(roster_ns)
        assert last_n == max(roster_ns)

    def test_n_customers_monotonic(self) -> None:
        keys = order_by_size(enumerate_stage_a())
        ns = [n_customers_for(k.instance_id) for k in keys]
        assert ns == sorted(ns), "customer counts must be non-decreasing"

    def test_within_instance_cheap_actions_first(self) -> None:
        keys = order_by_size(enumerate_stage_a())

        # Group by instance, preserving order, and check that within each
        # instance the action cost rank is non-decreasing. Audit variants
        # of pyvrp_60s sit at the tail of the action ordering.
        action_rank = {
            "reuse_direct": 0,
            "nearest_neighbor": 1,
            "clarke_wright": 2,
            "pyvrp_10s": 3,
            "pyvrp_60s": 4,
            "pyvrp_60s_seed2": 5,
            "pyvrp_60s_seed3": 6,
        }
        from itertools import groupby

        for instance_id, group in groupby(keys, key=lambda k: k.instance_id):
            ranks = [action_rank[k.action] for k in group]
            assert ranks == sorted(ranks), (
                f"actions for {instance_id} not in cheap→expensive order: {ranks}"
            )

    def test_first_run_is_smallest_instance_cheapest_action(self) -> None:
        keys = order_by_size(enumerate_stage_a())
        assert keys[0].action == "reuse_direct"
        assert n_customers_for(keys[0].instance_id) == 100

    def test_sort_is_deterministic(self) -> None:
        a = order_by_size(enumerate_stage_a())
        b = order_by_size(enumerate_stage_a())
        assert a == b

    def test_sort_is_stable_under_input_shuffling(self) -> None:
        """Same key set, different input order, same sorted output."""
        import random

        keys = enumerate_stage_a()
        shuffled = list(keys)
        random.Random(42).shuffle(shuffled)
        assert order_by_size(shuffled) == order_by_size(keys)


# ---------------------------------------------------------------------------
# filter_completed


class TestFilterCompleted:
    def test_empty_dir_returns_all(self, tmp_path: Path) -> None:
        keys = enumerate_stage_a()[:10]
        assert filter_completed(keys, tmp_path) == keys

    def test_completed_keys_dropped(self, tmp_path: Path) -> None:
        keys = enumerate_stage_a()[:10]
        # Mark the first 4 as completed.
        for k in keys[:4]:
            save_result(tmp_path, k, _make_result())
        remaining = filter_completed(keys, tmp_path)
        assert remaining == keys[4:]

    def test_failures_are_retried(self, tmp_path: Path) -> None:
        keys = enumerate_stage_a()[:10]
        # First 2 successes, next 3 failures.
        for k in keys[:2]:
            save_result(tmp_path, k, _make_result())
        for k in keys[2:5]:
            save_failure(tmp_path, k, RuntimeError("solver crashed"))
        remaining = filter_completed(keys, tmp_path)
        # Only the 2 successes are dropped. Failures (2..4) and untouched (5..9) stay.
        assert remaining == keys[2:]
        # And specifically: the failed keys are present.
        assert set(keys[2:5]).issubset(set(remaining))

    def test_logs_summary(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        keys = enumerate_stage_a()[:5]
        save_result(tmp_path, keys[0], _make_result())
        save_failure(tmp_path, keys[1], RuntimeError("x"))
        with caplog.at_level(logging.INFO, logger="vrp_copilot_bench.work_plan"):
            filter_completed(keys, tmp_path)
        # Look for the structured summary line.
        summary_lines = [r.message for r in caplog.records if "completed" in r.message]
        assert summary_lines, f"no summary line found in {caplog.records!r}"
        assert "1 completed, 4 remaining, 1 failures" in summary_lines[-1]

    def test_full_filter_pipeline(self, tmp_path: Path) -> None:
        """End-to-end: enumerate → order → simulate partial run → filter."""
        keys = order_by_size(enumerate_stage_a())
        # Simulate completing the first 25 (all small-instance reuse_direct cells).
        for k in keys[:25]:
            save_result(tmp_path, k, _make_result())
        remaining = filter_completed(keys, tmp_path)
        assert len(remaining) == len(keys) - 25
        assert remaining[0] == keys[25]


# ---------------------------------------------------------------------------
# is_large_instance


class TestIsLargeInstance:
    def test_small_instance_not_large(self) -> None:
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")  # 100 customers
        assert is_large_instance(key) is False

    def test_borderline_instance_not_large(self) -> None:
        key = ActionRunKey("X-n401-k29", "CAP_1", "reuse_direct")  # 400 customers
        # Threshold is "above 400", so 400 itself is NOT large.
        assert is_large_instance(key, threshold=400) is False

    def test_large_instance_above_threshold(self) -> None:
        key = ActionRunKey("X-n502-k39", "CAP_1", "reuse_direct")  # 501 customers
        assert is_large_instance(key, threshold=400) is True

    def test_threshold_default_is_400(self) -> None:
        assert DEFAULT_LARGE_THRESHOLD == 400
        # Large at default = above 400.
        key_500 = ActionRunKey("X-n502-k39", "CAP_1", "reuse_direct")
        assert is_large_instance(key_500) is True

    def test_custom_threshold(self) -> None:
        key = ActionRunKey("X-n200-k36", "CAP_1", "reuse_direct")  # 199 customers
        assert is_large_instance(key, threshold=150) is True
        assert is_large_instance(key, threshold=300) is False

    def test_large_keys_are_minority_in_stage_a(self) -> None:
        """Sanity: most Stage A instances are below the 400-customer threshold,
        so the two-phase dispatch isn't pathological. The Phase 3 dispatcher
        will run the small phase first at 6 workers, then the large phase at 4."""
        keys = enumerate_stage_a()
        large = [k for k in keys if is_large_instance(k)]
        large_base = [k for k in large if k.action in BASE_ACTIONS]
        n_large_instances = len({k.instance_id for k in large})

        # Each large instance contributes 16 × 5 = 80 base-action keys; audit
        # keys add a roster-dependent variable amount on top.
        assert len(large_base) == n_large_instances * 80
        # Roster sanity: the >400-customer set is a clear minority.
        total_instances = 75
        assert 0 < n_large_instances < total_instances // 2

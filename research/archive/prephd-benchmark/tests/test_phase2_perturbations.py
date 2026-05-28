"""Tests for Phase 2 perturbation families.

Verifies each perturbation:
  - produces a re-parseable .vrp file
  - preserves the invariants the family is supposed to preserve
  - changes the invariants the family is supposed to change
  - is deterministic (same output from two calls on the same instance)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vrpbench.data.instance import VRPInstance, load_instance
from vrpbench.perturbations.capacity import apply_capacity_reduction
from vrpbench.perturbations.customer_insertion import apply_customer_insertion
from vrpbench.perturbations.localized_demand import apply_localized_demand_inflation
from vrpbench.perturbations.regional_distance import apply_regional_distance_inflation


@pytest.fixture
def toy_path(tmp_path: Path) -> Path:
    """A tiny but non-degenerate VRP instance with coords and demand."""
    content = (
        "NAME : toy10\n"
        "TYPE : CVRP\n"
        "DIMENSION : 11\n"
        "EDGE_WEIGHT_TYPE : EUC_2D\n"
        "CAPACITY : 20\n"
        "NODE_COORD_SECTION\n"
        " 1 50 50\n"
        " 2 10 20\n"
        " 3 15 30\n"
        " 4 20 40\n"
        " 5 30 20\n"
        " 6 35 70\n"
        " 7 60 60\n"
        " 8 65 30\n"
        " 9 70 80\n"
        " 10 80 40\n"
        " 11 90 50\n"
        "DEMAND_SECTION\n"
        " 1 0\n"
        " 2 3\n"
        " 3 5\n"
        " 4 4\n"
        " 5 2\n"
        " 6 6\n"
        " 7 4\n"
        " 8 3\n"
        " 9 7\n"
        " 10 5\n"
        " 11 3\n"
        "DEPOT_SECTION\n"
        " 1\n"
        " -1\n"
        "EOF\n"
    )
    p = tmp_path / "toy10.vrp"
    p.write_text(content)
    return p


def _load(path: Path) -> VRPInstance:
    return load_instance(path)


# --------------------------------------------------------------------
# capacity_reduction (Phase 1 carry-over; regression-covered here too)
# --------------------------------------------------------------------

def test_capacity_reduction_rewrites_capacity_only(toy_path, tmp_path):
    base = _load(toy_path)
    out, new_cap = apply_capacity_reduction(base, 0.8, tmp_path / "out")
    perturbed = _load(out)
    assert perturbed.capacity == new_cap
    assert new_cap == int(round(base.capacity * 0.8))
    assert perturbed.n_customers == base.n_customers
    # Demand unchanged
    np.testing.assert_array_equal(
        np.asarray(perturbed.raw["demand"]), np.asarray(base.raw["demand"])
    )


# --------------------------------------------------------------------
# regional_distance_inflation
# --------------------------------------------------------------------

def test_regional_distance_inflates_region_edges(toy_path, tmp_path):
    base = _load(toy_path)
    out, meta = apply_regional_distance_inflation(base, 1.5, tmp_path / "out")
    perturbed = _load(out)

    base_ew = np.asarray(base.raw["edge_weight"], dtype=float)
    pert_ew = np.asarray(perturbed.raw["edge_weight"], dtype=float)

    # Same shape, preserves 0 diagonal.
    assert base_ew.shape == pert_ew.shape
    for i in range(base_ew.shape[0]):
        assert pert_ew[i, i] == 0

    # At least one pair increases by roughly factor.
    ratios = pert_ew / np.maximum(base_ew, 1e-9)
    off = ratios[~np.eye(ratios.shape[0], dtype=bool)]
    assert np.max(off) > 1.2  # some edges definitely inflated
    # Capacity + demand unchanged
    assert perturbed.capacity == base.capacity


def test_regional_distance_deterministic(toy_path, tmp_path):
    base = _load(toy_path)
    out_a, _ = apply_regional_distance_inflation(base, 1.25, tmp_path / "a")
    out_b, _ = apply_regional_distance_inflation(base, 1.25, tmp_path / "b")
    a = np.asarray(_load(out_a).raw["edge_weight"])
    b = np.asarray(_load(out_b).raw["edge_weight"])
    np.testing.assert_array_equal(a, b)


def test_regional_distance_rejects_factor_below_one(toy_path, tmp_path):
    base = _load(toy_path)
    with pytest.raises(ValueError):
        apply_regional_distance_inflation(base, 0.9, tmp_path / "out")


# --------------------------------------------------------------------
# localized_demand_inflation
# --------------------------------------------------------------------

def test_localized_demand_inflates_only_top_pct(toy_path, tmp_path):
    base = _load(toy_path)
    out, meta = apply_localized_demand_inflation(base, 1.25, tmp_path / "out")
    perturbed = _load(out)

    base_d = np.asarray(base.raw["demand"], dtype=float)
    pert_d = np.asarray(perturbed.raw["demand"], dtype=float)
    # Strictly more customers unchanged than changed (selection is top 10%).
    changed = (pert_d != base_d).sum()
    unchanged = (pert_d == base_d).sum()
    assert changed < unchanged
    # Changed ones must all be >= base (inflation, not reduction).
    for i in range(len(base_d)):
        if base_d[i] > 0 and pert_d[i] != base_d[i]:
            assert pert_d[i] > base_d[i]
    # Capacity unchanged
    assert perturbed.capacity == base.capacity


def test_localized_demand_rejects_factor_at_or_below_one(toy_path, tmp_path):
    base = _load(toy_path)
    with pytest.raises(ValueError):
        apply_localized_demand_inflation(base, 1.0, tmp_path / "out")


# --------------------------------------------------------------------
# customer_insertion
# --------------------------------------------------------------------

def test_customer_insertion_changes_dimension(toy_path, tmp_path):
    base = _load(toy_path)
    out, meta = apply_customer_insertion(base, 3, tmp_path / "out")
    perturbed = _load(out)
    assert perturbed.n_customers == base.n_customers + 3
    # Original coords preserved at the top of the block.
    base_coords = np.asarray(base.raw["node_coord"])
    pert_coords = np.asarray(perturbed.raw["node_coord"])
    np.testing.assert_array_equal(
        pert_coords[: base_coords.shape[0]], base_coords
    )


def test_customer_insertion_deterministic(toy_path, tmp_path):
    base = _load(toy_path)
    out_a, _ = apply_customer_insertion(base, 2, tmp_path / "a")
    out_b, _ = apply_customer_insertion(base, 2, tmp_path / "b")
    a = np.asarray(_load(out_a).raw["node_coord"])
    b = np.asarray(_load(out_b).raw["node_coord"])
    np.testing.assert_array_equal(a, b)

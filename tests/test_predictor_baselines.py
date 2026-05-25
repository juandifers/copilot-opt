"""Tests for the cheap-vs-escalate baseline policy suite.

Exercises the policies, the metric function, and the fold assignment on
small synthetic frames so we don't depend on the locked Stage A
artifact. The end-to-end integration is exercised separately by the
script's CLI smoke run.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from vrp_copilot_bench.predictor_baselines.data import (
    CELL_KEYS,
    CLAIM_FAMILIES,
    build_cheap_eval_frame,
    build_escalation_frame,
    instance_class_from_id,
)
from vrp_copilot_bench.predictor_baselines.folds import assign_instance_folds
from vrp_copilot_bench.predictor_baselines.metrics import (
    align_escalation_labels,
    compute_policy_metrics,
)
from vrp_copilot_bench.predictor_baselines.policies import (
    BlockRateTable,
    block_rule_predictions,
    compute_block_rate_table,
    compute_majority_table,
    feasibility_only_predictions,
    oracle_predictions,
    perturbation_majority_predictions,
)
from vrp_copilot_bench.predictor_baselines.runtime_costs import (
    FALLBACK_RUNTIME_S,
    policy_compute_cost,
    row_runtime,
)


def _make_long_frame() -> pd.DataFrame:
    """Synthetic 2-instance × 2-pert-id × 4-claim × 2-action frame.

    Cheap rows:
      - C001/A (TIME_WINDOW)  → reuse_direct,  feasible=True,  label=1 (OBJ),0 (PV),1 (ST),0 (SCH)
      - C001/B (ORDER_CHANGE) → local_repair_insert, feasible=False, label=NaN, 1, 0, NaN
      - R001/A (TIME_WINDOW)  → reuse_direct,  feasible=True,  label=0,0,1,1
      - R001/B (ORDER_CHANGE) → local_repair_insert, feasible=True, label=1,1,1,1
    Mid-tier (pyvrp_10s) and reference rows added for each cell × claim so
    the escalation-frame join lands on real rows.
    """
    rows = []
    cheap_specs = {
        ("C001", "A", "TIME_WINDOW"):  ("reuse_direct", True, {"OBJ":1, "PLAN_VALIDITY":0, "STRUCT":1, "SCHEDULE":0}),
        ("C001", "B", "ORDER_CHANGE"): ("local_repair_insert", False, {"OBJ":float("nan"), "PLAN_VALIDITY":1, "STRUCT":0, "SCHEDULE":float("nan")}),
        ("R001", "A", "TIME_WINDOW"):  ("reuse_direct", True, {"OBJ":0, "PLAN_VALIDITY":0, "STRUCT":1, "SCHEDULE":1}),
        ("R001", "B", "ORDER_CHANGE"): ("local_repair_insert", True, {"OBJ":1, "PLAN_VALIDITY":1, "STRUCT":1, "SCHEDULE":1}),
    }
    for (iid, pid, pfam), (action, feasible, labels) in cheap_specs.items():
        for fam in CLAIM_FAMILIES:
            rows.append({
                "instance_id": iid, "perturbation_id": pid,
                "perturbation_family": pfam,
                "action": action, "action_tier": "tier", "action_tier_index": 0,
                "is_middle_action": False, "is_reference_action": False,
                "action_runtime_s": FALLBACK_RUNTIME_S[action],
                "action_solver_time_limit": float("nan"),
                "action_seed": float("nan"), "action_valid": True,
                "cheap_action_for_cell": action, "is_cheap_action": True,
                "claim_family": fam, "loss": 0.0, "band": "easy",
                "sufficient_binary": labels[fam],
                "reference_valid": True,
                "reference_struct_unstable": False,
                "reference_obj_unstable": False,
                "action_feasible": feasible,
                "infeasibility_kind": "none" if feasible else "time_window",
                "reference_time_limit_s": 60,
            })
    # Escalation rows (pyvrp_10s and pyvrp_60s_reference) — always sufficient
    # to keep the test simple.
    for (iid, pid, pfam), _ in cheap_specs.items():
        for escalation in ("pyvrp_10s", "pyvrp_60s_reference"):
            for fam in CLAIM_FAMILIES:
                rows.append({
                    "instance_id": iid, "perturbation_id": pid,
                    "perturbation_family": pfam,
                    "action": escalation, "action_tier": "tier", "action_tier_index": 3,
                    "is_middle_action": escalation == "pyvrp_10s",
                    "is_reference_action": escalation == "pyvrp_60s_reference",
                    "action_runtime_s": FALLBACK_RUNTIME_S[escalation],
                    "action_solver_time_limit": (
                        10.0 if escalation == "pyvrp_10s" else 60.0
                    ),
                    "action_seed": 1.0, "action_valid": True,
                    "cheap_action_for_cell": "reuse_direct" if pfam != "ORDER_CHANGE"
                                              else "local_repair_insert",
                    "is_cheap_action": False,
                    "claim_family": fam, "loss": 0.0, "band": "easy",
                    "sufficient_binary": 1.0,
                    "reference_valid": True,
                    "reference_struct_unstable": False,
                    "reference_obj_unstable": False,
                    "action_feasible": True,
                    "infeasibility_kind": "none",
                    "reference_time_limit_s": 60,
                })
    return pd.DataFrame(rows)


def test_instance_class_from_id():
    assert instance_class_from_id("C101") == "C"
    assert instance_class_from_id("R208") == "R"
    assert instance_class_from_id("RC203") == "RC"
    assert instance_class_from_id("Z999") == "?"


def test_build_cheap_eval_frame_invariants():
    long_df = _make_long_frame()
    cheap = build_cheap_eval_frame(long_df, keep_nan_labels=True)
    # 4 cells × 4 claim families.
    assert len(cheap) == 16
    # NaN labels preserved.
    assert cheap["sufficient_binary"].isna().sum() == 2
    # One cheap row per cell × claim_family.
    assert cheap.groupby(list(CELL_KEYS)).size().eq(1).all()
    # ORDER_CHANGE cheap action is local_repair_insert.
    oc = cheap[cheap["perturbation_family"] == "ORDER_CHANGE"]
    assert set(oc["action"]) == {"local_repair_insert"}
    # Non-OC cheap action is reuse_direct.
    tw = cheap[cheap["perturbation_family"] == "TIME_WINDOW"]
    assert set(tw["action"]) == {"reuse_direct"}


def test_build_cheap_eval_frame_drop_nan():
    long_df = _make_long_frame()
    cheap = build_cheap_eval_frame(long_df, keep_nan_labels=False)
    assert cheap["sufficient_binary"].isna().sum() == 0
    assert len(cheap) == 14


def test_build_escalation_frame_one_per_cell():
    long_df = _make_long_frame()
    esc = build_escalation_frame(long_df, "pyvrp_10s")
    assert len(esc) == 16
    assert esc.groupby(list(CELL_KEYS)).size().eq(1).all()


def test_block_rule_predictions_threshold():
    eval_df = pd.DataFrame({
        "claim_family":        ["A", "A", "B", "B"],
        "perturbation_family": ["X", "Y", "X", "Y"],
        "sufficient_binary":   [1.0, 0.0, 1.0, 0.0],
    })
    table = BlockRateTable(rates={
        ("A", "X"): 0.9, ("A", "Y"): 0.2,
        ("B", "X"): 0.5, ("B", "Y"): 0.0,
    })
    out = block_rule_predictions(eval_df, table=table, threshold=0.5)
    assert out.tolist() == [True, False, True, False]
    out = block_rule_predictions(eval_df, table=table, threshold=0.95)
    assert out.tolist() == [False, False, False, False]


def test_block_rule_unseen_combination_is_escalate():
    eval_df = pd.DataFrame({
        "claim_family": ["A"], "perturbation_family": ["Z"],
        "sufficient_binary": [1.0],
    })
    table = BlockRateTable(rates={})  # no training rates
    out = block_rule_predictions(eval_df, table=table, threshold=0.5)
    assert out.tolist() == [False]


def test_oracle_predictions_uses_label():
    eval_df = pd.DataFrame({
        "sufficient_binary": [1.0, 0.0, float("nan"), 1.0],
    })
    out = oracle_predictions(eval_df)
    assert out.tolist() == [True, False, False, True]


def test_feasibility_only_predictions_uses_action_feasible():
    eval_df = pd.DataFrame({"action_feasible": [True, False, True, False]})
    out = feasibility_only_predictions(eval_df)
    assert out.tolist() == [True, False, True, False]


def test_compute_block_rate_table_drops_nan_labels():
    df = pd.DataFrame({
        "claim_family":        ["A", "A", "A", "B"],
        "perturbation_family": ["X", "X", "X", "X"],
        "sufficient_binary":   [1.0, 0.0, float("nan"), 1.0],
    })
    table = compute_block_rate_table(df)
    assert table.rate("A", "X") == pytest.approx(0.5)
    assert table.rate("B", "X") == pytest.approx(1.0)


def test_perturbation_majority_predictions():
    train = pd.DataFrame({
        "claim_family":        ["A", "A", "A", "B", "B"],
        "perturbation_family": ["X", "X", "X", "X", "X"],
        "sufficient_binary":   [1.0, 1.0, 0.0, 0.0, 0.0],
    })
    table = compute_majority_table(train)
    assert table[("A", "X")] == 1
    assert table[("B", "X")] == 0
    eval_df = pd.DataFrame({
        "claim_family":        ["A", "B"],
        "perturbation_family": ["X", "X"],
    })
    out = perturbation_majority_predictions(eval_df, table=table)
    assert out.tolist() == [True, False]


def test_assign_instance_folds_class_balanced():
    iids = [f"C{i:03d}" for i in range(10)] + [f"R{i:03d}" for i in range(10)] + ["RC101"]
    folds = assign_instance_folds(iids, n_folds=5)
    # Every instance assigned exactly once.
    assert len(folds) == 21
    # Folds are 0..4.
    assert set(folds["fold"]) <= {0, 1, 2, 3, 4}
    # Within each class, fold sizes within 1 of each other (round-robin).
    for cls in folds["instance_class"].unique():
        counts = folds[folds["instance_class"] == cls]["fold"].value_counts()
        assert counts.max() - counts.min() <= 1


def test_compute_policy_metrics_gate_only_counts():
    df = pd.DataFrame({
        "instance_id": ["a","a","b","b"],
        "perturbation_id": ["p","p","p","p"],
        "perturbation_family": ["X","X","Y","Y"],
        "claim_family": ["A","B","A","B"],
        "instance_class": ["C","C","R","R"],
        "sufficient_binary": [1.0, 0.0, 1.0, float("nan")],
    })
    accept = np.array([True, True, False, False])
    out = compute_policy_metrics(df, accept_cheap=accept)
    overall = out["overall"].iloc[0]
    # NaN label dropped from labelled subset.
    assert overall["n_rows"] == 3
    assert overall["n_missing_labels"] == 1
    assert overall["accepted_count"] == 2
    assert overall["accepted_correct_count"] == 1
    assert overall["false_accept_count"] == 1
    assert overall["lost_correct_count"] == 1
    assert overall["accepted_precision"] == pytest.approx(0.5)
    assert overall["false_accept_rate"] == pytest.approx(0.5)
    assert overall["lost_correct_rate"] == pytest.approx(0.5)


def test_align_escalation_labels_join_on_cell_keys():
    long_df = _make_long_frame()
    cheap = build_cheap_eval_frame(long_df, keep_nan_labels=False)
    esc = build_escalation_frame(long_df, "pyvrp_10s")
    labels, runtime = align_escalation_labels(cheap, esc)
    assert len(labels) == len(cheap)
    # All escalation rows are sufficient in the fixture.
    assert np.all((labels == 1.0) | np.isnan(labels))
    # Runtime falls back to the fixture's 10s entry.
    assert np.allclose(runtime, FALLBACK_RUNTIME_S["pyvrp_10s"])


def test_row_runtime_falls_back_when_missing():
    assert row_runtime("reuse_direct", None) == FALLBACK_RUNTIME_S["reuse_direct"]
    assert row_runtime("reuse_direct", float("nan")) == FALLBACK_RUNTIME_S["reuse_direct"]
    assert row_runtime("pyvrp_10s", 9.5) == pytest.approx(9.5)


def test_policy_compute_cost_pre_run_cheap():
    accept = np.array([True, False, False])
    cheap_runtime = np.array([0.001, 0.001, 0.001])
    escalation_runtime = np.array([10.0, 10.0, 10.0])

    # cheap_only-style: no escalation pairing.
    cost = policy_compute_cost(
        accept, cheap_runtime, escalation_runtime=None,
        pre_run_cheap_on_escalate=False,
    )
    # accept=True → cheap; accept=False with no escalation → 0.
    assert cost[0] == pytest.approx(0.001)
    assert cost[1] == 0.0

    # gated: cheap up-front + escalation when escalating.
    cost = policy_compute_cost(
        accept, cheap_runtime, escalation_runtime,
        pre_run_cheap_on_escalate=True,
    )
    assert cost[0] == pytest.approx(0.001)
    assert cost[1] == pytest.approx(10.001)
    assert cost[2] == pytest.approx(10.001)

    # always-recompute: skip cheap when escalating.
    cost = policy_compute_cost(
        np.array([False, False, False]),
        cheap_runtime, escalation_runtime,
        pre_run_cheap_on_escalate=False,
    )
    assert math.isclose(cost[0], 10.0)

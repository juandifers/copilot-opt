"""Baseline policy suite for the cheap-vs-escalate routing decision.

Operates on the locked Stage A long-table artifact
(``data/stage_a_vrptw_consolidated_claim_rows.parquet``). The "cheap action"
for a cell follows :data:`vrp_copilot_bench.vrptw.actions.CHEAP_ACTION_FOR_FAMILY`:
``reuse_direct`` for TRAVEL_TIME / TIME_WINDOW / SERVICE_TIME, and
``local_repair_insert`` for ORDER_CHANGE.

Public entry point: :func:`run_baselines` (also exposed as a CLI in
``scripts/run_predictor_baselines.py``).
"""
from .data import (
    CLAIM_FAMILIES,
    ESCALATION_ACTIONS,
    PERTURBATION_FAMILIES,
    build_cheap_eval_frame,
    build_escalation_frame,
    instance_class_from_id,
)
from .folds import assign_instance_folds
from .metrics import compute_policy_metrics
from .policies import (
    POLICY_NAMES,
    block_rule_predictions,
    feasibility_only_predictions,
    perturbation_majority_predictions,
)
from .runner import run_baselines

__all__ = [
    "CLAIM_FAMILIES",
    "ESCALATION_ACTIONS",
    "PERTURBATION_FAMILIES",
    "POLICY_NAMES",
    "assign_instance_folds",
    "block_rule_predictions",
    "build_cheap_eval_frame",
    "build_escalation_frame",
    "compute_policy_metrics",
    "feasibility_only_predictions",
    "instance_class_from_id",
    "perturbation_majority_predictions",
    "run_baselines",
]

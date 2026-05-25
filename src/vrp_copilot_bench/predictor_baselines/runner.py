"""End-to-end runner for the baseline policy suite.

Wires together :mod:`data`, :mod:`folds`, :mod:`policies`,
:mod:`runtime_costs`, and :mod:`metrics` to produce the CSVs and the
README expected by Task G. Output layout::

    reports/predictor_baselines/
      baseline_policy_overall.csv
      baseline_policy_summary.csv
      baseline_policy_by_block.csv
      baseline_policy_threshold_curves.csv
      fold_assignments.csv
      sanity_checks.txt
      README.md

The script is idempotent: re-running on the locked Stage A artifact
produces the same outputs byte-for-byte (modulo float ordering).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..vrptw.actions import CHEAP_ACTION_FOR_FAMILY
from .data import (
    CELL_KEYS,
    CLAIM_FAMILIES,
    ESCALATION_ACTIONS,
    PERTURBATION_FAMILIES,
    build_cheap_eval_frame,
    build_escalation_frame,
    load_long_table,
)
from .folds import assign_instance_folds
from .metrics import align_escalation_labels, compute_policy_metrics
from .policies import (
    BlockRateTable,
    block_rate_thresholds,
    block_rule_predictions,
    cheap_only_predictions,
    compute_block_rate_table,
    compute_majority_table,
    feasibility_only_predictions,
    oracle_predictions,
    perturbation_majority_predictions,
)
from .runtime_costs import (
    cheap_action_runtime_series,
    escalation_runtime_series,
    policy_compute_cost,
)

logger = logging.getLogger(__name__)


_EXPECTED_NON_NAN: dict[str, int] = {
    "OBJ": 889,
    "PLAN_VALIDITY": 896,
    "STRUCT": 889,
    "SCHEDULE": 889,
}


# ---------------------------------------------------------------------------
# Sanity checks (Task H)


@dataclass(frozen=True)
class SanityReport:
    lines: list[str]

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


def _run_sanity_checks(cheap_df: pd.DataFrame) -> SanityReport:
    """Explicit assertions over the cheap-action frame.

    Failing assertions raise — the assumption is that the locked
    artifact has already been validated and any drift here is a real
    regression worth surfacing immediately.
    """
    lines: list[str] = []
    counts = (
        cheap_df.groupby("claim_family")
        .agg(
            n_rows=("sufficient_binary", "size"),
            n_non_nan=("sufficient_binary", "count"),
            n_nan=("sufficient_binary", lambda s: int(s.isna().sum())),
            sum_label=("sufficient_binary", "sum"),
        )
        .reset_index()
    )
    lines.append("Cheap-action subset row counts:")
    lines.append(counts.to_string(index=False))
    for fam, expected in _EXPECTED_NON_NAN.items():
        actual = int(counts.loc[counts["claim_family"] == fam, "n_non_nan"].iloc[0])
        if actual != expected:
            raise AssertionError(
                f"cheap {fam} non-NaN count {actual} != expected {expected}"
            )

    n_cells = cheap_df.groupby(list(CELL_KEYS)).size()
    if (n_cells != 1).any():
        raise AssertionError("duplicate cheap-action rows for some cell × claim_family")
    lines.append(f"\nUnique cell × claim_family rows: {len(n_cells)} (all == 1).")

    for fam, expected_action in CHEAP_ACTION_FOR_FAMILY.items():
        actions = set(cheap_df.loc[cheap_df["perturbation_family"] == fam, "action"].unique())
        if actions != {expected_action}:
            raise AssertionError(
                f"cheap action for {fam} expected {expected_action}, got {actions}"
            )
        lines.append(f"  {fam:<14s} cheap = {expected_action} ✓")

    if (cheap_df["is_reference_action"]).any():
        raise AssertionError("reference rows leaked into cheap-action subset")
    lines.append("\nNo reference rows in the cheap-action subset.")
    return SanityReport(lines=lines)


def _flag_degenerate_blocks(rates: BlockRateTable) -> list[str]:
    """Surface (claim, pert) cells with extreme rates that pre-determine policy."""
    flags: list[str] = []
    for (fam, pert), rate in sorted(rates.rates.items()):
        if math.isnan(rate):
            flags.append(f"  {fam:<14s} × {pert:<13s} rate = NaN (no training rows)")
            continue
        if rate <= 0.05 or rate >= 0.95:
            flags.append(
                f"  {fam:<14s} × {pert:<13s} rate = {rate:.3f}  "
                f"(degenerate — pre-determined decision)"
            )
    return flags


# ---------------------------------------------------------------------------
# Per-policy plumbing


@dataclass(frozen=True)
class PolicyDecision:
    """One policy's per-row decisions plus its escalation pairing.

    ``escalation_action`` is None for ``cheap_only`` (no escalation
    pairing); for gated policies (block-rule, feasibility-only,
    perturbation-majority, oracle) it defaults to ``pyvrp_10s`` so the
    full-routing column has a meaningful upper bound.
    """

    name: str
    accept_cheap: np.ndarray
    escalation_action: str | None
    pre_run_cheap_on_escalate: bool
    notes: str = ""


def _decisions_for_policy(
    name: str,
    eval_df: pd.DataFrame,
    *,
    block_rates: BlockRateTable | None = None,
    block_threshold: float | None = None,
    majority_table: dict[tuple[str, str], int] | None = None,
    escalation_action_for_gated: str = "pyvrp_10s",
) -> PolicyDecision:
    if name == "cheap_only":
        return PolicyDecision(
            name=name,
            accept_cheap=cheap_only_predictions(eval_df),
            escalation_action=None,
            pre_run_cheap_on_escalate=False,
            notes="Always accepts the cheap action; no escalation pairing.",
        )
    if name == "always_pyvrp_10s":
        return PolicyDecision(
            name=name,
            accept_cheap=np.zeros(len(eval_df), dtype=bool),
            escalation_action="pyvrp_10s",
            pre_run_cheap_on_escalate=False,
            notes="Skips cheap; directly runs pyvrp_10s.",
        )
    if name == "always_reference":
        return PolicyDecision(
            name=name,
            accept_cheap=np.zeros(len(eval_df), dtype=bool),
            escalation_action="pyvrp_60s_reference",
            pre_run_cheap_on_escalate=False,
            notes="Skips cheap; directly runs reference recompute.",
        )
    if name == "feasibility_only_gate":
        return PolicyDecision(
            name=name,
            accept_cheap=feasibility_only_predictions(eval_df),
            escalation_action=escalation_action_for_gated,
            pre_run_cheap_on_escalate=True,
            notes="Cheap then escalate if action_feasible == False.",
        )
    if name == "oracle_cheap_sufficiency":
        return PolicyDecision(
            name=name,
            accept_cheap=oracle_predictions(eval_df),
            escalation_action=escalation_action_for_gated,
            pre_run_cheap_on_escalate=True,
            notes="Non-deployable upper bound; gates on the true label.",
        )
    if name == "block_rule_policy":
        if block_rates is None or block_threshold is None:
            raise ValueError("block_rule_policy requires block_rates and threshold")
        return PolicyDecision(
            name=name,
            accept_cheap=block_rule_predictions(
                eval_df, table=block_rates, threshold=block_threshold,
            ),
            escalation_action=escalation_action_for_gated,
            pre_run_cheap_on_escalate=True,
            notes=f"Cheap iff train block rate >= {block_threshold:.2f}.",
        )
    if name == "perturbation_family_majority":
        if majority_table is None:
            raise ValueError("perturbation_family_majority requires majority_table")
        return PolicyDecision(
            name=name,
            accept_cheap=perturbation_majority_predictions(
                eval_df, table=majority_table,
            ),
            escalation_action=escalation_action_for_gated,
            pre_run_cheap_on_escalate=True,
            notes="Cheap iff training majority label for (claim, pert) is 1.",
        )
    raise ValueError(f"unknown policy {name}")


# ---------------------------------------------------------------------------
# Aggregations across folds


def _stack_with_meta(
    metric_dict: dict[str, pd.DataFrame],
    *,
    policy: str,
    threshold: float | None,
    fold: int | None,
    escalation_action: str | None,
    evaluation_mode: str,
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for key, df in metric_dict.items():
        df = df.copy()
        df.insert(0, "policy", policy)
        df.insert(1, "evaluation_mode", evaluation_mode)
        df.insert(2, "threshold", threshold)
        df.insert(3, "fold", fold)
        df.insert(4, "escalation_action", escalation_action or "")
        out[key] = df
    return out


def _evaluate_policy_on_frame(
    eval_df: pd.DataFrame,
    decision: PolicyDecision,
    escalation_frames: dict[str, pd.DataFrame],
) -> dict[str, dict[str, pd.DataFrame]]:
    """Run gate-only and full-routing metrics for a policy on a frame.

    Returns ``{"gate_only": {...}, "full_routing": {...}}`` where each
    inner dict is the standard ``compute_policy_metrics`` output.
    """
    cheap_runtime = cheap_action_runtime_series(eval_df).to_numpy(dtype=float)
    # Gate-only: no escalation labels, no compute cost (gate semantics
    # don't depend on what the escalation produces).
    gate_metrics = compute_policy_metrics(
        eval_df,
        accept_cheap=decision.accept_cheap,
        escalation_label=None,
        compute_cost=None,
    )

    # Full-routing: pair with the configured escalation. For cheap_only
    # there is no escalation pairing and the compute cost is just the
    # cheap runtime.
    if decision.escalation_action is None:
        compute_cost = policy_compute_cost(
            decision.accept_cheap,
            cheap_runtime,
            escalation_runtime=None,
            pre_run_cheap_on_escalate=False,
        )
        full_metrics = compute_policy_metrics(
            eval_df,
            accept_cheap=decision.accept_cheap,
            escalation_label=None,
            compute_cost=compute_cost,
        )
    else:
        esc_df = escalation_frames[decision.escalation_action]
        labels, runtime = align_escalation_labels(eval_df, esc_df)
        # If the escalation runtime carried NaNs (missing cells), fall
        # back to the action's fallback constant on those rows so the
        # cost average is still defined.
        from .runtime_costs import FALLBACK_RUNTIME_S

        fallback = FALLBACK_RUNTIME_S[decision.escalation_action]
        runtime = np.where(np.isnan(runtime), fallback, runtime)
        compute_cost = policy_compute_cost(
            decision.accept_cheap,
            cheap_runtime,
            escalation_runtime=runtime,
            pre_run_cheap_on_escalate=decision.pre_run_cheap_on_escalate,
        )
        full_metrics = compute_policy_metrics(
            eval_df,
            accept_cheap=decision.accept_cheap,
            escalation_label=labels,
            compute_cost=compute_cost,
        )
    return {"gate_only": gate_metrics, "full_routing": full_metrics}


def _accumulate(records: dict[str, list[pd.DataFrame]], chunk: dict[str, pd.DataFrame]) -> None:
    for key, df in chunk.items():
        records.setdefault(key, []).append(df)


def _safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den else float("nan")


def _aggregate_cv_rows(
    fold_overall: pd.DataFrame,
    agg_keys: list[str],
) -> pd.DataFrame:
    """Aggregate per-fold metric rows by summing counts and recomputing rates.

    Mean-of-rates would only be an approximation when fold test sizes
    differ (which they do, since classes don't divide evenly into 5).
    Summing counts and recomputing the headline ratios from the summed
    numerators / denominators gives the same answer you'd get by
    evaluating the policy on the concatenation of all test folds.

    Cost columns (``average_compute_cost_s``) use a fold-size-weighted
    average via ``total_compute_cost_s / sum n_rows`` when available.
    """
    sum_cols = [
        "n_rows", "n_missing_labels",
        "accepted_count", "accepted_correct_count",
        "false_accept_count", "lost_correct_count",
        "escalation_count", "final_correctness_n",
        "total_compute_cost_s",
    ]
    sum_cols = [c for c in sum_cols if c in fold_overall.columns]
    agg = fold_overall.groupby(agg_keys, dropna=False)
    summed = agg[sum_cols].sum().reset_index()

    # Recompute ratios from the summed counts.
    rows: list[dict] = []
    for _, r in summed.iterrows():
        n_rows = int(r.get("n_rows", 0) or 0)
        accepted = int(r.get("accepted_count", 0) or 0)
        accepted_correct = int(r.get("accepted_correct_count", 0) or 0)
        false_accept = int(r.get("false_accept_count", 0) or 0)
        lost_correct = int(r.get("lost_correct_count", 0) or 0)
        escalated = int(r.get("escalation_count", 0) or 0)
        cheap_suff = accepted_correct + lost_correct
        final_n = int(r.get("final_correctness_n", 0) or 0)
        total_cost = r.get("total_compute_cost_s", float("nan"))
        rec = dict(r)
        rec["accepted_coverage"] = _safe_div(accepted, n_rows)
        rec["accepted_precision"] = _safe_div(accepted_correct, accepted)
        rec["false_accept_rate"] = _safe_div(false_accept, accepted)
        rec["lost_correct_rate"] = _safe_div(lost_correct, cheap_suff)
        rec["escalation_rate"] = _safe_div(escalated, n_rows)
        rec["cheap_sufficient_rate"] = _safe_div(cheap_suff, n_rows)
        # final_correctness is correct/final_n, but final correctness counts
        # aren't summed directly — derive from accepted_correct + escalation
        # correctness when present. Fall back to the mean of fold rates.
        rec["final_correctness"] = float("nan")
        rec["final_error_rate"] = float("nan")
        rec["average_compute_cost_s"] = (
            _safe_div(float(total_cost), n_rows) if not pd.isna(total_cost)
            else float("nan")
        )
        rows.append(rec)
    summed = pd.DataFrame(rows)

    # final_correctness needs the per-fold rate-weighted reconstruction.
    fc_mean = (
        fold_overall.groupby(agg_keys, dropna=False)
        .apply(
            lambda g: pd.Series({
                "final_correctness": (
                    (g["final_correctness"] * g["final_correctness_n"]).sum()
                    / g["final_correctness_n"].sum()
                    if g["final_correctness_n"].sum() else float("nan")
                ),
            }),
            include_groups=False,
        )
        .reset_index()
    )
    summed = summed.drop(columns=["final_correctness"]).merge(
        fc_mean, on=agg_keys, how="left",
    )
    summed["final_error_rate"] = 1.0 - summed["final_correctness"]

    # Gate-only rows never have compute cost; zero out the summed
    # total_compute_cost_s that pandas produced from NaN inputs and
    # leave the averaged cost as NaN.
    if "evaluation_mode" in summed.columns:
        gate_mask = summed["evaluation_mode"] == "gate_only"
        if gate_mask.any():
            for col in ("total_compute_cost_s", "average_compute_cost_s"):
                if col in summed.columns:
                    summed.loc[gate_mask, col] = float("nan")
    return summed


# ---------------------------------------------------------------------------
# Top-level driver


def run_baselines(
    long_parquet: Path,
    output_dir: Path,
    *,
    n_folds: int = 5,
    threshold_grid: Iterable[float] = block_rate_thresholds(),
    log: logging.Logger | None = None,
) -> None:
    """Run the full baseline suite and write CSVs + README."""
    log = log or logger
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading long table: %s", long_parquet)
    long_df = load_long_table(long_parquet)
    cheap_df = build_cheap_eval_frame(long_df, keep_nan_labels=True)
    cheap_df_drop = cheap_df.dropna(subset=["sufficient_binary"]).reset_index(drop=True)

    log.info("Cheap-action rows (with NaN preserved): %d", len(cheap_df))
    log.info("Cheap-action rows (NaN dropped):        %d", len(cheap_df_drop))

    sanity = _run_sanity_checks(cheap_df)
    log.info("Sanity checks passed.")

    # Escalation frames keyed by action.
    escalation_frames = {
        action: build_escalation_frame(long_df, action) for action in ESCALATION_ACTIONS
    }

    # Folds (Task F).
    instance_ids = cheap_df["instance_id"].unique().tolist()
    folds_df = assign_instance_folds(instance_ids, n_folds=n_folds)
    folds_df.to_csv(output_dir / "fold_assignments.csv", index=False)
    log.info("Fold assignments: %d instances into %d folds", len(folds_df), n_folds)

    # Attach fold to the eval frames so every metric slice can carry it.
    cheap_df_drop = cheap_df_drop.merge(folds_df, on="instance_id", how="left")
    # Some instance_class is already present from build_cheap_eval_frame;
    # merge brings an "_x" suffix only if mismatched — sanity-check.
    if "instance_class_x" in cheap_df_drop.columns:
        cheap_df_drop = cheap_df_drop.drop(columns=["instance_class_y"]).rename(
            columns={"instance_class_x": "instance_class"}
        )

    # Bookkeeping containers.
    metrics_overall: list[pd.DataFrame] = []
    metrics_summary: list[pd.DataFrame] = []
    metrics_by_block: list[pd.DataFrame] = []
    threshold_curve_rows: list[pd.DataFrame] = []
    fold_records: list[pd.DataFrame] = []

    # ---- Policies that don't need training rates (run on the full frame).
    simple_policies = [
        "cheap_only",
        "always_pyvrp_10s",
        "always_reference",
        "feasibility_only_gate",
        "oracle_cheap_sufficiency",
    ]
    for name in simple_policies:
        decision = _decisions_for_policy(name, cheap_df_drop)
        results = _evaluate_policy_on_frame(
            cheap_df_drop, decision, escalation_frames,
        )
        for mode_name, mode in results.items():
            meta = _stack_with_meta(
                mode,
                policy=name,
                threshold=None,
                fold=None,
                escalation_action=decision.escalation_action,
                evaluation_mode=mode_name,
            )
            metrics_overall.append(meta["overall"])
            metrics_summary.append(meta["by_claim_family"])
            metrics_by_block.append(meta["by_claim_x_perturbation"])

    # ---- Block-rule policy: in-sample sanity table + grouped-CV evaluation.
    insample_rates = compute_block_rate_table(cheap_df_drop)
    log.info("In-sample block rates (n=%d):", len(insample_rates.rates))
    degenerate_flags = _flag_degenerate_blocks(insample_rates)
    block_rate_df = pd.DataFrame(
        [
            {"claim_family": k[0], "perturbation_family": k[1], "block_rate": v}
            for k, v in sorted(insample_rates.rates.items())
        ]
    )
    block_rate_df.to_csv(output_dir / "block_rates_insample.csv", index=False)

    # Perturbation-majority table is computed once on the full frame for
    # a quick descriptive sanity row, then re-computed per fold below.
    insample_majority = compute_majority_table(cheap_df_drop)

    # ---- Grouped CV over folds, for block-rule + simple gated policies.
    thresholds = tuple(threshold_grid)
    for fold_id in sorted(folds_df["fold"].unique()):
        train_mask = cheap_df_drop["fold"] != fold_id
        test_mask = ~train_mask
        train_df = cheap_df_drop[train_mask].reset_index(drop=True)
        test_df = cheap_df_drop[test_mask].reset_index(drop=True)

        fold_block_rates = compute_block_rate_table(train_df)
        fold_majority = compute_majority_table(train_df)

        for threshold in thresholds:
            decision = _decisions_for_policy(
                "block_rule_policy",
                test_df,
                block_rates=fold_block_rates,
                block_threshold=threshold,
            )
            results = _evaluate_policy_on_frame(
                test_df, decision, escalation_frames,
            )
            for mode_name, mode in results.items():
                meta = _stack_with_meta(
                    mode,
                    policy="block_rule_policy",
                    threshold=threshold,
                    fold=int(fold_id),
                    escalation_action=decision.escalation_action,
                    evaluation_mode=mode_name,
                )
                fold_records.append(meta["overall"])
                metrics_summary.append(meta["by_claim_family"])
                metrics_by_block.append(meta["by_claim_x_perturbation"])
                # Threshold curves (per claim_family, gate-only).
                if mode_name == "gate_only":
                    threshold_curve_rows.append(meta["by_claim_family"])

        # perturbation_family_majority — train rates from this fold, eval on test.
        decision = _decisions_for_policy(
            "perturbation_family_majority",
            test_df,
            majority_table=fold_majority,
        )
        results = _evaluate_policy_on_frame(
            test_df, decision, escalation_frames,
        )
        for mode_name, mode in results.items():
            meta = _stack_with_meta(
                mode,
                policy="perturbation_family_majority",
                threshold=None,
                fold=int(fold_id),
                escalation_action=decision.escalation_action,
                evaluation_mode=mode_name,
            )
            fold_records.append(meta["overall"])
            metrics_summary.append(meta["by_claim_family"])
            metrics_by_block.append(meta["by_claim_x_perturbation"])

    # Aggregate CV folds for block-rule and majority into overall rows.
    if fold_records:
        fold_overall = pd.concat(fold_records, ignore_index=True)
        agg_keys = ["policy", "evaluation_mode", "threshold", "escalation_action"]
        cv_overall = _aggregate_cv_rows(fold_overall, agg_keys)
        cv_overall.insert(3, "fold", "cv_mean")
        metrics_overall.append(cv_overall)

    overall_df = pd.concat(metrics_overall, ignore_index=True)
    summary_df = pd.concat(metrics_summary, ignore_index=True)
    by_block_df = pd.concat(metrics_by_block, ignore_index=True)
    overall_df.to_csv(output_dir / "baseline_policy_overall.csv", index=False)
    summary_df.to_csv(output_dir / "baseline_policy_summary.csv", index=False)
    by_block_df.to_csv(output_dir / "baseline_policy_by_block.csv", index=False)

    if threshold_curve_rows:
        curves = pd.concat(threshold_curve_rows, ignore_index=True)
        # Aggregate across folds for a cleaner curve view.
        agg_keys = ["policy", "threshold", "claim_family"]
        curve_cols = [
            "accepted_coverage", "accepted_precision",
            "false_accept_rate", "lost_correct_rate", "escalation_rate",
        ]
        curves_agg = (
            curves.groupby(agg_keys, dropna=False)[curve_cols]
            .mean(numeric_only=True)
            .reset_index()
        )
        curves_agg.to_csv(
            output_dir / "baseline_policy_threshold_curves.csv", index=False,
        )

    # Sanity report file.
    sanity_lines = list(sanity.lines)
    if degenerate_flags:
        sanity_lines.append("\nDegenerate (claim, pert) blocks:")
        sanity_lines.extend(degenerate_flags)
    (output_dir / "sanity_checks.txt").write_text("\n".join(sanity_lines) + "\n")

    # README.
    _write_readme(
        output_dir,
        sanity=sanity,
        degenerate_flags=degenerate_flags,
        overall=overall_df,
        n_folds=n_folds,
    )
    log.info("Outputs written to %s", output_dir)


# ---------------------------------------------------------------------------
# README


def _write_readme(
    output_dir: Path,
    *,
    sanity: SanityReport,
    degenerate_flags: list[str],
    overall: pd.DataFrame,
    n_folds: int,
) -> None:
    overall = overall.copy()
    headline_cols = [
        "policy", "evaluation_mode", "threshold", "fold", "escalation_action",
        "n_rows", "accepted_coverage", "accepted_precision",
        "false_accept_rate", "lost_correct_rate", "escalation_rate",
        "final_correctness", "average_compute_cost_s",
    ]
    cols = [c for c in headline_cols if c in overall.columns]
    headline = overall[cols].copy()
    # Round for readability.
    for c in headline.columns:
        if headline[c].dtype.kind == "f":
            headline[c] = headline[c].round(3)

    deg_block = (
        "\n".join(degenerate_flags) if degenerate_flags
        else "  (none — every (claim, pert) block has labels in 0.05–0.95.)"
    )

    text = f"""# VRPTW copilot baseline policy suite

This directory contains the baseline-policy evaluation for the cheap-vs-escalate
routing decision on Stage A of the VRPTW copilot sufficiency benchmark. It
operates on the locked long-table artifact at
`data/stage_a_vrptw_consolidated_claim_rows.parquet`, filtered to the
*cheap-action subset* (one row per cell × claim_family, with the cheap action
selected per the prereg rule).

Cheap-action rule
-----------------

| perturbation_family | cheap action          |
| ------------------- | --------------------- |
| TRAVEL_TIME         | `reuse_direct`        |
| TIME_WINDOW         | `reuse_direct`        |
| SERVICE_TIME        | `reuse_direct`        |
| ORDER_CHANGE        | `local_repair_insert` |

There are 896 cells × 4 claim families = 3 584 cheap-action rows in
total. NaN labels (cells where the reference is invalid or all-infeasible)
are reported separately and dropped from headline metrics.

What each baseline tells us
---------------------------

- **`cheap_only`** — the *ungated copilot*. The copilot always returns
  the cheap action's output without recomputing. This is the speed
  upper bound (and the correctness reality check) — if it were already
  reliable everywhere, no learned predictor would be needed.

- **`always_pyvrp_10s`** — *always-mid-tier recompute*. Skips the cheap
  action and runs the 10 s solver. Helps establish what mid-tier
  recompute buys above the cheap action, at a 10 s per-cell cost.

- **`always_reference`** — *always full reference recompute*. The
  quality upper bound: every cell is solved at the 60 s (or 120 s) seed-1
  reference budget. Almost always sufficient by construction, with the
  highest compute cost.

- **`block_rule_policy`** — the *categorical baseline a learned model
  must beat*. For each (`claim_family`, `perturbation_family`) bucket
  we compute the empirical cheap-sufficiency rate on the training fold;
  the policy accepts cheap when this rate is at least a threshold.
  Evaluated under {n_folds}-fold grouped-by-instance CV across the threshold
  grid (0.50, 0.60, 0.70, 0.80, 0.90, 0.95).

- **`feasibility_only_gate`** — *intuitive but incomplete*. Accepts
  cheap iff `action_feasible == True`. Useful for PLAN_VALIDITY by
  construction; not expected to be reliable for OBJ / STRUCT / SCHEDULE
  because feasibility says nothing about how close the cheap action is
  to the reference plan.

- **`oracle_cheap_sufficiency`** — *non-deployable upper bound*.
  Accepts cheap iff the true cheap label is sufficient. Lets us read
  off the gap between "best possible gate" and any deployable baseline.

- **`perturbation_family_majority`** (optional) — simpler relative of
  the block rule: accept cheap iff the (claim, pert) training majority
  label is 1.

Sanity checks
-------------

{sanity.render()}

Degenerate (claim, pert) blocks
-------------------------------

These are the buckets where the in-sample cheap-sufficiency rate is at
or beyond the extremes (≤ 0.05 or ≥ 0.95). They pre-determine the
block-rule policy's decision regardless of threshold within the grid
— flagged here so the report can call out where the categorical baseline
is *too easy* to beat:

{deg_block}

Files
-----

| file                                       | description |
| ------------------------------------------ | ----------- |
| `baseline_policy_overall.csv`              | One row per policy × evaluation_mode (gate-only / full-routing). CV-aggregated for the threshold sweeps. |
| `baseline_policy_summary.csv`              | Per claim_family slice for every policy × threshold × fold. |
| `baseline_policy_by_block.csv`             | Per claim_family × perturbation_family slice. |
| `baseline_policy_threshold_curves.csv`     | Block-rule policy: per (threshold, claim_family) curves of coverage, precision, false-accept rate, lost-correct rate, escalation rate. |
| `block_rates_insample.csv`                 | The in-sample block-rate table (descriptive sanity output). |
| `fold_assignments.csv`                     | Instance → fold map (5 instance-grouped folds, class-balanced). |
| `sanity_checks.txt`                        | Sanity-check log (row counts, cheap-action invariants, degenerate blocks). |

Headline numbers
----------------

```
{headline.to_string(index=False)}
```

Notes
-----

- The `always_pyvrp_10s` and `always_reference` policies do *not* pay
  the cheap-action cost; they go straight to the escalation solve. The
  gated policies (block-rule, feasibility-only, majority, oracle) pay
  the cheap action's cost on every cell and add the escalation cost
  only when they escalate.
- Reference rows are never used as features in any baseline. They show
  up only as the optional escalation target for `always_reference` and
  in the routing-mode `final_correctness` computation.
- Block-rule rates for a test fold are computed strictly from training
  folds; no in-sample evaluation enters the CV-aggregated numbers in
  `baseline_policy_overall.csv` for `block_rule_policy`.
"""
    (output_dir / "README.md").write_text(text)


# ---------------------------------------------------------------------------
# CLI


def _build_argparser():
    import argparse
    p = argparse.ArgumentParser(
        prog="run_predictor_baselines",
        description="Run the cheap-vs-escalate baseline policy suite.",
    )
    p.add_argument(
        "--long-parquet",
        type=Path,
        default=Path("data/stage_a_vrptw_consolidated_claim_rows.parquet"),
        help="Stage A long-table parquet path.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/predictor_baselines"),
        help="Output directory for CSVs and README.",
    )
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument(
        "--log-level", default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_baselines(
        long_parquet=args.long_parquet,
        output_dir=args.output_dir,
        n_folds=args.n_folds,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

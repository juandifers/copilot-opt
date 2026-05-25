"""Metric tables, threshold sweeps, calibration curves, routing outcomes.

The OOF probability frame (one row per cheap cell × claim_family × model
× feature_set) drives every report in this module:

- :func:`per_fold_classifier_metrics` — AUROC / AUPRC / Brier per fold.
- :func:`threshold_sweep` — accepted_coverage, accepted_precision,
  false_accept_rate, lost_correct_rate, escalation_rate, final_correctness,
  average_compute_cost_s, p95_compute_cost_s for each threshold.
- :func:`calibration_curve_rows` — reliability curve bins.
- :func:`nonmonotone_preservation` — for the 54 STRUCT/SCHEDULE
  ``cheap=1, py10=0`` cells, count how many the predictor accepts.

All threshold-sweep tables reuse the same routing rule the baseline
suite uses: ``final = cheap_label if accept else escalation_label`` on
the same cell × claim_family join.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

from ..predictor_baselines.data import CELL_KEYS
from ..predictor_baselines.metrics import align_escalation_labels
from ..predictor_baselines.runtime_costs import (
    FALLBACK_RUNTIME_S,
    cheap_action_runtime_series,
    policy_compute_cost,
)


@dataclass(frozen=True)
class ThresholdConfig:
    """Threshold grid for the predictor sweep.

    0.98 is included because the calibrated LR sometimes assigns very
    high probability to "easy" PLAN_VALIDITY cells; the grid exercises
    that regime.
    """

    grid: tuple[float, ...] = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.98)


def per_fold_classifier_metrics(oof_long: pd.DataFrame) -> pd.DataFrame:
    """Per-fold AUROC / AUPRC / Brier for each (model, feature_set, claim, fold).

    Folds where the held-out test set is degenerate (single-class) emit
    NaN for AUROC / AUPRC; Brier is always well-defined.
    """
    keys = ["model", "feature_set", "claim_family", "fold"]
    rows: list[dict] = []
    for k, sub in oof_long.groupby(keys):
        y = sub["sufficient_binary"].astype(int).to_numpy()
        p = sub["pred_proba"].to_numpy(dtype=float)
        try:
            auroc = roc_auc_score(y, p)
        except ValueError:
            auroc = float("nan")
        try:
            auprc = average_precision_score(y, p)
        except ValueError:
            auprc = float("nan")
        brier = brier_score_loss(y, p)
        rec = dict(zip(keys, k))
        rec.update(
            {
                "n_rows": len(sub),
                "n_positive": int(y.sum()),
                "auroc": float(auroc),
                "auprc": float(auprc),
                "brier": float(brier),
                "pos_rate": float(y.mean()),
            }
        )
        rows.append(rec)
    return pd.DataFrame(rows)


def cv_aggregate_classifier_metrics(per_fold: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-fold metrics: weighted mean by ``n_rows`` for ratios."""
    keys = ["model", "feature_set", "claim_family"]
    rows: list[dict] = []
    for k, g in per_fold.groupby(keys):
        n = g["n_rows"].to_numpy(dtype=float)
        w = n / max(n.sum(), 1.0)
        rec = dict(zip(keys, k))
        rec["n_rows"] = int(g["n_rows"].sum())
        rec["n_positive"] = int(g["n_positive"].sum())
        rec["pos_rate"] = rec["n_positive"] / rec["n_rows"] if rec["n_rows"] else float("nan")
        for col in ("auroc", "auprc", "brier"):
            vals = g[col].to_numpy(dtype=float)
            mask = ~np.isnan(vals)
            if mask.any():
                rec[col + "_cv_mean"] = float(np.average(vals[mask], weights=w[mask]))
                rec[col + "_cv_std"] = float(np.std(vals[mask]))
            else:
                rec[col + "_cv_mean"] = float("nan")
                rec[col + "_cv_std"] = float("nan")
        rows.append(rec)
    return pd.DataFrame(rows)


def calibration_curve_rows(oof_long: pd.DataFrame, *, n_bins: int = 10) -> pd.DataFrame:
    """Reliability bins per (model, feature_set, claim_family).

    Uses equal-width bins from 0 to 1; rows record the bin centre, mean
    predicted probability inside the bin, observed positive rate, and
    bin count. Empty bins are emitted with NaN values so the curve can
    be plotted directly.
    """
    keys = ["model", "feature_set", "claim_family"]
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict] = []
    for k, sub in oof_long.groupby(keys):
        y = sub["sufficient_binary"].astype(int).to_numpy()
        p = sub["pred_proba"].to_numpy(dtype=float)
        for i in range(n_bins):
            lo, hi = bin_edges[i], bin_edges[i + 1]
            mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
            rec = dict(zip(keys, k))
            rec["bin_index"] = i
            rec["bin_lo"] = float(lo)
            rec["bin_hi"] = float(hi)
            rec["bin_center"] = float((lo + hi) / 2)
            rec["bin_count"] = int(mask.sum())
            rec["bin_mean_pred"] = float(p[mask].mean()) if mask.any() else float("nan")
            rec["bin_observed_rate"] = (
                float(y[mask].mean()) if mask.any() else float("nan")
            )
            rows.append(rec)
    return pd.DataFrame(rows)


def _routing_outcome_arrays(
    cheap_label: np.ndarray,
    accept: np.ndarray,
    escalation_label: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(final, final_mask)``: final correctness signal + valid mask."""
    final = np.where(accept, cheap_label, escalation_label)
    final_mask = ~np.isnan(final)
    return final, final_mask


def _p95(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.quantile(values, 0.95))


def _compute_threshold_metrics_block(
    sub: pd.DataFrame,
    *,
    threshold: float,
    cheap_label: np.ndarray,
    cheap_runtime: np.ndarray,
    escalation_label: np.ndarray,
    escalation_runtime: np.ndarray,
) -> dict[str, float]:
    """All gate + routing metrics for a single slice at a single threshold."""
    p = sub["pred_proba"].to_numpy(dtype=float)
    accept = p >= threshold
    label = cheap_label
    n_rows = len(sub)
    accepted = int(accept.sum())
    cheap_sufficient = int((label == 1.0).sum())
    accepted_correct = int(((label == 1.0) & accept).sum())
    false_accept = accepted - accepted_correct
    lost_correct = int(((label == 1.0) & ~accept).sum())
    escalated = n_rows - accepted

    final, final_mask = _routing_outcome_arrays(label, accept, escalation_label)
    n_final = int(final_mask.sum())
    correct = int((final[final_mask] == 1.0).sum())

    compute_cost = policy_compute_cost(
        accept,
        cheap_runtime,
        escalation_runtime=escalation_runtime,
        pre_run_cheap_on_escalate=True,
    )
    return {
        "n_rows": n_rows,
        "accepted_count": accepted,
        "accepted_coverage": accepted / n_rows if n_rows else float("nan"),
        "accepted_correct_count": accepted_correct,
        "accepted_precision": (
            accepted_correct / accepted if accepted else float("nan")
        ),
        "false_accept_count": false_accept,
        "false_accept_rate": (
            false_accept / accepted if accepted else float("nan")
        ),
        "lost_correct_count": lost_correct,
        "lost_correct_rate": (
            lost_correct / cheap_sufficient if cheap_sufficient else float("nan")
        ),
        "escalation_count": escalated,
        "escalation_rate": escalated / n_rows if n_rows else float("nan"),
        "cheap_sufficient_rate": (
            cheap_sufficient / n_rows if n_rows else float("nan")
        ),
        "final_correctness_n": n_final,
        "final_correctness": correct / n_final if n_final else float("nan"),
        "final_error_rate": (1 - correct / n_final) if n_final else float("nan"),
        "average_compute_cost_s": (
            float(np.mean(compute_cost)) if len(compute_cost) else float("nan")
        ),
        "total_compute_cost_s": (
            float(np.sum(compute_cost)) if len(compute_cost) else float("nan")
        ),
        "p95_compute_cost_s": _p95(compute_cost),
    }


def threshold_sweep(
    oof_long: pd.DataFrame,
    escalation_df: pd.DataFrame,
    *,
    grid: tuple[float, ...] = ThresholdConfig().grid,
    extra_group_columns: Iterable[str] = (),
) -> pd.DataFrame:
    """Threshold sweep for every (model, feature_set, claim_family[, extras]).

    ``escalation_df`` is the pyvrp_10s escalation frame from
    :func:`vrp_copilot_bench.predictor_baselines.data.build_escalation_frame`.
    Rows in ``oof_long`` are joined to it on cell × claim_family; the
    fallback runtime constant fills any missing escalation rows.
    """
    extra = list(extra_group_columns)
    base_keys = ["model", "feature_set", "claim_family"]
    keys = base_keys + extra
    rows: list[dict] = []
    fallback_esc = FALLBACK_RUNTIME_S["pyvrp_10s"]
    for k, sub in oof_long.groupby(keys):
        sub = sub.reset_index(drop=True)
        cheap_label = sub["sufficient_binary"].to_numpy(dtype=float)
        cheap_runtime = cheap_action_runtime_series(sub).to_numpy(dtype=float)
        esc_labels, esc_runtime = align_escalation_labels(sub, escalation_df)
        esc_runtime = np.where(np.isnan(esc_runtime), fallback_esc, esc_runtime)
        for t in grid:
            metrics = _compute_threshold_metrics_block(
                sub,
                threshold=t,
                cheap_label=cheap_label,
                cheap_runtime=cheap_runtime,
                escalation_label=esc_labels,
                escalation_runtime=esc_runtime,
            )
            rec = dict(zip(keys, k))
            rec["threshold"] = float(t)
            rec.update(metrics)
            rows.append(rec)
    return pd.DataFrame(rows)


def nonmonotone_preservation(
    oof_long: pd.DataFrame,
    escalation_df: pd.DataFrame,
    *,
    grid: tuple[float, ...] = ThresholdConfig().grid,
) -> pd.DataFrame:
    """For STRUCT / SCHEDULE non-monotone cells, count predictor acceptance.

    A "non-monotone cell" is a cell × claim_family in STRUCT or SCHEDULE
    where the cheap label is 1 and the pyvrp_10s label is 0. The report
    shows how many of these cells the predictor accepts at each
    threshold — high acceptance means the gate is preserving the cases
    where recomputation would hurt.
    """
    nm_cells = _build_nonmonotone_cells(oof_long, escalation_df)
    rows: list[dict] = []
    for (model, fs, cf), sub in oof_long.groupby(["model", "feature_set", "claim_family"]):
        if cf not in {"STRUCT", "SCHEDULE"}:
            continue
        nm_cf = nm_cells[nm_cells["claim_family"] == cf]
        join = sub.merge(
            nm_cf[list(CELL_KEYS)].assign(_nm=True),
            on=list(CELL_KEYS),
            how="left",
        )
        nm_mask = join["_nm"].astype("boolean").fillna(False).astype(bool).to_numpy()
        for t in grid:
            accept = join["pred_proba"].to_numpy(dtype=float) >= t
            n_cases = int(nm_mask.sum())
            n_accepted = int((nm_mask & accept).sum())
            rows.append(
                {
                    "model": model,
                    "feature_set": fs,
                    "claim_family": cf,
                    "threshold": float(t),
                    "n_cases": n_cases,
                    "n_accepted": n_accepted,
                    "acceptance_rate": (
                        n_accepted / n_cases if n_cases else float("nan")
                    ),
                }
            )
    return pd.DataFrame(rows)


def _build_nonmonotone_cells(
    oof_long: pd.DataFrame,
    escalation_df: pd.DataFrame,
) -> pd.DataFrame:
    """Cells × claim_family with cheap=1 and pyvrp_10s=0 (STRUCT/SCHEDULE)."""
    cheap_subset = (
        oof_long[oof_long["model"] == oof_long["model"].iloc[0]]
        .drop_duplicates(subset=list(CELL_KEYS))[
            list(CELL_KEYS) + ["sufficient_binary"]
        ]
        .rename(columns={"sufficient_binary": "cheap_sufficient"})
    )
    py10 = escalation_df[list(CELL_KEYS) + ["sufficient_binary"]].rename(
        columns={"sufficient_binary": "py10_sufficient"}
    )
    joined = cheap_subset.merge(py10, on=list(CELL_KEYS), how="left")
    return joined[
        (joined["cheap_sufficient"] == 1)
        & (joined["py10_sufficient"] == 0)
        & joined["claim_family"].isin(["STRUCT", "SCHEDULE"])
    ].reset_index(drop=True)


def pareto_frontier(
    df: pd.DataFrame,
    *,
    correctness_col: str = "final_correctness",
    cost_col: str = "average_compute_cost_s",
) -> np.ndarray:
    """Boolean mask marking rows that are Pareto-best across (cost, correctness).

    A point P dominates Q if ``P.correctness >= Q.correctness`` AND
    ``P.cost <= Q.cost`` with at least one strict inequality. Rows with
    NaN cost or correctness are never on the frontier.
    """
    n = len(df)
    cost = df[cost_col].to_numpy(dtype=float)
    corr = df[correctness_col].to_numpy(dtype=float)
    on_frontier = np.zeros(n, dtype=bool)
    valid = ~(np.isnan(cost) | np.isnan(corr))
    for i in range(n):
        if not valid[i]:
            continue
        dominated = False
        for j in range(n):
            if i == j or not valid[j]:
                continue
            if (
                cost[j] <= cost[i]
                and corr[j] >= corr[i]
                and (cost[j] < cost[i] or corr[j] > corr[i])
            ):
                dominated = True
                break
        on_frontier[i] = not dominated
    return on_frontier


def per_cell_decisions(
    oof_long: pd.DataFrame,
    escalation_df: pd.DataFrame,
    *,
    threshold: float,
) -> pd.DataFrame:
    """Per-cell decision arrays for a fixed (model, feature_set, threshold).

    Returns a long frame with columns:
      instance_id, perturbation_id, claim_family, fold, model, feature_set,
      threshold, cheap_label, escalation_label, accept, final_correct, compute_cost.

    Used as the input to :func:`paired_cell_bootstrap_cis`.
    """
    fallback_esc = FALLBACK_RUNTIME_S["pyvrp_10s"]
    pieces: list[pd.DataFrame] = []
    keys = ["model", "feature_set", "claim_family"]
    for key, sub in oof_long.groupby(keys):
        sub = sub.reset_index(drop=True)
        cheap_label = sub["sufficient_binary"].to_numpy(dtype=float)
        cheap_rt = cheap_action_runtime_series(sub).to_numpy(dtype=float)
        esc_labels, esc_rt = align_escalation_labels(sub, escalation_df)
        esc_rt = np.where(np.isnan(esc_rt), fallback_esc, esc_rt)
        accept = sub["pred_proba"].to_numpy(dtype=float) >= threshold
        final = np.where(accept, cheap_label, esc_labels)
        compute = policy_compute_cost(
            accept,
            cheap_rt,
            escalation_runtime=esc_rt,
            pre_run_cheap_on_escalate=True,
        )
        rec = sub[
            ["instance_id", "perturbation_id", "claim_family", "fold"]
        ].copy()
        rec["model"] = key[0]
        rec["feature_set"] = key[1]
        rec["threshold"] = float(threshold)
        rec["cheap_label"] = cheap_label
        rec["escalation_label"] = esc_labels
        rec["accept"] = accept
        rec["final_correct"] = final
        rec["compute_cost"] = compute
        pieces.append(rec)
    return pd.concat(pieces, ignore_index=True)


def paired_cell_bootstrap_cis(
    cells_a: pd.DataFrame,
    cells_b: pd.DataFrame,
    *,
    n_resamples: int = 1000,
    seed: int = 0,
    stratify_by_fold: bool = True,
) -> dict[str, float]:
    """Paired bootstrap CIs on (Δ correctness, Δ compute).

    ``cells_a`` and ``cells_b`` must align row-wise on
    ``(instance_id, perturbation_id, claim_family)``. Resamples cells
    with replacement (stratified by fold when present so the fold mix
    is preserved) and returns the 2.5/97.5 percentile of
    ``mean(final_correct_a) - mean(final_correct_b)`` and
    ``mean(compute_cost_a) - mean(compute_cost_b)``.

    NaN labels are dropped from the correctness-difference numerator/denominator
    only — compute cost is always defined.
    """
    keys = ["instance_id", "perturbation_id", "claim_family"]
    a = cells_a.sort_values(keys).reset_index(drop=True)
    b = cells_b.sort_values(keys).reset_index(drop=True)
    if len(a) != len(b):
        raise ValueError(
            f"cells_a ({len(a)}) and cells_b ({len(b)}) must align row-wise"
        )
    if not (a[keys].values == b[keys].values).all():
        raise ValueError("cells_a and cells_b row keys do not match after sort")

    corr_a = a["final_correct"].to_numpy(dtype=float)
    corr_b = b["final_correct"].to_numpy(dtype=float)
    cost_a = a["compute_cost"].to_numpy(dtype=float)
    cost_b = b["compute_cost"].to_numpy(dtype=float)
    folds = a["fold"].to_numpy() if stratify_by_fold and "fold" in a.columns else None

    rng = np.random.default_rng(seed)
    n = len(a)
    d_corr = np.empty(n_resamples, dtype=float)
    d_cost = np.empty(n_resamples, dtype=float)

    if folds is None:
        idx_pool = np.arange(n)
        for r in range(n_resamples):
            idx = rng.choice(idx_pool, size=n, replace=True)
            d_corr[r] = _nan_mean(corr_a[idx]) - _nan_mean(corr_b[idx])
            d_cost[r] = float(np.mean(cost_a[idx])) - float(np.mean(cost_b[idx]))
    else:
        groups: dict[int, np.ndarray] = {
            int(f): np.where(folds == f)[0] for f in np.unique(folds)
        }
        for r in range(n_resamples):
            sample_idx = np.concatenate(
                [
                    rng.choice(idxs, size=len(idxs), replace=True)
                    for idxs in groups.values()
                ]
            )
            d_corr[r] = (
                _nan_mean(corr_a[sample_idx]) - _nan_mean(corr_b[sample_idx])
            )
            d_cost[r] = (
                float(np.mean(cost_a[sample_idx]))
                - float(np.mean(cost_b[sample_idx]))
            )

    return {
        "delta_correctness_mean": float(np.nanmean(d_corr)),
        "delta_correctness_ci_lo": float(np.nanpercentile(d_corr, 2.5)),
        "delta_correctness_ci_hi": float(np.nanpercentile(d_corr, 97.5)),
        "delta_compute_mean": float(np.nanmean(d_cost)),
        "delta_compute_ci_lo": float(np.nanpercentile(d_cost, 2.5)),
        "delta_compute_ci_hi": float(np.nanpercentile(d_cost, 97.5)),
        "n_cells": n,
        "n_resamples": int(n_resamples),
    }


def _nan_mean(values: np.ndarray) -> float:
    mask = ~np.isnan(values)
    if not mask.any():
        return float("nan")
    return float(values[mask].mean())


def restrict_to_non_degenerate(oof_long: pd.DataFrame) -> pd.DataFrame:
    """Drop the degenerate OBJ × {TIME_WINDOW, TRAVEL_TIME} blocks.

    These are flagged by the baseline suite as having an in-sample cheap
    sufficiency rate at the extreme (>= 0.95), so they pre-determine the
    block-rule baseline regardless of threshold and inflate any
    deployable policy's headline numbers.
    """
    degenerate = [("OBJ", "TIME_WINDOW"), ("OBJ", "TRAVEL_TIME")]
    mask = pd.Series(True, index=oof_long.index)
    for cf, pf in degenerate:
        mask &= ~((oof_long["claim_family"] == cf) & (oof_long["perturbation_family"] == pf))
    return oof_long[mask].reset_index(drop=True)

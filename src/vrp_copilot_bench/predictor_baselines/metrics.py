"""Gate-only and full-routing metrics for a single policy slice.

Two evaluation modes:

- **Gate-only** answers "does the policy accept cheap only when cheap is
  sufficient?". Metrics: coverage, accepted_precision, false_accept_rate,
  lost_correct_rate, escalation_rate. NaN labels are excluded — they
  represent reference-invalid / all-infeasible cells that the
  cheap-vs-escalate question is not defined for.
- **Full-routing** plugs the escalation row's ``sufficient_binary`` in
  whenever the policy escalates, producing a per-row final correctness
  signal and an average compute cost.

Both modes are computed off a single :class:`PolicyEvalRow` constructor
that aligns the cheap-action frame, the escalation frame (if any), and
the policy's ``accept_cheap`` decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from .data import CELL_KEYS


@dataclass(frozen=True)
class PolicyEvalRow:
    """All per-row signals a metric function needs.

    ``cheap_label`` is the cheap action's ``sufficient_binary`` for the
    cell (NaN allowed). ``escalation_label`` is the escalation action's
    sufficiency on the same cell (NaN when the policy isn't paired with
    an escalation, or when the cell is undefined under that action).
    """

    df: pd.DataFrame  # cheap-action rows
    accept_cheap: np.ndarray
    cheap_runtime: np.ndarray
    escalation_label: np.ndarray | None = None
    escalation_runtime: np.ndarray | None = None
    compute_cost: np.ndarray | None = None


def _gate_metrics(cheap_label: np.ndarray, accept: np.ndarray) -> dict[str, float]:
    """Gate-only metrics on the **labelled** subset.

    Rows with NaN ``cheap_label`` are excluded — they are undefined.
    """
    mask = ~np.isnan(cheap_label)
    n_rows = int(mask.sum())
    n_missing = int((~mask).sum())
    if n_rows == 0:
        nan = float("nan")
        return {
            "n_rows": n_rows,
            "n_missing_labels": n_missing,
            "accepted_count": 0,
            "accepted_coverage": nan,
            "accepted_correct_count": 0,
            "accepted_precision": nan,
            "false_accept_count": 0,
            "false_accept_rate": nan,
            "lost_correct_count": 0,
            "lost_correct_rate": nan,
            "escalation_count": 0,
            "escalation_rate": nan,
            "cheap_sufficient_rate": nan,
        }
    label = cheap_label[mask].astype(bool)
    pred = accept[mask].astype(bool)

    accepted = int(pred.sum())
    escalated = n_rows - accepted
    accepted_correct = int((pred & label).sum())
    false_accept = accepted - accepted_correct
    cheap_sufficient = int(label.sum())
    lost_correct = int((~pred & label).sum())

    return {
        "n_rows": n_rows,
        "n_missing_labels": n_missing,
        "accepted_count": accepted,
        "accepted_coverage": accepted / n_rows,
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
        "escalation_rate": escalated / n_rows,
        "cheap_sufficient_rate": cheap_sufficient / n_rows,
    }


def _routing_metrics(
    cheap_label: np.ndarray,
    accept: np.ndarray,
    escalation_label: np.ndarray | None,
    compute_cost: np.ndarray | None,
) -> dict[str, float]:
    """Full-routing metrics: the policy's final correctness and compute.

    Final correctness for a row is taken from ``cheap_label`` if the
    policy accepts cheap and from ``escalation_label`` otherwise. Rows
    where the selected outcome's label is NaN are excluded from
    correctness; they are still reflected in the compute-cost average so
    the cost figure doesn't silently lose them.
    """
    out: dict[str, float] = {}
    if escalation_label is None:
        # No escalation pairing: final outcome ≡ cheap-only.
        final = np.where(accept, cheap_label, np.nan)
    else:
        final = np.where(accept, cheap_label, escalation_label)

    final_mask = ~np.isnan(final)
    n_final = int(final_mask.sum())
    if n_final > 0:
        correct = int((final[final_mask] == 1.0).sum())
        out["final_correctness_n"] = n_final
        out["final_correctness"] = correct / n_final
        out["final_error_rate"] = 1.0 - correct / n_final
    else:
        out["final_correctness_n"] = 0
        out["final_correctness"] = float("nan")
        out["final_error_rate"] = float("nan")

    if compute_cost is not None and len(compute_cost):
        out["average_compute_cost_s"] = float(np.mean(compute_cost))
        out["total_compute_cost_s"] = float(np.sum(compute_cost))
    else:
        out["average_compute_cost_s"] = float("nan")
        out["total_compute_cost_s"] = float("nan")
    return out


def _full_metric_dict(
    cheap_label: np.ndarray,
    accept: np.ndarray,
    escalation_label: np.ndarray | None,
    compute_cost: np.ndarray | None,
) -> dict[str, float]:
    out = _gate_metrics(cheap_label, accept)
    out.update(_routing_metrics(cheap_label, accept, escalation_label, compute_cost))
    return out


def compute_policy_metrics(
    df: pd.DataFrame,
    *,
    accept_cheap: np.ndarray,
    escalation_label: np.ndarray | None = None,
    compute_cost: np.ndarray | None = None,
    extra_group_columns: Iterable[str] = (),
) -> dict[str, pd.DataFrame]:
    """Compute metric tables for a single policy slice.

    Returns a dict with keys:
      * ``overall``                 — one-row aggregate;
      * ``by_claim_family``         — per claim_family;
      * ``by_perturbation_family``  — per perturbation_family;
      * ``by_claim_x_perturbation`` — full grid;
      * ``by_instance_class``       — per Solomon class;
      * ``by_claim_x_class``        — claim_family × Solomon class.

    ``extra_group_columns`` is forwarded as an additional grouping
    (currently used by the runner to slice block-rule sweeps by
    threshold and fold).
    """
    cheap_label = df["sufficient_binary"].to_numpy(dtype=float)
    accept = np.asarray(accept_cheap, dtype=bool)
    if len(accept) != len(df):
        raise ValueError("accept_cheap length must match df length")

    overall = pd.DataFrame(
        [_full_metric_dict(cheap_label, accept, escalation_label, compute_cost)]
    )

    def slice_metrics(group_cols: list[str]) -> pd.DataFrame:
        records: list[dict] = []
        idx = df.reset_index(drop=True)
        for keys, sub in idx.groupby(group_cols):
            if not isinstance(keys, tuple):
                keys = (keys,)
            sub_idx = sub.index.to_numpy()
            sub_label = cheap_label[sub_idx]
            sub_accept = accept[sub_idx]
            sub_esc = escalation_label[sub_idx] if escalation_label is not None else None
            sub_cost = compute_cost[sub_idx] if compute_cost is not None else None
            row = dict(zip(group_cols, keys))
            row.update(_full_metric_dict(sub_label, sub_accept, sub_esc, sub_cost))
            records.append(row)
        return pd.DataFrame(records)

    out = {
        "overall": overall,
        "by_claim_family": slice_metrics(["claim_family"]),
        "by_perturbation_family": slice_metrics(["perturbation_family"]),
        "by_claim_x_perturbation": slice_metrics(
            ["claim_family", "perturbation_family"]
        ),
    }
    if "instance_class" in df.columns:
        out["by_instance_class"] = slice_metrics(["instance_class"])
        out["by_claim_x_class"] = slice_metrics(["claim_family", "instance_class"])
    extra = [c for c in extra_group_columns if c in df.columns]
    if extra:
        out["by_extra"] = slice_metrics(extra)
    return out


def align_escalation_labels(
    cheap_df: pd.DataFrame,
    escalation_df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-cheap-row ``(escalation_label, escalation_runtime)``.

    The escalation frame is joined on cell × claim_family so the order
    matches the cheap frame's row order. Missing cells (e.g., no
    pyvrp_10s row for an OC cheap row that was tagged as cheap) emit
    NaN, which the metric functions interpret as "outcome undefined".
    """
    keys = list(CELL_KEYS)
    if "action_runtime_s" not in escalation_df.columns:
        raise ValueError("escalation_df missing action_runtime_s")
    join = cheap_df[keys].merge(
        escalation_df[keys + ["sufficient_binary", "action_runtime_s"]],
        how="left",
        on=keys,
        suffixes=("", "_esc"),
    )
    labels = join["sufficient_binary"].to_numpy(dtype=float)
    runtime = join["action_runtime_s"].to_numpy(dtype=float)
    return labels, runtime

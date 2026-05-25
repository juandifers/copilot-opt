"""Compute-cost accounting for the baseline policy suite.

The benchmark records ``action_runtime_s`` per row, which we prefer when
present. The fallbacks below match the prereg-stated solver budgets and
the observed wall-clock averages from the locked Stage A artifact:

    reuse_direct          ~0.001 s
    local_repair_insert   ~0.276 s
    construct_feasible    ~0.108 s
    pyvrp_10s             10.0 s
    pyvrp_60s_reference   reference_time_limit_s on the row (60 or 120 s)

``policy_compute_cost`` puts these together for the per-row policy cost:
cheap_only pays only the cheap action; gated policies pay the cheap
action up-front and add the escalation cost when they escalate;
always-recompute policies are configured to either pre-run the cheap or
go straight to the escalation (see :func:`policy_compute_cost`).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

#: Fallback per-action runtime when ``action_runtime_s`` is missing or NaN.
FALLBACK_RUNTIME_S: dict[str, float] = {
    "reuse_direct": 0.001,
    "local_repair_insert": 0.248,
    "construct_feasible": 0.100,
    "pyvrp_10s": 10.0,
    "pyvrp_60s_reference": 60.0,
}


def _coerce_runtime(value: float | None, fallback: float) -> float:
    if value is None:
        return float(fallback)
    if isinstance(value, float) and math.isnan(value):
        return float(fallback)
    return float(value)


def row_runtime(action: str, runtime_value: float | None) -> float:
    """Per-row runtime in seconds; falls back to the constant if missing."""
    return _coerce_runtime(runtime_value, FALLBACK_RUNTIME_S[action])


def reference_runtime(
    runtime_value: float | None,
    reference_time_limit_s: float | int | None,
) -> float:
    """Reference runtime falls back to the row's ``reference_time_limit_s``.

    The locked artifact carries 60 s for most cells and 120 s for the 256
    re-collected cells; preferring the recorded wall time when present
    keeps the cost faithful to what the solver actually spent.
    """
    if runtime_value is not None and not (
        isinstance(runtime_value, float) and math.isnan(runtime_value)
    ):
        return float(runtime_value)
    if reference_time_limit_s is None or (
        isinstance(reference_time_limit_s, float)
        and math.isnan(reference_time_limit_s)
    ):
        return FALLBACK_RUNTIME_S["pyvrp_60s_reference"]
    return float(reference_time_limit_s)


def cheap_action_runtime_series(cheap_df: pd.DataFrame) -> pd.Series:
    """Vector of cheap-row runtimes (seconds), one per cheap row."""
    actions = cheap_df["action"].to_numpy()
    raw = cheap_df["action_runtime_s"].to_numpy(dtype=float)
    out = np.empty(len(cheap_df), dtype=float)
    for i, (a, r) in enumerate(zip(actions, raw)):
        out[i] = row_runtime(a, r)
    return pd.Series(out, index=cheap_df.index, name="cheap_runtime_s")


def escalation_runtime_series(
    escalation_df: pd.DataFrame,
    escalation_action: str,
) -> pd.Series:
    """Vector of escalation-row runtimes (seconds), one per escalation row."""
    raw = escalation_df["action_runtime_s"].to_numpy(dtype=float)
    if escalation_action == "pyvrp_60s_reference":
        if "reference_time_limit_s" in escalation_df.columns:
            limits = escalation_df["reference_time_limit_s"].to_numpy(dtype=float)
        else:
            limits = np.full(len(escalation_df), np.nan, dtype=float)
        out = np.array(
            [reference_runtime(r, lim) for r, lim in zip(raw, limits)],
            dtype=float,
        )
    else:
        out = np.array(
            [row_runtime(escalation_action, r) for r in raw],
            dtype=float,
        )
    return pd.Series(out, index=escalation_df.index, name="escalation_runtime_s")


def policy_compute_cost(
    accept_cheap: np.ndarray,
    cheap_runtime: np.ndarray,
    escalation_runtime: np.ndarray | None,
    *,
    pre_run_cheap_on_escalate: bool,
) -> np.ndarray:
    """Per-row compute cost (seconds) for a policy.

    - ``cheap_only``-style policies pass ``escalation_runtime=None`` so the
      cost is just the cheap action's runtime.
    - Gated policies (cheap then escalate on the gate) set
      ``pre_run_cheap_on_escalate=True``: cost = cheap + escalation when
      escalating, cheap otherwise. This matches the deployed copilot loop
      where the cheap action is always tried before deciding to escalate.
    - "Always recompute" baselines (``always_pyvrp_10s`` / ``always_reference``)
      set ``pre_run_cheap_on_escalate=False`` and ``accept_cheap`` is all
      ``False``, so the cost is just the escalation runtime — they skip the
      cheap step entirely.

    The two conventions are explicit in the policy summary so the report
    can quote both numbers without ambiguity.
    """
    cost = np.where(accept_cheap, cheap_runtime, 0.0)
    if escalation_runtime is not None:
        escalated = ~accept_cheap
        cost = cost + np.where(escalated, escalation_runtime, 0.0)
        if pre_run_cheap_on_escalate:
            cost = cost + np.where(escalated, cheap_runtime, 0.0)
    return cost

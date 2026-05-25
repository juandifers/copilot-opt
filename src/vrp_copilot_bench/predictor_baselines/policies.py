"""Baseline policies that produce per-row accept-cheap decisions.

Each policy returns a boolean ``accept_cheap`` array aligned to the
input frame's row order. ``True`` means "use the cheap action's output";
``False`` means "escalate to the policy's configured escalation action".

The policies are deliberately simple so that the report can attribute
any gains beyond them to genuine signal in the features rather than to
the easy structural priors a learned model would otherwise exploit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

#: Canonical ordering used in summary tables.
POLICY_NAMES: tuple[str, ...] = (
    "cheap_only",
    "always_pyvrp_10s",
    "always_reference",
    "block_rule_policy",
    "feasibility_only_gate",
    "perturbation_family_majority",
    "oracle_cheap_sufficiency",
)


@dataclass(frozen=True)
class BlockRateTable:
    """Per (claim_family, perturbation_family) cheap-sufficiency rate.

    ``rates[(claim_family, perturbation_family)]`` is the empirical
    sufficiency rate computed on a training fold (or globally). NaN
    cells indicate that no training rows existed for that combination —
    treated as "do not accept" by :func:`block_rule_predictions`.
    """

    rates: dict[tuple[str, str], float]

    def rate(self, claim_family: str, perturbation_family: str) -> float:
        return self.rates.get((claim_family, perturbation_family), float("nan"))


def compute_block_rate_table(train_df: pd.DataFrame) -> BlockRateTable:
    """Cheap-sufficiency rate per (claim_family, perturbation_family).

    Rows with NaN ``sufficient_binary`` are excluded from the rate
    denominator — they are undefined cells (reference-invalid /
    all-infeasible) rather than a cheap-failure signal.
    """
    df = train_df.dropna(subset=["sufficient_binary"])
    grouped = (
        df.groupby(["claim_family", "perturbation_family"])["sufficient_binary"]
        .mean()
    )
    rates = {tuple(k): float(v) for k, v in grouped.items()}
    return BlockRateTable(rates=rates)


def block_rule_predictions(
    eval_df: pd.DataFrame,
    *,
    table: BlockRateTable,
    threshold: float,
) -> np.ndarray:
    """Accept cheap when training block rate at ``(family, pert)`` >= threshold.

    NaN block rates (combination unseen in training) produce ``False``
    (escalate) — the safe default when we have no evidence.
    """
    rates = np.array(
        [
            table.rate(row.claim_family, row.perturbation_family)
            for row in eval_df.itertuples(index=False)
        ],
        dtype=float,
    )
    decisions = rates >= float(threshold)
    decisions = decisions & ~np.isnan(rates)
    return decisions


def feasibility_only_predictions(eval_df: pd.DataFrame) -> np.ndarray:
    """Accept cheap iff ``action_feasible`` is True on the cheap-action row."""
    return eval_df["action_feasible"].to_numpy(dtype=bool)


def cheap_only_predictions(eval_df: pd.DataFrame) -> np.ndarray:
    """Always accept the cheap action."""
    return np.ones(len(eval_df), dtype=bool)


def always_escalate_predictions(eval_df: pd.DataFrame) -> np.ndarray:
    """Never accept the cheap action."""
    return np.zeros(len(eval_df), dtype=bool)


def oracle_predictions(eval_df: pd.DataFrame) -> np.ndarray:
    """Accept cheap iff the cell's cheap label is sufficient.

    Not deployable — used as an upper bound for any cheap-vs-escalate
    gate. NaN labels become ``False`` (escalate), consistent with the
    convention that undefined cells aren't credited as cheap-sufficient.
    """
    labels = eval_df["sufficient_binary"].to_numpy(dtype=float)
    decisions = labels == 1.0
    return decisions


def compute_majority_table(train_df: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Per (claim_family, perturbation_family) majority cheap label (0/1).

    Tie or empty → 0. Used by ``perturbation_family_majority`` — a
    simpler relative of the block-rule policy that doesn't pick a
    threshold.
    """
    df = train_df.dropna(subset=["sufficient_binary"])
    grouped = df.groupby(["claim_family", "perturbation_family"])["sufficient_binary"]
    table: dict[tuple[str, str], int] = {}
    for key, vals in grouped:
        suff_ones = int((vals == 1.0).sum())
        suff_zeros = int((vals == 0.0).sum())
        table[tuple(key)] = 1 if suff_ones > suff_zeros else 0
    return table


def perturbation_majority_predictions(
    eval_df: pd.DataFrame,
    *,
    table: dict[tuple[str, str], int],
) -> np.ndarray:
    """Accept cheap when the training majority label for the cell's
    (claim_family, perturbation_family) bucket is 1."""
    out = np.zeros(len(eval_df), dtype=bool)
    for i, row in enumerate(eval_df.itertuples(index=False)):
        key = (row.claim_family, row.perturbation_family)
        out[i] = bool(table.get(key, 0) == 1)
    return out


@dataclass(frozen=True)
class ExtendedBlockRateTable:
    """Per (claim_family, perturbation_family, perturbation_magnitude, instance_class)
    cheap-sufficiency rate.

    This is the *fair categorical baseline* a learned model with Set A
    must beat: it uses the same 4-dimensional bucket as Set A
    (claim × pert_family × pert_magnitude × instance_class) so any
    learned gain over it is signal beyond block memorisation.
    NaN cells indicate the bucket was empty in training; treated as
    "do not accept" by :func:`block_rule_extended_predictions`.
    """

    rates: dict[tuple[str, str, int, str], float]

    def rate(
        self,
        claim_family: str,
        perturbation_family: str,
        perturbation_magnitude: int,
        instance_class: str,
    ) -> float:
        return self.rates.get(
            (claim_family, perturbation_family, perturbation_magnitude, instance_class),
            float("nan"),
        )


def compute_extended_block_rate_table(
    train_df: pd.DataFrame,
) -> ExtendedBlockRateTable:
    """Cheap-sufficiency rate per extended 4-key bucket.

    ``train_df`` must carry ``perturbation_magnitude`` and
    ``instance_class``; rows with NaN ``sufficient_binary`` are
    excluded from the denominator.
    """
    df = train_df.dropna(subset=["sufficient_binary"])
    keys = [
        "claim_family",
        "perturbation_family",
        "perturbation_magnitude",
        "instance_class",
    ]
    grouped = df.groupby(keys)["sufficient_binary"].mean()
    rates: dict[tuple[str, str, int, str], float] = {}
    for k, v in grouped.items():
        cf, pf, pm, ic = k
        rates[(str(cf), str(pf), int(pm), str(ic))] = float(v)
    return ExtendedBlockRateTable(rates=rates)


def block_rule_extended_predictions(
    eval_df: pd.DataFrame,
    *,
    table: ExtendedBlockRateTable,
    threshold: float,
) -> np.ndarray:
    """Accept cheap when training 4-key rate >= threshold.

    NaN bucket rates (unseen in training) produce ``False`` (escalate).
    """
    rates = np.array(
        [
            table.rate(
                row.claim_family,
                row.perturbation_family,
                int(row.perturbation_magnitude),
                row.instance_class,
            )
            for row in eval_df.itertuples(index=False)
        ],
        dtype=float,
    )
    decisions = rates >= float(threshold)
    decisions = decisions & ~np.isnan(rates)
    return decisions


def block_rule_extended_rates(
    eval_df: pd.DataFrame,
    *,
    table: ExtendedBlockRateTable,
) -> np.ndarray:
    """Return per-row bucket rate (NaN → 0.0).

    Used to surface the extended block rule as a "pseudo-predictor" so
    it can pass through the predictor's threshold-sweep code path.
    """
    rates = np.array(
        [
            table.rate(
                row.claim_family,
                row.perturbation_family,
                int(row.perturbation_magnitude),
                row.instance_class,
            )
            for row in eval_df.itertuples(index=False)
        ],
        dtype=float,
    )
    return np.where(np.isnan(rates), 0.0, rates)


def block_rate_thresholds(
    extra: Iterable[float] = (),
) -> tuple[float, ...]:
    """Standard threshold grid used by the report tables."""
    grid = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
    return tuple(sorted({*grid, *extra}))

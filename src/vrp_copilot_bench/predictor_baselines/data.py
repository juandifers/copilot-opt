"""Loaders that turn the Stage A long table into evaluation frames.

Two derived frames drive the policy suite:

- :func:`build_cheap_eval_frame` — one row per cell × claim_family,
  restricted to the protocol cheap action. NaN labels are preserved so
  callers can report missingness explicitly before dropping for metrics.
- :func:`build_escalation_frame` — one row per cell × claim_family for a
  fixed escalation action (``pyvrp_10s`` or ``pyvrp_60s_reference``).
  Used by full-routing evaluation modes.

Both frames carry ``instance_class`` derived from the Solomon naming
convention (C/R/RC) so the runner can fold-balance and aggregate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from ..vrptw.actions import CHEAP_ACTION_FOR_FAMILY

#: Claim families covered by the cheap-action sufficiency benchmark.
CLAIM_FAMILIES: tuple[str, ...] = ("OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE")

#: Perturbation families. ORDER_CHANGE is the only one with a non-reuse cheap.
PERTURBATION_FAMILIES: tuple[str, ...] = (
    "TRAVEL_TIME",
    "TIME_WINDOW",
    "SERVICE_TIME",
    "ORDER_CHANGE",
)

#: Escalation actions used by ``always_pyvrp_10s`` and ``always_reference``.
ESCALATION_ACTIONS: tuple[str, ...] = ("pyvrp_10s", "pyvrp_60s_reference")

#: Identifies a single cell × claim_family row.
CELL_KEYS: tuple[str, ...] = ("instance_id", "perturbation_id", "claim_family")


def instance_class_from_id(instance_id: str) -> str:
    """Solomon naming: ``C*`` → C, ``R*`` → R, ``RC*`` → RC.

    Returns ``"?"`` for ids that don't match the expected pattern so
    downstream aggregations can flag them without crashing.
    """
    if instance_id.startswith("RC"):
        return "RC"
    if instance_id[:1] in {"C", "R"}:
        return instance_id[:1]
    return "?"


def _attach_instance_class(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["instance_class"] = df["instance_id"].map(instance_class_from_id)
    return df


def load_long_table(parquet_path: str | Path) -> pd.DataFrame:
    """Read the Stage A long table and attach ``instance_class``."""
    df = pd.read_parquet(parquet_path)
    return _attach_instance_class(df)


def _validate_cheap_action_assignment(df: pd.DataFrame) -> None:
    """The locked artifact tags one cheap row per cell. Validate the rule.

    Only families that appear in ``df`` are checked — synthetic frames
    used in tests don't necessarily exercise all four families.
    """
    present_families = set(df["perturbation_family"].unique())
    for fam, expected in CHEAP_ACTION_FOR_FAMILY.items():
        if fam not in present_families:
            continue
        actual = set(df.loc[df["perturbation_family"] == fam, "action"].unique())
        if actual != {expected}:
            raise AssertionError(
                f"cheap action for {fam} expected {{'{expected}'}}, got {actual}"
            )


def _validate_one_cheap_row_per_cell(df: pd.DataFrame) -> None:
    counts = df.groupby(list(CELL_KEYS)).size()
    bad = counts[counts != 1]
    if len(bad):
        raise AssertionError(
            f"{len(bad)} cell × claim_family pairs do not have exactly one cheap row;"
            f" first offender: {bad.index[0]} (count={int(bad.iloc[0])})"
        )


def build_cheap_eval_frame(
    long_df: pd.DataFrame,
    *,
    claim_families: Iterable[str] = CLAIM_FAMILIES,
    keep_nan_labels: bool = True,
) -> pd.DataFrame:
    """Cheap-action subset of the long table.

    The returned frame contains one row per cell × claim_family for the
    protocol cheap action, with ``instance_class`` attached. NaN labels
    are preserved by default so callers can report missingness before
    they drop. Pass ``keep_nan_labels=False`` to drop them upfront.

    Validates:
      * exactly one cheap row per cell × claim_family;
      * ORDER_CHANGE cheap rows are ``local_repair_insert``;
      * non-ORDER_CHANGE cheap rows are ``reuse_direct``.
    """
    if "instance_class" not in long_df.columns:
        long_df = _attach_instance_class(long_df)
    cheap = long_df[long_df["is_cheap_action"]].copy()
    cheap = cheap[cheap["claim_family"].isin(tuple(claim_families))].copy()
    cheap = cheap.reset_index(drop=True)
    _validate_one_cheap_row_per_cell(cheap)
    _validate_cheap_action_assignment(cheap)
    if not keep_nan_labels:
        cheap = cheap.dropna(subset=["sufficient_binary"]).reset_index(drop=True)
    return cheap


def build_escalation_frame(
    long_df: pd.DataFrame,
    escalation_action: str,
    *,
    claim_families: Iterable[str] = CLAIM_FAMILIES,
) -> pd.DataFrame:
    """One row per cell × claim_family for the chosen escalation action.

    Used by full-routing evaluation: when a policy escalates, the routed
    sufficiency is read off this row's ``sufficient_binary``. The row
    also carries ``action_runtime_s`` so the compute-cost accounting can
    use the actual observed wall time when available.
    """
    if escalation_action not in ESCALATION_ACTIONS:
        raise ValueError(
            f"escalation_action {escalation_action!r} not in {ESCALATION_ACTIONS}"
        )
    if "instance_class" not in long_df.columns:
        long_df = _attach_instance_class(long_df)
    esc = long_df[long_df["action"] == escalation_action].copy()
    esc = esc[esc["claim_family"].isin(tuple(claim_families))].copy()
    esc = esc.reset_index(drop=True)
    counts = esc.groupby(list(CELL_KEYS)).size()
    bad = counts[counts > 1]
    if len(bad):
        raise AssertionError(
            f"{len(bad)} cell × claim_family pairs have >1 {escalation_action} rows"
        )
    return esc

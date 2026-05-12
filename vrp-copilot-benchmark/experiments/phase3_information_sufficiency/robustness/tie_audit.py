"""Section 5 — λ=0 tie-breaking audit.

At λ=0 the policy objective collapses to the raw loss. PyVRP @ 60s is
the reference, so its loss vs itself is exactly zero on every cell. Any
other action that also achieves loss=0 (or is tied at the cell minimum)
should ideally not "win" the cell — but the original ``min(scored,
key=scored.get)`` pivot on a Python dict picks the FIRST-inserted action
with the minimum value, and the action insertion order is

    reuse_direct → nearest_neighbor → clarke_wright → pyvrp_10s → pyvrp_60s

so reuse_direct wins ties over pyvrp_60s on objective claims whenever
the fixed solution happens to be optimal under the perturbation, and
similarly pyvrp_10s wins ties over pyvrp_60s when 10s is enough to find
the same solution.

This module enumerates the ties at λ=0, reports which actions tie the
minimum, and records what would change under alternative tie-breakers.

Outputs:
  phase3_lambda_tie_audit.json   structured summary
  table_lambda_zero_ties.csv     per-cell tie membership
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import pandas as pd

from experiments.phase3_information_sufficiency.robustness._action_table import (
    ACTIONS,
    CLAIM_FAMILIES,
)


# Tie tolerance: float-equality on losses. Phase 3 errors are computed with
# different denominators per action, so we use a small absolute tolerance.
LOSS_EPS = 1e-9


def _ties_at_lambda_zero(action_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per cell with tie membership at λ=0."""
    rows = []
    grp = action_df.groupby(
        ["instance_id", "scenario_id", "perturbation_family",
         "perturbation_magnitude", "claim_family"], dropna=False,
    )
    for key, sub in grp:
        usable = sub[sub["loss"].notna()]
        if usable.empty:
            continue
        action_to_loss = dict(zip(usable["action"], usable["loss"]))
        action_to_runtime = dict(zip(usable["action"], usable["runtime_sec"]))
        min_loss = float(min(action_to_loss.values()))
        # Actions tied at the minimum within tolerance.
        tied = sorted(
            [a for a, l in action_to_loss.items()
             if math.isfinite(float(l)) and abs(float(l) - min_loss) <= LOSS_EPS],
            key=lambda a: ACTIONS.index(a),
        )
        # 'Original' tie-break: first-inserted action wins (matches Phase 3 main).
        original_winner = tied[0]
        # Alternative: the cheapest-runtime action among the tied set.
        cheapest_runtime_winner = min(
            tied, key=lambda a: float(action_to_runtime.get(a, float("inf")))
        )
        # Alternative: the strictest (PyVRP 60s if tied, else first-inserted).
        strict_winner = "pyvrp_60s" if "pyvrp_60s" in tied else original_winner

        rows.append({
            "instance_id": key[0],
            "scenario_id": key[1],
            "perturbation_family": key[2],
            "perturbation_magnitude": key[3],
            "claim_family": key[4],
            "min_loss": min_loss,
            "n_tied": len(tied),
            "tied_actions": ";".join(tied),
            "is_tie": len(tied) > 1,
            "original_winner": original_winner,
            "cheapest_runtime_winner": cheapest_runtime_winner,
            "strict_winner": strict_winner,
        })
    return pd.DataFrame(rows)


def write_outputs(action_df: pd.DataFrame, out_dir: Path) -> dict:
    log = logging.getLogger("phase3.robustness.tie_audit")
    df = _ties_at_lambda_zero(action_df)
    df.to_csv(out_dir / "table_lambda_zero_ties.csv", index=False)
    log.info("wrote table_lambda_zero_ties.csv (%d rows)", len(df))

    audit: dict = {
        "tolerance": LOSS_EPS,
        "tie_break_rule": (
            "Python's `min(dict, key=dict.get)` returns the first-inserted "
            "key with the minimum value. The action dict is built by "
            f"iterating ACTIONS = {list(ACTIONS)}, so reuse_direct wins "
            "ties over nearest_neighbor, which wins over clarke_wright, "
            "and so on; pyvrp_60s wins ties only if every other action "
            "fails to match its loss."
        ),
        "by_claim_family": {},
        "shifts": {},
    }

    for fam in CLAIM_FAMILIES:
        sub = df[df["claim_family"] == fam]
        if sub.empty:
            audit["by_claim_family"][fam] = {"n": 0}
            continue
        n = int(len(sub))
        n_ties = int(sub["is_tie"].sum())
        wins_pyvrp_60s_orig = int((sub["original_winner"] == "pyvrp_60s").sum())
        wins_pyvrp_60s_strict = int((sub["strict_winner"] == "pyvrp_60s").sum())
        wins_pyvrp_60s_cheap = int((sub["cheapest_runtime_winner"] == "pyvrp_60s").sum())
        # Win counts for the original tie-break, by action.
        win_counts_orig = sub["original_winner"].value_counts().to_dict()
        win_counts_strict = sub["strict_winner"].value_counts().to_dict()
        win_counts_cheap = sub["cheapest_runtime_winner"].value_counts().to_dict()
        audit["by_claim_family"][fam] = {
            "n": n,
            "n_with_ties": n_ties,
            "tie_share_pct": 100.0 * n_ties / n,
            "wins_pyvrp_60s_original_pct": 100.0 * wins_pyvrp_60s_orig / n,
            "wins_pyvrp_60s_strict_pct": 100.0 * wins_pyvrp_60s_strict / n,
            "wins_pyvrp_60s_cheapest_runtime_pct": 100.0 * wins_pyvrp_60s_cheap / n,
            "share_pct_original_tiebreak": {
                a: 100.0 * win_counts_orig.get(a, 0) / n for a in ACTIONS
            },
            "share_pct_strict_tiebreak": {
                a: 100.0 * win_counts_strict.get(a, 0) / n for a in ACTIONS
            },
            "share_pct_cheapest_runtime_tiebreak": {
                a: 100.0 * win_counts_cheap.get(a, 0) / n for a in ACTIONS
            },
        }

        # Where do non-pyvrp_60s wins come from? Most-common runner-up
        # winners under the original rule — these are the "honest" non-60s
        # cells (where the cheaper action actually has a strictly lower loss).
        non60 = sub[(sub["original_winner"] != "pyvrp_60s") & (~sub["is_tie"])]
        audit["by_claim_family"][fam]["honest_non_60s_wins_pct"] = (
            100.0 * len(non60) / n
        )

    # Across all families, overall shift summary.
    n_total = int(len(df))
    if n_total > 0:
        cells_changed_strict = int((df["strict_winner"] != df["original_winner"]).sum())
        cells_changed_cheap = int((df["cheapest_runtime_winner"] != df["original_winner"]).sum())
        audit["shifts"] = {
            "n_cells_total": n_total,
            "cells_changed_under_strict_tiebreak_pct": 100.0 * cells_changed_strict / n_total,
            "cells_changed_under_cheapest_runtime_tiebreak_pct": 100.0 * cells_changed_cheap / n_total,
        }

    out_path = out_dir / "phase3_lambda_tie_audit.json"
    out_path.write_text(json.dumps(audit, indent=2, default=str))
    log.info("wrote %s", out_path.name)
    return audit

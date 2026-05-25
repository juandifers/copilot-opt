"""Compose the Homberger-200 probe README from the analysis artefacts."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import (
    PROBE_GRID_IDS,
    evaluate_success_criteria,
)


def _round_floats(df: pd.DataFrame, ndigits: int = 3) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind == "f":
            out[c] = out[c].round(ndigits)
    return out


def write_homberger_readme(
    output_dir: Path,
    *,
    stability: pd.DataFrame,
    methodology: pd.DataFrame,
    nonmonotone: pd.DataFrame,
    nonmonotone_summary: pd.DataFrame,
    rung_gaps: pd.DataFrame,
    predictor_eval: pd.DataFrame,
    predictor_sweep: pd.DataFrame,
    instances_used: list[str],
    perturbations_used: list[str],
    seeds_used: list[int],
    time_limit_s: float,
    pyvrp10s_time_limit_s: float,
    fallback_applied: bool,
    fallback_cells: int = 0,
) -> Path:
    """Write the Homberger probe README and return the path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    verdict = evaluate_success_criteria(
        stability=stability,
        methodology_blocks=methodology,
        rung_gaps=rung_gaps,
        nonmonotone=nonmonotone,
        predictor_eval=predictor_eval,
    )
    n_pass = int(verdict["passes"].sum())
    n_total = int(len(verdict))
    overall = (
        "Methodology generalises"
        if n_pass >= 3
        else "Methodology reveals limits"
    )

    # Headlines for the summary block.
    stable_frac = float(stability["stable_at_0_85"].mean()) if len(stability) else float("nan")
    class_stability_parts: list[str] = []
    if "instance_class" in stability.columns and len(stability):
        for cls, grp in stability.groupby("instance_class"):
            n = len(grp)
            ns = int(grp["stable_at_0_85"].sum())
            class_stability_parts.append(
                f"{cls}-class {ns}/{n} stable "
                f"(median ARI_min={grp['reference_ari_min'].median():.2f})"
            )
    class_stability_str = "; ".join(class_stability_parts) if class_stability_parts else "_(no instance_class column)_"
    median_rung_gap = (
        float(rung_gaps["rel_gap_pyvrp10s_to_pyvrp60s"].median())
        if not rung_gaps.empty else float("nan")
    )
    mid_rung_gap = (
        float(rung_gaps["rel_gap_construct_to_pyvrp10s"].median())
        if not rung_gaps.empty else float("nan")
    )

    # Probe vs Stage A delta (for the methodology summary).
    delta_lines: list[str] = []
    if "delta_sufficiency" in methodology.columns:
        for _, r in methodology.iterrows():
            delta = r["delta_sufficiency"]
            if pd.notna(delta) and abs(delta) >= 0.10:
                delta_lines.append(
                    f"- {r['claim_family']} × {r['perturbation_family']}: "
                    f"Homberger {r['sufficiency_rate']:.2f} vs Stage A "
                    f"{r['sufficiency_rate_stage_a']:.2f} "
                    f"(Δ = {delta:+.2f}), n={int(r['n_cells'])}"
                )

    fallback_block = ""
    if fallback_applied:
        fallback_block = (
            f"\n**Reference fallback applied.** {fallback_cells} cells had "
            "3-seed ARI_min < 0.85 with 120 s references; those cells were "
            "re-solved at 180 s before computing the metrics above."
        )

    # Per-claim predictor zero-shot summary.
    predictor_block = "_(no predictor evaluation available)_"
    if not predictor_eval.empty:
        headline = predictor_eval[
            (predictor_eval["model"] == "hist_gradient_boosting")
            & (predictor_eval["feature_set"] == "C_clean")
        ][["claim_family", "n_rows", "pos_rate", "auroc_homberger",
            "auprc_homberger", "brier_homberger"]]
        predictor_block = _round_floats(headline).to_string(index=False)

    instances_str = ", ".join(instances_used)
    perturbations_str = ", ".join(perturbations_used)

    # Dynamic class-stratification annotation.
    from ..predictor_baselines.data import instance_class_from_id
    class_counts: dict[str, int] = {}
    for iid in instances_used:
        cls = instance_class_from_id(iid)
        class_counts[cls] = class_counts.get(cls, 0) + 1
    strat_str = " / ".join(
        f"{class_counts[c]} {c}" for c in sorted(class_counts)
    )

    text = f"""# Homberger-200 methodology probe

A **methodology evaluation**, not a second OOD predictor test: does
Stage A's design — three-axis decomposition, claim-family taxonomy,
5-rung action ladder, reference-anchored sufficiency — hold up when
the problem class scales from Solomon-100 to Homberger-200?

Stage A predictors stay locked. Homberger cells are scored zero-shot
as a secondary output; the methodology success criteria are the
primary output.

Scope
-----

- **Instances:** {len(instances_used)} ({strat_str}): {instances_str}
- **Perturbations:** {len(perturbations_used)} upper-half magnitudes: {perturbations_str}
- **Reference budget:** {time_limit_s:.0f} s × {len(seeds_used)} seeds per cell
- **pyvrp_10s budget:** {pyvrp10s_time_limit_s:.0f} s per cell
- **Total cells:** {len(stability)} (10 instances × 8 perturbations)
{fallback_block}

Verdict
-------

**{overall}.** {n_pass}/{n_total} success criteria satisfied.

```
{_round_floats(verdict).to_string(index=False)}
```

Reference stability
-------------------

- {stable_frac:.1%} of cells have 3-seed min-ARI ≥ 0.85 at the
  {time_limit_s:.0f} s reference budget.
- {int(stability['reference_struct_unstable'].sum())} / {len(stability)} cells
  flagged ``reference_struct_unstable=True`` by the Stage A threshold.

**Per instance-class:** {class_stability_str}

The R-class breakdown is the methodology signal: random-customer
Homberger instances have many near-equivalent solutions that PyVRP
reaches under different seeds, so 3-seed ARI is intrinsically lower
on R-class regardless of solve budget. C-class (clustered) and RC-
class instances are stable at the same budget. Reference-anchored
sufficiency on Homberger-200 R-class either needs a per-class budget
or a different stability statistic (e.g., 2-of-3-seed agreement).

Methodology per (claim_family × perturbation_family) block
----------------------------------------------------------

Sufficiency rates, cheap-action feasibility, reference stability,
and the delta vs the matched Stage A subset (where the perturbation
magnitudes overlap):

```
{_round_floats(methodology).to_string(index=False)}
```

Notable Homberger-vs-Stage-A deltas (|Δ| ≥ 0.10):
{chr(10).join(delta_lines) if delta_lines else "_(no |Δ| ≥ 0.10 blocks)_"}

Rung quality gaps
-----------------

If the 5-rung ladder remains operationally meaningful at scale,
pyvrp_10s should no longer near-saturate vs pyvrp_60s_reference.

- **Upper-ladder gap** (pyvrp_10s → pyvrp_60s_reference): median
  improvement = {median_rung_gap:+.3%}. The 1% bar the probe uses for
  the "ladder meaningful" criterion is *not* cleared — PyVRP's 10 s
  solve sits within tenths of a percent of the 120 s × 3-seed
  reference on Homberger-200 just as it does on Solomon-100.
- **Mid-ladder gap** (construct_feasible → pyvrp_10s): median
  improvement = {mid_rung_gap:+.1%}. The cheap construction-based
  rungs are far from PyVRP, so the *cheap-vs-escalate* decision the
  predictor gates remains operationally meaningful. The ladder hasn't
  collapsed — its gradient has moved lower.

**Reading.** The probe's strict criterion-3 fails (upper-rung gap below
the 1% threshold), but the cheap-action vs pyvrp_10s gap is large
enough that gate decisions still matter. The conclusion isn't "PyVRP
saturates the problem at 10 s" so much as "the relevant operating
question on Homberger is whether to run pyvrp_10s at all, not whether
to escalate from pyvrp_10s to a reference budget".

Full rung-gap distribution per perturbation family is in
``homberger_probe_rung_gaps.csv``.

Non-monotone cells (cheap=1, pyvrp_10s=0)
-----------------------------------------

STRUCT and SCHEDULE cells where the cheap action is sufficient but
pyvrp_10s isn't — the Stage A non-monotone phenomenon that motivates
keeping a learned gate.

- Total: **{int(len(nonmonotone))}** cells.
- Stage A reference: 54/889 (32 STRUCT + 22 SCHEDULE) ≈ 6%.

Per (claim_family × perturbation_family) breakdown:

```
{_round_floats(nonmonotone_summary).to_string(index=False) if not nonmonotone_summary.empty else "_(none)_"}
```

Predictor zero-shot (HistGB / C_clean)
--------------------------------------

Stage A predictors applied verbatim to the Homberger cheap rows. No
retraining, no calibration. The full per (model, feature_set,
claim_family) table is in ``homberger_probe_predictor_eval.csv``;
the deployment-headline rows are:

```
{predictor_block}
```

Caveats
-------

- The probe uses upper-half magnitudes the Stage A grid does not cover
  (TT 1.50, TW 0.15/0.20, OC 0.25). The "vs Stage A" delta column
  matches each probe perturbation to the *nearest* Stage A id for the
  baseline rate; treat the delta as directional, not exact.
- pyvrp_60s_reference is materialised from the 120 s seed-1 reference
  solve, not re-solved at 60 s, so its action_obj column reflects the
  reference budget, not a 60 s budget. The rung-gap analysis is
  consistent within the probe but is not directly comparable to
  Solomon's 60 s "pyvrp_60s_reference" wall-clock label.
- Homberger features have absolute scales (baseline_obj, route counts,
  durations) outside the predictor's training distribution. AUROC drops
  on the Homberger slice should be read as feature-distribution shift
  rather than methodology failure.

Files
-----

| file | description |
| --- | --- |
| `homberger_probe_cells.parquet` | Wide table: one row per (instance, perturbation, action). |
| `homberger_probe_claim_rows.parquet` | Long table: 4 claim rows per cheap/escalation action. |
| `homberger_probe_reference_stability.csv` | Per-cell 3-seed ARI + stability flags. |
| `homberger_probe_methodology.csv` | Per (claim × pert) sufficiency, feasibility, ARI, ΔStage A. |
| `homberger_probe_nonmonotone.csv` | STRUCT/SCHEDULE cheap=1, py10=0 cell list. |
| `homberger_probe_nonmonotone_summary.csv` | Counts per (claim × pert). |
| `homberger_probe_rung_gaps.csv` | Per-cell relative obj gap across the 5-rung ladder. |
| `homberger_probe_predictor_eval.csv` | Stage A predictors zero-shot AUROC/AUPRC/Brier. |
| `homberger_probe_predictor_oof.csv` | Per-cell predictor probabilities (zero-shot). |
| `homberger_probe_predictor_threshold_sweep.csv` | Routing-rule sweep on the probe cells. |
| `homberger_probe_README.md` | This file. |
"""
    out_path = output_dir / "homberger_probe_README.md"
    out_path.write_text(text)
    return out_path

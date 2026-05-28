# Pre-lock data grounding report

Source: 315 Phase-3 reuse-direct cells (15 × 7 × 3) plus 15 nominal PyVRP-60s seed=1 baselines from `reports/phase1/solutions.jsonl`. No solvers were re-run. Sufficiency labels were recomputed from stored errors using the prereg cuts (OBJ: loss ≤ 0.05 ∧ feasible; STRUCT: (1−ARI)/2 ≤ 0.05 ⇔ ARI ≥ 0.90; RANK: 1−top3-overlap ≤ 0.50). Phase-3's `difficulty_label` uses different STRUCT/RANK cuts (ARI > 0.75; overlap ≥ 0.67); this analysis ignores it.

## A. Slack profile

PyVRP packs at least one route to capacity on all 15 instances: `min_slack = 0` everywhere except X-n134-k13 (`min_slack_ratio = 0.0016`). Median `min_slack_ratio = 0.000`; **15/15 below 0.02 and 15/15 below 0.05**. `p10_slack` is also zero on 11/15 instances (≤ 1.0 on the rest). See `prereg/data/slack_profile.csv`, `prereg/figures/slack_distribution.png`.

**Interpretation.** The proposed `slack_anchor = max(p10_slack, 0.02·capacity)` collapses to the floor on every instance — `p10_slack` never wins. The 0.02 floor is the *operative* anchor, not a safety net. Recommend keeping floor = 0.02 and noting in the prereg that the anchor is *capacity-relative* on this grid; raising it to 0.05 would force CAP_1 into clearly-infeasible territory before α has room to spread (see §B).

## B. CAP feasibility breakpoint

Sweeping α ∈ [0, 5] in 0.1 steps with `new_capacity = cap·(1 − α·min_slack_ratio)`:

- **Literal formula.** Because `min_slack_ratio ≈ 0`, `new_capacity ≈ cap` for all α; 14/15 never break, X-n134-k13 alone breaks at α = 1.1. Buckets: [0,0.5]=0, (0.5,1.0]=0, (1.0,1.5]=1, (1.5,∞)=14.
- **Floored anchor** (msr ← max(p10, 0.02·cap)/cap): all 15 break at α = 0.1 — the smallest non-zero step. The proposed grid {0.5, 1.0, 1.5, 2.5} produces median overload counts {14, 18, 19, 20}, i.e. every level is "clearly infeasible". Buckets: [0,0.5]=15.

CSVs: `feasibility_breakpoint.csv`, `feasibility_breakpoint_anchor.csv`. Figure: `breakpoint_distribution.png`.

**Interpretation.** Neither parameterisation produces the intended spread (CAP_1 safe → CAP_4 infeasible). The literal formula is degenerate; the floored version is over-tight because even 1 % cap reduction overloads many routes when 11/15 instances pack p10 to capacity. **Recommendation: drop the slack-relative α grid.** The existing magnitudes (cap × {0.98, 0.95, 0.90, 0.80}) are direct fractional cuts and produce a workable spread (see §C). If a unitless α is needed, define `α = 1 − cap_new/cap_old` and use {0.02, 0.05, 0.10, 0.20}.

## C. Label distribution

`P(operational_sufficiency = 1)` per (claim, perturbation_family); n = number of cells:

| claim  | capacity_reduction | regional_distance_inflation |
|--------|--------------------|-----------------------------|
| OBJ    | P=0.12, n=60       | **P=0.98, n=45**            |
| STRUCT | P=0.12, n=60       | P=0.20, n=45                |
| RANK   | P=0.12, n=60       | P=0.29, n=45                |

CSV: `label_distribution.csv`. Figure: `label_distribution.png`.

**Interpretation.** One block fails the [0.10, 0.90] band: **OBJ × regional_distance_inflation = 0.98 (too positive)** — regdist barely moves the objective, so reuse_direct trivially wins. The redesigned regdist grid must push harder on objective: tighter region or higher multiplier (≥ 2.0). The two CAP × {STRUCT, RANK} blocks at 0.12 sit near the lower edge but inside the band; no action required.

## D. Predictability sanity check

Leave-one-instance-out logistic regression predicting `operational_sufficiency` over the 315 cells; bootstrap 95 % CIs over 15 fold-level AUROCs (2000 resamples). All folds had both classes.

| Model | features | mean AUROC | 95 % CI |
|------:|---|---:|---|
| 1 | claim_family (one-hot) | 0.754 | (0.675, 0.821) |
| 2 | claim + perturbation_family + magnitude (z within family) | 0.878 | (0.779, 0.956) |

Gap (Model 2 − Model 1) = **+0.124**.

**Interpretation.** Model 1 is below the 0.85 "too easy" threshold, so claim family alone does not saturate the task. Model 2 sits below 0.95, leaving room above. The +0.124 gap is well above the 0.05 "no signal" floor — magnitude carries real signal beyond claim family. **H1's expected AUROC +0.05 over a rule baseline is realistic** (already exceeded 2.5× in this pilot). The §C regdist redesign will lower the OBJ baseline rate from 0.98, which if anything tightens the gap and makes the +0.05 target more conservative. No revision to H1 needed.

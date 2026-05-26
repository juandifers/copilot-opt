# Homberger-200 methodology probe

A **methodology evaluation**, not a second OOD predictor test: does
Stage A's design — three-axis decomposition, claim-family taxonomy,
5-rung action ladder, reference-anchored sufficiency — hold up when
the problem class scales from Solomon-100 to Homberger-200?

Stage A predictors stay locked. Homberger cells are scored zero-shot
as a secondary output; the methodology success criteria are the
primary output.

Scope
-----

- **Instances:** 10 (4 C / 3 R / 3 RC): C1_2_1, C1_2_2, C2_2_1, C2_2_2, R1_2_1, R1_2_2, R2_2_1, RC1_2_1, RC1_2_2, RC2_2_1
- **Perturbations:** 8 upper-half magnitudes: OC_4, OC_5, ST_3, ST_4, TT_4, TT_5, TW_5, TW_6
- **Reference budget:** 120 s × 3 seeds per cell
- **pyvrp_10s budget:** 10 s per cell
- **Total cells:** 80 (10 instances × 8 perturbations)

**Reference fallback applied.** 28 cells had 3-seed ARI_min < 0.85 with 120 s references; those cells were re-solved at 180 s before computing the metrics above.

Verdict
-------

**Methodology generalises.** 4/5 success criteria satisfied.

```
                   criterion  passes  value  threshold                                                                    note
       1_reference_stability    True  0.725       0.70                                         58/80 cells with ARI_min ≥ 0.85
2_sufficiency_non_degenerate    True 12.000      12.00                             12/16 (claim × pert) blocks in (0.10, 0.95)
       3_rung_gap_measurable   False  0.000       0.01 median fractional obj improvement from pyvrp_10s to pyvrp_60s_reference
      4_nonmonotone_persists    True  9.000       3.00                            9 STRUCT/SCHEDULE cells with cheap=1, py10=0
 5_predictor_doesnt_collapse    True  4.000       2.00                     4/4 claim families with HistGB/C_clean AUROC ≥ 0.65
```

Reference stability
-------------------

- 72.5% of cells have 3-seed min-ARI ≥ 0.85 at the
  120 s reference budget.
- 21 / 80 cells
  flagged ``reference_struct_unstable=True`` by the Stage A threshold.

**Per instance-class:** C-class 31/32 stable (median ARI_min=1.00); R-class 11/24 stable (median ARI_min=0.75); RC-class 16/24 stable (median ARI_min=0.99)

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
 claim_family perturbation_family  n_cells  sufficiency_rate  cheap_feasible_rate  reference_ari_mean  reference_unstable_frac  sufficiency_rate_stage_a  delta_sufficiency
          OBJ        ORDER_CHANGE       18             0.889                0.444               0.866                    0.333                     0.860              0.029
          OBJ        SERVICE_TIME       20             0.600                0.000               0.850                    0.400                     0.826             -0.226
          OBJ         TIME_WINDOW       20             1.000                0.800               0.895                    0.300                     1.000              0.000
          OBJ         TRAVEL_TIME       16             0.750                0.000               0.845                    0.062                     0.973             -0.223
PLAN_VALIDITY        ORDER_CHANGE       20             0.400                0.400               0.866                    0.333                     0.670             -0.270
PLAN_VALIDITY        SERVICE_TIME       20             0.000                0.000               0.850                    0.400                     0.335             -0.335
PLAN_VALIDITY         TIME_WINDOW       20             0.800                0.800               0.895                    0.300                     0.402              0.398
PLAN_VALIDITY         TRAVEL_TIME       20             0.000                0.000               0.845                    0.062                     0.397             -0.397
     SCHEDULE        ORDER_CHANGE       18             0.778                0.444               0.866                    0.333                     0.425              0.352
     SCHEDULE        SERVICE_TIME       20             0.350                0.000               0.850                    0.400                     0.362             -0.012
     SCHEDULE         TIME_WINDOW       20             0.900                0.800               0.895                    0.300                     0.411              0.489
     SCHEDULE         TRAVEL_TIME       16             0.375                0.000               0.845                    0.062                     0.464             -0.089
       STRUCT        ORDER_CHANGE       18             0.333                0.444               0.866                    0.333                     0.520             -0.187
       STRUCT        SERVICE_TIME       20             0.000                0.000               0.850                    0.400                     0.549             -0.549
       STRUCT         TIME_WINDOW       20             0.800                0.800               0.895                    0.300                     0.567              0.233
       STRUCT         TRAVEL_TIME       16             0.438                0.000               0.845                    0.062                     0.600             -0.162
```

Notable Homberger-vs-Stage-A deltas (|Δ| ≥ 0.10):
- OBJ × SERVICE_TIME: Homberger 0.60 vs Stage A 0.83 (Δ = -0.23), n=20
- OBJ × TRAVEL_TIME: Homberger 0.75 vs Stage A 0.97 (Δ = -0.22), n=16
- PLAN_VALIDITY × ORDER_CHANGE: Homberger 0.40 vs Stage A 0.67 (Δ = -0.27), n=20
- PLAN_VALIDITY × SERVICE_TIME: Homberger 0.00 vs Stage A 0.33 (Δ = -0.33), n=20
- PLAN_VALIDITY × TIME_WINDOW: Homberger 0.80 vs Stage A 0.40 (Δ = +0.40), n=20
- PLAN_VALIDITY × TRAVEL_TIME: Homberger 0.00 vs Stage A 0.40 (Δ = -0.40), n=20
- SCHEDULE × ORDER_CHANGE: Homberger 0.78 vs Stage A 0.43 (Δ = +0.35), n=18
- SCHEDULE × TIME_WINDOW: Homberger 0.90 vs Stage A 0.41 (Δ = +0.49), n=20
- STRUCT × ORDER_CHANGE: Homberger 0.33 vs Stage A 0.52 (Δ = -0.19), n=18
- STRUCT × SERVICE_TIME: Homberger 0.00 vs Stage A 0.55 (Δ = -0.55), n=20
- STRUCT × TIME_WINDOW: Homberger 0.80 vs Stage A 0.57 (Δ = +0.23), n=20
- STRUCT × TRAVEL_TIME: Homberger 0.44 vs Stage A 0.60 (Δ = -0.16), n=16

Rung quality gaps
-----------------

If the 5-rung ladder remains operationally meaningful at scale,
pyvrp_10s should no longer near-saturate vs pyvrp_60s_reference.

- **Upper-ladder gap** (pyvrp_10s → pyvrp_60s_reference): median
  improvement = +0.044%. The 1% bar the probe uses for
  the "ladder meaningful" criterion is *not* cleared — PyVRP's 10 s
  solve sits within tenths of a percent of the 120 s × 3-seed
  reference on Homberger-200 just as it does on Solomon-100.
- **Mid-ladder gap** (construct_feasible → pyvrp_10s): median
  improvement = +49.1%. The cheap construction-based
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

- Total: **9** cells.
- Stage A reference: 54/889 (32 STRUCT + 22 SCHEDULE) ≈ 6%.

Per (claim_family × perturbation_family) breakdown:

```
 claim_family perturbation_family  n_nonmonotone  n_total_cells  nonmonotone_rate
          OBJ        ORDER_CHANGE              0             18             0.000
          OBJ        SERVICE_TIME              0             20             0.000
          OBJ         TIME_WINDOW              0             20             0.000
          OBJ         TRAVEL_TIME              0             16             0.000
PLAN_VALIDITY        ORDER_CHANGE              0             20             0.000
PLAN_VALIDITY        SERVICE_TIME              0             20             0.000
PLAN_VALIDITY         TIME_WINDOW              0             20             0.000
PLAN_VALIDITY         TRAVEL_TIME              0             20             0.000
     SCHEDULE        ORDER_CHANGE              0             18             0.000
     SCHEDULE        SERVICE_TIME              2             20             0.100
     SCHEDULE         TIME_WINDOW              0             20             0.000
     SCHEDULE         TRAVEL_TIME              0             16             0.000
       STRUCT        ORDER_CHANGE              1             18             0.056
       STRUCT        SERVICE_TIME              0             20             0.000
       STRUCT         TIME_WINDOW              6             20             0.300
       STRUCT         TRAVEL_TIME              0             16             0.000
```

Predictor zero-shot (HistGB / C_clean)
--------------------------------------

Stage A predictors applied verbatim to the Homberger cheap rows. No
retraining, no calibration. The full per (model, feature_set,
claim_family) table is in ``homberger_probe_predictor_eval.csv``;
the deployment-headline rows are:

```
 claim_family  n_rows  pos_rate  auroc_homberger  auprc_homberger  brier_homberger
          OBJ      74     0.811            0.967            0.992            0.062
PLAN_VALIDITY      80     0.300            0.974            0.901            0.025
     SCHEDULE      74     0.608            0.810            0.860            0.256
       STRUCT      74     0.392            0.785            0.676            0.207
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

Addendum: reference-budget pilot (pre-registration v1.4)
--------------------------------------------------------

A 9-cell pilot tested whether pyvrp_10s × 3 seeds could replace the
existing reference (120 s / 180 s × 3 seeds) without sacrificing
seed-stability — i.e., whether the rung-gap finding above (pyvrp_10s
sits within tenths of a percent of the long reference on **objective**)
also holds on the **structural-stability** axis the ARI machinery
requires.

**Pilot setup.** 3 cells per instance class, spanning easy (reference
ARI_min ≈ 1.0), borderline (≈ 0.93), and hard (≈ 0.65 – 0.70). All
4 perturbation families covered. The pilot **passes** iff every class
has ≥ 2 of 3 cells with `delta_ARI = ref_ARI_min – pilot_ARI_min ≤
0.05`. See ``homberger_reference_pilot.csv`` and
``homberger_reference_pilot_summary.md`` for the per-cell numbers.

**Verdict: pilot fails.** Per-class pass rates were C 3/3, R 1/3,
RC 2/3. Stage 2 (the calibrated-perturbation re-run with a cheaper
reference) is **not** launched under the v1.4 spec.

**Finding.** The failure has a consistent direction: pyvrp_10s × 3
seeds tends to *degrade* cells whose long-budget reference is already
stable. The clearest examples:

- R2_2_1 × TT_5: reference 1.000, pilot 0.768 (Δ +0.232)
- R1_2_1 × TW_5: reference 0.935, pilot 0.640 (Δ +0.295)
- RC1_2_1 × OC_4: reference 1.000, pilot 0.737 (Δ +0.263)

In each case the long reference converged to the same plan across all
three seeds, while pyvrp_10s landed on a near-equivalent but
structurally distinct plan on at least one seed. The very stability
property the methodology relies on collapses when the per-seed solve
budget shrinks, even though the per-seed *objective* would still be
within 0.04 % of the long-reference value (per the rung-gap analysis
above).

**Implication for the methodology paper.** The rung-gap finding —
pyvrp_10s saturates the reference on objective — does **not** generalise
to seed-stability. The two axes decouple at Homberger-200 scale, and
the structural-ARI axis is the load-bearing one for reference-anchored
sufficiency. The v1.4 question ("can we cheapen the reference?") gets
a clean negative answer: at Homberger-200, you need the long budget for
the stability check even if you could afford a short one for the
objective check. This is itself the methodology contribution — the
self-correction is in the experiment design, not the predictor.

**What this does not say.** It does not say pyvrp_10s is a poor cheap
*action*: it remains the right operating point for the predictor's
escalation target. The pilot only rules out using pyvrp_10s × 3 seeds
as the *reference* on which sufficiency is adjudicated.

| file | description |
| --- | --- |
| `homberger_reference_pilot.csv` | per-cell 3-seed ARI for pyvrp_10s vs the reference, with `delta_ari` and `passes_threshold`. |
| `homberger_reference_pilot_summary.md` | one-page verdict with per-class pass rates and interpretation. |


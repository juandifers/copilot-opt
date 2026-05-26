# VRPTW copilot baseline policy suite

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
  Evaluated under 5-fold grouped-by-instance CV across the threshold
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

Cheap-action subset row counts:
 claim_family  n_rows  n_non_nan  n_nan  sum_label
          OBJ     896        889      7      813.0
PLAN_VALIDITY     896        896      0      404.0
     SCHEDULE     896        889      7      369.0
       STRUCT     896        889      7      497.0

Unique cell × claim_family rows: 3584 (all == 1).
  TRAVEL_TIME    cheap = reuse_direct ✓
  TIME_WINDOW    cheap = reuse_direct ✓
  SERVICE_TIME   cheap = reuse_direct ✓
  ORDER_CHANGE   cheap = local_repair_insert ✓

No reference rows in the cheap-action subset.


Degenerate (claim, pert) blocks
-------------------------------

These are the buckets where the in-sample cheap-sufficiency rate is at
or beyond the extremes (≤ 0.05 or ≥ 0.95). They pre-determine the
block-rule policy's decision regardless of threshold within the grid
— flagged here so the report can call out where the categorical baseline
is *too easy* to beat:

  OBJ            × TIME_WINDOW   rate = 1.000  (degenerate — pre-determined decision)
  OBJ            × TRAVEL_TIME   rate = 0.973  (degenerate — pre-determined decision)

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
                      policy evaluation_mode threshold    fold   escalation_action  n_rows  accepted_coverage  accepted_precision  false_accept_rate  lost_correct_rate  escalation_rate  final_correctness  average_compute_cost_s
                  cheap_only       gate_only      None    None                        3563              1.000               0.585              0.415              0.000            0.000              0.585                     NaN
                  cheap_only    full_routing      None    None                        3563              1.000               0.585              0.415              0.000            0.000              0.585                   0.070
            always_pyvrp_10s       gate_only      None    None           pyvrp_10s    3563              0.000                 NaN                NaN              1.000            1.000                NaN                     NaN
            always_pyvrp_10s    full_routing      None    None           pyvrp_10s    3563              0.000                 NaN                NaN              1.000            1.000              0.940                  10.007
            always_reference       gate_only      None    None pyvrp_60s_reference    3563              0.000                 NaN                NaN              1.000            1.000                NaN                     NaN
            always_reference    full_routing      None    None pyvrp_60s_reference    3563              0.000                 NaN                NaN              1.000            1.000              0.998                  60.007
       feasibility_only_gate       gate_only      None    None           pyvrp_10s    3563              0.454               0.847              0.153              0.343            0.546              0.847                     NaN
       feasibility_only_gate    full_routing      None    None           pyvrp_10s    3563              0.454               0.847              0.153              0.343            0.546              0.895                   5.538
    oracle_cheap_sufficiency       gate_only      None    None           pyvrp_10s    3563              0.585               1.000              0.000              0.000            0.415              1.000                     NaN
    oracle_cheap_sufficiency    full_routing      None    None           pyvrp_10s    3563              0.585               1.000              0.000              0.000            0.415              0.955                   4.226
           block_rule_policy    full_routing       0.5 cv_mean           pyvrp_10s    3563              0.551               0.731              0.269              0.311            0.449              0.824                   4.564
           block_rule_policy    full_routing       0.6 cv_mean           pyvrp_10s    3563              0.351               0.833              0.167              0.500            0.649              0.885                   6.563
           block_rule_policy    full_routing       0.7 cv_mean           pyvrp_10s    3563              0.264               0.895              0.105              0.596            0.736              0.912                   7.434
           block_rule_policy    full_routing       0.8 cv_mean           pyvrp_10s    3563              0.250               0.915              0.085              0.610            0.750              0.919                   7.580
           block_rule_policy    full_routing       0.9 cv_mean           pyvrp_10s    3563              0.125               0.986              0.014              0.790            0.875              0.938                   8.830
           block_rule_policy    full_routing      0.95 cv_mean           pyvrp_10s    3563              0.125               0.986              0.014              0.790            0.875              0.938                   8.830
           block_rule_policy       gate_only       0.5 cv_mean           pyvrp_10s    3563              0.551               0.731              0.269              0.311            0.449              0.731                     NaN
           block_rule_policy       gate_only       0.6 cv_mean           pyvrp_10s    3563              0.351               0.833              0.167              0.500            0.649              0.833                     NaN
           block_rule_policy       gate_only       0.7 cv_mean           pyvrp_10s    3563              0.264               0.895              0.105              0.596            0.736              0.895                     NaN
           block_rule_policy       gate_only       0.8 cv_mean           pyvrp_10s    3563              0.250               0.915              0.085              0.610            0.750              0.915                     NaN
           block_rule_policy       gate_only       0.9 cv_mean           pyvrp_10s    3563              0.125               0.986              0.014              0.790            0.875              0.986                     NaN
           block_rule_policy       gate_only      0.95 cv_mean           pyvrp_10s    3563              0.125               0.986              0.014              0.790            0.875              0.986                     NaN
perturbation_family_majority    full_routing       NaN cv_mean           pyvrp_10s    3563              0.551               0.731              0.269              0.311            0.449              0.824                   4.564
perturbation_family_majority       gate_only       NaN cv_mean           pyvrp_10s    3563              0.551               0.731              0.269              0.311            0.449              0.731                     NaN
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

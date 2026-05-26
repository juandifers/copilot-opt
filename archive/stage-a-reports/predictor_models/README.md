# VRPTW copilot — learned cheap-sufficiency predictors (Stage A, Run 2)

Run 2 amends Run 1 with four fixes:

1. **Per-claim Set C** (``C_clean``) drops the columns that
   definitionally encode each family's label. For PV: drops
   ``action_feasible``, ``infeasibility_kind``, ``action_n_late_customers``,
   ``action_max_lateness``. For SCHEDULE: drops the two lateness columns.
   OBJ and STRUCT retain full Set C. The unified Set C is retained as
   ``C_leaky`` for the ablation table only.
2. **Pareto-best selection** replaces "highest correctness" as the
   headline rule.
3. **``block_rule_extended``** (a 4-key categorical baseline matching
   Set A's bucket granularity) is the fair categorical baseline.
4. **Platt (sigmoid) calibration** replaces isotonic.

Routing rule:

    accept_cheap if  P(cheap_sufficient | features, claim_family) >= threshold
    else escalate to pyvrp_10s

Fold layout is reused from `reports/predictor_baselines/fold_assignments.csv`.

Headline result
---------------

**Pareto-best at ≤7 s/cell:** hist_gradient_boosting / C_clean @ t=0.98 → final_correctness=0.937, average_compute_cost=6.33 s, coverage=0.375, precision=0.989.

Framing decision
----------------

**Outcome A (routing + verification).**  For SCHEDULE, C_clean beats B by ΔAUROC = +0.073 (C_clean=0.876, B=0.803). The thesis claims two contributions: routing models (OBJ, STRUCT, PLAN_VALIDITY) run before the cheap action via Set B; verification model (SCHEDULE) consumes cheap-action diagnostics via the remaining C_clean features.

Per-claim CV AUROC
------------------

```
                    model   feature_set   OBJ  PLAN_VALIDITY  STRUCT  SCHEDULE  non_degenerate_mean
            decision_tree A_categorical 0.958          0.820   0.833     0.731                0.782
            decision_tree   B_pre_cheap 0.934          0.848   0.828     0.712                0.770
            decision_tree       C_clean 0.930          0.998   0.812     0.849                0.830
            decision_tree       C_leaky 0.930          1.000   0.812     0.852                0.832
   hist_gradient_boosting A_categorical 0.960          0.845   0.849     0.754                0.801
   hist_gradient_boosting   B_pre_cheap 0.954          0.908   0.824     0.803                0.813
   hist_gradient_boosting       C_clean 0.978          0.999   0.851     0.876                0.864
   hist_gradient_boosting       C_leaky 0.978          1.000   0.851     0.877                0.864
      logistic_regression A_categorical 0.890          0.810   0.802     0.694                0.748
      logistic_regression   B_pre_cheap 0.913          0.853   0.789     0.750                0.769
      logistic_regression       C_clean 0.967          0.915   0.845     0.857                0.851
      logistic_regression       C_leaky 0.967          1.000   0.845     0.868                0.856
logistic_regression_platt A_categorical 0.878          0.809   0.794     0.686                0.740
logistic_regression_platt   B_pre_cheap 0.904          0.850   0.751     0.744                0.748
logistic_regression_platt       C_clean 0.963          0.902   0.842     0.856                0.849
logistic_regression_platt       C_leaky 0.963          1.000   0.842     0.864                0.853
```

Pareto frontier (top rows)
--------------------------

```
                    model   feature_set  threshold  n_rows  accepted_coverage  accepted_precision  false_accept_rate  lost_correct_rate  escalation_rate  final_correctness  average_compute_cost_s  p95_compute_cost_s  on_pareto_frontier
   hist_gradient_boosting A_categorical       0.95    3563              0.260               0.996              0.004              0.557            0.740              0.942                   7.473              10.439                True
logistic_regression_platt       C_leaky       0.95    3563              0.280               0.999              0.001              0.521            0.720              0.940                   7.274              10.437                True
   hist_gradient_boosting A_categorical       0.90    3563              0.287               0.986              0.014              0.516            0.713              0.939                   7.207              10.439                True
   hist_gradient_boosting       C_leaky       0.98    3563              0.378               0.993              0.007              0.358            0.622              0.939                   6.294              10.437                True
   hist_gradient_boosting       C_leaky       0.95    3563              0.420               0.983              0.017              0.295            0.580              0.938                   5.878              10.436                True
   hist_gradient_boosting       C_clean       0.95    3563              0.421               0.979              0.021              0.295            0.579              0.937                   5.867              10.436                True
   hist_gradient_boosting       C_leaky       0.90    3563              0.459               0.968              0.032              0.240            0.541              0.933                   5.479              10.436                True
   hist_gradient_boosting       C_leaky       0.80    3563              0.500               0.951              0.049              0.187            0.500              0.927                   5.078              10.431                True
   hist_gradient_boosting       C_clean       0.80    3563              0.501               0.948              0.052              0.187            0.499              0.926                   5.061              10.428                True
   hist_gradient_boosting       C_leaky       0.70    3563              0.530               0.936              0.064              0.152            0.470              0.922                   4.774              10.428                True
   hist_gradient_boosting       C_clean       0.70    3563              0.532               0.928              0.072              0.155            0.468              0.918                   4.749              10.427                True
   hist_gradient_boosting       C_leaky       0.60    3563              0.557               0.917              0.083              0.127            0.443              0.914                   4.507              10.420                True
   hist_gradient_boosting       C_leaky       0.50    3563              0.585               0.896              0.104              0.104            0.415              0.901                   4.224              10.414                True
   hist_gradient_boosting       C_clean       0.50    3563              0.585               0.895              0.105              0.104            0.415              0.901                   4.218              10.419                True
      logistic_regression       C_leaky       0.50    3563              0.590               0.896              0.104              0.096            0.410              0.900                   4.173              10.413                True
            decision_tree       C_leaky       0.60    3563              0.601               0.881              0.119              0.094            0.399              0.893                   4.058              10.415                True
            decision_tree       C_leaky       0.50    3563              0.612               0.877              0.123              0.082            0.388              0.890                   3.951              10.409                True
      block_rule_extended      baseline       0.95    3563              0.260               0.996              0.004              0.558            0.740              0.942                   7.479              10.439               False
      block_rule_extended      baseline       0.98    3563              0.260               0.996              0.004              0.558            0.740              0.942                   7.479              10.439               False
            decision_tree A_categorical       0.98    3563              0.240               1.000              0.000              0.589            0.760              0.942                   7.673              10.439               False
```

Bootstrap CIs (paired-cell, n=1000)
-----------------------------------

**Pairing rule.** Predictor side: the threshold that maximises
``final_correctness`` while keeping ``average_compute_cost_s`` ≤ 7
s/cell (the deployment ceiling reported above). Baseline side: the
*cheapest* threshold whose correctness is ≥ the predictor's
correctness — i.e., the baseline must match-or-beat correctness, and
the predictor's win is the compute saving. **Resample unit:** per-cell
decisions stratified by fold (paired-cluster bootstrap, n=1000); both
the predictor and the baseline arrays are indexed by the same sampled
rows in each resample so the Δ metrics are paired.

- **hist_gradient_boosting/C_clean vs block_rule_extended/baseline**: Δ correctness = -0.005 [-0.008, -0.002]; Δ compute = -1.15 s [-1.27, -1.03].
- **hist_gradient_boosting/B_pre_cheap vs block_rule_extended/baseline**: Δ correctness = -0.004 [-0.008, +0.001]; Δ compute = -0.49 s [-0.60, -0.38].
- **logistic_regression/C_clean vs block_rule_extended/baseline**: Δ correctness = -0.009 [-0.013, -0.004]; Δ compute = -0.38 s [-0.50, -0.27].

Set C ablation (PV + SCHEDULE: C_clean vs C_leaky)
--------------------------------------------------

```
                    model  claim_family  auroc_C_clean  auroc_C_leaky  delta_auroc  auprc_C_clean  auprc_C_leaky  brier_C_clean  brier_C_leaky  pos_rate
            decision_tree PLAN_VALIDITY          0.998          1.000        0.002          0.995          1.000          0.005          0.000     0.456
            decision_tree      SCHEDULE          0.849          0.852        0.004          0.782          0.786          0.162          0.160     0.418
   hist_gradient_boosting PLAN_VALIDITY          0.999          1.000        0.001          0.999          1.000          0.006          0.000     0.456
   hist_gradient_boosting      SCHEDULE          0.876          0.877        0.001          0.838          0.839          0.150          0.149     0.418
      logistic_regression PLAN_VALIDITY          0.915          1.000        0.085          0.882          1.000          0.117          0.000     0.456
      logistic_regression      SCHEDULE          0.857          0.868        0.011          0.827          0.833          0.149          0.146     0.418
logistic_regression_platt PLAN_VALIDITY          0.902          1.000        0.098          0.869          1.000          0.131          0.000     0.456
logistic_regression_platt      SCHEDULE          0.856          0.864        0.008          0.827          0.830          0.160          0.155     0.418
```

Deployment configuration
------------------------

For each claim family, the lowest-compute threshold that meets the
floor (or the highest-correctness threshold if no threshold meets it,
with ``floor_met=False``). PLAN_VALIDITY deploys on Set B
(``hist_gradient_boosting / B_pre_cheap``); OBJ, STRUCT, SCHEDULE
deploy on C_clean. Legacy PV × C_clean rows are kept with
``note=residual_leak_dropped_from_deployment`` for audit:

```
 claim_family  correctness_floor                  model feature_set  chosen_threshold  final_correctness  average_compute_cost_s  accepted_coverage  accepted_precision  false_accept_rate  floor_met                                  note
          OBJ               0.95 hist_gradient_boosting     C_clean              0.50              0.980                   0.914              0.916               0.978              0.022       True                     deployment_active
          OBJ               0.90 hist_gradient_boosting     C_clean              0.50              0.980                   0.914              0.916               0.978              0.022       True                     deployment_active
          OBJ               0.80 hist_gradient_boosting     C_clean              0.50              0.980                   0.914              0.916               0.978              0.022       True                     deployment_active
PLAN_VALIDITY               0.95 hist_gradient_boosting B_pre_cheap              0.80              0.962                   7.185              0.289               0.892              0.108       True                     deployment_active
PLAN_VALIDITY               0.95 hist_gradient_boosting     C_clean              0.50              0.988                   5.543              0.453               0.990              0.010       True residual_leak_dropped_from_deployment
PLAN_VALIDITY               0.90 hist_gradient_boosting B_pre_cheap              0.50              0.904                   5.532              0.454               0.801              0.199       True                     deployment_active
PLAN_VALIDITY               0.90 hist_gradient_boosting     C_clean              0.50              0.988                   5.543              0.453               0.990              0.010       True residual_leak_dropped_from_deployment
PLAN_VALIDITY               0.80 hist_gradient_boosting B_pre_cheap              0.50              0.904                   5.532              0.454               0.801              0.199       True                     deployment_active
PLAN_VALIDITY               0.80 hist_gradient_boosting     C_clean              0.50              0.988                   5.543              0.453               0.990              0.010       True residual_leak_dropped_from_deployment
       STRUCT               0.95 hist_gradient_boosting     C_clean              0.95              0.874                   7.713              0.236               0.943              0.057      False                     deployment_active
       STRUCT               0.90 hist_gradient_boosting     C_clean              0.95              0.874                   7.713              0.236               0.943              0.057      False                     deployment_active
       STRUCT               0.80 hist_gradient_boosting     C_clean              0.50              0.808                   4.358              0.571               0.787              0.213       True                     deployment_active
     SCHEDULE               0.95 hist_gradient_boosting     C_clean              0.98              0.892                   9.525              0.055               0.918              0.082      False                     deployment_active
     SCHEDULE               0.90 hist_gradient_boosting     C_clean              0.98              0.892                   9.525              0.055               0.918              0.082      False                     deployment_active
     SCHEDULE               0.80 hist_gradient_boosting     C_clean              0.50              0.828                   6.047              0.403               0.749              0.251       True                     deployment_active
```

**Deployment honesty.** The PV row at floor 0.95 used to read
``HistGB / C_clean @ t=0.5 → corr 0.988``, but that number rides on
the residual feasibility leak through continuous post-cheap features
(``action_time_warp``, ``action_obj_delta_pct``, …). The deployable
PV gate is HistGB / B_pre_cheap — see the legacy rows in
``deployment_config.csv`` for the comparison.

Non-monotone preservation (STRUCT / SCHEDULE)
---------------------------------------------

54 cells (32 STRUCT + 22 SCHEDULE) where the cheap action is
sufficient but ``pyvrp_10s`` is not. A "good" gate accepts a high
fraction — those are exactly the cells where escalating would hurt.

```
                    model   feature_set claim_family  threshold  n_cases  n_accepted  acceptance_rate
      block_rule_extended      baseline     SCHEDULE        0.7       22           5            0.227
      block_rule_extended      baseline       STRUCT        0.7       32           9            0.281
            decision_tree A_categorical     SCHEDULE        0.7       22           6            0.273
            decision_tree A_categorical       STRUCT        0.7       32           8            0.250
            decision_tree   B_pre_cheap     SCHEDULE        0.7       22           7            0.318
            decision_tree   B_pre_cheap       STRUCT        0.7       32          16            0.500
            decision_tree       C_clean     SCHEDULE        0.7       22          16            0.727
            decision_tree       C_clean       STRUCT        0.7       32          27            0.844
            decision_tree       C_leaky     SCHEDULE        0.7       22          16            0.727
            decision_tree       C_leaky       STRUCT        0.7       32          27            0.844
   hist_gradient_boosting A_categorical     SCHEDULE        0.7       22           6            0.273
   hist_gradient_boosting A_categorical       STRUCT        0.7       32           9            0.281
   hist_gradient_boosting   B_pre_cheap     SCHEDULE        0.7       22          11            0.500
   hist_gradient_boosting   B_pre_cheap       STRUCT        0.7       32          14            0.438
   hist_gradient_boosting       C_clean     SCHEDULE        0.7       22          13            0.591
   hist_gradient_boosting       C_clean       STRUCT        0.7       32          23            0.719
   hist_gradient_boosting       C_leaky     SCHEDULE        0.7       22          14            0.636
   hist_gradient_boosting       C_leaky       STRUCT        0.7       32          23            0.719
      logistic_regression A_categorical     SCHEDULE        0.7       22           1            0.045
      logistic_regression A_categorical       STRUCT        0.7       32          11            0.344
      logistic_regression   B_pre_cheap     SCHEDULE        0.7       22           5            0.227
      logistic_regression   B_pre_cheap       STRUCT        0.7       32          14            0.438
      logistic_regression       C_clean     SCHEDULE        0.7       22          11            0.500
      logistic_regression       C_clean       STRUCT        0.7       32          15            0.469
      logistic_regression       C_leaky     SCHEDULE        0.7       22          11            0.500
      logistic_regression       C_leaky       STRUCT        0.7       32          15            0.469
logistic_regression_platt A_categorical     SCHEDULE        0.7       22           0            0.000
logistic_regression_platt A_categorical       STRUCT        0.7       32           0            0.000
logistic_regression_platt   B_pre_cheap     SCHEDULE        0.7       22           0            0.000
logistic_regression_platt   B_pre_cheap       STRUCT        0.7       32           0            0.000
logistic_regression_platt       C_clean     SCHEDULE        0.7       22           5            0.227
logistic_regression_platt       C_clean       STRUCT        0.7       32           3            0.094
logistic_regression_platt       C_leaky     SCHEDULE        0.7       22           6            0.273
logistic_regression_platt       C_leaky       STRUCT        0.7       32           3            0.094
```

**Calibration verdict (Platt vs uncalibrated LR, non-monotone preservation at t=0.7):**
- logistic_regression / C_clean STRUCT: preserved 15/32
- logistic_regression_platt / C_clean STRUCT: preserved 3/32
- logistic_regression / C_clean SCHEDULE: preserved 11/22
- logistic_regression_platt / C_clean SCHEDULE: preserved 5/22

Platt preserves 8/54 of the non-monotone cells vs uncalibrated LR's 26/54. Both calibration methods (isotonic in Run 1, Platt in Run 2) degrade reference-anchored final correctness on this benchmark; uncalibrated LR is the deployable linear baseline. ``logistic_regression_platt`` rows are retained in the tables for transparency but excluded from the headline deployment recommendation.

**PV residual-leak check (C_clean drops `action_feasible`, `infeasibility_kind`, lateness columns):**
- decision_tree / C_clean × PLAN_VALIDITY AUROC = 0.998
- hist_gradient_boosting / C_clean × PLAN_VALIDITY AUROC = 0.999
- logistic_regression / C_clean × PLAN_VALIDITY AUROC = 0.915
- logistic_regression_platt / C_clean × PLAN_VALIDITY AUROC = 0.902

Nonlinear models (HistGB, DecisionTree) still reach AUROC ≈ 1.0 on PV × C_clean despite dropping the four definitional columns. Residual signal flows through continuous post-cheap features (``action_obj_delta_pct``, ``action_time_warp``, ``action_total_duration``, …) which are only well-defined when the cheap action is feasible. The linear LR (AUROC 0.915) shows the non-tautological signal level. For deployment, **PV should use Set B (pre-cheap) regardless of the framing decision** — its definitional ceiling makes C_clean a poor discriminator beyond "is the action feasible".

Escalation probe (zero-shot)
----------------------------

```
                    model   feature_set  claim_family  n_rows  pos_rate  auroc_probe  auprc_probe  brier_probe
      logistic_regression A_categorical           OBJ     156     0.949        0.805        0.988        0.049
      logistic_regression A_categorical PLAN_VALIDITY     160     0.306        0.804        0.630        0.161
      logistic_regression A_categorical        STRUCT     156     0.551        0.856        0.867        0.156
      logistic_regression A_categorical      SCHEDULE     156     0.391        0.788        0.711        0.187
      logistic_regression   B_pre_cheap           OBJ     156     0.949        0.860        0.992        0.047
      logistic_regression   B_pre_cheap PLAN_VALIDITY     160     0.306        0.873        0.750        0.150
      logistic_regression   B_pre_cheap        STRUCT     156     0.551        0.829        0.834        0.168
      logistic_regression   B_pre_cheap      SCHEDULE     156     0.391        0.812        0.743        0.177
      logistic_regression       C_clean           OBJ     156     0.949        0.970        0.998        0.025
      logistic_regression       C_clean PLAN_VALIDITY     160     0.306        0.950        0.894        0.097
      logistic_regression       C_clean        STRUCT     156     0.551        0.889        0.908        0.133
      logistic_regression       C_clean      SCHEDULE     156     0.391        0.922        0.893        0.099
      logistic_regression       C_leaky           OBJ     156     0.949        0.970        0.998        0.025
      logistic_regression       C_leaky PLAN_VALIDITY     160     0.306        1.000        1.000        0.000
      logistic_regression       C_leaky        STRUCT     156     0.551        0.889        0.908        0.133
      logistic_regression       C_leaky      SCHEDULE     156     0.391        0.931        0.902        0.098
logistic_regression_platt A_categorical           OBJ     156     0.949        0.774        0.985        0.048
logistic_regression_platt A_categorical PLAN_VALIDITY     160     0.306        0.804        0.630        0.178
logistic_regression_platt A_categorical        STRUCT     156     0.551        0.864        0.877        0.157
logistic_regression_platt A_categorical      SCHEDULE     156     0.391        0.794        0.700        0.197
logistic_regression_platt   B_pre_cheap           OBJ     156     0.949        0.829        0.990        0.045
logistic_regression_platt   B_pre_cheap PLAN_VALIDITY     160     0.306        0.852        0.721        0.160
logistic_regression_platt   B_pre_cheap        STRUCT     156     0.551        0.786        0.801        0.201
logistic_regression_platt   B_pre_cheap      SCHEDULE     156     0.391        0.808        0.748        0.194
logistic_regression_platt       C_clean           OBJ     156     0.949        0.943        0.997        0.032
logistic_regression_platt       C_clean PLAN_VALIDITY     160     0.306        0.919        0.837        0.119
logistic_regression_platt       C_clean        STRUCT     156     0.551        0.880        0.904        0.156
logistic_regression_platt       C_clean      SCHEDULE     156     0.391        0.922        0.901        0.121
logistic_regression_platt       C_leaky           OBJ     156     0.949        0.943        0.997        0.032
logistic_regression_platt       C_leaky PLAN_VALIDITY     160     0.306        1.000        1.000        0.000
logistic_regression_platt       C_leaky        STRUCT     156     0.551        0.880        0.904        0.156
logistic_regression_platt       C_leaky      SCHEDULE     156     0.391        0.930        0.906        0.116
   hist_gradient_boosting A_categorical           OBJ     156     0.949        0.738        0.978        0.042
   hist_gradient_boosting A_categorical PLAN_VALIDITY     160     0.306        0.848        0.656        0.150
   hist_gradient_boosting A_categorical        STRUCT     156     0.551        0.846        0.871        0.157
   hist_gradient_boosting A_categorical      SCHEDULE     156     0.391        0.811        0.721        0.179
   hist_gradient_boosting   B_pre_cheap           OBJ     156     0.949        0.806        0.986        0.033
   hist_gradient_boosting   B_pre_cheap PLAN_VALIDITY     160     0.306        0.932        0.821        0.122
   hist_gradient_boosting   B_pre_cheap        STRUCT     156     0.551        0.905        0.912        0.120
   hist_gradient_boosting   B_pre_cheap      SCHEDULE     156     0.391        0.903        0.826        0.133
   hist_gradient_boosting       C_clean           OBJ     156     0.949        0.973        0.998        0.024
   hist_gradient_boosting       C_clean PLAN_VALIDITY     160     0.306        1.000        1.000        0.000
   hist_gradient_boosting       C_clean        STRUCT     156     0.551        0.939        0.950        0.099
   hist_gradient_boosting       C_clean      SCHEDULE     156     0.391        0.962        0.956        0.070
   hist_gradient_boosting       C_leaky           OBJ     156     0.949        0.973        0.998        0.024
   hist_gradient_boosting       C_leaky PLAN_VALIDITY     160     0.306        1.000        1.000        0.000
   hist_gradient_boosting       C_leaky        STRUCT     156     0.551        0.939        0.950        0.099
   hist_gradient_boosting       C_leaky      SCHEDULE     156     0.391        0.960        0.957        0.068
            decision_tree A_categorical           OBJ     156     0.949        0.730        0.972        0.044
            decision_tree A_categorical PLAN_VALIDITY     160     0.306        0.829        0.659        0.152
            decision_tree A_categorical        STRUCT     156     0.551        0.837        0.830        0.153
            decision_tree A_categorical      SCHEDULE     156     0.391        0.798        0.673        0.186
            decision_tree   B_pre_cheap           OBJ     156     0.949        0.740        0.973        0.040
            decision_tree   B_pre_cheap PLAN_VALIDITY     160     0.306        0.893        0.786        0.147
            decision_tree   B_pre_cheap        STRUCT     156     0.551        0.866        0.856        0.149
            decision_tree   B_pre_cheap      SCHEDULE     156     0.391        0.797        0.674        0.181
            decision_tree       C_clean           OBJ     156     0.949        0.968        0.997        0.028
            decision_tree       C_clean PLAN_VALIDITY     160     0.306        1.000        1.000        0.000
            decision_tree       C_clean        STRUCT     156     0.551        0.899        0.901        0.130
            decision_tree       C_clean      SCHEDULE     156     0.391        0.916        0.853        0.107
            decision_tree       C_leaky           OBJ     156     0.949        0.968        0.997        0.028
            decision_tree       C_leaky PLAN_VALIDITY     160     0.306        1.000        1.000        0.000
            decision_tree       C_leaky        STRUCT     156     0.551        0.899        0.901        0.130
            decision_tree       C_leaky      SCHEDULE     156     0.391        0.936        0.902        0.087
```

- HistGB / C_clean: probe AUROC = 0.968; Stage A full CV mean = 0.926 (Δ = -0.042); Stage A TT/TW-slice CV mean = 0.942 (Δ = -0.026).

**Probe framing.** Probe AUROC exceeds the TT/TW-restricted Stage A CV AUROC (gap = -0.026). Even within the matched perturbation slice, the probe is easier — driving factors are the appendix-A magnitude grid (cleaner extremes) and the longer 120 s reference budget (more stable labels). **Reading: the probe is structurally cleaner than Stage A; treat the AUROC number as an upper bound on OOD performance**.

Stage A TT/TW subset (matched-perturbation reference)
-----------------------------------------------------

Restricting the Stage A OOF predictions to TIME_WINDOW and TRAVEL_TIME
cells only — the same perturbation families the escalation probe uses
— gives the apples-to-apples reference for the probe AUROC. Compare
this table's HistGB/C_clean numbers to the probe AUROC above:

```
                    model   feature_set  claim_family subset  n_rows  pos_rate  auroc  auprc  brier
      block_rule_extended      baseline           OBJ  TT_TW     444     0.986  0.898  0.997  0.011
      block_rule_extended      baseline PLAN_VALIDITY  TT_TW     448     0.400  0.799  0.714  0.177
      block_rule_extended      baseline      SCHEDULE  TT_TW     444     0.437  0.756  0.668  0.199
      block_rule_extended      baseline        STRUCT  TT_TW     444     0.583  0.879  0.920  0.138
            decision_tree A_categorical           OBJ  TT_TW     444     0.986  0.954  0.999  0.012
            decision_tree A_categorical PLAN_VALIDITY  TT_TW     448     0.400  0.741  0.657  0.190
            decision_tree A_categorical      SCHEDULE  TT_TW     444     0.437  0.729  0.647  0.204
            decision_tree A_categorical        STRUCT  TT_TW     444     0.583  0.863  0.908  0.138
            decision_tree   B_pre_cheap           OBJ  TT_TW     444     0.986  0.896  0.997  0.011
            decision_tree   B_pre_cheap PLAN_VALIDITY  TT_TW     448     0.400  0.865  0.787  0.151
            decision_tree   B_pre_cheap      SCHEDULE  TT_TW     444     0.437  0.744  0.689  0.209
            decision_tree   B_pre_cheap        STRUCT  TT_TW     444     0.583  0.877  0.911  0.141
            decision_tree       C_clean           OBJ  TT_TW     444     0.986  0.790  0.993  0.017
            decision_tree       C_clean PLAN_VALIDITY  TT_TW     448     0.400  1.000  1.000  0.000
            decision_tree       C_clean      SCHEDULE  TT_TW     444     0.437  0.896  0.842  0.127
            decision_tree       C_clean        STRUCT  TT_TW     444     0.583  0.849  0.890  0.155
            decision_tree       C_leaky           OBJ  TT_TW     444     0.986  0.790  0.993  0.017
            decision_tree       C_leaky PLAN_VALIDITY  TT_TW     448     0.400  1.000  1.000  0.000
            decision_tree       C_leaky      SCHEDULE  TT_TW     444     0.437  0.900  0.847  0.124
            decision_tree       C_leaky        STRUCT  TT_TW     444     0.583  0.849  0.890  0.155
   hist_gradient_boosting A_categorical           OBJ  TT_TW     444     0.986  0.976  1.000  0.011
   hist_gradient_boosting A_categorical PLAN_VALIDITY  TT_TW     448     0.400  0.795  0.704  0.176
   hist_gradient_boosting A_categorical      SCHEDULE  TT_TW     444     0.437  0.759  0.677  0.196
   hist_gradient_boosting A_categorical        STRUCT  TT_TW     444     0.583  0.878  0.922  0.137
   hist_gradient_boosting   B_pre_cheap           OBJ  TT_TW     444     0.986  0.994  1.000  0.009
   hist_gradient_boosting   B_pre_cheap PLAN_VALIDITY  TT_TW     448     0.400  0.920  0.883  0.116
   hist_gradient_boosting   B_pre_cheap      SCHEDULE  TT_TW     444     0.437  0.828  0.800  0.169
   hist_gradient_boosting   B_pre_cheap        STRUCT  TT_TW     444     0.583  0.854  0.904  0.161
   hist_gradient_boosting       C_clean           OBJ  TT_TW     444     0.986  0.984  1.000  0.008
   hist_gradient_boosting       C_clean PLAN_VALIDITY  TT_TW     448     0.400  1.000  1.000  0.000
   hist_gradient_boosting       C_clean      SCHEDULE  TT_TW     444     0.437  0.908  0.887  0.122
   hist_gradient_boosting       C_clean        STRUCT  TT_TW     444     0.583  0.878  0.918  0.148
   hist_gradient_boosting       C_leaky           OBJ  TT_TW     444     0.986  0.984  1.000  0.008
   hist_gradient_boosting       C_leaky PLAN_VALIDITY  TT_TW     448     0.400  1.000  1.000  0.000
   hist_gradient_boosting       C_leaky      SCHEDULE  TT_TW     444     0.437  0.909  0.886  0.122
   hist_gradient_boosting       C_leaky        STRUCT  TT_TW     444     0.583  0.878  0.918  0.148
      logistic_regression A_categorical           OBJ  TT_TW     444     0.986  0.675  0.995  0.015
      logistic_regression A_categorical PLAN_VALIDITY  TT_TW     448     0.400  0.728  0.627  0.196
      logistic_regression A_categorical      SCHEDULE  TT_TW     444     0.437  0.715  0.645  0.212
      logistic_regression A_categorical        STRUCT  TT_TW     444     0.583  0.853  0.898  0.153
      logistic_regression   B_pre_cheap           OBJ  TT_TW     444     0.986  0.734  0.996  0.015
      logistic_regression   B_pre_cheap PLAN_VALIDITY  TT_TW     448     0.400  0.825  0.755  0.164
      logistic_regression   B_pre_cheap      SCHEDULE  TT_TW     444     0.437  0.774  0.713  0.192
      logistic_regression   B_pre_cheap        STRUCT  TT_TW     444     0.583  0.823  0.846  0.163
      logistic_regression       C_clean           OBJ  TT_TW     444     0.986  0.941  0.999  0.012
      logistic_regression       C_clean PLAN_VALIDITY  TT_TW     448     0.400  0.891  0.827  0.134
      logistic_regression       C_clean      SCHEDULE  TT_TW     444     0.437  0.900  0.860  0.119
      logistic_regression       C_clean        STRUCT  TT_TW     444     0.583  0.890  0.922  0.134
      logistic_regression       C_leaky           OBJ  TT_TW     444     0.986  0.941  0.999  0.012
      logistic_regression       C_leaky PLAN_VALIDITY  TT_TW     448     0.400  1.000  1.000  0.000
      logistic_regression       C_leaky      SCHEDULE  TT_TW     444     0.437  0.904  0.864  0.118
      logistic_regression       C_leaky        STRUCT  TT_TW     444     0.583  0.890  0.922  0.134
logistic_regression_platt A_categorical           OBJ  TT_TW     444     0.986  0.569  0.992  0.015
logistic_regression_platt A_categorical PLAN_VALIDITY  TT_TW     448     0.400  0.731  0.628  0.203
logistic_regression_platt A_categorical      SCHEDULE  TT_TW     444     0.437  0.712  0.637  0.217
logistic_regression_platt A_categorical        STRUCT  TT_TW     444     0.583  0.865  0.911  0.159
logistic_regression_platt   B_pre_cheap           OBJ  TT_TW     444     0.986  0.656  0.994  0.017
logistic_regression_platt   B_pre_cheap PLAN_VALIDITY  TT_TW     448     0.400  0.811  0.728  0.170
logistic_regression_platt   B_pre_cheap      SCHEDULE  TT_TW     444     0.437  0.764  0.710  0.207
logistic_regression_platt   B_pre_cheap        STRUCT  TT_TW     444     0.583  0.806  0.866  0.204
logistic_regression_platt       C_clean           OBJ  TT_TW     444     0.986  0.837  0.997  0.013
logistic_regression_platt       C_clean PLAN_VALIDITY  TT_TW     448     0.400  0.868  0.792  0.146
logistic_regression_platt       C_clean      SCHEDULE  TT_TW     444     0.437  0.900  0.860  0.139
logistic_regression_platt       C_clean        STRUCT  TT_TW     444     0.583  0.887  0.924  0.154
logistic_regression_platt       C_leaky           OBJ  TT_TW     444     0.986  0.837  0.997  0.013
logistic_regression_platt       C_leaky PLAN_VALIDITY  TT_TW     448     0.400  1.000  1.000  0.000
logistic_regression_platt       C_leaky      SCHEDULE  TT_TW     444     0.437  0.903  0.865  0.134
logistic_regression_platt       C_leaky        STRUCT  TT_TW     444     0.583  0.887  0.924  0.154
```

Top features per claim family (C_clean)
---------------------------------------

```
                 model  claim_family  rank                          feature  value
   logistic_regression           OBJ     1     action_generalized_delta_pct -1.556
   logistic_regression           OBJ     2          action_n_late_customers -1.340
   logistic_regression           OBJ     3  perturbation_family=TIME_WINDOW  0.773
   logistic_regression           OBJ     4             affected_route_share  0.733
   logistic_regression           OBJ     5      affected_service_time_share -0.718
   logistic_regression PLAN_VALIDITY     1                 action_time_warp -6.494
   logistic_regression PLAN_VALIDITY     2      affected_service_time_share -0.821
   logistic_regression PLAN_VALIDITY     3     action_generalized_delta_pct -0.774
   logistic_regression PLAN_VALIDITY     4               affected_min_slack  0.732
   logistic_regression PLAN_VALIDITY     5             action_obj_delta_pct  0.666
   logistic_regression        STRUCT     1          action_n_late_customers -0.923
   logistic_regression        STRUCT     2     action_generalized_delta_pct -0.816
   logistic_regression        STRUCT     3            action_total_duration  0.813
   logistic_regression        STRUCT     4                     baseline_obj -0.676
   logistic_regression        STRUCT     5 perturbation_family=SERVICE_TIME  0.645
   logistic_regression      SCHEDULE     1     action_generalized_delta_pct -1.206
   logistic_regression      SCHEDULE     2   infeasibility_kind=time_window -1.072
   logistic_regression      SCHEDULE     3                 action_time_warp -0.949
   logistic_regression      SCHEDULE     4                  action_feasible  0.684
   logistic_regression      SCHEDULE     5                baseline_n_routes  0.680
         decision_tree           OBJ     1            action_total_duration  0.630
         decision_tree           OBJ     2                 action_time_warp  0.232
         decision_tree           OBJ     3     action_generalized_delta_pct  0.087
         decision_tree           OBJ     4          action_n_late_customers  0.040
         decision_tree           OBJ     5              action_max_lateness  0.011
         decision_tree PLAN_VALIDITY     1                 action_time_warp  0.998
         decision_tree PLAN_VALIDITY     2            action_total_duration  0.001
         decision_tree PLAN_VALIDITY     3             action_obj_delta_pct  0.000
         decision_tree PLAN_VALIDITY     4     action_generalized_delta_pct  0.000
         decision_tree PLAN_VALIDITY     5           perturbation_magnitude  0.000
         decision_tree        STRUCT     1            action_total_duration  0.346
         decision_tree        STRUCT     2          action_n_late_customers  0.333
         decision_tree        STRUCT     3             action_obj_delta_pct  0.083
         decision_tree        STRUCT     4     action_generalized_delta_pct  0.059
         decision_tree        STRUCT     5                 instance_class=C  0.058
         decision_tree      SCHEDULE     1                 action_time_warp  0.538
         decision_tree      SCHEDULE     2        baseline_generalized_cost  0.163
         decision_tree      SCHEDULE     3             action_obj_delta_pct  0.083
         decision_tree      SCHEDULE     4     action_generalized_delta_pct  0.064
         decision_tree      SCHEDULE     5 perturbation_family=SERVICE_TIME  0.045
hist_gradient_boosting           OBJ     1     action_generalized_delta_pct  0.123
hist_gradient_boosting           OBJ     2              action_max_lateness  0.007
hist_gradient_boosting           OBJ     3                 action_time_warp  0.004
hist_gradient_boosting           OBJ     4            affected_demand_share  0.004
hist_gradient_boosting           OBJ     5            action_total_duration  0.003
hist_gradient_boosting PLAN_VALIDITY     1                 action_time_warp  0.407
hist_gradient_boosting PLAN_VALIDITY     2            action_total_duration  0.002
hist_gradient_boosting PLAN_VALIDITY     3     action_generalized_delta_pct  0.001
hist_gradient_boosting PLAN_VALIDITY     4         baseline_min_route_slack  0.000
hist_gradient_boosting PLAN_VALIDITY     5           perturbation_magnitude  0.000
hist_gradient_boosting        STRUCT     1            action_total_duration  0.077
hist_gradient_boosting        STRUCT     2     action_generalized_delta_pct  0.037
hist_gradient_boosting        STRUCT     3                 action_time_warp  0.029
hist_gradient_boosting        STRUCT     4          action_n_late_customers  0.027
hist_gradient_boosting        STRUCT     5        baseline_generalized_cost  0.019
hist_gradient_boosting      SCHEDULE     1                 action_time_warp  0.258
hist_gradient_boosting      SCHEDULE     2     action_generalized_delta_pct  0.027
hist_gradient_boosting      SCHEDULE     3        baseline_generalized_cost  0.020
hist_gradient_boosting      SCHEDULE     4             action_obj_delta_pct  0.009
hist_gradient_boosting      SCHEDULE     5              affected_mean_slack  0.007
```

Files
-----

| file                                              | description |
| ------------------------------------------------- | ----------- |
| `predictor_model_summary.csv`                     | Per-fold AUROC / AUPRC / Brier + CV-aggregated mean / std. |
| `predictor_threshold_curves.csv`                  | Per-claim threshold sweep (gate + routing metrics). |
| `predictor_by_block.csv`                          | Claim × perturbation_family threshold sweep. |
| `predictor_pareto_frontier.csv`                   | Per (model, feature_set, threshold) row with `on_pareto_frontier` flag. |
| `predictor_vs_baselines_with_cis.csv`             | Paired-cell bootstrap CIs on Δ correctness and Δ compute. |
| `predictor_vs_baselines.csv`                      | Run 1 schema: predictor rows aggregated alongside baseline_policy_overall.csv rows. |
| `block_rule_extended.csv`                         | 4-key categorical bucket rates. |
| `predictor_setc_ablation.csv`                     | PV + SCHEDULE: C_clean vs C_leaky. |
| `deployment_config.csv`                           | Per-claim threshold for three correctness floors. PV deploys on Set B; legacy C_clean rows retained with `note=residual_leak_dropped_from_deployment`. |
| `stage_a_tt_tw_subset_metrics.csv`                | Stage A OOF metrics restricted to TT/TW perturbations — apples-to-apples reference for the probe. |
| `escalation_probe_oof.csv`                        | Zero-shot probe metrics. |
| `predictor_calibration_curves.csv`                | Reliability-curve bins per (model, feature_set, claim_family). |
| `predictor_coefficients_or_feature_importance.csv`| LR coefficients, DT importances, HistGB permutation importance. |
| `predictor_tree_exports/`                         | One text-export per (feature_set, claim_family) for the decision tree. |
| `nonmonotone_preservation.csv`                    | For STRUCT/SCHEDULE cheap=1, py10=0 cells: how often the gate preserves them. |
| `predictor_oof_predictions.csv`                   | OOF probabilities (predictors + `block_rule_extended`). |

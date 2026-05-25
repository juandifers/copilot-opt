# Pre-Run-2 Claim Family and Benchmark Design

_Summary of the Stage A / sufficiency benchmark design that precedes
and grounds Run 2. All numbers from sources locked at the pre-registration
tags listed below. No experiments are re-run here._

**Pre-registration tags:** `prereg-v1.0-vrptw` (commit `09c4c03`) →
`prereg-v1.1-vrptw` (commit `7d9cf08`) → `prereg-v1.2-vrptw` (commit
`274163a`). Primary spec: `prereg/PREREG_v1.2_vrptw.md`.

---

## 1. Three-Axis Decomposition

The thesis evaluates copilot answers along three independent axes (§3.1
PREREG_v1.2):

| Axis | Question | What it is between | VRPTW operationalisation |
|---|---|---|---|
| **Faithfulness** | Does the answer accurately report the action's output? | Language layer ↔ Action layer | Rubric-based LLM-as-judge scoring in the closing experiment (spec.md §5). Binary: score ≥ 4 on 5-point scale. |
| **Sufficiency** | Is the action's output close enough to the reference? | Action layer ↔ Reference | Claim-family-specific loss against PyVRP 60s seed=1 on perturbed instance. `band == easy` ⟹ sufficient. |
| **Operational validity** | Is the action's output executable under the perturbed constraints? | Action layer ↔ Real-world constraints | `capacity ∧ time_window ∧ coverage`: PyVRP `Solution.is_feasible()` + `num_missing_clients == 0`. Deterministic per-action. |

**Key design property:** the three axes can decouple. An action can be
faithful and sufficient yet operationally invalid (plan costs match but a
tightened TW is violated). It can be operationally valid and faithful yet
insufficient (construction heuristic places all customers but ignores the
operator's structural question). The decomposition makes these decouplings
visible — and their rate is what the closing experiment measures.

---

## 2. Claim Families

Four families (§3.2 PREREG_v1.2). The benchmark assigns exactly one
family per cell.

### 2.1 OBJ — Objective Value

- **Canonical question:** "What is the new total cost?" / "How much does cost change?"
- **Loss:** `|action_obj − ref_obj| / ref_obj` (relative objective gap).
- **Bands:** easy ≤ 0.05 · medium ≤ 0.15 · hard > 0.15.
- **Operational sufficiency rule:** `band == easy AND feasibility == True`. A numerically close cost on an infeasible plan is operationally wrong.
- **Generalised OBJ:** for TRAVEL_TIME and SERVICE_TIME cells where the distance matrix is unchanged, a second diagnostic (`distance + 0.1 × duration`) is reported. The primary metric is always distance-only; the generalised form appears in the analysis when the perturbation shifts duration without shifting distance.
- **Degenerate blocks:** `OBJ × TIME_WINDOW` cheap-sufficiency rate = 1.000 in-sample; `OBJ × TRAVEL_TIME` = 0.973. Both are effectively pre-determined decisions for the block-rule baseline.

### 2.2 PLAN_VALIDITY — Plan Feasibility

- **Canonical question:** "Can we keep using this plan?" / "Is the plan still feasible?"
- **Loss:** binary (0 = feasible, 1 = infeasible); determined by `action_feasible`.
- **Bands:** easy (feasible) / hard (infeasible). No medium band.
- **Operational sufficiency rule:** `feasibility_flag == True`. This is substantive — not a positive control.

> **v0.5 → v1.0 semantic shift.** v0.5 defined PLAN_VALIDITY as a
> positive-control family (reuse_direct's feasibility check was always
> correct by construction). v1.0 redefines it as a substantive feasibility
> claim computed per-action. Under v1.0, `reuse_direct` PLAN_VALIDITY-easy
> = 29.9% (18-instance scale-check); the label is not trivial.

- **Residual-leak note:** PV × C_clean achieves AUROC ≈ 1.000 for HistGB/DecisionTree because continuous post-cheap features (`action_time_warp`, `action_obj_delta_pct`, …) carry definitional feasibility signal. The deployed PV gate uses **Set B (pre-cheap)** — the B_pre_cheap feature set avoids this leak. The C_clean PV rows are retained in `deployment_config.csv` with `note = residual_leak_dropped_from_deployment` for audit transparency.

### 2.3 STRUCT — Structure

- **Canonical question:** "Which customers move?" / "Are the same customers still served together?"
- **Loss:** `1 − ARI(action_assignment, reference_assignment)`. Unassigned customers (partial-coverage cases from `reuse_direct` on ORDER_CHANGE) get sentinel label −1.
- **Bands:** easy ≤ 0.10 · medium ≤ 0.30 · hard > 0.30.
- **Operational sufficiency rule:** `band == easy`. Operational validity does not apply — a structural claim is answerable on any plan's assignment.
- **Rationale for ARI:** ARI is deterministic and the de facto standard for clustering comparison. Range is [−1, 1]; `loss_struct` therefore ranges [0, 2] but sits in [0, 1] for non-pathological partitions.
- **VRPTW advantage over CVRP:** CVRP `struct_unstable_rate ≈ 0.926` (PyVRP partitions are multimodal under the Uchoa-X noise floor). VRPTW `struct_unstable_rate = 0.167–0.194` (time-window constraints shrink the feasible high-quality partition set). The STRUCT metric is signal-bearing on VRPTW; it measured solver noise on CVRP.

### 2.4 SCHEDULE — Schedule Timing

- **Canonical question:** "When will deliveries arrive?" / "Whose schedules slip?"
- **Loss:** p90 of `|start_service_action[c] − start_service_ref[c]| / depot_horizon` over the *affected* customer subset.
- **Bands:** easy ≤ 0.02 · medium ≤ 0.05 · hard > 0.05. Calibrated on the perturbation pilot v2: pilot median 0.0214, p90 0.0645; 18-instance scale-check median 0.0214, p90 0.2415.
- **Operational sufficiency rule:** `band == easy`. Operational validity does not apply.
- **Affected subset definition:** customers whose baseline-vs-perturbed comparison is meaningful. INSERT new-customers (ORDER_CHANGE) are excluded (no baseline counterpart). Falls back to all common customers if the affected set is empty.
- **Replaces RANK (v0.5):** VRPTW admits multiple incompatible per-route impact metrics (cost delta, lateness, schedule shift, slack). SCHEDULE captures the most operationally critical form — *whose* schedule shifts — without forcing an arbitrary route-level ranking choice.

---

## 3. Perturbation Design

Sixteen perturbations per instance, four families of four (§6 PREREG_v1.2).
Full grid in `perturbation_design_summary.csv`.

| Family | Stress vector | Claim families most affected | n perturbations |
|---|---|---|---:|
| TRAVEL_TIME | Duration-matrix inflation on selected customer arcs (×1.05 to ×1.30) | SCHEDULE, OBJ, PLAN_VALIDITY | 4 |
| TIME_WINDOW | Customer window tightening or shifting (5–10% of width) | PLAN_VALIDITY, SCHEDULE | 4 |
| SERVICE_TIME | Service-duration inflation on selected customers (×1.05 to ×1.50) | OBJ, SCHEDULE, PLAN_VALIDITY | 4 |
| ORDER_CHANGE | Customer insertions (1–3 new; demand 5–20% of capacity; flexible or tight windows) | STRUCT, PLAN_VALIDITY, OBJ | 4 |

**Why four families?** Each stresses a different part of the copilot's
reasoning surface. TT and ST inflate costs / schedules without adding
new customers. TW tightens feasibility without changing costs. OC
tests the policy's ability to handle demand growth — the only case
where the baseline plan literally cannot cover all customers without
modification.

**Cheap-action selection by family:**
- TT / TW / ST → `reuse_direct` (score baseline routes unchanged; ~0.001 s)
- OC → `local_repair_insert` (cheapest-feasible insertion; ~0.3 s)

---

## 4. Action Portfolio

Five actions evaluated per cell. The portfolio is **not a ladder** — no single
linear quality ordering exists across all claim families (§7 PREREG_v1.2). See
`action_ladder_summary.csv` for the full table including 18-instance easy-rates.

| Action | Easy rate: OBJ | PV | STRUCT | SCHEDULE | Runtime |
|---|---:|---:|---:|---:|---:|
| `reuse_direct` | 88.0% | 29.9% | 62.5% | 47.6% | 0.002 s |
| `local_repair_insert` | 85.7% | 50.0% | 48.6% | 54.3% | 0.291 s |
| `construct_feasible` | 0.0% | 98.3% | 0.0% | 7.8% | 0.122 s |
| `pyvrp_10s` | 100.0% | 98.3% | 86.6% | 89.8% | 10.008 s |
| `pyvrp_60s_reference` | 100.0% | 98.3% | 100.0% | 100.0% | 60.008 s |

Source: 18-instance expanded-action scale-check
(`prereg/vrptw_scale_check_18_expanded_actions_report.md`).

**`construct_feasible` is a feasibility specialist, not a quality solver.**
Its 98.3% PV-easy / 0.0% OBJ-easy profile shows the fundamental tension
in the action portfolio: there is no sub-second action that recovers both
feasibility and objective quality. This motivates the copilot's policy
as a gated routing decision rather than a fixed rule.

**`pyvrp_60s_reference` is not deployable.** It is the label-generating
reference only. The wide-table row is materialised from the reference
solve at no extra cost.

---

## 5. Sufficiency Predictor

The deployed predictor is a per-family HistGradientBoosting gate that
outputs P(cheap_sufficient | features, claim_family) and accepts cheap
when P ≥ threshold.

### 5.1 Feature Sets

| Set | Name | Description |
|---|---|---|
| A | `A_categorical` | (claim_family, pert_family, instance_class, magnitude_bucket) — no action-output features |
| B | `B_pre_cheap` | Set A + pre-cheap diagnostics: baseline_obj, baseline_n_routes, baseline_min_route_slack, baseline_generalized_cost, perturbation_magnitude, affected_route/demand/service_time/min_slack shares |
| C | `C_clean` | Set B + post-cheap diagnostics: action_obj_delta_pct, action_generalized_delta_pct, action_time_warp, action_total_duration, action_n_late_customers, action_max_lateness, infeasibility_kind (OHE), action_feasible. **Drops definitional columns** for PV and SCHEDULE (avoids feasibility leak) |

`C_leaky` adds back the definitional columns (ablation; not deployable for PV).

### 5.2 Deployed Configuration

Source: `reports/predictor_models/deployment_config.csv`.

| Family | Model | Feature set | Threshold | Final correctness | Avg compute (s) | Coverage | Precision | Floor met |
|---|---|---|---:|---:|---:|---:|---:|---:|
| OBJ | HistGB | C_clean | 0.50 | 0.980 | 0.914 | 91.6% | 97.8% | Yes (at 0.95) |
| PLAN_VALIDITY | HistGB | **B_pre_cheap** | 0.80 | 0.962 | 7.185 | 28.9% | 89.2% | Yes (at 0.95) |
| STRUCT | HistGB | C_clean | 0.95 | 0.874 | 7.713 | 23.6% | 94.3% | No (floor 0.90 not met) |
| SCHEDULE | HistGB | C_clean | 0.98 | 0.892 | 9.525 | 5.5% | 91.8% | No (floor 0.90 not met) |

PLAN_VALIDITY deploys on Set B despite C_clean's higher correctness
(0.988 vs 0.962) because C_clean's performance on PV rides on the
residual feasibility leak through post-cheap continuous features.
The linear logistic model (C_clean AUROC 0.915 vs HistGB 0.999) shows
the non-tautological signal level for PV.

### 5.3 Headline AUROC (HistGB / C_clean, 5-fold grouped-by-instance CV)

| Family | AUROC | AUPRC | Notes |
|---|---:|---:|---|
| OBJ | 0.978 | — | Top feature: `action_generalized_delta_pct` (importance 0.123) |
| PLAN_VALIDITY | 0.999 | — | Near-ceiling; residual leak. LR C_clean 0.915 = non-tautological level |
| STRUCT | 0.851 | — | Weakest family. Top features: `action_total_duration`, `action_generalized_delta_pct` |
| SCHEDULE | 0.876 | — | ΔAUROC vs Set B = +0.073 (B AUROC 0.803). "Outcome A" framing: routing via B, verification via C |

### 5.4 Predictor vs Categorical Baseline (Bootstrap CIs, n=1000 paired-cell resamples)

| Comparison | Δ correctness (mean) | 95% CI | Δ compute (mean, s) | 95% CI |
|---|---:|---:|---:|---:|
| HistGB/C_clean vs block_rule_extended/t=0.95 | −0.005 | [−0.008, −0.002] | **−1.15 s** | [−1.27, −1.03] |
| HistGB/B_pre_cheap vs block_rule_extended/t=0.90 | −0.004 | [−0.008, +0.001] | **−0.49 s** | [−0.60, −0.38] |
| LR/C_clean vs block_rule_extended/t=0.90 | −0.009 | [−0.013, −0.004] | **−0.38 s** | [−0.50, −0.27] |

**Reading:** the predictor achieves the same correctness floor as the
categorical baseline while saving 1.15 s per cell (HistGB/C_clean at the
pareto-best operating point). The compute saving is the thesis claim;
the correctness margin is consistent with zero or a small negative.

### 5.5 Non-Monotone Preservation

54 cells (32 STRUCT + 22 SCHEDULE) where the cheap action is sufficient
but `pyvrp_10s` is not. A "good" gate accepts a high fraction of these —
escalating would hurt quality. HistGB/C_clean at t=0.70 preserves:

- STRUCT: 23/32 (71.9%) vs block_rule 9/32 (28.1%)
- SCHEDULE: 13/22 (59.1%) vs block_rule 5/22 (22.7%)

This is the key argument that a learned gate beats the categorical
baseline on the cases where the baseline would over-escalate.

---

## 6. Benchmark Scale

| Unit | Count | Notes |
|---|---:|---|
| Solomon-100 instances | 56 | Full eligible pool; all C/R/RC × 1xx/2xx archetypes |
| Perturbations per instance | 16 | 4 families × 4 perturbations |
| Total (instance, perturbation) cells | 896 | 56 × 16 |
| Wide rows (instance × perturbation × action) | 3,808 | 12 non-OC × 4 actions + 4 OC × 5 actions = 68 per instance |
| Long claim rows (× 4 claim families) | 15,232 | Primary analysis unit |
| Cheap-action long rows used for predictor | 3,563 | After dropping NaN labels (7 OBJ + 7 STRUCT + 7 SCHEDULE + 0 PV) |
| Reference solves (seeds 1/2/3) | 2,688 | Full multi-seed audit; §8.2 PREREG_v1.2 |

**Overall cheap-sufficiency rate:** 0.585 (2,083/3,563 cheap-action cells
are sufficient). This is the baseline correctness for an ungated copilot
(`cheap_only` policy).

---

## 7. Closing Experiment Design (spec.md)

The closing experiment puts the locked predictor in the loop with an LLM:

```
operator prompt
  → claim-family classifier (Haiku 4.5; zero-shot)
  → sufficiency predictor (locked from Stage A)
  → compute-aware policy (locked thresholds from deployment_config.csv)
  → answer generator (Haiku 4.5; structured output)
  → three-axis scorer (Sonnet 4.6 judge + deterministic op-validity)
```

**Prompt set:** 48 prompts (12 per family); 2×2 stratification per family
(TP / FP / FN / TN from the policy's perspective on the locked predictor).
24 synthetic templates + 24 LLM-generated variants.

**Pre-registered claims (spec.md §"Pre-registered claims"):**

| Claim | Threshold | What would fail it |
|---|---|---|
| 1 — Axis separability | ≥ 10% mixed-axis patterns | All prompts all-pass or all-fail |
| 2 — Policy effect | Op-validity rate differs ≥ 0.20 between policy-accepts and policy-escalates on insufficient cells | Policy decision not visible at language level |
| 3 — Sufficiency manifests | Mean faithfulness drop ≥ 0.5 points on insufficient cells (5-point scale) | Faithfulness does not correlate with sufficiency |
| 4 — Cross-scale | Homberger faithfulness within 0.5 points of Stage A | Scale degrades LLM grounding sharply |

**Success rule:** ≥ 3 of 4 claims hold (3-of-4 rule, spec.md §"What success looks like").

---

## 8. Key Caveats for Thesis Prose

1. **Stage A is Solomon-100 only.** The Homberger probe (12 prompts,
   Stage B gated on stability) is the OOD slice; it does not establish
   generalisation beyond Solomon-100.

2. **The predictor is a routing gate, not a quality predictor.** It
   predicts P(cheap_sufficient) for the specific (claim_family,
   perturbation) combination — not whether the operator's answer will
   be good in general.

3. **STRUCT and SCHEDULE floors are not met at t=0.90.** The best-correctness
   STRUCT/SCHEDULE thresholds fall below the 0.90 correctness floor (STRUCT
   0.874, SCHEDULE 0.892). These are documented in `deployment_config.csv`
   with `floor_met = False`; the thesis must not claim the predictor meets
   the 0.90 floor for those families.

4. **PV × C_clean inflated AUROC.** The near-perfect AUROC for PV × C_clean
   (HistGB 0.999) is a known artifact of the post-cheap continuous features.
   The deployable signal level is LR × C_clean (AUROC 0.915).

5. **Bootstrap CI on Δ correctness is negative for C_clean vs block_rule_extended.**
   The compute saving is the win (−1.15 s, CI [−1.27, −1.03]); correctness is
   neutral-to-slightly-negative relative to the matched baseline. The thesis
   framing is "same correctness, lower cost" not "higher correctness".

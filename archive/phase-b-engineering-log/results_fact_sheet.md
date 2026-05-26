# Results Chapter Fact Sheet

_Generated 2026-05-23. All numbers sourced directly from artifact files at HEAD `18b4811` (`run2-contract-extended`) unless noted._

---

## 1. System B Full Run 2 Results

**Run metadata:** run_id `run2-b-openai-gpt54mini-v1`, model `gpt-5.4-mini` (observed `gpt-5.4-mini-2026-03-17`), n=60, parsed=60, unscored=0.

### Overall (n=60)

| Metric | Value |
|---|---|
| intent accuracy | 0.950 |
| answerability accuracy | 0.967 |
| behavior_class accuracy | 0.917 |
| evidence precision | 0.771 |
| evidence recall | 0.902 |
| warning precision | 0.917 |
| warning recall | 0.950 |
| missing-field recall | 0.992 |
| useful_refusal correct | 0.944 (17/18) |

### By implementation_status

| | current (39) | target_extension (21) |
|---|---|---|
| intent | 0.949 | 0.952 |
| answerability | 0.949 | 1.000 |
| behavior_class | 0.872 | 1.000 |
| evidence P/R | 0.673 / 0.859 | 0.952 / 0.981 |
| warning P/R | 0.872 / 0.923 | 1.000 / 1.000 |
| missing-field R | 0.987 | 1.000 |
| useful_refusal | 0.857 (6/7) | 1.000 (11/11) |

### By family

| Family | n | intent | answerability | behavior_class | ev P/R | warn P/R |
|---|---|---|---|---|---|---|
| OBJ | 15 | 1.000 | 1.000 | 1.000 | 1.000 / 0.973 | 1.000 / 1.000 |
| PLAN_VALIDITY | 12 | 1.000 | 1.000 | 0.917 | 0.750 / 0.625 | 0.917 / 1.000 |
| SCHEDULE | 15 | 0.933 | 0.933 | 0.800 | 0.649 / 0.933 | 0.800 / 0.867 |
| STRUCT | 18 | 0.889 | 0.944 | 0.944 | 0.694 / 1.000 | 0.944 / 0.944 |

### By expected_behavior_class

| Behavior class | n | intent | answerability | behavior_class | ev P/R | warn P/R |
|---|---|---|---|---|---|---|
| direct_answer | 27 | 0.963 | 0.963 | 0.926 | 0.712 / 0.796 | 0.926 / 1.000 |
| direct_answer_with_warning | 8 | 0.875 | 0.875 | 0.625 | 0.500 / 1.000 | 0.625 / 0.625 |
| partial_answer_with_warning | 7 | 1.000 | 1.000 | 1.000 | 1.000 / 0.943 | 1.000 / 1.000 |
| useful_refusal | 18 | 0.944 | 1.000 | 1.000 | 0.889 / 1.000 | 1.000 / 1.000 |

`direct_answer_with_warning` is the weakest behavior class on intent, behavior_class, and warning P/R.

### Failure taxonomy (60 cases)

| Failure mode | Count |
|---|---|
| evidence_precision_miss | 22 |
| evidence_recall_miss | 9 |
| behavior_class_miss | 5 |
| warning_precision_miss | 3 |
| warning_recall_miss | 3 |
| intent_miss | 3 |
| answerability_miss | 2 |
| missing_field_miss | 1 |
| useful_refusal_composite_miss | 1 |
| partial_answer_composite_miss | 0 |

### Artifact paths

- Report: `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.md`
- CSV: `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.csv`
- Raw outputs: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-v1/`

---

## 2. System A Results

**System A was run on 30 cases, not the full 60.** The R2-6 design (§7) specifies a stratified 30-case sampler run, conditional on pass^k succeeding. The full 60-case run was not executed.

**Run metadata:** run_id `run2-a-openai-gpt54mini-30case-v1`, model `gpt-5.4-mini` (observed `gpt-5.4-mini-2026-03-17`), parsed=30, unscored=30.

### Overall (n=30)

| Metric | Value |
|---|---|
| intent accuracy | 1.000 |
| answerability accuracy | 1.000 |
| behavior_class accuracy | 0.933 |
| evidence precision | 0.806 |
| evidence recall | 0.902 |
| warning precision | 0.967 |
| warning recall | 1.000 |
| missing-field recall | 1.000 |
| useful_refusal correct | 1.000 (11/11) |

### By implementation_status

| | current (17) | target_extension (13) |
|---|---|---|
| intent | 1.000 | 1.000 |
| answerability | 1.000 | 1.000 |
| behavior_class | 0.941 | 0.923 |
| evidence P/R | 0.657 / 0.838 | 1.000 / 0.985 |
| warning P/R | 1.000 / 1.000 | 0.923 / 1.000 |
| missing-field R | 1.000 | 1.000 |
| useful_refusal | 1.000 (3/3) | 1.000 (8/8) |

### By family (30-case sample)

| Family | n | intent | answerability | behavior_class | ev P/R |
|---|---|---|---|---|---|
| OBJ | 5 | 1.000 | 1.000 | 1.000 | 1.000 / 0.960 |
| PLAN_VALIDITY | 7 | 1.000 | 1.000 | 1.000 | 0.738 / 0.607 |
| SCHEDULE | 11 | 1.000 | 1.000 | 1.000 | 0.773 / 1.000 |
| STRUCT | 7 | 1.000 | 1.000 | 0.714 | 0.786 / 1.000 |

### Failure taxonomy (30 cases)

| Failure mode | Count |
|---|---|
| evidence_precision_miss | 10 |
| evidence_recall_miss | 5 |
| behavior_class_miss | 2 |
| all others | 0 |

Cases where C-extended passes a component metric but System A misses: **7** (vs 15 for System B on 60 cases).

### Pass^k results

**System B** (R2-5, 10 cases × k=5, run-id `run2-b-openai-gpt54mini-passk-v1`):

| Subset | n | stable_success | stable_failure | flaky | pass^k_all | pass@k_any |
|---|---|---|---|---|---|---|
| target_extension | 5 | 3 | 0 | 2 | 0.60 | 1.00 |
| current-row | 5 | 0 | 5 | 0 | 0.00 | 0.00 |
| **overall** | **10** | **3** | **5** | **2** | **0.30** | **0.50** |

**System A** (R2-6, 10 cases × k=3, run-id `run2-a-openai-gpt54mini-passk-v1`):

| Subset | n | stable_success | stable_failure | flaky | pass^k_all | pass@k_any |
|---|---|---|---|---|---|---|
| target_extension | 5 | 4 | 0 | 1 | 0.80 | 1.00 |
| current-row | 5 | 1 | 3 | 1 | 0.20 | 0.40 |
| **overall** | **10** | **5** | **3** | **2** | **0.50** | **0.70** |

B→A delta: +0.20 pass^k_all, +2 stable successes, −2 stable failures.

Per-case migration:

| Case | B pass^k_all (k=5) | A pass^k_all (k=3) | Change |
|---|---|---|---|
| R2-008 | 1.000 | 1.000 | stable_success → stable_success |
| R2-012 | 1.000 | 1.000 | stable_success → stable_success |
| R2-015 | 1.000 | 1.000 | stable_success → stable_success |
| R2-048 | 0.400 | 0.667 | flaky → flaky (mild improvement) |
| R2-058 | 0.800 | 1.000 | flaky → **stable_success** |
| R2-027 | 0.000 | 0.000 | stable_failure → stable_failure |
| R2-040 | 0.000 | 1.000 | stable_failure → **stable_success** |
| R2-051 | 0.000 | 0.333 | stable_failure → flaky (partial recovery) |
| R2-055 | 0.000 | 0.000 | stable_failure → stable_failure |
| R2-060 | 0.000 | 0.000 | stable_failure → stable_failure |

### Artifact paths

- 30-case report: `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_30case_v1.md`
- 30-case CSV: `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_30case_v1.csv`
- Raw outputs: `product/evaluation/model_outputs/run2-a-openai-gpt54mini-30case-v1/`
- Smoke (5-case): `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_smoke.md`
- Pass^k report: `product/evaluation/reports/run2_passk_system_a_gpt54mini_v1.md`
- Pass^k CSV: `product/evaluation/reports/run2_passk_system_a_gpt54mini_v1.csv`
- System B pass^k: `product/evaluation/reports/run2_passk_gpt54mini_v1.md`
- Design: `product/evaluation/reports/run2_system_a_design.md`
- Final report: `product/evaluation/reports/run2_system_a_final_report.md`

---

## 3. C-Extended Run 2 Results

**n=60, contract-only mode (no generator answer_text), deterministic.**

### Overall

| Metric | Value |
|---|---|
| intent accuracy | 1.000 |
| answerability accuracy | 1.000 |
| behavior_class accuracy | 1.000 |
| evidence precision | 0.980 |
| evidence recall | 1.000 |
| warning precision | 1.000 |
| warning recall | 1.000 |
| missing-field recall | 1.000 |
| useful_refusal correct | 1.000 (18/18) |

Evidence precision is 0.980 (not 1.000) because the PLAN_VALIDITY family emits `infeasibility_kind` alongside the four primary feasibility-breakdown fields; the gold pins 4 paths and the contract emits 5. PLAN_VALIDITY evidence P = 0.900. All other families: evidence P = 1.000. This is a pre-existing contract/rubric mismatch, not a regression.

### By implementation_status

- **current (39):** all metrics 1.000 except evidence P = 0.969. **0 regressions.**
- **target_extension (21):** all metrics 1.000 (all 6 R2-3 extensions correct). **0 target_extension failures.**

### Whether pass^k_all = 1.00 is by construction or run as repeated eval

**By construction.** C-extended is a deterministic rule-based pipeline; given the same (prompt, payload) inputs it produces identical output on every call. No pass^k run was conducted for C-extended. The claim is stated as a structural invariant in `run2_system_a_final_report.md §5` and `run2_passk_system_a_gpt54mini_v1.md §11`.

### Three-way summary

| | C-extended (60) | System B (60) | System A (30) |
|---|---|---|---|
| intent | 1.000 | 0.950 | 1.000 |
| answerability | 1.000 | 0.967 | 1.000 |
| behavior_class | 1.000 | 0.917 | 0.933 |
| evidence P | 0.980 | 0.771 | 0.806 |
| evidence R | 1.000 | 0.902 | 0.902 |
| warning P | 1.000 | 0.917 | 0.967 |
| warning R | 1.000 | 0.950 | 1.000 |
| missing-field R | 1.000 | 0.992 | 1.000 |
| useful_refusal | 1.000 (18/18) | 0.944 (17/18) | 1.000 (11/11) |
| pass^k_all | 1.000 (by construction) | 0.30 (k=5, n=10) | 0.50 (k=3, n=10) |

### Artifact paths

- C-extended report: `product/evaluation/reports/run2_benchmark_eval_system_c_extended.md`
- C-extended CSV: `product/evaluation/reports/run2_benchmark_eval_system_c_extended.csv`
- C-current (pre-extension) report: `product/evaluation/reports/run2_benchmark_eval_system_c_current.md` — overall intent 0.950, answerability 0.817, behavior_class 0.817 (21 target_extension failures, as expected)
- Comprehensive stage-by-stage report: `product/evaluation/reports/run2_comprehensive_report.md`
- Model baselines summary CSV: `product/evaluation/thesis_narrative_packet/run2_model_baselines_summary.csv`

---

## 4. R2-S Stress Results Before D1 (C0 Baseline)

All axes frozen at HEAD `18b4811`. 24 cases each, 12 dev / 12 heldout.

### Axis 1 — Look-alike Intent

**C0 only.** Constructed prompts with surface-token attractors toward a neighbouring wrong intent.

#### Overall (n=24)

| Metric | Value |
|---|---|
| intent_correct | **87.5%** (21/24) |
| answerability_correct | 100.0% |
| behavior_class_correct | 100.0% |
| evidence_precision | 90.0% |
| evidence_recall | 100.0% |
| warning_precision | 100.0% |
| warning_recall | 100.0% |

Dev (12): intent 83.3%. Heldout (12): intent **91.7%**.

#### Bucket distribution

| Bucket | n |
|---|---|
| guard_protected | 18 |
| wrong_adjacent_intent | **3** |
| downstream_mismatch | 3 |
| unknown_intent | **0** |

All 3 wrong_adjacent_intent failures are in Band 4 (OBJ `objective_value` vs `objective_delta` via `_COMPARATIVE_TOKENS`). Zero `unknown` fallbacks — the distinguishing feature vs Axis 3.

#### Conditional on correct intent (21/24)

answerability 100.0%, behavior_class 100.0%, ev P 97.1%, ev R 100.0%, warning P/R 100.0%.

#### By confusion band

| Band | n | intent correct |
|---|---|---|
| membership_vs_new_customer_assignment | 6 | 100.0% |
| lateness_vs_feasibility_status | 6 | 100.0% |
| route_listing_vs_route_end_time | 6 | 100.0% |
| comparison_vs_status_or_objective | 6 | **50.0%** |

Path: `product/evaluation/run2_stress/axis1_lookalike/reports/axis1_closeout.md`

---

### Axis 2 — OOD Premises / Comparators

**C0 only.** Unsupported premises: nonexistent entities, unsupported movement, missing comparators, causal questions.

#### Overall (n=24)

| Metric | Value |
|---|---|
| intent_correct | **75.0%** (18/24) |
| answerability_correct | 75.0% |
| behavior_class_correct | 75.0% |
| evidence_precision | 83.3% |
| evidence_recall | 95.0% |
| warning_precision | 66.7% |
| warning_recall | 66.7% |
| missing_field_recall | 91.7% |
| useful_refusal_correct | **60.0%** (9/15) |
| partial_answer_correct | **50.0%** (2/4) |

Dev (12): intent 83.3%. Heldout (12): intent 66.7%.

#### Bucket distribution

| Bucket | n |
|---|---|
| correct_refusal_or_partial | 11 |
| schema_gap_or_unrepresentable_gold | **5** |
| wrong_intent | 4 |
| unknown_intent | 2 |
| missed_false_premise | 2 |
| over_answered_unsupported_premise | 0 |
| missed_missing_comparator | 0 |

#### By band

| Band | n | intent | useful_refusal |
|---|---|---|---|
| nonexistent_entity_false_premise | 6 | 100.0% | 66.7% (4/6) |
| unsupported_movement_or_assignment | 6 | 50.0% | 50.0% (3/6) |
| missing_comparator_or_baseline | 6 | 50.0% | 50.0% (1/2) |
| **causal_or_explanatory** | **6** | **100.0%** | **100.0% (1/1)** |

Path: `product/evaluation/run2_stress/axis2_ood_premises/reports/axis2_closeout.md`

---

### Axis 3 — Semantic Paraphrase

**C0 only.** Paraphrased surface forms of supported Run 2 intents.

#### Overall (n=24)

| Metric | Value |
|---|---|
| intent_correct | **62.5%** (15/24) |
| answerability_correct | 62.5% |
| behavior_class_correct | 62.5% |
| evidence_precision | 59.2% |
| evidence_recall | 62.5% |
| warning_precision | 87.5% |
| warning_recall | 87.5% |
| missing_field_recall | 100.0% |

Dev (12): intent 66.7%. Heldout (12): intent **58.3%**.

All 9 failures are `unknown` fallback — zero wrong-adjacent intent misroutes.

#### By subtype

| Subtype | n | intent_correct |
|---|---|---|
| cost_synonym | 3 | 100.0% |
| feasibility_synonym | 4 | 100.0% |
| entity_synonym | 5 | 80.0% |
| operator_colloquial | 2 | 50.0% |
| paraphrase | 2 | 0.0% |
| schedule_synonym | 8 | **37.5%** |

`schedule_synonym` is the weakest band: 5/8 fail because the SCHEDULE matcher requires both a `route` token and a specific completion verb (`wrap up` / `end time` / `finish` / `complete`).

#### Conditional on correct intent (15/24)

| Metric | Value |
|---|---|
| answerability_correct | **100.0%** |
| behavior_class_correct | **100.0%** |
| evidence_precision | 94.7% |
| evidence_recall | **100.0%** |
| warning_precision | **100.0%** |
| warning_recall | **100.0%** |
| missing_field_recall | **100.0%** |

The ev P shortfall (94.7%) is the pre-existing PLAN_VALIDITY `infeasibility_kind` off-by-one, not a paraphrase effect.

**Central finding:** C0's 100% Run 2 score is template-bound. Conditional on correct intent, every downstream layer performs exactly as on the locked benchmark. The bottleneck is semantic intent mapping, not answerability/evidence/refusal logic.

Path: `product/evaluation/run2_stress/axis3_semantic/reports/axis3_closeout.md`

---

### Axis 4 — Payload Scale

**C0, System A, System B.** All SCHEDULE family, Homberger-200 instances. Low band: n_routes ∈ [8,12]. High band: n_routes ∈ [18,22].

#### Per-system × band

| System | Band | n | intent | ans | beh | ev P | ev R | warn P | warn R |
|---|---|---|---|---|---|---|---|---|---|
| C0 | low | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A | low | 12 | 1.000 | 1.000 | 0.917 | 0.667 | 1.000 | 0.917 | 1.000 |
| A | high | 12 | 1.000 | 1.000 | 1.000 | 0.567 | 1.000 | 1.000 | 1.000 |
| B | low | 12 | 1.000 | 0.583 | 0.417 | 0.528 | 1.000 | 0.417 | 0.917 |
| B | high | 12 | 0.833 | 0.583 | 0.333 | 0.319 | 0.625 | 0.333 | 0.917 |

C0 is perfect (24/24) by construction — full structured payload, no projection cutoff. System A preserves intent/answerability via deterministic prior; evidence over-citation persists across both bands (17/24 A failures on ev P only). System B degrades sharply: 5 truncation-induced false premises from the `_MAX_SCHEDULE_ROWS_INLINE=60` projection cutoff.

API tokens: B prompt 184,679 / completion 2,881; A prompt 183,427 / completion 3,048.

Paths:
- Axis 4 closeout: `product/evaluation/run2_stress/axis4_payload/reports/axis4_closeout.md`
- System A baseline: `product/evaluation/run2_stress/axis4_payload/reports/system_a_baseline.md`
- System B baseline: `product/evaluation/run2_stress/axis4_payload/reports/system_b_baseline.md`

Aggregate stress summary: `product/evaluation/thesis_narrative_packet/stress_axes_summary.csv`

---

## 5. System D Results

All systems frozen at HEAD `18b4811`. Must-not-regress cohort: **70 cases** throughout all stages. Progression summary: `product/evaluation/thesis_narrative_packet/system_d_progression_summary.csv`

### D1 — Deterministic phrase-bank intent adapter

**Change locus:** `product/copilot/intent.py` (infer_intent_d1 + semantic_intent_adapter.py + query_frame.py)

| Metric | Value |
|---|---|
| Target failures | 18 |
| Fixed | **18/18** |
| Must-not-regress preserved | **70/70** |
| Core Run 2 regressions | **0** |
| Adapter invocations | 31 |
| Adapter overrides | 18 |
| Adapter fallbacks | 13 |

Stress intent gains vs C0: Axis 1 21→**24**, Axis 2 18→**24**, Axis 3 15→**24**, Axis 4 unchanged 24→24.

Run 2 core: all metrics 1.000 (evidence P = 0.980, inherited PLAN_VALIDITY artifact). 15 of 18 target cases fully perfect; 3 residual `route_indexing_ambiguity` warning gaps addressed in D2.

Guard-protected cases across all axes: C0 46/96 → D1 **64/96**.

Paths: `product/evaluation/system_d1/reports/system_d1_closeout.md`, `system_d1_core_run2_report.md`, `system_d1_stress_report.md`

---

### D2 — Answerability + warning wrapper extensions

**Change locus:** new `d2_answerability.py` + `d2_refusal_policy.py` wrapper layer on top of D1. `product/copilot/refusal_policy.py` and `product/data/answerability.py` byte-identical.

| Metric | Value |
|---|---|
| Target failures | 5 (2 missed_false_premise on A2, 3 route_indexing_ambiguity warning gaps on A1/A3) |
| Fixed | **5/5** |
| D1 target-18 preserved | **18/18** |
| Must-not-regress preserved | **70/70** |
| Core Run 2 regressions | **0** |
| Over-firing checks | **0** new over-fires |

Axis 2 behavior_class: D1 0.917 → D2 **1.000**. Axis 3 behavior_class: D1 0.875 → D2 **1.000**.

Full 156-case evaluation (Run 2 core + Axes 1–4). Total stress improvement vs C0: +17/96; vs D1: +3/96.

Paths: `product/evaluation/system_d2/reports/system_d2_closeout.md`, `system_d2_core_run2_report.md`, `system_d2_stress_report.md`

---

### D3 — Causal-unsupported schema extension

**Change locus:** `d3_refusal_policy.py` causal-warning extension + `axis2_causal_gold_overlay.csv` (schema-v2 overlay). `contracts.py` and `product_schema.py` byte-identical.

| Metric | Value |
|---|---|
| Target failures | 5 (Axis 2 causal band: A2D-10/11/12, A2H-11/12) under v2 gold overlay |
| Fixed | **5/5** under v2 overlay |
| D2 target-5 preserved | **5/5** |
| D1 target-18 preserved | **18/18** |
| Must-not-regress preserved | **70/70** |
| Core Run 2 regressions | **0** |
| Off-target causal emissions | **0** |
| Axis 4 regressions | **0** (24/24 perfect) |

Note: D3 drops Axis 2 behavior_class 1.000 → 0.792 under v1 gold (expected — v1 gold does not include `causal_mechanism_unsupported`). Under v2 overlay all 5 flip to pass.

Paths: `product/evaluation/system_d3/reports/system_d3_closeout.md`, `d2_d3_combined_summary.md`, `system_d3_core_run2_report.md`, `system_d3_stress_report.md`

---

### D4 — Compute-decision policy layer

**Change locus:** new `compute_decision.py` + `d4_system_c.py` wrapper. D1/D2/D3 modules unchanged.

#### D4 evaluation set (32 cases, 16 dev / 16 heldout)

Mode distribution: answer_from_payload=8, needs_comparison_payload=8, needs_recompute=8, partial_from_payload=4, clarification_needed=2, unsupported=2.

| Metric | Value |
|---|---|
| compute_mode_accuracy | **1.000** |
| requires_recompute_accuracy | **1.000** |
| recommended_action_accuracy | **1.000** |
| query_family_accuracy | **1.000** |
| missing_for_full_answer_recall | **1.000** |
| safe_no_solver_rate | **1.000** |

#### D3 regression check (Run 2 core + Axes 1–4, n=156)

All fields: intent, answerability, warnings, evidence_paths, missing_fields, next_actions, behavior_class → **all_fields_match_rate = 1.000**. Per-axis: all 1.000.

Paths: `product/evaluation/system_d4/reports/system_d4_closeout.md`, `system_d4_core_run2_report.md`, `system_d4_stress_report.md`, `api_contract_update.md`

---

## 6. D-Final Results

Model: `gpt-5.4-mini`. Mode: `hybrid_guarded`. Promoted to frontend default (`DEFAULT_SYSTEM = "d_final"`) 2026-05-21.

### Semantic holdout — single pass (48 cases, 32 dev / 16 heldout)

| Subtype | n | intent correct |
|---|---|---|
| route_end_time | 12 | 12/12 |
| full_route_listing | 12 | 12/12 |
| lateness_summary | 12 | 12/12 |
| movement_comparison | 6 | 6/6 |
| recompute | 6 | 5/6 |
| **overall** | **48** | **47/48 = 97.9%** |

Dev (32): 31/32 = 96.9%. Heldout (16): **16/16 = 100.0%**.

Single failure: **SH-41** (dev, subtype `recompute`, OBJ, gold=`objective_delta`). Predicted: `objective_value`. Adapter source: d1 (LLM schema validation error on 2 fields → fallback). C0 and D1 both return `objective_value` on this case.

D1 extrapolation on holdout: ~62% (based on Axis 3 heldout score). D-Final: **97.9%** overall, **100.0%** heldout.

---

### Pass^k on semantic holdout (k=5, n=48, total reps=240)

| Subtype | n | pass^k_all |
|---|---|---|
| route_end_time | 12 | **12/12** |
| full_route_listing | 12 | **12/12** |
| lateness_summary | 12 | **10/12** |
| movement_comparison | 6 | **6/6** |
| recompute | 6 | **3/6** |
| **overall** | **48** | **43/48 = 89.6%** |

pass@k_any (≥1 rep succeeds): **100.0% (48/48)**. Stable success: 43. Flaky: 5. Stable failure: **0**.

Heldout (16): stable_success=14, flaky=2 (SH-34, SH-48), stable_failure=0.

Schema valid rate: 71.2%. Adapter accept rate: 97.9%. Fallback rate: 2.1%. Mean LLM latency: 1135 ms. Mean prompt tokens: 745. Mean completion tokens: 75. LLM calls made: 34/48 holdout cases (71%). Estimated cost: ~$0.0275.

---

### Axis 3 live run (D-Final, hybrid_guarded, LLM live, 2026-05-22)

n=24.

| Metric | Value |
|---|---|
| intent_correct | **24/24 = 100.0%** |
| answerability_correct | 24/24 = 100.0% |
| behavior_class_correct | **24/24 = 100.0%** |
| evidence_precision | 0.3833 |
| evidence_recall | 0.4167 |
| warning_precision | 1.000 |
| warning_recall | 1.000 |

Behavior_class 24/24 **exceeds analytical prediction of 21/24**. LLM invocations: 8/24. Fallbacks: 0. Schema invalid: 0. Regressions vs D1: 0.

By subtype: cost_synonym 3/3, entity_synonym 5/5, feasibility_synonym 4/4, operator_colloquial 2/2, paraphrase 2/2, schedule_synonym 8/8 — all perfect.

Note on evidence P/R: Axis 3 stress cases inherit gold evidence paths from Run 2 base cases; the live evaluation does not rerun the full evidence extractor on stress cases. These values reflect path-matching on the stress subset, not an evidence regression.

---

### Run 2 core — full 60-case benchmark (2026-05-23)

_Updated result. Previously only 15 calibration cases were evaluated because `run_core()` hardcoded `default_cases_path()` (→ `run2_calibration_cases.csv`). Fixed by adding `benchmark_cases_path()` to `run2_case_loader.py` and updating `run_system_d_final.py` to use it. All 60 cases materialize from `experiment/results_RUN1/generator/full-run-v1.jsonl`._

**60/60 intent correct = 100.0%**

| Metric | Value |
|---|---|
| Cases | 60 |
| Intent accuracy | **100.0% (60/60)** |
| Regressions vs prior 15-case result | 0 |
| Adapter source: d1 | 57 |
| Adapter source: llm | 3 |
| Fallbacks | 0 |
| Mean LLM latency (when called) | 1348 ms |
| Total prompt tokens | 23,224 |
| Total completion tokens | 1,525 |

By family: OBJ 15/15, PLAN_VALIDITY 12/12, SCHEDULE 15/15, STRUCT 18/18.

LLM consulted on 3 cases (confidence ≥ 0.96 on all): R2-017 (`objective_delta`, 0.96), R2-018 (`objective_delta`, 0.98), R2-045 (`single_customer_route_membership`, 0.97). All correct.

`schema_valid=True` on 21/60 LLM-called cases; 39 cases used D1 directly (no LLM call, schema_valid=False by convention). Zero fallbacks on any of the 60 cases.

---

### Case details: SH-34, SH-48, SH-41

**SH-34** (heldout, `lateness_summary`, SCHEDULE):
- Single pass: intent_correct = **1** (predicted `lateness_summary`, confidence 0.94, source llm)
- Pass^k (k=5): **2/5 success** — flaky
- Root cause: genuine semantic ambiguity between `lateness_summary` and `feasibility_status` on prompt "Which customers won't be served within their window?" LLM oscillates at high confidence (0.93–0.97) across replicates. Not an infrastructure failure.

**SH-48** (heldout, `recompute`, OBJ, gold=`objective_delta`):
- Single pass: intent_correct = **1** (predicted `objective_delta`, confidence 0.90, source llm)
- Pass^k (k=5): **3/5 success** — flaky
- Root cause: intermittent schema validation failure → D1 fallback → D1 returns `objective_value`. In 3/5 reps LLM correctly returns `objective_delta` at 0.93–0.96 confidence. Infrastructure gap in schema normalizer.

**SH-41** (dev, `recompute`, OBJ, gold=`objective_delta`):
- Single pass: intent_correct = **0** (predicted `objective_value`, source d1 fallback)
- Pass^k (k=5): **1/5 success**
- Root cause: LLM schema validation error (2 errors) → fallback to D1. D1 returns `objective_value`. In successful reps, LLM returns `before_after_comparison` (0.91–0.96 confidence) or `objective_delta`. Pre-dates D-Final: C0 and D1 both fail on this case. D-Final changes the failure mode from `objective_value` (C0/D1) to `before_after_comparison` (LLM) in non-fallback reps.

---

### Artifact paths

| Artifact | Path |
|---|---|
| Holdout single-pass CSV | `product/evaluation/system_d_final/reports/d_final_semantic_holdout_report.csv` |
| Run 2 core CSV | `product/evaluation/system_d_final/reports/d_final_core_report.csv` |
| Axis 3 live report | `product/evaluation/system_d_final/reports/d_final_axis3_live.md` |
| Axis 3 live CSV | `product/evaluation/system_d_final/reports/d_final_axis3_live.csv` |
| Pass^k all-48 summary | `product/evaluation/system_d_final/passk/reports/d_final_passk_all48_k5_summary.md` |
| Pass^k heldout failure analysis | `product/evaluation/system_d_final/passk/reports/d_final_passk_heldout_k5_failure_analysis.md` |
| Closeout | `product/evaluation/system_d_final/reports/d_final_closeout.md` |
| Thesis framing | `product/evaluation/system_d_final/reports/thesis_framing_note.md` |

---

## 7. D5 and Verbalization

### D5 — Recompute execution

**Test suite:** `tests/product_api/test_recompute_api.py` — **23 test cases**.

**Coverage:** ui_actions emitted iff mode=needs_recompute; `/copilot/ask` never calls executor under any prompt; confirm required (400); unknown scenario (404); invalid/forbidden/mismatched action; recompute_not_recommended (409); action_mismatch (409); unimplemented deployable action → 501 (pins `run_nearest_neighbor`); run_reuse_direct against no-routes payload (400); `run_pyvrp_10s` success (skipped without pyvrp/vrplib); `run_reuse_direct` success (same skip); `run_clarke_wright` success + runtime artifacts + routes; `run_clarke_wright` honest infeasibility; `run_clarke_wright` rejects perturbation overlay (501); service-layer unit tests pinning allowed/implemented/forbidden sets.

**Regression:** `tests/product_api/` 52/52, `tests/system_d{1..4}/` 177/177.

#### Recompute action status

| Action | Implemented | Notes |
|---|---|---|
| `run_reuse_direct` | **yes** | Re-evaluates source payload routes via `evaluate_vrptw_solution`. ~50 ms. Returns 400 if payload has no routes. |
| `run_clarke_wright` | **yes** | Parallel-savings construction + VRPTW evaluation. ~100 ms. May return `feasible=False` honestly (no silent fallback). |
| `run_pyvrp_10s` | **yes** | Bounded PyVRP solve, seed=1, 10 s budget. |
| `run_nearest_neighbor` | **no** | Returns 501 `action_not_implemented`. |

Forbidden: `pyvrp_60s`, `run_pyvrp_60s`, `pyvrp_60s_seed2`, `pyvrp_60s_seed3` → HTTP 400 `forbidden_action`.

Implemented set reported in 501 response: `["run_clarke_wright", "run_pyvrp_10s", "run_reuse_direct"]`.

D5 is local/demo infrastructure: no cancellation, no streaming, no job queue, no auth/rate limiting. Runtime artifacts gitignored under `product/api/runtime/recompute_runs/`. Each request blocks the worker for up to ~12 s.

**Artifact paths:**
- Closeout: `product/evaluation/system_d5/reports/system_d5_closeout.md`
- API contract: `product/evaluation/system_d5/reports/api_recompute_contract.md`
- Tests: `tests/product_api/test_recompute_api.py`

---

### Verbalization faithfulness check

**n=24 cases, 100.0% pass (24/24).** Template-based deterministic renderer (`product/copilot/verbalization.py`), no LLM calls.

#### Results by behavior class

| Behavior class | n | Pass |
|---|---|---|
| direct_answer | 6 | 6/6 = 100.0% |
| direct_answer_with_warning | 6 | 6/6 = 100.0% |
| useful_refusal | 5 | 5/5 = 100.0% |
| partial_answer_with_warning | 3 | 3/3 = 100.0% |
| needs_recompute | 4 | 4/4 = 100.0% |

#### Headline metrics

| Metric | Value |
|---|---|
| Overall pass rate | **100.0% (24/24)** |
| Faithful to contract | 100.0% |
| Critical omission rate | 0.0% |
| Unsupported addition rate | 0.0% |
| Numeric/entity error rate | 0.0% |
| Warning preservation rate | 100.0% |
| Missing-field preservation rate | 100.0% |
| Compute-decision preservation rate | 100.0% |
| Failures | **0** |

Scope: this check tests rendering faithfulness only, not the contract itself. The structured contract is the primary evaluated artifact; this check verifies that the natural-language `answer_text` faithfully renders the already-correct contract object.

API integration: 24/24 verbalization validation cases passing, 71/71 product API tests passing.

**Artifact paths:**
- Design: `product/evaluation/verbalization_check/design.md`
- Cases: `product/evaluation/verbalization_check/verbalization_cases.csv`
- Summary: `product/evaluation/verbalization_check/reports/verbalization_summary.md`
- Raw: `product/evaluation/verbalization_check/reports/verbalization_raw.csv`
- Failures: `product/evaluation/verbalization_check/reports/verbalization_failures.md` (0 failures)
- Thesis framing: `product/evaluation/verbalization_check/reports/thesis_framing_note.md`
- API integration note: `product/evaluation/verbalization_check/reports/api_integration_note.md`

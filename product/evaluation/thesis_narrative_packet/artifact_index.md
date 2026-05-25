# Artifact Index — Thesis Narrative Packet

_All source reports used to produce the thesis narrative packet.
Grouped by phase. Frozen at HEAD `18b4811` (tag `run2-contract-extended`)._

---

## Run 2 Methodology

| Path | Purpose | Key numbers |
|---|---|---|
| `product/evaluation/run2_contract_benchmark_design.md` | R2-0 design doc: evaluation surface, systems under test, metrics, gold protocol, caveats | Three-axis decomposition × 4 claim families × 4 behavior classes; no composite |
| `product/evaluation/run2_gold_schema.md` | Strict 17-column gold row schema; §12 false-premise exception; §10a field-family evidence policy | 17 columns; predicate-pinned-path stripping rule |
| `product/evaluation/run2_benchmark_cases.csv` | Frozen 60-case benchmark (immutable from R2-2 onward) | 60 rows; OBJ=15 PV=12 SCHED=15 STRUCT=18 |
| `product/evaluation/run2_calibration_cases.csv` | Frozen 15-case calibration set | 15 rows; 9 current + 6 target_extension |
| `product/evaluation/run2_benchmark_case_notes.md` | Cluster rationale + corrections log (B-001..B-006; R2-038 R2-052 R2-057 R2-022) | 3 new prompts + 1 revision corrected in-flight |
| `product/evaluation/reports/run2_benchmark_expansion_report.md` | Expansion from 15 → 60 cases: distribution, balance, authoring log | 39 current + 21 target_extension |
| `product/evaluation/reports/run2_comprehensive_report.md` | End-to-end synthesis of all Run 2 stages (R2-0 → R2-6) | All headline numbers; primary reference |

---

## R2-3 Deterministic Contract

| Path | Purpose | Key numbers |
|---|---|---|
| `product/evaluation/reports/run2_extension_implementation_report.md` | Step-by-step implementation log for the 6 R2-3 contract extensions | 6 extension families; regression-clean after each step |
| `product/evaluation/reports/run2_contract_extension_thesis_summary.md` | Closeout summary; contains the verbatim thesis paragraph on the engineering-instrument finding | "benchmark used as engineering instrument" |
| `product/evaluation/reports/run2_benchmark_eval_system_c_extended.md` | 60-case C-extended evaluation results (Markdown) | intent/ans/beh 1.000; ev_prec 0.980; useful_refusal 18/18 |
| `product/evaluation/reports/run2_benchmark_eval_system_c_extended.csv` | Same data in machine-readable form | 60 rows × metrics |
| `product/evaluation/reports/run2_calibration_eval_system_c.md` | 15-case calibration C-current evaluation | current 1.000/1.000/1.000; target_ext 0.333 useful_refusal |
| `product/evaluation/reports/run2_benchmark_eval_system_c_current.md` | 60-case C-current evaluation (before R2-3 extensions) | overall beh 0.817; target_ext useful_refusal 0.000 |

---

## System B / A Baselines

| Path | Purpose | Key numbers |
|---|---|---|
| `product/evaluation/reports/run2_model_baseline_model_lock_openai_gpt54mini.md` | Model lock report: gpt-5.4-mini pinned to response `gpt-5.4-mini-2026-03-17` | Model alias snapshot confirmed |
| `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.md` | System B 60-case full run results | intent 0.950 ans 0.967 beh 0.917; ev P/R 0.771/0.902; 60/60 parsed |
| `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.csv` | Same data in machine-readable form | 60 rows |
| `product/evaluation/reports/run2_4a_final_report.md` | R2-4A summary: System B setup, quirks, headline shape, failure taxonomy | Over-citation + intent confusion + policy-warning omission |
| `product/evaluation/reports/run2_passk_subset.md` | Pre-registered 10-case pass^k subset | 5 target-ext + 5 current-fail cases |
| `product/evaluation/reports/run2_passk_gpt54mini_v1.md` | System B pass^k 10×5 results | pass^k_all 0.30; stable_success 3; stable_failure 5; flaky 2 |
| `product/evaluation/reports/run2_passk_gpt54mini_v1.csv` | Same data in machine-readable form | 10 rows × 5 replicates |
| `product/evaluation/reports/run2_5_final_report.md` | R2-5 summary: two findings (flaky vs stable failure) | B target-ext 2/5 flaky; B current 5/5 stable_failure |
| `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_smoke.md` | System A 5-case smoke on B-failed cases | 5/5 intent+ans correct; 2 precision misses (over-citation) |
| `product/evaluation/reports/run2_passk_system_a_gpt54mini_v1.md` | System A pass^k 10×3 results | pass^k_all 0.50; stable_success 5; stable_failure 3; flaky 2 |
| `product/evaluation/reports/run2_passk_system_a_gpt54mini_v1.csv` | Same data in machine-readable form | 10 rows × 3 replicates |
| `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_30case_v1.md` | System A 30-case stratified sampler | intent 1.000 ans 1.000 beh 0.933; useful_refusal 11/11 |
| `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_30case_v1.csv` | Same data in machine-readable form | 30 rows |
| `product/evaluation/reports/run2_system_a_final_report.md` | R2-6 summary: what prior fixes / doesn't fix | Prior fixes intent confusion + policy warnings; cannot fix evidence over-citation |

---

## Stress Axes

| Path | Purpose | Key numbers |
|---|---|---|
| `product/evaluation/run2_stress/shared/coordination_report.md` | Axis naming decisions; boundary audit; shared methodology status | Path B adopted; axis3 = paraphrase; 4 axes all C0-closed |
| `product/evaluation/run2_stress/shared/system_d_design_envelope.md` | Locked System D scope: intent.py only | Envelope definition |
| `product/evaluation/run2_stress/axis1_lookalike/reports/axis1_closeout.md` | Axis 1 C0 baseline closeout | intent 87.5%; 3 wrong_adjacent_intent (OBJ Band4); 18 guard_protected |
| `product/evaluation/run2_stress/axis1_lookalike/reports/c0_baseline.csv` | Axis 1 per-case wide results | 24 rows |
| `product/evaluation/run2_stress/axis1_lookalike/reports/scatter.csv` | Axis 1 shared scatter (long form) | 240 rows (24 × 10 metrics) |
| `product/evaluation/run2_stress/axis2_ood_premises/reports/axis2_closeout.md` | Axis 2 C0 baseline closeout | intent 75%; 4 wrong_intent + 2 unknown + 2 missed_false_premise + 5 schema_gap + 11 correct |
| `product/evaluation/run2_stress/axis2_ood_premises/reports/c0_baseline.csv` | Axis 2 per-case wide results | 24 rows |
| `product/evaluation/run2_stress/axis2_ood_premises/reports/scatter.csv` | Axis 2 shared scatter | 240 rows |
| `product/evaluation/run2_stress/axis3_semantic/reports/axis3_closeout.md` | Axis 3 C0 baseline closeout | intent 62.5%; 9 unknown_intent; conditional-on-correct ans/beh 100% |
| `product/evaluation/run2_stress/axis3_semantic/reports/c0_baseline.csv` | Axis 3 per-case wide results | 24 rows |
| `product/evaluation/run2_stress/axis3_semantic/reports/scatter.csv` | Axis 3 shared scatter | 240 rows (48 null-score for inapplicable metrics) |
| `product/evaluation/run2_stress/axis4_payload/reports/axis4_closeout.md` | Axis 4 C0/A/B closeout | C0 100% all; A ev_prec 0.667/0.567 (low/high); B ans 0.583 both bands |
| `product/evaluation/run2_stress/axis4_payload/reports/c0_baseline.csv` | Axis 4 C0 per-case results | 24 rows |
| `product/evaluation/run2_stress/axis4_payload/reports/system_a_baseline.csv` | Axis 4 System A per-case results | 24 rows; 18 model_projection_failure |
| `product/evaluation/run2_stress/axis4_payload/reports/system_b_baseline.csv` | Axis 4 System B per-case results | 24 rows; 24 model_projection_failure |
| `product/evaluation/run2_stress/axis4_payload/reports/stress_axis4_summary.md` | Combined C0/A/B Axis 4 summary | Per-(system×band×intent) breakdown; predicted-vs-observed delta |
| `product/evaluation/run2_stress/axis4_payload/reports/scatter.csv` | Axis 4 shared scatter (3 systems) | 720 rows (24 × 3 × 10) |

---

## Cross-Axis Synthesis

| Path | Purpose | Key numbers |
|---|---|---|
| `product/evaluation/run2_stress/analysis/cross_axis_synthesis.md` | Unified failure taxonomy across all 4 axes | 144 rows; 6 categories; 18 D-addressable; 70 must-not-regress |
| `product/evaluation/run2_stress/analysis/unified_scatter.csv` | Concatenated scatter (all axes + systems) | 1,440 rows |
| `product/evaluation/run2_stress/analysis/failure_map.csv` | Per-(case,axis,system) category + sub_label | 144 rows |
| `product/evaluation/run2_stress/analysis/failure_summary.csv` | Per-(axis,system,category) counts | Long-form aggregation |

---

## D1 / D2 / D3 / D4

| Path | Purpose | Key numbers |
|---|---|---|
| `product/evaluation/system_d1/reports/system_d1_closeout.md` | D1 closeout: semantic intent adapter | 18/18 target fixed; 70/70 must-not-regress; 0 core regressions; 64/96 guard-protected |
| `product/evaluation/system_d1/reports/system_d1_core_run2_report.md` | D1 on 60-case Run2 benchmark | All metrics identical to C0; 0 regressions |
| `product/evaluation/system_d1/reports/system_d1_stress_report.md` | D1 on all 4 stress axes | intent axis1 100% axis2 100% axis3 100% axis4 100% |
| `product/evaluation/system_d1/reports/system_d1_failure_map.csv` | Per-case D1 failure map | Residual: 3 route_indexing_ambiguity warning gaps |
| `product/evaluation/system_d2/reports/system_d2_closeout.md` | D2 closeout: answerability + warning extensions | 5/5 target fixed; 70/70 must-not-regress; 0 regressions; 0 over-fires |
| `product/evaluation/system_d2/reports/system_d2_core_run2_report.md` | D2 on 60-case Run2 benchmark | All metrics 1.000; identical to D1 |
| `product/evaluation/system_d2/reports/system_d2_stress_report.md` | D2 on all 4 stress axes | axis2+axis3 beh 1.000 |
| `product/evaluation/system_d2/reports/d2_d3_combined_summary.md` | Combined D2/D3 summary | D2→D3 progression table |
| `product/evaluation/system_d3/reports/system_d3_closeout.md` | D3 closeout: schema-v2 causal overlay | 5/5 v2 target fixed; 0 off-target causal emissions; 0 regressions |
| `product/evaluation/system_d3/reports/system_d3_core_run2_report.md` | D3 on 60-case Run2 benchmark | All 1.000; no causal phrase in any Run2 core prompt |
| `product/evaluation/system_d3/reports/system_d3_stress_report.md` | D3 on all 4 stress axes | axis2 beh 0.792 under v1 gold (expected); v2 overlay 5/5 |
| `product/evaluation/system_d3/axis2_causal_gold_overlay.csv` | Versioned v2 gold for 5 causal cases | 5 rows; causal_mechanism_unsupported warning expected |
| `product/evaluation/system_d4/reports/system_d4_closeout.md` | D4 closeout: compute-decision policy layer | 32/32 all metrics 1.000; D3 156-case regression all_fields_match_rate 1.000 |
| `product/evaluation/system_d4/reports/system_d4_decision_report.csv` | D4 per-case compute_decision detail | 32 rows; 6 modes |
| `product/evaluation/system_d4/reports/system_d4_core_run2_report.md` | D4 D3-regression on 156 cases | intent/ans/warnings/evidence/behavior/all_fields all 1.000 |
| `product/evaluation/system_d4/reports/api_contract_update.md` | Frontend/API contract note for compute_decision field | Enum semantics + frontend usage guide |

---

## API / Frontend Contract

| Path | Purpose | Key numbers |
|---|---|---|
| `product/api/API_FOR_FRONTEND.md` | REST API contract documentation for the frontend | Endpoint schemas; evidence field semantics |
| `product/evaluation/system_d4/reports/api_contract_update.md` | D4 additions to the API contract | compute_decision JSON shape; 6 modes; recommended_action ladder |

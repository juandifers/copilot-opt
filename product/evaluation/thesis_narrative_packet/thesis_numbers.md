# Thesis Numbers — Final Citable Values

_Compact reference for prose. All numbers are from frozen artifacts at
HEAD `18b4811` (tag `run2-contract-extended`). Source files are
listed for each entry. Caveats are editorial: they name the
scope limitation you must qualify in prose._

---

## Run 2 Core (Benchmark Engineering)

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 60 | Frozen benchmark cases (Run 2) | `run2_benchmark_cases.csv` | Intentionally narrow; does not generalise beyond these 60 cases |
| 39 / 21 | current vs target_extension partition | `run2_benchmark_cases.csv` | target_extension rows encode planned-but-unshipped behaviour; partition is bookkeeping, not a metric |
| 0.817 | C-current overall behavior_class accuracy before R2-3 extensions (n=60) | `run2_benchmark_eval_system_c_current.md` | Drops to 0.000 useful_refusal_correct on target_extension; gap is artificial — contract didn't implement those yet |
| 0.000 | C-current useful_refusal_correct on target_extension (n=21) before extensions | `run2_benchmark_eval_system_c_current.md` | Confirms instrument detects gaps, not that the contract is broken |
| 6 | Number of R2-3 contract extension families shipped | `run2_extension_implementation_report.md` | Each family targeted a pre-registered gap; no gold labels moved |
| 1.000 | C-extended intent / answerability / behavior_class on all 60 cases after R2-3 | `run2_benchmark_eval_system_c_extended.md` | Deterministic; 1.000 by construction for supported behaviors |
| 0.980 | C-extended overall evidence_precision (60 cases) | `run2_benchmark_eval_system_c_extended.md` | 0.969 on current partition; pre-existing PV feasibility_breakdown subkey mismatch in gold rubric; not a regression |
| 18/18 | C-extended useful_refusal_correct | `run2_benchmark_eval_system_c_extended.md` | Deterministic contract layer |
| 103 | Run 2 tests at R2-3 closeout | `run2_comprehensive_report.md` §5.2 | Grows to 139 by R2-6 end |

---

## System B (Prompt-Only LLM Baseline)

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 0.950 | System B intent_accuracy on 60 cases | `run2_model_baseline_b_openai_gpt54mini_v1.md` | Single sample; hides 2 flaky target-extension cases |
| 0.967 | System B answerability_accuracy on 60 cases | same | Single sample |
| 0.917 | System B behavior_class_accuracy on 60 cases | same | Single sample |
| 0.771 | System B evidence_precision on 60 cases | same | Main failure mode: evidence over-citation (adds identifier fields alongside answer field) |
| 60/60 | System B parsed with zero errors | same | gpt-5.4-mini-2026-03-17; max_completion_tokens quirk patched |
| 0.30 | System B pass^k_all on 10-case subset (k=5) | `run2_passk_gpt54mini_v1.md` | 10-case targeted subset; not a population estimate |
| 3 / 5 / 2 | B stable_success / stable_failure / flaky (k=5, n=10) | `run2_passk_gpt54mini_v1.md` | 5 stable failures are all from current-row failures |
| 0/5 | B current-row failures replicate as stable failures (none recovered at k=5) | `run2_passk_gpt54mini_v1.md` | Confirms failure modes are systematic not stochastic |

---

## System A (Deterministic Prior + Model Hybrid)

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 1.000 | System A intent_accuracy on 30-case sampler | `run2_model_baseline_a_openai_gpt54mini_30case_v1.md` | 30 cases; different denominator than B's 60 |
| 1.000 | System A answerability_accuracy on 30-case sampler | same | same caveat |
| 0.933 | System A behavior_class_accuracy on 30-case sampler | same | Route_indexing_ambiguity warning cases dominate residual misses |
| 0.50 | System A pass^k_all on 10-case subset (k=3) | `run2_passk_system_a_gpt54mini_v1.md` | vs B = 0.30 at k=5; k differs — qualitative direction is clear |
| 5 / 3 / 2 | A stable_success / stable_failure / flaky (k=3, n=10) | `run2_passk_system_a_gpt54mini_v1.md` | 2 recovered from B stable-failure (R2-040, R2-058) |
| +0.20 | A pass^k_all gain over B (0.50 vs 0.30) | `run2_comprehensive_report.md` | Different k (3 vs 5); A closes >50% of the B-to-C gap |

---

## B → A → C Reliability Spectrum

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 0.30 → 0.50 → 1.00 | pass^k_all gradient (B k=5 / A k=3 / C by construction) | `run2_comprehensive_report.md` §4.1 | Exactly the gradient the thesis claim predicts; k differs for B and A |
| R2-040 + R2-058 | Two B stable-failures recovered deterministically under A | `run2_comprehensive_report.md` §4.3 | Recovery mechanism: prior locks correct intent / false-premise warning; not general-purpose |
| R2-027 / R2-055 / R2-060 | Three B stable-failures that remain failures under A | same | Evidence over-citation and PV subkey gap that the prior surface does not constrain |

---

## Stress Axes (C0 Baselines)

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 4 | Number of R2-S stress axes | `run2_stress/shared/coordination_report.md` | Each axis probes a different failure mode; not independent samples |
| 24 × 4 = 96 | Total C0-only stress cases | per-axis closeouts | Diagnostic; case selection targets known gaps |
| 87.5% (21/24) | Axis 1 C0 intent accuracy on look-alike prompts | `axis1_closeout.md` | Heldout 91.7%; 3 failures all in one band (OBJ comparative attractor) |
| 3 | Axis 1 wrong_adjacent_intent failures (OBJ Band 4) | `axis1_closeout.md` | Confidently misrouted; contract produces plausible wrong answer with no warning |
| 18 | Axis 1 guard-protected cases (C0 guards held) | `axis1_closeout.md` | Customer-number guard + listing-phrase precedence + family-routing architecture |
| 75.0% (18/24) | Axis 2 C0 intent accuracy on OOD premise prompts | `axis2_closeout.md` | 11 correct_refusal; 6 intent failures (D-addressable); 5 schema gaps |
| 62.5% (15/24) | Axis 3 C0 intent accuracy on paraphrase prompts | `axis3_closeout.md` | Conditional on correct intent: ans/beh 100%; bottleneck is keyword classifier |
| 100% / 100% | Axis 4 C0 intent / answerability across 24 payload-scale cases | `axis4_closeout.md` | C0 has full structured payload; model-facing projection not exercised |

---

## Cross-Axis Synthesis

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 18 | System-D-addressable intent failures (all axes) | `cross_axis_synthesis.md` §4 | All 18 are intent-classifier misroutes; downstream would be correct if intent were right |
| 70 | Must-not-regress guard-protected cohort | `cross_axis_synthesis.md` §9 | System D must hold 70/70 perfect |
| 42 | Model-projection failures (Axis 4 A+B) | `cross_axis_synthesis.md` §3.1 | All out-of-C0-envelope; projection/evidence/warning-post-validation future work |
| 5 | Schema-gap cases (Axis 2 Band 4 causal) | `cross_axis_synthesis.md` §6 | Un-fixable under R2-1 schema; D3 ships v2 overlay fix |
| 2 | Out-of-envelope answerability failures | `cross_axis_synthesis.md` §5 | Both require answerability.py + refusal_policy.py change; D2 ships as out-of-scope wrappers |
| 46/96 → 64/96 | C0-only guard-protected before/after D1 (47.9% → 66.7%) | `system_d1_closeout.md` §11 | Matches the synthesis prediction exactly |

---

## System D Progression

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 18/18 | D1 fixed all system-D-addressable intent failures | `system_d1_closeout.md` §8 | Deterministic stress set, not population generalisation |
| 0 | D1 core Run 2 regressions | `system_d1_closeout.md` §9 | 60/60 identical to C0 on every metric |
| 5/5 | D2 fixed all D1-remaining answerability + warning failures | `system_d2_closeout.md` §5 | 2 missed_false_premise + 3 route_indexing_ambiguity warning gaps |
| 0 | D2 over-fires of widened false-premise or vehicle/truck regex | `system_d2_closeout.md` §9 | Requires explicit customer-N token; generic lateness/feasibility prompts never trigger |
| 5/5 | D3 fixed all causal schema-gap cases under v2 overlay gold | `system_d3_closeout.md` §5 | v2 overlay scoring only; under v1 gold these cases intentionally score ✗ |
| 0 | D3 off-target causal emissions | `system_d3_closeout.md` §10 | Causal detector requires "why / what caused" phrase |
| 1.000 | D4 all compute-decision metrics on 32-case set | `system_d4_closeout.md` §7 | Deterministic policy; 32 purpose-built cases; not a population benchmark |
| 1.000 | D4 D3-regression all_fields_match_rate on n=156 | `system_d4_core_run2_report.md` | D4 wrapper forwards every D3 field unchanged |
| 49 / 56 / 49 / 23 | D1 / D2 / D3 / D4 test counts | test suite `--collect-only` | Tests pin contracts; not a coverage metric for the product |
| 1176 | Total test suite size | `pytest --collect-only` | Full repo; 369 are run2-tagged |

---

## Integrity

| Number | Meaning | Source | Caveat |
|---|---|---|---|
| 0 | Protected-file modifications at HEAD 18b4811 | `validators.validate_no_protected_files_modified()` | 7 locked Run 2 files verified byte-identical |
| 139 | Run 2 tests at end of R2-6 | `run2_comprehensive_report.md` §5.2 | 103 at R2-3 + 36 added across R2-4A → R2-6 |
| 18b4811 | HEAD commit throughout R2-3 → R2-6 | git log | Pre-registration discipline; benchmark / gold / scorer unchanged |

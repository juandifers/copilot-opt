# Evaluation Case Taxonomy

_Authored 2026-05-21. Maps every named case set used in the thesis to its n,
unit of evaluation, purpose, and analytical role._

---

## 1. Stage A sufficiency cells

| Field | Value |
|---|---|
| **n** | 48 prompts × evaluated on Solomon-100 and Homberger-200 instances |
| **Unit** | Prompt × (family, sufficiency_level, scale) cell |
| **Sources** | 24 synthetic (template-derived) + 24 LLM-generated; locked at `preregistration-prompts-v1` |
| **Family distribution** | OBJ=12, PV=12, STRUCT=12, SCHEDULE=12 |
| **Stratification** | 2×2 per family: (suff_accept, suff_escal) × (Solomon-100, Homberger-200); SCHEDULE Homberger is escalate-only |
| **Purpose** | Primary experiment: test the four pre-registered claims (faithfulness ≥ 4/5, sufficiency direction, op-validity, cross-scale) |
| **Supports** | **Generalization** — the 48-prompt set is treated as a sample from the population of operator-style natural-language VRP queries; claims are population inferences under the pre-registered success criteria |

---

## 2. Run 2 locked 60 product-contract cases

| Field | Value |
|---|---|
| **n** | 60 |
| **Unit** | (prompt, gold contract row) — a 17-column gold row encoding expected intent, answerability, evidence fields, warnings, behavior class, useful-refusal verdict |
| **Family distribution** | OBJ=15, PV=12, SCHEDULE=15, STRUCT=18 |
| **Partition** | 39 current (implemented behavior) + 21 target_extension (planned but unshipped at R2-0) |
| **Source file** | `product/evaluation/run2_benchmark_cases.csv` — immutable from R2-2 onward |
| **Purpose** | Engineering benchmark for the deterministic payload contract; drives contract development (R2-3 extensions), baseline comparison (Systems B and A), and System D regression gate |
| **Supports** | **Regression** (0-regression gate for every System D layer), **implementation validation** (1.000 intent/answerability/behavior after R2-3 extensions) |

---

## 3. 15 materialized D-Final core subset

| Field | Value |
|---|---|
| **n** | 15 |
| **Unit** | Run 2 benchmark case whose payload was materialized from the local `full-run-v1` generator artifact |
| **How selected** | Cases whose generator JSONL record exists in `experiment/results_RUN1/generator/full-run-v1.jsonl`; all 60 require a complete experiment run to materialize |
| **Purpose** | D-Final regression check on the Run 2 benchmark using available payloads; proxy for the full 60-case check pending complete materialization |
| **Result** | 15/15 D-Final intent correct; 0 regressions |
| **Supports** | **Regression** (partial — covers materialized subset only); does NOT support generalization claims |

---

## 4. R2-S stress cases

| Field | Value |
|---|---|
| **n** | 96 total (4 axes × 24 cases each) |
| **Unit** | Stress prompt designed to probe a specific classifier/contract failure mode |
| **Axes** | Axis 1 (look-alike intents, 24), Axis 2 (OOD premises, 24), Axis 3 (semantic paraphrase, 24), Axis 4 (payload scale, 24) |
| **Systems evaluated** | C0 on all axes; System A and B additionally on Axis 4 |
| **Purpose** | Diagnostic: characterize C0 classifier failure modes, quantify guard-protection, identify which failures are system-D-addressable vs structural |
| **Key numbers** | C0 intent: Axis 1 87.5%, Axis 2 75.0%, Axis 3 62.5%, Axis 4 100%; 18 failures flagged as D-addressable; 70 guard-protected (must-not-regress cohort) |
| **Supports** | **Stress diagnosis** — not a population benchmark; cases were selected to target known gaps |

---

## 5. Cross-axis synthesis rows

| Field | Value |
|---|---|
| **n** | 144 rows in `failure_map.csv` (per-case × axis × system category assignments) |
| **Unit** | (case, axis, system) tuple with failure category and sub-label |
| **Source** | `product/evaluation/run2_stress/analysis/cross_axis_synthesis.md` and associated CSVs |
| **Purpose** | Unified failure taxonomy across all 4 axes; identifies the 18 D-addressable intent failures, 70 must-not-regress guard-protected cases, 42 model-projection failures, 5 schema-gap cases, and 2 out-of-envelope answerability failures |
| **Supports** | **Stress diagnosis** — analytical synthesis of R2-S stress results; directly motivates System D layer sequencing (D1 → D2 → D3 → D4) |

---

## 6. D3 schema-v2 overlay cases

| Field | Value |
|---|---|
| **n** | 5 |
| **Unit** | Axis 2 OOD case involving a causal premise; evaluated under versioned gold (v1 and v2) |
| **Source** | `product/evaluation/system_d3/axis2_causal_gold_overlay.csv` |
| **Gold versioning** | Under v1 gold, these cases intentionally score ✗ (causal mechanism not in schema). Under v2 gold, D3's `causal_mechanism_unsupported` warning is the expected output |
| **Purpose** | Validate the D3 schema extension: confirm the causal-unsupported warning fires exactly on causal premises and nowhere else (0 off-target emissions) |
| **Supports** | **Schema extension validation** — tests a specific contract vocabulary addition; not a generalization benchmark |

---

## 7. D4 compute-decision cases

| Field | Value |
|---|---|
| **n** | 32 |
| **Unit** | (prompt, payload + field flags, expected compute_decision) — covers 6 compute modes |
| **Source** | `product/evaluation/system_d4/reports/system_d4_decision_report.csv` |
| **Purpose** | Validate the deterministic compute-decision policy layer (cheap-accept, recompute-required, recompute-recommended, recompute-optional, recompute-infeasible, unknown) |
| **Result** | All metrics 1.000 on 32-case set; D3-regression on 156 cases all_fields_match_rate 1.000 |
| **Supports** | **Implementation validation** — deterministic policy; 32 purpose-built cases are not a population estimate |

---

## 8. D-Final semantic holdout

| Field | Value |
|---|---|
| **n** | 48 total (32 dev / 16 heldout) |
| **Unit** | Novel paraphrase prompt whose language form is outside D1's fixed phrase banks |
| **Split** | 32 dev (visible during D-Final development), 16 heldout (untouched until final evaluation run) |
| **Subtypes** | route_end_time (12), full_route_listing (12), lateness_summary (12), movement_comparison (6), recompute/objective_delta (6) |
| **Source** | `product/evaluation/system_d_final/semantic_holdout_cases.csv` |
| **Purpose** | Evaluate LLM semantic adapter on language forms that defeat D1; primary evidence that D-Final improves over the deterministic baseline for novel phrasing |
| **Result** | 47/48 overall (97.9%); heldout 16/16 (100%); D1 extrapolated baseline ~62% (from Axis 3 performance) |
| **Supports** | **Generalization** (to novel natural-language phrasings outside the D1 vocabulary); **regression** (via dev set); single failure (SH-41) is in the dev split |

---

## 9. D5 recompute / API cases

| Field | Value |
|---|---|
| **n** | No standalone case set; D5 is evaluated through the D4 regression surface |
| **Unit** | D5 (UI action enrichment, `product/api/copilot_service.py`) wraps D4 output; regression is verified via the D4 D3-regression run (156 cases, all_fields_match_rate 1.000) and the D-Final acceptance criterion "0 D4/D5 compute-decision regressions" |
| **Purpose** | Confirm that D5's UI action enrichment layer does not alter any upstream D4 field; validate that the API endpoint dispatches `d_final` correctly |
| **Supports** | **Regression** — D5 is verified via forwarding invariance, not a dedicated case benchmark; API dispatch correctness is covered by the test suite (40 pass, 2 live-gated skips) |

---

## Summary table

| Case set | n | Generalization | Regression | Stress diagnosis | Schema extension | Impl validation |
|---|---:|:---:|:---:|:---:|:---:|:---:|
| Stage A sufficiency cells | 48 | ✓ | | | | |
| Run 2 locked 60 cases | 60 | | ✓ | | | ✓ |
| 15 materialized D-Final core | 15 | | ✓ (partial) | | | |
| R2-S stress cases | 96 | | | ✓ | | |
| Cross-axis synthesis rows | 144 | | | ✓ | | |
| D3 schema-v2 overlay | 5 | | | | ✓ | |
| D4 compute-decision | 32 | | ✓ | | | ✓ |
| D-Final semantic holdout | 48 | ✓ | ✓ | | | |
| D5 recompute / API | (via D4) | | ✓ | | | ✓ |

# Sufficiency Benchmark → Run 2 Payload Contract Bridge

_Conceptual bridge between the Stage A / sufficiency benchmark design and the
Run 2 product-contract benchmark. Shows how each Stage A construct maps onto
the Run 2 evaluation surface, enabling a single thesis narrative that runs
from benchmark through closing experiment through contract evaluation._

---

## 1. Why a bridge is needed

Stage A operationalises claim families as **structured label computations**
against solver outputs. The question is binary: is the cheap action's output
close enough to the reference for the claim family the operator is asking about?

Run 2 operationalises the same claim families as **product-contract fields**
emitted by the copilot's structured response object (`intent`, `answerability`,
`evidence`, `missing_fields`, `warnings`, `behavior_class`). The question is:
does the contract's structured response accurately and completely describe what
the payload supports — and does it handle edge cases (false premises, missing
comparators, causal questions) with the right policy?

The two benchmarks share the same four claim families and the same three-axis
decomposition. The bridge below shows the specific field-level mappings.

---

## 2. Claim Family → Product Intent Mapping

Stage A's four claim families map onto Run 2's `intent` enum as follows:

| Stage A claim family | Stage A canonical question | Run 2 intent(s) | Mapping rationale |
|---|---|---|---|
| **OBJ** | "What is the new total cost? / How much does cost change?" | `objective_value`, `objective_delta` | The distinction (value vs delta) is Stage A's OBJ loss vs the before-after framing. In Run 2, `objective_delta` requires a comparison payload; `objective_value` does not. Axis 1 stress tests (`A1D-11`, `A1D-12`, `A1H-11`) confirm the classifier is brittle to surface attractor tokens. |
| **PLAN_VALIDITY** | "Is the plan still feasible? / Can we keep using this plan?" | `feasibility_status`, `before_after_comparison` | `feasibility_status` maps directly. `before_after_comparison` handles the "what changed in feasibility" variant. Run 2 Axis 2 Band 2 (unsupported movement) and Band 3 (missing comparator) are the OOD stress surface for PV-adjacent questions. |
| **STRUCT** | "Which customers move? / Are the same customers still served together?" | `single_customer_route_membership`, `same_route_boolean`, `full_route_listing`, `new_customer_assignment`, `before_after_comparison` | STRUCT splits into five Run 2 intents depending on whether the question asks about one customer, a pair, the full listing, a new-customer, or a before-after comparison. The `full_route_listing` intent was added in R2-3. |
| **SCHEDULE** | "When will deliveries arrive? / Whose schedules slip?" | `customer_arrival`, `route_end_time`, `lateness_summary` | SCHEDULE maps onto three Run 2 intents by granularity: per-customer arrival time, per-route finish time, or aggregate lateness summary. Axis 3 (paraphrase stress) shows C0's keyword classifier is brittle on SCHEDULE vocabulary (`when does vehicle 1 close out?` → `unknown`). |

**Note on intent size:** Run 2 has 14 intents total; Stage A has 4 claim
families. The Run 2 intents subdivide each Stage A family by query shape,
not by claim content. The same Stage A OBJ-loss cell could produce either
`objective_value` or `objective_delta` depending on whether the operator
asks "what is the cost" or "how did the cost change."

---

## 3. Sufficiency → Answerability / Missing Fields / Warnings

Stage A's sufficiency label (`band == easy`) collapses a rich payload-state
question into a binary. Run 2's contract decomposes that same question into
the multi-field answerability + evidence + missing-fields machinery:

| Stage A concept | Run 2 contract field(s) | Mechanism |
|---|---|---|
| **Sufficient = easy** (the cheap action's output is close to reference) | `answerability == "answerable"`, `behavior_class == "direct_answer"` or `"direct_answer_with_warning"` | The payload carries the evidence to answer the question. No missing fields, no refusal. |
| **Sufficient but OOD/unsupported premise** | `answerability == "not_answerable"`, `behavior_class == "useful_refusal"`, `warnings ∋ "false_premise_detected"` or `"comparison_referent_ambiguity"` | The payload would be sufficient for the canonical intent, but the user's premise is wrong (false entity, missing comparator). Run 2 R2-3 extensions ship these cases. |
| **Insufficient = medium/hard** (cheap action diverges from reference) | `answerability == "partially_answerable"`, `behavior_class == "partial_answer_with_warning"`, `missing_fields` populated | The payload is present but incomplete for the question. The contract must surface what is missing, not just refuse. |
| **Action infeasible (PV failure)** | `answerability == "not_answerable"`, `warnings ∋ "false_premise_detected"` (for non-existent entity) or `missing_fields ∋ "use_validity_payload"` | Run 2 R2-3 extension: when the payload's plan is infeasible, the contract signals the operator to reload with a validity payload. |
| **Missing comparator (OBJ delta without baseline)** | `answerability == "partially_answerable"`, `warnings ∋ "comparison_referent_ambiguity"`, `next_actions ∋ "expose_reference_solution_objective"` | Run 2 R2-3 extension: `comparison_referent_ambiguity` fires when the operator asks for a delta but the payload has no baseline objective. |
| **Units mismatch (OBJ without units)** | `warnings ∋ "evidence_units_missing"`, `next_actions ∋ "expose_units_objective"` | Run 2 R2-3 extension: the contract warns about the solver's objective units when the payload's unit field is missing. |

**Bridge summary:** Stage A's `band == easy` ↔ Run 2's `answerable + direct_answer`;
Stage A's `band == hard` + feasibility failure ↔ Run 2's `not_answerable + useful_refusal`;
Stage A's `band == medium/hard` without infeasibility ↔ Run 2's `partially_answerable + partial_answer_with_warning`.

---

## 4. Recompute Routing → D4 Compute Decision

Stage A's policy gate (`accept_cheap` vs `escalate_to_pyvrp_10s`) is the
direct precursor of D4's `compute_decision` field. The mapping:

| Stage A policy outcome | D4 `compute_decision.mode` | D4 `recommended_action` |
|---|---|---|
| `accept_cheap` (P ≥ threshold) | `answer_from_payload` | `none` |
| `escalate_to_pyvrp_10s` (P < threshold) + recompute framing | `needs_recompute` | `run_pyvrp_10s` |
| `escalate_to_pyvrp_10s` + reuse-direct framing | `needs_recompute` | `run_reuse_direct` |
| Comparison payload required (no reference objective in payload) | `needs_comparison_payload` | — |
| Causal question (SCHEDULE STRUCT "why") | `partial_from_payload` | — |
| Unsupported or out-of-schema concept | `unsupported` | — |
| Hedged inquiry ("can you improve?") | `clarification_needed` | — |

**Key difference:** D4 is deterministic (rule-based phrase triggers), while
Stage A's gate is a learned probabilistic model. D4's design doc (§3) explicitly
documents this as a stepping stone: a future `learned_d4_v2` would adapt the
Stage A feature set (`predictor_models/features.py`) to contract-payload
features and re-train per-family gates.

**Why pyvrp_60s is absent from D4.** Stage A uses `pyvrp_60s_reference` as a
label-generating reference only — not a deployable rung. D4 inherits that
framing: the `run_pyvrp_10s` action is the top deployable rung; `pyvrp_60s`
is intentionally absent from the recommended-action enum.

---

## 5. Three-Axis Decomposition → Run 2 Metrics

| Stage A axis | Run 2 operationalisation |
|---|---|
| **Faithfulness** | Not graded on the contract (Run 2 grades the structured response object, not the rendered text). Faithfulness lives in the closing experiment (spec.md) and is out of Run 2's scope by design. |
| **Sufficiency** | Operationalised via `answerability_accuracy` + `missing_field_recall`. A contract that marks a question as `answerable` when the payload does not support it fails sufficiency. A contract that marks it `partially_answerable` but misses which fields are missing also fails. |
| **Operational validity** | Operationalised via `behavior_class_accuracy` + `useful_refusal_correct` + `partial_answer_correct`. A contract that emits the wrong behavior class — e.g., `direct_answer` when the situation calls for `useful_refusal` — fails operational validity. |

The **three-axis decoupling property** from Stage A also appears in Run 2:

- A contract can be faithful (correct intent, correct evidence paths) yet
  operationally invalid (wrong behavior class) — e.g., R2-040 / R2-051
  under System B: intent is wrong, but the payload fields are present and
  evidence recall is fine.
- A contract can be operationally valid (correct answerability, correct
  behavior class) yet insufficient (evidence precision < 1.0) — e.g., the
  persistent evidence-over-citation in System A/B on Axis 4 payloads.

---

## 6. Stage A → Run 2 Claim Family Distribution Reconciliation

Stage A generates 3,584 cells across 4 families and 4 perturbation families.
Run 2's 60-case benchmark distributes differently because it is a targeted
contract-evaluation instrument, not a sufficiency-rate survey:

| Family | Stage A long-row rate | Run 2 case count | Run 2 intent coverage |
|---|---:|---:|---|
| OBJ | 25% (by construction) | 15 (25%) | `objective_value`, `objective_delta` |
| PLAN_VALIDITY | 25% | 12 (20%) | `feasibility_status`, `before_after_comparison`, `single_customer_route_membership` |
| STRUCT | 25% | 18 (30%) | `full_route_listing`, `single_customer_route_membership`, `same_route_boolean`, `new_customer_assignment`, `before_after_comparison` |
| SCHEDULE | 25% | 15 (25%) | `customer_arrival`, `route_end_time`, `lateness_summary` |

The STRUCT over-representation in Run 2 (18 vs 15) reflects the larger
number of STRUCT intents — the contract design needs coverage of
membership, listing, same-route, new-customer, and before-after all in
the STRUCT family.

---

## 7. Benchmark Lineage (for the thesis narrative)

```
CVRP v0.5 (PREREG_v0.5.md)
  │  Establishes: three-axis decomposition, claim families (OBJ/PV/STRUCT/RANK),
  │  sufficiency labels, perturbation design, action portfolio, reference protocol.
  │  Finding: STRUCT is noise-dominated on CVRP (Uchoa-X struct_unstable ≈ 0.926).
  ↓
VRPTW Stage A (PREREG_v1.0–v1.2_vrptw.md)
  │  Replaces RANK with SCHEDULE. Redefines PLAN_VALIDITY as substantive.
  │  VRPTW struct_unstable ≈ 0.167–0.194 (usable signal).
  │  Trains per-family HistGB sufficiency predictor; locked deployment_config.
  │  56 Solomon-100 instances × 16 perturbations × 4 families = 3,584 cells.
  ↓
Closing experiment (spec.md, preregistration-v1 tag)
  │  Puts the locked predictor in the loop with an LLM (Haiku 4.5 generator,
  │  Sonnet 4.6 judge). 48 prompts × 2×2 stratification.
  │  Measures three-axis decomposition on natural-language prompts.
  ↓
Run 2 product-contract benchmark (run2_contract_benchmark_design.md)
  │  Shifts evaluation from natural-language answers to the structured
  │  contract object. 60 frozen cases × 17-column gold schema.
  │  R2-3: 6 contract extensions close the target_extension gaps.
  │  R2-4A–R2-6: System B/A baselines + pass^k reliability.
  ↓
R2-S stress axes (run2_stress/axis1–4)
  │  4 axes × 24 cases = 96 C0 stress cases.
  │  Cross-axis synthesis identifies 18 D-addressable intent failures,
  │  70 must-not-regress, 42 model-projection failures (Axis 4).
  ↓
System D progression (D1 → D2 → D3 → D4)
     D1: semantic intent adapter fixes 18/18 intent failures.
     D2: answerability + warning extensions fix 5/5 remaining failures.
     D3: schema-v2 causal overlay fixes 5/5 schema-gap cases.
     D4: compute-decision policy layer (32-case evaluation); bridges
         back to Stage A's routing gate concept with a deterministic
         rule-based implementation.
```

---

## 8. Source Index

| Source | What it contains for this bridge |
|---|---|
| `spec.md` | Closing experiment design; pipeline diagram; claim-family classifier; three-axis rubric; pre-registered claims |
| `prereg/PREREG_v1.2_vrptw.md` | Claim family definitions (§3); sufficiency labels (§3.3); perturbation grids (§6); action set (§7); reference protocol (§8); schema (§4) |
| `src/vrp_copilot_bench/labels.py` | `compute_losses_and_bands` — loss formula implementations for OBJ/PV/STRUCT/SCHEDULE; band thresholds |
| `reports/predictor_models/README.md` | HistGB/C_clean results; deployment configuration; feature importance; non-monotone preservation; framing decision (Outcome A) |
| `reports/predictor_models/deployment_config.csv` | Per-family locked thresholds; correctness / coverage / precision at deployment |
| `reports/predictor_baselines/README.md` | Baseline policies (`cheap_only`, `always_pyvrp_10s`, `block_rule_policy`, `oracle`); headline numbers; cheap-action rule per perturbation family |
| `product/evaluation/run2_contract_benchmark_design.md` | Run 2 evaluation surface; intent enum; product contract schema |
| `product/evaluation/run2_gold_schema.md` | 17-column gold schema; field-family evidence policy; false-premise exception §12 |
| `product/evaluation/system_d4/reports/system_d4_closeout.md` | D4 compute-decision policy; mode enum; recommended-action ladder; pyvrp_60s exclusion rationale |
| `product/evaluation/system_d4/design.md` | D4 relationship to Stage A predictor (§3); why learned_d4_v2 is future work (feature-set adaptation required) |
| `product/evaluation/run2_stress/analysis/cross_axis_synthesis.md` | Unified failure taxonomy; system-D-addressable intent cases; must-not-regress cohort |

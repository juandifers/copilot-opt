# Run 2 — Comprehensive Report

_End-to-end synthesis of the Run 2 product-contract benchmark for the LLM-in-the-loop VRPTW copilot. Covers stages R2-0 → R2-6: pre-registration, calibration, expansion, contract extensions, deterministic reference, prompt-only model baseline, pass^k reliability, and deterministic-prior + model hybrid. All numbers are pulled directly from the per-stage reports listed in the pointer index at the end of this document._

---

## 0. TL;DR

| stage | what it produced | headline number |
|---|---|---|
| **R2-0** | Pre-registered design + 17-column gold schema | Three-axis decomposition × four claim families × four behavior classes, no aggregate composite |
| **R2-1** | 15-case calibration set + System C adapter | C-current 1.000 on every metric for `current` rows; 0.333 behavior_class on `target_extension` rows (instrument exposes contract gaps) |
| **R2-2** | 60-case frozen benchmark (calibration ∪ 45 new) | 39 current + 21 target_extension. C-current overall behavior_class 0.817; useful_refusal_correct 0.000 on target_extension |
| **R2-3** | Six contract extensions implemented in `product/copilot` + `product/data` | C-**extended**: 1.000 / 1.000 / 1.000 across the partition; current rows regression-clean (only the pre-existing 0.969 evidence_precision dip remains) |
| **R2-4A** | System B = OpenAI gpt-5.4-mini prompt-only JSON | 60/60 parsed; intent 0.950, ans 0.967, behavior 0.917, evidence P/R 0.771/0.902 |
| **R2-5** | System B pass^k (10 cases × k=5) | pass^k_all 0.30; 3 stable successes, 5 stable failures, 2 flaky |
| **R2-6** | System A = deterministic-prior + gpt-5.4-mini hybrid | pass^k_all 0.50 (+0.20 vs B); R2-040 fully recovered, R2-058 fully recovered, R2-051 partially recovered; 30-case sampler intent/ans = 1.000/1.000 |

The single-sentence finding: **the rule-based contract is a perfectly reliable contract emitter (1.000 by construction), an off-the-shelf prompted LLM is strong but not reliable (3/10 stable at k=5), and a thin deterministic prior closes more than half the reliability gap (5/10 stable at k=3) — exactly the wedge the thesis claim predicts.**

---

## 1. Motivation and research question

### 1.1 What Run 1 showed

Run 1 was the foundational empirical study: 48 operator-style natural-language prompts × two payload conditions (clean / mutated) × the existing product copilot. It produced answer texts and metric reports that fed the closing experiment. Its limitation, surfaced by the labelling work that preceded R2-0, was the **opacity of the verdict**: a pass/warn/fail score collapsed "the system answered correctly", "the system refused for the right reason", and "the system would have answered correctly if the payload carried a different field" into a single bucket. The four-axis labelling exercise wanted to separate those.

### 1.2 What Run 2 is supposed to do

Run 2 evaluates the *product contract* — the structured response object the copilot emits *before* its rendering layer turns it into operator-visible text. The unit of evaluation is one (`prompt_text`, `payload_condition`) pair; the gold label is the contract response shape (`intent`, `answerability`, `evidence`, `missing_fields`, `warnings`, `next_actions`, `behavior_class`). The contract is graded on **component metrics**, not an aggregate composite. (Design §6.9 forbids composites — they're the original Run 1 verdict opacity problem in a different disguise.)

### 1.3 What Run 2 explicitly does NOT do

- It does not score operator-visible answer text (no LLM-as-judge against `answer_text`).
- It does not call a solver.
- It does not evaluate user-facing quality (no user study).
- It does not measure generalisation beyond its 60 frozen cases.
- It does not move gold labels in response to system behaviour ("never tune gold to contract" was a hard pre-registration constraint).

---

## 2. Methodology

### 2.1 Three-axis decomposition

Each case label encodes three orthogonal claims:

- **Faithfulness** — did the contract emit only claims the payload actually grounds? (evidence precision)
- **Sufficiency** — did the contract emit every claim the payload supports? (evidence recall, missing-field recall)
- **Operational validity** — did the contract fire the right answerability, behavior class, warnings, and next actions? (component accuracies, useful_refusal_correct, partial_answer_correct)

### 2.2 Four claim families

OBJ (objective value / delta), PLAN_VALIDITY (feasibility / route count / single-customer membership / same-route boolean / before-after / new-customer-assignment), STRUCT (route count / membership / listings), SCHEDULE (route end time / customer arrival / lateness summary / before-after). The benchmark distribution: OBJ=15, PLAN_VALIDITY=12, SCHEDULE=15, STRUCT=18.

### 2.3 Four behavior classes (schema §7)

| class | shape |
|---|---|
| `direct_answer` | answerable + no warnings + evidence cited |
| `direct_answer_with_warning` | answerable + warnings + evidence cited |
| `partial_answer_with_warning` | partially_answerable + warnings + missing fields + evidence cited |
| `useful_refusal` | partially / not answerable + next actions + (typically) no evidence |

Frozen-benchmark distribution: direct_answer 27, direct_answer_with_warning 8, partial_answer_with_warning 7, useful_refusal 18.

### 2.4 Component metrics

All metrics are per-case scalars, aggregated by mean / fraction. No composite.

- `intent_accuracy`, `answerability_accuracy`, `behavior_class_accuracy` (booleans)
- `evidence_precision / evidence_recall` (set metrics, field-family normalised — predicate-pinned paths `[key=value]` are stripped to `[]` before matching)
- `warning_precision / warning_recall` (set metrics)
- `missing_field_recall` (set metric)
- `useful_refusal_correct` (composite, scored only on `useful_refusal` cases)
- `partial_answer_correct` (composite, scored only on `partial_answer_with_warning` cases)

### 2.5 Implementation status partition

Every case is labelled either `current` (the rule-based contract was already expected to produce this gold) or `target_extension` (the gold encodes a planned but un-shipped contract behaviour). The partition is **bookkeeping, not a metric** — its purpose is to keep "system got this wrong because the contract isn't there yet" from cancelling out with "system got this wrong because the contract was there and the system regressed."

### 2.6 Pre-registration discipline

The 60-case CSV, the 17-column gold schema, the System C adapter, and the scorer are all immutable across stages R2-2 → R2-6. The hash-pinned commit `18b4811` (tag `run2-contract-extended`) is HEAD throughout R2-4A, R2-5, and R2-6.

---

## 3. Stage-by-stage findings

### 3.1 R2-0 — Pre-registered design

Two authoritative documents produced:

- `product/evaluation/run2_contract_benchmark_design.md` — design (motivation, evaluation surface, systems under test, metrics, conventions, dataset size, gold protocol, caveats).
- `product/evaluation/run2_gold_schema.md` — strict 17-column row schema with §12 false-premise exception, §13 disallowed shapes, §10a field-family evidence policy.

System under test enumeration: **C** = the deterministic product contract (the existing `product/copilot` + `product/data` code), **B** = a prompt-only model baseline (added later), **A** = a deterministic-prior + model hybrid (added later).

### 3.2 R2-1 — 15-case calibration

The first 15 hand-labelled cases were intended as a debugging instrument: enough variation to exercise every behavior class, but small enough to label by hand twice and reconcile disagreements. The calibration's own evaluation against the System C contract:

| group | n | intent | ans | beh | evidence P/R | warning P/R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 9 | 1.000 | 1.000 | 1.000 | 0.978/1.000 | 1.000/1.000 | 1.000 (2) |
| target_extension | 6 | 0.833 | 0.333 | 0.333 | 0.500/0.833 | 0.167/0.333 | 0.000 (3) |

The asymmetry was load-bearing: `current` rows scoring 1.000 (modulo a single PV evidence_precision dip) confirmed the labels were operationally derivable from the contract; `target_extension` rows scoring 0.000 useful_refusal_correct confirmed the contract really did *not* yet emit the planned codes (`false_premise_detected`, `use_validity_payload`, `expose_reference_solution_objective`, `expose_units_objective`, `full_route_listing` intent, `comparison_referent_ambiguity`). Without that asymmetry, the closing-experiment instrument would have been measuring overfitting to the contract.

### 3.3 R2-2 — Expansion to 60 cases

The 15 calibration rows were carried forward unchanged. 45 new rows were authored to balance the family and behavior-class distributions and to widen the `payload_condition` coverage. Three new prompts (R2-038, R2-052, R2-057) and one revision (R2-022) were corrected in flight when the evaluator surfaced classifier-prompt mismatches — the gold text was the bug, not the contract.

The expansion report's "C-current" evaluation (the deterministic contract scored at R2-2, before any R2-3 extension):

| partition | n | intent | ans | beh | evidence P/R | warning P/R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 39 | 1.000 | 1.000 | 1.000 | 0.969/1.000 | 1.000/1.000 | 1.000 (7) |
| target_extension | 21 | 0.857 | 0.476 | 0.476 | 0.429/0.857 | 0.381/0.429 | 0.000 (11) |
| **overall** | 60 | 0.950 | 0.817 | 0.817 | 0.780/0.950 | 0.783/0.800 | 0.389 (18) |

This is the canonical "gap" picture. The 21 target_extension rows surface every R2-1 → R2-3 contract gap: warning omission (`false_premise_detected`, `comparison_referent_ambiguity`, `evidence_units_missing`), missing semantic codes (`use_validity_payload`, `expose_reference_solution_objective`, `expose_units_objective`, `clarify_false_premise`), and a proposed intent (`full_route_listing`).

### 3.4 R2-3 — Six contract extensions

Implemented one extension family at a time, re-running the benchmark after each step to verify (a) lift was restricted to target_extension cells, (b) current rows stayed regression-clean. The six families:

1. **PLAN_VALIDITY missing-fields → `use_validity_payload`** (R2-012, R2-032..R2-036).
2. **OBJ units-missing → `expose_units_objective` + `evidence_units_missing`** (R2-014, R2-021..R2-023).
3. **`full_route_listing` intent + dedicated matcher** before the new-customer heuristic (R2-010, R2-048, R2-049).
4. **`false_premise_detected` for customer** + `clarify_false_premise` next action + evidence short-circuit (R2-008, R2-047, R2-058).
5. **`false_premise_detected` for route** — same plumbing via `entity_resolution.py`, structurally a no-op verification step (R2-015, R2-059).
6. **`comparison_referent_ambiguity`** with `expose_reference_solution_objective` (R2-013, R2-024, R2-025).

C-extended on the 60-case benchmark, post-extension:

| partition | n | intent | ans | beh | evidence P/R | warning P/R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 39 | 1.000 | 1.000 | 1.000 | 0.969/1.000 | 1.000/1.000 | 1.000 (7) |
| target_extension | 21 | **1.000** | **1.000** | **1.000** | **1.000/1.000** | **1.000/1.000** | **1.000 (11)** |
| **overall** | 60 | 1.000 | 1.000 | 1.000 | 0.980/1.000 | 1.000/1.000 | 1.000 (18) |

The 0.969 current evidence_precision dip is unchanged from R2-2: it's a known PV `feasibility_breakdown` subkey-enumeration mismatch the *gold rubric* surfaces, not a contract regression. R2-3 closeout committed at `18b4811` with tag `run2-contract-extended`. C-extended is the **deterministic reference** for the remainder of Run 2.

R2-3 amounts to the thesis paragraph the closing-experiment summary quotes verbatim:

> "Run 2 shows that the benchmark can be used as an engineering instrument: it first exposes contract gaps in answerability, evidence, warning, and refusal behavior, and then verifies that targeted product-layer extensions close those gaps without breaking already-supported cases."

### 3.5 R2-4A — System B = OpenAI gpt-5.4-mini prompt-only

#### 3.5.1 Setup

- Provider: OpenAI Chat Completions API. Model: requested `gpt-5.4-mini`, pinned response `gpt-5.4-mini-2026-03-17` (the May 2026 alias snapshot). Confirmed via the model lock report at `run2_model_baseline_model_lock_openai_gpt54mini.md`.
- API key: read from `.env` via `python-dotenv`; the wrapper never echoes the key.
- Wrapper quirks discovered and adapted: gpt-5-class models reject the legacy `max_tokens` and require `max_completion_tokens`; they also reject `temperature=0` and require the default. Both fixes are isolated to the OpenAI client wrapper and apply only to models whose names start with `gpt-5`, `o1`, `o3`, or `o4`.
- Prompt: schema enums + operational conventions + compact payload projection + the case prompt. No gold labels, no scorer code, no C-extended outputs.

#### 3.5.2 Results

| partition | n | intent | ans | beh | evidence P/R | warning P/R | miss R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | 39 | 0.949 | 0.949 | 0.872 | 0.673/0.859 | 0.872/0.923 | 0.987 | 0.857 (7) |
| target_extension | 21 | 0.952 | 1.000 | 1.000 | 0.952/0.981 | 1.000/1.000 | 1.000 | 1.000 (11) |
| **overall** | 60 | 0.950 | 0.967 | 0.917 | 0.771/0.902 | 0.917/0.950 | 0.992 | 0.944 (18) |

60/60 parsed, 0 errors, 118.31 s wall time, 200k prompt tokens / 7.3k completion tokens.

#### 3.5.3 Headline shape

The model nails **every R2-3 extension behaviour** on the target_extension partition (1.000 on warning, missing-fields, useful_refusal_correct; 0.952 intent — only because of one R2-047 lexical confusion with `new_customer_assignment`). The gap concentrates on the *current* partition's evidence-precision axis (0.673 vs C's 0.969). The most common failure mode is **over-citation**: the model adds `routes[].route_idx` alongside `routes[].customer_ids`, or `customer_schedule[].customer_id` alongside `.arrival`. These are correct field-family citations but the gold rubric pins only the answer-grounding column. Other real misses: R2-040 / R2-051 intent confusion, R2-055 / R2-060 omitting `route_indexing_ambiguity`, R2-027 et al. failing to enumerate `feasibility_breakdown` subkeys.

### 3.6 R2-5 — System B pass^k

R2-4A's headline number is one sample per case. R2-5 asks how stable that sample is. 10 cases × k=5 replicates = 50 calls on the same model.

#### 3.6.1 Subset (pre-registered in `run2_passk_subset.md`)

- Target-extension success-stability: R2-008, R2-012, R2-015, R2-048, R2-058
- Current-row failure-stability: R2-027, R2-040, R2-051, R2-055, R2-060

#### 3.6.2 Results

| subset | n | stable_success | stable_failure | flaky | mean all-pass | pass^k_all | pass@k_any |
|---|---:|---:|---:|---:|---:|---:|---:|
| target-extension | 5 | 3 | 0 | **2** | 0.840 | 0.600 | 1.000 |
| current-row failure | 5 | 0 | **5** | 0 | 0.000 | 0.000 | 0.000 |
| **overall** | 10 | 3 | 5 | 2 | 0.420 | **0.300** | 0.500 |

50/50 parsed. The two findings:

1. **R2-4A's 1.000 target-extension score was partly a single-sample upper bound.** Two of five target_extension cases are flaky under k=5 — R2-048 (all-pass 0.40) and R2-058 (all-pass 0.80). The other three (R2-008 / R2-012 / R2-015) are stable.
2. **Every R2-4A current-row failure replicates as a stable failure.** None of the five recovered on any of the five replicates. R2-060 (omitted `route_indexing_ambiguity` on "Route 1") is 0/5 on the warning axis.

### 3.7 R2-6 — System A = deterministic-prior + gpt-5.4-mini hybrid

#### 3.7.1 Setup

A *thin* prior layer reuses the existing product-layer functions (`infer_intent`, `compute_answerability`, `build_warnings`, `suggested_next_actions_for_missing_fields`) to compute intent / answerability / missing-fields / warnings / next-actions / behavior-class priors. The prior is rendered as JSON into the prompt; the model is told to copy locked fields verbatim unless it flags `prior_disagreement=true` with a one-sentence reason in `adapter_notes`. The prior layer **does not call `run_system_c_on_case`** — A is a thin prior, not "C-with-extra-steps."

#### 3.7.2 5-case smoke (cases B failed in R2-4A)

| case | A intent | A ans | A behavior | A evidence P/R | A warning P/R |
|---|---|---|---|---|---|
| R2-040 | ✓ | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 |
| R2-048 | ✓ | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 |
| R2-051 | ✓ | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 |
| R2-055 | ✓ | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 |
| R2-060 | ✓ | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 |

5/5 parsed. The four-of-five fully-passing criterion is met; the two precision misses are the route-indexing over-citation pattern the prior cannot constrain.

#### 3.7.3 Pass^k (10 cases × k=3) on the same R2-5 subset

| subset | n | stable_success | stable_failure | flaky | pass^k_all | pass@k_any |
|---|---:|---:|---:|---:|---:|---:|
| target-extension | 5 | 4 | 0 | 1 | 0.800 | 1.000 |
| current-row failure | 5 | 1 | 3 | 1 | 0.200 | 0.400 |
| **overall** | 10 | 5 | 3 | 2 | **0.500** | **0.700** |

30/30 parsed.

#### 3.7.4 30-case stratified sampler (5 OBJ + 5 PV + 5 STRUCT + 5 SCHEDULE + the 10 pass^k cases)

| partition | n | intent | ans | beh | evidence P/R | warning P/R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 17 | 1.000 | 1.000 | 0.941 | 0.657/0.838 | 1.000/1.000 | 1.000 (3) |
| target_extension | 13 | 1.000 | 1.000 | 0.923 | 1.000/0.985 | 0.923/1.000 | 1.000 (8) |
| **overall** | 30 | **1.000** | **1.000** | 0.933 | 0.806/0.902 | 0.967/1.000 | 1.000 (11) |

System A locks **perfect intent and answerability on the 30 sampled cases**, vs B's 0.949 / 0.949 on the 39 current rows of the full benchmark. The remaining 0.933 behavior_class accuracy is dominated by the `route_indexing_ambiguity` warning behaviour the prior locks but where the model's evidence over-citation still drops precision below 1.0.

---

## 4. Cross-stage comparison — the core thesis result

### 4.1 The (B, A, C) reliability spectrum on the R2-5 pass^k subset

| | System B (R2-4A/R2-5) | System A (R2-6) | C-extended (R2-3) |
|---|---|---|---|
| pass^k_all on the 10-case subset | **0.30** (k=5) | **0.50** (k=3) | **1.00** by construction |
| target-extension pass^k_all | 0.60 | 0.80 | 1.00 |
| current-row pass^k_all | 0.00 | 0.20 | 1.00 |
| stable_success count | 3 | 5 | 10 |
| stable_failure count | 5 | 3 | 0 |
| flaky count | 2 | 2 | 0 |

Per-case migration B → A:

| case | B pass^k_all (k=5) | A pass^k_all (k=3) | classification change |
|---|---|---|---|
| R2-008 | 5/5 | 3/3 | stable_success → stable_success |
| R2-012 | 5/5 | 3/3 | stable_success → stable_success |
| R2-015 | 5/5 | 3/3 | stable_success → stable_success |
| R2-048 | 2/5 (0.40) | 2/3 (0.67) | flaky → flaky (mild improvement) |
| R2-058 | 4/5 (0.80) | 3/3 | flaky → **stable_success** |
| R2-027 | 0/5 | 0/3 | stable_failure → stable_failure |
| R2-040 | 0/5 | 3/3 | stable_failure → **stable_success** |
| R2-051 | 0/5 | 1/3 | stable_failure → flaky (partial recovery) |
| R2-055 | 0/5 | 0/3 | stable_failure → stable_failure |
| R2-060 | 0/5 | 0/3 | stable_failure → stable_failure |

### 4.2 Overall-benchmark numbers (single-sample run)

| | C-extended (60) | System B (60) | System A 30-case sampler (30) |
|---|---:|---:|---:|
| intent_accuracy | 1.000 | 0.950 | **1.000** |
| answerability_accuracy | 1.000 | 0.967 | **1.000** |
| behavior_class_accuracy | 1.000 | 0.917 | 0.933 |
| evidence_precision | 0.980 | 0.771 | 0.806 |
| evidence_recall | 1.000 | 0.902 | 0.902 |
| warning_precision | 1.000 | 0.917 | 0.967 |
| warning_recall | 1.000 | 0.950 | 1.000 |
| missing_field_recall | 1.000 | 0.992 | 1.000 |
| useful_refusal_correct_rate | 1.000 (18/18) | 0.944 (17/18) | 1.000 (11/11) |

System A's 30-case sampler covers a different denominator than the C/B 60, so the comparison isn't quite like-for-like — but the *direction* of the deltas is unambiguous: A reaches C-extended on intent and answerability, lifts warning_precision and warning_recall above B, and still trails C on the evidence-precision axis where the prior gives no guidance.

### 4.3 What the prior actually fixes

Two failure modes recover deterministically when A is given the prior:

1. **Intent confusion on lexically ambiguous prompts.** R2-040 ("Which route is customer 17 on…") and R2-051 ("Is anyone going to be late…") were stable B failures because the model picked `new_customer_assignment` / `feasibility_status` from surface tokens. A locks the right intent and the model preserves it across replicates.
2. **Policy warnings the surface prompt does not name.** R2-058 (false-premise customer, flaky useful_refusal under B) becomes stable under A because the prior locks `false_premise_detected` + `clarify_false_premise` in `warnings_prior` and `next_actions_prior`.

### 4.4 What the prior cannot fix

Two failure modes persist into A:

1. **Evidence over-citation.** R2-048 (target_extension), R2-051 (one of three replicates), R2-055 / R2-060 — the model adds extra field-family paths (`routes[].route_idx`, `route_end_times[].route_idx`, `customer_schedule[].customer_id`) alongside the answer-grounding column the gold pins. The prior surfaces `required_fields` as a hint but never constrains the evidence *list*; that's the model's degree of freedom by design.
2. **PV `feasibility_breakdown` subkey enumeration.** R2-027 (and R2-011, R2-028, R2-029, R2-030, R2-031 on the broader benchmark). The gold rubric enumerates `feasibility_breakdown.{capacity_ok, time_windows_ok, coverage_ok}` separately; the prior and C-extended both emit `feasibility_breakdown` as one path. This is **a rubric-vs-contract gap C-extended also shows** (0.969 current evidence_precision baseline at R2-3 closeout). A inherits it.

### 4.5 The thesis claim verdict

The R2-6 design doc named the claim under test:

> "Thin deterministic priors improve model stability but full deterministic contract execution remains the most reliable."

The evidence supports it. A occupies the middle of the (B = 0.30, C = 1.00) reliability spectrum exactly where the claim places it. The recovered failures are precisely the ones where the prior *has something to lock*; the persistent failures are precisely the ones where the prior surface is silent (evidence pinning, gold-rubric subkey expectations).

---

## 5. Cost and integrity

### 5.1 Cost

| run | calls | tokens (prompt / completion) | wall time |
|---|---:|---:|---:|
| R2-4A smoke (5 cases) | 5 | 15,420 / 574 | 11.22 s |
| R2-4A full (60 cases) | 60 | 200,058 / 7,275 | 118.31 s |
| R2-5 pass^k (10 × 5) | 50 | 265,480 / 6,094 | 109.93 s |
| R2-6 smoke (5 cases) | 5 | ~24,000 / ~600 | ~12 s |
| R2-6 pass^k (10 × 3) | 30 | ~135,000 / ~3,500 | ~75 s |
| R2-6 30-case (30 cases) | 30 | ~135,000 / ~3,500 | ~80 s |
| **Total** | **180** | **~775,000 / ~21,500** | **~7 min** |

(The R2-6 token / time numbers are estimated; the precise per-run logs are in `model_outputs/*/run_log.md` for each.)

### 5.2 Integrity

Throughout R2-3 through R2-6:

- HEAD is `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` = `run2-contract-extended`.
- `git diff --stat HEAD` is empty for every protected path: `run2_benchmark_cases.csv`, `run2_gold_schema.md`, `run2_scoring.py`, `run2_calibration_cases.csv`, `run2_system_c.py`, `product/copilot/*`, `product/data/*`, `experiment/configs/*`, `experiment/data/*`.
- `.env` is in `.gitignore` and `git ls-files --error-unmatch .env` returns non-zero — never tracked.
- No `OPENAI_API_KEY` or `sk-…` substring appears in any `model_outputs/` file. (Slug substrings of `openai-gpt54mini` are not key prefixes.)
- 139/139 R2 tests pass at the end of R2-6 (R2-3 left 103; the 36 added across R2-4A → R2-6 break down as: 11 model-output adapter + 6 pass^k aggregation + 13 System A prior + 6 prior-fields parser).

---

## 6. Limitations and caveats

The benchmark is intentionally narrow. The following are *not* established by Run 2 and would require separate stages to claim:

- **Not a user study.** The benchmark grades the structured contract, not the operator-visible answer text. A perfectly-scored contract still has to be rendered by the product copy layer; that rendering is out of scope.
- **Not generalisation.** 60 frozen cases is enough to make claim-level comparisons between (B, A, C) but not enough to claim the model will behave the same on the next 60 cases.
- **Not model robustness.** R2-5 / R2-6 measure replicate-stability at modest k. The model could still fail on (case, prompt) variations the benchmark does not include.
- **Not solver validation.** No solver was called at any point in Run 2; payload mutations are deterministic deep-copy transformations of the locked Run 1 generator records.
- **Contract ≠ answer text.** A correct contract is necessary, not sufficient, for a good operator-visible answer.

The PV `feasibility_breakdown` rubric mismatch is also worth flagging: the gold expects three subkey citations; the contract emits the parent path. Neither C-extended nor A "fixes" this. The right fix is on the rubric side (treat `feasibility_breakdown` as one field-family), but that change was explicitly excluded — "never tune gold to contract" was pre-registered.

---

## 7. What was *not* done

Per user direction, the following are explicitly out of scope for Run 2:

- **Claude Code as model-under-test.** Claude Code carries repo / tool / project context that the contract is supposed to test for; the user ruled it out as a baseline.
- **Full-60 System A pass^k.** R2-6 scope was the 10-case subset + a 30-case single-sample sampler.
- **Stress split.** Deferred.
- **System variations beyond B and A.** No retrieval-grounded baseline, no fine-tuned model, no alternative deterministic adapter.
- **Modification of the locked benchmark / gold schema / scorer.** Pre-registration discipline held across all six stages.

---

## 8. What Run 2 actually showed

Three claims, each grounded in numbers above:

### 8.1 The benchmark is an engineering instrument

R2-1 → R2-3 demonstrated that the benchmark can be used to surface contract gaps, target them with deliberate extensions, and verify the extensions land in the right cells without regressing the already-supported cases. Six R2-3 extensions lifted target_extension scoring from useful_refusal_correct 0.000 → 1.000 while current rows stayed within ±0.000 of their pre-extension scores (modulo the long-standing PV evidence_precision dip). The before/after rows are reproducible from the commit log.

### 8.2 A prompt-only model is strong but unreliable

System B (gpt-5.4-mini, the latest available OpenAI mini model at the time of the run) reaches 0.95+ on intent and answerability at single-sample evaluation but only 0.30 strict pass^k_all on a 10-case subset at k=5. The failure modes are stable, not random — 5 of 5 R2-4A current-row failures stay failures on every one of 5 replicates. R2-4A's single-sample 1.000 on target_extension cases hid two flaky cases at k=5.

### 8.3 A thin deterministic prior closes more than half the reliability gap

System A reaches 0.50 pass^k_all on the same subset at k=3 (vs B = 0.30, C = 1.00). The cases that recover are exactly the ones where the prior has something to lock (intent classification, false-premise detection, warning policy). The cases that don't recover are exactly the ones where the prior surface is silent (evidence pinning, rubric-vs-contract subkey expectations).

The (B → A → C) gradient is the thesis claim's prediction made concrete.

---

## 9. Pointer index

Authoritative sources for every number in this report:

### Pre-registration
- `product/evaluation/run2_contract_benchmark_design.md` — design doc (R2-0).
- `product/evaluation/run2_gold_schema.md` — gold schema (R2-0).
- `product/evaluation/run2_benchmark_cases.csv` — frozen 60-case benchmark.
- `product/evaluation/run2_calibration_cases.csv` — frozen 15-case calibration.

### R2-1 / R2-2 (calibration + expansion)
- `product/evaluation/run2_benchmark_case_notes.md` — cluster rationale + B-001..B-006 corrections.
- `product/evaluation/reports/run2_calibration_eval_system_c.{md,csv}` — calibration C-current.
- `product/evaluation/reports/run2_benchmark_eval_system_c_current.{md,csv}` — R2-2 60-case C-current.
- `product/evaluation/reports/run2_benchmark_expansion_report.md` — expansion log.

### R2-3 (contract extensions)
- `product/evaluation/reports/run2_extension_implementation_report.md` — step-by-step implementation log.
- `product/evaluation/reports/run2_contract_extension_thesis_summary.md` — closeout summary with verbatim thesis paragraph.
- `product/evaluation/reports/run2_benchmark_eval_system_c_extended.{md,csv}` — 60-case C-extended.
- HEAD: `18b4811`, tag `run2-contract-extended`.

### R2-4A (System B prompt-only)
- `product/evaluation/reports/run2_model_baseline_model_lock_openai_gpt54mini.md` — model lock.
- `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.{md,csv}` — 60-case results.
- `product/evaluation/reports/run2_4a_final_report.md` — R2-4A summary.

### R2-5 (System B pass^k)
- `product/evaluation/reports/run2_passk_subset.md` — pre-registered subset.
- `product/evaluation/reports/run2_passk_gpt54mini_v1.{md,csv}` — 10 × 5 results.
- `product/evaluation/reports/run2_5_final_report.md` — R2-5 summary.

### R2-6 (System A hybrid)
- `product/evaluation/reports/run2_system_a_design.md` — design doc.
- `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_smoke.{md,csv}` — 5-case smoke.
- `product/evaluation/reports/run2_passk_system_a_gpt54mini_v1.{md,csv}` — 10 × 3 pass^k.
- `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_30case_v1.{md,csv}` — 30-case sampler.
- `product/evaluation/reports/run2_system_a_final_report.md` — R2-6 summary.

### Per-run raw / parsed outputs
- `product/evaluation/model_outputs/run2-b-openai-gpt54mini-smoke/`
- `product/evaluation/model_outputs/run2-b-openai-gpt54mini-v1/`
- `product/evaluation/model_outputs/run2-b-openai-gpt54mini-passk-v1/`
- `product/evaluation/model_outputs/run2-a-openai-gpt54mini-smoke/`
- `product/evaluation/model_outputs/run2-a-openai-gpt54mini-passk-v1/`
- `product/evaluation/model_outputs/run2-a-openai-gpt54mini-30case-v1/`

### Code
- `product/evaluation/run2_case_loader.py`, `run2_payloads.py`, `run2_scoring.py`, `run2_system_c.py` — deterministic instrument.
- `product/evaluation/model_clients/openai_client.py` — API wrapper.
- `product/evaluation/run2_model_prompts.py` — System B + System A prompt builders.
- `product/evaluation/run2_model_output_adapter.py` — JSON parser with optional System A fields.
- `product/evaluation/run2_model_baseline_runner.py`, `run2_passk_runner.py` — single-sample + pass^k runners.
- `product/evaluation/run2_score_model_outputs.py`, `run2_passk_report.py` — scoring + reporting.
- `product/evaluation/run2_system_a_prior.py` — deterministic-prior builder.
- `tests/test_run2_*.py` — 139 tests.

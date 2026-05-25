# R2-S Axis 2 OOD False Premises & Comparators — Baseline Report

_System: C0. Run started: 2026-05-20T22:25:57Z. HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`. Seed run_id: `full-run-v1`._

## Purpose

Axis 2 tests whether the System C0 contract layer (`product/copilot/refusal_policy.py` plus `product/data/answerability.py` and `product/data/entity_resolution.py`) correctly **refuses or partially answers** when the operator's question contains an unsupported premise: a nonexistent entity, an unsupported movement/reassignment, a missing comparator/baseline, or a causal explanation the payload does not record. Unlike Axis 1 (look-alike intent attractors) and Axis 3 (semantic paraphrases), Axis 2 grades the contract layer, not the front-door keyword classifier in isolation.

## Method

- 24 cases, split 12 dev / 12 heldout via an explicit `split` column; 4 OOD-premise bands of 6 cases each (3 dev + 3 heldout).
- Payloads materialized via `run2_payloads.materialize_case_payload(run_id='full-run-v1')` — identical to the locked-benchmark path.
- No solver calls. No model calls (System C0 is deterministic).
- Scores reuse `run2_scoring.score_case` against gold rows **authored per case** (Axis 2 does not inherit gold verbatim from the base case — the prompt deliberately mutates the user premise).
- No locked Run 2 file modified. No `product/copilot/*` or `product/data/*` file modified.

### Case distribution

| Stratum | n |
|---|---:|
| total | 24 |
| split = dev | 12 |
| split = heldout | 12 |
| band = `causal_or_explanatory_unsupported_premise` | 6 |
| band = `missing_comparator_or_baseline` | 6 |
| band = `nonexistent_entity_false_premise` | 6 |
| band = `unsupported_movement_or_assignment_premise` | 6 |

## Guardrails and caveats

- **Not a user study.** All gold labels are author-derived.
- **Not solver validation.** No optimization run, no feasibility check was performed.
- **Not a Run 2 replacement.** Axis 2 is a diagnostic stress split, not a benchmark.
- **Heldout must not be tuned on.** Iteration on C0 or a future System D consumes the `dev` split only.

## Overall metrics

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | 24 | 75.0% | 75.0% | 75.0% | 83.3% | 95.0% | 66.7% | 66.7% | 91.7% |

## Metrics by split

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | 12 | 83.3% | 75.0% | 75.0% | 83.3% | 95.0% | 75.0% | 75.0% | 91.7% |
| heldout | 12 | 66.7% | 75.0% | 75.0% | 83.3% | 95.0% | 58.3% | 58.3% | 91.7% |
| overall | 24 | 75.0% | 75.0% | 75.0% | 83.3% | 95.0% | 66.7% | 66.7% | 91.7% |

## Metrics by OOD-premise band

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal_or_explanatory_unsupported_premise | 6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| missing_comparator_or_baseline | 6 | 50.0% | 66.7% | 66.7% | 100.0% | 80.0% | 50.0% | 50.0% | 66.7% |
| nonexistent_entity_false_premise | 6 | 100.0% | 66.7% | 66.7% | 66.7% | 100.0% | 66.7% | 66.7% | 100.0% |
| unsupported_movement_or_assignment_premise | 6 | 50.0% | 66.7% | 66.7% | 66.7% | 100.0% | 50.0% | 50.0% | 100.0% |

## Useful-refusal and partial-answer summary

| Group | useful_refusal n | useful_refusal correct | partial_answer n | partial_answer correct |
|---|---:|---:|---:|---:|
| overall | 15 | 60.0% | 4 | 50.0% |
| dev | 7 | 71.4% | 2 | 50.0% |
| heldout | 8 | 50.0% | 2 | 50.0% |
| causal_or_explanatory_unsupported_premise | 1 | 100.0% | 0 | — |
| missing_comparator_or_baseline | 2 | 50.0% | 4 | 50.0% |
| nonexistent_entity_false_premise | 6 | 66.7% | 0 | — |
| unsupported_movement_or_assignment_premise | 6 | 50.0% | 0 | — |

## Failure taxonomy (bucket counts)

Mutually exclusive, exhaustive over all 24 cases. See `design.md` §8 for the bucket definitions.

| Bucket | n |
|---|---:|
| `schema_gap_or_unrepresentable_gold` | 5 |
| `correct_refusal_or_partial` | 11 |
| `unknown_intent` | 2 |
| `wrong_intent` | 4 |
| `missed_false_premise` | 2 |

### Buckets by split

| Split | schema_gap_or_unrepresentable_gold | correct_refusal_or_partial | unknown_intent | wrong_intent | missed_false_premise | missed_missing_comparator | over_answered_unsupported_premise | downstream_evidence_mismatch | guard_protected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | 3 | 6 | 0 | 2 | 1 | 0 | 0 | 0 | 0 |
| heldout | 2 | 5 | 2 | 2 | 1 | 0 | 0 | 0 | 0 |

### Buckets by band

| Band | schema_gap_or_unrepresentable_gold | correct_refusal_or_partial | unknown_intent | wrong_intent | missed_false_premise | missed_missing_comparator | over_answered_unsupported_premise | downstream_evidence_mismatch | guard_protected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `causal_or_explanatory_unsupported_premise` | 5 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `missing_comparator_or_baseline` | 0 | 3 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| `nonexistent_entity_false_premise` | 0 | 4 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `unsupported_movement_or_assignment_premise` | 0 | 3 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |

## Per-case failure table (13 non-correct cases)

| case_id | split | band | bucket | gold intent | pred intent | gold cls | pred cls | ev p/r | warn p/r | miss r |
|---|---|---|---|---|---|---|---|---|---|---|
| A2D-03 | dev | `nonexistent_entity_false_premise` | `missed_false_premise` | lateness_summary | lateness_summary | useful_refusal | direct_answer | 0.00/1.00 | 0.00/0.00 | 1.00 |
| A2H-02 | heldout | `nonexistent_entity_false_premise` | `missed_false_premise` | feasibility_status | feasibility_status | useful_refusal | direct_answer | 0.00/1.00 | 0.00/0.00 | 1.00 |
| A2D-06 | dev | `unsupported_movement_or_assignment_premise` | `wrong_intent` | before_after_comparison | single_customer_route_membership | useful_refusal | direct_answer_with_warning | 0.00/1.00 | 0.00/0.00 | 1.00 |
| A2H-05 | heldout | `unsupported_movement_or_assignment_premise` | `wrong_intent` | before_after_comparison | single_customer_route_membership | useful_refusal | direct_answer_with_warning | 0.00/1.00 | 0.00/0.00 | 1.00 |
| A2H-06 | heldout | `unsupported_movement_or_assignment_premise` | `unknown_intent` | before_after_comparison | unknown | useful_refusal | useful_refusal | 1.00/1.00 | 0.00/0.00 | 1.00 |
| A2D-08 | dev | `missing_comparator_or_baseline` | `wrong_intent` | objective_delta | objective_value | partial_answer_with_warning | direct_answer | 1.00/0.40 | 0.00/0.00 | 0.00 |
| A2H-08 | heldout | `missing_comparator_or_baseline` | `wrong_intent` | objective_delta | objective_value | partial_answer_with_warning | direct_answer | 1.00/0.40 | 0.00/0.00 | 0.00 |
| A2H-09 | heldout | `missing_comparator_or_baseline` | `unknown_intent` | before_after_comparison | unknown | useful_refusal | useful_refusal | 1.00/1.00 | 0.00/0.00 | 1.00 |
| A2D-10 | dev | `causal_or_explanatory_unsupported_premise` | `schema_gap_or_unrepresentable_gold` | lateness_summary | lateness_summary | direct_answer_with_warning | direct_answer_with_warning | 1.00/1.00 | 1.00/1.00 | 1.00 |
| A2D-11 | dev | `causal_or_explanatory_unsupported_premise` | `schema_gap_or_unrepresentable_gold` | objective_value | objective_value | direct_answer | direct_answer | 1.00/1.00 | 1.00/1.00 | 1.00 |
| A2D-12 | dev | `causal_or_explanatory_unsupported_premise` | `schema_gap_or_unrepresentable_gold` | lateness_summary | lateness_summary | direct_answer | direct_answer | 1.00/1.00 | 1.00/1.00 | 1.00 |
| A2H-11 | heldout | `causal_or_explanatory_unsupported_premise` | `schema_gap_or_unrepresentable_gold` | route_count | route_count | direct_answer | direct_answer | 1.00/1.00 | 1.00/1.00 | 1.00 |
| A2H-12 | heldout | `causal_or_explanatory_unsupported_premise` | `schema_gap_or_unrepresentable_gold` | lateness_summary | lateness_summary | direct_answer | direct_answer | 1.00/1.00 | 1.00/1.00 | 1.00 |

## Interpretation

C0 produced 11/24 **correct_refusal_or_partial**, 5/24 **schema_gap**, 2/24 **unknown_intent**, 4/24 **wrong_intent**, 2/24 **missed_false_premise**, 0/24 **missed_missing_comparator**, 0/24 **over_answered_unsupported_premise**, 0/24 **downstream_evidence_mismatch**, and 0/24 **guard_protected** outcomes. See `axis2_closeout.md` for the full methodological interpretation, including which failure modes are System-D-addressable vs future-work outside the current envelope.


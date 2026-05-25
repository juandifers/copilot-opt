# Run 2 model baseline — System B (openai gpt-5.4-mini)

- run_id: run2-b-openai-gpt54mini-v1
- provider: openai
- requested_model: gpt-5.4-mini
- cases: 60
- scored: 60
- unscored (parse/skip): 0

## 1. Parse success

- parsed: 60

## 2. Cases schema validation
- rows: 60
- errors: 0

## 3. Aggregate scores (component metrics only — no composite)

### Overall

| n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | 0.950 | 0.967 | 0.917 | 0.771/0.902 | 0.917/0.950 | 0.992 | 0.944 (18) |

### By implementation_status

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | 39 | 0.949 | 0.949 | 0.872 | 0.673/0.859 | 0.872/0.923 | 0.987 | 0.857 (7) |
| target_extension | 21 | 0.952 | 1.000 | 1.000 | 0.952/0.981 | 1.000/1.000 | 1.000 | 1.000 (11) |

### By family

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBJ | 15 | 1.000 | 1.000 | 1.000 | 1.000/0.973 | 1.000/1.000 | 1.000 | — (0) |
| PLAN_VALIDITY | 12 | 1.000 | 1.000 | 0.917 | 0.750/0.625 | 0.917/1.000 | 1.000 | 1.000 (6) |
| SCHEDULE | 15 | 0.933 | 0.933 | 0.800 | 0.649/0.933 | 0.800/0.867 | 1.000 | 1.000 (6) |
| STRUCT | 18 | 0.889 | 0.944 | 0.944 | 0.694/1.000 | 0.944/0.944 | 0.972 | 0.833 (6) |

### By expected_behavior_class

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct_answer | 27 | 0.963 | 0.963 | 0.926 | 0.712/0.796 | 0.926/1.000 | 1.000 | — (0) |
| direct_answer_with_warning | 8 | 0.875 | 0.875 | 0.625 | 0.500/1.000 | 0.625/0.625 | 1.000 | — (0) |
| partial_answer_with_warning | 7 | 1.000 | 1.000 | 1.000 | 1.000/0.943 | 1.000/1.000 | 1.000 | — (0) |
| useful_refusal | 18 | 0.944 | 1.000 | 1.000 | 0.889/1.000 | 1.000/1.000 | 0.972 | 0.944 (18) |

### By difficulty

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| easy | 20 | 0.950 | 0.950 | 0.900 | 0.712/0.800 | 0.900/1.000 | 0.975 | 0.667 (3) |
| hard | 14 | 0.929 | 1.000 | 1.000 | 0.929/0.971 | 1.000/1.000 | 1.000 | 1.000 (5) |
| medium | 26 | 0.962 | 0.962 | 0.885 | 0.731/0.942 | 0.885/0.885 | 1.000 | 1.000 (10) |

## 4. Failure taxonomy

| kind | overall |
|---|---:|
| intent_miss | 3 |
| answerability_miss | 2 |
| behavior_class_miss | 5 |
| missing_field_miss | 1 |
| evidence_precision_miss | 22 |
| evidence_recall_miss | 9 |
| warning_precision_miss | 3 |
| warning_recall_miss | 3 |
| useful_refusal_composite_miss | 1 |
| partial_answer_composite_miss | 0 |

### Failure taxonomy by family

| kind | OBJ | PLAN_VALIDITY | SCHEDULE | STRUCT |
|---|---:|---:|---:|---:|
| intent_miss | 0 | 0 | 1 | 2 |
| answerability_miss | 0 | 0 | 1 | 1 |
| behavior_class_miss | 0 | 1 | 3 | 1 |
| missing_field_miss | 0 | 0 | 0 | 1 |
| evidence_precision_miss | 0 | 6 | 9 | 7 |
| evidence_recall_miss | 2 | 6 | 1 | 0 |
| warning_precision_miss | 0 | 0 | 2 | 1 |
| warning_recall_miss | 0 | 0 | 2 | 1 |
| useful_refusal_composite_miss | 0 | 0 | 0 | 1 |
| partial_answer_composite_miss | 0 | 0 | 0 | 0 |

## 5. Comparison vs C-extended

**Cases where C-extended passes a component metric but the model misses it:** 15

| case | misses |
|---|---|
| R2-011 | evidence_recall |
| R2-013 | evidence_recall |
| R2-025 | evidence_recall |
| R2-027 | evidence_recall |
| R2-028 | evidence_recall |
| R2-029 | behavior_class, evidence_recall |
| R2-030 | evidence_recall |
| R2-031 | evidence_recall |
| R2-040 | intent, answerability, behavior_class, warning_recall |
| R2-043 | missing_field_recall, useful_refusal_composite |
| R2-047 | intent |
| R2-051 | intent, answerability, behavior_class |
| R2-054 | evidence_recall |
| R2-055 | behavior_class, warning_recall |
| R2-060 | behavior_class, warning_recall |

## 6. Top 10 illustrative failures

### R2-004 (current, STRUCT, medium)

- prompt: Which route is customer 42 on after travel times went up 30%?
- payload_condition: clean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: single_customer_route_membership / answerable / direct_answer_with_warning
- pred intent / ans / beh: single_customer_route_membership / answerable / direct_answer_with_warning
- gold evidence: ['routes[].customer_ids']
- pred evidence: ['routes[].customer_ids', 'routes[].route_idx']
- gold warnings / pred warnings: ['struct_membership_ambiguity'] / ['struct_membership_ambiguity']
- gold actions / pred actions: [] / ['apply_route_label_augmentation']

### R2-006 (current, SCHEDULE, medium)

- prompt: What time does route 1 wrap up after service times went up 100%?
- payload_condition: convention_boundary
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- pred intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- gold evidence: ['route_end_times[].end_time']
- pred evidence: ['route_end_times[].end_time', 'route_end_times[].route_idx']
- gold warnings / pred warnings: ['route_indexing_ambiguity'] / ['route_indexing_ambiguity']

### R2-007 (current, SCHEDULE, easy)

- prompt: When does the driver reach customer 42 after the new orders came in?
- payload_condition: clean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: customer_arrival / answerable / direct_answer
- pred intent / ans / beh: customer_arrival / answerable / direct_answer
- gold evidence: ['customer_schedule[].arrival']
- pred evidence: ['customer_schedule[].arrival', 'customer_schedule[].customer_id']

### R2-009 (current, STRUCT, medium)

- prompt: Are customers 12 and 17 still on the same route after the new orders came in?
- payload_condition: same_route_boolean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: same_route_boolean / answerable / direct_answer
- pred intent / ans / beh: same_route_boolean / answerable / direct_answer
- gold evidence: ['routes[].customer_ids']
- pred evidence: ['routes[].customer_ids', 'routes[].route_idx']

### R2-011 (current, PLAN_VALIDITY, easy)

- prompt: After we slotted in the new customer, does the updated plan still hold up within all the usual constraints?
- payload_condition: clean
- miss_kinds: evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown']

### R2-013 (target_extension, OBJ, hard)

- prompt: What did this end up costing compared to running a full re-solve?
- payload_condition: missing_reference_solution
- miss_kinds: evidence_recall_miss
- gold intent / ans / beh: objective_delta / partially_answerable / partial_answer_with_warning
- pred intent / ans / beh: objective_delta / partially_answerable / partial_answer_with_warning
- gold evidence: ['baseline_objective', 'action_objective', 'objective_delta_absolute', 'objective_delta_percent', 'units.objective']
- pred evidence: ['action_objective', 'baseline_objective', 'objective_delta_absolute', 'objective_delta_percent']
- gold missing / pred missing: ['reference_solution.objective'] / ['reference_solution.objective']
- gold warnings / pred warnings: ['comparison_referent_ambiguity'] / ['comparison_referent_ambiguity']
- gold actions / pred actions: ['expose_reference_solution_objective'] / ['expose_reference_solution_objective']

### R2-025 (target_extension, OBJ, hard)

- prompt: What does the 10-second solve end up costing compared to a full re-solve?
- payload_condition: missing_reference_solution
- miss_kinds: evidence_recall_miss
- gold intent / ans / beh: objective_delta / partially_answerable / partial_answer_with_warning
- pred intent / ans / beh: objective_delta / partially_answerable / partial_answer_with_warning
- gold evidence: ['baseline_objective', 'action_objective', 'objective_delta_absolute', 'objective_delta_percent', 'units.objective']
- pred evidence: ['action_objective', 'baseline_objective', 'objective_delta_absolute', 'objective_delta_percent']
- gold missing / pred missing: ['reference_solution.objective'] / ['reference_solution.objective']
- gold warnings / pred warnings: ['comparison_referent_ambiguity'] / ['comparison_referent_ambiguity']
- gold actions / pred actions: ['expose_reference_solution_objective'] / ['expose_reference_solution_objective']

### R2-027 (current, PLAN_VALIDITY, easy)

- prompt: After adding the new customers, can the existing routes handle all of them, or are some going to get left out?
- payload_condition: clean
- miss_kinds: evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown']

### R2-028 (current, PLAN_VALIDITY, easy)

- prompt: Does this plan still work after the time windows got tighter?
- payload_condition: clean
- miss_kinds: evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown']

### R2-029 (current, PLAN_VALIDITY, easy)

- prompt: Does this plan still work after travel times went up 20%?
- payload_condition: clean
- miss_kinds: behavior_class_miss, evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer_with_warning
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown']
- gold warnings / pred warnings: [] / ['unsupported_comparison']


## Per-case predictions and scores

| case | status | family | gold intent | pred intent | gold ans | pred ans | gold beh | pred beh | parse | intent ✓ | ans ✓ | ev P/R | warn P/R | miss R |
|---|---|---|---|---|---|---|---|---|---|:---:|:---:|---:|---:|---:|
| R2-001 | current | OBJ | objective_value | objective_value | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-002 | current | OBJ | objective_delta | objective_delta | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-003 | current | STRUCT | new_customer_assignment | new_customer_assignment | partially_answerable | partially_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 0.000/1.000 | 1.000/1.000 | 1.000 |
| R2-004 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-005 | current | STRUCT | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-006 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-007 | current | SCHEDULE | customer_arrival | customer_arrival | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-008 | target_extension | SCHEDULE | customer_arrival | customer_arrival | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-009 | current | STRUCT | same_route_boolean | same_route_boolean | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-010 | target_extension | STRUCT | full_route_listing | full_route_listing | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-011 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-012 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-013 | target_extension | OBJ | objective_delta | objective_delta | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/0.800 | 1.000/1.000 | 1.000 |
| R2-014 | target_extension | OBJ | objective_value | objective_value | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-015 | target_extension | SCHEDULE | route_end_time | route_end_time | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-016 | current | OBJ | objective_value | objective_value | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-017 | current | OBJ | objective_delta | objective_delta | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-018 | current | OBJ | objective_delta | objective_delta | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-019 | current | OBJ | objective_value | objective_value | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-020 | current | OBJ | objective_delta | objective_delta | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-026 | current | OBJ | objective_delta | objective_delta | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-021 | target_extension | OBJ | objective_value | objective_value | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-022 | target_extension | OBJ | objective_value | objective_value | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-023 | target_extension | OBJ | objective_value | objective_value | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-024 | target_extension | OBJ | objective_delta | objective_delta | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-025 | target_extension | OBJ | objective_delta | objective_delta | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/0.800 | 1.000/1.000 | 1.000 |
| R2-027 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-028 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-029 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/0.250 | 0.000/1.000 | 1.000 |
| R2-030 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-031 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-032 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-033 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-034 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-035 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-036 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-037 | current | STRUCT | route_count | route_count | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-038 | current | STRUCT | route_count | route_count | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-039 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-040 | current | STRUCT | single_customer_route_membership | new_customer_assignment | answerable | partially_answerable | direct_answer_with_warning | partial_answer_with_warning | parsed | ✗ | ✗ | 0.500/1.000 | 0.000/0.000 | 1.000 |
| R2-041 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-042 | current | STRUCT | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-043 | current | STRUCT | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 0.500 |
| R2-044 | current | STRUCT | new_customer_assignment | new_customer_assignment | partially_answerable | partially_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-045 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-046 | current | STRUCT | same_route_boolean | same_route_boolean | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-047 | target_extension | STRUCT | single_customer_route_membership | new_customer_assignment | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✗ | ✓ | 0.000/1.000 | 1.000/1.000 | 1.000 |
| R2-048 | target_extension | STRUCT | full_route_listing | full_route_listing | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-049 | target_extension | STRUCT | full_route_listing | full_route_listing | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-050 | current | SCHEDULE | customer_arrival | customer_arrival | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-051 | current | SCHEDULE | lateness_summary | feasibility_status | answerable | partially_answerable | direct_answer | direct_answer_with_warning | parsed | ✗ | ✗ | 0.333/1.000 | 0.000/1.000 | 1.000 |
| R2-052 | current | SCHEDULE | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-053 | current | SCHEDULE | lateness_summary | lateness_summary | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.400/1.000 | 1.000/1.000 | 1.000 |
| R2-054 | current | SCHEDULE | lateness_summary | lateness_summary | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.000/0.000 | 1.000/1.000 | 1.000 |
| R2-055 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 0.000/0.000 | 1.000 |
| R2-056 | current | SCHEDULE | customer_arrival | customer_arrival | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-057 | current | SCHEDULE | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-058 | target_extension | SCHEDULE | customer_arrival | customer_arrival | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-059 | target_extension | SCHEDULE | route_end_time | route_end_time | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-060 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 0.000/0.000 | 1.000 |


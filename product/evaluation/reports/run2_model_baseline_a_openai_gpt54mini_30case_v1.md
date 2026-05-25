# Run 2 model baseline — System A (openai gpt-5.4-mini)

- run_id: run2-a-openai-gpt54mini-30case-v1
- provider: openai
- requested_model: gpt-5.4-mini
- cases: 60
- scored: 30
- unscored (parse/skip): 30

## 1. Parse success

- parsed: 30

## 2. Cases schema validation
- rows: 60
- errors: 0

## 3. Aggregate scores (component metrics only — no composite)

### Overall

| n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 1.000 | 1.000 | 0.933 | 0.806/0.902 | 0.967/1.000 | 1.000 | 1.000 (11) |

### By implementation_status

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | 17 | 1.000 | 1.000 | 0.941 | 0.657/0.838 | 1.000/1.000 | 1.000 | 1.000 (3) |
| target_extension | 13 | 1.000 | 1.000 | 0.923 | 1.000/0.985 | 0.923/1.000 | 1.000 | 1.000 (8) |

### By family

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBJ | 5 | 1.000 | 1.000 | 1.000 | 1.000/0.960 | 1.000/1.000 | 1.000 | — (0) |
| PLAN_VALIDITY | 7 | 1.000 | 1.000 | 1.000 | 0.738/0.607 | 1.000/1.000 | 1.000 | 1.000 (3) |
| SCHEDULE | 11 | 1.000 | 1.000 | 1.000 | 0.773/1.000 | 1.000/1.000 | 1.000 | 1.000 (5) |
| STRUCT | 7 | 1.000 | 1.000 | 0.714 | 0.786/1.000 | 0.857/1.000 | 1.000 | 1.000 (3) |

### By expected_behavior_class

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct_answer | 11 | 1.000 | 1.000 | 0.909 | 0.742/0.750 | 0.909/1.000 | 1.000 | — (0) |
| direct_answer_with_warning | 5 | 1.000 | 1.000 | 1.000 | 0.600/1.000 | 1.000/1.000 | 1.000 | — (0) |
| partial_answer_with_warning | 3 | 1.000 | 1.000 | 1.000 | 1.000/0.933 | 1.000/1.000 | 1.000 | — (0) |
| useful_refusal | 11 | 1.000 | 1.000 | 0.909 | 0.909/1.000 | 1.000/1.000 | 1.000 | 1.000 (11) |

### By difficulty

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| easy | 9 | 1.000 | 1.000 | 1.000 | 0.722/0.750 | 1.000/1.000 | 1.000 | 1.000 (1) |
| hard | 9 | 1.000 | 1.000 | 0.889 | 1.000/0.978 | 0.889/1.000 | 1.000 | 1.000 (5) |
| medium | 12 | 1.000 | 1.000 | 0.917 | 0.722/0.958 | 1.000/1.000 | 1.000 | 1.000 (5) |

## 4. Failure taxonomy

| kind | overall |
|---|---:|
| intent_miss | 0 |
| answerability_miss | 0 |
| behavior_class_miss | 2 |
| missing_field_miss | 0 |
| evidence_precision_miss | 10 |
| evidence_recall_miss | 5 |
| warning_precision_miss | 0 |
| warning_recall_miss | 0 |
| useful_refusal_composite_miss | 0 |
| partial_answer_composite_miss | 0 |

### Failure taxonomy by family

| kind | OBJ | PLAN_VALIDITY | SCHEDULE | STRUCT |
|---|---:|---:|---:|---:|
| intent_miss | 0 | 0 | 0 | 0 |
| answerability_miss | 0 | 0 | 0 | 0 |
| behavior_class_miss | 0 | 0 | 0 | 2 |
| missing_field_miss | 0 | 0 | 0 | 0 |
| evidence_precision_miss | 0 | 4 | 5 | 1 |
| evidence_recall_miss | 1 | 4 | 0 | 0 |
| warning_precision_miss | 0 | 0 | 0 | 0 |
| warning_recall_miss | 0 | 0 | 0 | 0 |
| useful_refusal_composite_miss | 0 | 0 | 0 | 0 |
| partial_answer_composite_miss | 0 | 0 | 0 | 0 |

## 5. Comparison vs C-extended

**Cases where C-extended passes a component metric but the model misses it:** 7

| case | misses |
|---|---|
| R2-003 | behavior_class |
| R2-010 | behavior_class |
| R2-011 | evidence_recall |
| R2-013 | evidence_recall |
| R2-027 | evidence_recall |
| R2-029 | evidence_recall |
| R2-031 | evidence_recall |

## 6. Top 10 illustrative failures

### R2-003 (current, STRUCT, medium)

- prompt: After adding the new customer, which route did they end up getting assigned to?
- payload_condition: missing_new_customer_ids
- miss_kinds: behavior_class_miss
- gold intent / ans / beh: new_customer_assignment / partially_answerable / useful_refusal
- pred intent / ans / beh: new_customer_assignment / partially_answerable / partial_answer_with_warning
- gold evidence: []
- pred evidence: ['routes[].customer_ids']
- gold missing / pred missing: ['new_customer_ids'] / ['new_customer_ids']
- gold warnings / pred warnings: ['missing_new_customer_attribution'] / ['missing_new_customer_attribution']
- gold actions / pred actions: ['expose_new_customer_ids'] / ['expose_new_customer_ids']

### R2-006 (current, SCHEDULE, medium)

- prompt: What time does route 1 wrap up after service times went up 100%?
- payload_condition: convention_boundary
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- pred intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- gold evidence: ['route_end_times[].end_time']
- pred evidence: ['route_end_times[].route_idx', 'route_end_times[].end_time']
- gold warnings / pred warnings: ['route_indexing_ambiguity'] / ['route_indexing_ambiguity']

### R2-007 (current, SCHEDULE, easy)

- prompt: When does the driver reach customer 42 after the new orders came in?
- payload_condition: clean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: customer_arrival / answerable / direct_answer
- pred intent / ans / beh: customer_arrival / answerable / direct_answer
- gold evidence: ['customer_schedule[].arrival']
- pred evidence: ['customer_schedule[].customer_id', 'customer_schedule[].arrival']

### R2-010 (target_extension, STRUCT, hard)

- prompt: List all the customers assigned to each route after the new orders came in.
- payload_condition: full_route_membership
- miss_kinds: behavior_class_miss
- gold intent / ans / beh: full_route_listing / answerable / direct_answer
- pred intent / ans / beh: full_route_listing / answerable / direct_answer_with_warning
- gold evidence: ['routes[].customer_ids']
- pred evidence: ['routes[].customer_ids']
- gold warnings / pred warnings: [] / ['struct_membership_ambiguity']

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

### R2-027 (current, PLAN_VALIDITY, easy)

- prompt: After adding the new customers, can the existing routes handle all of them, or are some going to get left out?
- payload_condition: clean
- miss_kinds: evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown']

### R2-029 (current, PLAN_VALIDITY, easy)

- prompt: Does this plan still work after travel times went up 20%?
- payload_condition: clean
- miss_kinds: evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown']

### R2-031 (current, PLAN_VALIDITY, medium)

- prompt: Did we end up dropping any customers after the time windows got tighter?
- payload_condition: clean
- miss_kinds: evidence_recall_miss, evidence_precision_miss
- gold intent / ans / beh: feasibility_status / answerable / direct_answer
- pred intent / ans / beh: feasibility_status / answerable / direct_answer
- gold evidence: ['feasible', 'feasibility_breakdown.capacity_ok', 'feasibility_breakdown.time_windows_ok', 'feasibility_breakdown.coverage_ok']
- pred evidence: ['feasible', 'feasibility_breakdown', 'feasibility_breakdown.time_windows_ok']

### R2-040 (current, STRUCT, medium)

- prompt: Which route is customer 17 on after a new order came in?
- payload_condition: clean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: single_customer_route_membership / answerable / direct_answer_with_warning
- pred intent / ans / beh: single_customer_route_membership / answerable / direct_answer_with_warning
- gold evidence: ['routes[].customer_ids']
- pred evidence: ['routes[].customer_ids', 'routes[].route_idx']
- gold warnings / pred warnings: ['struct_membership_ambiguity'] / ['struct_membership_ambiguity']


## Per-case predictions and scores

| case | status | family | gold intent | pred intent | gold ans | pred ans | gold beh | pred beh | parse | intent ✓ | ans ✓ | ev P/R | warn P/R | miss R |
|---|---|---|---|---|---|---|---|---|---|:---:|:---:|---:|---:|---:|
| R2-001 | current | OBJ | objective_value | objective_value | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-002 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-003 | current | STRUCT | new_customer_assignment | new_customer_assignment | partially_answerable | partially_answerable | useful_refusal | partial_answer_with_warning | parsed | ✓ | ✓ | 0.000/1.000 | 1.000/1.000 | 1.000 |
| R2-004 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-005 | current | STRUCT | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-006 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-007 | current | SCHEDULE | customer_arrival | customer_arrival | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-008 | target_extension | SCHEDULE | customer_arrival | customer_arrival | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-009 | current | STRUCT | same_route_boolean | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-010 | target_extension | STRUCT | full_route_listing | full_route_listing | answerable | answerable | direct_answer | direct_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 0.000/1.000 | 1.000 |
| R2-011 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-012 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-013 | target_extension | OBJ | objective_delta | objective_delta | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/0.800 | 1.000/1.000 | 1.000 |
| R2-014 | target_extension | OBJ | objective_value | objective_value | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-015 | target_extension | SCHEDULE | route_end_time | route_end_time | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-016 | current | OBJ | objective_value | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-017 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-018 | current | OBJ | objective_delta | objective_delta | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-019 | current | OBJ | objective_value | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-020 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-026 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-021 | target_extension | OBJ | objective_value | objective_value | partially_answerable | partially_answerable | partial_answer_with_warning | partial_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-022 | target_extension | OBJ | objective_value | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-023 | target_extension | OBJ | objective_value | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-024 | target_extension | OBJ | objective_delta | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-025 | target_extension | OBJ | objective_delta | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-027 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-028 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-029 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/0.250 | 1.000/1.000 | 1.000 |
| R2-030 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-031 | current | PLAN_VALIDITY | feasibility_status | feasibility_status | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.667/0.500 | 1.000/1.000 | 1.000 |
| R2-032 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-033 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-034 | target_extension | PLAN_VALIDITY | feasibility_status | feasibility_status | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-035 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-036 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-037 | current | STRUCT | route_count | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-038 | current | STRUCT | route_count | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-039 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-040 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-041 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-042 | current | STRUCT | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-043 | current | STRUCT | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-044 | current | STRUCT | new_customer_assignment | _unscored_ | partially_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-045 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-046 | current | STRUCT | same_route_boolean | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-047 | target_extension | STRUCT | single_customer_route_membership | single_customer_route_membership | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-048 | target_extension | STRUCT | full_route_listing | full_route_listing | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-049 | target_extension | STRUCT | full_route_listing | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-050 | current | SCHEDULE | customer_arrival | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-051 | current | SCHEDULE | lateness_summary | lateness_summary | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-052 | current | SCHEDULE | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-053 | current | SCHEDULE | lateness_summary | lateness_summary | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-054 | current | SCHEDULE | lateness_summary | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-055 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-056 | current | SCHEDULE | customer_arrival | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-057 | current | SCHEDULE | before_after_comparison | before_after_comparison | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-058 | target_extension | SCHEDULE | customer_arrival | customer_arrival | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-059 | target_extension | SCHEDULE | route_end_time | route_end_time | not_answerable | not_answerable | useful_refusal | useful_refusal | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-060 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |

## 7. Unscored cases

- `R2-002` parse_status=missing notes=no parsed row
- `R2-009` parse_status=missing notes=no parsed row
- `R2-016` parse_status=missing notes=no parsed row
- `R2-017` parse_status=missing notes=no parsed row
- `R2-019` parse_status=missing notes=no parsed row
- `R2-020` parse_status=missing notes=no parsed row
- `R2-026` parse_status=missing notes=no parsed row
- `R2-022` parse_status=missing notes=no parsed row
- `R2-023` parse_status=missing notes=no parsed row
- `R2-024` parse_status=missing notes=no parsed row
- `R2-025` parse_status=missing notes=no parsed row
- `R2-028` parse_status=missing notes=no parsed row
- `R2-030` parse_status=missing notes=no parsed row
- `R2-033` parse_status=missing notes=no parsed row
- `R2-035` parse_status=missing notes=no parsed row
- `R2-036` parse_status=missing notes=no parsed row
- `R2-037` parse_status=missing notes=no parsed row
- `R2-038` parse_status=missing notes=no parsed row
- `R2-039` parse_status=missing notes=no parsed row
- `R2-041` parse_status=missing notes=no parsed row
- `R2-042` parse_status=missing notes=no parsed row
- `R2-043` parse_status=missing notes=no parsed row
- `R2-044` parse_status=missing notes=no parsed row
- `R2-045` parse_status=missing notes=no parsed row
- `R2-046` parse_status=missing notes=no parsed row
- `R2-049` parse_status=missing notes=no parsed row
- `R2-050` parse_status=missing notes=no parsed row
- `R2-052` parse_status=missing notes=no parsed row
- `R2-054` parse_status=missing notes=no parsed row
- `R2-056` parse_status=missing notes=no parsed row


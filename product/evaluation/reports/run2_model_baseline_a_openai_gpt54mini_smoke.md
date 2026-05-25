# Run 2 model baseline — System B (openai gpt-5.4-mini)

- run_id: run2-a-openai-gpt54mini-smoke
- provider: openai
- requested_model: gpt-5.4-mini
- cases: 60
- scored: 5
- unscored (parse/skip): 55

## 1. Parse success

- parsed: 5

## 2. Cases schema validation
- rows: 60
- errors: 0

## 3. Aggregate scores (component metrics only — no composite)

### Overall

| n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 1.000 | 1.000 | 1.000 | 0.800/1.000 | 1.000/1.000 | 1.000 | — (0) |

### By implementation_status

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | 4 | 1.000 | 1.000 | 1.000 | 0.750/1.000 | 1.000/1.000 | 1.000 | — (0) |
| target_extension | 1 | 1.000 | 1.000 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000 | — (0) |

### By family

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SCHEDULE | 3 | 1.000 | 1.000 | 1.000 | 0.667/1.000 | 1.000/1.000 | 1.000 | — (0) |
| STRUCT | 2 | 1.000 | 1.000 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000 | — (0) |

### By expected_behavior_class

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct_answer | 2 | 1.000 | 1.000 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000 | — (0) |
| direct_answer_with_warning | 3 | 1.000 | 1.000 | 1.000 | 0.667/1.000 | 1.000/1.000 | 1.000 | — (0) |

### By difficulty

| group | n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| easy | 1 | 1.000 | 1.000 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000 | — (0) |
| hard | 1 | 1.000 | 1.000 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000 | — (0) |
| medium | 3 | 1.000 | 1.000 | 1.000 | 0.667/1.000 | 1.000/1.000 | 1.000 | — (0) |

## 4. Failure taxonomy

| kind | overall |
|---|---:|
| intent_miss | 0 |
| answerability_miss | 0 |
| behavior_class_miss | 0 |
| missing_field_miss | 0 |
| evidence_precision_miss | 2 |
| evidence_recall_miss | 0 |
| warning_precision_miss | 0 |
| warning_recall_miss | 0 |
| useful_refusal_composite_miss | 0 |
| partial_answer_composite_miss | 0 |

### Failure taxonomy by family

| kind | SCHEDULE |
|---|---:|
| intent_miss | 0 |
| answerability_miss | 0 |
| behavior_class_miss | 0 |
| missing_field_miss | 0 |
| evidence_precision_miss | 2 |
| evidence_recall_miss | 0 |
| warning_precision_miss | 0 |
| warning_recall_miss | 0 |
| useful_refusal_composite_miss | 0 |
| partial_answer_composite_miss | 0 |

## 5. Comparison vs C-extended

**Cases where C-extended passes a component metric but the model misses it:** 0


## 6. Top 10 illustrative failures

### R2-055 (current, SCHEDULE, medium)

- prompt: What time does route 1 wrap up after the new orders came in?
- payload_condition: clean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- pred intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- gold evidence: ['route_end_times[].end_time']
- pred evidence: ['route_end_times[].route_idx', 'route_end_times[].end_time']
- gold warnings / pred warnings: ['route_indexing_ambiguity'] / ['route_indexing_ambiguity']

### R2-060 (current, SCHEDULE, medium)

- prompt: What time does Route 1 finish after the service times went up?
- payload_condition: clean
- miss_kinds: evidence_precision_miss
- gold intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- pred intent / ans / beh: route_end_time / answerable / direct_answer_with_warning
- gold evidence: ['route_end_times[].end_time']
- pred evidence: ['route_end_times[].route_idx', 'route_end_times[].end_time']
- gold warnings / pred warnings: ['route_indexing_ambiguity'] / ['route_indexing_ambiguity']


## Per-case predictions and scores

| case | status | family | gold intent | pred intent | gold ans | pred ans | gold beh | pred beh | parse | intent ✓ | ans ✓ | ev P/R | warn P/R | miss R |
|---|---|---|---|---|---|---|---|---|---|:---:|:---:|---:|---:|---:|
| R2-001 | current | OBJ | objective_value | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-002 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-003 | current | STRUCT | new_customer_assignment | _unscored_ | partially_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-004 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-005 | current | STRUCT | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-006 | current | SCHEDULE | route_end_time | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-007 | current | SCHEDULE | customer_arrival | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-008 | target_extension | SCHEDULE | customer_arrival | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-009 | current | STRUCT | same_route_boolean | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-010 | target_extension | STRUCT | full_route_listing | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-011 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-012 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-013 | target_extension | OBJ | objective_delta | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-014 | target_extension | OBJ | objective_value | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-015 | target_extension | SCHEDULE | route_end_time | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-016 | current | OBJ | objective_value | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-017 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-018 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-019 | current | OBJ | objective_value | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-020 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-026 | current | OBJ | objective_delta | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-021 | target_extension | OBJ | objective_value | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-022 | target_extension | OBJ | objective_value | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-023 | target_extension | OBJ | objective_value | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-024 | target_extension | OBJ | objective_delta | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-025 | target_extension | OBJ | objective_delta | _unscored_ | partially_answerable | — | partial_answer_with_warning | — | missing | — | — | — | — | — |
| R2-027 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-028 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-029 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-030 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-031 | current | PLAN_VALIDITY | feasibility_status | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-032 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-033 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-034 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-035 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-036 | target_extension | PLAN_VALIDITY | feasibility_status | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-037 | current | STRUCT | route_count | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-038 | current | STRUCT | route_count | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-039 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-040 | current | STRUCT | single_customer_route_membership | single_customer_route_membership | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-041 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-042 | current | STRUCT | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-043 | current | STRUCT | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-044 | current | STRUCT | new_customer_assignment | _unscored_ | partially_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-045 | current | STRUCT | single_customer_route_membership | _unscored_ | answerable | — | direct_answer_with_warning | — | missing | — | — | — | — | — |
| R2-046 | current | STRUCT | same_route_boolean | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-047 | target_extension | STRUCT | single_customer_route_membership | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-048 | target_extension | STRUCT | full_route_listing | full_route_listing | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-049 | target_extension | STRUCT | full_route_listing | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-050 | current | SCHEDULE | customer_arrival | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-051 | current | SCHEDULE | lateness_summary | lateness_summary | answerable | answerable | direct_answer | direct_answer | parsed | ✓ | ✓ | 1.000/1.000 | 1.000/1.000 | 1.000 |
| R2-052 | current | SCHEDULE | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-053 | current | SCHEDULE | lateness_summary | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-054 | current | SCHEDULE | lateness_summary | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-055 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |
| R2-056 | current | SCHEDULE | customer_arrival | _unscored_ | answerable | — | direct_answer | — | missing | — | — | — | — | — |
| R2-057 | current | SCHEDULE | before_after_comparison | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-058 | target_extension | SCHEDULE | customer_arrival | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-059 | target_extension | SCHEDULE | route_end_time | _unscored_ | not_answerable | — | useful_refusal | — | missing | — | — | — | — | — |
| R2-060 | current | SCHEDULE | route_end_time | route_end_time | answerable | answerable | direct_answer_with_warning | direct_answer_with_warning | parsed | ✓ | ✓ | 0.500/1.000 | 1.000/1.000 | 1.000 |

## 7. Unscored cases

- `R2-001` parse_status=missing notes=no parsed row
- `R2-002` parse_status=missing notes=no parsed row
- `R2-003` parse_status=missing notes=no parsed row
- `R2-004` parse_status=missing notes=no parsed row
- `R2-005` parse_status=missing notes=no parsed row
- `R2-006` parse_status=missing notes=no parsed row
- `R2-007` parse_status=missing notes=no parsed row
- `R2-008` parse_status=missing notes=no parsed row
- `R2-009` parse_status=missing notes=no parsed row
- `R2-010` parse_status=missing notes=no parsed row
- `R2-011` parse_status=missing notes=no parsed row
- `R2-012` parse_status=missing notes=no parsed row
- `R2-013` parse_status=missing notes=no parsed row
- `R2-014` parse_status=missing notes=no parsed row
- `R2-015` parse_status=missing notes=no parsed row
- `R2-016` parse_status=missing notes=no parsed row
- `R2-017` parse_status=missing notes=no parsed row
- `R2-018` parse_status=missing notes=no parsed row
- `R2-019` parse_status=missing notes=no parsed row
- `R2-020` parse_status=missing notes=no parsed row
- `R2-026` parse_status=missing notes=no parsed row
- `R2-021` parse_status=missing notes=no parsed row
- `R2-022` parse_status=missing notes=no parsed row
- `R2-023` parse_status=missing notes=no parsed row
- `R2-024` parse_status=missing notes=no parsed row
- `R2-025` parse_status=missing notes=no parsed row
- `R2-027` parse_status=missing notes=no parsed row
- `R2-028` parse_status=missing notes=no parsed row
- `R2-029` parse_status=missing notes=no parsed row
- `R2-030` parse_status=missing notes=no parsed row
- `R2-031` parse_status=missing notes=no parsed row
- `R2-032` parse_status=missing notes=no parsed row
- `R2-033` parse_status=missing notes=no parsed row
- `R2-034` parse_status=missing notes=no parsed row
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
- `R2-047` parse_status=missing notes=no parsed row
- `R2-049` parse_status=missing notes=no parsed row
- `R2-050` parse_status=missing notes=no parsed row
- `R2-052` parse_status=missing notes=no parsed row
- `R2-053` parse_status=missing notes=no parsed row
- `R2-054` parse_status=missing notes=no parsed row
- `R2-056` parse_status=missing notes=no parsed row
- `R2-057` parse_status=missing notes=no parsed row
- `R2-058` parse_status=missing notes=no parsed row
- `R2-059` parse_status=missing notes=no parsed row


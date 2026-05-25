# D-Final Axis 3 Live Evaluation Report

_Run date: 2026-05-22_  
_Mode: hybrid\_guarded_  
_LLM live: True_  

---

## 1. Summary metrics

### Overall

| Metric | Value |
|---|---|
| n_cases | 24 |
| intent_correct | 24/24 |
| answerability_correct | 24/24 |
| behavior_class_correct | 24/24 |
| evidence_precision | 0.3833 |
| evidence_recall | 0.4167 |
| warning_precision | 1.0 |
| warning_recall | 1.0 |
| unknown_rate | 0.0 |
| wrong_adjacent_intent_rate | 0.0 |
| llm_invocation_count | 8 |
| fallback_count | 0 |
| schema_invalid_count | 0 |
| regressions_vs_d1 | 0 |

### By split

| Metric | dev (12) | heldout (12) | overall (24) |
|---|---:|---:|---:|
| intent_correct | 12/12 | 12/12 | 24/24 |
| answerability_correct | 12/12 | 12/12 | 24/24 |
| behavior_class_correct | 12/12 | 12/12 | 24/24 |
| evidence_precision | 0.3833 | 0.3833 | 0.3833 |
| evidence_recall | 0.4167 | 0.4167 | 0.4167 |
| warning_precision | 1.0 | 1.0 | 1.0 |
| warning_recall | 1.0 | 1.0 | 1.0 |
| unknown_rate | 0.0 | 0.0 | 0.0 |
| wrong_adjacent_rate | 0.0 | 0.0 | 0.0 |
| llm_invocations | 4 | 4 | 8 |
| fallback_count | 0 | 0 | 0 |
| schema_invalid | 0 | 0 | 0 |
| regressions_vs_d1 | 0 | 0 | 0 |

### By subtype

| Subtype | n | intent_correct | behavior_class_correct | llm_invocations |
|---|---:|---:|---:|---:|
| cost_synonym | 3 | 3/3 | 3/3 | 3 |
| entity_synonym | 5 | 5/5 | 5/5 | 4 |
| feasibility_synonym | 4 | 4/4 | 4/4 | 0 |
| operator_colloquial | 2 | 2/2 | 2/2 | 1 |
| paraphrase | 2 | 2/2 | 2/2 | 0 |
| schedule_synonym | 8 | 8/8 | 8/8 | 0 |

---

## 2. Comparison vs C0 / D1 / analytical D-Final

| System | n | intent_correct | behavior_class_correct | regressions_vs_d1 | source |
|---|---:|---:|---:|---:|---|
| C0 baseline | 24 | 15/24 | (see D1 report) | n/a | D1 stress report |
| D1 live | 24 | 24/24 | (see D1 report) | n/a | D1 stress report |
| D-Final analytical | 24 | 24/24 | see report | 0 | d_final_axis3_report.csv |
| **D-Final live** | 24 | **24/24** | **24/24** | **0** | this run |

---

## 3. Does the live result confirm the analytical derivation?

**CONFIRMED (intent).** Live D-Final achieves 24/24 intent accuracy with 0 regressions vs D1, matching the analytical prediction (intent_correct=24/24, regressions=0).

**EXCEEDS analytical (behavior_class).** The analytical derivation predicted 21/24 behavior_class_correct (3 failures on S1D-08, S1D-09, S1H-10 due to an assumed route_indexing_ambiguity warning gap inherited from D1). The live run achieved **24/24** — the warning IS correctly fired for vehicle/truck-prefixed route_end_time queries. The analytical prediction was conservatively wrong on this sub-metric.

The D3 warning layer fires `route_indexing_ambiguity` based on the `route_end_time` intent itself, not on whether the prompt uses "route" vs. "vehicle"/"truck" phrasing. The analytical derivation incorrectly assumed the warning would be absent for vehicle-prefixed queries.

### Analytical vs live, case by case

| case_id | gold | d1 | analytical_final | live_final | match | note |
|---|---|---|---|---|---|---|
| S1D-01 | objective_value | objective_value | objective_value | objective_value | ✓ |  |
| S1D-02 | feasibility_status | feasibility_status | feasibility_status | feasibility_status | ✓ |  |
| S1D-03 | feasibility_status | feasibility_status | feasibility_status | feasibility_status | ✓ |  |
| S1D-04 | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | ✓ |  |
| S1D-05 | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | ✓ |  |
| S1D-06 | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | ✓ |  |
| S1D-07 | full_route_listing | full_route_listing | full_route_listing | full_route_listing | ✓ |  |
| S1D-08 | route_end_time | route_end_time | route_end_time | route_end_time | ✓ |  |
| S1D-09 | route_end_time | route_end_time | route_end_time | route_end_time | ✓ |  |
| S1D-10 | customer_arrival | customer_arrival | customer_arrival | customer_arrival | ✓ |  |
| S1D-11 | lateness_summary | lateness_summary | lateness_summary | lateness_summary | ✓ |  |
| S1D-12 | lateness_summary | lateness_summary | lateness_summary | lateness_summary | ✓ |  |
| S1H-01 | objective_value | objective_value | objective_value | objective_value | ✓ |  |
| S1H-02 | objective_value | objective_value | objective_value | objective_value | ✓ |  |
| S1H-03 | feasibility_status | feasibility_status | feasibility_status | feasibility_status | ✓ |  |
| S1H-04 | feasibility_status | feasibility_status | feasibility_status | feasibility_status | ✓ |  |
| S1H-05 | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | ✓ |  |
| S1H-06 | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | single_customer_route_membership | ✓ |  |
| S1H-07 | full_route_listing | full_route_listing | full_route_listing | full_route_listing | ✓ |  |
| S1H-08 | full_route_listing | full_route_listing | full_route_listing | full_route_listing | ✓ |  |
| S1H-09 | route_end_time | route_end_time | route_end_time | route_end_time | ✓ |  |
| S1H-10 | route_end_time | route_end_time | route_end_time | route_end_time | ✓ |  |
| S1H-11 | customer_arrival | customer_arrival | customer_arrival | customer_arrival | ✓ |  |
| S1H-12 | lateness_summary | lateness_summary | lateness_summary | lateness_summary | ✓ |  |

---

## 4. Per-case detail

| case_id | split | subtype | prompt | gold | final | correct | adapter | conf | fallback | schema_valid | regression |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S1D-01 | dev | cost_synonym | What score did the solver give this plan? | objective_value | objective_value | ✓ | d1 | 1.00 | False | True | False |
| S1D-02 | dev | feasibility_synonym | Can this plan actually be driven as-is? | feasibility_status | feasibility_status | ✓ | d1 | 1.00 | False | True | False |
| S1D-03 | dev | feasibility_synonym | Is the route plan valid under the current constrai… | feasibility_status | feasibility_status | ✓ | d1 | 1.00 | False | True | False |
| S1D-04 | dev | operator_colloquial | Where did customer 42 get placed? | single_customer_route_membership | single_customer_route_membership | ✓ | d1 | 1.00 | False | True | False |
| S1D-05 | dev | entity_synonym | What run contains customer 42? | single_customer_route_membership | single_customer_route_membership | ✓ | d1 | 1.00 | False | True | False |
| S1D-06 | dev | entity_synonym | Which truck has customer 17 on it today? | single_customer_route_membership | single_customer_route_membership | ✓ | d1 | 1.00 | False | True | False |
| S1D-07 | dev | entity_synonym | Give me the full set of vehicle runs. | full_route_listing | full_route_listing | ✓ | d1 | 0.90 | False | True | False |
| S1D-08 | dev | schedule_synonym | When does vehicle 1 close out? | route_end_time | route_end_time | ✓ | d1 | 0.90 | False | True | False |
| S1D-09 | dev | schedule_synonym | When is vehicle 1 finished? | route_end_time | route_end_time | ✓ | d1 | 0.90 | False | True | False |
| S1D-10 | dev | schedule_synonym | When does customer 42 get served? | customer_arrival | customer_arrival | ✓ | d1 | 1.00 | False | True | False |
| S1D-11 | dev | schedule_synonym | Does anyone miss their promised window? | lateness_summary | lateness_summary | ✓ | d1 | 1.00 | False | True | False |
| S1D-12 | dev | operator_colloquial | Which customers fall behind schedule? | lateness_summary | lateness_summary | ✓ | d1 | 0.90 | False | True | False |
| S1H-01 | heldout | cost_synonym | How expensive is the current routing solution over… | objective_value | objective_value | ✓ | d1 | 1.00 | False | True | False |
| S1H-02 | heldout | cost_synonym | What value is the optimizer assigning to this plan… | objective_value | objective_value | ✓ | d1 | 1.00 | False | True | False |
| S1H-03 | heldout | feasibility_synonym | Is the proposed routing plan executable? | feasibility_status | feasibility_status | ✓ | d1 | 1.00 | False | True | False |
| S1H-04 | heldout | feasibility_synonym | Can the proposed set of routes be carried out? | feasibility_status | feasibility_status | ✓ | d1 | 1.00 | False | True | False |
| S1H-05 | heldout | entity_synonym | Which vehicle is customer 42 assigned to? | single_customer_route_membership | single_customer_route_membership | ✓ | d1 | 1.00 | False | True | False |
| S1H-06 | heldout | entity_synonym | Which truck has customer 12 right now? | single_customer_route_membership | single_customer_route_membership | ✓ | d1 | 1.00 | False | True | False |
| S1H-07 | heldout | paraphrase | Show me every route in the plan. | full_route_listing | full_route_listing | ✓ | d1 | 0.90 | False | True | False |
| S1H-08 | heldout | paraphrase | List the complete route plan. | full_route_listing | full_route_listing | ✓ | d1 | 0.90 | False | True | False |
| S1H-09 | heldout | schedule_synonym | At what time is route 1 done for the day? | route_end_time | route_end_time | ✓ | d1 | 0.90 | False | True | False |
| S1H-10 | heldout | schedule_synonym | When does truck 1 complete its run? | route_end_time | route_end_time | ✓ | d1 | 0.90 | False | True | False |
| S1H-11 | heldout | schedule_synonym | What time does the driver reach customer 17? | customer_arrival | customer_arrival | ✓ | d1 | 1.00 | False | True | False |
| S1H-12 | heldout | schedule_synonym | Are any stops served after their allowed time? | lateness_summary | lateness_summary | ✓ | d1 | 0.90 | False | True | False |

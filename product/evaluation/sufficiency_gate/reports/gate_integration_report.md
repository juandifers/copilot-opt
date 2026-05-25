# Sufficiency Gate Integration Report

Synthetic integration check driving the learned Stage A
sufficiency gate through D4's `decide_compute` policy. Each
case is evaluated twice — gate disabled and gate enabled —
and the deltas are surfaced below.

## Headline metrics

| Metric | Value |
| --- | --- |
| n_cases_evaluated | 13 |
| gate_invocation_count | 5 |
| no_decision_count | 1 |
| accept_current_count | 2 |
| recommend_recompute_count | 2 |
| overrides_blocked_by_hard_contract | 8 |
| unsafe_override_count | 0 |
| pyvrp_60s_recommendation_count | 0 |
| compute_decision_flips | 2 |

## Safety invariants

- `unsafe_override_count` MUST be 0.
- `pyvrp_60s_recommendation_count` MUST be 0.

- Safe: True
- No pyvrp_60s recommendation: True

## Per-case results

| case_id | description | baseline_mode | gated_mode | gated_action | gate_decision | p_suff | threshold | flip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G-001 | OBJ answer_from_payload — gate accepts current (high p) | answer_from_payload | answer_from_payload | none | accept_current | 0.999 | 0.50 | False |
| G-002 | PLAN_VALIDITY answer_from_payload — gate flips to recompute | answer_from_payload | needs_recompute | run_pyvrp_10s | recommend_recompute | 0.002 | 0.50 | True |
| G-003 | STRUCT route count — gate consulted on answer_from_payload | answer_from_payload | answer_from_payload | none | accept_current | 0.996 | 0.95 | False |
| G-004 | SCHEDULE customer arrival — gate consulted on answer_from_payload | answer_from_payload | needs_recompute | run_pyvrp_10s | recommend_recompute | 0.960 | 0.98 | True |
| G-005 | Unsupported (driver preferences) — gate suppressed | unsupported | unsupported | unsupported | none |  |  | False |
| G-006 | Clarification (can you improve this) — gate suppressed | clarification_needed | clarification_needed | ask_clarification | none |  |  | False |
| G-007 | Explicit recompute (what if) — gate suppressed | needs_recompute | needs_recompute | run_pyvrp_10s | none |  |  | False |
| G-008 | Comparison without diff — gate suppressed | needs_comparison_payload | needs_comparison_payload | build_comparison_payload | none |  |  | False |
| G-009 | Causal explanation — gate suppressed | partial_from_payload | partial_from_payload | none | none |  |  | False |
| G-010 | Partial answerability (D2) — gate suppressed | partial_from_payload | partial_from_payload | none | none |  |  | False |
| G-011 | not_answerable (missing fields) — gate suppressed | clarification_needed | clarification_needed | ask_clarification | none |  |  | False |
| G-012 | Overview intent — gate not calibrated for OVERVIEW family | answer_from_payload | answer_from_payload | none | none |  |  | False |
| G-013 | Empty contexts — gate returns no_decision | answer_from_payload | answer_from_payload | none | no_decision |  | 0.50 | False |

## Examples where the gate changed the compute decision

- **G-002** `feasibility_status` — baseline `answer_from_payload` → gated `needs_recompute` (`run_pyvrp_10s`), p=0.002 < threshold=0.50.
- **G-004** `customer_arrival` — baseline `answer_from_payload` → gated `needs_recompute` (`run_pyvrp_10s`), p=0.960 < threshold=0.98.

## Examples where the gate abstained because hard contract logic dominated

- **G-005** `objective_value` — baseline `unsupported` blocked the gate (hard contract precedence).
- **G-006** `objective_value` — baseline `clarification_needed` blocked the gate (hard contract precedence).
- **G-007** `objective_value` — baseline `needs_recompute` blocked the gate (hard contract precedence).
- **G-008** `before_after_comparison` — baseline `needs_comparison_payload` blocked the gate (hard contract precedence).
- **G-009** `route_count` — baseline `partial_from_payload` blocked the gate (hard contract precedence).
- **G-010** `objective_value` — baseline `partial_from_payload` blocked the gate (hard contract precedence).
- **G-011** `objective_value` — baseline `clarification_needed` blocked the gate (hard contract precedence).
- **G-012** `perturbation_summary` — baseline `answer_from_payload` blocked the gate (hard contract precedence).

## Regression check

Per-suite pass/fail counts from the parallel pytest run.
These numbers are recorded by the maintainer and pasted in
below when this report is regenerated.

- D4: see `tests/system_d4` — all gate tests pass; no new failures.
- D5 (recompute_service path): unchanged; gate does not run when   `decide_compute` is invoked from the recompute-service request   validator (no perturbation_context/action_context passed there).
- D-Final semantic holdout: unchanged (gate is off by default;   enabling it does not alter intent classification, only the   compute-decision suggestion for `answer_from_payload` cases on   OBJ/PV/STRUCT/SCHEDULE).

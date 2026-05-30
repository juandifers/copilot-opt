# Self-consistency smoke run (20260530_123711)

- corpus rows scored: **50** (focus_failures=True, limit=50, n=5, temperature=0.5)
- control unknown-rate:   22/50 = **44.0%**
- treatment unknown-rate: 19/50 = **38.0%**
- Δ unknown-rate: **-6.0 pp** (treatment − control)
- agreement rate (control intent == treatment intent): **92.0%** (46/50)
- treatment tie_break fired: **0** rows

> No statistical-significance claim. These are raw deltas; a full-corpus run is needed to draw conclusions.

## Disagreement rows (treatment intent ≠ control intent)

| case_id | category | control | treatment | samples | tie_break |
|---|---|---|---|---|---|
| OP-028 | prioritized_diagnosis | `unknown` | `what_to_watch` | what_to_watch what_to_watch what_to_watch what_to_watch what_to_watch | False |
| OP-044 | comparison | `before_after_comparison` | `route_impact_summary` | route_impact_summary route_impact_summary route_impact_summary route_impact_summary route_impact_summary | False |
| OP-059 | evaluation | `unknown` | `evaluate_plan_acceptability` | evaluate_plan_acceptability unknown evaluate_plan_acceptability evaluate_plan_acceptability unknown | False |
| OP-062 | risk_fragility | `unknown` | `what_to_watch` | what_to_watch what_to_watch what_to_watch what_to_watch what_to_watch | False |

## Treatment intent distribution

- `unknown`: 19
- `scenario_summary`: 6
- `what_to_watch`: 6
- `evaluate_plan_acceptability`: 6
- `before_after_comparison`: 5
- `solution_summary`: 2
- `single_customer_route_membership`: 1
- `full_route_listing`: 1
- `customer_arrival`: 1
- `perturbation_summary`: 1
- `route_impact_summary`: 1
- `evaluate_dimension_acceptability`: 1

## Files

- per-row CSV: `product/evaluation/reports/self_consistency_v1/smoke_run_20260530_123711.csv`
- this summary: `product/evaluation/reports/self_consistency_v1/smoke_run_20260530_123711_summary.md`

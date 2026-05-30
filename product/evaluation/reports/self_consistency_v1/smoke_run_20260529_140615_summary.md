# Self-consistency smoke run (20260529_140615)

- corpus rows scored: **50** (focus_failures=True, limit=50, n=5, temperature=0.5)
- control unknown-rate:   24/50 = **48.0%**
- treatment unknown-rate: 24/50 = **48.0%**
- Δ unknown-rate: **+0.0 pp** (treatment − control)
- agreement rate (control intent == treatment intent): **96.0%** (48/50)
- treatment tie_break fired: **0** rows

> No statistical-significance claim. These are raw deltas; a full-corpus run is needed to draw conclusions.

## Disagreement rows (treatment intent ≠ control intent)

| case_id | category | control | treatment | samples | tie_break |
|---|---|---|---|---|---|
| OP-033 | prioritized_diagnosis | `unknown` | `evaluate_dimension_acceptability` | evaluate_dimension_acceptability evaluate_dimension_acceptability evaluate_dimension_acceptability evaluate_dimension_acceptability evaluate_dimension_acceptability | False |
| OP-057 | evaluation | `evaluate_plan_acceptability` | `unknown` | evaluate_plan_acceptability evaluate_plan_acceptability evaluate_plan_acceptability evaluate_plan_acceptability evaluate_dimension_acceptability | False |

## Treatment intent distribution

- `unknown`: 24
- `scenario_summary`: 6
- `before_after_comparison`: 6
- `evaluate_dimension_acceptability`: 3
- `evaluate_plan_acceptability`: 3
- `solution_summary`: 2
- `what_to_watch`: 2
- `single_customer_route_membership`: 1
- `full_route_listing`: 1
- `customer_arrival`: 1
- `route_impact_summary`: 1

## Files

- per-row CSV: `product/evaluation/reports/self_consistency_v1/smoke_run_20260529_140615.csv`
- this summary: `product/evaluation/reports/self_consistency_v1/smoke_run_20260529_140615_summary.md`

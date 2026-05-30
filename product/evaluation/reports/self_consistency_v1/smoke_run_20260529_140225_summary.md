# Self-consistency smoke run (20260529_140225)

- corpus rows scored: **50** (focus_failures=True, limit=50, n=5, temperature=0.5)
- control unknown-rate:   25/50 = **50.0%**
- treatment unknown-rate: 21/50 = **42.0%**
- Δ unknown-rate: **-8.0 pp** (treatment − control)
- agreement rate (control intent == treatment intent): **86.0%** (43/50)
- treatment tie_break fired: **0** rows

> No statistical-significance claim. These are raw deltas; a full-corpus run is needed to draw conclusions.

## Disagreement rows (treatment intent ≠ control intent)

| case_id | category | control | treatment | samples | tie_break |
|---|---|---|---|---|---|
| OP-022 | prioritized_diagnosis | `unknown` | `what_to_watch` |  | False |
| OP-028 | prioritized_diagnosis | `unknown` | `what_to_watch` |  | False |
| OP-044 | comparison | `route_impact_summary` | `before_after_comparison` |  | False |
| OP-057 | evaluation | `unknown` | `evaluate_plan_acceptability` |  | False |
| OP-061 | risk_fragility | `unknown` | `evaluate_dimension_acceptability` |  | False |
| OP-361 | risk_fragility | `unknown` | `evaluate_dimension_acceptability` |  | False |
| OP-073 | justification | `what_to_watch` | `unknown` |  | False |

## Treatment intent distribution

- `unknown`: 21
- `before_after_comparison`: 7
- `scenario_summary`: 6
- `what_to_watch`: 4
- `evaluate_plan_acceptability`: 4
- `evaluate_dimension_acceptability`: 3
- `solution_summary`: 2
- `single_customer_route_membership`: 1
- `full_route_listing`: 1
- `customer_arrival`: 1

## Files

- per-row CSV: `product/evaluation/reports/self_consistency_v1/smoke_run_20260529_140225.csv`
- this summary: `product/evaluation/reports/self_consistency_v1/smoke_run_20260529_140225_summary.md`

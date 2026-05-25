# API contract — D5 recompute

D5 adds two endpoints and one optional field to the
`/copilot/ask` response shape.

## Response enrichment on `/copilot/ask`

The response now carries a `ui_actions` array:

```json
{
  "...": "existing D4 contract fields (unchanged)",
  "compute_decision": { "...": "unchanged D4 shape" },
  "ui_actions": [
    {
      "type": "recompute",
      "label": "Run recompute",
      "action": "run_pyvrp_10s",
      "enabled": true,
      "requires_confirmation": true,
      "endpoint": "/scenarios/<scenario_id>/recompute",
      "method": "POST",
      "reason": "<copy of compute_decision.reason>",
      "expected_runtime_seconds": 10.0
    }
  ]
}
```

Invariant: `ui_actions` is **always** present (possibly empty). It is
non-empty iff `compute_decision.mode == "needs_recompute"` AND
`compute_decision.recommended_action` is one of the deployable rungs.

Frontend rendering rule:

```typescript
if (response.ui_actions.length > 0) {
  // Render the affordance using ui_actions[0].
}
```

## `POST /scenarios/{instance_id}/{perturbation_id}/recompute`

Request body:

```json
{
  "prompt": "What if we add customer 999 near route 4?",
  "requested_action": "run_pyvrp_10s",
  "perturbation": {
    "type": "insert_customer",
    "customer": {
      "customer_id": 999,
      "x": 42.1, "y": 51.3,
      "demand": 8,
      "time_window_start": 300, "time_window_end": 600,
      "service_time": 90
    }
  },
  "confirm": true
}
```

- `prompt` is required.
- `requested_action` must be in `{run_reuse_direct, run_nearest_neighbor, run_clarke_wright, run_pyvrp_10s}`.
- `perturbation` is optional; required only when the executor needs it.
  No executor currently accepts a request-level perturbation overlay;
  passing one returns 501 `perturbation_application_not_implemented`.
- `confirm` MUST be `true`.

Implemented today: `run_reuse_direct`, `run_clarke_wright`,
`run_pyvrp_10s`. `run_nearest_neighbor` returns a structured 501.
`run_clarke_wright` reuses the existing CVRP-style parallel-savings
construction and evaluates under VRPTW on top — it may report honest
VRPTW infeasibility, and the backend does not silently degrade to
`run_pyvrp_10s` when CW produces an infeasible plan.

### Success (200)

```json
{
  "status": "completed",
  "source_scenario_id": "C1_2_1__TT_5",
  "new_scenario_id": "C1_2_1__TT_5__run_pyvrp_10s__20260521_153000",
  "action_used": "run_pyvrp_10s",
  "runtime_seconds": 8.7,
  "summary": {
    "feasible": true,
    "objective": 2912.4,
    "n_routes": 23,
    "n_late_customers": 1
  },
  "artifacts": {
    "scenario_path": "product/api/runtime/recompute_runs/.../scenario.json",
    "payload_path":  "product/api/runtime/recompute_runs/.../payload.json"
  },
  "next_actions": [
    {"type": "load_scenario", "scenario_id": "...", "label": "Open recomputed scenario"},
    {"type": "ask_again",    "scenario_id": "...", "label": "Ask the original question on the recomputed scenario"}
  ]
}
```

### Structured errors

| HTTP | code | When |
|---|---|---|
| 400 | `confirmation_required` | `confirm != true` |
| 400 | `invalid_scenario_id`    | malformed scenario id |
| 400 | `invalid_action`         | unknown action name |
| 400 | `forbidden_action`       | `pyvrp_60s` family |
| 400 | `invalid_perturbation`   | malformed or under-specified |
| 400 | `invalid_prompt`         | empty prompt |
| 404 | `scenario_not_found`     | unknown source scenario |
| 404 | `instance_geometry_not_found` | source `.vrp` file missing |
| 409 | `recompute_not_recommended` | D4 mode != `needs_recompute` |
| 409 | `action_mismatch`        | action ≠ D4 recommended |
| 501 | `action_not_implemented` | deployable but unimplemented |
| 501 | `perturbation_application_not_implemented` | perturbation provided but executor cannot apply |
| 400 | `payload_missing_routes` | `run_reuse_direct` invoked on a payload with no routes |

All wrapped in the standard envelope:

```json
{ "error": { "code": "...", "message": "...", "detail": { } } }
```

## `GET /recompute_runs/{new_scenario_id}`

Loads the materialized runtime scenario document written by the
recompute service. Returns 404 `runtime_scenario_not_found` if the
directory is missing.

## Solver invariant

`/copilot/ask` never invokes a solver. The only path that runs a
solver is the `/scenarios/.../recompute` handler, and only after the
full validation chain succeeds.

## pyvrp_60s

The benchmark reference label generator. It is **never** in
`ui_actions`, **never** in `ALLOWED_ACTIONS`, and **never** in
`IMPLEMENTED_ACTIONS`. Any client that requests `pyvrp_60s` (in any
form) receives a 400 `forbidden_action`.

## Runtime artifact policy

Runtime artifacts live under `product/api/runtime/recompute_runs/` and
are **not benchmark truth**. They are gitignored, safe to delete, and
not referenced by any evaluation harness. They exist purely so the
local dashboard can load a recomputed scenario back into the UI.

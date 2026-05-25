# System D5 — Closeout

D5 implements the operator-authorized recompute execution layer. It is
the natural successor of D4 (compute-decision recommendation) and
closes the loop documented in `system_d4/reports/api_contract_update.md`
under "Future: `POST /recompute`".

## Purpose

Turn D4's `needs_recompute` recommendation into a controlled, explicit,
operator-authorized solver execution that materializes a new scenario
the dashboard can load.

## D4 vs D5

| | D4 | D5 |
|---|---|---|
| Role | Recommendation | Execution |
| Triggered by | Every `/copilot/ask` | Explicit operator click |
| Side effects | None | Solver run, file write |
| Endpoint | `POST /copilot/ask` | `POST /scenarios/{scenario_id}/recompute` |
| Confirmation | n/a | Requires `confirm=true` |
| Solver call | Never | Only inside this layer |

## API endpoints added or changed

| Method | Path | Behavior |
|---|---|---|
| POST | `/copilot/ask` | Now emits a `ui_actions` array. Single `recompute` action when D4 says `needs_recompute`. |
| POST | `/scenarios/{instance_id}/{perturbation_id}/recompute` | New. Validates + executes the recompute. |
| GET | `/recompute_runs/{new_scenario_id}` | New. Loads the materialized runtime scenario. |

`/copilot/ask` does not run any solver. The `ui_actions` array is pure
response shaping over D4's `compute_decision`.

## Allowed deployable actions

```
run_reuse_direct
run_nearest_neighbor
run_clarke_wright
run_pyvrp_10s
```

Mirrors `product.evaluation.system_d4.DEPLOYABLE_RECOMPUTE_ACTIONS`.

## Forbidden actions

```
pyvrp_60s, run_pyvrp_60s
pyvrp_60s_seed2, run_pyvrp_60s_seed2
pyvrp_60s_seed3, run_pyvrp_60s_seed3
```

`pyvrp_60s` was the benchmark reference label generator; it is never
deployable. The endpoint rejects any of these names at validation with
HTTP 400 and `error.code == "forbidden_action"`.

## Validation rules

See `system_d5/design.md` for the ordered list.

Structured error codes (all wrapped in the standard `{"error": {...}}`
envelope):

| HTTP | code | When |
|---|---|---|
| 400 | `confirmation_required` | `confirm != true` |
| 400 | `invalid_scenario_id` | scenario_id missing `__` separator |
| 404 | `scenario_not_found` | unknown `(instance, perturbation)` |
| 400 | `forbidden_action` | `pyvrp_60s` family |
| 400 | `invalid_action` | not on the deployable ladder |
| 400 | `invalid_perturbation` | malformed/unknown perturbation |
| 400 | `invalid_prompt` | empty prompt |
| 409 | `recompute_not_recommended` | D4 does not recommend recompute |
| 409 | `action_mismatch` | requested ≠ D4 recommended |
| 501 | `action_not_implemented` | action allowed but not implemented |
| 501 | `perturbation_application_not_implemented` | perturbation provided for an executor that cannot apply it |
| 400 | `payload_missing_routes` | `run_reuse_direct` against a payload with no routes |
| 404 | `instance_geometry_not_found` | VRPTW `.vrp` file missing |

## Runtime artifact policy

Artifacts live under `product/api/runtime/recompute_runs/<new_scenario_id>/`.
This directory is:

- gitignored,
- local-dev / thesis-demo only,
- never read by any benchmark or evaluation harness,
- safe to delete between sessions.

`new_scenario_id` format: `<source>__<action>__<YYYYMMDD_HHMMSS>`.

## Implementation status

| Action | Implemented? | Notes |
|---|---|---|
| `run_pyvrp_10s` | yes | Calls `solve_vrptw` on the underlying VRPTW instance, seed=1, 10 s. Returns 501 if a request-level perturbation is provided. |
| `run_reuse_direct` | yes | Calls `evaluate_vrptw_solution` against the routes in the source payload. Returns 400 `payload_missing_routes` if the payload carries no routes. Returns 501 if a request-level perturbation is provided. |
| `run_clarke_wright` | yes | Constructs a fresh route plan via the existing parallel-savings heuristic, then evaluates it under VRPTW. May return `feasible=False` honestly when the savings plan violates time windows. Returns 501 if a request-level perturbation is provided. |
| `run_nearest_neighbor` | no | Returns 501 `action_not_implemented`. |
| `pyvrp_60s` (any seed) | forbidden | Returns 400 `forbidden_action`. |

`run_clarke_wright` is the cheap *replan* rung between the no-solve
`run_reuse_direct` (re-score existing routes) and the stronger
`run_pyvrp_10s` (bounded fresh solve). It reuses
`vrp_copilot_bench.solvers.heuristics.clarke_wright.construct` (a
CVRP-style parallel-savings algorithm) because the heuristic only
reads `n_customers`, `capacity`, and `demands` from the instance —
fields the VRPTW instance exposes. Time windows are honored at
*evaluation* time via `evaluate_vrptw_solution`; the response surfaces
the per-constraint breakdown so the operator can see whether a TW or
capacity violation is the cause of any reported infeasibility. **The
backend does not silently degrade to a stronger solver if CW produces
an infeasible plan** — the result is materialized and reported.

The `run_reuse_direct` summary carries the standard fields plus a
diagnostic breakdown for "is the current plan still feasible?" prompts:

```json
{
  "feasible": true,
  "objective": 2699.5,
  "n_routes": 20,
  "n_late_customers": 0,
  "feasible_capacity_only": true,
  "feasible_tw_only": true,
  "n_unserved_customers": 0
}
```

The breakdown lets the frontend distinguish *which* constraint a
"reuse the current plan" plan would violate under the operator's
hypothetical change.

The 501 responses are intentional: the contract surface is complete,
and the missing executors are local-dev follow-ups.

## Example `/copilot/ask` response with `ui_actions`

Request:

```json
POST /copilot/ask
{
  "scenario_id": "C105__TT_4",
  "prompt": "Find a better plan that reduces lateness.",
  "system": "d4"
}
```

Response (excerpt):

```json
{
  "system": "d4",
  "scenario_id": "C105__TT_4",
  "compute_decision": {
    "mode": "needs_recompute",
    "requires_recompute": true,
    "recommended_action": "run_pyvrp_10s",
    "expected_runtime_seconds": 10.0,
    "reason": "The prompt asks about a changed scenario..."
  },
  "ui_actions": [
    {
      "type": "recompute",
      "label": "Run recompute",
      "action": "run_pyvrp_10s",
      "enabled": true,
      "requires_confirmation": true,
      "endpoint": "/scenarios/C105__TT_4/recompute",
      "method": "POST",
      "reason": "The prompt asks about a changed scenario...",
      "expected_runtime_seconds": 10.0
    }
  ]
}
```

When the operator clicks "Run recompute", the frontend POSTs to the
endpoint named in `ui_actions[0].endpoint`.

## Example `/recompute` success response

```json
POST /scenarios/C105/TT_4/recompute
{
  "prompt": "Find a better plan that reduces lateness.",
  "requested_action": "run_pyvrp_10s",
  "confirm": true
}
```

Returns:

```json
{
  "status": "completed",
  "source_scenario_id": "C105__TT_4",
  "new_scenario_id": "C105__TT_4__run_pyvrp_10s__20260521_153000",
  "action_used": "run_pyvrp_10s",
  "runtime_seconds": 10.1,
  "summary": {
    "feasible": true,
    "objective": 828.94,
    "n_routes": 10,
    "n_late_customers": 0
  },
  "artifacts": {
    "scenario_path": ".../C105__TT_4__run_pyvrp_10s__20260521_153000/scenario.json",
    "payload_path": ".../C105__TT_4__run_pyvrp_10s__20260521_153000/payload.json"
  },
  "next_actions": [
    {"type": "load_scenario", "scenario_id": "...", "label": "Open recomputed scenario"},
    {"type": "ask_again", "scenario_id": "...", "label": "Ask the original question on the recomputed scenario"}
  ]
}
```

## Example structured 501 response

```json
POST /scenarios/C105/TT_4/recompute
{
  "prompt": "Use a nearest-neighbor heuristic to reroute the plan.",
  "requested_action": "run_nearest_neighbor",
  "confirm": true
}
```

Returns HTTP 501:

```json
{
  "error": {
    "code": "action_not_implemented",
    "message": "The requested recompute action is recognized but not implemented in this local demo backend.",
    "detail": {
      "requested_action": "run_nearest_neighbor",
      "allowed_actions": ["run_clarke_wright", "run_nearest_neighbor", "run_pyvrp_10s", "run_reuse_direct"],
      "implemented_actions": ["run_clarke_wright", "run_pyvrp_10s", "run_reuse_direct"]
    }
  }
}
```

## Example Clarke-Wright success (with honest infeasibility)

```json
POST /scenarios/C1_2_2/TW_5/recompute
{
  "prompt": "Run a cheap savings heuristic.",
  "requested_action": "run_clarke_wright",
  "confirm": true
}
```

Returns HTTP 200 — note that the summary surfaces *why* the plan is
infeasible (TW violations) rather than hiding it behind the top-level
`feasible` flag:

```json
{
  "status": "completed",
  "source_scenario_id": "C1_2_2__TW_5",
  "new_scenario_id": "C1_2_2__TW_5__run_clarke_wright__20260521_172144",
  "action_used": "run_clarke_wright",
  "runtime_seconds": 0.06,
  "summary": {
    "feasible": false,
    "objective": 2633.3,
    "n_routes": 19,
    "n_late_customers": 75,
    "feasible_capacity_only": true,
    "feasible_tw_only": false,
    "n_unserved_customers": 0
  }
}
```

The frontend can read the per-constraint flags to render an explicit
"capacity OK, time-window violations: 75 customers late" line.

## Tests

`tests/product_api/test_recompute_api.py` — 23 cases covering:

- `ui_actions` emitted iff `mode == needs_recompute`
- `/copilot/ask` does not call the recompute executor under any prompt
- `confirm` required (400)
- Unknown scenario (404)
- Invalid action (400)
- Forbidden `pyvrp_60s` family (400)
- Action mismatch with D4 recommendation (409)
- Recompute not recommended for answerable prompt (409)
- Invalid / under-specified perturbation (400)
- Unimplemented deployable action (501) — pins `run_nearest_neighbor`
- `run_reuse_direct` against a payload with no routes (400)
- Pre-execute validation paths do not trigger the executor
- `run_pyvrp_10s` success path (skipped when `pyvrp`/`vrplib` missing)
- `run_reuse_direct` success path (skipped when `pyvrp`/`vrplib` missing)
- `run_clarke_wright` success path + runtime artifacts + routes
- `run_clarke_wright` honest infeasibility reporting
- `run_clarke_wright` rejects perturbation overlay (501)
- Service-layer unit tests pinning allowed / implemented / forbidden sets

Regression: `tests/product_api/` (52/52), `tests/system_d{1..4}/`
(177/177). Locked Run 2 artifacts are unchanged.

## Limitations

- Three of the four deployable rungs (`run_reuse_direct`,
  `run_clarke_wright`, `run_pyvrp_10s`) are implemented;
  `run_nearest_neighbor` still returns 501.
- `run_reuse_direct` re-evaluates the source payload's routes — it
  cannot run against scenarios whose payload carries no routes
  (returns 400 `payload_missing_routes`).
- `run_clarke_wright` reuses the CVRP-style parallel-savings
  construction and applies the VRPTW evaluator on top. The
  construction step does not optimize for time windows, so the
  resulting plan may be VRPTW-infeasible even when the source plan was
  feasible. The response reports this honestly via
  `feasible_tw_only=false` and `n_late_customers > 0`; the backend
  does not silently fall back to a stronger solver.
- Recompute solves the *unperturbed* VRPTW instance fresh; applying
  the original perturbation (let alone a request-level one) on top of
  the loaded instance is not implemented and returns 501 when a
  perturbation is provided.
- No cancellation, no streaming, no job queue. Each request blocks
  the worker for up to ~12 s.
- No auth / rate limiting. The endpoint is for localhost-only dev.
- Runtime scenarios are not picked up by the canonical
  `/scenarios/{instance_id}/{perturbation_id}` route; they live under
  `/recompute_runs/{new_scenario_id}` instead. Loading them into the
  canonical scenario store would require a separate registry merge
  and is intentionally out of scope.

## Future work

- Production job queue (run in background, return `202 Accepted` with
  a job id).
- Progress streaming (Server-Sent Events) for in-flight solves.
- Cancellation endpoint.
- Implement `run_nearest_neighbor` via the existing
  `vrp_copilot_bench.solvers.heuristics.nearest_neighbor.construct`
  using the same VRPTW-evaluator-on-top pattern that
  `run_clarke_wright` already uses.
- A VRPTW-aware construction heuristic (currently `run_clarke_wright`
  is CVRP-style, with TW honored only at evaluation) so the savings
  rung can produce feasible plans more often on tight-window Solomon
  instances.
- Apply request-level perturbations to the loaded instance.
- Audit log of all recompute requests (success and failure).
- Cost / runtime display in the UI affordance.
- Learned sufficiency gate (D4 v2) feeding into D5 with calibrated
  confidence.
- A proper perturbation editor in the frontend.
- User-confirmation UX for high-cost actions.
- Wire runtime scenarios into a follow-up `/copilot/ask` against the
  new scenario id.

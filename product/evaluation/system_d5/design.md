# System D5 — Operator-Authorized Recompute Execution

## What D5 is

D5 is the recompute execution layer. It turns D4's
`compute_decision.mode == "needs_recompute"` recommendation into a
controlled, explicit, operator-authorized action.

```
User asks question
→ D4 says compute_decision.mode == "needs_recompute"
→ /copilot/ask returns a recompute UI action affordance
→ frontend renders a "Run recompute" button
→ operator clicks the button
→ /scenarios/{scenario_id}/recompute validates the request
→ backend runs the recommended deployable action
→ backend materializes a new scenario payload
→ frontend can load the recomputed scenario by new_scenario_id
→ copilot can answer follow-up questions on the new payload
```

The hard invariant: **`/copilot/ask` does not run a solver under any
circumstances.** D4 only recommends; D5 (and only D5) executes, and
only after explicit confirmation.

## What D5 is not

- Not an automatic recompute. The endpoint refuses requests without
  `confirm=true` and refuses prompts whose D4 mode is not
  `needs_recompute`.
- Not a production job queue. Cancellation, progress streaming,
  per-tenant rate limiting, and audit log are explicit future work.
- Not a re-implementation of solvers. D5 calls existing PyVRP wrappers
  (`vrp_copilot_bench.vrptw.solver.solve_vrptw`) via an adapter and
  reshapes the output into the dashboard scenario format.
- Not a learned policy. The validation and action selection are
  deterministic; the D4 decision is the only policy input.

## Action contract

```
ALLOWED_ACTIONS     = {run_reuse_direct, run_nearest_neighbor,
                       run_clarke_wright, run_pyvrp_10s}
IMPLEMENTED_ACTIONS = {run_reuse_direct, run_clarke_wright,
                       run_pyvrp_10s}                  ← local-dev demo
FORBIDDEN_ACTIONS   = {pyvrp_60s, run_pyvrp_60s,
                       pyvrp_60s_seed2, pyvrp_60s_seed3, ...}
```

The three implemented rungs form a cost ladder:

| Rung | Cost | What it does |
|---|---|---|
| `run_reuse_direct` | ~50 ms | Re-evaluates the source payload's routes via `evaluate_vrptw_solution`. No construction, no solve. |
| `run_clarke_wright` | ~100 ms | Constructs a new plan with parallel-savings (CVRP-style; existing `solvers.heuristics.clarke_wright.construct`), then evaluates under VRPTW. May surface honest TW infeasibility. |
| `run_pyvrp_10s` | ~10 s | Fresh bounded PyVRP solve, seed 1, 10 s. Returns a feasible plan when one exists at this budget. |

All three reuse the same evaluator (`evaluate_vrptw_solution`) so the
response shape and per-constraint feasibility breakdown
(`feasible_capacity_only`, `feasible_tw_only`, `n_unserved_customers`)
are uniform across rungs. The backend never silently degrades or
upgrades between rungs — the action that ran is the action that was
requested, and the reported feasibility is the truth.

`pyvrp_60s` and its seed variants are the *benchmark reference label
generator* and are not deployable. The endpoint rejects them at the
validation stage regardless of how the request is shaped.

Unimplemented deployable actions return HTTP 501 with
`error.code == "action_not_implemented"`, surfacing the full
`allowed_actions` and `implemented_actions` sets so the frontend can
disable the affordance accordingly.

## Validation order

1. `confirm == True`. Otherwise → 400 `confirmation_required`.
2. `scenario_id` is registered in the scenario store. Otherwise → 404
   `scenario_not_found`.
3. `requested_action` is not in `FORBIDDEN_ACTIONS`. Otherwise → 400
   `forbidden_action`.
4. `requested_action` is in `ALLOWED_ACTIONS`. Otherwise → 400
   `invalid_action`.
5. `perturbation`, if provided, has a known `type` and required fields.
   Otherwise → 400 `invalid_perturbation`.
6. `prompt` is non-empty. Otherwise → 400 `invalid_prompt`.
7. Re-run D4 on `(prompt, current payload)`. If its `mode` is not
   `needs_recompute` → 409 `recompute_not_recommended`.
8. `requested_action == d4.recommended_action`. Otherwise → 409
   `action_mismatch`.
9. Dispatch to the executor. Unimplemented actions → 501
   `action_not_implemented`.

The D4 re-run guards against a frontend trying to coerce a solver run
on a prompt D4 would have refused. The same validation runs whether or
not the frontend constructed the request from the D4-emitted UI action.

## Runtime artifact policy

Materialized recompute results live under
`product/api/runtime/recompute_runs/<new_scenario_id>/` and are:

- gitignored (`product/api/runtime/` is in `.gitignore`),
- safe to delete between runs,
- not benchmark truth (do not import them into any evaluation harness),
- not commingled with locked Run 2 artifacts.

Each runtime directory contains:

```
metadata.json   request + decision metadata + timestamps
payload.json    augmented payload + summary + diff
scenario.json   dashboard-shaped scenario document
diff.json       only when objective + feasibility delta computable
```

`new_scenario_id` is
`<source_scenario_id>__<action>__<YYYYMMDD_HHMMSS>`.

## Diff support

The diff block is computed lazily from the source payload and the
recomputed solution. When both sides have an `objective` (and
optionally a `feasible`), the diff carries `objective_delta_absolute`,
`objective_delta_percent`, and `feasibility_changed`. Route- and
customer-level deltas are deliberately *not* synthesized — they would
require alignment logic this layer does not yet implement.

## Why D5 is separate from D4

D4's job is to decide whether the *available payload* is sufficient.
That decision is small, deterministic, and side-effect-free; it is
safe to call on every `/copilot/ask` request. D5 is the side-effect
layer: it loads instance geometry, calls a solver, and writes files.
Conflating the two would make `/copilot/ask` a solver-trigger surface,
which is exactly what the architecture prohibits.

Separating them also makes D4 testable as a pure function and lets the
frontend treat the recompute affordance as a normal UI action: it has
its own endpoint, its own request body, and its own structured-error
contract.

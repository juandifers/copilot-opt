# VRPTW Copilot Dashboard API

A small, read-only HTTP API the dashboard frontend consumes. It is a
thin wrapper around the already-evaluated contract systems and the
Run 1 scenario artifacts; no business logic is added here.

## What this wraps

- **`c0`** — original deterministic Run 2 contract
  (`product/evaluation/run2_system_c.py`)
- **`d1`** — D1 semantic intent adapter
  (`product/evaluation/system_d1/d1_system_c.py`)
- **`d2`** — D1 + answerability / route-warning extension
  (`product/evaluation/system_d2/d2_system_c.py`)
- **`d3`** — D2 + causal-unsupported warning overlay
  (`product/evaluation/system_d3/d3_system_c.py`)
- **`d4`** — D3 + compute-decision / recompute-policy layer
  (`product/evaluation/system_d4/d4_system_c.py`)
- **`d5`** — operator-authorized recompute execution layer
  (`product/api/recompute_service.py`)

`d_final` is the default for `/copilot/ask` (promoted 2026-05-21 after
97.9% semantic holdout, 100% heldout, 0 regressions). `d5` is *not* a
chat system — it is a separate execution endpoint, see below.

Scenarios are loaded from
`experiment/results_RUN1/generator/full-run-v1.jsonl`
(via `payload_snapshot`) joined with `experiment/data/prompts.csv`.

## Running locally

```bash
uvicorn product.api.app:app --reload --host 127.0.0.1 --port 8000
```

The app allows CORS from `http://localhost:3000`, `http://localhost:5173`
and `http://localhost:6006` (and their `127.0.0.1` equivalents).

## Endpoints

### `GET /health`

```json
{
  "status": "ok",
  "run2_contract_base_commit": "18b4811a1f85c166ea3ba8c777dfc021b2a5f747",
  "run2_contract_base_tag": "run2-contract-extended",
  "current_git_commit": "<current sha>",
  "available_systems": ["c0", "d1", "d2", "d3", "d4"],
  "default_system": "d4"
}
```

### `GET /instances`

```json
{
  "instances": [
    {
      "instance_id": "C1_2_1",
      "family": "homberger200",
      "n_customers": 200,
      "available_perturbations": ["ST_3", "TT_5"]
    }
  ]
}
```

### `GET /scenarios/{instance_id}/{perturbation_id}`

Returns a frontend-ready scenario for map, route table, and schedule
visualization. Fields not present in the payload come back `null` and
are flagged `false` in `available_fields`.

```json
{
  "scenario_id": "C105__TT_4",
  "instance_id": "C105",
  "perturbation_id": "TT_4",
  "perturbation_summary": "Travel-time perturbation (TT_4)",
  "instance": {
    "depot": {"x": 40.0, "y": 50.0},
    "customers": [
      {
        "customer_id": 1,
        "x": 41.0, "y": 49.0,
        "demand": 10,
        "time_window_start": 0.0, "time_window_end": 1236.0,
        "service_time": 90.0
      }
    ],
    "vehicle_capacity": 200
  },
  "solution": {
    "feasible": null,
    "objective": null,
    "n_routes": null,
    "routes": null,
    "customer_schedule": [
      {
        "customer_id": 12,
        "route_idx": 0,
        "route_label": "Route 1",
        "position_in_route": 0,
        "arrival": 9.2, "service_start": 9.2, "service_end": 99.2,
        "time_window_start": 0.0, "time_window_end": 100.0,
        "is_late": false, "lateness_minutes": 0.0
      }
    ]
  },
  "baseline_solution": null,
  "diff": null,
  "available_fields": {
    "solution": true,
    "routes": false,
    "customer_schedule": true,
    "route_end_times": true,
    "baseline_solution": false,
    "diff": false,
    "objective_delta": false,
    "causal_diagnostics": false
  }
}
```

Every route-typed object always includes both `route_idx`
(zero-based internal) and `route_label` (display string starting at
`Route 1`).

Missing scenario → 404 with `{"error": {"code": "scenario_not_found", ...}}`.

### `POST /copilot/ask`

```json
{
  "scenario_id": "C105__TT_4",
  "prompt": "What time does route 3 finish?",
  "system": "d3"
}
```

`system` is optional; default `"d_final"`. `family` is also accepted
and defaults to the family of the underlying Run 1 prompt for the
scenario. Example response:

```json
{
  "system": "d_final",
  "scenario_id": "C105__TT_4",
  "intent": "route_end_time",
  "answerability": {"status": "answerable", "missing_fields": []},
  "behavior_class": "direct_answer_with_warning",
  "answer_text": "Route 3 finishes at 1234.8 min. Route numbers in this response are sequential position indices (starting at 1), not necessarily the labels shown in the original plan.",
  "evidence": [
    {
      "field_path": "route_end_times[route_idx=2].end_time",
      "value": 1234.8,
      "display_anchor": {
        "type": "route_end",
        "route_idx": 2,
        "route_label": "Route 3"
      }
    }
  ],
  "warnings": ["route_indexing_ambiguity"],
  "useful_refusal": null,
  "suggested_next_actions": [],
  "compute_decision": {
    "mode": "answer_from_payload",
    "requires_recompute": false,
    "recommended_action": "none",
    "..."  : "..."
  },
  "ui_actions": []
}
```

#### answer_text

`answer_text` is populated by a **deterministic template-based
verbalization renderer** (`product/copilot/verbalization.py`).

- The renderer makes **no LLM calls** — it reads from the structured
  contract fields (intent, evidence values, warnings, missing fields,
  compute decision) and applies templates to produce prose.
- The renderer was independently validated: 24/24 pass, 0 unsupported
  additions, 0 critical omissions, 0 numeric/entity errors, 100%
  warning and missing-field preservation.
- `answer_text` is a **display convenience**, not the source of truth.
  The structured fields (`evidence`, `warnings`, `missing_fields`,
  `compute_decision`, `ui_actions`) remain authoritative. The frontend
  should expose those fields too; `answer_text` may be shown first as
  a summary but must not be the only information exposed.
- If the renderer fails unexpectedly, `answer_text` falls back to
  `null` and the structured response is returned unchanged.

Behavior class → answer_text coverage:

| Behavior class | answer_text |
|---|---|
| `direct_answer` | Fact sentence from evidence (or grounded overview, for overview intents) |
| `direct_answer_with_warning` | Fact sentence + warning note(s) |
| `partial_answer_with_warning` | Partial fact + missing-field note (or graceful overview partial) |
| `useful_refusal` | Refusal explanation from warnings / missing fields |
| `needs_recompute` | Recompute recommendation from compute_decision |

#### Grounded overview support

In addition to the 14 contract intents, `POST /copilot/ask` now
answers high-level explanatory prompts that map to one of six
**overview intents**:

| Intent | Example prompts |
|---|---|
| `perturbation_summary`        | "What is this perturbation doing?", "What kind of perturbation is this?" |
| `scenario_summary`            | "What am I looking at?", "Summarize this scenario." |
| `solution_summary`            | "How does the plan look?", "Summarize the current solution." |
| `perturbation_impact_summary` | "Did this make things worse?", "How is this perturbation affecting the solution?" |
| `route_impact_summary`        | "Which routes are most affected?", "How is this perturbation affecting routes?" |
| `what_to_watch`               | "What should I pay attention to?", "Anything concerning here?" |

These prompts no longer collapse to `unknown` /
`clarification_needed`. Instead they read from a compact, deterministic
**explanation context card** (`product/copilot/explanation_context.py`)
built from the scenario payload and perturbation metadata. The card
contains:

- perturbation family + operator explanation + metrics-to-watch
- current solution status (feasible / objective / route count / lateness)
- comparison availability (baseline / diff / route-level diff)
- limitations (`baseline_diff_missing`, `route_level_diff_missing`,
  `causal_diagnostics_missing`)
- per-intent allowed and forbidden claim labels

The card is flattened into `explanation_context.*` evidence items
attached to the response, so the frontend can see exactly what the
answer was built from. The verbalization renderer reads from the card
to produce `answer_text`; **no LLM call is made for the overview path**.

Important invariants:

- Descriptive intents (`perturbation_summary`, `scenario_summary`,
  `solution_summary`, `what_to_watch`) **never** recommend recompute.
- Impact intents (`perturbation_impact_summary`, `route_impact_summary`)
  recommend `build_comparison_payload` (D4 mode
  `needs_comparison_payload`) when baseline/diff is missing — they
  never recommend a solver to substitute for missing data.
- The renderer cannot claim route changes without a diff, objective
  movement without a baseline, or causal mechanisms without causal
  diagnostics.
- `perturbation_impact_summary` has an **OBJ-inline escape hatch**:
  when `baseline_objective` and `objective_delta_absolute` are present
  inline (as in OBJ-family payloads), the impact answer cites them
  directly and is `answerable`. The escape hatch does not apply to
  `route_impact_summary`, which still requires a route-level diff.

Validation: the offline `explanation_check` harness
(`product/evaluation/explanation_check/`) runs 24 cases and reports
intent accuracy, answerability accuracy, compute-decision accuracy,
and overclaim counters. Current status: 24/24 overall pass, 0 causal
overclaims, 0 comparison overclaims.

Invalid `system` → 400 with `{"error": {"code": "unknown_system", ...}}`.
Unknown `scenario_id` → 404 with `{"error": {"code": "scenario_not_found", ...}}`.

### D4 compute_decision and D5 ui_actions

Under `d4` (the default), every `/copilot/ask` response carries a
`compute_decision` object (full enum domain in
`product/evaluation/system_d4/reports/api_contract_update.md`) and a
`ui_actions` array.

`ui_actions` is **always present** — empty when nothing is recommended.
The only currently emitted entry is the recompute affordance:

```json
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
```

Frontend rule:

```typescript
if (response.compute_decision?.mode === "needs_recompute") {
  // Render the affordance from response.ui_actions[0].
  // On click: POST to ui_actions[0].endpoint with confirm=true.
}
```

`/copilot/ask` **never** runs a solver, regardless of `compute_decision`.
The recompute is executed by the dedicated endpoint below.

### `POST /scenarios/{instance_id}/{perturbation_id}/recompute`

D5 endpoint — operator-authorized recompute execution. Only called
*after* the operator clicks the affordance returned by `/copilot/ask`.

Request body:

```json
{
  "prompt": "Find a better plan that reduces lateness.",
  "requested_action": "run_pyvrp_10s",
  "perturbation": null,
  "confirm": true
}
```

Allowed `requested_action` values:
`run_reuse_direct`, `run_nearest_neighbor`, `run_clarke_wright`,
`run_pyvrp_10s`. `pyvrp_60s` (and its seed variants) is the benchmark
reference solver and is **never** deployable — the endpoint rejects
it with HTTP 400 `forbidden_action`.

Success response (`200`):

```json
{
  "status": "completed",
  "source_scenario_id": "C105__TT_4",
  "new_scenario_id": "C105__TT_4__run_pyvrp_10s__20260521_153000",
  "action_used": "run_pyvrp_10s",
  "runtime_seconds": 10.1,
  "summary": {"feasible": true, "objective": 828.9, "n_routes": 10, "n_late_customers": 0},
  "artifacts": {"scenario_path": ".../scenario.json", "payload_path": ".../payload.json"},
  "next_actions": [
    {"type": "load_scenario", "scenario_id": "...", "label": "Open recomputed scenario"},
    {"type": "ask_again",    "scenario_id": "...", "label": "Ask the original question on the recomputed scenario"}
  ]
}
```

Structured error codes (envelope: `{"error": {"code", "message", "detail"}}`):

| HTTP | code | When |
|---|---|---|
| 400 | `confirmation_required` | `confirm != true` |
| 400 | `invalid_action`         | not on the deployable ladder |
| 400 | `forbidden_action`       | `pyvrp_60s` family |
| 400 | `invalid_perturbation`   | malformed or under-specified |
| 400 | `invalid_prompt`         | empty prompt |
| 404 | `scenario_not_found`     | unknown source scenario |
| 404 | `instance_geometry_not_found` | source `.vrp` file missing |
| 409 | `recompute_not_recommended` | D4 mode != `needs_recompute` |
| 409 | `action_mismatch`        | action ≠ D4 recommended |
| 501 | `action_not_implemented` | deployable but not implemented |
| 501 | `perturbation_application_not_implemented` | executor can't apply perturbation |
| 400 | `payload_missing_routes` | `run_reuse_direct` against a payload with no routes |

`run_pyvrp_10s`, `run_reuse_direct`, and `run_clarke_wright` are
implemented in this local-dev backend. Only `run_nearest_neighbor`
still returns a structured 501.

- `run_reuse_direct` re-scores the source payload's routes against
  the VRPTW instance. Requires the source payload to carry a `routes`
  block — schedule-only or OBJ-only scenarios return 400
  `payload_missing_routes` instead of pretending to succeed.
- `run_clarke_wright` builds a fresh plan via the existing
  parallel-savings construction and evaluates it under VRPTW. The
  construction step is CVRP-style; tight Solomon time windows can
  produce VRPTW-infeasible plans, which the response surfaces
  honestly (`feasible: false`, `feasible_tw_only: false`,
  `n_late_customers > 0`). The backend never silently degrades to a
  stronger solver.
- `run_pyvrp_10s` runs a fresh bounded PyVRP solve.

After a successful recompute, the new scenario can be loaded with:

```
GET /recompute_runs/{new_scenario_id}
```

Runtime artifacts live under `product/api/runtime/recompute_runs/`,
are gitignored, and are **not benchmark truth**. Delete the directory
freely between sessions.

Full design + closeout: `product/evaluation/system_d5/`.

### `POST /scenarios/{instance_id}/{perturbation_id}/diff`

Returns before/after diff if the payload carries `baseline_solution`
or `diff`; otherwise 404 with `code: "diff_not_available"`.

```json
{
  "scenario_id": "C202__TW_3",
  "objective_delta_absolute": 156.3,
  "objective_delta_percent": 6.0,
  "feasibility_changed": null,
  "customer_changes": [],
  "route_changes": []
}
```

The API does not compute customer movement or route deltas from
scratch; it only formats what the payload already exposes. Most Run 1
payloads do **not** carry `baseline_solution`/`diff`, so `404
diff_not_available` is the common case.

### `GET /verification/cases`

Optional debug endpoint exposing the Run 2 calibration case headline
columns (`case_id`, `source_prompt_id`, `family`, `expected_intent`,
`expected_answerability`, `expected_behavior_class`, `difficulty`).
Returns an empty list if the calibration CSV is unavailable.

## Display anchors

Every evidence item carries a `display_anchor` so the frontend can
highlight the right thing without parsing field paths. Shapes:

| `type`               | extra keys                                                  |
|----------------------|-------------------------------------------------------------|
| `customer`           | `customer_id`                                               |
| `route`              | `route_idx`, `route_label`                                  |
| `route_end`          | `route_idx`, `route_label`                                  |
| `customer_arrival`   | `customer_id` (+ `route_idx`/`route_label` when resolvable) |
| `solution_summary`   | —                                                           |
| `none`               | —                                                           |

The mapping lives in `product/api/evidence_anchors.py`. Unrecognised
field paths return `{"type": "none"}` rather than guessing.

## Warnings

Existing contract warnings pass through unchanged:

- `route_indexing_ambiguity`
- `struct_membership_ambiguity`
- `unsupported_comparison`
- `missing_new_customer_attribution`
- `false_premise_detected`
- `comparison_referent_ambiguity`

D3 adds one warning that the dashboard should know about:

- **`causal_mechanism_unsupported`** — the payload supports the
  observed facts but does not support the causal attribution the
  prompt asks about (e.g. "why did the cost go up?" on a payload that
  carries `action_objective` and `objective_delta_*` but no
  mechanism-level diagnostics). Render this as a soft caveat next to
  the answer rather than blocking it.

## Limitations

- `/copilot/ask` never runs a solver. The only path that runs a solver
  is the explicit D5 recompute endpoint.
- D5 implements `run_pyvrp_10s` (fresh solve), `run_clarke_wright`
  (savings-heuristic construction + VRPTW evaluation), and
  `run_reuse_direct` (re-evaluation of source payload routes).
  `run_nearest_neighbor` still returns a structured 501.
- D5 executors operate on the *underlying* VRPTW instance; applying
  the original perturbation (or a request-level perturbation) on top
  of the instance is not yet implemented and returns 501 if requested.
- `run_clarke_wright` uses a CVRP-style savings construction and may
  surface VRPTW infeasibility honestly; it never silently degrades to
  `run_pyvrp_10s`.
- Runtime recompute artifacts under `product/api/runtime/` are
  **local-dev / thesis demo only** — not benchmark truth, not picked
  up by any evaluation harness.
- No persistence beyond the runtime directory. Each `/copilot/ask`
  request is stateless.
- No authentication. Localhost CORS only.
- No file uploads.
- No streaming, no job queue, no cancellation.
- No business logic in the API layer beyond formatting, lookup,
  evidence-anchor enrichment, D4 decision, and D5 execution.
- Diff endpoint at `/scenarios/.../diff` is available **only** for
  scenarios whose payload already carries `baseline_solution` /
  `diff` fields. Run 1 generator payloads typically do not.

## Files

| File                       | What it does                                            |
|----------------------------|---------------------------------------------------------|
| `app.py`                   | FastAPI app + routes + CORS + error envelopes           |
| `models.py`                | Pydantic request/response models                        |
| `scenario_store.py`        | (instance, perturbation) registry + scenario assembly   |
| `copilot_service.py`       | Dispatch + result-shaping for c0/d1/d2/d3/d4/d_final; verbalization wiring |
| `recompute_service.py`     | D5 validation + execution + materialization             |
| `evidence_anchors.py`      | Field-path → display-anchor helper                      |

## Tests

```bash
pytest tests/product_api/ -q
```

The test module skips automatically if Run 1 artifacts are missing.

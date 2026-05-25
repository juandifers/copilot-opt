# VRPTW Copilot Dashboard — API Reference for Frontend Design

## 1. Overview

This API serves a single-page dashboard for inspecting Vehicle Routing
Problem with Time Windows (VRPTW) scenarios and chatting with a
copilot about each one. The frontend is expected to render a route
map, route table, customer schedule, and a chat panel. The API is a
read-only JSON-over-HTTP service that runs locally during
development; every endpoint returns pre-computed data — the API
never solves a VRPTW instance on demand.

## 2. Base URL and request conventions

- **Base URL (development):** `http://127.0.0.1:8000`
- **Request format:** `application/json` for `POST` bodies. `GET`
  endpoints take no body.
- **Response format:** `application/json` for all responses,
  including errors.
- **HTTP methods used:** `GET`, `POST`. The diff endpoint uses `POST`
  with an empty body.
- **Authentication:** None. The API is unauthenticated and the
  frontend must not present a login flow.
- **CORS:** Localhost origins only (`http://localhost:3000`,
  `:5173`, `:6006`, and their `127.0.0.1` equivalents).

### Error response shape

Every error — 400, 404, and 500 — returns the same envelope:

```json
{
  "error": {
    "code": "scenario_not_found",
    "message": "No scenario for instance 'NOSUCH' and perturbation 'NONE'.",
    "detail": {
      "scenario_id": "NOSUCH__NONE"
    }
  }
}
```

`code` is a stable string the frontend can branch on. `message` is
operator-readable. `detail` may be empty or carry endpoint-specific
keys (e.g., `missing_fields`, `available`, `scenario_id`).

## 3. Endpoint reference

### 3.1 `GET /health`

**Purpose.** Lightweight health probe. The frontend calls this once
on startup to confirm the API is reachable and to learn which copilot
systems are available.

**Path parameters.** None.

**Query parameters.** None.

**Response body**

```json
{
  "status": "ok",
  "run2_contract_base_commit": "18b4811a1f85c166ea3ba8c777dfc021b2a5f747",
  "run2_contract_base_tag": "run2-contract-extended",
  "current_git_commit": "18b4811a1f85c166ea3ba8c777dfc021b2a5f747",
  "available_systems": ["c0", "d1", "d2", "d3", "d4"],
  "default_system": "d4"
}
```

`current_git_commit` may be `null` when the API runs outside a git
checkout. `default_system` is the system used when a copilot request
omits the `system` field.

**Error cases.** None expected under normal operation.

---

### 3.2 `GET /instances`

**Purpose.** List every (instance, perturbation) pair the dashboard
can load. Drives the scenario picker in the sidebar.

**Path parameters.** None.

**Query parameters.** None.

**Response body**

```json
{
  "instances": [
    {
      "instance_id": "C102",
      "family": "solomon100",
      "n_customers": 100,
      "available_perturbations": ["OC_1"]
    },
    {
      "instance_id": "C1_2_1",
      "family": "homberger200",
      "n_customers": 200,
      "available_perturbations": ["ST_3", "TT_5"]
    },
    {
      "instance_id": "RC107",
      "family": "solomon100",
      "n_customers": 100,
      "available_perturbations": ["TW_1", "TW_2"]
    }
  ]
}
```

`family` is either `"solomon100"` (100-customer benchmark) or
`"homberger200"` (200-customer benchmark). `n_customers` may be
`null` if the instance geometry cannot be located on disk; the
frontend should treat `null` as "size unknown" and skip size badges.

**Error cases.** None expected under normal operation.

---

### 3.3 `GET /scenarios/{instance_id}/{perturbation_id}`

**Purpose.** Return everything needed to render one scenario: the
static instance geometry (depot + customer positions), the
pre-computed solution (routes, schedule, objective), and a flag
table marking which fields are actually present in this scenario's
payload.

**Path parameters**

| Name              | Type   | Example  | Description                                                |
|-------------------|--------|----------|------------------------------------------------------------|
| `instance_id`     | string | `C105`   | VRPTW instance id (Solomon or Homberger naming).           |
| `perturbation_id` | string | `TT_4`   | Perturbation id (`{family}_{n}`; see §5 PerturbationFamily). |

**Query parameters.** None.

**Response body (scenario with `customer_schedule` and `route_end_times`)**

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
        "x": 45.0,
        "y": 68.0,
        "demand": 10,
        "time_window_start": 885.0,
        "time_window_end": 994.0,
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
        "customer_id": 1,
        "route_idx": 9,
        "route_label": "Route 10",
        "position_in_route": 0,
        "arrival": 940.7,
        "service_start": 940.7,
        "service_end": 1030.7,
        "time_window_start": 885.0,
        "time_window_end": 994.0,
        "is_late": false,
        "lateness_minutes": 0.0,
        "waiting_minutes": null
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

**Response body (scenario with explicit `routes`, no schedule)**

```json
{
  "scenario_id": "RC107__TW_1",
  "instance_id": "RC107",
  "perturbation_id": "TW_1",
  "perturbation_summary": "Time-window perturbation (TW_1)",
  "instance": {
    "depot": {"x": 40.0, "y": 50.0},
    "customers": [
      {
        "customer_id": 1,
        "x": 25.0,
        "y": 85.0,
        "demand": 20,
        "time_window_start": 145.0,
        "time_window_end": 175.0,
        "service_time": 10.0
      }
    ],
    "vehicle_capacity": 200
  },
  "solution": {
    "feasible": null,
    "objective": null,
    "n_routes": 12,
    "routes": [
      {
        "route_idx": 0,
        "route_label": "Route 1",
        "customer_ids": [61, 81, 54, 96],
        "load": null,
        "capacity": null,
        "distance": null,
        "end_time": null
      },
      {
        "route_idx": 1,
        "route_label": "Route 2",
        "customer_ids": [82, 9, 87, 59, 75, 97, 58, 74],
        "load": null,
        "capacity": null,
        "distance": null,
        "end_time": null
      }
    ],
    "customer_schedule": null
  },
  "baseline_solution": null,
  "diff": null,
  "available_fields": {
    "solution": true,
    "routes": true,
    "customer_schedule": false,
    "route_end_times": false,
    "baseline_solution": false,
    "diff": false,
    "objective_delta": false,
    "causal_diagnostics": false
  }
}
```

**Response body (OBJ-family scenario, objective only)**

```json
{
  "scenario_id": "C202__TW_3",
  "instance_id": "C202",
  "perturbation_id": "TW_3",
  "perturbation_summary": "Time-window perturbation (TW_3)",
  "instance": {
    "depot": {"x": 40.0, "y": 50.0},
    "customers": [],
    "vehicle_capacity": 200
  },
  "solution": {
    "feasible": null,
    "objective": 591.6,
    "n_routes": null,
    "routes": null,
    "customer_schedule": null
  },
  "baseline_solution": null,
  "diff": null,
  "available_fields": {
    "solution": true,
    "routes": false,
    "customer_schedule": false,
    "route_end_times": false,
    "baseline_solution": false,
    "diff": false,
    "objective_delta": true,
    "causal_diagnostics": false
  }
}
```

**Field availability depends on scenario state.** Three states are
worth designing for:

- **OBJ-family** scenarios (e.g., `C202__TW_3`): carry an
  `objective` value but no `routes` and no `customer_schedule`.
  The frontend should render the objective and disable map/schedule
  panels (or show them in a "no detail available" state).
- **STRUCT-family** scenarios (e.g., `RC107__TW_1`): carry explicit
  `routes` with `customer_ids`. The map and route table populate;
  the schedule panel is empty.
- **SCHEDULE-family** scenarios (e.g., `C105__TT_4`): carry
  `customer_schedule` and per-route `route_end_times`. The route
  table is synthesised from the schedule; the schedule grid
  populates.

**Error cases**

| Status | Error code             | When it fires                                                   |
|-------:|------------------------|-----------------------------------------------------------------|
| 404    | `scenario_not_found`   | The `(instance_id, perturbation_id)` is not in the registry.     |

---

### 3.4 `POST /copilot/ask`

**Purpose.** Ask the copilot a natural-language question about a
specific scenario. Returns structured fields (intent, evidence,
warnings, next actions, compute decision); does **not** return prose
prose — the frontend renders the structured fields directly.

**Path parameters.** None.

**Query parameters.** None.

**Request body**

```json
{
  "scenario_id": "C105__TT_4",
  "prompt": "What time does route 3 finish?",
  "system": "d4",
  "family": "SCHEDULE"
}
```

| Field         | Type                | Required | Description                                                                                                                                       |
|---------------|---------------------|----------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| `scenario_id` | string              | yes      | `"{instance_id}__{perturbation_id}"`. Double underscore separator.                                                                                |
| `prompt`      | string              | yes      | The user's question. Free text.                                                                                                                   |
| `system`      | string (enum) or null | no     | Which contract system to use. Allowed: `c0`, `d1`, `d2`, `d3`, `d4`. Defaults to the API's `default_system` (currently `d4`).                     |
| `family`      | string or null      | no       | Optional hint at the question's claim family (`OBJ`, `PLAN_VALIDITY`, `STRUCT`, `SCHEDULE`). If omitted, falls back to the scenario's own family. |

`extra` fields are rejected with 400.

**Response body (answerable SCHEDULE question, default `d4` system)**

```json
{
  "system": "d4",
  "scenario_id": "C105__TT_4",
  "intent": "route_end_time",
  "answerability": {
    "status": "answerable",
    "missing_fields": []
  },
  "behavior_class": "direct_answer_with_warning",
  "answer_text": null,
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
    "query_family": "SCHEDULE",
    "reason": "The contract reports the prompt is answerable from the current payload.",
    "confidence": 1.0,
    "required_fields": ["route_end_times"],
    "available_fields": [
      "route_end_times",
      "customer_schedule",
      "units",
      "late_customer_ids",
      "n_late_customers"
    ],
    "missing_for_full_answer": [],
    "expected_runtime_seconds": null,
    "policy_source": "deterministic_d4_v1"
  }
}
```

**Response body (hypothetical question, `d4` recommends a recompute)**

```json
{
  "system": "d4",
  "scenario_id": "C105__TT_4",
  "intent": "single_customer_route_membership",
  "answerability": {
    "status": "not_answerable",
    "missing_fields": ["routes[].customer_ids"]
  },
  "behavior_class": "useful_refusal",
  "answer_text": null,
  "evidence": [],
  "warnings": ["route_indexing_ambiguity", "struct_membership_ambiguity"],
  "useful_refusal": null,
  "suggested_next_actions": [],
  "compute_decision": {
    "mode": "needs_recompute",
    "requires_recompute": true,
    "recommended_action": "run_pyvrp_10s",
    "query_family": "STRUCT",
    "reason": "The prompt asks about a changed scenario or optimization that is not materialized in the current payload.",
    "confidence": 0.9,
    "required_fields": ["perturbed_solution"],
    "available_fields": [
      "route_end_times",
      "customer_schedule",
      "units"
    ],
    "missing_for_full_answer": ["perturbed_solution"],
    "expected_runtime_seconds": 10.0,
    "policy_source": "deterministic_d4_v1"
  }
}
```

**Response body (pre-D4 systems return `compute_decision: null`)**

```json
{
  "system": "c0",
  "scenario_id": "C202__TW_3",
  "intent": "objective_value",
  "answerability": {"status": "answerable", "missing_fields": []},
  "behavior_class": "direct_answer",
  "answer_text": null,
  "evidence": [
    {
      "field_path": "action_objective",
      "value": 591.6,
      "display_anchor": {"type": "solution_summary"}
    },
    {
      "field_path": "units.objective",
      "value": "solomon_distance",
      "display_anchor": {"type": "solution_summary"}
    }
  ],
  "warnings": [],
  "useful_refusal": null,
  "suggested_next_actions": [],
  "compute_decision": null
}
```

`answer_text` is always `null`. The frontend should render the
answer by combining `intent`, `evidence[].value`, and the
`display_anchor` highlights — not by displaying a sentence the
server provided.

**Error cases**

| Status | Error code              | When it fires                                                                       |
|-------:|-------------------------|-------------------------------------------------------------------------------------|
| 400    | `invalid_scenario_id`   | `scenario_id` is missing the `__` separator.                                        |
| 400    | `unknown_system`        | `system` is not one of `c0`, `d1`, `d2`, `d3`, `d4`. `detail.available` lists allowed values. |
| 404    | `scenario_not_found`    | The scenario is well-formed but not in the registry.                                |

---

### 3.5 `POST /scenarios/{instance_id}/{perturbation_id}/diff`

**Purpose.** Return a structured before/after diff for the scenario.
Most scenarios in the benchmark do **not** carry baseline/diff data;
this endpoint is only useful when `available_fields.diff` is `true`
on the scenario response.

**Path parameters**

| Name              | Type   | Example   | Description                              |
|-------------------|--------|-----------|------------------------------------------|
| `instance_id`     | string | `C202`    | VRPTW instance id.                       |
| `perturbation_id` | string | `TW_3`    | Perturbation id.                         |

**Query parameters.** None.

**Request body.** None (empty `POST`).

**Response body (when baseline/diff present)**

```json
{
  "scenario_id": "C202__TW_3",
  "objective_delta_absolute": 156.3,
  "objective_delta_percent": 6.0,
  "feasibility_changed": false,
  "customer_changes": [
    {
      "customer_id": 42,
      "change_type": "moved_route",
      "from_route_idx": 1,
      "from_route_label": "Route 2",
      "to_route_idx": 4,
      "to_route_label": "Route 5",
      "arrival_delta_minutes": 23
    }
  ],
  "route_changes": [
    {
      "route_idx": 2,
      "route_label": "Route 3",
      "change_type": "end_time_shifted",
      "before_end_time": 854.0,
      "after_end_time": 871.3,
      "delta_minutes": 17.3
    }
  ]
}
```

**Error cases**

| Status | Error code             | When it fires                                                       |
|-------:|------------------------|---------------------------------------------------------------------|
| 404    | `scenario_not_found`   | Scenario does not exist.                                            |
| 404    | `diff_not_available`   | Scenario exists but the payload carries no `baseline_solution` or `diff` field. `detail.missing_fields` lists `["baseline_solution", "diff"]`. |

---

### 3.6 `GET /verification/cases`

**Purpose.** Optional debug surface listing the benchmark
calibration cases (`case_id`, expected intent, expected
answerability, expected behavior class, difficulty). The frontend
can use this to render a verification panel showing how each system
scored on canonical cases.

**Path parameters.** None.

**Query parameters.** None.

**Response body**

```json
{
  "cases": [
    {
      "case_id": "R2-001",
      "source_prompt_id": "001",
      "family": "OBJ",
      "expected_intent": "objective_value",
      "expected_answerability": "answerable",
      "expected_behavior_class": "direct_answer",
      "difficulty": "easy"
    }
  ]
}
```

Returns `{"cases": []}` when the calibration CSV is not available
on disk. The frontend should treat an empty list as "verification
view disabled" rather than as an error.

**Error cases.** None.

## 4. Data model glossary

### `Scenario`

The top-level shape returned by `GET /scenarios/{...}/{...}`.

| Field                 | Type                 | Nullable | Description                                                            |
|-----------------------|----------------------|----------|------------------------------------------------------------------------|
| `scenario_id`         | string               | no       | `"{instance_id}__{perturbation_id}"`.                                  |
| `instance_id`         | string               | no       | VRPTW instance id.                                                     |
| `perturbation_id`     | string               | no       | Perturbation id.                                                       |
| `perturbation_summary`| string               | no       | One-line operator description (e.g., "Travel-time perturbation (TT_4)"). |
| `instance`            | `Instance` or null   | yes      | Static instance geometry. `null` only when geometry files are missing. |
| `solution`            | `Solution` or null   | yes      | Pre-computed solution. `null` if no solution-shaped data is present.   |
| `baseline_solution`   | `BaselineSolution` or null | yes | The pre-perturbation solution if the payload carries one; almost always `null`. |
| `diff`                | `Diff` or null       | yes      | Inline diff if the payload carries one; almost always `null`.          |
| `available_fields`    | `AvailableFields`    | no       | Booleans indicating which sub-blocks are actually populated.           |

Example:

```json
{
  "scenario_id": "C105__TT_4",
  "instance_id": "C105",
  "perturbation_id": "TT_4",
  "perturbation_summary": "Travel-time perturbation (TT_4)",
  "instance": {"depot": {"x": 40.0, "y": 50.0}, "customers": [], "vehicle_capacity": 200},
  "solution": {"feasible": null, "objective": null, "n_routes": null, "routes": null, "customer_schedule": []},
  "baseline_solution": null,
  "diff": null,
  "available_fields": {
    "solution": true, "routes": false, "customer_schedule": true,
    "route_end_times": true, "baseline_solution": false, "diff": false,
    "objective_delta": false, "causal_diagnostics": false
  }
}
```

### `Instance`

| Field              | Type                | Nullable | Description                                                  |
|--------------------|---------------------|----------|--------------------------------------------------------------|
| `depot`            | `{x, y}`            | no       | Depot coordinates in abstract Euclidean space.               |
| `customers`        | `Customer[]`        | no       | Customer geometry rows. Empty list for OBJ-family scenarios. |
| `vehicle_capacity` | integer             | yes      | Vehicle capacity in demand units, `null` if unknown.         |

```json
{"depot": {"x": 40.0, "y": 50.0}, "customers": [], "vehicle_capacity": 200}
```

### `Customer`

| Field                | Type    | Nullable | Description                                       |
|----------------------|---------|----------|---------------------------------------------------|
| `customer_id`        | integer | no       | Stable customer id (positive integer).            |
| `x`                  | float   | no       | x-coordinate, abstract Euclidean.                 |
| `y`                  | float   | no       | y-coordinate, abstract Euclidean.                 |
| `demand`             | integer | no       | Demand in instance units.                         |
| `time_window_start`  | float   | no       | Earliest service start, Solomon-minutes.          |
| `time_window_end`    | float   | no       | Latest service start, Solomon-minutes.            |
| `service_time`       | float   | no       | Service duration, Solomon-minutes.                |

```json
{
  "customer_id": 1,
  "x": 45.0, "y": 68.0,
  "demand": 10,
  "time_window_start": 885.0,
  "time_window_end": 994.0,
  "service_time": 90.0
}
```

### `Solution`

| Field               | Type                          | Nullable | Description                                                                              |
|---------------------|-------------------------------|----------|------------------------------------------------------------------------------------------|
| `feasible`          | boolean                       | yes      | Whether the plan satisfies all constraints. Often `null` when not asserted by the payload. |
| `objective`         | float                         | yes      | Total cost in `solomon_distance` units. `null` for non-OBJ payloads.                     |
| `n_routes`          | integer                       | yes      | Number of routes used. May be `null`.                                                    |
| `routes`            | `Route[]` or null             | yes      | Per-route customer lists. `null` if the payload does not carry routes.                   |
| `customer_schedule` | `CustomerScheduleEntry[]` or null | yes  | Per-customer arrival/service rows. `null` if the payload does not carry a schedule.       |

```json
{
  "feasible": null,
  "objective": 591.6,
  "n_routes": 12,
  "routes": null,
  "customer_schedule": null
}
```

### `Route`

| Field          | Type        | Nullable | Description                                                       |
|----------------|-------------|----------|-------------------------------------------------------------------|
| `route_idx`    | integer     | no       | Internal zero-based index. Do **not** display this.               |
| `route_label`  | string      | no       | User-facing label (`"Route 1"`, `"Route 12"`, …).                 |
| `customer_ids` | integer[]   | no       | Customer ids in visit order.                                      |
| `load`         | integer     | yes      | Total demand on the route. Currently always `null`.               |
| `capacity`     | integer     | yes      | Vehicle capacity used for this route. Currently always `null`.    |
| `distance`     | float       | yes      | Route distance in `solomon_distance`. Currently always `null`.    |
| `end_time`     | float       | yes      | Time the route returns to depot, Solomon-minutes. `null` if not in payload. |

```json
{
  "route_idx": 1,
  "route_label": "Route 2",
  "customer_ids": [82, 9, 87, 59, 75, 97, 58, 74],
  "load": null,
  "capacity": null,
  "distance": null,
  "end_time": null
}
```

### `CustomerScheduleEntry`

| Field                | Type    | Nullable | Description                                                          |
|----------------------|---------|----------|----------------------------------------------------------------------|
| `customer_id`        | integer | no       | Customer id.                                                         |
| `route_idx`          | integer | no       | Zero-based route index.                                              |
| `route_label`        | string  | no       | User-facing route label.                                             |
| `position_in_route`  | integer | no       | Visit order on the route, zero-based.                                |
| `arrival`            | float   | yes      | Arrival time, Solomon-minutes.                                       |
| `service_start`      | float   | yes      | Service start time, Solomon-minutes.                                 |
| `service_end`        | float   | yes      | Service end time, Solomon-minutes.                                   |
| `time_window_start`  | float   | yes      | Customer's earliest allowed start (echoed from instance).            |
| `time_window_end`    | float   | yes      | Customer's latest allowed start (echoed from instance).              |
| `is_late`            | boolean | no       | `true` if the visit started after `time_window_end`.                 |
| `lateness_minutes`   | float   | no       | Lateness amount; `0.0` when on time.                                 |
| `waiting_minutes`    | float   | yes      | Idle time before service start. Currently always `null`.             |

```json
{
  "customer_id": 1,
  "route_idx": 9,
  "route_label": "Route 10",
  "position_in_route": 0,
  "arrival": 940.7,
  "service_start": 940.7,
  "service_end": 1030.7,
  "time_window_start": 885.0,
  "time_window_end": 994.0,
  "is_late": false,
  "lateness_minutes": 0.0,
  "waiting_minutes": null
}
```

### `BaselineSolution`

Same shape as `Solution`. Represents the pre-perturbation plan when
the payload carries one. The frontend may safely render it with the
same component used for `solution`. Almost always `null` in the
current benchmark — design for absence as the default.

### `Diff`

| Field                       | Type             | Nullable | Description                                                       |
|-----------------------------|------------------|----------|-------------------------------------------------------------------|
| `scenario_id`               | string           | no       | Echo of the scenario id.                                          |
| `objective_delta_absolute`  | float            | yes      | Absolute objective change (after − before).                       |
| `objective_delta_percent`   | float            | yes      | Percent change vs baseline.                                       |
| `feasibility_changed`       | boolean          | yes      | Whether feasibility flipped (`null` if not asserted).              |
| `customer_changes`          | `CustomerChange[]` | no    | Per-customer movement / lateness deltas. May be empty.            |
| `route_changes`             | `RouteChange[]`  | no       | Per-route shape / timing deltas. May be empty.                    |

```json
{
  "scenario_id": "C202__TW_3",
  "objective_delta_absolute": 156.3,
  "objective_delta_percent": 6.0,
  "feasibility_changed": false,
  "customer_changes": [],
  "route_changes": []
}
```

### `CustomerChange`

| Field                  | Type    | Nullable | Description                                                       |
|------------------------|---------|----------|-------------------------------------------------------------------|
| `customer_id`          | integer | no       | Customer affected.                                                |
| `change_type`          | string  | no       | See ChangeType enum.                                              |
| `from_route_idx`       | integer | yes      | Source route index for `moved_route`.                             |
| `from_route_label`     | string  | yes      | Source route label.                                               |
| `to_route_idx`         | integer | yes      | Destination route index for `moved_route`.                        |
| `to_route_label`       | string  | yes      | Destination route label.                                          |
| `arrival_delta_minutes`| float   | yes      | Change in arrival time, Solomon-minutes.                          |

```json
{
  "customer_id": 42,
  "change_type": "moved_route",
  "from_route_idx": 1,
  "from_route_label": "Route 2",
  "to_route_idx": 4,
  "to_route_label": "Route 5",
  "arrival_delta_minutes": 23
}
```

### `RouteChange`

| Field             | Type    | Nullable | Description                                                  |
|-------------------|---------|----------|--------------------------------------------------------------|
| `route_idx`       | integer | no       | Internal route index.                                        |
| `route_label`     | string  | no       | User-facing route label.                                     |
| `change_type`     | string  | no       | See ChangeType enum.                                         |
| `before_end_time` | float   | yes      | End time on the baseline plan.                               |
| `after_end_time`  | float   | yes      | End time on the perturbed plan.                              |
| `delta_minutes`   | float   | yes      | `after − before`.                                            |

```json
{
  "route_idx": 2,
  "route_label": "Route 3",
  "change_type": "end_time_shifted",
  "before_end_time": 854.0,
  "after_end_time": 871.3,
  "delta_minutes": 17.3
}
```

### `CopilotResponse`

Top-level response of `POST /copilot/ask`.

| Field                    | Type                       | Nullable | Description                                                                                                  |
|--------------------------|----------------------------|----------|--------------------------------------------------------------------------------------------------------------|
| `system`                 | string                     | no       | Which system handled this request (see `available_systems`).                                                 |
| `scenario_id`            | string                     | no       | Echo of the scenario id.                                                                                     |
| `intent`                 | string (enum)              | no       | The contract's interpretation of the question. See Intent enum.                                              |
| `answerability`          | `Answerability`            | no       | Whether the payload supports the answer.                                                                     |
| `behavior_class`         | string (enum)              | no       | The shape of response the contract chose. See BehaviorClass enum.                                            |
| `answer_text`            | string                     | yes      | Always `null` — the API never returns prose. The frontend composes the answer from structured fields.        |
| `evidence`               | `EvidenceItem[]`           | no       | Ground-truth field references supporting the answer. Empty for refusals.                                     |
| `warnings`               | string[]                   | no       | List of warning codes the contract emitted. See WarningCode enum.                                            |
| `useful_refusal`         | `UsefulRefusal` or null    | yes      | Structured refusal explanation when answerability is partial/none; otherwise `null`.                         |
| `suggested_next_actions` | string[]                   | no       | Operator-facing suggestions. Each entry is either a freeform sentence or a semantic code (see NextActionCode).|
| `compute_decision`       | `ComputeDecision` or null  | yes      | Present only when `system == "d4"`. Pre-D4 systems return `null`.                                            |

Example (D4 system, answerable):

```json
{
  "system": "d4",
  "scenario_id": "C105__TT_4",
  "intent": "route_end_time",
  "answerability": {"status": "answerable", "missing_fields": []},
  "behavior_class": "direct_answer_with_warning",
  "answer_text": null,
  "evidence": [
    {
      "field_path": "route_end_times[route_idx=2].end_time",
      "value": 1234.8,
      "display_anchor": {"type": "route_end", "route_idx": 2, "route_label": "Route 3"}
    }
  ],
  "warnings": ["route_indexing_ambiguity"],
  "useful_refusal": null,
  "suggested_next_actions": [],
  "compute_decision": {
    "mode": "answer_from_payload",
    "requires_recompute": false,
    "recommended_action": "none",
    "query_family": "SCHEDULE",
    "reason": "The contract reports the prompt is answerable from the current payload.",
    "confidence": 1.0,
    "required_fields": ["route_end_times"],
    "available_fields": ["route_end_times", "customer_schedule", "units"],
    "missing_for_full_answer": [],
    "expected_runtime_seconds": null,
    "policy_source": "deterministic_d4_v1"
  }
}
```

### `Answerability`

| Field            | Type     | Nullable | Description                                                                |
|------------------|----------|----------|----------------------------------------------------------------------------|
| `status`         | string (enum) | no  | See AnswerabilityStatus enum.                                              |
| `missing_fields` | string[] | no       | Field paths the payload lacks (e.g., `"routes[].customer_ids"`).           |

```json
{"status": "not_answerable", "missing_fields": ["routes[].customer_ids"]}
```

### `EvidenceItem`

| Field           | Type            | Nullable | Description                                                                                                |
|-----------------|-----------------|----------|------------------------------------------------------------------------------------------------------------|
| `field_path`    | string          | no       | A predicate-style path identifying where in the payload the value lives (e.g., `route_end_times[route_idx=2].end_time`). |
| `value`         | any (JSON)      | yes      | The actual value at that path; `null` if it could not be resolved.                                          |
| `display_anchor`| `DisplayAnchor` | no       | How the frontend should highlight this evidence visually. See DisplayAnchor.                                |

```json
{
  "field_path": "customer_schedule[customer_id=42].arrival",
  "value": 9.2,
  "display_anchor": {
    "type": "customer_arrival",
    "customer_id": 42,
    "route_idx": 1,
    "route_label": "Route 2"
  }
}
```

### `DisplayAnchor`

The load-bearing field for evidence highlighting. Always carries a
`type` string; additional fields depend on the type. See §5
DisplayAnchorType for the full vocabulary.

```json
{"type": "route_end", "route_idx": 2, "route_label": "Route 3"}
```

### `UsefulRefusal`

Present when the contract emits a structured refusal (mostly under
D2/D3/D4). The API currently passes refusal information through the
top-level `evidence`, `warnings`, and `suggested_next_actions`
fields and leaves this field `null`. When non-`null`, expect:

| Field                    | Type     | Nullable | Description                                       |
|--------------------------|----------|----------|---------------------------------------------------|
| `refusal_reason`         | string   | no       | Operator-readable explanation.                    |
| `missing_fields`         | string[] | no       | Same vocabulary as `Answerability.missing_fields`.|
| `available_subclaims`    | string[] | no       | Sub-claims that could still be answered.          |
| `suggested_next_actions` | string[] | no       | Actions the operator could take.                  |

```json
{
  "refusal_reason": "The current payload does not contain before/after route comparison fields.",
  "missing_fields": ["baseline_solution", "diff"],
  "available_subclaims": [],
  "suggested_next_actions": ["Build before/after comparison payload."]
}
```

### `ComputeDecision`

Returned by the D4 system. Tells the frontend whether the question
can be answered from the current payload alone, or whether it would
need a comparison payload, a fresh recompute, or operator
clarification.

| Field                      | Type         | Nullable | Description                                                                                     |
|----------------------------|--------------|----------|-------------------------------------------------------------------------------------------------|
| `mode`                     | string (enum)| no       | See ComputeMode enum.                                                                            |
| `requires_recompute`       | boolean      | no       | `true` when the recommended action is a solver invocation.                                       |
| `recommended_action`       | string (enum)| no       | See RecommendedAction enum.                                                                      |
| `query_family`             | string (enum)| no       | The query family the policy assigned (see QueryFamily enum).                                     |
| `reason`                   | string       | no       | One-sentence operator explanation.                                                               |
| `confidence`               | float        | no       | `[0.0, 1.0]` — how confident the deterministic policy is.                                        |
| `required_fields`          | string[]     | no       | Payload field paths the prompt would need.                                                      |
| `available_fields`         | string[]     | no       | Payload field paths actually present.                                                            |
| `missing_for_full_answer`  | string[]     | no       | `required_fields − available_fields`, in stable order.                                           |
| `expected_runtime_seconds` | float        | yes      | Expected wallclock of the recommended action. `null` when no recompute is recommended.            |
| `policy_source`            | string       | no       | Always `"deterministic_d4_v1"` — used for telemetry / replayability.                             |

```json
{
  "mode": "needs_recompute",
  "requires_recompute": true,
  "recommended_action": "run_pyvrp_10s",
  "query_family": "STRUCT",
  "reason": "The prompt asks about a changed scenario or optimization that is not materialized in the current payload.",
  "confidence": 0.9,
  "required_fields": ["perturbed_solution"],
  "available_fields": ["route_end_times", "customer_schedule", "units"],
  "missing_for_full_answer": ["perturbed_solution"],
  "expected_runtime_seconds": 10.0,
  "policy_source": "deterministic_d4_v1"
}
```

### `AvailableFields`

Boolean flag table on every `Scenario`. The frontend uses it to
decide which panels to render or disable.

| Field                | Type    | Description                                                          |
|----------------------|---------|----------------------------------------------------------------------|
| `solution`           | boolean | `true` if any solution-shaped data exists.                            |
| `routes`             | boolean | `true` if `solution.routes` is a non-empty list.                      |
| `customer_schedule`  | boolean | `true` if `solution.customer_schedule` is a non-empty list.           |
| `route_end_times`    | boolean | `true` if the payload carries explicit per-route end times.           |
| `baseline_solution`  | boolean | `true` if `baseline_solution` is present (rare).                      |
| `diff`               | boolean | `true` if a `diff` object is present (rare).                          |
| `objective_delta`    | boolean | `true` if the payload carries delta-objective fields.                 |
| `causal_diagnostics` | boolean | `true` if the payload carries causal mechanism diagnostics.            |

```json
{
  "solution": true,
  "routes": true,
  "customer_schedule": false,
  "route_end_times": false,
  "baseline_solution": false,
  "diff": false,
  "objective_delta": false,
  "causal_diagnostics": false
}
```

## 5. Enumerations and controlled vocabularies

### Intent

The contract's interpretation of the user's question. The frontend
can use this to choose an answer template.

| Value                              | Description                                                                  |
|------------------------------------|------------------------------------------------------------------------------|
| `objective_value`                  | "What does this plan cost?" — single objective value.                        |
| `objective_delta`                  | "How much did the cost change?" — delta vs a baseline/reference.             |
| `feasibility_status`               | "Is this plan feasible?"                                                     |
| `route_count`                      | "How many routes does this plan use?"                                        |
| `single_customer_route_membership` | "Which route is customer N on?"                                              |
| `same_route_boolean`               | "Are customers A and B on the same route?"                                   |
| `route_end_time`                   | "When does route N finish?"                                                  |
| `customer_arrival`                 | "When does the driver reach customer N?"                                     |
| `lateness_summary`                 | "Which customers are late?" / "How many missed their window?"                |
| `before_after_comparison`          | "What changed between the previous plan and this one?"                       |
| `new_customer_assignment`          | "Which route did the newly-inserted customer go on?"                         |
| `full_route_listing`               | "List the customers on each route."                                          |
| `refusal_or_insufficient_payload`  | The model refused or the payload is insufficient; treat as an inability.     |
| `unknown`                          | Could not classify; surface to operator for narrowing.                       |

### AnswerabilityStatus

| Value                  | Description                                                              |
|------------------------|--------------------------------------------------------------------------|
| `answerable`           | Every required field is present.                                         |
| `partially_answerable` | Some required fields are missing; sub-claims may still be answerable.    |
| `not_answerable`       | The payload cannot support the question; render as useful refusal.       |

### BehaviorClass

| Value                            | Description                                                                  |
|----------------------------------|------------------------------------------------------------------------------|
| `direct_answer`                  | Answerable, no warnings — render the answer cleanly.                          |
| `direct_answer_with_warning`     | Answerable, with caveats — render the answer plus a warning chip.             |
| `partial_answer_with_warning`    | Partial answer plus a refusal explanation for the missing part.               |
| `useful_refusal`                 | The contract refuses and suggests what to ask next instead.                   |

### WarningCode

The contract can emit any of the following:

| Value                              | Description                                                                              |
|------------------------------------|------------------------------------------------------------------------------------------|
| `route_indexing_ambiguity`         | The question or answer references a route by integer; route numbering may be ambiguous. |
| `struct_membership_ambiguity`      | A single-customer membership claim — subset vs full set ambiguity.                       |
| `unsupported_comparison`           | A before/after question on a payload that lacks baseline/diff fields.                    |
| `missing_new_customer_attribution` | A "where did the new customer go?" question without `new_customer_ids` in the payload.   |
| `evidence_units_missing`           | OBJ value/delta grounded but `units.objective` is missing — can't display units.         |
| `false_premise_detected`           | The question names a customer or route that does not exist in the payload.               |
| `comparison_referent_ambiguity`    | OBJ delta names a comparator the baseline does not describe.                              |
| `causal_mechanism_unsupported`     | (D3/D4) Payload supports facts but not the causal attribution the prompt asks about.     |

### NextActionCode

`suggested_next_actions[]` entries are either freeform sentences or
one of the following semantic codes:

| Value                                        | Description                                                  |
|----------------------------------------------|--------------------------------------------------------------|
| `Build before/after comparison payload.`     | Get a baseline + diff alongside the current payload.         |
| `Expose perturbation.new_customer_ids in the product payload.` | Add insertion attribution to the payload schema. |
| `Apply product route-label schema augmentation.` | Use the product schema layer to attach route labels.     |
| `Use SCHEDULE payload or run schedule projection.` | Render the SCHEDULE payload variant for this question.  |
| `use_validity_payload`                       | Switch to a PLAN_VALIDITY-shape payload.                     |
| `expose_units_objective`                     | Add `units.objective` to the payload.                         |
| `expose_reference_solution_objective`        | Add `reference_solution.objective` to the payload.            |
| `clarify_false_premise`                      | Surface a clarifying question (entity does not exist).       |

The frontend should treat unknown entries as freeform text and
render them verbatim.

### DisplayAnchorType

Drives which panel highlights when the user clicks an evidence
chip. Every anchor has a `type` field; additional fields depend on
the type.

| `type`               | Additional fields                                                  | Frontend action                                                                                                                                |
|----------------------|--------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `customer`           | `customer_id` (integer)                                            | Highlight the customer pin on the map and the customer row in the schedule.                                                                    |
| `route`              | `route_idx` (integer), `route_label` (string)                      | Highlight the route polyline on the map and the route row in the route table.                                                                  |
| `route_end`          | `route_idx` (integer), `route_label` (string)                      | Highlight the route in the route table and emphasise its end-time cell (or the depot-return marker on the timeline).                            |
| `customer_arrival`   | `customer_id` (integer), `route_idx` (integer, optional), `route_label` (string, optional) | Highlight the customer's row in the schedule and (when route info is present) the route polyline on the map.                 |
| `solution_summary`   | —                                                                  | Highlight the summary panel (objective, n_routes, feasibility chips).                                                                          |
| `none`               | —                                                                  | No anchor available — render the evidence chip as plain text without a highlight target.                                                       |

Anchors carry `route_label` whenever a route is involved so the
frontend never has to compute display labels from `route_idx`.

### ChangeType

Used in `Diff.customer_changes[].change_type` and
`Diff.route_changes[].change_type`. The frontend should treat
unknown values as "other" rather than fail.

| Value              | Where it appears        | Description                                                            |
|--------------------|-------------------------|------------------------------------------------------------------------|
| `moved_route`      | `customer_changes`      | A customer moved from one route to another.                            |
| `arrival_shifted`  | `customer_changes`      | A customer stayed on the same route but their arrival time changed.    |
| `end_time_shifted` | `route_changes`         | A route's end time changed.                                            |
| `route_added`      | `route_changes`         | A new route was added in the perturbed plan.                            |
| `route_removed`    | `route_changes`         | A route was removed in the perturbed plan.                              |

### ComputeMode (D4)

| Value                          | Description                                                                                |
|--------------------------------|--------------------------------------------------------------------------------------------|
| `answer_from_payload`          | Current payload is sufficient. No recompute needed.                                        |
| `partial_from_payload`         | Current payload supports a partial answer; remaining sub-claims need more data.            |
| `needs_comparison_payload`     | A before/after question that needs a baseline payload joined to the current one.            |
| `needs_recompute`              | A solver invocation is required (the recommended_action names which solver).               |
| `clarification_needed`         | The prompt is inquiry-shaped ("can we improve this?") — ask the operator a clarifying Q.    |
| `unsupported`                  | The question is outside the system's scope (e.g., labour rules, fuel pricing, emissions).    |

### RecommendedAction (D4)

| Value                         | Description                                                                                      |
|-------------------------------|--------------------------------------------------------------------------------------------------|
| `none`                        | No action needed — answer from the current payload.                                              |
| `build_comparison_payload`    | Construct a payload that carries both the current and baseline solutions.                        |
| `load_baseline_payload`       | Fetch the pre-perturbation baseline payload.                                                     |
| `run_reuse_direct`            | Verify the current plan against the perturbed instance without re-solving.                        |
| `run_nearest_neighbor`        | Run a nearest-neighbor heuristic solve.                                                          |
| `run_clarke_wright`           | Run a Clarke-Wright savings heuristic solve.                                                     |
| `run_pyvrp_10s`               | Run the PyVRP solver with a 10-second budget.                                                    |
| `ask_clarification`           | The operator must clarify before any action runs.                                                |
| `unsupported`                 | The system cannot handle this — render an "out of scope" message.                                 |

### QueryFamily (D4)

| Value          | Description                                                       |
|----------------|-------------------------------------------------------------------|
| `OBJ`          | Objective / cost questions.                                       |
| `PLAN_VALIDITY`| Feasibility questions.                                            |
| `STRUCT`       | Route structure / membership questions.                           |
| `SCHEDULE`     | Per-customer arrival / lateness / per-route end-time questions.    |
| `CAUSAL`       | "Why did X happen?" questions (D3/D4 detect via causal warning).   |
| `UNKNOWN`      | Could not classify; treat the prompt as freeform.                  |

### PerturbationFamily

`perturbation_id` is `"{family_prefix}_{n}"` where the prefix is one of:

| Prefix | Full family       | Description                                                              |
|--------|-------------------|--------------------------------------------------------------------------|
| `TT`   | `TRAVEL_TIME`     | All travel times scaled by a factor (e.g., `+50%`).                       |
| `TW`   | `TIME_WINDOW`     | Customer time windows perturbed (typically tightened or shifted).        |
| `ST`   | `SERVICE_TIME`    | Service times scaled by a factor.                                        |
| `OC`   | `CUSTOMER_ORDERS` | New customer orders inserted into the instance.                          |

The `_{n}` suffix is a deterministic seed index (e.g., `TT_4` is the
fourth travel-time perturbation seed). The frontend should treat the
suffix as an opaque identifier and surface `perturbation_summary`
instead.

## 6. Interaction patterns

### 6.1 Loading a scenario

```
1.  GET  /health                                       (once, on app startup)
2.  GET  /instances                                    (populates the picker)
3.  GET  /scenarios/{instance_id}/{perturbation_id}    (on user selection)
```

The frontend should not poll `/health` after startup. The
`/instances` list is static for a given backend session and may be
cached for the page lifetime. When the user picks a scenario, the
frontend hits `/scenarios/{...}/{...}` and reads `available_fields`
to decide which panels are renderable.

### 6.2 Asking the copilot

```
1.  POST /copilot/ask    body: {scenario_id, prompt, system?, family?}
2.  Receive CopilotResponse.
3.  For each EvidenceItem, look at evidence[i].display_anchor.type
    and dispatch to the right panel highlight.
```

The frontend's panels must handle every `DisplayAnchorType` value:

| Anchor type        | Panels that should react                                                            |
|--------------------|-------------------------------------------------------------------------------------|
| `customer`         | Map (pin pulse), schedule (row highlight).                                          |
| `route`            | Map (polyline emphasis), route table (row highlight).                               |
| `route_end`        | Route table (row highlight + end-time cell emphasis), timeline (depot-return marker). |
| `customer_arrival` | Schedule (row highlight), map (polyline emphasis when route info present).          |
| `solution_summary` | Summary panel (objective / n_routes / feasibility chips).                            |
| `none`             | No highlight. Render the evidence chip plain.                                       |

If `system == "d4"` the response carries `compute_decision`. The
frontend can use `compute_decision.mode` to drive a separate
recompute-affordance banner:

| `compute_decision.mode`        | Recommended UI affordance                                                                                                              |
|--------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| `answer_from_payload`          | None — render the answer.                                                                                                              |
| `partial_from_payload`         | Show a subtle "partial answer" chip.                                                                                                   |
| `needs_comparison_payload`     | Banner: "This question needs a baseline payload." Disabled action button labelled with `recommended_action`.                            |
| `needs_recompute`              | Banner with action button: e.g., "Run PyVRP (≈10s)" when `recommended_action == "run_pyvrp_10s"`. The button is informational only — the API does not run solvers. |
| `clarification_needed`         | Banner: "Please clarify what you want." Render the `reason`.                                                                            |
| `unsupported`                  | Banner: "This is outside the copilot's scope." Render the `reason`.                                                                     |

`warnings[]` should always be surfaced as chips below the answer
(one chip per warning). Map each warning code to its human-readable
message using the WarningCode table in §5.

### 6.3 Before/after diff

```
1.  Check scenario.available_fields.diff and scenario.available_fields.baseline_solution.
2.  If both are false: do NOT call /diff — disable the toggle.
3.  Otherwise: POST /scenarios/{instance_id}/{perturbation_id}/diff (empty body).
4.  If the response is 200: render the diff object.
5.  If the response is 404 with code "diff_not_available":
       Show a small explanatory message ("No baseline data for this scenario")
       and disable the toggle until the user picks another scenario.
6.  If the response is 404 with code "scenario_not_found":
       Treat as a routing error (back-navigate or refresh the picker).
```

In the current benchmark, every Run 1 scenario returns 404
`diff_not_available`. Designs should treat the diff view as a
"rarely available" affordance — not the default state.

## 7. Field-level conventions

**Route labels vs route indices.** Every route-typed object returns
both `route_idx` (zero-based internal integer) and `route_label`
(one-based display string, e.g. `"Route 1"`, `"Route 12"`). The
frontend must always render `route_label` and never display
`route_idx` to the user. The two fields are kept in sync server-side.

**Time units.** All time-typed fields (`arrival`, `service_start`,
`service_end`, `end_time`, `time_window_start`, `time_window_end`,
`lateness_minutes`) are in **Solomon-minutes** — a unitless minute
count from a synthetic start-of-day reference, not a wall-clock
time. Typical magnitudes are in the hundreds to low thousands
(`9.2`, `871.3`, `1234.8`). Render as a number with one decimal
place. Do **not** format as "HH:MM"; the underlying data is
benchmark-synthetic and the conversion would be misleading.

**Coordinate system.** Customer `x`/`y` are abstract Euclidean
coordinates in the Solomon/Homberger benchmark, roughly bounded by
the 0–100 box (Solomon) or 0–200 box (Homberger). They are
**not** geographic latitude/longitude. Designers should reach for a
plain SVG (or HTML canvas) scatter, not Leaflet/MapLibre or any
geographic map library. The same scale should fit both Solomon and
Homberger instances since coordinates remain Euclidean.

**Nullable fields.** A `null` field means "the underlying payload
does not carry this", not "the field is empty":

| Field                              | What `null` means                                                              |
|------------------------------------|--------------------------------------------------------------------------------|
| `solution.objective`               | Payload carries no objective value (likely a STRUCT/SCHEDULE-only payload).    |
| `solution.feasible`                | Payload carries no top-level feasibility boolean.                              |
| `solution.routes`                  | Payload carries no explicit route list (routes may be inferable from schedule). |
| `solution.customer_schedule`       | Payload carries no per-customer schedule.                                      |
| `baseline_solution`                | No baseline plan is included with this scenario (the common case).             |
| `diff`                             | No inline diff is included (the common case).                                  |
| `route.load`, `route.capacity`, `route.distance` | API-layer placeholders; always `null` for now.                  |
| `route.end_time`                   | Payload carries no end time for this route.                                    |
| `customer_arrival.arrival` / `service_start` / `service_end` | Schedule row exists but the timing field is missing. |
| `customer_arrival.waiting_minutes` | API-layer placeholder; always `null` for now.                                  |
| `instance.vehicle_capacity`        | Capacity not recorded for this instance.                                       |
| `current_git_commit` (on `/health`) | The API is running outside a git checkout.                                     |
| `compute_decision`                 | The request was served by a pre-D4 system.                                     |
| `compute_decision.expected_runtime_seconds` | The recommended action requires no solver invocation.                  |
| `answer_text`                      | Always `null` — the API never returns prose.                                    |

## 8. Worked example — full request/response trace

Scenario: `C105__TT_4` (Solomon 100-customer instance C105, 4th
travel-time perturbation). The user lands on the dashboard, picks
this scenario from the sidebar, and asks "What time does route 3
finish?".

**Request 1 — list instances**

```
GET /instances
```

**Response 1**

```json
{
  "instances": [
    {"instance_id": "C102", "family": "solomon100", "n_customers": 100, "available_perturbations": ["OC_1"]},
    {"instance_id": "C105", "family": "solomon100", "n_customers": 100, "available_perturbations": ["TT_4"]},
    {"instance_id": "C1_2_1", "family": "homberger200", "n_customers": 200, "available_perturbations": ["ST_3", "TT_5"]},
    {"instance_id": "RC107", "family": "solomon100", "n_customers": 100, "available_perturbations": ["TW_1", "TW_2"]}
  ]
}
```

**Request 2 — load the scenario**

```
GET /scenarios/C105/TT_4
```

**Response 2** (abridged — full schedule is 100 rows; first and last shown)

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
        "x": 45.0,
        "y": 68.0,
        "demand": 10,
        "time_window_start": 885.0,
        "time_window_end": 994.0,
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
        "customer_id": 1,
        "route_idx": 9,
        "route_label": "Route 10",
        "position_in_route": 0,
        "arrival": 940.7,
        "service_start": 940.7,
        "service_end": 1030.7,
        "time_window_start": 885.0,
        "time_window_end": 994.0,
        "is_late": false,
        "lateness_minutes": 0.0,
        "waiting_minutes": null
      },
      {
        "customer_id": 100,
        "route_idx": 7,
        "route_label": "Route 8",
        "position_in_route": 8,
        "arrival": 697.0,
        "service_start": 697.0,
        "service_end": 787.0,
        "time_window_start": 608.0,
        "time_window_end": 765.0,
        "is_late": false,
        "lateness_minutes": 0.0,
        "waiting_minutes": null
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

`available_fields.diff` is `false`, so the diff toggle is disabled.

**Request 3 — ask the copilot**

```
POST /copilot/ask
Content-Type: application/json

{
  "scenario_id": "C105__TT_4",
  "prompt": "What time does route 3 finish?",
  "family": "SCHEDULE"
}
```

**Response 3**

```json
{
  "system": "d4",
  "scenario_id": "C105__TT_4",
  "intent": "route_end_time",
  "answerability": {
    "status": "answerable",
    "missing_fields": []
  },
  "behavior_class": "direct_answer_with_warning",
  "answer_text": null,
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
    "query_family": "SCHEDULE",
    "reason": "The contract reports the prompt is answerable from the current payload.",
    "confidence": 1.0,
    "required_fields": ["route_end_times"],
    "available_fields": [
      "route_end_times",
      "customer_schedule",
      "units",
      "late_customer_ids",
      "n_late_customers"
    ],
    "missing_for_full_answer": [],
    "expected_runtime_seconds": null,
    "policy_source": "deterministic_d4_v1"
  }
}
```

What the frontend renders from this response:

- **Answer block.** "Route 3 finishes at 1234.8 solomon_minutes."
  (Composed from `intent: "route_end_time"`,
  `evidence[0].value = 1234.8`, and the route label inside the
  `display_anchor`.)
- **Highlight.** The route table emphasises the Route 3 row and its
  end-time cell. The timeline panel pulses the depot-return marker
  for Route 3.
- **Warning chip.** `route_indexing_ambiguity` → "Route numbering
  may be ambiguous."
- **No recompute banner.** `mode == "answer_from_payload"`.

**Request 4 — diff (defensive call, expected to 404)**

```
POST /scenarios/C105/TT_4/diff
```

**Response 4**

```json
{
  "error": {
    "code": "diff_not_available",
    "message": "This scenario does not include baseline/diff fields.",
    "detail": {
      "missing_fields": ["baseline_solution", "diff"]
    }
  }
}
```

The frontend never needed to make this call (the toggle was
disabled), but seeing the shape here clarifies what would have come
back if the user had forced it.

## 9. What this API does NOT do

- **Does not stream responses.** `POST /copilot/ask` returns a
  single JSON body; the chat UI should not implement streaming
  rendering.
- **Does not authenticate.** No login, no tokens, no session
  cookies. Do not design a sign-in flow.
- **Does not persist state.** No conversation history is stored
  server-side; closing the browser loses the chat. Design without a
  history sidebar by default. The frontend may keep its own local
  history if desired.
- **Does not solve VRPTW instances on demand.** All solutions are
  pre-computed. The D4 `recommended_action` is informational only —
  the API does not actually run `run_pyvrp_10s` when asked. A
  separate, future system would.
- **Does not return prose.** `answer_text` is always `null`. The
  frontend composes the answer from `intent`, `evidence`, and
  `display_anchor`.
- **Does not modify any data.** Every endpoint is read-only.
- **Does not upload files.** No multipart endpoints exist; the
  frontend should not present an upload widget.
- **Does not maintain user accounts.** Multi-user UX (sharing,
  permissions, presence) is out of scope.

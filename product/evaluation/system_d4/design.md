# System D4 — Design

_D4 is the fourth implementation step of the System D envelope. It adds
a deterministic compute-decision layer on top of D3 that tells the
frontend/operator whether the current payload is sufficient to answer
the prompt, or whether a comparison payload, a cheap recomputation, or
solver escalation is required._

## 1. Goal

Make the recompute/comparison decision explicit in the copilot response
contract.

Today the API prompt says "no solver calls; we never recompute." That
is correct for the first read-only wrapper, but it is not the final
product principle. Some operator questions ("when does route 3 finish",
"which customers are late") are answerable from the materialized
payload; others ("what if we add customer 999", "is this better than
baseline") are not. D4 makes the difference machine-readable.

## 2. What D4 is NOT

- D4 does not call a solver.
- D4 is not the learned benchmark predictor (yet).
- D4 does not add a `/recompute` HTTP endpoint.
- D4 does not modify locked Run 2 artifacts.
- D4 does not modify any Axis 1/2/3/4 case CSVs.
- D4 does not modify D1/D2/D3 semantics — it adds one optional field
  to the response (`compute_decision`).
- D4 does not expose `pyvrp_60s` as a deployable action; that solve
  was the benchmark reference-label generator only.

## 3. Architecture

```
prompt_text, family, payload
   │
   ▼
infer_intent_d1_frame  (D1)
   │
   ▼
compute_answerability_d2  (D2)
   │
   ▼
build_evidence_items  (unchanged)
   │
   ▼
build_warnings_d3  (D3)
   │
   ▼
build_useful_refusal_d3  (D3 passthrough)
   │
   ▼
_infer_behavior_class
   │
   ▼
decide_compute  (D4 — new)
   │       └ deterministic policy over
   │         (prompt_text, intent, answerability,
   │          warnings, available_fields)
   ▼
PredictedContractD4(compute_decision=ComputeDecision(...))
```

D4 only writes into the new `compute_decision` field. Every existing
D3 field is forwarded verbatim.

## 4. ComputeDecision shape

```json
{
  "mode": "answer_from_payload",
  "requires_recompute": false,
  "recommended_action": "none",
  "query_family": "SCHEDULE",
  "reason": "The current payload contains the route end time needed.",
  "confidence": 1.0,
  "required_fields": ["route_end_times"],
  "available_fields": ["route_end_times", "customer_schedule"],
  "missing_for_full_answer": [],
  "expected_runtime_seconds": null,
  "policy_source": "deterministic_d4_v1"
}
```

### Modes

| mode | semantics |
|---|---|
| `answer_from_payload` | Current payload contains the fields needed for a complete answer. |
| `partial_from_payload` | Observed facts can be cited; the requested explanation/comparison cannot be fully grounded. |
| `needs_comparison_payload` | A baseline/diff payload is required; not necessarily a fresh solve. |
| `needs_recompute` | The prompt asks about a not-materialized scenario or an optimization/repair under changed constraints. |
| `clarification_needed` | Ambiguous between status query and optimization request. |
| `unsupported` | Outside current app capabilities (driver preferences, fuel price, etc.). |

### Recommended actions

| action | when |
|---|---|
| `none` | `answer_from_payload`, `partial_from_payload` without comparison signal |
| `build_comparison_payload` | `needs_comparison_payload` (no baseline available) |
| `load_baseline_payload` | `needs_comparison_payload` (baseline pointer known but not loaded) |
| `run_reuse_direct` | `needs_recompute` + "reuse current solution" or feasibility under changed constraints |
| `run_nearest_neighbor` | `needs_recompute` + explicit cheap-heuristic ask (NN) |
| `run_clarke_wright` | `needs_recompute` + explicit cheap-heuristic ask (CW) or generic "quick" |
| `run_pyvrp_10s` | `needs_recompute` + "better/fresh/stronger" or default for ambiguous-recompute |
| `ask_clarification` | `clarification_needed` |
| `unsupported` | `unsupported` |

`pyvrp_60s` is intentionally absent.

## 5. Intent → query-family mapping

```
OBJ            ← objective_value, objective_delta
PLAN_VALIDITY  ← feasibility_status
STRUCT         ← route_count, single_customer_route_membership,
                 same_route_boolean, full_route_listing,
                 new_customer_assignment, before_after_comparison
SCHEDULE       ← route_end_time, customer_arrival, lateness_summary
CAUSAL         ← any intent above WHEN warnings contains
                 `causal_mechanism_unsupported`
UNKNOWN        ← unknown, refusal_or_insufficient_payload
```

The CAUSAL family is an overlay — it is selected when D3 has fired the
causal warning, regardless of the underlying intent.

## 6. Policy rules (deterministic_d4_v1)

The policy is purely lexical + status-driven. No model calls.

### Rule group 1 — Current payload is enough

If D3 answerability is `answerable` AND no recompute/comparison/
unsupported triggers are detected in the prompt:

```
mode = answer_from_payload
recommended_action = none
```

### Rule group 2 — Partial

If D3 returned a behavior_class consistent with partial answer
(`partial_answer_with_warning` or any case where D3 emits
`causal_mechanism_unsupported`), and no recompute/comparison triggers
are present:

```
mode = partial_from_payload
recommended_action = none
```

If the partial-answer prompt also names a comparison referent, prefer
`needs_comparison_payload`.

### Rule group 3 — Needs comparison payload

Triggers (any): `compared to`, `previous`, `prior`, `old solution`,
`baseline`, `before/after`, `changed routes`, `moved from`,
`reassigned from`, `improved/worse/reduced/increased`.

If baseline/diff fields are absent from `available_fields`:

```
mode = needs_comparison_payload
recommended_action = build_comparison_payload
```

### Rule group 4 — Needs recompute

Triggers (any): `what if`, `suppose`, `add customer`, `insert customer`,
`remove customer`, `change demand`, `capacity drops`,
`tighten time window`, `relax time window`, `make customer on time`,
`find a better plan`, `improve this`, `reroute`, `repair`, `reoptimize`,
`fresh solve`, `stronger solver`.

```
mode = needs_recompute
requires_recompute = true
```

Action selection (in order):

1. `reuse current` / `current solution still feasible` → `run_reuse_direct`
2. `nearest neighbor` / `NN heuristic` → `run_nearest_neighbor`
3. `clarke wright` / `quick heuristic` / `cheap solve` → `run_clarke_wright`
4. `better/fresh/stronger/optimize` → `run_pyvrp_10s`
5. otherwise → `run_pyvrp_10s` (safe default)

### Rule group 5 — Clarification

Ambiguous between status and optimization (`can you improve this?`,
`is route 3 okay?`, `what should we do?`):

```
mode = clarification_needed
recommended_action = ask_clarification
```

### Rule group 6 — Unsupported

Prompt asks for out-of-schema concepts (`driver preferences`,
`labor rules`, `fuel price`, `emissions`, `depot staffing`,
`customer priority` when not in payload):

```
mode = unsupported
recommended_action = unsupported
```

### Precedence

`unsupported` > `needs_recompute` > `needs_comparison_payload` >
`partial_from_payload` > `clarification_needed` > `answer_from_payload`.

The reason: a recompute or unsupported framing should never be
silently downgraded to a status answer, even if the current payload
happens to contain a field that loosely matches the prompt.

## 7. Relationship to earlier predictor / routing-policy work

The Stage A benchmark trained per-claim-family binary gates with
features computed over VRPTW perturbation diagnostics
(`predictor_models/`, `predictor_baselines/`). That work cannot be
ported directly because:

- Its claim families (`OBJ / PV / STRUCT / SCHEDULE`) overlap but do
  not coincide with the contract intent enum.
- Its features (`baseline_n_routes`, `action_time_warp`, …) are
  perturbation diagnostics, not contract-payload features.
- It assumes a `pyvrp_60s` reference solve at label time; production
  has no equivalent oracle at inference time.

D4 v1 is therefore deterministic. A learned sufficiency gate
(`deterministic_d4_v1` → `learned_d4_v2`) is reserved as future work
once the feature set has been adapted to the contract surface.

## 8. Evaluation

`d4_cases.csv` — 32 hand-labeled D4 cases:

- 8 `answer_from_payload`
- 8 `needs_comparison_payload`
- 8 `needs_recompute`
- 4 `partial_from_payload`
- 4 `clarification_needed` / `unsupported`

Split: 16 dev / 16 heldout. Splits are not used to tune case-by-case;
rules are kept semantic.

Headline metrics:

- `compute_mode_accuracy`
- `requires_recompute_accuracy`
- `recommended_action_accuracy`
- `query_family_accuracy`
- `missing_for_full_answer_recall`
- `safe_no_solver_rate` (must be 1.0)

Plus regression checks (D3 intent / behavior_class / warning P-R on
Run 2 core and Axes 1–4 unchanged when D3 is re-run through the D4
wrapper).

## 9. Frontend/API surface

`compute_decision` is **additive**. The frontend can continue to
consume `ProductCopilotResponse` unchanged; D4-aware clients read the
new field. The future `/recompute` endpoint will consume
`recommended_action` and `expected_runtime_seconds` directly. See
`reports/api_contract_update.md`.

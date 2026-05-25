# API contract update — D4 compute decision

D4 adds one optional field to the copilot response. No existing field
is renamed, removed, or repurposed.

## Response enrichment

`POST /copilot/ask` (or the GET equivalent) responses gain a top-level
`compute_decision` object:

```json
{
  "...": "existing D3 contract fields (unchanged)",
  "compute_decision": {
    "mode": "needs_recompute",
    "requires_recompute": true,
    "recommended_action": "run_pyvrp_10s",
    "query_family": "SCHEDULE",
    "reason": "The prompt asks about a changed scenario that is not materialized in the current payload.",
    "confidence": 0.9,
    "required_fields": ["perturbed_solution"],
    "available_fields": ["current_solution", "route_end_times", "customer_schedule"],
    "missing_for_full_answer": ["perturbed_solution"],
    "expected_runtime_seconds": 10.0,
    "policy_source": "deterministic_d4_v1"
  }
}
```

### Enum domains (frozen for v1)

- `mode` ∈ `{answer_from_payload, partial_from_payload, needs_comparison_payload, needs_recompute, clarification_needed, unsupported}`
- `recommended_action` ∈ `{none, build_comparison_payload, load_baseline_payload, run_reuse_direct, run_nearest_neighbor, run_clarke_wright, run_pyvrp_10s, ask_clarification, unsupported}`
- `query_family` ∈ `{OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE, CAUSAL, UNKNOWN}`

`pyvrp_60s` is **not** a member of `recommended_action`. It was the
benchmark's reference-label solver, never a deployable rung.

## Backward compatibility

- Clients that do not read `compute_decision` see no change.
- The `compute_decision` field is optional; downstream code that
  receives D4-aware responses but treats them as D3 will work.

## No solver invocation on this endpoint

`/copilot/ask` still does **not** call a solver under any
`recommended_action`. The action is a recommendation only; the user
(or a future endpoint) decides whether to act on it.

## Future: `POST /recompute`

Out of scope for D4. The future endpoint will consume:

```json
{
  "prompt_id": "...",
  "recommended_action": "run_pyvrp_10s",
  "scenario_id": "...",
  "expected_runtime_seconds": 10.0
}
```

…and return a recomputed payload. D4's `compute_decision` object is
the contract surface that future endpoint will be wired against.

## Frontend usage sketch

```typescript
const decision = response.compute_decision;
if (!decision) {
  renderD3Response(response);  // pre-D4 client path
  return;
}
switch (decision.mode) {
  case "answer_from_payload":
    renderD3Response(response);
    break;
  case "partial_from_payload":
    renderD3Response(response);
    showPartialNotice(decision.reason);
    break;
  case "needs_comparison_payload":
    showComparisonCTA(decision.recommended_action, decision.missing_for_full_answer);
    break;
  case "needs_recompute":
    showRecomputeCTA(decision.recommended_action, decision.expected_runtime_seconds);
    break;
  case "clarification_needed":
    openClarificationDialog(decision.reason);
    break;
  case "unsupported":
    showUnsupportedMessage(decision.reason);
    break;
}
```

The CTA must never invoke a solver on its own.

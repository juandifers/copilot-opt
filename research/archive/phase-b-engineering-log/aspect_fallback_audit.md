# Aspect-Fallback Audit

Read-only audit of the copilot pipeline ahead of the proposed entity+aspect
fallback layer. Every claim cites a file:line; inferences are marked
`(inference)`. Architectural pressure points are flagged inline as
**PRESSURE POINT** where the current code makes an assumption the amendment
will need to relax.

The two most consequential findings up front:

- **Easier than design implies** (section 4): the LLM frame already
  extracts `entities.customer_ids` and `entities.route_labels` at
  `product/copilot/llm_query_frame.py:98–101`, and those entities are
  carried into the `QueryFrame` (`product/copilot/query_frame.py:37–39`)
  **even when the LLM's intent is rejected by a validation gate**. The
  amendment can consume entities the existing path already produces.
  But: the *adapter currently returns the D1 frame on rejection*
  (see section 4) — the rejected LLM frame's entities never reach
  downstream. Plumbing change required, but no new extractor.
- **Easier than design implies** (section 1): payloads in the wild are
  **family-sharded**. OBJ payloads carry only `units / action_objective /
  baseline_objective / objective_delta_*`. PV payloads carry only
  `feasible / feasibility_breakdown / infeasibility_kind /
  n_unserved_customers / unserved_customer_ids`. STRUCT carries only
  `n_routes / routes[]`. SCHEDULE carries only `units.time /
  n_late_customers / late_customer_ids / route_end_times[] /
  customer_schedule[]`. No payload in Run 1 has `baseline_solution`,
  `diff`, `reference_solution`, or `causal_diagnostics`. Aspect
  dispatch is constrained to the present family's columns; the cross-
  family aspect taxonomy in this report is mostly aspirational.

---

## 1. Payload schema map

Phase 5 (`product/api/copilot_service.py:222–264`) hands two artifacts to
the rest of the pipeline:

1. The augmented payload from `product.data.product_schema.augment_payload_for_product`
   (`product/data/product_schema.py:118–124`), which deep-copies the
   `payload_snapshot` and mutates route-bearing list items to add
   `display_route_number` and `route_label`
   (`product/data/product_schema.py:14–47`).
2. The evidence items built by `product.data.evidence.build_evidence_items`
   (`product/data/evidence.py:384–429`). The list is keyed by `field_path`
   in `copilot_service.py:230–232`.

### 1.1 Empirical schema, per family

I walked `experiment/results_RUN1/generator/full-run-v1.jsonl` (48 records,
12 per family) using `payload_snapshot` and confirmed every key shown is
**universally present** within its family. No family-conditional or
scenario-conditional variance was observed in the 48 records.

```
OBJ (n=12, universally present in family):
├── units                              dict
│   └── objective                      str   (e.g. "solomon_distance")
├── action_objective                   float
├── baseline_objective                 float
├── objective_delta_absolute           float
└── objective_delta_percent            float

PLAN_VALIDITY (n=12, universally present in family):
├── feasible                           bool
├── feasibility_breakdown              dict
│   ├── capacity_ok                    bool
│   ├── time_windows_ok                bool
│   └── coverage_ok                    bool
├── infeasibility_kind                 str
├── n_unserved_customers               int
└── unserved_customer_ids              list[int]

STRUCT (n=12, universally present in family):
├── n_routes                           int
└── routes                             list[dict]
    └── [].route_idx                   int
    └── [].customer_ids                list[int]
    (after augmentation, also: display_route_number int, route_label str)

SCHEDULE (n=12, universally present in family):
├── units                              dict
│   └── time                           str   (e.g. "solomon_minutes")
├── n_late_customers                   int
├── late_customer_ids                  list[int]
├── route_end_times                    list[dict]
│   └── [].route_idx                   int
│   └── [].end_time                    float
│   └── [].has_time_warp               bool
│       (augmented: display_route_number, route_label)
└── customer_schedule                  list[dict]
    └── [].customer_id                 int
    └── [].route_idx                   int
    └── [].arrival                     float
    └── [].start_service               float
    └── [].end_service                 float
    └── [].tw_early                    float
    └── [].tw_late                     float
    └── [].is_late                     bool
    └── [].lateness_minutes            float
        (augmented: display_route_number, route_label)
```

### 1.2 Cross-family field presence

**The payload sharding is hard.** Across all 48 records:

```
24/48  units                         (12 OBJ + 12 SCHEDULE; SCHEDULE.units.time only)
12/48  action_objective, baseline_objective, objective_delta_absolute,
       objective_delta_percent       (OBJ only)
12/48  feasible, feasibility_breakdown.*, infeasibility_kind,
       n_unserved_customers, unserved_customer_ids   (PV only)
12/48  n_routes, routes              (STRUCT only)
12/48  n_late_customers, late_customer_ids, route_end_times,
       customer_schedule             (SCHEDULE only)
 0/48  baseline_solution, diff, reference_solution, causal_diagnostics
```

This was reproduced by enumerating `payload.keys()` over every record.

### 1.3 Fields referenced by infrastructure but never present in payloads

Several modules consume field names that **never exist** in any Run 1
payload. These appear in answerability/required_fields, scenario_store
diff helpers, sufficiency-gate feature dicts, etc.:

- `baseline_solution`, `diff` — required for `before_after_comparison`,
  `perturbation_impact_summary`, `route_impact_summary`, and
  `new_customer_assignment.routes[].customer_ids` paths
  (`product/data/answerability.py:49–50,70–71`). Always absent.
- `reference_solution.objective` — added to missing-fields when an
  ambiguous comparison referent is detected
  (`product/data/answerability.py:219–226`). Always absent.
- `causal_diagnostics` — checked by the explanation-context card
  (`product/copilot/explanation_context.py:363,389–397`). Always absent.
- `new_customer_ids` — referenced by warnings
  (`product/copilot/refusal_policy.py:132–137`) and D4
  (`product/evaluation/system_d4/compute_decision.py:608, 575–576`).
  Always absent in the 48-record set.
- `assignment` — D4 requires it for STRUCT membership intents
  (`product/evaluation/system_d4/compute_decision.py:605–606`). Always
  absent.

Note: this is the empirical situation in the **Run 1** dataset. The
recompute pathway (`/recompute_runs/`) writes its own scenario JSONs;
those may or may not differ in shape. The contract code is built as if
these fields *could* be there.

### 1.4 Fields present in payloads but NOT in any intent's `required_fields`

These are unsurfaced columns the aspect layer could expose:

| field path                                  | family | currently surfaced by                                  | not in `_REQUIRED_FIELDS`? |
| ------------------------------------------- | ------ | ------------------------------------------------------ | -------------------------- |
| `units.time`                                | SCHEDULE | nothing                                              | yes                        |
| `infeasibility_kind`                        | PV     | evidence item only (`evidence.py:189–196`)             | yes                        |
| `n_unserved_customers`                      | PV     | nothing (evidence does not cite it)                    | yes                        |
| `unserved_customer_ids`                     | PV     | evidence item (`evidence.py:197–205`)                  | yes                        |
| `feasibility_breakdown.capacity_ok`         | PV     | evidence item (`evidence.py:178–188`)                  | yes (only umbrella listed) |
| `feasibility_breakdown.time_windows_ok`     | PV     | "                                                      | yes                        |
| `feasibility_breakdown.coverage_ok`         | PV     | "                                                      | yes                        |
| `route_end_times[].has_time_warp`           | SCHEDULE | evidence item conditional on truthy (`evidence.py:302–308`) | yes                |
| `customer_schedule[].is_late`               | SCHEDULE | evidence item conditional on truthy (`evidence.py:343–349`) | yes                |
| `customer_schedule[].lateness_minutes`      | SCHEDULE | nothing                                              | yes                        |
| `customer_schedule[].start_service`         | SCHEDULE | nothing                                              | yes                        |
| `customer_schedule[].end_service`           | SCHEDULE | nothing                                              | yes                        |
| `customer_schedule[].tw_early`              | SCHEDULE | nothing                                              | yes                        |
| `customer_schedule[].tw_late`               | SCHEDULE | nothing                                              | yes                        |

The lateness columns and the time-window columns are the densest patch of
"present-but-unsurfaced" data. **PRESSURE POINT**: a lateness-aspect
question routed by aspect dispatch could legitimately surface
`n_late_customers`, `late_customer_ids`, **and** the per-customer
`lateness_minutes` + `tw_late` rows — none of which any current intent
exposes together. The grounding invariant is satisfied: every value
is a real field path.

---

## 2. Intent → fields table with proposed aspect clustering

### 2.1 Intent → required_fields table

Authoritative source: `product/data/answerability.py:31–75` plus the
escape-hatch logic at `:82–92, 121–124, 153–164, 171–176, 187–194,
201–210, 219–226`.

| intent                                | `_REQUIRED_FIELDS`                                                                                          |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `objective_value`                     | `action_objective`, `units.objective`                                                                       |
| `objective_delta`                     | `baseline_objective`, `action_objective`, `objective_delta_absolute`, `objective_delta_percent`             |
| `feasibility_status`                  | `feasible`, `feasibility_breakdown`                                                                          |
| `route_count`                         | `n_routes`                                                                                                  |
| `single_customer_route_membership`    | `routes[].customer_ids`                                                                                     |
| `same_route_boolean`                  | `routes[].customer_ids`                                                                                     |
| `route_end_time`                      | `route_end_times[].route_idx`, `route_end_times[].end_time`                                                 |
| `customer_arrival`                    | `customer_schedule[].customer_id`, `customer_schedule[].arrival`                                            |
| `lateness_summary`                    | `n_late_customers`, `late_customer_ids`                                                                     |
| `before_after_comparison`             | `baseline_solution`, `diff`                                                                                 |
| `new_customer_assignment`             | `new_customer_ids`, `routes[].customer_ids`                                                                 |
| `full_route_listing`                  | `routes[].customer_ids`                                                                                     |
| `refusal_or_insufficient_payload`     | (empty)                                                                                                     |
| `unknown`                             | (empty)                                                                                                     |
| `perturbation_summary`                | (empty — perturbation card is always producible)                                                            |
| `scenario_summary`                    | (empty)                                                                                                     |
| `solution_summary`                    | `feasible`                                                                                                  |
| `perturbation_impact_summary`         | `baseline_solution`, `diff`                                                                                 |
| `route_impact_summary`                | `baseline_solution`, `diff`                                                                                 |
| `what_to_watch`                       | (empty)                                                                                                     |

### 2.2 Escape hatches in `answerability.py`

Five places relax the required-field check. I number them as the prompt
asks:

1. **`answerability.py:121–124`** — OBJ-inline `before_after_comparison`:
   if `_obj_delta_already_covered` (baseline_objective + action_objective
   + objective_delta_absolute all present), `missing = []`.
2. **`answerability.py:153–164`** — overview impact intents
   (`perturbation_impact_summary`, `route_impact_summary`): if
   `not_answerable` and any of `feasible / action_objective / routes /
   customer_schedule / n_routes` is present, downgrade to
   `partially_answerable`. Lets the renderer describe the current state.
3. **`answerability.py:171–176`** — `solution_summary` downgrades from
   `not_answerable` to `partially_answerable` if any of `action_objective
   / routes / customer_schedule / n_routes` is present.
4. **`answerability.py:187–194`** — `perturbation_impact_summary` flips
   to `answerable` (with `missing = []`) if `baseline_objective` and
   `objective_delta_absolute` are both present. Objective-level impact
   is grounded by OBJ-inline deltas.
5. **`answerability.py:201–210`** — false-premise override: for
   customer-bound or route-bound intents, if the named entity is not in
   the payload, `status = not_answerable, missing = []`. This is the one
   that pairs with the entity-resolution module — the amendment's
   entity-aspect dispatcher must call into the same lookup.

A 6th, at **`:219–226`**, is the ambiguous-comparison-referent extension
to `objective_delta` (adds `reference_solution.objective` to missing).
Not strictly an escape hatch — it's a missing-field *addition* — but
it's the one place answerability synthesises a field path that does
not exist in any payload (always absent per section 1.3).

### 2.3 Proposed aspect clustering (the opinion section)

Clusters are proposed below. Each row says (a) which payload field paths
belong, (b) which intents currently consume them. Field paths inside
brackets are **not actually present in any Run 1 payload** but are
referenced by infrastructure.

| aspect family       | payload field paths (present)                                              | intents consuming                                                |
| ------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **cost**            | `action_objective`, `baseline_objective`, `units.objective`                | `objective_value`, `objective_delta`, `before_after_comparison`* |
| **delta**           | `objective_delta_absolute`, `objective_delta_percent` *(+[`baseline_solution`, `diff`])* | `objective_delta`, `before_after_comparison`, `perturbation_impact_summary`, `route_impact_summary` |
| **feasibility**     | `feasible`, `feasibility_breakdown.*`, `infeasibility_kind`, `unserved_customer_ids`, `n_unserved_customers` | `feasibility_status`, `solution_summary`              |
| **structure**       | `n_routes`, `routes[].customer_ids`                                        | `route_count`, `single_customer_route_membership`, `same_route_boolean`, `full_route_listing`, `new_customer_assignment` |
| **timing**          | `route_end_times[].end_time`, `route_end_times[].has_time_warp`, `customer_schedule[].arrival`, `customer_schedule[].start_service`, `customer_schedule[].end_service` | `route_end_time`, `customer_arrival` |
| **lateness**        | `n_late_customers`, `late_customer_ids`, `customer_schedule[].is_late`, `customer_schedule[].lateness_minutes` | `lateness_summary` (only; `customer_schedule[].lateness_minutes` unsurfaced today) |
| **time windows**    | `customer_schedule[].tw_early`, `customer_schedule[].tw_late`              | none (unsurfaced)                                                |
| **units**           | `units.objective`, `units.time`                                            | `objective_value`/`objective_delta` (units.objective only)       |
| **counts**          | `n_routes`, `n_late_customers`, `n_unserved_customers`                     | `route_count`, `lateness_summary`, none (n_unserved unsurfaced)  |
| **identity / membership** | `routes[].customer_ids`, `routes[].route_idx`, `customer_schedule[].customer_id`, `customer_schedule[].route_idx`, augmented `route_label` | `single_customer_route_membership`, `same_route_boolean`, `full_route_listing`, `new_customer_assignment` |

Notes / field paths that don't cleanly fit one aspect:

- `units.objective` straddles **cost** and **units**. Could be a sub-attribute of cost.
- `objective_delta_absolute` straddles **delta** and **cost**. Currently OBJ-inline is the cost domain's substitute for `baseline_solution/diff`.
- `routes[].customer_ids` is both the **structure** and **identity/membership** primitive.
- `route_end_times[].has_time_warp` is **timing** but really a feasibility signal — the route had to "time-warp" to be feasible. Today only surfaced by `route_end_time` evidence.
- `infeasibility_kind` is **feasibility** but it's also a *cause* hint — the one place a payload says *why* infeasibility occurred. The amendment may want to elevate it as a "diagnostic" sub-aspect.
- `n_unserved_customers` and `unserved_customer_ids` are **counts** + **feasibility** + **identity** simultaneously.

The fact that **every aspect family corresponds to one payload family**
(except identity/membership, which spans STRUCT and SCHEDULE) is the
biggest structural fact in this audit. **PRESSURE POINT**: aspect
dispatch *cannot* surface a "lateness" answer from an OBJ payload —
the field paths aren't there. The aspect layer's value-add is on
prompts whose family was *correctly* identified by D1's family routing
but whose intent fell off the 20-intent vocabulary.

---

## 3. Entity registry analysis

### 3.1 Per-entity representation

| entity         | representation                                                                                              | canonical set per scenario                                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **customer**   | `int` ID throughout the payload (`routes[].customer_ids`, `customer_schedule[].customer_id`, `late_customer_ids`, `unserved_customer_ids`, `new_customer_ids`). | Union of those lists. Computed by `product/data/entity_resolution.py:34–57` (`available_customer_ids`).                                                  |
| **route**     | Internal `route_idx: int` (0-indexed) and user-facing `route_label: str` ("Route N", N = idx+1).             | Internal: `available_route_idxs` (`entity_resolution.py:92–104`). User-facing: `available_display_route_numbers` (`entity_resolution.py:107–109`) = `{idx+1 for idx in idxs}`. |
| **vehicle**    | No dedicated entity. `n_routes` is the only count. (inference) "Vehicle" and "route" are used interchangeably in prompts.                          | No registry — `n_routes` is the only signal. (inference)                                                                                                |
| **depot**     | Geometry only: `instance.depot.{x,y}` in the scenario response (`scenario_store.py:218`). No depot id in payload_snapshot. | The block exists only after `_build_instance_block` (`scenario_store.py:195–222`); never reaches `copilot_service.ask` because `ask()` only calls `augmented_payload`, not `build_scenario_response`. |
| **perturbation** | `perturbation_id: str` (e.g. "OC_1", "TT_4", "TW_5") on the `ScenarioRow` (`scenario_store.py:50`); `perturbation_family` (e.g. "ORDER_CHANGE", "TRAVEL_TIME", "SERVICE_TIME", "TIME_WINDOW") (`scenario_store.py:54`). | The `ScenarioRow` itself. Family map in `_PERTURBATION_SUMMARIES` (`scenario_store.py:169–174`) and `_PERTURBATION_EXPLANATIONS` (`explanation_context.py:57–112`). |

### 3.2 The false-premise lookup path

For customer-bound intents (`product/data/answerability.py:23–27`)
the lookup is:

```
answerability.compute_answerability  (answerability.py:201)
  → entity_resolution.prompt_references_unknown_customer  (entity_resolution.py:64)
      → entity_resolution.prompt_customer_ids  (entity_resolution.py:60)        # regex: r"\bcustomer\s+(\d+)"
      → entity_resolution.available_customer_ids  (entity_resolution.py:34)     # walks routes / customer_schedule / late_/new_/unserved_*
```

Route-bound intents (`route_end_time` only) follow the same shape but
with `available_display_route_numbers` and the regex
`r"\broute\s+(\d+)"` (`entity_resolution.py:18–19, 116–122`).

### 3.3 Shared helper vs ad-hoc

`entity_resolution` is the **single shared helper** for customer/route
*existence*. But the lookups are **duplicated across three sites**:

1. `product/data/answerability.py:201–210` — short-circuits status to
   `not_answerable`.
2. `product/copilot/refusal_policy.py:24–34, 202–226` — `_is_false_premise_case`
   re-checks the same predicate to drive `false_premise_detected` warning
   and the useful-refusal sentence.
3. `product/data/evidence.py:16–21, 400–407` — short-circuits evidence
   to `[]`.

All three sites import `entity_resolution`, so the **predicate** is
shared. What's duplicated is the **set membership check** of
`_CUSTOMER_BOUND_INTENTS` / `_ROUTE_BOUND_INTENTS` — that constant is
re-declared in all three files (`answerability.py:23–28`, `evidence.py:16–21`,
`refusal_policy.py:16–21`). If the amendment widens which intents are
"entity-bound" (e.g. to make `lateness_summary about customer N` an
entity-bound query when `customer_N` is referenced), all three sets
need the same change.

There is **no shared helper for entity *extraction from prompt text***
beyond the two regexes in `entity_resolution.py:18–19`. The LLM frame
holds an independent extraction in `entities.customer_ids` /
`entities.route_labels` (`llm_query_frame.py:98–101`). The two paths
do not consult each other.

**PRESSURE POINT**: the amendment will introduce a third extractor (or
unify the existing two). If the entity-aspect dispatcher uses the LLM's
extraction, then validation against canonical sets must happen at one
place, not three. If the prompt-regex path is preferred (deterministic
fallback when LLM is unavailable), the regex is currently only
customer/route shaped — it would need extension for "the depot",
"vehicle 3", "the new orders", etc.

There is **no entity registry for vehicles, depots, or perturbations**
beyond the constants in `_PERTURBATION_SUMMARIES`. A
"perturbation aspect" question (e.g. "what changed about the time
windows?") cannot today be validated against a canonical set —
perturbations are identified by string IDs and family labels, not by
structured records.

---

## 4. LLM frame contents at `unknown` outcome

### 4.1 The LLM frame schema

`LLMSemanticFrame` (`product/copilot/llm_query_frame.py:104–121`) carries:

- `intent: str` — one of `ALLOWED_INTENTS` or `"unknown"`.
- `confidence: float [0,1]`
- `entities: LLMEntities` with `customer_ids: list[int]`, `route_labels: list[int]` (note: `int`, not `str`, despite "label") (`llm_query_frame.py:98–101`).
- `requires_baseline: bool`
- `comparison_type: str` (one of `ALLOWED_COMPARISON_TYPES` — `none / baseline / previous_solution / reference_solver / implicit / unsupported`)
- `causal_request: bool`
- `recompute_request: bool`
- `ambiguity: LLMAmbiguity` (`is_ambiguous`, `reason`)
- `alternative_intents: list[LLMAlternativeIntent]` (each: `intent`, `reason`)

There is **no aspect/topic/facet/subject field** today. Everything is
intent-centric.

### 4.2 What happens in `hybrid_guarded` mode when the result is `unknown`

`infer_intent_hybrid_guarded` (`product/copilot/llm_semantic_intent_adapter.py:569–658`):

1. Runs D1 first (`:587`).
2. If D1 is **not** in `_RISK_ZONE_INTENTS` (`:109–114`: `objective_value`,
   `objective_delta`, `single_customer_route_membership`, `unknown`),
   D1 is accepted and **the LLM is not called** (`:592–597`). The
   `QueryFrame` returned is the C0/D1 frame — entities are empty
   (`QueryFrameEntities()` default) unless D1's `semantic_adapter`
   layer populated them (it does not; the D1 adapter is intent-only —
   `product/copilot/semantic_intent_adapter.py` only emits an intent
   string + override notes, no entities).
3. If D1 is in the risk zone (including `unknown`), call the LLM (`:600`).
4. The LLM frame is validated through `validate_llm_frame`
   (`:215–279`), which returns one of:
   - `accepted`
   - `rejected_invalid_enum` (intent not in enum, or comparison_type not in enum)
   - `rejected_low_confidence` (confidence < 0.60, or 0.60–0.80 and D1 disagrees)
   - `rejected_ambiguous` (LLM flagged is_ambiguous)
   - `rejected_unsafe_semantics` (causal_request true with incompatible intent, malformed entity)
5. If rejected, the adapter returns the **D1 frame** (`:618–621`). **The
   LLM frame is discarded.** The metadata records `fallback_to_d1`.
6. If accepted and D1=unknown but LLM≠unknown, the LLM frame is
   preferred (`:634–638`). If both agree, prefer D1 (`:641–645`). If
   LLM≠D1 but LLM is high-confidence, prefer LLM (`:648–652`).

**The crucial bookkeeping**: when validation fails, **the rejected LLM
frame's entities are not propagated** (`:613, 621`). The function
returns `d1_frame`, not the LLM frame. The metadata block
(`LLMAdapterMetadata`, `llm_query_frame.py:145–162`) carries provenance
(`mode`, `source`, `accepted`, `fallback_used`, `fallback_reason`,
`confidence`, `validation_outcome`, `d1_intent`, `llm_intent`) but
**does not carry the LLM's `entities` or `comparison_type`**. So even
the metadata view downstream loses the entity extraction.

### 4.3 Path from `unknown` to the response

When the final `intent` is `"unknown"`, this is most commonly because:

(a) D1 returned `unknown` and the LLM frame was rejected → adapter
returns D1's `unknown` frame (`:618–621`); or
(b) D1 returned `unknown`, LLM call failed (`:608–613`) → adapter
returns D1's `unknown` frame; or
(c) Adapter dispatched to `infer_intent_d_final_frame` with `client=None`
(the API default — `copilot_service.py:73–86`), which falls through to
D1 deterministically (`llm_semantic_intent_adapter.py:685–699`) — no
LLM call at all, and D1 returned `unknown`.

In all three cases the resulting `QueryFrame` carries
`intent="unknown"`, default-empty `entities`, `confidence` from D1
(which is `1.0` per `semantic_intent_adapter` (inference)),
`requires_baseline=False`, `comparison_type="none"`.

### 4.4 Existing semantic flags that an aspect layer could read

Even though there is no `topic` field, several existing LLM frame flags
*proxy* aspect-shape information:

- `requires_baseline: bool` + `comparison_type` → **delta / change** aspect signal.
- `causal_request: bool` → **causality** aspect signal.
- `recompute_request: bool` → **planning request** signal (not aspectual but useful for the unknown-route dispatcher).
- `ambiguity.reason: str` → free-text. The LLM sometimes encodes "the user is asking about lateness for customer N" here. (inference; would need a sample of real outputs to confirm).
- `alternative_intents: list` — when the LLM is unsure, it lists the second/third candidates *with reasons*. These reasons are an existing aspect-like signal at zero marginal cost. (inference)

### 4.5 Easier-than-design implication

**Significantly easier than the design implies**, with one caveat. The
LLM already extracts `entities.customer_ids` and `entities.route_labels`
**unconditionally** (the system prompt at
`llm_semantic_intent_adapter.py:118–165` instructs it to fill them whenever the prompt names IDs, regardless of intent). The Pydantic schema permits empty lists as defaults (`llm_query_frame.py:100–101`).

**Caveat**: the current code path **throws the LLM frame away** on
rejection (`llm_semantic_intent_adapter.py:608–621`). The amendment
needs the adapter to **return the LLM frame (or its entities) even on
rejection**, so the aspect dispatcher has them. This is a one-shape
change:

- Option A: extend `LLMAdapterMetadata` to hold the rejected LLM frame
  (or just its `entities` + `comparison_type` + `causal_request`).
- Option B: have `infer_intent_d_final_frame` return a third value — the
  raw `LLMSemanticFrame` regardless of validation outcome — so
  downstream can read entities without trusting the intent.
- Option C: when D1 returns `unknown` and the LLM frame is rejected,
  return an `unknown` `QueryFrame` populated with the LLM's entities
  (`QueryFrameEntities` already has the slots:
  `product/copilot/query_frame.py:36–39`).

Option C is the smallest change, but care: the entity is currently
considered "unknown-but-named", so it bypasses the false-premise check
unless the new dispatcher re-runs it.

---

## 5. Refusal traffic sample

There is **no production telemetry for `/copilot/ask`**. Specifically:

- `product/api/app.py:159–211` has no logging beyond the
  default-uvicorn access log; the body of `copilot_ask` does not
  capture `intent`, `behavior_class`, or `validation_outcome` to disk.
- `product/api/copilot_service.py:175–198` uses `logging.getLogger`
  only in the verbalization fallback (`:194`) to emit an exception trace.
- Run-2 evaluation outputs (`product/evaluation/reports/*.csv`,
  `product/evaluation/system_d_final/reports/*.csv`) are the only
  source of historical (intent, behavior_class) data. These are
  **evaluation runs against the locked 60- or 48-case sets**, not
  production traffic.

### 5.1 What the eval corpus tells us about `unknown` outcomes

The deepest unknown count I found was the D1 stress report
(`product/evaluation/system_d1/reports/system_d1_stress_report.csv`,
96 rows). C0 returns `unknown` on **11 of 96 stress cases**. The
**D1 adapter rescued every single one** — `d1_predicted_intent` is
never `unknown`. All 11 cases are paraphrase-axis stress cases where
the C0 regex misses but D1's lexical adapter (e.g.
`schedule_completion_verb='close out'`, `full_route_listing_phrase='every route'`,
`schedule_lateness_phrase='served after their allowed time'`) catches.

In the Run-2 60-case benchmark (`product/evaluation/reports/run2_benchmark_eval_system_c.csv`),
C0 returns `unknown` on **2 of 60** cases (R2-048, R2-049). Both are
`full_route_listing` cases with paraphrases C0's regex didn't catch
("List the customers on each route after the new stops were added.";
"Which customers are on each vehicle in the current plan?"). The
**`unknown` reached the behavior class `useful_refusal`** in both
cases — they are concrete examples of the current pipeline emitting
"I could not classify this question" on questions whose payload would
have answered them in full.

In the D-Final reports
(`product/evaluation/system_d_final/reports/d_final_*_report.csv`,
108 rows across semantic_holdout / axis3_live / core), **zero
predicted_intent values are `unknown`**. D-Final's
`validation_outcome` is `accepted` for all 48 semantic-holdout rows
and all 60 core rows.

### 5.2 Aggregate

Putting it together:

- 96 D1 stress cases: 11 C0 unknowns, 0 D1 unknowns.
- 60 Run-2 benchmark (system C, pre-D1): 2 unknowns.
- 60 + 48 D-Final eval: 0 unknowns.

**The empirical "fall-through" rate is in the single digits across
locked eval sets.** There is no production log of operator queries.
The user's amendment will need an instrumentation step
(API request log capturing `intent`, `validation_outcome`,
`entities.customer_ids`, `entities.route_labels`) to measure impact
in the field. **PRESSURE POINT**: the design's value is mostly
*off-distribution* — questions the locked eval set doesn't cover.
Without instrumentation, the amendment's lift cannot be measured
against real traffic.

---

## 6. Response builder coupling

The dashboard pipeline has **two response builders**:

1. **API path (production)**: `product.api.copilot_service.ask`
   (`copilot_service.py:201–351`). This is what `/copilot/ask` hits.
   It does **not** call `product.copilot.response_builder` —
   `response_builder.build_replay_response`
   (`response_builder.py:143–228`) is a Stage 2 replay builder that
   loads Run 1 bundles. The API builds its own shape from
   `PredictedContractDFinal` fields.

2. **Replay path (offline)**: `product.copilot.response_builder` and
   `product.copilot.verbalization` (`verbalization.py:810–889`). The
   API does use `verbalize` (`copilot_service.py:177–192`) to render
   `answer_text`, but the surrounding shape (evidence/warnings/
   behavior_class) is taken from the contract's structured fields.

### 6.1 Dispatch sites

`verbalization.verbalize` (`verbalization.py:810–889`) branches on
`behavior_class` **first** (`:830`, `:834`, `:838`), and on `intent`
**second** to pick the renderer:

```
if compute_decision.mode == "needs_recompute":      → render_compute_decision
elif behavior_class == "useful_refusal" or
     answerability == "not_answerable":             → render_useful_refusal
elif behavior_class == "partial_answer_with_warning": → render_partial_answer
else:                                                # direct_answer*
    if intent == "objective_value":                  → render_objective_value
    elif intent == "objective_delta":                → render_objective_delta
    ... (large else-if chain)
    else: text = f"Intent '{intent}' — no verbalizer implemented."
```

The "direct_answer" branch has 14 explicit `intent` arms and a generic
fallback at `:881` that produces `"Intent 'unknown' — no verbalizer
implemented."` for any unknown intent. (`verbalization.py:840–882`)

### 6.2 Can `intent=unknown` + populated evidence + `partial_answer_with_warning` flow through today?

Walking it through the verbalizer:

- `compute_decision.mode` for an `unknown` intent without any explicit
  recompute/comparison/clarification triggers is `clarification_needed`
  (because `decide_compute` at
  `system_d4/compute_decision.py:891–909` collapses `not_answerable` to
  `clarification_needed`). With evidence populated, the contract path
  computes `answerability.status` via the `unknown` branch of
  `answerability.py:129–130` → `not_answerable`. Then
  `run2_system_c._infer_behavior_class` (`run2_system_c.py:88–98`)
  returns `useful_refusal` for `not_answerable` *regardless of
  evidence count*.
- **So today, the path `intent=unknown` + populated evidence cannot
  reach `partial_answer_with_warning`**. Two things gate it:
  1. `answerability.compute_answerability` forces
     `unknown → not_answerable` at `:129–130`.
  2. `_infer_behavior_class` ignores evidence when status is
     `not_answerable` (`:98`).

The smallest change to make the path possible:

- Add an "unknown-but-aspectual" status (or treat `unknown` like the
  overview intents do — let answerability return
  `partially_answerable` when evidence can be assembled). The
  answerability function is pure (`:106–236`) so this is local.
- Teach `_infer_behavior_class` to honour evidence when intent is
  `unknown` (one branch).
- The verbalizer's `partial_answer_with_warning` dispatch
  (`verbalization.py:712–758`) has `else: partial = "Partial information
  is available."` which is a usable fallback. To do better, add an
  `intent == "unknown"` arm that walks the evidence items by aspect.

This is the **largest architectural lift** in the audit — not because
any one site is gnarly, but because at least three modules
(`answerability`, `_infer_behavior_class`, `verbalize`) need an
"unknown-with-evidence" branch. **PRESSURE POINT**: the response
builder is *currently* intent-shaped only at the surface (the dispatch
tree) — the structural shape underneath is `behavior_class`-shaped.
That's the good news. The bad news is `_infer_behavior_class` does not
treat `unknown` as a valid "answer-with-evidence" carrier today.

### 6.3 Where `aspectual_dispatch` metadata attaches

Phase 8 in `copilot_service.ask` (`copilot_service.py:312–325`) is the
attachment point for `semantic_adapter` metadata. It's a `dict`-shaped
block on the response. **Yes, this is the natural spot.** Add an
`aspectual_dispatch` block alongside `semantic_adapter`:

```python
if predicted.aspectual_dispatch is not None:
    result["aspectual_dispatch"] = {
        "triggered": True,
        "intent_at_dispatch": "unknown",
        "entities_extracted": {...},
        "aspect_family": "lateness",
        "field_paths_surfaced": [...],
    }
```

`CopilotAskResponse` already has `model_config = ConfigDict(extra="allow")`
(`product/api/models.py:233`), so adding a top-level field is
forward-compatible. **No schema change is needed on the response shape**
beyond adding the optional block.

### 6.4 Frontend coupling

The frontend reads `evidence[].field_path`, `evidence[].value`,
`evidence[].display_anchor` per `evidence_anchors.py:127–173`. The
anchor switch (`:139–173`) keys on the *field_path's prefix*. New
field paths surfaced by the aspect layer (e.g.
`customer_schedule[customer_id=42].lateness_minutes`) will route to
`customer_arrival` anchor (`:162–171`) — works for free. New unsurfaced
paths (e.g. raw `feasibility_breakdown.capacity_ok`) fall through to
`{"type": "solution_summary"}` (`:139–140` already lists it). **No
frontend changes are forced by the amendment.**

---

## 7. Phase-by-phase impact

`copilot_service.ask` runs 10 logical phases. I number them as the
prompt does (1=normalize through 10=final assembly).

| Phase | Lines | Assumes `intent != unknown`? | Notes / impact                                                                                                                                                                                                                                                                                                                                                                                |
| ----- | ----- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | 209   | no                            | Normalizes `system` name; no intent.                                                                                                                                                                                                                                                                                                                                                          |
| 2     | 210–213 | no                          | Builds case + payload; no intent.                                                                                                                                                                                                                                                                                                                                                              |
| 3     | 215–220 | no                          | Dispatches to runner (D-Final via `_run_d_final_on_case`, `:73–86`). Returns `PredictedContractDFinal` with a possibly-`unknown` `predicted_intent`.                                                                                                                                                                                                                                            |
| 4     | 224–229 | partial                     | Calls `_resolve_evidence_items` which calls `evidence.build_evidence_items(intent=...)`. For `intent="unknown"`, the function falls through to `return []` (`evidence.py:429`). **PRESSURE POINT**: the aspect layer needs to be hooked in here — either by re-running evidence extraction in "aspect mode" or by an upstream call that pre-fills `evidence_items` when intent is unknown.       |
| 5     | 230–264 | **yes**                     | Resolves `field_path → value`. Loop is keyed on `predicted.predicted_evidence_paths`. **For `intent=unknown`, this list is empty today** (`evidence.py:429` returns `[]` and the contract emits no paths). The phase will simply emit `evidence_out=[]` — no crash, but no aspect data surfaces. Behavior is graceful but useless.                                                              |
| 6     | 271–303 | no (graceful)               | Overview-intent post-processing is gated on `predicted.predicted_intent in OVERVIEW_INTENTS`. `unknown` is not in `OVERVIEW_INTENTS` (`llm_query_frame.py:54–61`), so the block is skipped. **Confirmed graceful skip.**                                                                                                                                                                          |
| 7     | 305–309 | no                          | Reads `compute_decision` if available. `decide_compute` accepts an `intent` of any string and projects via `intent_to_query_family` (`system_d4/compute_decision.py:186–214`). When intent is unknown, the family resolves to `UNKNOWN` (`:214`). The precedence ladder (`:760–910`) still runs — when answerability_status is `not_answerable` and no trigger fires, it returns `clarification_needed` (`:891–909`). With evidence present + intent unknown, it would still say `clarification_needed` because `not_answerable` is the bridge. **Returns a coherent result, but the recommendation is "ask the operator to refine"** — which contradicts having usable evidence. |
| 8     | 312–325 | no                          | Semantic-adapter metadata; **natural attachment point** for `aspectual_dispatch` metadata. The block is keyed only on `predicted.adapter_metadata` being non-None. (`copilot_service.py:313`)                                                                                                                                                                                                  |
| 9     | 327–328, 354–391 | no              | `_build_ui_actions` is keyed only on `compute_decision.get("mode") == "needs_recompute"` and the action being in `ALLOWED_ACTIONS`. For `intent=unknown` the mode will be `clarification_needed`, so this returns `[]`. **PRESSURE POINT**: when the aspect layer makes the intent path coherent, the recompute affordance should still be suppressed for aspect-grounded answers — confirm the gate. |
| 10    | 330–351 | no                          | Final dict assembly. The response schema (`product/api/models.py:232–253`, `CopilotAskResponse`) has `intent: str` (`:237`), not the Literal type. No validation gate fails on `unknown`. **No assertions hold; the response can carry `intent=unknown` + populated evidence today.** It just won't, because phases 4–5 won't populate evidence.                                                |

Summary of phase-level changes the amendment will need:

- **Phase 4–5** (evidence): the aspect layer's primary insertion point.
  Either as a fork inside `evidence.build_evidence_items` (one branch
  for `intent="unknown" + entities + aspect`), or as an additional
  call in `copilot_service.ask` that overlays aspect-derived items
  when the contract emits nothing.
- **Phase 7** (compute_decision): `intent_to_query_family` already
  returns `UNKNOWN` (`compute_decision.py:214`); the question is
  whether D4 should change its mode from `clarification_needed` to
  something like `partial_from_payload` when the aspect layer fired.
  This is **out of scope** per the amendment's invariants (no D4
  changes) — but the `clarification_needed` recommendation will
  conflict with the aspect-grounded evidence visually. **PRESSURE POINT**.
- **Phase 8**: clean attachment point for metadata. No structural change.

---

## 8. Sufficiency gate interaction

The gate (`product/copilot/sufficiency_gate.py`) is **disabled by
default** (`:118–121, 453–472`) — controlled by env var
`PRODUCT_USE_LEARNED_SUFFICIENCY_GATE` (`:61`). The D-Final API path
does not flip this on (`copilot_service.py` does not touch the env
var; `d_final_system_c.py:128–135` calls `decide_compute` without the
`use_learned_sufficiency_gate` arg, so the default `None` path runs
which checks `gate_enabled()` (`compute_decision.py:967–969`)).

### 8.1 Does the gate run if intent is unknown?

Only if D4 first lands on `answer_from_payload`. The gate's gating
invariants are at `compute_decision.py:967–974`:

```python
if not use_gate: return decision
if decision.mode != "answer_from_payload": return decision
if family not in _GATE_SUPPORTED_FAMILIES: return decision
```

`_GATE_SUPPORTED_FAMILIES = {OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE}`
(`sufficiency_gate.py:68–70`). When `intent="unknown"`,
`intent_to_query_family` returns `"UNKNOWN"`
(`compute_decision.py:214`). `"UNKNOWN"` is **not** in
`_GATE_SUPPORTED_FAMILIES`, so the third check returns early.

**Confirmed: today, the gate **never** fires for `intent=unknown`.** It
abstains by family.

Independently, the gate also won't fire for an unknown intent because
`decision.mode` won't be `answer_from_payload` — the D4 ladder routes
unknown intents to `clarification_needed` (`:891–909`).

### 8.2 Feature extraction dependence on intent

`predict_sufficiency` (`sufficiency_gate.py:423–449`) takes `family`,
not `intent`. Feature extraction
(`_extract_feature_dict`, `:298–402`) pulls from
`payload_snapshot`, `action_context`, `perturbation_context` —
all family- and perturbation-shaped, no intent dependency.
**Confirmed: feature extraction is intent-independent.**

### 8.3 Behavior if gate were forced on for an aspect-grounded unknown response

If the user's amendment widens the family check to admit a synthetic
"family" for aspect responses (it won't, per invariant 1 — the
amendment is additive), the gate could in principle fire. But:

- The gate would predict against the *family* the payload belongs to
  (OBJ/PV/STRUCT/SCHEDULE), so the prediction would be the same as if
  the prompt had been classified to a within-family intent.
- The `recommend_recompute` output would still resolve to
  `run_pyvrp_10s` by default (`sufficiency_gate.py:586–587`). This
  would mark the response as "recommend recompute" for a question that
  was just *answered from the payload*. That is incoherent.

**Recommended behaviour, matching the user's intent**: the gate should
abstain on aspect-grounded unknown responses. The current code does
this for free (via the family-membership check at line 973). The
amendment does not need to touch the gate at all *if the aspect layer
keeps `intent_to_query_family` returning `UNKNOWN`*.

**PRESSURE POINT**: if a future iteration of the aspect layer wants the
gate to apply (because aspect-grounded answers *can* still be
insufficient), `_GATE_SUPPORTED_FAMILIES` would need extending. Not in
scope for this amendment.

---

## 9. Open questions

These are for the user to decide before implementation. I have **not
resolved** any of them.

### 9.1 Design conclusions to make

1. **Where does aspect dispatch run?** Two viable hooks:
   - Inside `evidence.build_evidence_items` as an `intent="unknown"`
     branch that consumes the LLM frame's `entities` + a derived
     aspect. Minimum-blast-radius.
   - As a fourth module called from `copilot_service.ask` between
     phases 4 and 5, overlaying onto `evidence_items` when intent is
     unknown. More visible but more files touched.

2. **How is the aspect derived from the prompt + LLM frame?** The LLM
   today emits no `topic`/`facet` field (section 4.1). Options:
   - Extend `LLMSemanticFrame` with an optional `aspect: str` field
     (constrained to a closed vocabulary — matches the 10 aspect
     families in section 2.3). Adds an LLM call shape to retrain.
   - Use existing flags (`requires_baseline`, `causal_request`,
     `comparison_type`) as proxies + a regex lookup over prompt text
     for aspect keywords ("lateness", "arrival", "feasibility",
     "cost", "time window", ...). No LLM-side change.
   - Reuse `alternative_intents[].intent` — when D1+LLM both reject
     the primary intent, the LLM's alternatives are usually
     aspect-coherent (e.g. it lists `lateness_summary` as alt 1, then
     `customer_arrival` as alt 2 → "schedule/lateness aspect"). Needs
     a sample of real alternatives to evaluate.

3. **Should the entity-extractor consume the LLM's `entities` or run
   its own regex?** The LLM frame's `entities.customer_ids` is rich
   (handles "the customer with the late delivery", "customer 42",
   "customers 1, 3, and 5"). The deterministic regex
   (`entity_resolution.py:18`) only handles `customer N`. Three modes:
   - **LLM-only**: prefer LLM entities; refuse to fall back to regex
     when client is unavailable. Means aspect layer is offline when
     the LLM is.
   - **Regex-first, LLM as backup**: deterministic when client absent;
     LLM extension when present.
   - **Union**: always merge both. Simpler to reason about; risks
     LLM hallucinating IDs.

4. **What is the canonical entity set for vehicles and depots?** Today
   there is none (section 3.1). Vehicles map 1:1 to routes (`n_routes`),
   but depot is a single point and the payload doesn't even carry it
   (geometry-only). If aspect dispatch is supposed to handle
   "what's at the depot?" or "how many vehicles are idle?", a registry
   change is needed.

5. **Should the entity extractor share `_CUSTOMER_BOUND_INTENTS` /
   `_ROUTE_BOUND_INTENTS` with answerability+refusal+evidence?** The
   constant is currently re-declared in three files (section 3.3). Is
   this amendment the moment to extract a shared module
   (`product.data.entity_intents` or similar)? Or scoped out?

6. **How does the response builder dispatch on
   `intent=unknown + populated evidence`?** Section 6.2 shows three
   modules need an "unknown-with-evidence" branch:
   `compute_answerability`, `_infer_behavior_class`, and `verbalize`.
   Is the right approach:
   - Add an explicit `aspectual_answer` behavior class (5th value,
     joining `direct_answer / direct_answer_with_warning /
     partial_answer_with_warning / useful_refusal`)? Breaks the
     four-valued enum.
   - Reuse `partial_answer_with_warning` and let the verbalizer's
     `else` branch handle aspect rendering?
   - Add an `aspect_dispatch` block to `CopilotAskResponse` separate
     from `evidence` (display the aspect facts as a parallel artifact
     rather than as `evidence[]`)?

7. **What does `compute_decision` say for an aspect-grounded unknown
   response?** The current ladder routes `not_answerable` → `clarification_needed`
   (`compute_decision.py:891–909`). The recommendation will be
   `ask_clarification`, with no recompute affordance. That is *probably*
   right (we just answered the operator; no need to ask back), but the
   `reason` text ("D4 recommends asking the operator to refine the
   question") will read oddly next to evidence. Either:
   - Carve out an `unknown + aspect_dispatch_active` branch that
     returns `partial_from_payload` (changes D4 — out of scope).
   - Leave D4's output as-is but have the response builder suppress
     `compute_decision` rendering when `aspectual_dispatch.triggered`
     is true. Smaller change.

8. **What's the legitimate-refusal fallback?** When the amendment's
   second branch (`intent==unknown` AND extractors empty) fires, today
   that path also returns useful_refusal with a generic
   "could not classify" message
   (`refusal_policy.py:239–244`). The amendment's design says "same as
   today", but: does the user want the refusal text differentiated
   for "no entities" vs "no intent"? Today they are identical strings.

### 9.2 Data questions

9. **Aspect taxonomy granularity**: section 2.3 proposes 10 aspect
   families. Some collapse cleanly into one (units → cost; counts →
   structure/lateness). Some are speculative (time-windows aspect is
   present in payloads but never queried by any locked prompt). What
   is the right granularity for the first version — 4 (matching the
   payload families)? 10? Per-payload-field?

10. **Per-family payload sharding** (section 1.2): the four payload
    families are non-overlapping. Does the amendment need to detect
    cross-family aspect questions (e.g. "is the new customer late?" —
    a STRUCT+SCHEDULE question)? Today this would fail because no
    payload has both routes and customer_schedule. The current
    pipeline already has this problem; the amendment may not make it
    worse but should declare it explicitly.

11. **Instrumentation** (section 5): the API has no request log.
    Should the amendment include a "log every aspect-dispatch event"
    hook so the lift can be measured? Otherwise we are flying blind
    on the in-distribution rate of unknowns.

### 9.3 Implementation seams

12. **Adapter return signature** (section 4.5): one of options A/B/C to
    propagate rejected-LLM entities. Which one?

13. **Schema location for aspect labels**: if aspect is exposed on the
    LLM frame (open question 2, option A), where do the allowed
    aspect strings live? Mirroring the `ALLOWED_INTENTS` pattern
    (`llm_query_frame.py:24–51`) is the obvious move, but it adds
    another closed vocabulary the LLM must conform to.

14. **Verbalization for aspect output**: section 6 notes that
    `verbalization.py:881` says `f"Intent '{intent}' — no verbalizer
    implemented."` for `unknown`. The aspect layer needs a verbalizer.
    Should this be:
    - a new per-aspect renderer set (parallel to the 14 per-intent
      renderers in `verbalization.py:132–306`)? or
    - a generic "list these N field paths with their values" template?

15. **Frontend display anchor for aspect-only items**: today
    `evidence_anchors.field_path_to_display_anchor`
    (`evidence_anchors.py:127–173`) only knows route, customer, and
    solution_summary anchors. Aspect items with paths like
    `customer_schedule[].lateness_minutes` route correctly (they
    start with `customer_schedule` — line 162). Paths like
    `feasibility_breakdown.capacity_ok` hit the `_SOLUTION_SUMMARY_PATHS`
    set (`evidence_anchors.py:110–124`). New paths in unanchored
    territory (e.g. `customer_schedule[].tw_late`) would fall through
    to `{"type": "none"}` (`:173`). Is the renderer prepared to
    display evidence with no anchor?

---

## Summary call-outs

**Easier than design implies:**

- LLM frame already extracts `entities` (`llm_query_frame.py:98–101`) but
  the adapter discards them on rejection
  (`llm_semantic_intent_adapter.py:608–621`). Plumbing change, not a new
  extractor. (section 4)
- The frontend evidence anchor map already routes the most useful
  unsurfaced field paths
  (`customer_schedule[].lateness_minutes`,
  `customer_schedule[].tw_late`) to the customer-arrival anchor. No
  frontend change needed. (section 6.4)
- The API response shape (`models.py:232–253`) is `extra="allow"` and
  uses `intent: str` (not the contracts.py Literal), so phase-10 final
  assembly accepts `intent=unknown` + populated evidence without
  schema changes. (section 7)
- The sufficiency gate already abstains on `family=UNKNOWN`
  (`compute_decision.py:973`), so no gate changes required. (section 8)

**Harder than design implies:**

- `compute_answerability` forces `unknown → not_answerable`
  (`answerability.py:129–130`), and `_infer_behavior_class` then
  forces `not_answerable → useful_refusal`
  (`run2_system_c.py:98`) regardless of evidence count. To make
  `intent=unknown + evidence` flow through, both modules need a new
  branch, **and** the verbalizer needs an `intent=unknown`
  partial-answer arm. Three files. (section 6.2)
- Payload sharding is strict: each Run-1 payload carries one family's
  columns only (section 1.2). Cross-family aspects (e.g.
  "is the new customer in route 3 late?") cannot be grounded today —
  this is a property of the data, not the code.
- `_CUSTOMER_BOUND_INTENTS` is duplicated in three modules
  (`answerability.py:23`, `evidence.py:16`, `refusal_policy.py:16`).
  If the amendment widens entity-bound semantics, all three need
  parallel updates. Extracting a shared module is a prerequisite
  refactor (or accepted technical debt). (section 3.3)
- No production telemetry exists (section 5). The amendment's lift
  cannot be measured without instrumentation. The locked eval sets
  see between 0 and 11 unknowns out of 60–96 cases.

**Architectural pressure points (recap):**

- Lateness columns are the densest patch of present-but-unsurfaced
  data (section 1.4) — natural first aspect target.
- Aspect dispatch is structurally constrained to the present family's
  columns (section 2.3) — value-add is family-internal, not
  cross-family.
- Entity extraction lives in 3 sites today; widening it must keep them
  in sync (section 3.3).
- The adapter throws away the LLM frame on rejection (section 4) —
  this is the smallest plumbing change that unblocks the entire
  amendment.
- Three pipeline modules co-enforce `unknown → useful_refusal` today
  (section 6.2).
- `compute_decision` will read `clarification_needed` for any aspect-
  grounded unknown response (section 7, phase 7) — visual clash with
  the aspect-grounded evidence; suppress in the renderer.


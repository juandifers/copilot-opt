# Highlight contract

How a query type drives what the operator UI highlights. This is the spec the
backend implements and the frontend consumes. Keep it in sync with the code.

## Invariant (do not break)

Highlights are **deterministic output of the contract**, not a decision made by
the LLM or improvised in the frontend. The flow is:

```
LLM semantic adapter  ->  intent (one of the Intent enum values)
contract pipeline     ->  evidence[] + visual_actions[]   (infer_visual_actions)
API response          ->  carries intent, evidence (with display_anchor), visual_actions
frontend              ->  renders lens / selection / panel focus from visual_actions
```

The LLM never names a route, a customer, or a lens. It only produces the intent
and entities; `infer_visual_actions(intent, evidence)` turns that into highlight
hints. If you find yourself adding highlight logic to a prompt, stop — it belongs
in `infer_visual_actions`.

## Where each piece lives

- Intent enum: `product/copilot/contracts.py` (`Intent = Literal[...]`)
- Visual-action inference: `product/data/evidence.py` -> `infer_visual_actions(intent, evidence_items)`
- `VisualAction` model: `product/copilot/contracts.py` (`kind: str`, `target: dict`)
- Per-evidence anchors: `product/api/evidence_anchors.py` -> `field_path_to_display_anchor`
- API response schema: `product/api/schemas.py` (`visual_actions`) and `product/api/models.py` (`CopilotAskResponse`, `EvidenceItem.display_anchor`)
- Frontend response type: `frontend/src/api/types.ts` (`CopilotAskResponse`)
- Frontend shared state: `frontend/src/selection.ts` (`Selection`), `frontend/src/lens.ts` (`LensMode`), owned in `frontend/src/App.tsx`
- Frontend consumption today: `frontend/src/components/CopilotPanel.tsx` (`autoSelect`, ~line 960)

## Vocabulary (exact, current)

- `Intent`: objective_value, objective_delta, feasibility_status, route_count,
  single_customer_route_membership, same_route_boolean, route_end_time,
  customer_arrival, lateness_summary, before_after_comparison,
  new_customer_assignment, full_route_listing, refusal_or_insufficient_payload,
  unknown, perturbation_summary, scenario_summary, solution_summary,
  perturbation_impact_summary, route_impact_summary, what_to_watch,
  evaluate_plan_acceptability, evaluate_dimension_acceptability
- `VisualAction.kind` today: highlight_route, highlight_customer, show_schedule_row,
  show_route_end_time, show_feasibility_card, show_objective_card,
  show_lateness_summary, show_route_count
- `LensMode`: route | lateness | slack
- `Selection`: { none } | { route, idx, label? } | { customer, id } | { summary }
- `DisplayAnchor.type`: route | route_end | customer_arrival | solution_summary | none

## New VisualAction kinds to add

- `set_lens` — `target: { mode: "route" | "lateness" | "slack" }`
- `focus_panel` — `target: { panel: "map" | "schedule" | "tables" | "impact" }`

These keep lens-switching and panel focus deterministic and testable, instead of
hard-coding intent checks in the frontend.

## Intent -> presentation map

| Intent | set_lens | highlight | focus_panel |
|---|---|---|---|
| objective_value / objective_delta | route | summary | impact |
| feasibility_status | slack | tight stops | schedule |
| route_count | route | route(s) | tables |
| full_route_listing | route | route(s) | tables |
| single_customer_route_membership / same_route_boolean | route | queried customer(s) + their route | map |
| new_customer_assignment | route | the new customer + its route | map |
| route_end_time | lateness | route_end | schedule |
| customer_arrival | lateness | customer (+ its route) | schedule |
| lateness_summary | lateness | **every** late customer (multi) | schedule |
| before_after_comparison | route | changed routes/customers | impact (diff) |
| perturbation_impact_summary / route_impact_summary | route | impacted routes | impact |
| scenario_summary / solution_summary / perturbation_summary | route | summary | impact |
| what_to_watch | slack | at-risk stops | schedule |
| evaluate_plan_acceptability | route | summary | impact |
| evaluate_dimension_acceptability | (dimension-dependent: lateness for time, slack for feasibility) | offending stops | schedule |
| refusal_or_insufficient_payload / unknown | (leave user's lens) | none | surface AvailableFieldsStrip |

## Gaps to close (this is the work)

1. **Plumb `visual_actions` to the live endpoint.** It exists on
   `product/api/schemas.py` and is forwarded by `routes/prompts.py`, but the
   copilot-ask path (`copilot_service` -> `CopilotAskResponse`) and the frontend
   `CopilotAskResponse` type do not carry it. Add it to both.
2. **Add `set_lens` + `focus_panel`** to `infer_visual_actions`, per the table.
3. **`lateness_summary` must emit one `highlight_customer` per late stop.** Today
   it only emits `show_lateness_summary`.
4. **Fill missing intents** in `infer_visual_actions`: full_route_listing,
   new_customer_assignment, before_after_comparison, the *_summary intents,
   what_to_watch, evaluate_*.
5. **Frontend: consume `visual_actions`** in place of the single-anchor
   `autoSelect`. Set lens via `setLens`, focus via `setTablesTab` / scroll, and
   support a **set** of highlights (extend `Selection`, or add a parallel
   highlight set, so multi-target intents light up every stop).
6. **Finish Map selection wiring.** `App.tsx` notes "Map will adopt the same
   selection when it's wired" — wire it so a route/customer selection highlights
   on the map too.
7. **Refusal as a real state.** On refusal/unknown, do not yank the lens; instead
   surface the available-fields hint. This is the honest-refusal UX.

## Acceptance

A fixture `tests/product_api/test_highlight_contract.py` (or similar) asserts, for
a handful of representative prompts per intent, that the API returns the expected
`intent`, the expected `visual_actions` kinds, and the expected `set_lens` mode.
The same fixture doubles as the demo script. Run it alongside the existing
load-bearing tests; do not move or edit the locked benchmark.

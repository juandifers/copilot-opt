# SOLUTION DATA payload schemas — per-family rationale

Companion to `payload_schemas.json`. The schemas there are closed
(`additionalProperties: false`); this file argues why each field is in or
out per family and flags the places the spec template assumes fields that
do not exist in the raw action output.

## Shared design rules

### Op-validity vs faithfulness scoping

Op-validity is the family-specific binary deterministic check defined
per family below. It grades exactly one headline claim per family: the
stated objective for OBJ, the feasibility flag for PLAN_VALIDITY, the
route count or membership for STRUCT, the timing claims for SCHEDULE.

Faithfulness is the rubric-based prose-vs-payload verification covering
every other payload-supported claim the generator makes. An OBJ answer
that states both the absolute objective and a percent delta is scored
on faithfulness against both; op-validity grades only the absolute.
When an answer contains multiple payload-covered claims, faithfulness
earns the lower of the per-claim sub-scores.

This split is deliberate. Op-validity is binary and machine-checkable
per family; faithfulness is the broader prose verification. The rubric
in Prompt 4 encodes this scoping explicitly.

### Payload construction

These apply to every family.

- **Identifying metadata stays in CONTEXT, not in the payload.** The spec's
  prompt template already routes `instance_id`, perturbation description,
  and action name through a CONTEXT block. Putting them in SOLUTION DATA
  too gives the generator two surfaces to "cite", which encourages
  paraphrasing context as evidence. Keep it on one surface.
- **Units are published Solomon units, never PyVRP scaled units.** The
  solver internally scales by `SCALING_FACTOR = 10` (see
  `src/vrp_copilot_bench/solvers/pyvrp_vrptw_wrapper.py` module
  docstring). Operators speak in Solomon-native units, so the payload
  always divides by 10 and rounds. A `units` block names the unit so
  the generator can use it in the answer without guessing.
- **All numerical fields are pre-rounded.** The generator must not do
  arithmetic in tokens (it gets it wrong). Anything derived
  (`objective_delta_*`, `lateness_minutes`, `is_late`) is precomputed
  in the projection step and rounded to the precision the op-validity
  check tolerates.
- **The payload is the same shape across all five actions
  (`reuse_direct`, `local_repair_insert`, `construct_feasible`,
  `pyvrp_10s`, `pyvrp_60s_reference`).** Every action emits the same
  in-memory `ActionResult` shape (discovery report §5), so this is a
  projection problem, not a per-action problem. ORDER_CHANGE cells with
  unserved customers will have `customer_schedule` entries for the
  served subset only — that is a true property of the action's output,
  not a schema variance.

## OBJ payload

**Operator claim:** "what is / how much did the total cost change to".

**Op-validity check:** stated objective within 0.5% of `action_objective`.

### Fields included

| field                       | rationale                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `units.objective`           | Names the unit so the generator does not invent "kilometres" or "minutes".                                                                                      |
| `action_objective`          | `EvaluatedVRPTW.objective / 10`. The number the op-validity check compares to. Required.                                                                        |
| `baseline_objective`        | Pre-perturbation `baseline_obj` from the Stage A row (already a float in scaled units; divide by 10). Operators routinely ask for the change, not just the new value. |
| `objective_delta_absolute`  | Pre-subtracted. Saves the generator from doing arithmetic and gives a single defensible number when the question is "by how much did distance increase".         |
| `objective_delta_percent`   | Same as above, as a percent. Cheap to include; expensive (= hallucinated) when the LLM has to compute it.                                                       |

### Fields deliberately excluded

| excluded                                                                              | reason                                                                                                                                                                |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `routes`, `assignment`, `n_routes`                                                    | STRUCT territory. An OBJ answer that lists routes invents structural claims that op-validity doesn't grade and the generator gets wrong.                              |
| `feasible`, `feasibility_breakdown`, `infeasibility_kind`                             | PV territory. Generators given `feasible=False` alongside an OBJ question tend to volunteer "but the plan is infeasible" — a faithfulness drift even when it's true.  |
| `per_customer_schedule`, `late_customer_ids`, `route_end_times`                       | SCHEDULE territory.                                                                                                                                                   |
| `total_duration`, `total_wait`, `total_distance`, `generalized_cost`                  | Diagnostic fields from `EvaluatedVRPTW`; redundant with `objective` (which equals `total_distance` per the wrapper, since `unit_duration_cost=0`). Including both invites confusion. |
| `route_costs` (per-route distance breakdown)                                          | Operator OBJ questions are about the total. Per-route distance enables structural sub-claims that OBJ op-validity does not grade.                                       |

### Tolerance notes

- `action_objective` and `baseline_objective` rounded to **2 decimals**
  in Solomon distance. The op-validity tolerance is 0.5%; on a Solomon
  C-class instance with baseline ~828, 0.5% ≈ 4, so 2 decimals is well
  inside tolerance.
- Deltas rounded to 2 decimals.
- The op-validity check should normalise the generator's stated number
  before comparing (`abs(stated - action_objective) / action_objective
  ≤ 0.005`).

## PV (PLAN_VALIDITY) payload

**Operator claim:** "is the plan feasible / what's wrong with it / which
customers can't be served".

**Op-validity check:** stated feasibility (yes/no) matches
`action_feasible`. Spec §"Operational validity" requires the binary
match; we additionally surface the breakdown so the generator can
answer "why" questions truthfully.

### Fields included

| field                              | rationale                                                                                                                                            |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `feasible`                         | `EvaluatedVRPTW.feasible`. The bit op-validity grades.                                                                                               |
| `feasibility_breakdown.capacity_ok` | `EvaluatedVRPTW.feasible_capacity_only`. Lets the generator say "capacity is fine" or "capacity overloaded" specifically.                            |
| `feasibility_breakdown.time_windows_ok` | `EvaluatedVRPTW.feasible_tw_only`. Same for time windows.                                                                                        |
| `feasibility_breakdown.coverage_ok` | `EvaluatedVRPTW.is_complete`. Distinguishes capacity/TW failure from coverage failure (the ORDER_CHANGE `reuse_direct` case).                       |
| `infeasibility_kind`               | Output of `vrp_copilot_bench.vrptw.evaluation.infeasibility_kind` — categorical `{none, capacity, time_window, both, coverage}`. Same information as the breakdown but in the form Stage A's parquet uses; the generator can echo either phrasing. |
| `n_unserved_customers`             | Headline count for coverage-failure questions. Length of `unserved_customers`.                                                                       |
| `unserved_customer_ids`            | `EvaluatedVRPTW.unserved_customers`. Lets the generator list customer IDs without inventing them. Empty when `coverage_ok=true`.                     |

### Fields deliberately excluded

| excluded                                            | reason                                                                                                                                          |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `objective`, `baseline_objective`, deltas           | OBJ territory.                                                                                                                                  |
| `routes`, `n_routes`, `assignment`                  | STRUCT territory. Generators given route structure on a PV question tend to attribute infeasibility to specific routes — a structural claim PV doesn't verify. |
| `per_customer_schedule`, `route_end_times`          | SCHEDULE territory. A PV generator with schedule data tends to claim specific customers are late even when the actual failure is capacity.       |
| `total_time_warp`, `max_lateness`, `n_late_customers` | Same — SCHEDULE-shaped diagnostics that nudge the generator into timing claims on a feasibility question.                                       |
| Route-level `has_excess_load` / `has_time_warp`     | Per-route attribution is one layer below what PV's op-validity verifies. If we later add a "which route violated" claim type, surface it then.   |

### Tolerance notes

- All four flags are booleans; op-validity is exact.
- `infeasibility_kind` is a closed enum; the generator should match
  string identity (case-insensitive). The judge prompt should accept
  paraphrases like "time-window violation" ↔ `"time_window"` only when
  the categorical mapping is unambiguous.

## STRUCT payload

**Operator claim:** "how many routes are there / which route serves
customer X / are customers A and B on the same route".

**Op-validity check:** route-count or assignment claim matches exactly.

### Fields included

| field        | rationale                                                                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `n_routes`   | `len(EvaluatedVRPTW.routes)`. The number the op-validity check compares exactly.                                                                       |
| `routes`     | `EvaluatedVRPTW.routes` projected to `[{route_idx, customer_ids}, …]`. Supplies both "how many" (length) and "which" (membership lookup). Customer IDs are in visit order, which lets the generator answer light sequence questions ("does route 3 visit customer 5 before customer 12") without us needing a separate sequence field. |

### Fields deliberately excluded

| excluded                                                  | reason                                                                                                                                  |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `assignment` (`{customer_id: route_idx}`)                 | Redundant with `routes` — derivable in two lines. Including both lets the generator cross-reference inconsistently when they disagree (which they shouldn't, but a buggy projection could). One source of truth. |
| `objective`, deltas                                       | OBJ territory.                                                                                                                          |
| Feasibility flags, `infeasibility_kind`, unserved list    | PV territory. A STRUCT generator that sees `feasible=false` often refuses to answer a perfectly valid structural question.              |
| `route_summaries` (distances, durations, slack, etc.)     | The op-validity check is on route count or membership, not on per-route metrics. Per-route stats invite numerical sub-claims STRUCT does not grade. |
| Schedules                                                 | SCHEDULE territory.                                                                                                                     |
| Route distance / cost per route                           | Same as `route_summaries` rationale; if a future claim type asks about per-route distance, surface it then.                             |

### Tolerance notes

- `n_routes` is an integer; op-validity is exact equality.
- Customer IDs are integers; op-validity should match on the **set**
  membership for "which route serves X" claims, and on the **sequence**
  for "what is the order of stops on route Y" claims. Both are exact —
  there is no tolerance.
- `route_idx` is consistent within this action's output — the
  `route_idx` field on each `customer_schedule` entry points to a route
  in the `routes` list whose `customer_ids` contains that customer.

## SCHEDULE payload

**Operator claim:** "when does customer X get serviced / is anyone late /
what time does route Y finish".

**Op-validity check:** stated timing within 1 minute of the action's
schedule.

### Fields included

| field                              | rationale                                                                                                                                                |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `units.time`                       | Names the unit (Solomon minutes).                                                                                                                        |
| `n_late_customers`                 | `EvaluatedVRPTW.n_late_customers`. Headline for "how many late".                                                                                         |
| `late_customer_ids`                | Derived list of customer IDs with `VisitSchedule.time_warp > 0`. The raw output does NOT carry this — see "spec deviation" below.                        |
| `route_end_times`                  | Projection of `RouteSummary.end_time` and `has_time_warp` per route. Supports "what time does route X return to depot".                                  |
| `customer_schedule[].customer_id`  | Identifies the customer the row describes.                                                                                                               |
| `customer_schedule[].route_idx`    | So the generator can say "customer 17, on route 5". Aligns with `route_end_times`.                                                                       |
| `customer_schedule[].arrival`      | `VisitSchedule.arrival`. Distinct from `start_service` when wait > 0; operators sometimes ask about either.                                              |
| `customer_schedule[].start_service` | The number the op-validity check compares against (within 1 minute).                                                                                    |
| `customer_schedule[].end_service`  | Useful for "when does the truck leave customer X".                                                                                                       |
| `customer_schedule[].tw_early`     | Window opening. Required so the generator can say "the truck waits at the door until the window opens" truthfully (not all waits are problems).          |
| `customer_schedule[].tw_late`      | Window closing. Required for "is customer X late" reasoning.                                                                                              |
| `customer_schedule[].is_late`      | Precomputed `time_warp > 0`. Boolean shortcut so the generator does not have to compare `start_service` vs `tw_late` itself (it gets that wrong).        |
| `customer_schedule[].lateness_minutes` | `time_warp / 10`, rounded to 1 decimal. Zero when on time. Op-validity should match on this for "how late is customer X" claims.                     |

### Fields deliberately excluded

| excluded                                                | reason                                                                                                                                       |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `objective`, deltas                                     | OBJ territory.                                                                                                                               |
| `feasible`, `feasibility_breakdown`, `infeasibility_kind` | PV territory. A SCHEDULE generator that sees `feasible=false` often blames "infeasibility" for individual customer lateness — wrong attribution. |
| `routes` (as a sequence of customer IDs)                | STRUCT territory. `route_idx` in each `customer_schedule` entry is enough for SCHEDULE questions; the full visit sequence is not.            |
| `wait_duration` per visit                               | Borderline. Useful for "why is the truck waiting at customer 30" questions, but operators in the closing experiment are not expected to ask wait-attribution questions; including it doubles the per-customer payload size for marginal benefit. Re-evaluate if pilot prompts demand it. |
| `service_duration` per visit                            | Same — derivable from `end_service - start_service`; not worth two fields.                                                                   |
| `slack_to_tw_late` per visit                            | Predictor input, not an answer field. Operators don't ask about slack.                                                                       |
| Route-level `start_time`, `distance`, `duration`, `wait_duration`, `service_duration`, `travel_duration`, `slack`, `min_slack_to_tw_late`, `mean_slack_to_tw_late`, `n_customers`, `n_late_customers` per route | Same rationale: per-route diagnostic stats invite per-route sub-claims that the SCHEDULE op-validity check (per-customer timing within 1 min, or route end time) does not grade. Route-end is the only route-level number kept. |
| `total_time_warp`, `max_lateness`                       | Headline counts already covered by `n_late_customers`; lateness magnitude is on each `customer_schedule` row.                                |

### Tolerance notes

- All times rounded to **1 decimal** in Solomon minutes. The op-validity
  tolerance is 1 minute; 0.1 is an order of magnitude tighter.
- `is_late` is exact (boolean).
- `lateness_minutes` op-validity should match within 1 minute, same as
  the timing tolerance — the generator should round to the nearest
  minute when answering.
- Note for the judge: ORDER_CHANGE customers that the action could not
  serve are **not** in `customer_schedule`. A question about such a
  customer's arrival time is unanswerable; the generator should refuse
  per the answer template ("If the data does not answer the question,
  say so explicitly"). Refusal on an unanswerable question (the payload
  genuinely does not support the claim) scores faithfulness = 5:
  refusal is the faithful response. Refusal on an answerable question
  (the payload was sufficient and the model evaded) scores
  faithfulness = 1. Op-validity on refusals is N/A because no headline
  claim was made. This rule applies across all four families; the
  rubric in Prompt 4 encodes it once.

## Spec deviations to flag

Three places where the closing-experiment spec assumes payload shapes
that the action layer does not directly emit. Each is bridged in the
projection step rather than pretending the raw output is already
shaped correctly.

### 1. `late_customers_list` is derived, not raw

The spec's answer-generator template lists `{late_customers_list}` as a
`SOLUTION DATA` field. The raw action output does not emit such a list.
What exists per the discovery report:

- `EvaluatedVRPTW.n_late_customers` (count, aggregated)
- `RouteSummary.n_late_customers` (count, per route)
- `VisitSchedule.time_warp` (per-customer lateness in scaled units)
- `RouteSummary.has_time_warp` (per-route boolean)

There is no per-customer `late_flag` and no precomputed `late_customers`
list. The projection step therefore computes

```python
late_customer_ids = sorted(
    cid for cid, v in evaluation.per_customer_schedule.items()
    if v.time_warp > 0
)
is_late = (visit.time_warp > 0)        # per customer_schedule row
lateness_minutes = visit.time_warp / 10
```

**Proposal:** treat `late_customer_ids` and per-row `is_late` /
`lateness_minutes` as first-class fields of the SCHEDULE payload (as
above), not as something derived ad-hoc by the answer prompt. If the
projection is a documented transformation we can verify, the payload is
still grounded; if the LLM is asked to derive it from `time_warp` it
will get the sign or threshold wrong.

### 2. `route_summary` and `schedule_summary` in the spec template are placeholders, not fields

The spec template reads:

```
SOLUTION DATA:
- Routes: {route_summary}
- Schedule: {schedule_summary}
- Objective: {objective_value}
- Feasibility: {feasibility_flags}
- Late customers: {late_customers_list}
```

These are illustrative names, not field labels in the action output.
The schemas in `payload_schemas.json` operationalise them per family
rather than producing a single super-payload with all five placeholders
filled in. A single super-payload would defeat the point of the
2×2 stratification across claim families: the whole reason for
separating OBJ from STRUCT from SCHEDULE from PV is that a generator
given everything will paraphrase everything, and the three-axis scorer
cannot then attribute failure to a specific axis.

**Proposal:** the answer-prompt template per family substitutes the
*family-specific* `SOLUTION DATA` block. The CONTEXT block remains
identical across families. The judge prompt sees the same per-family
payload the generator saw, not a richer one — otherwise the judge can
catch hallucinations the generator could never have avoided.

### 3. Spec's action list (§"Action output schemas" of `spec.md`) does not match the implemented VRPTW actions

This is also flagged in the discovery report §6.5. Spec says
`reuse_direct, nearest_neighbor, clarke_wright, pyvrp_10s, pyvrp_60s`;
the VRPTW pipeline emits `reuse_direct, local_repair_insert,
construct_feasible, pyvrp_10s, pyvrp_60s_reference`. The schemas above
work for the implemented set because every action emits the same
`ActionResult` shape and the projection is identical. **Proposal:** the
closing experiment uses the implemented action names (with
`local_repair_insert` and `construct_feasible` substituted for
`nearest_neighbor` and `clarke_wright`), and the prereg amendment
notes this mapping so the spec doesn't drift further from the code.

## Open question for the next prompt

`customer_schedule` includes all served customers (typically 100 for
Solomon-100, up to 200 for Homberger-200). That is a meaningful prompt
size, but pruning would risk the generator inventing data when asked
about a specific customer that was pruned. The conservative choice is
to keep the full list and accept the prompt-size cost; if the pilot
scoring shows the generator is bloating answers by reciting unused
schedule entries, revisit (e.g. include only affected customers and
explicitly tell the generator that other customers' schedules are
withheld).

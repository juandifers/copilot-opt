# Synthetic prompt templates — to be locked at preregistration-prompts-v1

Three templates per claim family. Each template is instantiated against
2 cells from `experiment/data/cell_selection.csv` (rows where
`source_planned = synthetic`), for 3 × 2 = 6 synthetic prompts per
family, 24 across the 48-prompt set.

The templates exercise **different phrasing patterns within each
family**, not paraphrases of one pattern. The intent is that the
synthetic spine covers the question shapes a real operator would use
across the family, so the LLM-generated prompts (the other 6 per
family) test variation in surface form rather than variation in
underlying question shape.

Per-cell instantiation rule: the `{perturbation}` placeholder is
substituted at construction time using the cell's `perturbation_family`
and the canonical magnitude from
`vrp_copilot_bench.vrptw_perturbations.types.PERTURBATION_MAGNITUDES`.
Substitution phrasings:

| family | magnitude convention | substitution phrase |
| --- | --- | --- |
| `TRAVEL_TIME` | multiplier (TT_1=1.1, …, TT_5=1.5) | "after travel times went up {int((m-1)*100)}%" |
| `SERVICE_TIME` | multiplier (ST_1=1.1, …, ST_4=2.0) | "after service times went up {int((m-1)*100)}%" |
| `TIME_WINDOW` | tightening fraction (TW_1=0.1, …, TW_6=0.2) | "after the time windows got tighter" |
| `ORDER_CHANGE` | new-customer-insertion fraction (OC_1=0.05, …, OC_5=0.25) | for OC_1/OC_2 ("after a new order came in"); for OC_3/OC_4/OC_5 ("after the new orders came in") |

If a template can't be instantiated faithfully against a specific cell
(see "Template substitution audit" below for the trigger conditions),
the substitution rule above is overridden cell-by-cell and the
override is logged at `experiment/data/llm_prompt_rejections.md`
alongside the LLM rejections. Same audit channel; the prereg expects
these to be rare.

## op_validity_gradable per template

Each prompt in `experiment/data/prompts.csv` carries a boolean column
`op_validity_gradable`. True = the prompt elicits the family's headline
claim and op-validity applies per `rubric.md` (b). False = the prompt
elicits a non-headline answer (e.g., a delta, a direction, a
sub-feasibility status); op-validity is N/A and the judge sets
`op_validity_pass = null` and `op_validity_check_results = null` per
`rubric.md` (c). Faithfulness scores the actual claim normally either
way.

Per-template values for the synthetic prompts:

| family | T1 | T2 | T3 |
| --- | --- | --- | --- |
| OBJ | True (absolute objective) | False (delta magnitude) | False (direction only) |
| PV | True (overall feasibility) | False (capacity sub-feasibility) | False (coverage sub-feasibility) |
| STRUCT | True (route count) | True (single-customer assignment) | True (same-route boolean — covered by the extended rule in rubric.md (b)) |
| SCHEDULE | True (any-late boolean — covered by the extended rule in rubric.md (b)) | True (route end time) | True (specific customer arrival) |

For LLM-generated prompts, `op_validity_gradable` is set at filter time
per the rule in `payload_schemas_rationale.md`'s "Op-validity vs
faithfulness scoping" section: headline OBJ cost question → True;
delta or direction question → False. Headline PV feasibility question
→ True; sub-feasibility question → False. STRUCT and SCHEDULE prompts
default True unless the prompt asks something outside the rubric's
extended rules.

## OBJ — total objective value claims

**OBJ-1 (absolute objective value).** 

> What's the total cost on this plan after {perturbation}?

*Pattern*: absolute objective value question. The headline claim the
generator must produce is `claimed_objective`. Op-validity gates the
stated number to within 0.5%.

**OBJ-2 (delta magnitude).**

> How much did the total distance change after {perturbation}?

*Pattern*: magnitude-of-change question. The generator should cite
`objective_delta_absolute` (or compute and report it from
`action_objective − baseline_objective`). Op-validity still gates on
`claimed_objective` if the answer states the absolute number alongside
the delta; if the answer states only the delta, op-validity considers
whether the implied stated objective matches within 0.5%.

**OBJ-3 (direction).**

> Is the cost up or down compared to before {perturbation}?

*Pattern*: directional comparison. Answer is "up" or "down" plus
optionally the magnitude. If the answer states a number for the new
objective, op-validity grades that; otherwise the answer is
direction-only and is graded on faithfulness alone.

## PLAN_VALIDITY — feasibility and coverage claims

**PV-1 (binary feasibility).**

> Does this plan still work after {perturbation}?

*Pattern*: yes/no feasibility question. Headline claim is
`claimed_feasible` (boolean). Op-validity gates exact match against
`payload.feasible`.

**PV-2 (capacity-specific).**

> Are we hitting any capacity issues after {perturbation}?

*Pattern*: feasibility-by-cause question. The generator should answer
in terms of `feasibility_breakdown.capacity_ok` (or the broader
`infeasibility_kind` if both capacity and TW fail). Op-validity grades
the binary feasibility claim made; faithfulness covers whether the
generator correctly attributes the cause to capacity vs. time windows
vs. coverage.

**PV-3 (coverage).**

> Did we end up dropping any customers after {perturbation}?

*Pattern*: coverage question. Answer cites `n_unserved_customers` and
`unserved_customer_ids`. Faithfulness covers the customer-ID list if
the answer enumerates IDs; op-validity grades the binary "any dropped"
claim against `n_unserved_customers > 0`.

## STRUCT — route structure claims

**STRUCT-1 (route count).**

> How many routes does this end up needing after {perturbation}?

*Pattern*: total route count. Headline claim is `claimed_route_count`.
Op-validity gates exact match against `payload.n_routes`.

**STRUCT-2 (single-customer assignment).**

> Which route is customer 42 on after {perturbation}?

*Pattern*: per-customer route membership. Headline claim is
`claimed_route_membership = [{route_idx: r, customer_ids: [42]}]`.
Op-validity checks that the stated route_idx for customer 42 matches
the payload's `routes[r].customer_ids` containing 42.

Customer 42 is present in every Solomon-100 (numbering 1–100) and
every Homberger-200 instance (numbering 1–200). On ORDER_CHANGE cells
where customer 42 is one of the inserted-and-served customers, the
question is answerable; if cheap-action coverage fails and customer 42
is among `unserved_customer_ids`, the generator should refuse. The
template choice of customer 42 (not a higher ID) keeps the question
answerable across the broadest set of cells.

**STRUCT-3 (same-route check).**

> Are customers 12 and 17 still on the same route after {perturbation}?

*Pattern*: pairwise membership. Headline claim is
`claimed_route_membership` listing the route_idx for each of 12 and 17
(or a yes/no in `answer_text`). Op-validity checks the set membership.

12 and 17 are present in every Solomon-100 / Homberger-200 instance.
The customer-pair check is structurally distinct from the
single-customer check in STRUCT-2: it adds a relational question that
single-membership doesn't.

## SCHEDULE — timing claims

**SCHEDULE-1 (lateness existence).**

> Is anyone going to be late after {perturbation}?

*Pattern*: existence question for lateness. Answer cites
`n_late_customers > 0` (yes) or `n_late_customers == 0` (no). Headline
claim is implicitly `claimed_late_customers` (empty list for "no",
non-empty for "yes"). Op-validity grades against `late_customer_ids`.

**SCHEDULE-2 (route end time).**

> What time does route 1 wrap up after {perturbation}?

*Pattern*: specific route-end timing. Headline claim is a number in
`claimed_customer_timings`-equivalent shape but for route end —
practically, the generator states a clock time in Solomon minutes.
Op-validity grades against `route_end_times[route_idx=1].end_time`
within the 1-minute tolerance.

Route_idx=1 exists in every action output: every cell in
`cell_selection.csv` has at least 8 routes in the cheap-action /
pyvrp_10s output (smallest observed: 8 routes on R202 cells).

**SCHEDULE-3 (specific customer arrival).**

> When does the driver reach customer 42 after {perturbation}?

*Pattern*: per-customer arrival time. Headline claim is
`claimed_customer_timings[0].stated_arrival_or_start` for customer 42.
Op-validity gates the stated arrival against
`customer_schedule[customer_id=42].start_service` within 1 minute.

Same answerability argument as STRUCT-2: customer 42 is always in the
instance; refusal is appropriate if the action's coverage dropped 42
or if the cell has no served `customer_schedule` entry for 42.

## Template substitution audit

If during Step 3 instantiation a template can't be applied faithfully
to a specific cell, the substitution is logged at
`experiment/data/llm_prompt_rejections.md` with:

- Template ID (e.g., `OBJ-1`)
- Cell ID
- Failure mode (one of: "perturbation phrasing ungrammatical",
  "template references entity not in payload", "claim is
  payload-unanswerable")
- Substitution chosen (which other template from the same family
  filled the slot)

The prereg expects ≤ 2 substitutions across the 24 synthetic prompts.
More than that would indicate the templates don't span the family well
enough; the rationale doc would need revision before lock.

## Source-of-truth for the rendered prompts

The instantiated prompts (after substitution) land in
`experiment/data/prompts.csv` under `prompt_text`. The templates here
are the inputs; the CSV is the output. Both are committed at
`preregistration-prompts-v1`.

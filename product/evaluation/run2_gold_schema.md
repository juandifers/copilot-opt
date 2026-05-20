# Run 2 — Gold-Label Case Schema

_Companion to `run2_contract_benchmark_design.md`. Defines the row
schema used by `run2_calibration_cases.csv` and (in Stage R2-1) the
60-case benchmark CSV. The schema is strict so that two labellers can
independently arrive at the same expected contract output for a
given (prompt, payload condition) pair._

## 1. Row schema

Each case is one CSV row. Field types and value constraints below.

| Field | Type | Required | Notes |
|---|---|---|---|
| `case_id` | str | yes | Stable identifier of the form `R2-NNN` where `NNN` is a zero-padded 3-digit counter. Unique within the file. |
| `source_prompt_id` | str \| empty | no | Run 1 prompt ID this case seeds from (e.g. `025`). Empty for purely synthetic cases. |
| `family` | enum | yes | One of `OBJ`, `PLAN_VALIDITY`, `STRUCT`, `SCHEDULE`. |
| `prompt_text` | str | yes | The operator-style natural-language question. Quoted in CSV if it contains commas. |
| `payload_condition` | enum | yes | See §2. |
| `payload_mutation_needed` | str | yes | Free-text description of how to derive this case's payload from the seed (Run 1 prompt's payload, or `synthetic`). Used by the future evaluator to construct the payload deterministically. Use `none` for a clean seed reuse. |
| `expected_intent` | enum | yes | One of the 13 current `Intent` values from `product/copilot/contracts.py`, **or** one of the proposed Stage R2-1 intent extensions in §3. |
| `expected_answerability` | enum | yes | One of `answerable`, `partially_answerable`, `not_answerable`. See §4. |
| `expected_evidence_paths` | list[str] (`;`-separated) | yes | The set of payload field paths the contract response should cite under this case. Use `[]`-style predicates only when the field is list-of-dicts and a specific item is the one cited (`routes[route_idx=K].customer_ids`); otherwise use generic `key[].subkey`. Empty when no evidence is expected (refusals, false premise). |
| `expected_missing_fields` | list[str] (`;`-separated) | yes | The set of payload field paths the contract response should list as missing (or *should report as missing under target behavior*; see `implementation_status`). Empty for `answerable` cases whose subclaims are fully grounded. |
| `expected_warnings` | list[str] (`;`-separated) | yes | The set of warning codes from §5. Empty when no warning is expected. |
| `expected_next_actions` | list[str] (`;`-separated) | yes | Semantic codes from §6. Empty for fully answerable cases with no warnings. |
| `expected_behavior_class` | enum | yes | One of `direct_answer`, `direct_answer_with_warning`, `partial_answer_with_warning`, `useful_refusal`. See §7. **Renamed from `expected_validator_result` in the R2-0 revision** to remove the misleading `pass/warn/fail` framing; in particular, `useful_refusal` is a *correct* contract outcome, not a system failure. |
| `implementation_status` | enum | yes | One of `current`, `target_extension`. See §8. Marks whether the gold encodes behavior the current contract already exhibits (`current`) or planned/target behavior that diverges from the current implementation (`target_extension`). |
| `difficulty` | enum | yes | One of `easy`, `medium`, `hard`. See §9. |
| `label_rationale` | str | yes | One- or two-sentence justification for the expected labels. Concrete enough that a second labeller could re-derive the same labels. For `target_extension` cases, include the specific policy gap the case surfaces. |
| `ambiguity_notes` | str | no | Free-text notes on edge-case interpretations or known labeller disagreements. Empty if the case is unambiguous. |

CSV encoding rules:
- Multi-value fields use `;` as the separator (not `,`, to keep CSV
  parsing simple).
- Empty multi-value fields are encoded as the empty string, not
  `none` or `null`.
- Text fields containing `,`, `"`, or newlines are wrapped in double
  quotes per RFC 4180. Embedded `"` are doubled (`""`).

## 2. Allowed values for `payload_condition`

The `payload_condition` field captures *how the payload differs from
a clean Run 1 baseline payload* for this prompt. The evaluator (in a
later stage) will use this code, plus `payload_mutation_needed`, to
construct the test payload deterministically.

| Value | Meaning |
|---|---|
| `clean` | Use the seed Run 1 prompt's payload as-is; no mutation. Used for cases that test the happy path. |
| `missing_baseline_solution` | Remove `baseline_solution` and `diff` from the payload, simulating a STRUCT/SCHEDULE/PLAN_VALIDITY before/after question against a payload that does not carry a structural baseline. |
| `missing_new_customer_ids` | Remove `new_customer_ids` from a payload whose perturbation family is `ORDER_CHANGE`. Forces `new_customer_assignment` into `partially_answerable`. |
| `missing_units` | Remove `units.objective` from an OBJ payload to test whether the contract still lists `action_objective` correctly and warns or downgrades evidence. |
| `missing_validity_fields` | Remove `feasible` and `feasibility_breakdown` from a PLAN_VALIDITY payload. Forces `feasibility_status` into `not_answerable`. |
| `missing_reference_solution` | The payload does not include a `reference_solution.objective` field (the cost of a full re-solve of the perturbed instance). Distinct from `missing_baseline_solution`: `baseline_objective` is the pre-perturbation Stage A cost, *not* a re-solve of the perturbed instance. Cases marked with this condition test whether the contract handles a natural-language "compared to a full re-solve" comparator whose payload referent is absent. |
| `false_premise_customer` | The prompt names a customer ID that is not present in any route / schedule entry of the payload. |
| `false_premise_route` | The prompt names a route by integer that does not exist in the augmented payload (e.g. asks about route 9 in a 5-route plan). |
| `unsupported_comparison` | Prompt explicitly asks a before/after comparison and the payload is non-OBJ (so the OBJ escape hatch does not apply) **and** `baseline_solution`/`diff` are absent. This is the canonical Run 1 027/033/035/036 shape. |
| `convention_boundary` | Prompt explicitly names a route by integer (e.g. "route 1") and the case exists to test that the response uses `Route N` display convention rather than `route_idx`. |
| `single_customer_membership` | Prompt names one customer and asks for that customer's route assignment. Exists to test the subset-vs-full-route ambiguity that triggers `struct_membership_ambiguity`. |
| `full_route_membership` | Prompt asks for the full roster of a route or of all routes. Exists as the contrast case for `single_customer_membership`. |
| `same_route_boolean` | Prompt names two customers and asks whether they are on the same route. Distinct from single-customer membership; the contract intent is `same_route_boolean`. |
| `synthetic_other` | Reserved for synthetic cases whose mutation does not fit any of the above. `payload_mutation_needed` must spell it out. |

This list may grow in Stage R2-1; new values must be added to this
section before being used in a case.

## 3. Allowed values for `expected_intent`

### 3.1 Current contract intents

These are the 13 `Intent` values from
`product/copilot/contracts.py` (Literal type), reproduced here so the
schema is self-contained:

```
objective_value
objective_delta
feasibility_status
route_count
single_customer_route_membership
same_route_boolean
route_end_time
customer_arrival
lateness_summary
before_after_comparison
new_customer_assignment
refusal_or_insufficient_payload
unknown
```

`unknown` is permitted as an expected label only when the question
genuinely does not map to any other intent (e.g. an underspecified
"can you tell me about this?"). It is **not** to be used as a
fallback for "the labeller couldn't decide" — and it should **not**
be used as the expected intent for a question that is operationally
meaningful but happens to fall outside the current intent
enumeration. For those questions, use a proposed extension (§3.2)
and mark `implementation_status = target_extension`.

### 3.2 Proposed Stage R2-1 intent extensions

Used as `expected_intent` only on rows whose `implementation_status`
is `target_extension`. Each extension is justified in the case's
`label_rationale`.

| Proposed value | Operational meaning | Current contract behaviour |
|---|---|---|
| `full_route_listing` | "List the customers on each route" — the operator wants the full roster per route, not a per-customer membership lookup. The required field is `routes[].customer_ids`. | Currently routes to `unknown` because the STRUCT branch in `product/copilot/intent.py` has no matcher for the "per each route" / "list all" phrasing. |

Stage R2-1 may add more proposed intents (e.g. `unserved_customer_listing`,
`route_load_summary`); each must be added here before being used.

## 4. Allowed values for `expected_answerability`

The three values from `AnswerabilityStatus` in
`product/copilot/contracts.py`:

| Value | When to use |
|---|---|
| `answerable` | All required fields for the intent are present in the payload. No structural ambiguity blocks a direct answer. (A case may still raise a warning and still be `answerable`.) |
| `partially_answerable` | At least one but not all required fields are present, **or** the OBJ escape hatch applies and the subclaim list is non-empty, **or** the question can be answered for a subset of the entities it asks about. |
| `not_answerable` | None of the required fields are present, **or** the question presupposes a false premise the payload contradicts, **or** the intent itself maps to `refusal_or_insufficient_payload` / `unknown` under the current contract. |

The mapping from `expected_answerability` to `expected_behavior_class`
is not 1:1 — a case can be `answerable` and still expected to emit a
warning (e.g. `single_customer_route_membership` always warns), which
maps to `direct_answer_with_warning` rather than `direct_answer`.

## 5. Allowed values for `expected_warnings`

### 5.1 Current contract warnings

Codes already emitted by `product/copilot/refusal_policy.py`:

| Code | When to expect it |
|---|---|
| `route_indexing_ambiguity` | The prompt or the answer references a route by integer, **or** the prompt is one of the explicitly flagged Run 1 cases (`040`, `041`). |
| `struct_membership_ambiguity` | `expected_intent == single_customer_route_membership` (the schema cannot distinguish subset membership from full-route equality). |
| `unsupported_comparison` | `expected_intent == before_after_comparison` and `expected_answerability != answerable`. |
| `missing_new_customer_attribution` | `expected_intent == new_customer_assignment` and `new_customer_ids` is in `expected_missing_fields`. |

### 5.2 Proposed Stage R2-1 warning extensions

Used as `expected_warnings` only on rows whose `implementation_status`
is `target_extension`. Each is justified in the case's `label_rationale`.

| Proposed code | Operational meaning | Current contract behaviour |
|---|---|---|
| `false_premise_detected` | The prompt names a customer ID, route number, or other entity that the payload does not contain. Target behaviour: refuse with a "this entity is not in the current plan" message rather than silently answering against the nearest entity. | Currently not emitted; the contract may classify the question as answerable because the *type* of required field exists for other entities, masking the false premise. |
| `comparison_referent_ambiguity` | The prompt frames an OBJ delta as a comparison against an external comparator (e.g. "a full re-solve", "the optimum") whose payload referent is not `baseline_objective`. `baseline_objective` is the pre-perturbation Stage A cost; the natural-language comparator may instead refer to a re-solve of the perturbed instance (which would live at a hypothetical `reference_solution.objective` field that the payload does not carry). | Currently not emitted as a warning; surfaced only by the diagnostic `volunteered_or_risky_comparison_guardrail_hits` probe in `product/data/metrics.py`. |
| `evidence_units_missing` | The OBJ payload supplies `action_objective` but not `units.objective`. The numeric answer can be cited, but the operator cannot tell whether the figure is in `solomon_distance` units, minutes, or another unit. Target behaviour: partial answer with a warning and a missing-field entry for `units.objective`. | Currently not emitted; the contract returns `action_objective` evidence without flagging that the unit annotation is absent. |

New warning codes beyond this section are not permitted in Stage R2-0
case labels. Adding more is a Stage R2-1 schema change.

## 6. Allowed values for `expected_next_actions`

These are *semantic codes*, not the literal strings from
`refusal_policy._NEXT_ACTION_BY_FIELD`. Run 2 grades useful refusal
on whether the contract response includes at least one suggested
action whose semantic intent matches one of these codes. A future
evaluator stage will map each semantic code to one or more concrete
suggestion-string patterns from `refusal_policy.compose_suggestions`.

### 6.1 Current semantic codes

| Semantic code | Concrete suggestion in current contract |
|---|---|
| `build_baseline_comparison_payload` | `"Build before/after comparison payload."` |
| `expose_new_customer_ids` | `"Expose perturbation.new_customer_ids in the product payload."` |
| `apply_route_label_augmentation` | `"Apply product route-label schema augmentation."` |
| `use_schedule_payload` | `"Use SCHEDULE payload or run schedule projection."` |
| `narrow_question_to_available_field` | `"Narrow the question to a specific customer, route, or claim type, or pick a field from the available payload fields list."` |

### 6.2 Proposed Stage R2-1 semantic codes

| Proposed code | Operational meaning | Current contract behaviour |
|---|---|---|
| `clarify_false_premise` | Prompt the operator to confirm the referenced entity actually exists in the current plan. | Not emitted. |
| `use_validity_payload` | Switch to a PLAN_VALIDITY payload (or run a feasibility projection) that includes `feasible` and `feasibility_breakdown` fields. | `refusal_policy._NEXT_ACTION_BY_FIELD` does not currently map either field, so the contract emits `useful_refusal` with empty `suggested_next_actions` — a violation of the §7 useful-refusal contract that Stage R2-1 closes. |
| `expose_reference_solution_objective` | Re-solve the perturbed instance under a reference budget and expose its objective in the payload, so the contract can ground a "compared to a full re-solve" comparator. | Not emitted; the payload does not carry a reference-solution field today. |
| `expose_units_objective` | Add `units.objective` to the OBJ payload so numeric answers carry their unit annotation. | Not emitted; the contract does not flag `units.objective` absence. |

## 7. Allowed values for `expected_behavior_class`

| Value | Meaning |
|---|---|
| `direct_answer` | The contract response is expected to answer the question directly: `expected_answerability == answerable`, `expected_warnings` is empty, `expected_evidence_paths` is non-empty (or the intent legitimately has no evidence to cite). |
| `direct_answer_with_warning` | The contract response is expected to answer the question and raise one or more legitimate warnings (`route_indexing_ambiguity`, `struct_membership_ambiguity`, …). A `direct_answer_with_warning` case must have a non-empty `expected_warnings` **and an empty `expected_missing_fields`** — the answer is complete, the warning is policy-side context. |
| `partial_answer_with_warning` | The contract response is expected to answer the *supported* subclaim of a multi-part question, raise a warning, and list missing fields for the *unsupported* subclaim along with a concrete next action. Required shape: `expected_answerability == partially_answerable`, `expected_evidence_paths` non-empty (the supported subclaim is grounded), `expected_warnings` non-empty (names what the response cannot ground), `expected_missing_fields` non-empty (what would be needed to ground the unsupported subclaim), `expected_next_actions` non-empty. Distinct from `useful_refusal`: `partial_answer_with_warning` substantively answers part of the question and cites evidence, while `useful_refusal` returns no claim-grounding evidence. |
| `useful_refusal` | The contract response is expected to refuse or partially refuse: `expected_answerability ∈ {partially_answerable, not_answerable}`, with a non-empty `expected_next_actions` (the contract owes the operator a recoverable next step). `expected_evidence_paths` is typically empty (or limited to context fields the refusal narrative cites). A `useful_refusal` is a **correct** contract outcome, not a system failure; it is graded on whether the refusal payload (missing fields, suggestions) matches the gold. |

**Choosing between `partial_answer_with_warning` and `useful_refusal`
when `expected_answerability == partially_answerable`.** Use
`partial_answer_with_warning` when the contract is expected to cite
evidence for the supported part of the question (the operator
receives a usable answer plus a flag). Use `useful_refusal` when the
contract returns no substantive claim-grounding evidence and the
response is primarily refusal-shaped (the operator receives a
refusal narrative plus next steps). The new-customer-assignment
missing-IDs case (`partially_answerable` but with no answer-grounding
evidence in the current contract) is `useful_refusal`; the OBJ
delta with an ambiguous external comparator
(`partially_answerable`, OBJ delta fields are cited as evidence, the
unsupported comparator subclaim is flagged) is
`partial_answer_with_warning`.

**Why renamed from `expected_validator_result`.** The earlier
`pass/warn/fail` enum confused two distinct things: (a) whether the
case's gold contract response is a refusal, and (b) whether the
system-under-test produced the gold. Run 2 grades systems on
component metrics (intent acc, answerability acc, evidence
precision/recall, …), not on a single `pass/warn/fail` verdict.
`expected_behavior_class` is purely a property of the case's gold.

## 8. Allowed values for `implementation_status`

| Value | Meaning |
|---|---|
| `current` | The behavior encoded by this row is what the current contract (`product/copilot/*` + `product/data/*` at the time of writing) is expected to produce. Cases marked `current` are the ones that can be scored against the existing System C without policy extensions. |
| `target_extension` | The behavior encoded by this row is the *target* behavior under a planned Stage R2-1 contract extension. The current contract is expected to diverge — usually by emitting `unknown`, by failing to fire a planned warning, by omitting a planned semantic next action, or by silently passing a question that should refuse. `label_rationale` must specify the divergence; `ambiguity_notes` should document what System C is expected to produce *today* vs the gold. |

`implementation_status` is **not** evaluated by any Run 2 metric. Its
purpose is bookkeeping: it lets the benchmark distinguish "the system
got this wrong because the contract isn't there yet" from "the system
got this wrong because the contract is there and the system regressed."
A Run 2 report should split aggregate scores by
`implementation_status` so the two failure modes do not cancel.

## 9. Allowed values for `difficulty`

| Value | Rough rubric |
|---|---|
| `easy` | A single intent fires unambiguously; the payload either clearly supports the answer or clearly does not; one warning at most; no convention or false-premise traps. |
| `medium` | Multiple plausible intents or a missing-field branch; convention rules apply; or one of: subset-vs-full-route membership, OBJ before/after escape hatch, partial answerability over multi-entity questions. |
| `hard` | False premise, multi-step combinations of the above, or cases where the contract behaviour is currently underspecified and the case exists to drive a policy decision. Most `target_extension` cases will be `hard` or `medium`. |

## 10. Field-path grammar reminder

(Mirrors `product/data/evidence.py:field_path_exists` and the
`available_payload_fields` enumerator.)

- `key` — top-level field.
- `key.subkey` — dotted nested access into a dict-valued field.
- `key[].subkey` — list-of-dicts access; means "any item in `key`
  whose dict contains `subkey`."
- `key[predicate].subkey` — list-of-dicts access where the item is
  pinned by a key-value predicate, e.g. `routes[route_idx=4].customer_ids`.
  The evaluator normalises `[predicate]` → `[]` before comparing to
  gold; predicates exist for display, not for matching.

### 10a. Evidence path specificity policy (R2-0)

The R2-0 evidence precision/recall metrics use **canonical generic
paths** for matching. The policy is:

- **Gold `expected_evidence_paths` use generic list paths only.**
  Write `routes[].customer_ids`,
  `customer_schedule[].arrival`, `route_end_times[].end_time` —
  never `customer_schedule[customer_id=42].arrival` or
  `route_end_times[route_idx=0].end_time`.
- **System outputs may use predicate-pinned paths**
  (`customer_schedule[customer_id=42].arrival`,
  `routes[route_idx=4].customer_ids`). The evaluator strips the
  predicate (`[anything=anything]` → `[]`) before comparing to gold.
- **Predicate pinning is encouraged for UI display.** The product
  layer's `evidence.py` already emits pinned paths because the
  dashboard renders them as "Customer 42 on Route 5." This is good
  product behaviour and Run 2 does not penalize it.
- **Evidence precision/recall in R2-0 is a *field-family* metric,
  not an entity-specificity metric.** A response that cites
  `customer_schedule[customer_id=99].arrival` matches the gold
  `customer_schedule[].arrival`; the metric does not check that the
  cited entity (`customer_id=99`) is the entity the question asked
  about. Entity-specificity is the concern of the
  convention-consistency metric (which checks whether the route or
  customer number named in the answer text resolves to the entity in
  the cited evidence under the display convention), not of evidence
  precision/recall.
- **A future `evidence_specificity` metric** may grade
  predicate-pinning correctness directly (e.g. "the gold expects the
  cited customer to be the one named in the question"). It is
  deferred past R2-0; gold field paths are written so that adding it
  later does not require relabelling.

## 11. CSV parsing rules for the evaluator

The benchmark CSV is canonical and must be read identically by every
evaluator stage. The required reader contract:

```
import pandas as pd
df = pd.read_csv(path, keep_default_na=False, dtype=str)
```

(or any equivalent reader that produces the same shape).

Rules:

- `keep_default_na=False` is mandatory. Empty cells must be read as
  the empty string `""`, **never** as `NaN`. Code that assumes NaN
  will silently break on cases like R2-001 where most multi-value
  columns are intentionally empty.
- `dtype=str` is mandatory. Numeric coercion would mangle field
  paths like `routes[].customer_ids` and corrupt evidence matching.
- Multi-value fields (`expected_evidence_paths`,
  `expected_missing_fields`, `expected_warnings`,
  `expected_next_actions`) are split on `;`. The empty string splits
  to the empty list `[]`, not `[""]`. Whitespace around items is
  stripped (`" foo ; bar"` → `["foo", "bar"]`).
- Unknown columns must be rejected. The evaluator must verify that
  the CSV header matches the 17-column schema in §1 exactly; an
  extra column is a labelling error, not a feature.
- Row count is checked against the design doc's declared Stage R2-0
  size (15 rows in this revision).

## 12. False-premise rows (Stage R2-0 exception)

Cases whose `payload_condition` is `false_premise_customer` or
`false_premise_route` follow a deliberate exception to the
"useful_refusal must list missing fields" intuition:

- `expected_answerability` is `not_answerable`.
- `expected_missing_fields` **may be empty**. The problem is not
  that a required payload field is absent — every required field is
  in fact present for *other* entities — the problem is that the
  prompt references an entity (a customer ID, a route number) that
  the payload does not contain. Fabricating a synthetic missing
  field like `customer_schedule[customer_id=999].arrival` to satisfy
  a non-empty-missing-fields rule is **wrong**, because the
  evaluator must not penalise systems for omitting a payload field
  that was never the issue.
- `expected_warnings` **must include** `false_premise_detected`.
- `expected_next_actions` **must include** `clarify_false_premise`.
- `expected_behavior_class` is `useful_refusal`.

This exception is recorded explicitly so future labellers do not
introduce fake missing fields to false-premise cases.

## 13. Disallowed shapes (Stage R2-0)

- A row with `expected_answerability == answerable` and a non-empty
  `expected_missing_fields` is invalid. Reject during review. (An
  *answerable* case has nothing the contract should refuse to cite.
  Cases that previously appeared to violate this — e.g. an OBJ delta
  with an ambiguous comparator — are now `partially_answerable`
  under `partial_answer_with_warning`.)
- A row with `expected_behavior_class == direct_answer` and a
  non-empty `expected_warnings` is invalid — use
  `direct_answer_with_warning` instead.
- A row with `expected_behavior_class == direct_answer_with_warning`
  and empty `expected_warnings` is invalid — promote to
  `direct_answer` or specify the expected warning.
- A row with `expected_behavior_class == direct_answer_with_warning`
  and non-empty `expected_missing_fields` is invalid — use
  `partial_answer_with_warning` instead.
- A row with `expected_behavior_class == partial_answer_with_warning`
  is invalid unless **all four** of the following hold:
  `expected_answerability == partially_answerable`;
  `expected_warnings` non-empty;
  `expected_missing_fields` non-empty;
  `expected_next_actions` non-empty. Reject during review.
- A row with `expected_behavior_class == partial_answer_with_warning`
  and empty `expected_evidence_paths` is invalid — the supported
  subclaim must be cited as evidence, otherwise the case is
  `useful_refusal`, not partial answer.
- A row with `expected_behavior_class == useful_refusal` and
  `expected_answerability == answerable` is invalid. A useful refusal
  presupposes that the answer is at least partially withheld.
- A row with `expected_behavior_class == useful_refusal` and empty
  `expected_next_actions` is invalid — the convention is that every
  useful refusal carries at least one recoverable next step. (If the
  current contract would produce no next action for this case, mark
  the row `target_extension` and use the planned semantic code; do
  not leave `expected_next_actions` empty.)
- A row whose `expected_warnings` contains `false_premise_detected`
  but whose `payload_condition` is not a `false_premise_*` value is
  invalid. Reject during review.
- A row whose `payload_condition` is a `false_premise_*` value
  must include `false_premise_detected` in `expected_warnings` and
  `clarify_false_premise` in `expected_next_actions` (per §12).
- A row whose `expected_warnings` contains
  `comparison_referent_ambiguity` but whose `expected_intent` is not
  `objective_delta` (or whose family is not OBJ) is invalid in Stage
  R2-0 — the warning is OBJ-delta-specific.
- A row whose `expected_warnings` contains `evidence_units_missing`
  but whose family is not OBJ is invalid in Stage R2-0 — the warning
  is OBJ-specific (only OBJ payloads carry `units.objective`).
- A row whose `expected_evidence_paths` contains a predicate-pinned
  path (`[key=value]`) is invalid per §10a. Use the generic form.
- A row whose `expected_intent` uses a Stage R2-1 proposed extension
  (e.g. `full_route_listing`) but whose `implementation_status` is
  `current` is invalid — proposed intents are by definition
  target-extension.
- A row whose `expected_warnings` uses a Stage R2-1 proposed
  extension (e.g. `false_premise_detected`,
  `comparison_referent_ambiguity`, `evidence_units_missing`) but
  whose `implementation_status` is `current` is invalid — same
  reason.
- A row whose `expected_next_actions` uses a Stage R2-1 proposed
  semantic code (e.g. `clarify_false_premise`, `use_validity_payload`,
  `expose_reference_solution_objective`, `expose_units_objective`)
  but whose `implementation_status` is `current` is invalid — same
  reason.
- A row with no `label_rationale` is invalid. Every row must justify
  its labels.

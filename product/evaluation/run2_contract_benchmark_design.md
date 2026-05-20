# Run 2 — Product Contract Benchmark (Design Document)

_Status: design draft, Stage R2-0. No models or solvers are run from this
document. The locked experiment files at `experiment/configs/` and
`experiment/data/` are not modified by Run 2._

## 1. Motivation from Run 1

Run 1 (the locked 48-prompt replay, summarised in
`product/reports/thesis_metrics_baseline_run1.md`) measured whether the
language layer of the copilot was **faithful** to a single, fixed,
deterministic VRPTW payload. It did this very well: 47/48 prompts cleared
the faithfulness rubric. What Run 1 did **not** measure, by construction:

1. **The product contract.** Run 1's primary unit was an answer text
   judged against a payload. The product layer added on top of Run 1
   (`product/copilot/*` + `product/data/*`) introduces additional
   contractual objects per response — `intent`, `answerability`,
   `evidence`, `missing_fields`, `warnings`, `useful_refusal`,
   `suggested_next_actions` — and there is currently no benchmark that
   scores those objects against ground truth.
2. **Behaviour under payload variation.** Every Run 1 prompt was paired
   with exactly the payload it was authored for. The product contract
   has explicit branches that fire only when the payload is missing a
   field (`baseline_solution`, `diff`, `new_customer_ids`, …) or when the
   payload is *present but the question is unsupported*. Run 1 cannot
   distinguish "the contract did the right thing on a clean payload"
   from "the contract would do the right thing on a missing-field
   payload" because Run 1 only contained one payload condition per
   prompt.
3. **Abstention and useful refusal.** Run 1 surfaces 7 non-answerable
   prompts and reports useful-refusal-rate = 7/7 = 1.000. This is a
   compliance metric by construction — every non-answerable prompt
   carries a `suggested_next_actions` list because the contract emits
   one — and it does not test whether the abstention decision itself
   was correct. There is no Run 1 case where the model abstains
   incorrectly or fails to abstain when it should.
4. **Evidence precision and recall.** Run 1 reports
   `evidence_coverage = 48/48`, again a presence/contract metric. It
   does not score whether the *right* payload field paths were cited
   for a given claim, nor whether any cited field is irrelevant.

In short, Run 1 is a faithfulness evaluation of the natural-language
answer. Run 2 is a **contract evaluation** of the structured product
response. The two are complementary; neither subsumes the other.

## 2. What Run 2 evaluates

Run 2 evaluates the **product contract**: for a given (prompt, payload
condition) pair, does the product layer emit the correct structured
response? The contract surfaces under test are:

- `intent` — was the question classified into the correct intent?
- `answerability.status` and `missing_fields` — given the payload
  condition, did the system correctly judge whether the question is
  answerable, partially answerable, or not answerable, and did it list
  the right missing fields?
- `evidence` — for the supported subclaims, did the system cite the
  correct payload field paths (precision) and did it cite every field
  required to ground the claim (recall)?
- `warnings` — did the contract raise the correct policy warnings
  (`route_indexing_ambiguity`, `struct_membership_ambiguity`,
  `unsupported_comparison`, `missing_new_customer_attribution`,
  `false_premise_detected`)?
- `useful_refusal` — when refusal was correct, was the refusal payload
  (reason, missing_fields, suggested_next_actions) substantively
  correct?
- **Convention consistency** — when the response or the
  question references a route by integer, did the system use the
  product display convention (`Route N`, `display_route_number = N`)
  rather than the internal `route_idx = N-1`?

The unit of evaluation is a **case**, defined as the tuple

```
case = (prompt_text, payload_condition) → expected_contract_response
```

where `payload_condition` is one of a small, enumerated set of
mutations of a base Run 1 payload (e.g. `clean`, `missing_baseline`,
`missing_new_customer_ids`, `false_premise_customer`,
`unsupported_comparison`, …). The condition is what gives Run 2 the
payload variation Run 1 lacked.

## 3. What Run 2 explicitly does not evaluate

- **Natural-language fluency, style, or wording.** Run 2 scores the
  structured contract object, not the human-readable `answer_text`.
  Faithfulness of the text remains a Run 1 concern.
- **End-to-end operator task performance.** Time-to-answer reduction,
  trust, perceived usefulness, dashboard interaction success — these
  are user-study metrics. Run 2 is a contract benchmark, not a user
  study.
- **Solver correctness.** No solver runs are issued by Run 2. The
  payloads used are either Run 1 payloads or deterministic mutations
  thereof; the gold labels are decided from the payload condition and
  the prompt, not from a solver re-run.
- **New claim families.** Run 2 stays inside the four Run 1 claim
  families (OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE) and the 11 contract
  intents. Adding new families is out of scope.
- **Generator-side hallucination beyond the contract.** Run 2 does not
  re-score the generator's text; if the contract correctly states
  "not_answerable, missing baseline_solution" then the case is graded
  on that structured output regardless of whether a model's natural
  language wording was good or bad.

## 4. Unit of evaluation

A Run 2 case has the shape:

```
case_id              : str       — stable identifier (R2-001, R2-002, …)
source_prompt_id     : str|null  — Run 1 prompt this seeds from, if any
family               : OBJ | PLAN_VALIDITY | STRUCT | SCHEDULE
prompt_text          : str
payload_condition    : enum (see schema)
payload_mutation_needed : str — how to derive the payload from the seed
expected_intent      : enum (current 13 Intents, or Stage R2-1 extension)
expected_answerability : answerable | partially_answerable | not_answerable
expected_evidence_paths : list[str]  — field paths the response must cite
expected_missing_fields : list[str]
expected_warnings       : list[str]  — warning codes
expected_next_actions   : list[str]  — semantic next-action codes
expected_behavior_class : direct_answer | direct_answer_with_warning | useful_refusal
implementation_status   : current | target_extension
difficulty           : easy | medium | hard
label_rationale      : str
ambiguity_notes      : str | null
```

Each case is **one row** in the calibration / benchmark CSV. The
schema is locked in `run2_gold_schema.md`.

Two field choices are worth flagging here because they shape how the
benchmark reads:

- `expected_behavior_class` (replaces the earlier
  `expected_validator_result`). The earlier `pass/warn/fail` enum
  framed `useful_refusal` as a "failure," which it is not — a
  correctly refused case *passes* its gold. The renamed enum has
  four values: `direct_answer`, `direct_answer_with_warning`,
  `partial_answer_with_warning`, `useful_refusal`. It is a property
  of the case's gold, not a verdict on the system-under-test. Run 2
  reports per-component metrics (§6.1–6.8); there is no single
  pass/fail verdict per case. `partial_answer_with_warning` is the
  case shape for a multi-part question where the contract answers
  one subclaim with grounded evidence while warning about an
  ungrounded subclaim (the canonical example is the OBJ delta with
  a "compared to a full re-solve" comparator — see §7 and the
  R2-013 calibration case).
- `implementation_status`. Every row is tagged `current` (the
  current contract is expected to produce this behavior) or
  `target_extension` (the gold encodes planned behavior that the
  current contract is expected to diverge from). This separation
  exists so that "the system got this wrong because the contract
  isn't there yet" does not get conflated with "the system got this
  wrong because the contract is there and the system regressed." Run
  2 reports must split aggregate scores by `implementation_status`.

## 5. Systems under test

Run 2's primary comparison must hold the generator constant so that
the A→B→C delta isolates the contribution of the product contract
layer, not the choice of model. This was a known confound in the
first draft of this section. The revised system list:

**System A — Sonnet naive.** Claude Sonnet 4.6 given only the prompt
and the payload, with no product system prompt, no intent classifier,
no answerability check, no evidence extractor. Output: a free-text
answer that the evaluator parses into a contract-shaped object using
a deterministic adapter (§5a). Floor.

**System B — Sonnet prompt-only.** Same model as A (Sonnet 4.6), but
with a system prompt that documents the contract (intent enum,
answerability statuses, evidence field-path grammar, convention
rules) and asks the model to return a JSON object in the contract
shape. No deterministic intent/answerability/evidence backends; the
model is responsible for all four. Used to isolate "prompting helps"
from "the product layer helps."

**System C-Sonnet — Sonnet + full product layer.** The pipeline
already implemented in `product/copilot/*` + `product/data/*`
(intent → answerability → evidence → warnings → useful_refusal →
response_builder), fed by the augmented payload from
`product/data/product_schema.py`. The generator used for
`answer_text` (where the contract response includes one) is Sonnet
4.6, matching A and B. This is the main system Run 2 evaluates.

**System C-Haiku — Haiku + full product layer (optional, continuity
check).** Same pipeline as C-Sonnet, but the `answer_text` generator
is Haiku 4.5 — the same model family used in Run 1. Reported
separately from the A/B/C-Sonnet comparison; its purpose is to give
Run 1 readers a like-for-like continuity number, not to argue about
the contract layer.

**Why this split.** A vs B vs C-Sonnet holds the model fixed and
varies only the surrounding scaffold (none → prompted → contract).
That isolates the product-layer effect. Mixing in C-Haiku to the
main comparison would conflate the contract-layer effect with the
generator-family effect; reporting C-Haiku separately preserves the
Run 1 continuity number without contaminating the headline finding.

**Contract-only mode for System C.** Most Run 2 metrics —
intent accuracy, answerability accuracy, evidence
precision/recall, missing-field recall, warning precision/recall,
useful-refusal correctness — depend only on the contract-shaped
object that `product.copilot.response_builder` returns. They do
**not** depend on the natural-language `answer_text`. For those
metrics, System C can run in *contract-only mode* (no generator
call), and the score is deterministic — A vs B vs C-Sonnet still
holds because A and B both depend on a generator. The two metrics
that **do** depend on `answer_text` are convention consistency
(§6.8, regexes route numbers in the answer) and any future
`answer_text`-sensitive probe; for those, C-Sonnet and C-Haiku
diverge from contract-only-C, and the report must say which
variant produced the number.

Run 2 reports per-metric scores for A, B, C-Sonnet, optionally
C-Haiku, and the A→C-Sonnet delta. The research claim Run 2
supports is "the product contract layer improves contract metrics
over both a naive frontier model and a contract-aware prompted model
on a payload-varying test set, holding the generator family fixed at
Sonnet 4.6," not "the language layer is faithful," which Run 1
already established.

## 5a. Adapter and normalization for model baselines

System A returns free text; System B returns a JSON-shaped contract
object the model produced; System C returns a contract object the
product layer produced. The evaluator normalizes all three onto the
same gold-comparable shape before any metric is computed. The rules
below also make the gold *independent of stochastic wording* — the
gold warning set for a case does not change because a model happened
to mention a route by number.

- **System A adapter.** A deterministic parser (separate stage, no
  model call) extracts `intent`, `answerability.status`, evidence
  field paths, missing fields, and warnings from the model's free
  text, using the same patterns the product layer uses internally
  (`intent.py:_COMPARATIVE_TOKENS`, the `route \d+` regex, the
  refusal-phrase list). The adapter is stable across runs and is
  versioned alongside the evaluator.
- **System B normalizer.** B already emits JSON; the normalizer
  strips fields the schema does not allow, lower-cases enums,
  rejects unknown intents/warnings (mapping them to `unknown` /
  empty), and applies the same path-stripping (§10a of the schema)
  to evidence.
- **System C normalizer.** Mostly a passthrough — `product/copilot`
  already produces contract-shaped objects — but path normalization
  is applied so that pinned evidence paths
  (`routes[route_idx=4].customer_ids`) match the gold's generic
  paths.
- **Warning precision/recall is scored against the *fixed* gold
  warning set.** If a system's answer text happens to mention "Route
  5," the system's emitted `route_indexing_ambiguity` warning is
  scored as a false positive against any case whose gold does not
  include it. The gold is **not** dynamically expanded based on
  sampled wording.
- **Convention consistency is the place where wording matters.**
  §6.8 checks whether the route number cited in `answer_text`
  resolves under the display convention to a `route_idx` that
  appears in the evidence. It is allowed to penalize a system whose
  wording introduces a route-number ambiguity; warning gold is not
  changed in response.
- **No retries; no best-of-k.** The R2-0 baseline runs are
  single-sample. Stochastic stability is a Stage R2-3 concern (§8).

## 6. Proposed metrics

All metrics are computed per case and aggregated per system. Unless
stated otherwise, each is a fraction in `[0, 1]`.

### 6.1 Intent accuracy
`count(predicted_intent == expected_intent) / n_cases`.
A single discrete label. Failure modes include: misrouting a
`before_after_comparison` to `route_count`, misrouting a
`single_customer_route_membership` to `same_route_boolean` when only
one customer is named, classifying a refusal-shaped question as
`unknown` instead of `refusal_or_insufficient_payload`.

### 6.2 Answerability accuracy
`count(predicted_status == expected_status) / n_cases`, where status is
the three-valued enum `answerable | partially_answerable |
not_answerable`. Conceptually analogous to AbstentionBench's
answerability evaluation, adapted to VRPTW payload availability.

### 6.3 Evidence precision
This is a **field-family** metric, not an entity-specificity metric
(see schema §10a). For each case where the contract returns one or
more `evidence` items, let `P` be the predicted set of `field_path`
strings (normalised by stripping predicate-style qualifiers like
`[route_idx=4]` to `[]`) and `G` be the gold
`expected_evidence_paths` set (which by schema convention is already
generic, never pinned). Then

```
precision_case = |P ∩ G| / |P|     if |P| > 0
               = 1                  if |P| = |G| = 0
               = 0                  if |P| > 0 and |G| = 0
```

Aggregate as a macro-average over cases that have non-empty `P` or
`G`. This is the field-path analogue of ALCE's citation precision.

### 6.4 Evidence recall
Symmetric to 6.3:

```
recall_case = |P ∩ G| / |G|        if |G| > 0
            = 1                     if |G| = 0
```

Aggregate macro-averaged. A case can be high-precision and
low-recall if the contract cites only one of several required fields
(e.g. cites `action_objective` but omits `units.objective`).

**Entity specificity is deferred.** A response that cites
`customer_schedule[customer_id=99].arrival` matches the gold
`customer_schedule[].arrival` even if the question was about
customer 42. Whether the cited entity is the *right* entity is
graded by convention consistency (§6.8) where relevant; a dedicated
`evidence_specificity` metric is a possible Stage R2-1 or later
addition.

### 6.5 Missing-field recall
For cases where `expected_answerability ∈ {partially_answerable,
not_answerable}`:

```
missing_recall_case = |predicted_missing ∩ expected_missing| /
                       |expected_missing|
```

This is the part of the contract that drives the **useful refusal**
suggested next actions. A failure here means the system either
abstained for the wrong reason or did not list a recoverable next
step.

### 6.6 Warning precision / recall
Treat the warning code set per case as a set-classification problem:

```
warning_precision = |predicted_warnings ∩ expected_warnings| /
                     |predicted_warnings|       if |predicted_warnings| > 0
warning_recall    = |predicted_warnings ∩ expected_warnings| /
                     |expected_warnings|        if |expected_warnings| > 0
```

Both default to 1 when both sides are empty. The case-level pair is
macro-averaged. Important: warnings carry an operator-attention cost,
so warning precision is reported as prominently as warning recall.

### 6.7 Useful-refusal correctness
A composite per case whose `expected_behavior_class ∈
{useful_refusal, partial_answer_with_warning}` — the two refusal-
or partial-shaped behavior classes. A response is **useful-refusal
correct** iff *all* of the following hold:

- `predicted_status` matches the gold `expected_answerability`
  (`partially_answerable` or `not_answerable`);
- the predicted `missing_fields` ⊇ the gold `expected_missing_fields`
  (with the §12 false-premise exception: when gold missing-fields is
  empty, the predicted set may also be empty);
- the predicted `suggested_next_actions` contains at least one of the
  gold `expected_next_actions` semantic codes.

Reported as a count and as a rate over the
useful-refusal-or-partial subset. Unlike Run 1's
`useful_refusal_rate`, the denominator is grounded because Run 2 has
gold labels. *A useful refusal is a correct outcome, not a failure*;
the metric scores whether the refusal payload matches gold, not
whether the system refused.

### 6.8 Convention consistency
For cases whose `payload_condition` or `expected_warnings` carries a
route convention concern, score whether the response uses the display
convention (`Route N`, `display_route_number = N`) in both
`answer_text` (if any) and `evidence` field paths, or — for
system A/B that may emit only text — whether the route numbers cited
in the text map under `display_route_number = route_idx + 1` to the
route_idx whose `customer_ids` or `end_time` is implied. Macro-average
over the convention-relevant subset. This is the structured analogue
of metric 4.8 in the Run 1 baseline report.

### 6.9 No aggregate composite
The earlier draft of this design proposed an unweighted aggregate
composite over {intent acc, answerability acc, evidence F1,
missing-field recall, warning F1, useful-refusal correctness,
convention consistency}. The R2-0 revision **removes** that
composite. The justification: an unweighted mean implies every
component matters equally, which is not true — a contract that
silently answers a `false_premise` case has lost the case in a way
that intent accuracy on the other 14 cases cannot offset. Reporting
the components separately, split by `implementation_status`, is the
authoritative report. The composite, if it exists at all, lives in
a future appendix as an optional diagnostic and is not used to
support any thesis claim.

## 7. Explicit product conventions Run 2 will enforce

Every gold label is written under these conventions, which describe
the **target** contract. A response that violates a convention is
graded against the convention, not against "what the model probably
meant." Where a convention is not yet implemented in the current
contract, cases that depend on it are marked
`implementation_status = target_extension`; the gold still encodes
the target behavior (per fix R2-0-2 — *do not encode current system
limitations as gold*). See §7a for the per-convention current/target
breakdown.

- **route_label vs route_idx.** User-facing references to routes use
  `Route N` where `N = route_idx + 1`. Evidence field paths may carry
  `route_idx=K` as a predicate qualifier, but any user-visible number
  in `answer_text` or `display_label` must use the display number.
  Source of truth: `product/data/product_schema.py:_add_display_to_route_dict`.

- **single-customer membership vs full-route equality.** A question
  that names one customer and asks "which route is customer X on?" is
  `single_customer_route_membership` and triggers
  `struct_membership_ambiguity`. A question that asks "which customers
  are on each vehicle?" is **not** a single-customer-membership
  question, and any answer that lists a single customer in place of
  the full route roster is a contract failure.

- **before/after requires baseline_solution + diff (except OBJ).** For
  PLAN_VALIDITY / STRUCT / SCHEDULE before/after questions, the
  required fields are `baseline_solution` and `diff`. If either is
  missing the case is `not_answerable` and `unsupported_comparison`
  must fire. For OBJ before/after questions, the escape hatch in
  `product/data/answerability.py:_obj_delta_already_covered` applies:
  presence of `baseline_objective + action_objective +
  objective_delta_absolute` makes the OBJ delta answerable from inline
  fields.

- **OBJ `baseline_objective` is *pre-perturbation*, not "a full
  re-solve."** This is the §7a convention that the Run 1 baseline
  report's volunteered/risky-comparison probe (metric 4.4) hinted at
  but did not enforce. Per
  `experiment/configs/payload_schemas_rationale.md:75`,
  `baseline_objective` is "pre-perturbation `baseline_obj` from the
  Stage A row" — the cost of the original plan before the
  perturbation, not the cost of running a full re-solve of the
  perturbed instance. When an operator's prompt frames the delta as
  "compared to a full re-solve" / "vs the optimum" / "if we re-ran
  from scratch," the comparator named in natural language does
  **not** refer to `baseline_objective` and the payload does not
  carry the field it would refer to (a hypothetical
  `reference_solution.objective`). Target behavior: respond as
  `partial_answer_with_warning` — cite the OBJ delta evidence
  (baseline_objective, action_objective, the two delta fields) as
  the supported subclaim, raise `comparison_referent_ambiguity`,
  list `reference_solution.objective` as a missing field for the
  unsupported comparator subclaim, and suggest
  `expose_reference_solution_objective`. The R2-013 calibration case
  is the canonical example. This is a `target_extension` policy; the
  current contract does not emit the warning, and the *benign* OBJ
  delta question with a "compared to before" comparator (R2-002) is
  a separate `direct_answer` / `current` case.

- **new-customer assignment requires new_customer_ids.** Any question
  whose subject is "the new customer / order" requires
  `new_customer_ids` in the payload. Absence yields
  `partially_answerable` (the route plan is visible; the attribution
  is not), `missing_new_customer_attribution`, and the
  "Expose perturbation.new_customer_ids" next action.

- **Unsupported prompts require useful refusal.** Any prompt graded
  `not_answerable` or `partially_answerable` must emit a
  `useful_refusal` with non-empty `suggested_next_actions`. Empty
  refusals are a contract failure even if the abstention itself was
  correct.

- **False premise.** If the question presupposes a fact the payload
  contradicts (e.g. "when does the driver reach customer 999?" when
  customer 999 does not exist), the expected behaviour is
  `not_answerable` + `false_premise_detected` warning, **not** silent
  best-effort answering against the nearest customer. This is a
  `target_extension`: the current contract does not detect this case
  (it would mark the question answerable because the required
  *types* of field exist for other entities), and the calibration
  case for it is tagged accordingly.

- **Full-route listing has its own intent.** A question that asks
  "list the customers on each route" or "which customers are on each
  vehicle" is operationally meaningful and is grounded by
  `routes[].customer_ids`. It is **not** a
  `single_customer_route_membership` question and it is **not** an
  `unknown` question — the only reason the current contract returns
  `unknown` is that the intent enum does not yet contain a
  `full_route_listing` value. The target contract adds that intent.
  This is a `target_extension`.

## 7a. Current vs target behavior: per-convention summary

The table below maps each convention to its current contract
implementation and whether cases that depend on it are encoded as
`current` or `target_extension` gold:

| Convention | Currently implemented? | Implementation surface | `implementation_status` for cases |
|---|---|---|---|
| `route_label` / `route_idx` augmentation | yes | `product/data/product_schema.py:add_display_route_numbers` | `current` |
| `single_customer_route_membership` warning | yes | `refusal_policy.py:build_warnings` | `current` |
| `before/after` requires `baseline_solution`+`diff` (non-OBJ) | yes | `answerability.py:_REQUIRED_FIELDS["before_after_comparison"]` | `current` |
| OBJ delta escape hatch via inline fields | yes | `answerability.py:_obj_delta_already_covered` | `current` |
| `new_customer_assignment` requires `new_customer_ids` | yes | `answerability.py:_REQUIRED_FIELDS["new_customer_assignment"]` | `current` |
| Useful refusal with non-empty `suggested_next_actions` | partial — fails when missing fields have no entry in `refusal_policy._NEXT_ACTION_BY_FIELD` (e.g. `feasibility_breakdown`) | `refusal_policy.compose_suggestions` | `target_extension` for the gap rows |
| OBJ "vs full re-solve" comparator → `comparison_referent_ambiguity` warning + `reference_solution.objective` missing field + `partial_answer_with_warning` behavior class | **no** | not implemented; surfaced only by the diagnostic `volunteered_or_risky_comparison_guardrail_hits` probe in `product/data/metrics.py` | `target_extension` |
| OBJ missing `units.objective` → `evidence_units_missing` warning + `expose_units_objective` next action | **no** | not implemented; the contract silently omits the unit when the field is absent | `target_extension` |
| False premise detection → `false_premise_detected` warning + `clarify_false_premise` next action | **no** | not implemented | `target_extension` |
| `full_route_listing` intent | **no** | not in `Intent` Literal in `contracts.py` | `target_extension` |

This is the §7a "target/current distinction" the R2-0 revision adds.
Gold labels are written against the target column; the
`implementation_status` field is the per-case bookkeeping that
records whether the gold matches the current contract.

## 8. Planned dataset size

- **Stage R2-0 (this stage):** 15 calibration cases (revised up from
  10 → 12 → 15 across two R2-0 revisions: +PLAN_VALIDITY coverage,
  +split of R2-002 into benign delta and comparator-ambiguity cases,
  +OBJ `missing_units` case, +`false_premise_route` companion to
  the existing `false_premise_customer` case). Their purpose is
  to (i) stress-test the gold schema by labelling cases manually and
  reaching agreement on edge cases, and (ii) make any schema or
  metric ambiguities visible before the larger set is built.
- **Stage R2-1:** expand to a 60-case benchmark covering each of the
  4 families × ~5 payload conditions × ~3 difficulty bins, with
  intentional coverage of false premise, partial answerability, the
  convention boundary cases, and the proposed intent / warning /
  next-action extensions documented in §3.2, §5.2 and §6.2 of
  `run2_gold_schema.md`. The exact distribution is a Stage R2-1
  decision and is not committed by this document. Stage R2-1 must
  preserve the current/target split — the benchmark is not allowed
  to be all-`current` or all-`target_extension`.
- **Stage R2-2:** evaluator implementation and System A / B /
  C-Sonnet runs against the 60-case benchmark. None of this runs
  during Stage R2-0. Every Run 2 report must split aggregate
  metrics by `implementation_status` so that contract-gap failures
  and contract-regression failures are not conflated.
- **Stage R2-3 (optional reliability sweep):** on a stratified hard
  subset of the benchmark (e.g. the `hard` difficulty band and the
  `target_extension` rows), run the stochastic Systems A and B with
  *k = 5* samples per case and report (a) the point-estimate score
  used in Stage R2-2 and (b) the all-`k` success rate (a.k.a.
  pass^k — the fraction of cases on which the system produces a
  gold-correct contract object every time across `k` independent
  samples). Purpose: distinguish stable contract behaviour from
  sampling luck. System C metrics that depend only on the
  deterministic contract object (intent acc, answerability acc,
  evidence precision/recall, missing-field recall, warning
  precision/recall, useful-refusal correctness) do **not** require
  pass^k, because the contract is deterministic given the same
  payload; only `answer_text`-sensitive metrics (convention
  consistency in particular) need pass^k for System C. Not
  implemented in R2-0; design hook only.

## 9. Gold-label protocol

For Stage R2-0:

1. The author proposes a case (prompt + payload condition + expected
   contract fields + rationale).
2. A second labeller (the principal investigator, or another labeller
   blinded to the proposal's rationale) re-derives the expected
   contract fields from the prompt and payload condition alone.
3. The two labels are compared. Disagreements are recorded in
   `ambiguity_notes` on the case and trigger either a schema
   clarification (preferred) or a difficulty bump.
4. The case is included once the two labellers agree on `intent`,
   `expected_answerability`, and `expected_warnings`. Evidence
   field-path lists may have small disagreements that are absorbed
   into `ambiguity_notes` and revisited in Stage R2-1.

For Stage R2-1 the protocol will be extended to require a documented
adjudication round; that is out of scope for Stage R2-0.

**Disagreement log.** Calibration produces two artefacts: (a) the
per-row `ambiguity_notes` field on each case, which records local
edge-case interpretations, and (b) an aggregate disagreement log at
`product/evaluation/run2_calibration_disagreement_log.md`, which is
the changelog of schema/policy decisions made during R2-0
calibration that should carry forward into R2-1 (case splits,
policy clarifications, new behavior classes, etc.). The
disagreement log is **not** a per-row commentary; it captures
issues that triggered a schema-level change or that remain open
ambiguities for the next stage. Every R2-0 → R2-1 hand-off must
review the disagreement log first.

## 10. Caveats

- **Calibration set is not the benchmark.** The 15 calibration cases
  are explicitly an instrument-shakedown set. They are not balanced
  enough to be reported as a benchmark result and should not be used
  to score systems comparatively.
- **`current` vs `target_extension` rows score differently.** A Run
  2 run of System C against the current contract will, by
  construction, score below the gold on the `target_extension`
  subset. That is the intended behavior — the
  `target_extension` rows are the policy backlog, not a regression
  test of the existing contract. Reports that present a single
  aggregate composite without splitting by `implementation_status`
  will hide both contract gaps and contract regressions; always
  split.
- **Synthetic payload mutations are deterministic but not
  operationally validated.** "missing_new_customer_ids" simply
  removes that key from the payload; it does not re-run a solver. The
  contract under test does not require a re-solve, so this is a
  faithful test of the contract, but it does *not* validate the
  underlying VRP claim itself.
- **Single-labeller risk in Stage R2-0.** With only two labellers,
  inter-rater agreement statistics are not meaningful. Stage R2-1
  will widen the labeller pool.
- **No model calls in Stage R2-0.** The systems-under-test are
  described here for completeness; nothing is run until at least
  Stage R2-2.
- **Convention consistency depends on parser quality.** For systems
  A/B that emit free text, the convention-consistency metric is only
  as good as the route-number regex used to parse their text. This is
  the same limitation as Run 1 metric 4.8 and is inherited
  deliberately.
- **Evidence precision/recall is field-path equality, not semantic
  equivalence.** A response that cites `routes[route_idx=4].customer_ids`
  matches a gold of `routes[].customer_ids` only after the qualifier
  is stripped. A response that cites `n_routes` does **not** match a
  gold of `routes[].customer_ids` even if the underlying value is
  consistent. This is the strict interpretation; loosening it is a
  Stage R2-1 decision.

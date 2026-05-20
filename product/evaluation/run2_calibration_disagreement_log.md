# Run 2 — Calibration Disagreement Log

_Aggregate changelog of schema and policy decisions made during R2-0
calibration. This is a complement to the per-row `ambiguity_notes`
field in `run2_calibration_cases.csv`: per-row notes record local
edge-case interpretations; this log records issues that triggered a
schema-level change or that remain open ambiguities for Stage R2-1._

The log is the canonical R2-0 → R2-1 hand-off artefact. Every Stage
R2-1 reviewer should read this before proposing new cases or new
schema values.

## How to read this log

Each entry is a separate `###` subsection with the following
sub-fields:

- **case_id** — the calibration case(s) that triggered the issue, or
  `n/a` if the issue is purely schema-level.
- **issue / disagreement** — the disagreement or ambiguity, stated
  in one or two sentences.
- **resolution** — what was decided.
- **schema change made?** — yes / no; if yes, point to the schema
  section.
- **remaining ambiguity** — what is still unresolved at the end of
  R2-0, if anything.
- **carried to R2-1?** — yes / no; if yes, what Stage R2-1 must do
  about it.

## Entries

### D-001 — R2-002 mixed two distinct issues

- **case_id:** R2-002 (original)
- **issue / disagreement:** The original R2-002 used the Run 1
  prompt-002 wording ("compared to running a full re-solve") and
  was labelled `answerable` because the OBJ escape hatch supplies a
  delta from inline fields. But the natural-language comparator ("a
  full re-solve") does not refer to what the payload's
  `baseline_objective` actually is — `baseline_objective` is the
  pre-perturbation Stage A cost
  (`experiment/configs/payload_schemas_rationale.md:75`), not a
  full re-solve of the perturbed instance. Labelling the case
  `answerable / direct_answer` would let a system silently treat
  "compared to a full re-solve" as a clean baseline-vs-action
  delta, hiding the comparator ambiguity the Run 1 baseline report
  flagged (metric 4.4, volunteered/risky comparison probe).
- **resolution:** Split into two cases. R2-002 keeps the OBJ
  escape-hatch path with a *benign* rewritten comparator
  ("compared to before"), as `direct_answer / answerable /
  current`. R2-013 keeps the original Run 1 wording ("compared to
  running a full re-solve"), labelled `partial_answer_with_warning /
  partially_answerable / target_extension` with
  `comparison_referent_ambiguity` warning,
  `reference_solution.objective` missing field, and
  `expose_reference_solution_objective` next action.
- **schema change made?** Yes. Added `partial_answer_with_warning`
  to the `expected_behavior_class` enum (schema §7), with the
  required shape: `partially_answerable` + non-empty
  evidence/warnings/missing/next-actions. Added
  `comparison_referent_ambiguity` to warning codes (schema §5.2)
  and `expose_reference_solution_objective` to semantic next-action
  codes (schema §6.2), both as `target_extension`.
- **remaining ambiguity:** Whether `partial_answer_with_warning`
  versus `useful_refusal` is the right shape for *other* partial
  cases (e.g. when only some entities in a multi-entity question
  are answerable). The distinction in schema §7 — "did the contract
  cite evidence for the supported subclaim?" — is a clean criterion
  for OBJ delta / units / OBJ family cases, but multi-entity
  STRUCT/SCHEDULE partial cases have not been calibrated yet.
- **carried to R2-1?** Yes. Stage R2-1 should add at least two
  multi-entity partial cases (e.g. a route_end_time question that
  names two routes where only one route's data is in the payload)
  and verify that the partial_answer_with_warning vs useful_refusal
  rule from §7 still adjudicates them cleanly.

### D-002 — R2-010 current `unknown` vs target `full_route_listing`

- **case_id:** R2-010
- **issue / disagreement:** The question "List all the customers
  assigned to each route" is operationally meaningful and is
  grounded by `routes[].customer_ids`, but the current contract's
  STRUCT intent branch has no matcher for the "per each route" /
  "list all" phrasing and routes the question to `unknown`. The
  first R2-0 draft labelled the case `unknown / not_answerable /
  current` to reflect the current behaviour — which violated R2-0
  fix #1 (do not encode current limitations as gold).
- **resolution:** Re-label as a target case under a new proposed
  intent `full_route_listing`. The gold is `answerable / direct_answer`
  with evidence `routes[].customer_ids`; the case is marked
  `target_extension` so System C against the current contract is
  expected to score 0 on intent accuracy and missing-field recall
  for this row.
- **schema change made?** Yes. Added `full_route_listing` to the
  proposed Stage R2-1 intents (schema §3.2). The corresponding
  current-behaviour observation is recorded in the case's
  `ambiguity_notes`.
- **remaining ambiguity:** Whether a `full_route_listing` response
  also needs to cite `routes[].route_idx` (or `route_label`) in
  evidence to be useful to the dashboard. R2-0 gold uses only
  `routes[].customer_ids`.
- **carried to R2-1?** Yes. Decision needed in R2-1: does
  `full_route_listing` require both the route identifier and the
  customer list in evidence, or is the customer-list field
  sufficient under the contract?

### D-003 — Evidence path pinning ambiguity

- **case_id:** R2-004, R2-006, R2-007 (and any future
  entity-specific intent)
- **issue / disagreement:** The schema field-path grammar (schema
  §10) allows both generic paths (`customer_schedule[].arrival`)
  and predicate-pinned paths
  (`customer_schedule[customer_id=42].arrival`), but the first R2-0
  draft did not commit on which form gold should use, nor on
  whether evidence precision/recall should grade entity specificity.
  The product layer's `evidence.py` already emits pinned paths
  because the dashboard renders them as "Customer 42 on Route 5";
  grading systems that pin against a generic gold would be
  arbitrary.
- **resolution:** Gold `expected_evidence_paths` is always generic.
  The evaluator normalises predicate-pinned system outputs to
  generic before matching (schema §10a). Evidence precision/recall
  is a *field-family* metric; entity specificity is handled by
  convention consistency (metric 6.8) and a possible future
  `evidence_specificity` metric.
- **schema change made?** Yes. Added schema §10a "Evidence path
  specificity policy" and the predicate-pinned-gold disallowed
  shape in §13. Updated design doc §6.3 and §6.4 to call out the
  field-family framing.
- **remaining ambiguity:** None at R2-0 schema level. The future
  `evidence_specificity` metric is intentionally deferred; if it is
  added it must not require relabelling because gold is generic.
- **carried to R2-1?** Optional. Stage R2-1 may decide to add the
  `evidence_specificity` metric; if so, it grades whether the cited
  entity matches the entity named in the question, not the
  field-path family.

### D-004 — False-premise rows have no missing required fields

- **case_id:** R2-008, R2-015
- **issue / disagreement:** Useful-refusal cases canonically list a
  required field that the payload does not carry. False-premise
  cases break that pattern: the payload *does* carry the required
  type of field (e.g. `customer_schedule[].arrival` is present),
  but for *other* entities, not the one the prompt named. An
  earlier draft considered fabricating a synthetic missing field
  like `customer_schedule[customer_id=999].arrival` to satisfy a
  "useful_refusal must list missing fields" rule. That would
  silently penalise systems for omitting a payload field that was
  never the actual issue.
- **resolution:** Schema §12 explicitly allows
  `expected_missing_fields` to be empty for
  `payload_condition ∈ {false_premise_customer, false_premise_route}`,
  with the trade-off that `false_premise_detected` must appear in
  `expected_warnings` and `clarify_false_premise` must appear in
  `expected_next_actions`. The useful-refusal-correctness metric
  (design §6.7) is updated so that an empty gold-missing set permits
  an empty predicted-missing set.
- **schema change made?** Yes. Added §12 "False-premise rows
  (Stage R2-0 exception)" and the corresponding disallowed-shape
  rules in §13.
- **remaining ambiguity:** Whether other "structural false premise"
  classes exist that R2-0 did not enumerate (e.g. "a customer that
  exists but is not in the current solution," or "a route_idx that
  exists but has zero customers"). R2-0 ships with two: customer
  and route.
- **carried to R2-1?** Yes. Stage R2-1 should add cases that probe
  the boundary between false-premise and missing-required-field
  cases (e.g. a question about a customer who exists in the payload
  but has no `customer_schedule` row).

### D-005 — Useful-refusal cases with no current next-action mapping

- **case_id:** R2-012, R2-014 (and any future case whose missing
  field is not in `refusal_policy._NEXT_ACTION_BY_FIELD`)
- **issue / disagreement:** The schema requires that every
  `useful_refusal` (and `partial_answer_with_warning`) row carry a
  non-empty `expected_next_actions`. But the current contract's
  `refusal_policy._NEXT_ACTION_BY_FIELD` only maps a handful of
  fields (`baseline_solution`, `diff`, `new_customer_ids`, the
  display augmentations, the schedule fields). Cases whose missing
  field is `feasible`, `feasibility_breakdown`, or `units.objective`
  produce a `UsefulRefusal` with empty `suggested_next_actions`
  under current code — a contract-convention violation that no
  current System C run can score correctly.
- **resolution:** Add target semantic next-action codes
  `use_validity_payload` and `expose_units_objective` to the schema
  (§6.2) as `target_extension`, and mark the affected cases
  (R2-012, R2-014) as `target_extension` so the divergence between
  current contract behaviour and target gold is recorded explicitly
  rather than hidden as a schema violation.
- **schema change made?** Yes. Added the two semantic codes to §6.2;
  added `evidence_units_missing` warning code to §5.2 for the
  paired R2-014 warning.
- **remaining ambiguity:** Whether the gap should be closed in
  Stage R2-1 code (extend `_NEXT_ACTION_BY_FIELD`) or only in the
  benchmark (treat it as a target the system is allowed to fail).
  R2-0 deliberately does not commit; the disagreement log keeps it
  open.
- **carried to R2-1?** Yes. Stage R2-1 should decide whether to
  close the gap by extending `refusal_policy._NEXT_ACTION_BY_FIELD`
  to map `feasible`, `feasibility_breakdown`, and `units.objective`
  to the new semantic codes.

### D-006 — `expected_validator_result` → `expected_behavior_class` rename

- **case_id:** n/a (schema-level)
- **issue / disagreement:** The first R2-0 draft used the field
  name `expected_validator_result` with values `pass / warn / fail`.
  That framed `useful_refusal` (which the case is meant to be) as
  `fail`, conflating "the case's gold response is a refusal" with
  "the system-under-test failed."
- **resolution:** Renamed to `expected_behavior_class` with values
  `direct_answer / direct_answer_with_warning /
  partial_answer_with_warning / useful_refusal`. Run 2 scores
  systems on per-component metrics; there is no single pass/fail
  verdict per case.
- **schema change made?** Yes. Schema §7 and §1 row table.
- **remaining ambiguity:** None.
- **carried to R2-1?** No. Closed.

### D-007 — Generator-family confound in A/B/C comparison

- **case_id:** n/a (design-level)
- **issue / disagreement:** The first R2-0 draft of design §5
  described Systems A and B as "Sonnet" but did not name the
  generator System C uses for `answer_text`. If C uses Haiku (Run 1
  generator) while A and B use Sonnet, the A→C delta confounds the
  product-layer effect with a generator-family effect.
- **resolution:** Pin all three systems to Sonnet 4.6 for the main
  comparison (Systems A, B, C-Sonnet). Report a separate
  C-Haiku run as a continuity check, not part of the headline
  finding. Most Run 2 metrics depend only on the deterministic
  contract object (which does not require a generator), and the
  design now flags which metrics depend on `answer_text`.
- **schema change made?** No. Design doc §5 and new §5a only.
- **remaining ambiguity:** Whether C-Haiku should be a permanent
  reported number or a one-off continuity check. R2-0 takes the
  one-off view.
- **carried to R2-1?** Yes. Stage R2-2 (the actual run) should
  decide whether to keep C-Haiku in subsequent runs.

### D-008 — Aggregate composite metric removed

- **case_id:** n/a (design-level)
- **issue / disagreement:** The first R2-0 draft included an
  unweighted aggregate composite over the per-component metrics as
  a headline number. That implies every component matters equally —
  but a system that silently passes a false-premise case has lost
  it in a way that intent accuracy on other cases cannot offset.
- **resolution:** Remove the composite from the main design doc.
  Run 2 reports component metrics only, split by
  `implementation_status`.
- **schema change made?** No. Design doc §6.9 updated to record
  the removal.
- **remaining ambiguity:** None.
- **carried to R2-1?** No. Closed.

### D-009 — Stochastic stability is a Stage R2-3 concern, not R2-0

- **case_id:** n/a (planning-level)
- **issue / disagreement:** Systems A and B are stochastic; a
  single-sample score may misrepresent stable behaviour. The R2-0
  revision asks whether pass^k / reliability should be in the
  Stage R2-0 schema.
- **resolution:** Add a Stage R2-3 placeholder in the design doc's
  planned-stages section that describes the pass^k methodology and
  the stratified hard subset. Do not implement now; the schema does
  not need to change for it.
- **schema change made?** No. Design doc §8 only.
- **remaining ambiguity:** k value. R2-0 suggests k=5 as a
  starting point.
- **carried to R2-1?** Partially — the R2-3 plan exists; the
  decision to run it is a Stage R2-2 or R2-3 call, not R2-0.

### D-011 — R2-004 `route_indexing_ambiguity` removed from gold

- **case_id:** R2-004
- **issue / disagreement:** The R2-0 gold listed both
  `struct_membership_ambiguity` and `route_indexing_ambiguity` in
  `expected_warnings`. The R2-1 evaluator (running System C in
  contract-only mode, per design §5 "Contract-only mode for System
  C") found that `refusal_policy.build_warnings` only fires
  `route_indexing_ambiguity` when either the prompt text or the
  answer text contains an integer route reference (or the
  prompt_id is in the explicitly-flagged set
  `{040, 041}`). R2-004's prompt text does not name a route by
  integer (it asks "which route is customer 42 on?"); the original
  gold's expectation that the warning would fire was conditional on
  a hypothetical answer text saying "on route 5." This violates
  design §5a ("the gold warning set is not dynamically expanded
  based on sampled wording") because it required a stochastic
  generator output that the contract-only evaluator does not have.
- **resolution:** Drop `route_indexing_ambiguity` from
  R2-004's `expected_warnings`. Keep `struct_membership_ambiguity`
  (which fires from intent alone) and `direct_answer_with_warning`
  behavior class. Route-number display convention concerns for the
  eventual rendered answer are graded by **convention consistency**
  (design §6.8), not by warning recall in contract-only mode.
- **schema change made?** No — only the case-level gold changed.
  Schema §5 still allows `route_indexing_ambiguity` for cases
  whose prompt text names a route by integer (R2-006 still
  carries it correctly, because its prompt text literally says
  "route 1").
- **remaining ambiguity:** Whether Stage R2-2 should add an
  `answer_text`-mode for System C where this warning is checked
  against actually generated text. R2-0/R2-1 only score
  contract-only.
- **carried to R2-1?** Closed by this revision. Stage R2-2 should
  decide whether to add answer-text-mode scoring; if so, this case
  may need a paired test that does name a route by integer in
  prompt or answer.

### D-012 — Evidence over-specification for R2-006 and R2-007

- **case_id:** R2-006, R2-007
- **issue / disagreement:** R2-0 gold listed two field-family
  paths per case (the identifier *and* the value):
  - R2-006: `route_end_times[].route_idx;route_end_times[].end_time`
  - R2-007: `customer_schedule[].customer_id;customer_schedule[].arrival`
  The R2-1 evaluator showed that the current contract emits a
  single evidence item per case (e.g.
  `route_end_times[route_idx=0].end_time` or
  `customer_schedule[customer_id=42].arrival`), where the entity
  identifier is *conveyed through the predicate qualifier*. Schema
  §10a strips predicate qualifiers before matching, so the predicted
  set normalises to `{route_end_times[].end_time}` and
  `{customer_schedule[].arrival}` respectively. The gold's
  additional `[].route_idx` / `[].customer_id` entries are
  unreachable by the current evidence layer and were over-specified
  for an R2-1 evidence-recall metric that explicitly does not grade
  predicate specificity.
- **resolution:** Drop the identifier paths
  (`route_end_times[].route_idx`,
  `customer_schedule[].customer_id`) from the gold. Keep only the
  value-bearing paths (`...end_time`, `...arrival`). Both cases'
  `ambiguity_notes` were updated to record that entity-specific
  pinning is a convention-consistency / future
  `evidence_specificity` concern (schema §10a), not an
  evidence-recall concern.
- **schema change made?** No — the policy in schema §10a already
  said evidence precision/recall is a field-family metric and
  predicate-pinned details are out of scope. The R2-0 calibration
  rows simply did not follow that policy strictly. R2-1 corrects
  the rows to match the schema.
- **remaining ambiguity:** Whether Stage R2-1 needs to add an
  `evidence_specificity` metric that grades entity pinning
  directly. R2-0/R2-1 do not; the field-family evidence
  precision/recall metric stands.
- **carried to R2-1?** Closed by this revision. Stage R2-2 may
  add `evidence_specificity` as an optional auxiliary metric.

### D-013 — R2-010 acquired an explicit seed

- **case_id:** R2-010
- **issue / disagreement:** The R2-0 case for
  `full_route_listing` (target_extension) had an empty
  `source_prompt_id` and a deliberately vague
  `payload_mutation_needed` ("any clean STRUCT-family payload with
  an ORDER_CHANGE perturbation"). The R2-1 materializer correctly
  refused to silently guess and returned
  `skipped_no_seed`, meaning the case could not be scored end-to-end
  by the evaluator.
- **resolution:** Pick a concrete seed and write it into the CSV.
  Selected Run 1 prompt **028** (STRUCT, R102 with OC_1
  perturbation): 18 routes, `routes[].customer_ids` populated for
  every route, which is what the target full_route_listing intent
  grounds against. Updated the case's
  `payload_mutation_needed` text to reference 028 explicitly and
  added a note in `ambiguity_notes` recording the R2-1 backfill.
- **schema change made?** No — schema §2 already lists
  `full_route_membership` as a valid `payload_condition`; the
  change is per-row gold backfill.
- **remaining ambiguity:** Whether 028 is the right seed
  representative. Any STRUCT/OC seed with non-empty
  `routes[].customer_ids` works equivalently for contract-only
  scoring of full_route_listing; 028 was chosen for having the
  most routes (18), making the "list per route" intent visually
  meaningful. Stage R2-1 60-case expansion may want to include
  several STRUCT/OC seeds.
- **carried to R2-1?** Closed by this revision.

### D-014 — Source-prompt-id backfill policy

- **case_id:** R2-008, R2-009, R2-010, R2-012, R2-014, R2-015
- **issue / disagreement:** Six R2-0 calibration cases had
  empty `source_prompt_id` cells and relied on the R2-1
  materializer's rationale-text inference (a regex that finds
  `prompt \d{3}` references in `payload_mutation_needed`) to
  locate a seed. The materializer warned about this on every
  inferred case, but the inference is fragile: a future labeller
  could mutate the rationale text and silently change which seed
  the case binds to. Reproducibility requires that every case bind
  to an explicit seed listed in a typed column.
- **resolution:** Backfill `source_prompt_id` for all six rows:
  - R2-008 → 046 (was inferred)
  - R2-009 → 032 (was inferred; rationale named 032 ambiguously)
  - R2-010 → 028 (was `skipped_no_seed`; see D-013)
  - R2-012 → 013 (was inferred)
  - R2-014 → 001 (was inferred)
  - R2-015 → 040 (was inferred)
  Rationale text was updated on every backfilled row to reflect
  the explicit seed and to record the R2-1 cleanup origin. The
  rationale-text inference path in the materializer remains in
  place (defence-in-depth for future synthetic cases) but is no
  longer exercised by any R2-0/R2-1 calibration row.
- **schema change made?** No — schema §1 already required
  `source_prompt_id` to be filled when a seed exists; R2-0 left it
  blank in violation of the spirit (though not the letter) of the
  schema. R2-1 closes the gap.
- **remaining ambiguity:** None for the 15-case calibration. For
  Stage R2-1 60-case expansion: the schema should consider
  requiring `source_prompt_id` to be non-empty for any case that
  is not purely synthetic, and adding a separate
  `payload_fixture_plan` field for truly-synthetic cases that
  cannot reuse a Run 1 seed (none today).
- **carried to R2-1?** Closed for the calibration set. Stage
  R2-1's 60-case expansion should formalise the
  "source_prompt_id is mandatory unless payload_fixture_plan is
  set" rule.

### D-010 — Calibration set size grew from 10 → 12 → 15

- **case_id:** n/a (planning-level)
- **issue / disagreement:** The original R2-0 scope stated 10
  calibration cases. The first R2-0 revision expanded to 12 (added
  PLAN_VALIDITY coverage). The second R2-0 revision expanded to 15
  (R2-002 split into R2-002 + R2-013, plus R2-014 missing_units and
  R2-015 false_premise_route).
- **resolution:** Calibration size is intentionally allowed to grow
  during the calibration stage — the purpose of R2-0 is to stress
  the schema, not to hit a target size. The current count (15) is
  the closing R2-0 number.
- **schema change made?** No.
- **remaining ambiguity:** Whether further calibration growth is
  warranted before R2-1, e.g. for multi-entity partial cases
  (D-001) or structural-false-premise cases (D-004). R2-0 ships
  with 15 and leaves those for R2-1.
- **carried to R2-1?** Yes. Stage R2-1 builds the 60-case
  benchmark; the calibration set is *not* part of the benchmark.

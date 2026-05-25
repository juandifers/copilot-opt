# R2-S Axis 2 — Out-of-Distribution False Premises and Comparators

_Frozen baseline: HEAD `18b4811` ("Run 2 contract extensions completed").
Authored 2026-05-21 under the shared R2-S methodology in
`product/evaluation/run2_stress/shared/`._

## 1. Axis definition

Axis 2 stresses the **contract layer that decides whether the user's
question is answerable at all**: false premises, unsupported movement
assumptions, missing comparators or baselines, and causal/explanatory
requests whose mechanism the payload does not record. The cases are not
paraphrases (Axis 3) and not look-alike intent attractors (Axis 1).
They are prompts whose premise is not supported by the payload and for
which the correct contract behavior is some shape of useful refusal,
partial answer, or warning — never a confidently-asserted answer.

For every Axis 2 case the gold contract response is authored against
the locked Run 2 schema (`product/evaluation/run2_gold_schema.md`).
Where the existing schema cannot express the most faithful refusal
shape, the case is graded against the **closest supported behavior**
and the gap is recorded in `ambiguity_notes` and §10 below.

## 2. Hypothesis (H-A2)

System C0 will partially generalize the Run 2 R2-3 contract extensions
(false-premise detection for entity-bound intents; comparison-referent
ambiguity for OBJ delta; `unsupported_comparison` for STRUCT/SCHEDULE
before-after questions) to out-of-distribution wordings within the
same mechanism. It will **fail** when:

- the false premise affects an intent C0 does not currently false-
  premise-check (e.g. `lateness_summary`, `feasibility_status`,
  `route_count`, `new_customer_assignment`);
- the unsupported movement or reassignment is expressed without the
  comparative tokens C0 looks for (`_COMPARATIVE_TOKENS`
  = changed | change | actually change | still | compared | different);
- the comparator is implicit or named with vocabulary outside
  `_AMBIGUOUS_REFERENT_PATTERNS` (full re-solve | run from scratch |
  optim* | reference solution | stronger solver);
- the question is causal in shape and the contract has no causal
  layer.

Expected diagnostic outcomes:

1. Some cases pass because R2-3 already built the useful-refusal /
   warning machinery the case exercises (Band 1's entity-bound
   subset; Band 2's comparative-token subset; Band 3's OBJ-delta
   ambiguous-referent subset; Band 4's missing-validity-fields case).
2. Some cases fail because C0 only detects narrower false-premise
   shapes (Band 1's non-entity-bound intents; Band 2's
   non-comparative wording; Band 3's implicit comparator; Band 4's
   "causal" `unknown` fallback).
3. Failures are classified by **contract layer** (intent classifier,
   entity-resolver, answerability, evidence, warning policy), not by
   intent alone, via the bucket taxonomy in §8.

The axis must answer: *Does C0 refuse or partially answer correctly
when the user's question assumes unsupported state?*

## 3. Exclusion criteria

Axis 2 must not include:

- simple paraphrases of supported intents (those are Axis 3);
- look-alike adjacent-intent attractors aimed at the keyword
  classifier (those are Axis 1);
- large payload retrieval stress (that is Axis 4);
- nonexistent entities used purely to confuse intent rather than to
  assert a false premise;
- vague natural-language questions for which no clear gold contract
  behavior can be written down without inventing schema values.

## 4. Case construction protocol

For every Axis 2 case:

1. Choose a locked Run 2 base case (the `base_case_id` column). Reuse
   its `source_prompt_id` and seed payload so the case materializes
   via the **unmodified** `run2_payloads.materialize_case_payload`
   path. The base case anchors payload reuse and traceability; the
   stress row deliberately diverges from the base case's gold to
   express the OOD premise.
2. Author the stress prompt so the user-side premise is not supported
   by the materialized payload (entity absent / comparator missing /
   movement diff absent / causal mechanism absent).
3. Set `payload_condition` to the existing Run 2 mutation code that
   most faithfully expresses the unsupported support:
   - `false_premise_customer` / `false_premise_route` (Bands 1 & 4);
   - `unsupported_comparison` (Bands 2 & 3);
   - `missing_reference_solution` (Band 3 OBJ-delta subset);
   - `missing_validity_fields` (Band 4 causal-PV subset);
   - `clean` only when the payload is genuinely intact and the gap
     is in the user's question, not in the payload.
4. Author the gold contract row from scratch — Axis 2 does NOT inherit
   gold verbatim from the base case (cf. Axis 1 / Axis 3, which do).
   Every gold field (`expected_intent`, `expected_answerability`,
   `expected_behavior_class`, `expected_evidence_paths`,
   `expected_missing_fields`, `expected_warnings`,
   `expected_next_actions`, `implementation_status`, `difficulty`,
   `label_rationale`) is set per the OOD case's correct contract
   behavior under the locked Run 2 schema.
5. Use **only** the enum values declared in
   `product/evaluation/run2_case_loader.py` (CURRENT/PROPOSED for
   intents/warnings/next_actions). The validator enforces this.
6. If the existing schema cannot express the most faithful refusal,
   pick the closest supported behavior and record the gap in
   `ambiguity_notes`.
7. Cases must not be paraphrases of Axis 1 or Axis 3 cases.

## 5. Four confusion bands

Six cases per band (3 dev + 3 heldout). The band name is the value of
the `band` and `ood_premise_band` columns.

### 5.1 `nonexistent_entity_false_premise`

The prompt names a customer ID or route number that the payload does
not contain. C0 detects this only when intent ∈ {`customer_arrival`,
`single_customer_route_membership`, `same_route_boolean`,
`route_end_time`} via `entity_resolution.prompt_references_unknown_*`.
For other intents (e.g. `lateness_summary`, `feasibility_status`), the
false-premise check is not applied — the contract may silently answer
against an unrelated answer-shape. This band probes both subsets.

Target behavior: `not_answerable`, `useful_refusal`, warnings include
`false_premise_detected`, next actions include `clarify_false_premise`.

### 5.2 `unsupported_movement_or_assignment_premise`

The prompt asserts that a customer was moved, reassigned, swapped, or
inserted, and asks about the prior state or the reassignment. The
referenced customer exists; the unsupported piece is the movement
itself. C0 routes the question to `before_after_comparison` only when
the wording contains comparative tokens; non-comparative wordings
route to `single_customer_route_membership` or `unknown` and the
movement premise is never surfaced.

Target behavior: `before_after_comparison` intent, `not_answerable`
under `payload_condition=unsupported_comparison`, `useful_refusal`,
warning `unsupported_comparison`, next action
`build_baseline_comparison_payload`. (Closest supported behavior under
the current schema; the schema has no movement-specific warning.)

### 5.3 `missing_comparator_or_baseline`

Comparison and before/after questions whose payload lacks the
comparator support. OBJ-delta with `missing_reference_solution` is the
canonical R2-3 detected shape. STRUCT/SCHEDULE before/after with
`unsupported_comparison` is the canonical R2-0 detected shape. The
band includes both detected shapes plus implicit-comparator wordings
that fall outside `_AMBIGUOUS_REFERENT_PATTERNS` (the `against the
optimum` / `versus the prior schedule` etc. tail).

Target behavior:
- OBJ-delta + ambiguous referent → `partial_answer_with_warning` with
  `comparison_referent_ambiguity` + `expose_reference_solution_objective`.
- STRUCT/SCHEDULE `before_after_comparison` + unsupported_comparison →
  `useful_refusal` with `unsupported_comparison` +
  `build_baseline_comparison_payload`.

### 5.4 `causal_or_explanatory_unsupported_premise`

`Why ...?` and `What caused ...?` prompts whose causal mechanism the
payload does not record. The contract has no causal layer, so the
faithful target behavior is one of:
- cite the available facts and let the operator infer (when the
  payload exposes the outcome that motivates the question, e.g.
  `Why is route 1 late?` against a payload with `late_customer_ids`);
- refuse with the closest supported next action when no outcome is
  cite-able (e.g. `Why is this plan infeasible?` with
  `missing_validity_fields`).

The band intentionally includes one case whose gold is `unknown` +
`useful_refusal` to anchor the "no causal layer; no available
sub-intent" shape; the rest pivot on whether the payload exposes the
outcome the question implicitly asks about.

## 6. Split policy

- `split = dev` for `A2D-NN`; `split = heldout` for `A2H-NN`.
- Three dev cases and three heldout cases per band.
- `dev` is the only split that may be iterated on; `heldout` is touched
  only for the final C0 closeout. No tuning of C0 (C0 is the frozen
  baseline; this axis does not modify it).
- The closeout reports per-split metrics so any gap between dev and
  heldout is visible.

## 7. Scoring policy

- Scoring reuses `run2_scoring.score_case` unchanged. Per-case
  component metrics: `intent_correct`, `answerability_correct`,
  `behavior_class_correct`, `evidence_precision`, `evidence_recall`,
  `warning_precision`, `warning_recall`, `missing_field_recall`,
  `useful_refusal_correct` (only where gold is `useful_refusal`),
  `partial_answer_correct` (only where gold is
  `partial_answer_with_warning`).
- Aggregation: overall, by split, by band. Cases whose gold is
  `useful_refusal` or `partial_answer_with_warning` are also summed
  separately in the closeout — Axis 2 is the axis where these
  conditional metrics matter most.
- Scatter rows conform to `shared/scatter_schema.md`:
  `axis=axis2_ood_premises`, `system=c0`, `band=ood_premise_band`
  (= cases.csv `band`), `intent=expected_intent`, `n_routes` and
  `payload_chars` from the materialized payload (null when not
  computable).

## 8. Expected failure taxonomy (buckets)

Mutually exclusive, exhaustive over scored cases. Each per-case result
is tagged with exactly one bucket.

- `correct_refusal_or_partial` — gold is `useful_refusal` or
  `partial_answer_with_warning`, and C0 produced the expected
  refusal/partial shape (`useful_refusal_correct == True` or
  `partial_answer_correct == True`).
- `missed_false_premise` — gold warnings include
  `false_premise_detected` and C0's predicted warnings do not.
- `missed_missing_comparator` — gold warnings include either
  `comparison_referent_ambiguity` or `unsupported_comparison`, and
  C0's predicted warnings do not.
- `over_answered_unsupported_premise` — gold is `useful_refusal` or
  `partial_answer_with_warning`, and C0 produced `direct_answer` or
  `direct_answer_with_warning` (i.e. answered confidently when the
  contract owed a refusal/partial).
- `wrong_intent` — `intent_correct == False` and predicted intent is
  not `unknown`. Failure mode dominates the case.
- `unknown_intent` — predicted intent is `unknown` and gold intent
  is not `unknown`.
- `downstream_evidence_mismatch` — intent and behavior class are
  correct, but `evidence_precision`, `evidence_recall`,
  `warning_precision`, `warning_recall`, or `missing_field_recall`
  is < 1.0.
- `schema_gap_or_unrepresentable_gold` — `ambiguity_notes` records
  that the case's most-faithful gold is not representable under the
  current Run 2 schema and was downgraded to a closest supported
  behavior. Tracked separately to keep the other buckets honest
  about scoring against the current schema.
- `guard_protected` (terminal positive bucket) — every metric is
  perfect and gold is not refusal/partial-shaped (i.e. the case is a
  Band 4 "answerable, cite facts" outcome that C0 handled correctly).

Bucket precedence (first matching wins):
`schema_gap_or_unrepresentable_gold` → `correct_refusal_or_partial`
→ `unknown_intent` → `wrong_intent` →
`over_answered_unsupported_premise` → `missed_false_premise` →
`missed_missing_comparator` → `downstream_evidence_mismatch` →
`guard_protected`.

## 9. Schema limitations

The current Run 2 schema cannot directly express:

- A *movement-specific* warning (e.g. "movement_premise_unsupported").
  Band 2 maps these to `unsupported_comparison` + `before_after_comparison`,
  the closest supported shape; `ambiguity_notes` records the gap.
- A *causal-mechanism-unsupported* warning. Band 4 maps these to
  `useful_refusal` (when no facts are available) or
  `direct_answer`/`direct_answer_with_warning` (when the outcome is
  cite-able and the causal aspect is implicitly unaddressed by the
  contract).
- A *reassignment-listing* intent. Band 2's "Which customers were
  reassigned away from Route 1?" maps to `before_after_comparison`
  as the closest supported behavior; `ambiguity_notes` flags this.

These limitations are explicit; the closeout's `schema_gap_*` bucket
counts them. Extending the schema would be a Stage R2-2 change and
is out of scope for this closeout.

## 10. System D scope note

System D, per `shared/system_d_design_envelope.md`, is bounded to the
**intent classifier and semantic intent adapter**
(`product/copilot/intent.py`). Axis 2 failures fall into three groups
with very different System D implications:

- **Intent-mediated failures** (e.g. Band 2's non-comparative wordings
  routing to `single_customer_route_membership` instead of
  `before_after_comparison`; Band 3's implicit-comparator wordings
  routing to `objective_value` instead of `objective_delta`): in
  scope for System D — a better intent adapter could route these
  correctly without touching the answerability/refusal layer.
- **Entity-resolution / answerability-policy failures** (e.g.
  Band 1's `lateness_summary` and `feasibility_status` not running
  the false-premise check): **out of scope** under the current
  System D envelope. Addressing them would require modifying
  `product/data/entity_resolution.py` or
  `product/data/answerability.py`, which is forbidden by the Axis 2
  hard constraints.
- **Schema-gap failures** (Bands 2 and 4 cases marked
  `schema_gap_or_unrepresentable_gold`): out of scope for System D
  entirely; future-work.

The closeout's "System D implication" section explicitly partitions
Axis 2 failures by these three groups so the scope question can be
answered honestly.

## 11. Out-of-scope future work

- Extend the schema with `movement_premise_unsupported`,
  `causal_mechanism_unsupported`, and `unserved_customer_listing` /
  `reassignment_listing` intents (Stage R2-2).
- Build false-premise checks for non-entity-bound intents
  (`lateness_summary`, `feasibility_status`, `route_count`,
  `new_customer_assignment`) — this is an answerability-policy
  change, not a System D change.
- Add B/A system runs on Axis 2 (deferred, mirror Axis 1/3 stubs).
- Cross-axis synthesis once Axes 1, 2, 3 (and ideally 4) are all
  closed for C0.

## 12. Frozen baseline commit

C0 metrics in this closeout are recorded against HEAD `18b4811`. Any
re-run on a different HEAD requires re-recording the metrics and is
not comparable to the figures in `reports/c0_baseline.md` or
`reports/axis2_closeout.md`.

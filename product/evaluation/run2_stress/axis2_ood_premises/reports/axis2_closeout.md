# R2-S Axis 2 Closeout — OOD False Premises and Comparators

_Status: **CLOSED for C0 baseline.** Frozen at HEAD `18b4811`
("Run 2 contract extensions completed"). Closeout authored
2026-05-21 under the shared methodology in
`product/evaluation/run2_stress/shared/`._

## 1. Purpose

Axis 2 tests whether System C0 — the deterministic contract layer at
`product/copilot/` and `product/data/` — produces the correct
**useful-refusal** or **partial-answer** shape when the operator's
question carries an unsupported premise. The unsupported piece is the
*user-side claim*: a customer or route that does not exist, a movement
or reassignment the payload does not record, a comparator with no
referent in the payload, or a causal "why" whose mechanism is not
captured anywhere in the contract's payload schema. Axis 2 is
deliberately distinct from semantic paraphrase (Axis 3) and look-alike
intent attractors (Axis 1).

## 2. Relationship to Axis 1 and Axis 3

- **Axis 3** tested *unseen wording* of supported intents → the
  failure mode was `unknown` fallback (9/24 unknown_intent).
- **Axis 1** tested *misleading familiar wording* with attractor
  tokens → the failure mode was confidently misrouted adjacent
  intent (3/24 wrong_adjacent_intent in the OBJ comparative subset).
- **Axis 2** tests *unsupported premises and comparators* → the
  failure mode is contract-shape: missed refusals, missed warnings,
  and intent misrouting on non-attractor wording. The contract layer
  itself is the system under test, not just the keyword classifier.

Together, the three axes give complementary failure-mode coverage:
unseen-vocabulary, attractor-tokens, and unsupported-premises.

## 3. Method

- **24 cases**, **12 dev / 12 heldout** via an explicit `split`
  column. No random sampling.
- **4 OOD-premise bands**: 6 cases each (3 dev + 3 heldout):
  - `nonexistent_entity_false_premise`
  - `unsupported_movement_or_assignment_premise`
  - `missing_comparator_or_baseline`
  - `causal_or_explanatory_unsupported_premise`
- **C0 only** for this closeout. Systems B / A are deferred — see §9.
- **No solver calls.** No optimization run.
- **No `product/copilot/*` or `product/data/*` modifications.**
- **No locked Run 2 files modified.**
- **Cases do NOT inherit gold verbatim from a base case** (a
  departure from Axes 1 and 3): each gold contract row is authored
  per case because Axis 2 deliberately mutates the user's premise.
  `base_case_id` is retained for payload-materialization
  traceability.
- **Payloads materialize from Run 1 seeds** via the locked
  `run2_payloads.materialize_case_payload(run_id='full-run-v1')`
  path.
- **Scoring reuses `run2_scoring.score_case`** unchanged.

Artefacts:

- `reports/c0_baseline.csv` — 24 per-case wide-form results with
  `bucket` column.
- `reports/c0_baseline.md` — human-readable summary.
- `reports/scatter.csv` — long-form per-case scatter; 240 rows =
  24 cases × 10 metrics; conforms to `shared/scatter_schema.md`.
- `reports/axis2_closeout.md` — this file.

## 4. Results

### 4.1 Overall (n = 24)

| Metric | Value |
|---|---:|
| `intent_correct` | **75.0%** (18 / 24) |
| `answerability_correct` | 75.0% (18 / 24) |
| `behavior_class_correct` | 75.0% (18 / 24) |
| `evidence_precision` | 83.3% |
| `evidence_recall` | 95.0% |
| `warning_precision` | 66.7% |
| `warning_recall` | 66.7% |
| `missing_field_recall` | 91.7% |
| `useful_refusal_correct` | **60.0%** (9 / 15 cases of class) |
| `partial_answer_correct` | **50.0%** (2 / 4 cases of class) |

### 4.2 By split

| Split | n | intent | ans | bc | ev p/r | warn p/r | miss r | useful_refusal | partial_answer |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | 12 | 83.3% | 75.0% | 75.0% | 83.3% / 95.0% | 75.0% / 75.0% | 91.7% | 71.4% (5/7) | 50.0% (1/2) |
| heldout | 12 | 66.7% | 75.0% | 75.0% | 83.3% / 95.0% | 58.3% / 58.3% | 91.7% | 50.0% (4/8) | 50.0% (1/2) |

### 4.3 By band

| Band | n | intent | ans | bc | ev p/r | warn p/r | miss r | useful_refusal | partial_answer |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `nonexistent_entity_false_premise` | 6 | 100% | 66.7% | 66.7% | 66.7% / 100% | 66.7% / 66.7% | 100% | 66.7% (4/6) | n/a |
| `unsupported_movement_or_assignment_premise` | 6 | 50.0% | 66.7% | 66.7% | 66.7% / 100% | 50.0% / 50.0% | 100% | 50.0% (3/6) | n/a |
| `missing_comparator_or_baseline` | 6 | 50.0% | 66.7% | 66.7% | 100% / 80.0% | 50.0% / 50.0% | 66.7% | 50.0% (1/2) | 50.0% (2/4) |
| `causal_or_explanatory_unsupported_premise` | 6 | 100% | 100% | 100% | 100% / 100% | 100% / 100% | 100% | 100% (1/1) | n/a |

## 5. Failure taxonomy

Mutually exclusive, exhaustive over all 24 cases. Bucket precedence
per `design.md` §8.

| Bucket | n |
|---|---:|
| `correct_refusal_or_partial` | **11** |
| `schema_gap_or_unrepresentable_gold` | **5** |
| `unknown_intent` | **2** |
| `wrong_intent` | **4** |
| `missed_false_premise` | **2** |
| `missed_missing_comparator` | 0 |
| `over_answered_unsupported_premise` | 0 |
| `downstream_evidence_mismatch` | 0 |
| `guard_protected` | 0 |

### 5.1 Per-band breakdown

| Band | correct | schema_gap | unknown_intent | wrong_intent | missed_false_premise |
|---|---:|---:|---:|---:|---:|
| `nonexistent_entity_false_premise` | 4 | 0 | 0 | 0 | 2 |
| `unsupported_movement_or_assignment_premise` | 3 | 0 | 1 | 2 | 0 |
| `missing_comparator_or_baseline` | 3 | 0 | 1 | 2 | 0 |
| `causal_or_explanatory_unsupported_premise` | 1 | 5 | 0 | 0 | 0 |

### 5.2 What each bucket means here

- **`correct_refusal_or_partial` (11)**: the gold was
  `useful_refusal` or `partial_answer_with_warning` and C0 produced
  the right refusal/partial shape (matching answerability, missing
  fields, and at least one canonical next action). Concentrated in
  the entity-bound subset of Band 1 (where R2-3's false-premise
  detection fires) and the comparative-token subset of Bands 2 and 3
  (where R2-0's `unsupported_comparison` / R2-3's
  `comparison_referent_ambiguity` fire), plus the Band 4
  `missing_validity_fields` case.

- **`schema_gap_or_unrepresentable_gold` (5)**: all 5 Band 4 cases
  whose most faithful gold would have included a
  `causal_mechanism_unsupported` warning the schema does not carry.
  Gold was downgraded to the closest supported behavior (cite the
  available facts as a normal `direct_answer` /
  `direct_answer_with_warning`). C0 produced the downgraded behavior
  perfectly (all five score 100% on every metric); the bucket is a
  methodological **notice that the schema does not let us grade the
  causal aspect**, not a system failure. See §9 for the gap list.

- **`unknown_intent` (2)**: A2H-06 (`Were any customers reassigned
  away from Route 1 in this update?`) and A2H-09 (`Did the route
  structure shift versus the prior schedule?`). Both prompts have no
  comparative token and no entity anchor, so STRUCT falls through
  every branch to `unknown`. The faithful gold is
  `before_after_comparison + useful_refusal`; C0's `unknown` fallback
  produces the wrong refusal shape (cites
  `narrow_question_to_available_field` instead of
  `build_baseline_comparison_payload`).

- **`wrong_intent` (4)**: A2D-06 / A2H-05 (Band 2, non-comparative
  movement wording routes to `single_customer_route_membership`);
  A2D-08 / A2H-08 (Band 3, implicit comparator wording routes OBJ
  to `objective_value` instead of `objective_delta`). All four are
  intent-classifier failures, not contract failures.

- **`missed_false_premise` (2)**: A2D-03
  (`lateness_summary` with phantom customer 9999) and A2H-02
  (`feasibility_status` with phantom customer 8888). C0's
  false-premise check is gated to `_CUSTOMER_BOUND_INTENTS`
  (`customer_arrival`, `single_customer_route_membership`,
  `same_route_boolean`) and `_ROUTE_BOUND_INTENTS`
  (`route_end_time`); `lateness_summary` and `feasibility_status` are
  not in either set, so the contract treats the question as
  answerable.

- **`missed_missing_comparator`, `over_answered_unsupported_premise`,
  `downstream_evidence_mismatch`, `guard_protected`**: zero in each.
  No case fell into these residual buckets — every detected failure
  was either intent-mediated, false-premise gating, or a schema gap.

### 5.3 Per-case failure rows

| case_id | split | band | bucket | gold intent → pred intent | gold cls → pred cls |
|---|---|---|---|---|---|
| A2D-03 | dev | `nonexistent_entity_false_premise` | `missed_false_premise` | lateness_summary → lateness_summary | useful_refusal → direct_answer |
| A2H-02 | heldout | `nonexistent_entity_false_premise` | `missed_false_premise` | feasibility_status → feasibility_status | useful_refusal → direct_answer |
| A2D-06 | dev | `unsupported_movement_or_assignment_premise` | `wrong_intent` | before_after_comparison → single_customer_route_membership | useful_refusal → direct_answer_with_warning |
| A2H-05 | heldout | `unsupported_movement_or_assignment_premise` | `wrong_intent` | before_after_comparison → single_customer_route_membership | useful_refusal → direct_answer_with_warning |
| A2H-06 | heldout | `unsupported_movement_or_assignment_premise` | `unknown_intent` | before_after_comparison → unknown | useful_refusal → useful_refusal |
| A2D-08 | dev | `missing_comparator_or_baseline` | `wrong_intent` | objective_delta → objective_value | partial_answer_with_warning → direct_answer |
| A2H-08 | heldout | `missing_comparator_or_baseline` | `wrong_intent` | objective_delta → objective_value | partial_answer_with_warning → direct_answer |
| A2H-09 | heldout | `missing_comparator_or_baseline` | `unknown_intent` | before_after_comparison → unknown | useful_refusal → useful_refusal |

## 6. Methodological interpretation

**Does C0's existing refusal machinery generalize beyond the R2-3
target extensions?**

Partially. The R2-3 false-premise extension correctly fires on
**every** OOD wording of an entity-bound intent (4/4 in Band 1 plus
the same_route_boolean heldout case). The R2-3
comparison_referent_ambiguity extension correctly fires on **every**
OBJ-delta prompt whose comparator vocabulary is in
`_AMBIGUOUS_REFERENT_PATTERNS` (2/2 detected in Band 3). The R2-0
`unsupported_comparison` warning correctly fires on **every**
before-after STRUCT prompt with a `_COMPARATIVE_TOKEN` (3/3 detected
in Band 2 plus 1/1 in Band 3). So inside the mechanisms R2-0 / R2-3
built, the generalization to OOD surface wording is robust.

The failures cluster outside those mechanisms:

1. **Non-entity-bound false premise (2 cases — `missed_false_premise`).**
   `lateness_summary` and `feasibility_status` have no false-premise
   check. The fix is to widen `_CUSTOMER_BOUND_INTENTS` in
   `product/data/answerability.py` and `product/copilot/refusal_policy.py`
   — an answerability/refusal-policy change.

2. **Implicit / non-tokenized comparator (4 cases — `wrong_intent`).**
   Wordings like `better than … optimum`, `rank against … stronger
   solver`, `where was customer X before`, `which route did customer X
   swap from` carry no token in `_COMPARATIVE_TOKENS`. The intent
   classifier routes them to `objective_value` or
   `single_customer_route_membership`, and the OBJ /
   `unsupported_comparison` checks never get a chance to fire. The fix
   is to widen the comparative-token set (or add a semantic intent
   adapter) in `product/copilot/intent.py` — **an intent-classifier
   change, in the System D envelope**.

3. **No-anchor STRUCT before/after (2 cases — `unknown_intent`).**
   Prompts whose only signal is implicit comparison (no comparative
   token, no entity number, no vehicle-count token) fall through to
   `unknown`. The fix is the same as (2) — widen the intent
   classifier — though here the wording is closer to Axis 3's
   unseen-vocabulary failure mode.

4. **Causal explanation (5 cases — `schema_gap_or_unrepresentable_gold`).**
   The schema has no `causal_mechanism_unsupported` warning. C0
   correctly cites the available facts (its current behavior is exactly
   the most faithful closest supported behavior), but the causal aspect
   of the question is implicitly unaddressed. No fix is possible
   without a schema change, which is outside the System D envelope.

Are failures mostly due to intent, entity resolution, missing-field
logic, or schema limitations? The mix is:

- Intent classifier: 6 cases (4 wrong_intent + 2 unknown_intent)
- Entity resolution / answerability policy: 2 cases
  (missed_false_premise)
- Schema gap (un-fixable under R2-1): 5 cases
- Correct contract behavior: 11 cases

## 7. System D implication

The System D envelope is bounded to the intent classifier and a
semantic intent adapter (`product/copilot/intent.py` plus a
prompted-LLM intent classifier). Under that envelope:

- **System-D-addressable failures (6 cases)**:
  - 4 wrong_intent failures (A2D-06, A2H-05 in Band 2; A2D-08, A2H-08
    in Band 3) — caused by missing comparative-token coverage; a
    better intent classifier routes these to
    `before_after_comparison` (Band 2) or `objective_delta` (Band 3)
    and the downstream contract layer produces the correct refusal /
    partial without any other change.
  - 2 unknown_intent failures (A2H-06, A2H-09) — same root cause; a
    better intent classifier maps the "shift / versus / prior /
    reassigned" wordings to `before_after_comparison`.

  If System D fixes all 6 of these, `correct_refusal_or_partial`
  rises from 11/24 → 17/24 and the remaining failures are entirely
  outside the System D envelope.

- **Out-of-envelope failures (2 cases)**:
  - 2 missed_false_premise (A2D-03, A2H-02) — addressing these
    requires modifying `product/data/answerability.py` and
    `product/copilot/refusal_policy.py` to widen the false-premise
    check to `lateness_summary` and `feasibility_status` (or to all
    intents). This is an answerability-policy change, not an intent
    change, and is **explicitly outside** the current System D
    envelope per `shared/system_d_design_envelope.md`.

- **Future-work / un-fixable under R2-1 (5 cases)**:
  - All 5 schema_gap cases in Band 4 — fixing them requires adding a
    `causal_mechanism_unsupported` warning or a causal-explanation
    sub-intent to the schema, which is a Stage R2-2 change.

The net implication: **Axis 2 reveals one set of failures that System
D can address (the 6 intent-mediated cases) and two sets that it
cannot (the 2 answerability-policy cases and the 5 schema-gap cases).**
The closeout owner can decide whether to broaden the System D envelope
to cover the answerability-policy fix, but Axis 2 alone does not
mandate doing so.

## 8. Status

**Axis 2 is CLOSED for the C0 baseline at HEAD `18b4811`.**

- 24/24 cases scored.
- Scatter validates against `validate_scatter_schema` and
  `validate_metric_names` with zero errors.
- No protected files modified.
- All locked Run 2 tests and Axis 1 / Axis 3 / shared methodology
  tests continue to pass.

## 9. Deferred

- **Systems B and A.** Mirror the Axis 1 / Axis 3 deferral. Optional
  for the Axis 2 closeout; can be wired through
  `run2_model_baseline_runner.py`.
- **System D run.** Not built yet. When built, the closeout's
  System-D-addressable cohort (6 cases) is the explicit target.
- **Schema R2-2 extension**: `causal_mechanism_unsupported` warning,
  `unserved_customer_listing` / `reassignment_listing` intent,
  widened false-premise check. Not in scope for this closeout.
- **Cross-axis synthesis.** Once Axis 4 is closed, a unified
  scatter-driven analysis across Axes 1, 2, 3, 4 will let us state
  the overall contract-layer coverage cleanly.

## 10. Recommended next axis

**Axis 4 — Payload Stress.** The Axis 4 module is already
scaffolded under `product/evaluation/run2_stress/axis4_payload/`
with cases authored. Closing Axis 4 against C0 gives the fourth
orthogonal probe (payload scale rather than language; entity-bounded
behaviour under stress). After Axis 4 is closed for C0, the
cross-axis joint analysis becomes the natural next step.

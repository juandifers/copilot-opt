# R2-S1 — Semantic Intent Stress (Axis 3)

_Stress-test split that probes whether the VRPTW copilot's front-door
intent classifier maps semantically equivalent but lexically held-out
operator language to the correct canonical intent. Sibling of the locked
Run 2 contract benchmark, not a replacement for it._

Frozen-baseline commit: **`18b4811`** ("Run 2 contract extensions
completed"). C0 scoring on the stress split must verify HEAD before
running and the runner records HEAD into the per-run CSV.

## 1. Purpose

Run 2's locked benchmark (`product/evaluation/run2_benchmark_cases.csv`)
uses operator-style prompts whose surface form was authored alongside
the deterministic intent classifier in `product/copilot/intent.py`. A
copilot that *appears* to handle the four claim families on Run 2 can
still be brittle when an operator phrases the same question in
different words.

R2-S1 isolates the **language-to-intent mapping** problem. Each case
is a paraphrase of an existing Run 2 case with the **same canonical
intent** and the **same payload condition**. The expected contract
response (answerability, evidence paths, missing fields, warnings,
next actions, behavior class) is inherited from the base case; only
the prompt text changes.

The stress split tests one hypothesis and only one hypothesis:

> **H-S1.** Under semantically equivalent but lexically held-out
> operator language, a deterministic-prior contract system with
> keyword-level intent detection (`System C0`) loses intent accuracy
> relative to its Run 2 score. The downstream component metrics
> (answerability, evidence, warnings) are conditioned on intent being
> correct; their conditional accuracies should remain stable.

R2-S1 does **not** test: lookalike intents (axis 1), false
premises (axis 2), large-context payloads (axis 4), causal/explanation
questions, multi-turn dialog, or solver validity.

## 2. Scope and guardrails

This split is a diagnostic, not a benchmark replacement.

1. **No locked Run 2 file is modified.** `run2_benchmark_cases.csv`,
   `run2_gold_schema.md`, `run2_scoring.py`, `run2_case_loader.py`,
   `run2_payloads.py`, and `run2_system_c.py` remain at
   commit `18b4811`. The stress runner imports them.
2. **No `product/copilot` or `product/data` logic is changed.** The
   goal is to *measure* C0's intent fragility, not to patch it. Any
   future C1/D semantic-intent adapter is a separate task.
3. **No one-off keywords added to C0.** Forbidden under (2).
4. **No tuning on heldout.** The 12 heldout cases are sequestered.
   Iteration on C0 or a future C1/D may consume `dev` only.
5. **No solver calls.** Payloads are materialized from Run 1 generator
   JSONL via `run2_payloads.materialize_case_payload`, identical to
   the locked-benchmark path.
6. **Not a user study.** All gold labels are author-derived from the
   base Run 2 case. No operator validation is claimed.
7. **Not evidence of broad generalization.** The case count is
   deliberately small (24); any positive result is suggestive, not
   conclusive.

## 3. Case design

### 3.1 Inventory

24 cases total, split 12/12 between `dev` and `heldout`. All cases
have `stress_axis = semantic_intent` and one of the following
`stress_subtype` values:

| Subtype | Operational meaning |
|---|---|
| `cost_synonym` | Replaces "cost" / "objective" with a domain synonym ("score", "value the optimizer assigns", "how expensive"). |
| `feasibility_synonym` | Replaces "feasible" / "valid plan" with a domain synonym ("can be driven", "executable", "carried out"). |
| `entity_synonym` | Replaces "route" / "customer" with operator synonyms ("vehicle", "truck", "run"). |
| `schedule_synonym` | Replaces "finish", "end time", or "late" with a domain synonym ("close out", "complete its run", "done for the day", "miss promised window"). |
| `operator_colloquial` | Operator-style phrasing that has no canonical surface form ("Where did customer N get placed?", "Which customers fall behind schedule?"). |
| `paraphrase` | General lexical paraphrase that does not fit a tighter subtype ("Show me every route", "List the complete route plan"). |
| `synonym` | Reserved for axis-internal synonyms not covered above. Unused at R2-S1 baseline; the loader still accepts it. |

### 3.2 Coverage by canonical intent

| Canonical intent | n dev | n heldout |
|---|---|---|
| `objective_value` | 1 | 2 |
| `feasibility_status` | 2 | 2 |
| `single_customer_route_membership` | 3 | 2 |
| `full_route_listing` (target_extension) | 1 | 2 |
| `route_end_time` | 2 | 2 |
| `customer_arrival` | 1 | 1 |
| `lateness_summary` | 2 | 1 |
| **Total** | **12** | **12** |

`objective_delta` is not in the stress split because every Run 2
`objective_delta` case carries a comparator-induced
`comparison_referent_ambiguity` warning or a baseline-shape mutation;
paraphrasing the comparator surface form mixes the semantic-intent
question with the OBJ escape-hatch question. Axis-internal isolation
matters more than coverage of every Run 2 intent.

`route_count` is omitted for the same reason in reverse: the existing
matcher already accepts `"how many routes"`, `"how many vehicles"`,
and `"how many trucks"`, so meaningful paraphrase variants would
collapse onto the matcher and not exercise the stress axis.

### 3.3 Gold-label provenance

Every stress case inherits the locked Run 2 gold labels for:

- `expected_answerability`
- `expected_evidence_paths`
- `expected_missing_fields`
- `expected_warnings`
- `expected_next_actions`
- `expected_behavior_class`

…from its `base_case_id`. The CSV records `base_case_id` explicitly
so the inheritance is auditable. The only fields the stress author
changes are `prompt_text` and the stress-metadata columns
(`stress_axis`, `stress_subtype`, `split`, `base_case_id`,
`canonical_prompt`, `paraphrase_notes`, `forbidden_keywords_removed`).

`canonical_prompt` records the base case's original prompt verbatim,
so the lexical diff between canonical and stress is auditable in one
CSV cell.

`forbidden_keywords_removed` is a `;`-separated list of base-case
tokens the stress prompt drops. The list is descriptive, not
prescriptive: it documents what makes the stress prompt
lexically distinct.

### 3.4 Implementation status

For stress cases targeting `current` canonical intents, the row's
`implementation_status` is `current`. The fact that the *current*
contract may misclassify a paraphrase is the diagnostic the stress
split surfaces; it is not a target-extension extension of the
contract.

Stress cases targeting `full_route_listing` are `target_extension`,
matching the locked benchmark's convention for that proposed intent
(`run2_gold_schema.md` §3.2 / §13).

### 3.5 Entity validity

Every stress case that names a customer ID or a route number reuses
an entity that is **present in the base case's seed payload**.
Concretely:

- Customer 42 in `S1D-04`, `S1D-05`, `S1D-10`, `S1H-05`, `S1H-11`
  inherits from base cases R2-004 / R2-039 / R2-007 / R2-041 / R2-056,
  each of which already references customer 42 against a payload that
  contains it.
- Customer 17 in `S1D-06`, `S1H-11` inherits from R2-040 / R2-056.
- Customer 12 in `S1H-06` inherits from R2-045.
- Route 1 in `S1D-08`, `S1D-09`, `S1H-09`, `S1H-10` inherits from
  the route-end-time base cases R2-055 / R2-060, both of which
  reference "Route 1" / "route 1" against a payload whose
  `route_end_times[]` includes a route with `route_idx=0`.

No stress case introduces a customer or route ID that the base
case's seed payload does not already certify.

## 4. CSV schema

The stress CSV extends `run2_gold_schema.md` §1's 17-column gold
schema with **9 stress-metadata columns**, appended after the gold
columns. The full 26-column header is:

```
case_id, source_prompt_id, family, prompt_text, payload_condition,
payload_mutation_needed, expected_intent, expected_answerability,
expected_evidence_paths, expected_missing_fields, expected_warnings,
expected_next_actions, expected_behavior_class, implementation_status,
difficulty, label_rationale, ambiguity_notes,
stress_axis, stress_subtype, split, base_case_id, base_family,
canonical_prompt, paraphrase_notes, forbidden_keywords_removed, notes
```

Column-by-column:

| Column | Type | Notes |
|---|---|---|
| `case_id` | str | `S1D-NN` for dev (NN = 01..12) or `S1H-NN` for heldout (NN = 01..12). Unique within the file. |
| `source_prompt_id` | str | Inherited from `base_case_id`'s row. Used by the payload materializer. |
| `family` | enum | Inherited from base case. Drives the intent classifier's family branch. |
| `prompt_text` | str | The **stress** paraphrase. |
| `payload_condition` | enum | Inherited from base case; almost always `clean`. |
| `payload_mutation_needed` | str | Inherited from base case. |
| `expected_intent` | enum | Inherited from base case. |
| `expected_answerability` | enum | Inherited from base case. |
| `expected_evidence_paths` | `;`-list | Inherited from base case. |
| `expected_missing_fields` | `;`-list | Inherited from base case. |
| `expected_warnings` | `;`-list | Inherited from base case. |
| `expected_next_actions` | `;`-list | Inherited from base case. |
| `expected_behavior_class` | enum | Inherited from base case. |
| `implementation_status` | enum | `current` for current-contract intents; `target_extension` only for `full_route_listing`. |
| `difficulty` | enum | Inherited from base case, capped at `medium` (stress paraphrasing is a separate axis from base difficulty). |
| `label_rationale` | str | Re-stated for the stress row: "Paraphrase of `<base_case_id>`; inherits gold contract response." plus subtype-specific note. |
| `ambiguity_notes` | str | Records expected C0 failure modes (e.g. "C0 returns `unknown` because `'close out'` is not in the SCHEDULE matcher token set"). |
| `stress_axis` | const | Always `semantic_intent` in this file. |
| `stress_subtype` | enum | One of the §3.1 values. |
| `split` | enum | `dev` or `heldout`. |
| `base_case_id` | str | The R2-NNN base case the stress row paraphrases. Must exist in the locked benchmark. |
| `base_family` | str | Mirror of `family`. Carried explicitly so a future cross-axis joint loader does not have to re-resolve the base case to know which Run 2 family the stress row inherits from. |
| `canonical_prompt` | str | The base case's original prompt text. |
| `paraphrase_notes` | str | One-line description of the lexical change. |
| `forbidden_keywords_removed` | `;`-list | Base-case tokens this stress prompt deliberately drops. |
| `notes` | str | Free-text overflow. |

CSV encoding rules mirror the locked-benchmark contract (schema §11):
`pd.read_csv(path, keep_default_na=False, dtype=str)`; multi-value
columns use `;`.

## 5. Loader contract

`product/evaluation/run2_stress/axis3_semantic/loader.py` exposes:

- `Run2StressCase` — dataclass mirroring `Run2Case` with the
  additional stress-metadata fields.
- `load_stress_cases(path)` — reads the CSV with the 26-column reader
  contract; validates the extended schema.
- `validate_all_stress_cases(cases)` — returns a `ValidationReport`
  with per-case errors and aggregate distributions.

Schema validation runs the locked `validate_case` from
`run2_case_loader.py` on the 17 gold columns, **plus** stress-only
checks:

- `case_id` matches `^S1[DH]-\d{2}$`.
- Exactly 24 cases, 12 dev, 12 heldout.
- `stress_axis == "semantic_intent"` for every row.
- `stress_subtype` ∈ allowed §3.1 values.
- `split` ∈ `{dev, heldout}`.
- `base_case_id` ∈ the locked Run 2 benchmark.
- The stress row inherits `expected_intent`, `family`,
  `payload_condition`, `expected_answerability`, `expected_evidence_paths`,
  `expected_missing_fields`, `expected_warnings`,
  `expected_next_actions`, `expected_behavior_class` **identically**
  from the named `base_case_id`. A mismatch is a loader error — the
  stress split is defined to inherit the gold contract response.
- All `expected_*` enum values are valid under the locked
  `run2_case_loader` enums. (No new intents, warnings, or next
  actions are introduced by the stress split.)

## 6. Runner contract

`runner.py` is a thin orchestration layer:

1. `load_stress_cases(cases.csv)` and assert HEAD == `18b4811`.
2. For each case, call
   `run2_payloads.materialize_case_payload(case, run_id='full-run-v1')`.
   `MaterializedPayload.materialization_status == 'materialized'` is
   required for scoring; the runner records skips but does not silently
   drop them.
3. For System C0: call
   `run2_system_c.run_system_c_on_materialized(case, mat)` to obtain a
   `PredictedContract`.
4. Score with `run2_scoring.score_case(case, pred)`.
5. Emit a per-case CSV (`reports/c0_baseline.csv`) and a Markdown
   summary (`reports/c0_baseline.md`).

Systems B and A are out of scope for the R2-S1 baseline runner:
they require live API keys, network access, and re-using the
existing `run2_model_baseline_runner.py` CLI with a stress-CSV
adapter. Hooks are left in `runner.py` (`run_system_b`, `run_system_a`)
as `NotImplementedError` stubs to make the next-step extension
shape obvious without committing dead code.

## 7. Report contract

`report.py` aggregates a list of `CaseScore` records into:

1. **Overall** metrics on all 24 cases.
2. **By split**: `dev` vs `heldout` vs `overall`.
3. **By stress_subtype**: one row per subtype.
4. **Conditional on intent correct**: among cases where
   `intent_correct`, report answerability accuracy, behavior-class
   accuracy, evidence precision/recall, warning precision/recall.
   This separates language-mapping failures from downstream contract
   failures.
5. **Per-case failure rows**: every case where `intent_correct ==
   False` or `behavior_class_correct == False`, listing the
   gold/predicted pair and a short note.

Metrics reused verbatim from `run2_scoring.py`:
`intent_accuracy`, `answerability_accuracy`,
`behavior_class_accuracy`, `evidence_precision`,
`evidence_recall`, `warning_precision`, `warning_recall`,
`missing_field_recall`, `useful_refusal_correct_rate`,
`partial_answer_correct_rate`.

R2-S1-specific aliases / aggregations:

- `semantic_intent_accuracy` — alias of `intent_accuracy` for this
  axis; flagged distinctly in the report so the reader does not
  confuse it with Run 2's overall intent accuracy.
- `downstream_accuracy_given_intent_correct` — the conditional table
  in §7.4.
- `by_split` and `by_stress_subtype` slices — additional aggregation
  axes beyond `run2_scoring.aggregate_scores`' built-in slices.

## 8. Tests

`tests/run2_stress/axis3_semantic/test_axis3_semantic.py` covers:

1. CSV loads successfully and 26-column header is exactly the
   schema declared above.
2. All 24 case_ids are unique and match the `S1[DH]-NN` regex.
3. `stress_axis == "semantic_intent"` for all rows.
4. `split` ∈ `{dev, heldout}` with exact 12/12 counts.
5. Every `base_case_id` exists in `run2_benchmark_cases.csv`.
6. Every stress row inherits its base case's gold contract response.
7. All payloads materialize (`materialization_status ==
   "materialized"`) under `run_id='full-run-v1'`.
8. `run_system_c_on_materialized` returns a `PredictedContract` for
   every case.
9. `score_case` returns a `CaseScore` for every case.
10. `report.aggregate_axis3(scores, cases)` emits CSV and Markdown
    artifacts without raising.

The existing Run 2 test suite is preserved unchanged; no test in
`tests/test_run2_*.py` is modified by this axis.

## 9. Future work (deferred, not part of R2-S1 baseline)

These are recorded here so the next stage has a concrete shape:

- **C1 semantic-intent adapter.** Replace the `intent.py` keyword
  matchers with a deterministic synonym lookup over a canonical
  query frame ({objective_value, feasibility_status,
  customer_route_membership, full_route_listing, route_end_time,
  customer_arrival, lateness_summary}). Each canonical frame
  carries a synonym set (`vehicle`, `truck`, `run` → route;
  `close out`, `finished`, `done for the day` → route_end_time;
  …) and an entity resolver that maps surface forms to payload IDs.
- **System D.** Pair a model-based intent classifier with the
  deterministic answerability / evidence contract. The semantic
  adapter is the front door; the back-end contract remains the
  audit layer.
- **Heldout discipline.** Any C1/D iteration on the dev split must
  freeze the heldout split before publishing a heldout score.
  The recommended discipline is: tag the dev-iteration commit, run
  heldout once at that tag, and record the score against the tag.

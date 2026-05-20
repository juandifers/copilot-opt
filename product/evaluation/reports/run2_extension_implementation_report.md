# Run 2 — Stage R2-3 extension implementation report

This report records the implementation of the six planned target-extension
behaviours surfaced by the R2-2 60-case benchmark. The benchmark is the
deterministic instrument; this stage closes the policy backlog one
extension family at a time and verifies, after each one, that the
`current` rows remain regression-clean and that lift is restricted to the
intended `target_extension` partition.

No model calls, no solver runs, no locked-experiment-file modifications.

---

## 1. Files modified

### Stage 2 product code (intentional contract surface changes)

- `product/copilot/contracts.py` — added `full_route_listing` to the
  `Intent` literal (STEP 3).
- `product/copilot/intent.py` — added `_is_full_route_listing` matcher
  ahead of `_is_about_new_customer_assignment` so roster-per-route
  questions are not hijacked by the new-customer subject heuristic
  (STEP 3).
- `product/copilot/refusal_policy.py` —
  - extended `_NEXT_ACTION_BY_FIELD` with four R2-3 semantic codes:
    `feasible`/`feasibility_breakdown` → `use_validity_payload`,
    `units.objective` → `expose_units_objective`,
    `reference_solution.objective` → `expose_reference_solution_objective`
    (STEPS 1, 2, 6);
  - added `evidence_units_missing` warning emission for OBJ
    value/delta with missing `units.objective` (STEP 2);
  - added `false_premise_detected` warning + suppression of
    `route_indexing_ambiguity` / `struct_membership_ambiguity` when it
    fires (STEPS 4–5);
  - added `comparison_referent_ambiguity` warning emission when the
    answerability layer has flagged `reference_solution.objective` as
    missing on an OBJ delta question (STEP 6);
  - extended `build_useful_refusal(payload, prompt_text)` to compose a
    false-premise-aware reason string and prepend `clarify_false_premise`
    to the suggested actions when applicable (STEPS 4–5).
- `product/copilot/response_builder.py` — pass `payload` and
  `prompt_text` through to `build_useful_refusal` so the production
  orchestrator gets the same false-premise treatment as the System C
  adapter.
- `product/data/answerability.py` —
  - added `full_route_listing` to `_REQUIRED_FIELDS` with
    `routes[].customer_ids` (STEP 3);
  - added false-premise override that flips status to `not_answerable`
    with empty `missing_fields` when the prompt names an unknown
    customer or route (STEPS 4–5, schema §12);
  - added comparison-referent override that adds
    `reference_solution.objective` to `missing_fields` and demotes
    status from `answerable` to `partially_answerable` when an
    objective_delta prompt names an ambiguous comparator and the
    reference field is absent (STEP 6).
- `product/data/evidence.py` —
  - added `_evidence_full_route_listing` builder (STEP 3);
  - added a false-premise short-circuit at the dispatcher (so the
    contract does not cite stale evidence about the seed prompt's
    customer when the rewritten prompt names a non-existent one);
  - gated `_evidence_feasibility` behind the presence of a primary
    feasibility field (`feasible` or `feasibility_breakdown`) so
    supplementary diagnostics are not surfaced as standalone evidence
    when feasibility itself cannot be reported.
- `product/data/entity_resolution.py` (**new**) — pure helpers shared
  between answerability and refusal layers:
  `available_customer_ids`, `prompt_customer_ids`,
  `prompt_references_unknown_customer`,
  `unknown_customer_ids_from_prompt`, the analogous route trio, and
  `prompt_has_ambiguous_comparison_referent` for STEP 6.

### Run 2 evaluation tests

- `tests/test_run2_system_c.py` — flipped three R2-1-era assertions
  that pinned pre-extension baseline divergence (R2-008 false-premise
  not emitted; R2-010 intent not `full_route_listing`; R2-013
  comparator-ambiguity not emitted) to instead assert that the
  contract now emits the target-extension behaviour. The tests were
  renamed to mark the R2-3 transition and now serve as positive
  regression guards.

### Files **not** modified

- `experiment/configs/*`, `experiment/data/*` — locked at
  `preregistration-v1.1` / `preregistration-prompts-v1`; mtimes
  unchanged (all pre-2026-05-20).
- `product/evaluation/run2_benchmark_cases.csv`, the calibration CSV,
  and the gold schema — gold labels are unchanged. No label bug was
  discovered during R2-3.

---

## 2. Extension families implemented

| # | Extension | Target cases | Implementation surface |
|---|---|---|---|
| 1 | `use_validity_payload` next action | R2-012, R2-032, R2-033, R2-034, R2-035, R2-036 | `refusal_policy._NEXT_ACTION_BY_FIELD` |
| 2 | `evidence_units_missing` + `expose_units_objective` | R2-014, R2-021, R2-022, R2-023 | `refusal_policy.build_warnings` + next-action mapping |
| 3 | `full_route_listing` intent + evidence | R2-010, R2-048, R2-049 | `contracts.Intent`, `intent.py`, `answerability._REQUIRED_FIELDS`, `evidence._evidence_full_route_listing` |
| 4 | `false_premise_detected` + `clarify_false_premise` (customer) | R2-008, R2-047, R2-058 | `entity_resolution`, `answerability` override, `refusal_policy` warning + reason, `evidence` short-circuit |
| 5 | `false_premise_detected` + `clarify_false_premise` (route) | R2-015, R2-059 | same plumbing as #4 with route helpers (`prompt_references_unknown_route`) |
| 6 | `comparison_referent_ambiguity` + `expose_reference_solution_objective` | R2-013, R2-024, R2-025 | `entity_resolution.prompt_has_ambiguous_comparison_referent`, `answerability` referent override, `refusal_policy` warning |

Extensions were implemented one at a time, with the 60-case benchmark
re-run after each step (see §5 for the per-step lift table).

---

## 3. Before / after target-extension metrics

| Metric | C-current (R2-2 baseline) | C-extended (R2-3) |
|---|---:|---:|
| n | 21 | 21 |
| intent_accuracy | 0.857 | **1.000** |
| answerability_accuracy | 0.476 | **1.000** |
| behavior_class_accuracy | 0.476 | **1.000** |
| evidence_precision | 0.429 | **1.000** |
| evidence_recall | 0.857 | **1.000** |
| missing_field_recall | 0.857 | **1.000** |
| warning_precision | 0.381 | **1.000** |
| warning_recall | 0.429 | **1.000** |
| useful_refusal_correct_rate | 0.000 (0/11) | **1.000 (11/11)** |
| partial_answer_correct_rate | 0.000 (0/7) | **1.000 (7/7)** |

All 21 `target_extension` cases pass under C-extended. Zero residual
extension gaps.

---

## 4. Current-row regression check

| Metric | C-current (R2-2 baseline) | C-extended (R2-3) | Δ |
|---|---:|---:|---:|
| n | 39 | 39 | 0 |
| intent_accuracy | 1.000 | 1.000 | 0 |
| answerability_accuracy | 1.000 | 1.000 | 0 |
| behavior_class_accuracy | 1.000 | 1.000 | 0 |
| evidence_precision | 0.969 | 0.969 | 0 |
| evidence_recall | 1.000 | 1.000 | 0 |
| missing_field_recall | 1.000 | 1.000 | 0 |
| warning_precision | 1.000 | 1.000 | 0 |
| warning_recall | 1.000 | 1.000 | 0 |
| useful_refusal_correct_rate | 1.000 (7/7) | 1.000 (7/7) | 0 |

**Current-row failures: 0 → 0.** No regressions on any of the 39
`current` rows. The R2-2 evidence_precision baseline (0.969) is
preserved verbatim.

---

## 5. Per-step lift (target_extension partition)

Each row reports the state of the benchmark **after the named step**.
The "remaining failures" column is the number of `target_extension`
cases still failing on any component metric immediately after that
step.

| Step | Extension | Cases lifted | Remaining failures | useful_refusal_correct | partial_answer_correct |
|---|---|---|---:|---:|---:|
| 0 | (baseline) | — | 21 | 0/11 | 0/7 |
| 1 | `use_validity_payload` | R2-012, R2-032..R2-036 | 15 | 6/11 | 0/7 |
| 2 | `evidence_units_missing` + `expose_units_objective` | R2-014, R2-021, R2-022, R2-023 | 11 | 6/11 | 4/7 |
| 3 | `full_route_listing` | R2-010, R2-048, R2-049 | 8 | 6/11 | 4/7 |
| 4 | `false_premise_detected` (customer) | R2-008, R2-047, R2-058 | 3 | 9/11 | 4/7 |
| 5 | `false_premise_detected` (route) | R2-015, R2-059 | 3* | 11/11 | 4/7 |
| 6 | `comparison_referent_ambiguity` | R2-013, R2-024, R2-025 | 0 | 11/11 | 7/7 |
| 6+ | precision clean-up (false-premise dominance + feasibility evidence gating) | — | 0 | 11/11 | 7/7 |

*STEP 5 was a no-op in code: the route false-premise helpers were
already built alongside the customer ones in STEP 4 (the
`entity_resolution.prompt_references_unknown_route` path was
added concurrently with the customer path), so STEP 4 already
resolved both R2-015 and R2-059. STEP 5 is recorded as the
verification point.

After STEP 6, the target_extension partition was clean on every
component metric but evidence_precision (0.571) and warning_precision
(0.929). Investigation showed two purely-precision issues that were
already encoded in the gold:

- 6 PV refusal cases (R2-012, R2-032..R2-036) cited `infeasibility_kind`
  as supplementary evidence even when both primary feasibility fields
  were stripped. Gold says no evidence when feasibility itself cannot
  be answered. Fix: gate `_evidence_feasibility` behind the presence
  of a primary field.
- 2 SCHEDULE false-premise cases (R2-008, R2-058) cited the
  *seed prompt's* customer (e.g., customer 42 for the R2-008 prompt
  that names customer 999) because the Run 1 generator record's
  `claimed_customer_timings` overrode the prompt-parsed target. Gold
  says no evidence when the named entity is a false premise. Fix:
  short-circuit the evidence dispatcher when
  `prompt_references_unknown_customer` is true.
- 3 cases (R2-015, R2-047, R2-059) co-emitted
  `route_indexing_ambiguity` or `struct_membership_ambiguity` with
  `false_premise_detected`. Gold says false-premise dominates. Fix:
  drop those two warnings from the warning list when
  `false_premise_detected` is present.

These three precision fixes do not introduce new contract behaviour —
they enforce the same gold-aligned policy as the earlier steps. After
them, target_extension precision joins recall at 1.000.

---

## 6. Unexpected metric changes

None. All metric changes on the `target_extension` partition
correspond to a planned extension; all metric values on the `current`
partition are unchanged from the R2-2 baseline. There is no case where
a step touched a row outside its target list.

---

## 7. Remaining gaps

None. Every `target_extension` case in the 60-row benchmark scores
1.0 on every component metric. The R2-2 backlog is fully resolved.

The remaining `current`-row evidence_precision of 0.969 is **not** an
R2-3 issue — it is the R2-2 baseline figure (one current case emits a
single extra evidence field beyond gold) and is documented in the
R2-2 benchmark expansion report.

---

## 8. Tests run and passing

- `python3 -m pytest tests/test_run2_*.py -q` — **103 passed**.
- `python3 -m product.evaluation.run2_evaluate_calibration --cases
  product/evaluation/run2_benchmark_cases.csv --system C --report-stem
  run2_benchmark_eval_system_c_extended` — 60/60 materialized, 0
  schema errors, 0 current-row failures, 0 target_extension failures.

Three R2-1-era assertions in `tests/test_run2_system_c.py` that pinned
pre-extension contract divergence were flipped to assert the post-R2-3
contract behaviour. The renamed tests now serve as forward-direction
regression guards:

- `test_R2_008_false_premise_emits_warning_after_R2_3_extension`
- `test_R2_010_full_route_listing_routes_correctly_after_R2_3_extension`
- `test_R2_013_comparison_referent_emits_warning_after_R2_3_extension`

The R2-2 expansion-gate test
(`test_benchmark_current_rows_score_perfectly_on_component_metrics`)
continues to pass and would have flagged any current-row regression in
intent / answerability / behavior_class / evidence_recall /
warning_recall.

Pre-existing failures in `tests/test_answerability.py` and other
Stage 2 test files are infrastructure issues (those tests expect
`experiment/results/joined/full-run-v1.csv`, a path that was renamed
to `experiment/results_RUN1/...` before Stage R2-1) and are unrelated
to R2-3 contract changes.

---

## 9. Confirmation: no locked experiment files modified

```
$ stat -f "%Sm %N" -t "%Y-%m-%d %H:%M" experiment/configs/*.{json,md} experiment/data/*.csv
2026-05-19 00:47  experiment/configs/generator_output_schema.json
2026-05-19 00:47  experiment/configs/judge_output_schema.json
2026-05-18 17:22  experiment/configs/payload_schemas.json
2026-05-19 00:51  experiment/configs/cost_warmup_note.md
2026-05-19 01:39  experiment/configs/payload_schemas_rationale.md
2026-05-19 00:50  experiment/configs/pilot_protocol.md
2026-05-19 01:37  experiment/configs/rubric.md
2026-05-19 00:49  experiment/configs/stratification.md
2026-05-19 00:49  experiment/configs/success_criteria.md
2026-05-19 01:38  experiment/configs/synthetic_templates.md
2026-05-19 00:50  experiment/configs/verification_protocol.md
2026-05-19 01:56  experiment/data/_llm_generated_draft.csv
2026-05-19 01:43  experiment/data/_synthetic_draft.csv
2026-05-19 01:20  experiment/data/cell_selection.csv
2026-05-19 01:58  experiment/data/prompts.csv
```

All locked files at pre-2026-05-20 mtimes. No solver runs. No model
calls. No `experiment/results/<run_id>/` directory written.

---

## 10. Acceptance criteria — satisfied

- ☑ Current rows remain regression-clean (39/39, 0 failures, all
  component metrics unchanged).
- ☑ Target-extension rows improve substantially (21/21 now scoring
  1.000 on every component metric; was 0/21 component-clean).
- ☑ Each extension family has traceable lift (§5 table).
- ☑ No model calls.
- ☑ No solver calls.
- ☑ Tests pass (103/103 R2 tests).
- ☑ No locked experiment files modified (§9).

The benchmark and its companion C-extended contract are ready for
Stage R2-3 sign-off. The next sanctioned activity is operator
review and the eventual System A / System B (model-baselines)
evaluation; both are out of R2-3 scope and not initiated here.

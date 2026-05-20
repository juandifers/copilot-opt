# Run 2 contract extension — thesis-facing summary

This document is the closing summary for the Run 2 contract-extension
arc. It records what Run 2 evaluates, what was found before and after
the planned extensions, and how the result should be read in the
thesis. It is the artefact a reader should consult first when looking
at Run 2 — it sits one level above the benchmark expansion report
(`run2_benchmark_expansion_report.md`) and the extension
implementation report (`run2_extension_implementation_report.md`).

---

## A. Purpose

Run 2 evaluates the **product copilot's contract**. The unit under
test is the deterministic mapping

```
(prompt_text, payload_condition)  →  contract response
```

where the contract response is the structured object the operator
would receive in the product UI: an intent, an answerability verdict
(answerable / partially_answerable / not_answerable), grounded
evidence items, a missing-fields list, warnings, a useful-refusal
message when not fully answerable, and a list of suggested next
actions. Run 2 does **not** evaluate the natural-language answer text
the LLM-shaped backends would render on top of that contract; that is
graded separately and (under R2-4) against the same contract.

The methodological role of Run 2 inside the thesis is to provide an
*engineering instrument*: a reproducible, deterministic harness that
asks "for this prompt and this payload, is the contract response the
right shape?" and that can be re-run after every change to the product
contract to catch regressions and confirm intended lifts.

---

## B. Benchmark setup

- **60 cases.** Authored from the locked Run 1 prompt set with
  deterministic payload mutations (11 distinct `payload_condition`
  values: `clean`, `missing_validity_fields`, `missing_units`,
  `missing_reference_solution`, `missing_baseline_solution`,
  `missing_new_customer_ids`, `unsupported_comparison`,
  `false_premise_customer`, `false_premise_route`,
  `full_route_membership`, `same_route_boolean`, `convention_boundary`).
- **39 current rows** — gold reflects behaviour the contract is
  expected to support at the current product-layer version. Used as
  the regression baseline.
- **21 target_extension rows** — gold reflects behaviour the contract
  *should* support but did not at the start of Stage R2-3. These rows
  encode the policy backlog (six extension families; §C below).
- **Distributions.** Family: OBJ 15, PLAN_VALIDITY 12, STRUCT 18,
  SCHEDULE 15. Behavior class: direct_answer 27,
  direct_answer_with_warning 8, partial_answer_with_warning 7,
  useful_refusal 18. Difficulty: easy 20, medium 26, hard 14.
- **Component metrics only.** Per case the benchmark scores:
  intent_correct, answerability_correct, behavior_class_correct,
  evidence precision/recall (field-family, schema §10a),
  missing_field_recall, warning precision/recall,
  useful_refusal_correct (when gold = useful_refusal),
  partial_answer_correct (when gold = partial_answer_with_warning).
  These are reported separately for the `current` and
  `target_extension` partitions and never combined into a single
  headline number.
- **No aggregate composite.** Design §6.9 explicitly forbids one.
  Each component is meaningful on its own; collapsing them would
  hide the structure the benchmark is designed to expose.
- **No model calls.** The contract is computed by deterministic
  product-layer functions. The R2-4 model baselines (§G) are a
  separate stage.
- **No solver calls.** Payloads are materialised from already-solved
  Run 1 instances; the benchmark does not invoke pyvrp or any other
  solver.

The benchmark was finalised at Stage R2-2 (60 rows, 0 schema errors,
60/60 materialise, no rationale-text seed inference, 103/103 R2 tests
green). Stage R2-3 closes the policy backlog the R2-2 instrument
exposed.

---

## C. C-current result (pre-extension baseline)

At the close of R2-2, the deterministic contract (System C-current)
scored as follows on the 60-row benchmark:

| Partition | intent | answerability | behaviour_class | useful_refusal_correct | partial_answer_correct |
|---|---:|---:|---:|---:|---:|
| current (39) | 1.000 | 1.000 | 1.000 | 1.000 (7/7) | — |
| target_extension (21) | 0.857 | 0.476 | 0.476 | 0.000 (0/11) | 0.000 (0/7) |

The **current** rows are regression-clean. Every component metric is
1.000 except evidence_precision (0.969 — a single case emits one
extra evidence field beyond gold, documented in
`run2_benchmark_expansion_report.md`).

The **target_extension** rows fail in exactly six expected extension
families, each corresponding to a planned product-layer extension:

1. **`full_route_listing`** — operator asks for the per-route roster
   ("List the customers on each route"); the contract has no intent
   for that shape and routes to `unknown` or
   `new_customer_assignment`. Cases: R2-010, R2-048, R2-049.
2. **`false_premise_customer`** — operator asks about a customer ID
   that does not exist in the payload; the contract checks only that
   the schema column is present and silently answers about an
   unrelated customer. Cases: R2-008, R2-047, R2-058.
3. **`false_premise_route`** — operator asks about a route number
   that does not exist in the payload; the evidence builder returns
   an empty list silently instead of refusing. Cases: R2-015, R2-059.
4. **`comparison_referent_ambiguity`** — operator asks for an OBJ
   delta against a comparator (`a full re-solve`, `the optimum`)
   that `baseline_objective` does not describe; the OBJ escape hatch
   silently treats the question as answerable against the wrong
   referent. Cases: R2-013, R2-024, R2-025.
5. **`evidence_units_missing`** — OBJ value/delta is grounded by
   `action_objective` but `units.objective` is absent, so the figure
   cannot be displayed; the contract marks the question partially
   answerable but emits no warning and no next action. Cases: R2-014,
   R2-021, R2-022, R2-023.
6. **`use_validity_payload`** — PLAN_VALIDITY question against a
   payload missing both `feasible` and `feasibility_breakdown`; the
   contract refuses correctly but offers no semantic next action.
   Cases: R2-012, R2-032, R2-033, R2-034, R2-035, R2-036.

Each family is a distinct, named policy gap. The benchmark exposes
them as failures on specific component metrics, not as a single
opaque drop.

---

## D. C-extended result (post-extension)

Stage R2-3 implemented the six extension families one at a time,
re-running the full benchmark after each one. After all six were in
place (and after two precision-only clean-ups that enforce the same
gold-aligned policy: false-premise dominance over
`route_indexing_ambiguity` / `struct_membership_ambiguity`, and
suppression of supplementary feasibility evidence when the primary
fields are absent), the contract scores:

| Partition | intent | answerability | behaviour_class | useful_refusal_correct | partial_answer_correct | evidence p/r | warning p/r | missing_field_recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current (39) | 1.000 | 1.000 | 1.000 | 1.000 (7/7) | — | 0.969 / 1.000 | 1.000 / 1.000 | 1.000 |
| target_extension (21) | **1.000** | **1.000** | **1.000** | **1.000 (11/11)** | **1.000 (7/7)** | **1.000 / 1.000** | **1.000 / 1.000** | **1.000** |

- **Current rows: no regressions.** Every component metric is byte-for-byte
  identical to the R2-2 baseline. The 0.969 evidence_precision figure
  on the current partition is the same single case from the R2-2
  report, unchanged.
- **Target_extension rows: 21/21 pass.** Every component metric
  reaches 1.000. The policy backlog the R2-2 instrument exposed is
  fully closed.

The implementation details are recorded in
`run2_extension_implementation_report.md` (files modified, per-step
lift table, before/after numbers); the canonical post-extension score
sheet is `run2_benchmark_eval_system_c_extended.{md,csv}`.

---

## E. Thesis interpretation

> Run 2 shows that the benchmark can be used as an engineering
> instrument: it first exposes contract gaps in answerability,
> evidence, warning, and refusal behavior, and then verifies that
> targeted product-layer extensions close those gaps without breaking
> already-supported cases.

This is the thesis-level claim Run 2 supports. The benchmark is not
the science result on its own; it is the *measurement apparatus* that
makes the science result legible. Three properties are jointly
necessary for that role and are demonstrated here:

1. **Diagnostic resolution.** The benchmark's failures are
   addressable. Each of the 21 target_extension failures pointed to
   one of six named extension families, not to an opaque ensemble
   problem. A reader who saw the R2-2 score sheet could (and did)
   list the six extensions before any code was written.
2. **Surgical lift.** Each implemented extension lifted exactly the
   cases it was designed to lift. Per-step accounting is in
   `run2_extension_implementation_report.md` §5. No step accidentally
   improved an unrelated metric or regressed a current row.
3. **Regression integrity.** The 39 current rows remained
   bit-identical across all six extensions. The `current` partition
   is a real regression baseline, not a leaderboard the system can
   game; the test
   `test_benchmark_current_rows_score_perfectly_on_component_metrics`
   would have failed immediately on any drift.

These three properties together justify using the same instrument to
measure model-shaped backends (R2-4 below). Without (1) the
benchmark would be uninformative; without (2) it would be
unfalsifiable; without (3) any "improvement" could be a quiet
trade-off.

---

## F. Caveats

State these explicitly when citing Run 2:

- **This is not a user study.** No human operator interacted with the
  contract during Run 2. The gold encodes the design's expected
  contract shape, not measured user satisfaction.
- **This is not model robustness.** System C is a deterministic
  product-layer function; it has no sampling temperature, no
  prompt-sensitivity surface, and no failure mode that would
  manifest as a sampling tail. Robustness claims belong to
  R2-4 model baselines.
- **This is not solver validation.** Payloads are materialised from
  already-solved Run 1 instances. Whether the underlying VRPTW
  solutions are themselves optimal is the Stage A / solver concern,
  not Run 2's.
- **This does not prove generalization beyond the benchmark.** 60
  cases is enough to expose and close six named policy gaps; it is
  not enough to claim that the contract will behave correctly on
  unseen operator phrasings. The benchmark grew from a 10-case
  calibration set to 60 in three stages and each stage surfaced
  new gold-level issues; the same pattern can be expected as the set
  grows further.
- **The contract is not the user-visible answer.** Run 2 evaluates
  the structured contract; whether a model backend renders the
  contract into a faithful, useful natural-language answer is a
  separate evaluation (R2-4 + a later answer-text rubric).

---

## G. Recommended next stage — R2-4 model baselines

Stage R2-4 is the natural sequel and is **not initiated here**.
The setup it inherits from R2-3:

- **C-extended** is now the deterministic upper bound: it scores
  1.000 on every component metric on the 60-case benchmark and is
  the reference implementation of the intended contract behaviour.
- **B-Sonnet prompt-only JSON baseline** — a Claude Sonnet 4.x model
  prompted in JSON mode against the same `(prompt_text, payload)`
  pairs, with the schema in `run2_gold_schema.md` provided in the
  system prompt, no tool calls, no retrieval. The benchmark scores
  this as if it were System C (same scorer, same gold). The
  hypothesis is that a strong model with the schema in context will
  approach C-extended on `current` rows but lag on the
  `target_extension` families because the schema does not encode the
  policy gates as procedure.
- **A-Sonnet naive baseline** — same model, no schema in the prompt,
  asked to respond in JSON. Expected to be substantially below
  B-Sonnet and to fail many `current` rows on evidence and warning
  precision. Anchors the bottom of the comparison.
- **Comparison against C-extended.** Same 60-case benchmark, same
  scorer. The interesting quantities are:
  (a) the gap between A and B (cost of giving the model the schema),
  (b) the gap between B and C-extended (cost of model interpretation
      vs. deterministic policy execution),
  (c) per-family decomposition of (b) — which extension families are
      hardest to learn from schema alone.
- **Later: pass^k on a hard subset.** Sample-budget permitting, run
  B-Sonnet at k ∈ {1, 5, 10} on the 14 hard cases and report
  pass^k. This is the sampling-tail measurement the deterministic
  system cannot provide.

R2-4 must not change `run2_benchmark_cases.csv`, the gold schema, or
the scorer. Any modification to those files would invalidate the
R2-3 baseline this summary records.

---

## Pointer index

- Benchmark: `product/evaluation/run2_benchmark_cases.csv`
- Schema: `product/evaluation/run2_gold_schema.md`
- Design: `product/evaluation/run2_contract_benchmark_design.md`
- R2-2 expansion: `product/evaluation/reports/run2_benchmark_expansion_report.md`
- R2-3 implementation: `product/evaluation/reports/run2_extension_implementation_report.md`
- Canonical post-extension scores:
  `product/evaluation/reports/run2_benchmark_eval_system_c_extended.{md,csv}`
- Disagreement log: `product/evaluation/run2_calibration_disagreement_log.md`
- Case notes: `product/evaluation/run2_benchmark_case_notes.md`
- Tag for this state: `run2-contract-extended`

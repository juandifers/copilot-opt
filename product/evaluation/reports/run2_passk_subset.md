# Run 2 pass^k subset — System B (OpenAI gpt-5.4-mini prompt-only)

_Stage R2-5 subset definition. Ten cases chosen to test the two
reliability hypotheses we care about: (a) does the model emit the
R2-3 extension contract codes *consistently*, and (b) are its R2-4A
`current`-row misses *stable* (always wrong) or *flaky* (sometimes
right)? Pass^k is a reliability instrument layered on top of the
60-case benchmark; it is not a replacement for it._

## Selection method

- All ten case IDs were taken from the user-specified R2-5 list and
  cross-checked against `product/evaluation/run2_benchmark_cases.csv`.
- All ten are present and unchanged from the R2-3 frozen benchmark
  (tag `run2-contract-extended` / commit `18b4811`).
- R2-4A outcome columns are read from
  `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.csv`
  (the 60-case scored run).
- No substitutions were needed.

## Five target-extension success-stability cases

These cases tested whether the model emits the *R2-3 extension*
contract codes when the prompt phrasing requires them. R2-4A got
each one fully correct (every component metric == 1.000). Pass^k
asks: does this hold across k=5 replicates, or did R2-4A see the
single sample that happened to land right?

| case | family | payload_condition | gold intent | gold beh | gold ans | R2-4A outcome |
|---|---|---|---|---|---|---|
| R2-008 | SCHEDULE | false_premise_customer | customer_arrival | useful_refusal | not_answerable | all 1.000 — model emitted `false_premise_detected` + `clarify_false_premise` |
| R2-012 | PLAN_VALIDITY | missing_validity_fields | feasibility_status | useful_refusal | not_answerable | all 1.000 — model emitted `use_validity_payload` |
| R2-015 | SCHEDULE | false_premise_route | route_end_time | useful_refusal | not_answerable | all 1.000 — false-premise on Route 99 |
| R2-048 | STRUCT | full_route_membership | full_route_listing | direct_answer | answerable | all 1.000 — model emitted the proposed R2-3 intent `full_route_listing` correctly |
| R2-058 | SCHEDULE | false_premise_customer | customer_arrival | useful_refusal | not_answerable | all 1.000 — false-premise on customer 500 |

These cases all touch a planned **R2-3 contract extension** code
(`false_premise_detected` / `clarify_false_premise`,
`use_validity_payload`, `full_route_listing`). If the model gets them
right on every replicate, the prompt is reliably surfacing the
extension behavior. If it flakes, R2-4A's headline target-extension
score of 1.000 was generous and the operational claim is weaker.

## Five current-row failure-stability cases

These five `current`-row cases failed at least one component metric
in R2-4A. Pass^k asks whether the failures are *systematic* (the
model picks the wrong label every time) or *intermittent* (sometimes
it gets it right). The remediation strategy is different for each:

| case | family | payload_condition | gold intent | gold beh | gold ans | R2-4A miss kinds |
|---|---|---|---|---|---|---|
| R2-027 | PLAN_VALIDITY | clean | feasibility_status | direct_answer | answerable | evidence_recall_miss, evidence_precision_miss (cited `feasibility_breakdown` once; gold expects four subkeys) |
| R2-040 | STRUCT | clean | single_customer_route_membership | direct_answer_with_warning | answerable | intent_miss, answerability_miss, behavior_class_miss, warning_recall_miss (predicted `new_customer_assignment` instead of `single_customer_route_membership`) |
| R2-051 | SCHEDULE | clean | lateness_summary | direct_answer | answerable | intent_miss, answerability_miss, behavior_class_miss (predicted `feasibility_status`) |
| R2-055 | SCHEDULE | clean | route_end_time | direct_answer_with_warning | answerable | behavior_class_miss, warning_recall_miss (omitted `route_indexing_ambiguity` warning on "route 1") |
| R2-060 | SCHEDULE | clean | route_end_time | direct_answer_with_warning | answerable | behavior_class_miss, warning_recall_miss (same as R2-055, on "Route 1") |

Two of the five (R2-055 / R2-060) are near-identical prompts about
"route 1" / "Route 1" — pass^k will tell us whether the missing
`route_indexing_ambiguity` warning is a stable omission tied to the
prompt pattern or a sampling artefact.

## What pass^k will and will not tell us

**Will tell us:**
- Whether each of the 10 cases is *stable success*, *stable failure*,
  or *flaky*.
- Whether the R2-3 extension behaviors are reliable under repeated
  sampling on the small subset they exercise.
- Whether the R2-4A `current`-row misses we care about most are worth
  trying to remediate via prompt tuning, or whether they are
  systematic enough to need a different system condition (e.g. System
  A — deterministic LLM-augmented).

**Will not tell us:**
- Generalisation beyond these 10 cases (the broader benchmark already
  did that at k=1).
- Anything about systems other than B-GPT-5.4-mini (no Claude Code,
  no System A in this stage).
- Solver- or user-study-level claims (the benchmark grades the
  contract, not the operator-visible answer).

## Operational notes

- k=5 replicates per case → 50 total OpenAI calls. Expected wall
  time ~100s based on R2-4A's ~2 s/case median.
- Each call is independent (no state shared across replicates). The
  wrapper passes `temperature=0` for backward compatibility with
  gpt-4-class but the gpt-5-class branch drops `temperature` from the
  request, so the model uses its own (non-zero) default sampling.
  This means the 50 calls are nominally independent samples even
  with the deterministic-looking "temperature=0" request.
- The runner reuses the R2-4A `openai_client`, `run2_model_prompts`,
  `run2_model_output_adapter`, and `run2_scoring` modules verbatim.
  No new prompt content, no new scoring definition.

## Pre-registration

This document is the pre-registered subset for R2-5. The case IDs,
expected outcomes, and selection rationale are committed before the
pass^k calls are made. The runner writes its outputs under a fresh
`run-id`; the report compares results back to this memo.

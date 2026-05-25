# R2-S1 Semantic Intent Stress — Baseline Report

_System: C0. Run started: 2026-05-20T21:20:10Z. HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`. Seed run_id: `full-run-v1`._

## Purpose

R2-S1 tests whether the VRPTW copilot maps semantically equivalent but lexically held-out operator phrasing to the correct canonical intent. Each of the 24 cases is a paraphrase of a Run 2 base case; the expected contract response (answerability, evidence, warnings, next actions, behavior class) is inherited from the base case verbatim, so only the prompt text changes between Run 2 and the stress split.

## Method

- 24 cases, split 12/12 between `dev` and `heldout`. The split is an explicit `split` column; no shuffling, no random sampling.
- Payloads are materialized from Run 1 generator JSONL via `run2_payloads.materialize_case_payload(run_id='full-run-v1')` — identical to the locked-benchmark path.
- No solver calls. No model calls (System C0 is deterministic).
- Scores reuse `run2_scoring.score_case` against gold rows inherited verbatim from the named `base_case_id` in the locked Run 2 benchmark.
- No locked Run 2 file was read for write or modified. The stress split lives entirely under `product/evaluation/run2_stress/axis3_semantic/`.

## Guardrails and caveats

- **Not a user study.** All gold labels were author-derived from the base Run 2 case.
- **Not solver validation.** No optimization run, no objective or feasibility check was performed.
- **Not a replacement for Run 2.** R2-S1 is a diagnostic stress split, not a benchmark.
- **Not evidence of broad generalization.** The case count is small (24); a positive heldout score is suggestive, not conclusive.
- **Heldout must not be tuned on.** Iteration on C0 or a future C1/D semantic adapter consumes the `dev` split only.

## Overall metrics

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | 24 | 62.5% | 62.5% | 62.5% | 59.2% | 62.5% | 87.5% | 87.5% | 100.0% |

## Metrics by split

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | 12 | 66.7% | 66.7% | 66.7% | 63.3% | 66.7% | 83.3% | 83.3% | 100.0% |
| heldout | 12 | 58.3% | 58.3% | 58.3% | 55.0% | 58.3% | 91.7% | 91.7% | 100.0% |
| overall | 24 | 62.5% | 62.5% | 62.5% | 59.2% | 62.5% | 87.5% | 87.5% | 100.0% |

**`semantic_intent_accuracy`** (alias of intent accuracy for this axis):

- dev: 66.7%
- heldout: 58.3%
- overall: 62.5%

## Metrics by stress_subtype

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cost_synonym | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| entity_synonym | 5 | 80.0% | 80.0% | 80.0% | 80.0% | 80.0% | 100.0% | 100.0% | 100.0% |
| feasibility_synonym | 4 | 100.0% | 100.0% | 100.0% | 80.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| operator_colloquial | 2 | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 100.0% | 100.0% | 100.0% |
| paraphrase | 2 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% |
| schedule_synonym | 8 | 37.5% | 37.5% | 37.5% | 37.5% | 37.5% | 62.5% | 62.5% | 100.0% |

## Downstream metrics conditional on intent correct

Among cases where the front-door intent was predicted correctly, how does the downstream contract response look? This isolates language-mapping failures from contract-response failures.

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| intent_correct only | 15 | 100.0% | 100.0% | 100.0% | 94.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| overall (for reference) | 24 | 62.5% | 62.5% | 62.5% | 59.2% | 62.5% | 87.5% | 87.5% | 100.0% |

## Failure rows (9)

| case_id | split | subtype | prompt | gold intent | pred intent | gold ans | pred ans | gold cls | pred cls | ev p/r | warn p/r | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1D-07 | dev | entity_synonym | Give me the full set of vehicle runs. | full_route_listing | unknown | answerable | not_answerable | direct_answer | useful_refusal | 0.00/0.00 | 1.00/1.00 | classified as unknown |
| S1D-08 | dev | schedule_synonym | When does vehicle 1 close out? | route_end_time | unknown | answerable | not_answerable | direct_answer_with_warning | useful_refusal | 0.00/0.00 | 0.00/0.00 | classified as unknown |
| S1D-09 | dev | schedule_synonym | When is vehicle 1 finished? | route_end_time | unknown | answerable | not_answerable | direct_answer_with_warning | useful_refusal | 0.00/0.00 | 0.00/0.00 | classified as unknown |
| S1D-12 | dev | operator_colloquial | Which customers fall behind schedule? | lateness_summary | unknown | answerable | not_answerable | direct_answer | useful_refusal | 0.00/0.00 | 1.00/1.00 | classified as unknown |
| S1H-07 | heldout | paraphrase | Show me every route in the plan. | full_route_listing | unknown | answerable | not_answerable | direct_answer | useful_refusal | 0.00/0.00 | 1.00/1.00 | classified as unknown |
| S1H-08 | heldout | paraphrase | List the complete route plan. | full_route_listing | unknown | answerable | not_answerable | direct_answer | useful_refusal | 0.00/0.00 | 1.00/1.00 | classified as unknown |
| S1H-09 | heldout | schedule_synonym | At what time is route 1 done for the day? | route_end_time | unknown | answerable | not_answerable | direct_answer_with_warning | useful_refusal | 0.00/0.00 | 1.00/1.00 | classified as unknown |
| S1H-10 | heldout | schedule_synonym | When does truck 1 complete its run? | route_end_time | unknown | answerable | not_answerable | direct_answer_with_warning | useful_refusal | 0.00/0.00 | 0.00/0.00 | classified as unknown |
| S1H-12 | heldout | schedule_synonym | Are any stops served after their allowed time? | lateness_summary | unknown | answerable | not_answerable | direct_answer | useful_refusal | 0.00/0.00 | 1.00/1.00 | classified as unknown |

## Interpretation

C0 reaches **62.5%** semantic-intent accuracy on the 24-case stress split and **58.3%** on the heldout 12 cases. Among cases where intent classification is correct, downstream answerability is **100.0%** — consistent with the locked benchmark.

C0 is contract-stable on Run 2 but this stress split probes whether its front-door intent mapping is lexically brittle. The failure table shows the surface forms that bypass the existing keyword matchers in `product/copilot/intent.py`. We do **not** claim C0 generalizes to operator paraphrases on the basis of these numbers; the heldout split is small (12 cases) and the case selection deliberately targets known gaps.

## Next steps (informative, not commitments)

- **C1 semantic-intent adapter.** Replace `intent.py`'s keyword matchers with a deterministic synonym lookup over a canonical query frame (`objective_value`, `feasibility_status`, `customer_route_membership`, `full_route_listing`, `route_end_time`, `customer_arrival`, `lateness_summary`). Each frame carries a synonym set and an entity resolver.
- **System D.** Pair a model-based intent classifier with the deterministic answerability / evidence contract. The semantic adapter is the front door; the back-end contract remains the audit layer.
- **Heldout discipline.** Any C1/D iteration on `dev` must freeze `heldout` before publishing a heldout score. Tag the dev-iteration commit; run heldout once at that tag; record the score against the tag.


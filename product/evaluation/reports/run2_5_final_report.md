# Stage R2-5 — Final report

_Pass^k reliability instrument for System B (OpenAI gpt-5.4-mini prompt-only JSON baseline). Layered on top of the R2-4A 60-case benchmark; measures whether the model's per-case successes and failures are stable across repeated independent calls. Not a replacement for the 60-case benchmark._

## 1. Files created / modified

### Created

| Path | Purpose |
|---|---|
| `product/evaluation/run2_passk_runner.py` | CLI runner. Reuses `openai_client`, `run2_model_prompts`, `run2_model_output_adapter`, and `run2_scoring` from R2-4A. For each case, builds the prompt once and issues `k` independent calls; writes `raw.jsonl`, `parsed.jsonl`, `scored.jsonl`, `run_log.md`. Halts at preflight if outputs already exist. |
| `product/evaluation/run2_passk_report.py` | CLI report generator. Pure aggregation over the runner's `scored.jsonl`. Computes per-case reliability (intent/answerability/behavior rates, mean P/R for evidence/warning, mean missing-field recall, useful_refusal / partial_answer composite rates) plus the strict `all_components_pass_rate`, `pass^k_all`, and diagnostic `pass@k_any`. Classifies each case as `stable_success` / `stable_failure` / `flaky`. |
| `tests/test_run2_passk.py` | 6 tests covering stable success / stable failure / flaky classification, useful_refusal composite aggregation, direct_answer cases where the composite must be `None`, and parse failures lowering the all-pass rate. |
| `product/evaluation/reports/run2_passk_subset.md` | Pre-registered case subset (the 10 cases used by R2-5) with selection rationale and R2-4A outcome per case. |
| `product/evaluation/reports/run2_passk_gpt54mini_v1.md` | Pass^k report — sections 1–12 from the user spec, all populated. |
| `product/evaluation/reports/run2_passk_gpt54mini_v1.csv` | Per-case reliability CSV. |
| `product/evaluation/reports/run2_5_final_report.md` | _This file._ |
| `product/evaluation/model_outputs/run2-b-openai-gpt54mini-passk-v1/` | Per-replicate raw / parsed / scored outputs + run log. |

### Not modified (verified `git diff --stat HEAD` is empty)

- `product/evaluation/run2_benchmark_cases.csv`
- `product/evaluation/run2_gold_schema.md`
- `product/evaluation/run2_scoring.py`
- `product/evaluation/run2_calibration_cases.csv`
- `product/evaluation/run2_system_c.py`
- `product/copilot/*`, `product/data/*`
- `experiment/configs/*`, `experiment/data/*`
- the R2-4A prompt template (`run2_model_prompts.py`) — unchanged; pass^k reuses it verbatim
- `.env`

HEAD remains `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` (the R2-3 commit `run2-contract-extended`). No commit was made for R2-5 in line with the task scope.

## 2. Pass^k subset

Pre-registered in `product/evaluation/reports/run2_passk_subset.md`; reproduced here for self-containment.

| case | family | payload_condition | implementation_status | gold beh | role in subset |
|---|---|---|---|---|---|
| R2-008 | SCHEDULE | false_premise_customer | target_extension | useful_refusal | success-stability (R2-3 ext: false_premise_detected) |
| R2-012 | PLAN_VALIDITY | missing_validity_fields | target_extension | useful_refusal | success-stability (R2-3 ext: use_validity_payload) |
| R2-015 | SCHEDULE | false_premise_route | target_extension | useful_refusal | success-stability (R2-3 ext: false_premise_detected, route) |
| R2-048 | STRUCT | full_route_membership | target_extension | direct_answer | success-stability (R2-3 ext: full_route_listing intent) |
| R2-058 | SCHEDULE | false_premise_customer | target_extension | useful_refusal | success-stability (R2-3 ext: false_premise_detected) |
| R2-027 | PLAN_VALIDITY | clean | current | direct_answer | failure-stability (R2-4A miss: feasibility_breakdown subkey citation) |
| R2-040 | STRUCT | clean | current | direct_answer_with_warning | failure-stability (R2-4A miss: intent confusion → new_customer_assignment) |
| R2-051 | SCHEDULE | clean | current | direct_answer | failure-stability (R2-4A miss: intent confusion → feasibility_status) |
| R2-055 | SCHEDULE | clean | current | direct_answer_with_warning | failure-stability (R2-4A miss: omitted route_indexing_ambiguity) |
| R2-060 | SCHEDULE | clean | current | direct_answer_with_warning | failure-stability (R2-4A miss: omitted route_indexing_ambiguity) |

## 3. Calls attempted / completed

| | n |
|---|---:|
| cases | 10 |
| k | 5 |
| calls_attempted | 50 |
| calls_completed (response received, non-skip) | 50 |
| API/transport errors | 0 |

- Provider: OpenAI
- Requested model: `gpt-5.4-mini`
- Response model (pinned, every replicate): `gpt-5.4-mini-2026-03-17`
- Wall time: 109.93 s (mean 2.20 s/call)
- Tokens: 265,480 prompt / 6,094 completion total

## 4. Parse success

| parse_status | n |
|---|---:|
| parsed | 50 |
| invalid_json | 0 |
| invalid_enum | 0 |
| missing_required_fields | 0 |
| error (api/empty) | 0 |

50/50 model responses parsed cleanly. The adapter never had to strip a fence or coerce a list shape across the run.

## 5. Main reliability result

| subset | n | stable_success | stable_failure | flaky | mean all-pass rate | pass^k_all fraction | pass@k_any fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| **overall** | 10 | 3 | 5 | 2 | 0.420 | **0.300** | 0.500 |
| target-extension | 5 | 3 | 0 | **2** | 0.840 | 0.600 | 1.000 |
| current-row failure | 5 | 0 | **5** | 0 | 0.000 | 0.000 | 0.000 |

**Headline:** under the strict `pass^k_all` definition (every component metric = 1.0 on every one of k=5 replicates, with the appropriate composite for useful_refusal cases), GPT-5.4-mini's R2-4A 60-case benchmark numbers are best read as an *upper bound* on its reliability:

- 3 of 5 R2-3 extension successes were genuinely stable: `R2-008`, `R2-012`, `R2-015`.
- 2 of 5 R2-3 extension successes were *flaky at k=5*: `R2-048`, `R2-058`. R2-4A's single-sample 1.000 score on these cases reflected one lucky draw rather than reliable behavior.
- All 5 R2-4A failures replicated as **stable failures** at k=5. None of them flipped to success on any replicate.

## 6. Stable success cases (pass^k_all == true)

`R2-008`, `R2-012`, `R2-015` — all useful_refusal target_extension cases.

The shared shape is: prompts where the contract should refuse + name a *concrete schematic gap* (a missing customer, a missing route, missing PV fields). For these the model emits the correct R2-3 extension code (`false_premise_detected` / `use_validity_payload`) on every replicate. This is the most operationally important reliability result in the report — the planned contract extensions actually do hold up under repeated sampling on the cases they were designed for.

## 7. Stable failure cases (all_components_pass_rate == 0.0)

`R2-027`, `R2-040`, `R2-051`, `R2-055`, `R2-060` — all `current`-row cases.

| case | gold expects | model does (stably) |
|---|---|---|
| R2-027 | cites `feasibility_breakdown.{capacity_ok,time_windows_ok,coverage_ok}` separately (gold-rubric subkey enumeration) | cites `feasibility_breakdown` once. evP 0.50, evR 0.25 on every replicate. Same shape as the 0.969 evidence_precision dip the C-extended reference shows on PLAN_VALIDITY |
| R2-040 | intent `single_customer_route_membership`, warning `struct_membership_ambiguity`, answerable | intent `new_customer_assignment` 4/5 replicates, behavior_class `partial_answer_with_warning`, warning omitted. (One replicate predicted the right intent but with the wrong warning shape, so `all_components_pass` was still False.) |
| R2-051 | intent `lateness_summary`, answerable, direct_answer | intent `feasibility_status` 2/5 replicates, `lateness_summary` 3/5 — but even when the intent is right, evidence_precision is too low (mean 0.34). Stable failure with intermittent intent label. |
| R2-055 | warning `route_indexing_ambiguity` on "route 1" | omits the warning 3/5 replicates; over-cites evidence 5/5. Stable failure with mixed warning behavior. |
| R2-060 | warning `route_indexing_ambiguity` on "Route 1" | omits the warning **5/5**; over-cites evidence 5/5. The most systematic miss in the subset. |

The pattern: **none of these failures are sampling artefacts.** The model has a stable disagreement with the rubric (or a stable lexical mis-classification) that prompt tuning or a stronger model would need to address.

## 8. Flaky cases

`R2-048` (target_extension, STRUCT, direct_answer) — all-pass rate **0.40**:
- intent_correct = 1.00 (model always predicts `full_route_listing`)
- behavior_class_correct = 0.80 (one replicate predicted `direct_answer_with_warning`)
- evidence_precision_mean = 0.80, warning_precision_mean = 0.80 — on the failing replicates the model adds extra evidence paths beyond `routes[].customer_ids` and an unnecessary warning

`R2-058` (target_extension, SCHEDULE, useful_refusal) — all-pass rate **0.80**:
- Every component metric = 1.0 on 4 of 5 replicates
- One replicate had evidence_precision 0.0 — the model cited an evidence path on a useful_refusal case where gold expects none

These two together are the single most important finding of R2-5: R2-4A's 1.000 target-extension scores were *partially* a single-sample upper bound. Under k=5 the realistic target-extension pass^k_all fraction is **3/5 = 0.60**, not 1.0.

## 9. Should System A naive baseline be run next?

Recommendation: **yes — but scope it narrowly.**

R2-5 isolates the operational claim Stage R2 has been building toward: the planned R2-3 contract extensions encode behavior an off-the-shelf prompted LLM can match (3/5 stable) but does not match reliably on every case (2/5 flaky). System A — the LLM-augmented deterministic baseline — would test whether a thin deterministic prior (the same intent classifier and answerability checker the contract uses) makes that 3/5 → 5/5 on the cases where the model has the right idea but flakes.

A useful A-run is small and narrow:
- Cover the 10 R2-5 cases (so the comparison is direct) plus a 20-case sampler from the rest of the benchmark — total ≤30 cases.
- Use the same model (gpt-5.4-mini) and the same prompt scaffold; the difference is wrapping the model call with the deterministic intent + answerability classifier and letting the model only fill the parts the classifier defers on.
- Score with the existing `run2_scoring.score_case`. No new scoring code.
- Run at k=3 to bound flakiness without paying the full pass^k cost.

If the thesis only cares about the headline "deterministic vs prompted" contrast, the existing C-extended vs B-prompted comparison from R2-4A already makes that case. System A's added value is narrower: showing that the prompted-LLM failures are recoverable by a small deterministic prior. That is worth one targeted stage, but not a 60-case re-run.

## 10. Locked-file / integrity integrity

- `git diff --stat HEAD` returns empty for every protected path.
- HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`. Tag `run2-contract-extended` points to the same commit.
- `.env` is not tracked. `git ls-files --error-unmatch .env` errors as expected.
- 120/120 R2 tests pass (was 114 after R2-4A; the 6 new tests are the pass^k aggregation tests).
- No API key string was ever written to a log, raw output, or report. The only `sk-…`-shaped matches in `model_outputs/` are slug substrings of the run-id (`run2-b-openai-gpt54mini-passk-v1`), not OpenAI key prefixes.

## 11. Stop point

Stage R2-5 complete. **Not started:** Claude Code repo-agent baseline (deferred per the user direction that all model-under-test runs go through the API), System A (deterministic LLM-augmented). Resuming either is an explicit next-stage request.

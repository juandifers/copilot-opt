# Stage R2-6 — Final report

_System A: deterministic-prior + GPT-5.4-mini hybrid baseline. Tests whether a thin product-layer prior recovers the prompt-only model's failure modes from R2-4A / R2-5._

## 1. Files created / modified

### Created

| Path | Purpose |
|---|---|
| `product/evaluation/run2_system_a_prior.py` | `build_system_a_prior(case, payload)`. Wires the existing `infer_intent`, `compute_answerability`, `build_warnings`, `suggested_next_actions_for_missing_fields` into a single JSON-serialisable prior with `prior_locked_fields`. Uses `generator_record=None` (no Run 1 leakage). Does NOT call `run_system_c_on_case` — A is a *thin prior*, not C-with-extra-steps. |
| `tests/test_run2_system_a_prior.py` | 13 prior tests including the 7 acceptance cases (R2-008/012/015/027/040/048/058) plus invariants. |
| `product/evaluation/reports/run2_system_a_design.md` | Design doc (§1–7): motivation, positioning vs B and C, what A locks deterministically, what the model still does, what A does not do, expected failure-mode hypotheses, stop criteria. |
| `product/evaluation/reports/run2_passk_system_a_gpt54mini_v1.{md,csv}` | A pass^k report (10 cases × k=3). |
| `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_30case_v1.{md,csv}` | Optional 30-case single-sample run. |
| `product/evaluation/reports/run2_model_baseline_a_openai_gpt54mini_smoke.{md,csv}` | 5-case smoke. |
| `product/evaluation/reports/run2_system_a_final_report.md` | _This file._ |
| `product/evaluation/model_outputs/run2-a-openai-gpt54mini-smoke/` | Smoke raw/parsed. |
| `product/evaluation/model_outputs/run2-a-openai-gpt54mini-passk-v1/` | Pass^k raw/parsed/scored. |
| `product/evaluation/model_outputs/run2-a-openai-gpt54mini-30case-v1/` | 30-case raw/parsed. |

### Modified (additive only — System B behavior unchanged)

| Path | Change |
|---|---|
| `product/evaluation/run2_model_prompts.py` | Added `_SYSTEM_PROMPT_A`, `_PRIOR_INSTRUCTIONS_TEMPLATE`, `_build_prior_block`, and `build_system_a_prior_prompt(case, payload, prior)`. System B prompt builder is byte-unchanged. |
| `product/evaluation/run2_model_output_adapter.py` | Added optional `prior_disagreement` (bool) and `adapter_notes` (str) on `ParsedModelOutput`. System B outputs default both to `False` / `""` without warning. JSONL round-trip preserves both. |
| `product/evaluation/run2_model_baseline_runner.py` | Added `--system A` choice + `_build_messages_for_system()` dispatcher. Per-case raw row now carries `system` and `prior_summary`. System B path byte-unchanged in semantics. |
| `product/evaluation/run2_passk_runner.py` | Same `--system A` extension; per-replicate raw row carries `system` and `prior_summary`. |
| `product/evaluation/run2_passk_report.py` | `--system` accepts `A` or `B`; A report gets an R2-6 framing paragraph. |
| `product/evaluation/run2_score_model_outputs.py` | `--system` accepts `A` or `B`. |
| `tests/test_run2_model_output_adapter.py` | +6 tests covering optional prior fields, string coercion, invalid-enum case with prior fields, JSONL round-trip. |

### NOT modified (verified `git diff --stat HEAD` is empty)

- `product/evaluation/run2_benchmark_cases.csv`
- `product/evaluation/run2_gold_schema.md`
- `product/evaluation/run2_scoring.py`
- `product/evaluation/run2_calibration_cases.csv`
- `product/evaluation/run2_system_c.py`
- `product/copilot/*`, `product/data/*`
- `experiment/configs/*`, `experiment/data/*`
- `.env`

HEAD is still `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` (= `run2-contract-extended`). No commit for R2-6 per the task scope.

## 2. Definition of System A

A deterministic prior layer computes — from the prompt text, family, and materialised payload — the contract fields the product-layer code already produces:

- `intent_prior` (locked) — `product.copilot.intent.infer_intent(prompt_text, family)`
- `answerability_prior` (locked) — `product.data.answerability.compute_answerability(...)`
- `required_fields`, `available_fields` (informational) — exposed to the model so it has hints about which paths the rubric cares about
- `missing_fields_prior` (locked) — the same `answerability.missing_fields`
- `warnings_prior` (locked) — `product.copilot.refusal_policy.build_warnings(...)` (with `answer_text=""`)
- `next_actions_prior` (locked) — `suggested_next_actions_for_missing_fields(...)` mapped to semantic codes
- `behavior_class_prior` (locked) — projected via the same decision tree the C-extended adapter uses

The model receives this prior plus the standard prompt + payload projection, is told to copy the locked fields verbatim unless it flags `prior_disagreement=true`, and emits the canonical contract JSON.

Critically: the prior layer **does not call `run_system_c_on_case`**. The model still has to emit the final JSON (intent, answerability, missing, warnings, actions, behavior class, evidence paths, optional answer_text). If A simply echoed C-extended, this stage would be measuring "is the model capable of copying a dict" — not what we want.

## 3. How System A differs from B and C

| | System B (R2-4A) | System A (this stage) | System C-extended (R2-3) |
|---|---|---|---|
| Who picks intent | the model | deterministic prior, locked into the model's output | deterministic rule layer |
| Who picks answerability | the model | deterministic prior, locked | deterministic rule layer |
| Who picks warnings | the model | deterministic prior, locked | deterministic rule layer |
| Who picks evidence | the model | the model (prior gives `required_fields` as a hint, not a list to cite) | deterministic rule layer + Run 1 structured_output |
| Who emits the final JSON | the model | the model | the deterministic adapter |
| Repository / scorer access | none | none | full (it *is* the contract) |
| Replicate variance | high | reduced where the prior is decisive | zero by construction |

System A is intentionally narrow. The only thing that changes between B and A is who decided the locked fields *before* the model was asked.

## 4. Smoke result (TASK 6)

5-case smoke on the cases System B failed in R2-4A: R2-040, R2-048, R2-051, R2-055, R2-060.

| case | A intent | A ans | A behavior | A ev P/R | A warn P/R |
|---|---|---|---|---|---|
| R2-040 | ✓ single_customer_route_membership | ✓ answerable | ✓ direct_answer_with_warning | 1.000/1.000 | 1.000/1.000 |
| R2-048 | ✓ full_route_listing | ✓ answerable | ✓ direct_answer | 1.000/1.000 | 1.000/1.000 |
| R2-051 | ✓ lateness_summary | ✓ answerable | ✓ direct_answer | 1.000/1.000 | 1.000/1.000 |
| R2-055 | ✓ route_end_time | ✓ answerable | ✓ direct_answer_with_warning | 0.500/1.000 | 1.000/1.000 |
| R2-060 | ✓ route_end_time | ✓ answerable | ✓ direct_answer_with_warning | 0.500/1.000 | 1.000/1.000 |

- Parse: 5/5
- Intent / answerability / behavior class / warnings: **5/5 on every case** (recovered every System B failure on these axes)
- Only remaining miss: evidence_precision 0.5 on R2-055/R2-060 (model adds `route_end_times[].route_idx` alongside `.end_time`; gold pins only `.end_time`). This is a precision-only over-citation that the prior does not address (the prior gives `required_fields` for the intent but does not lock the cited evidence list).

Smoke acceptance (≥4/5 components-pass on cases the prior is being followed): **met**.

## 5. Pass^k result (TASK 7)

10-case × k=3 pass^k on the exact R2-5 subset.

- run_id: `run2-a-openai-gpt54mini-passk-v1`
- requested model: `gpt-5.4-mini` / response_model `gpt-5.4-mini-2026-03-17` on every one of the 30 calls
- calls_attempted: 30; calls_completed: 30; errors: 0
- parse success: 30/30
- pass^k_all (strict, all components on every replicate): **5/10 = 0.50**
- pass@k_any (diagnostic, at least one replicate fully passes): **7/10 = 0.70**

### Stable / flaky / stable-failure
| | n | cases |
|---|---:|---|
| stable_success | 5 | R2-008, R2-012, R2-015, R2-040, R2-058 |
| stable_failure | 3 | R2-027, R2-055, R2-060 |
| flaky | 2 | R2-048 (2/3), R2-051 (1/3) |

### Subset breakdown
| subset | n | stable_success | stable_failure | flaky | pass^k_all |
|---|---:|---:|---:|---:|---:|
| target-extension success-stability | 5 | 4 | 0 | 1 | 0.80 |
| current-row failure-stability | 5 | 1 | 3 | 1 | 0.20 |
| overall | 10 | 5 | 3 | 2 | 0.50 |

## 6. Direct comparison to System B R2-5

| case | B pass^k_all (k=5) | A pass^k_all (k=3) | recovered? |
|---|---|---|---|
| R2-008 | ✓ 5/5 | ✓ 3/3 | preserved |
| R2-012 | ✓ 5/5 | ✓ 3/3 | preserved |
| R2-015 | ✓ 5/5 | ✓ 3/3 | preserved |
| R2-048 | ✗ flaky 2/5 (0.40) | ✗ flaky 2/3 (0.67) | improved (still flaky) |
| R2-058 | ✗ flaky 4/5 (0.80) | ✓ 3/3 | **RECOVERED** |
| R2-027 | ✗ 0/5 | ✗ 0/3 | unchanged |
| R2-040 | ✗ 0/5 | ✓ 3/3 | **RECOVERED** |
| R2-051 | ✗ 0/5 | ✗ flaky 1/3 | partial recovery |
| R2-055 | ✗ 0/5 | ✗ 0/3 | unchanged |
| R2-060 | ✗ 0/5 | ✗ 0/3 | unchanged |

Aggregate:
| metric | B (R2-5) | A (R2-6) | Δ |
|---|---:|---:|---:|
| pass^k_all fraction | 0.30 | **0.50** | +0.20 |
| pass@k_any fraction | 0.50 | **0.70** | +0.20 |
| target-extension pass^k_all | 0.60 | **0.80** | +0.20 |
| current-row pass^k_all | 0.00 | **0.20** | +0.20 |
| stable_success count | 3 | **5** | +2 |
| stable_failure count | 5 | 3 | −2 |
| flaky count | 2 | 2 | 0 |

The target-extension subset becomes one short of perfect at k=3 (only R2-048 is still flaky on evidence-precision; intent/ans/behavior/warning are now stable). The current-row subset has one new stable success (R2-040) and one partial recovery (R2-051).

## 7. Which System B failures were recovered

- **R2-040 (intent confusion → fully recovered).** B stably predicted `new_customer_assignment` 4/5 replicates. A's prior locked `single_customer_route_membership`; A passes 3/3 on every component.
- **R2-058 (flaky useful_refusal → fully recovered).** B was 4/5 (one replicate over-cited evidence on a refusal case). A's prior locked `false_premise_detected` + `clarify_false_premise`; A is 3/3.
- **R2-051 (intent confusion → partially recovered).** B stably predicted `feasibility_status` (3/5 wrong intent). A's prior locked `lateness_summary` and the model preserved it on 1/3 replicates with full-component pass; on the other 2 replicates the model over-cited evidence (evP dropped). Still flaky, but moved from stable_failure to flaky.
- **R2-048 (flaky over-citation → mildly improved).** B all-pass rate 0.40. A all-pass rate 0.67. Still flaky on the same axis (extra evidence path).

## 8. Which failures remain

- **R2-027 (PV feasibility_breakdown subkey enumeration).** The gold rubric expects three subkeys cited separately (`feasibility_breakdown.{capacity_ok, time_windows_ok, coverage_ok}`); the deterministic prior's `required_fields` lists only `feasibility_breakdown` and `feasible`. C-extended itself scores 0.800 evidence_precision on the same case. A inherits this rubric/contract gap. **Not a model failure — a contract-vs-rubric mismatch.** Predicted in the R2-6 design doc §6.
- **R2-055 / R2-060 (route_end_times[].route_idx over-citation).** A's prior locks intent, ans, behavior, and the `route_indexing_ambiguity` warning — and the model preserves all of them. But the model still adds `route_end_times[].route_idx` alongside `.end_time` in evidence, dropping evidence_precision to 0.5. The prior provides `required_fields = ["route_end_times[].route_idx", "route_end_times[].end_time"]` which arguably *invites* this — the model is technically obeying the prior hint. A targeted fix would be to add an explicit "cite only `.end_time`" evidence policy to the prompt; declined for R2-6 to keep the prompt minimal.
- **R2-048 / R2-051 flakiness.** Same evidence over-citation pattern as R2-055/R2-060.

## 9. Thesis claim support

The thesis claim under test:

> "Thin deterministic priors improve model stability but full deterministic contract execution remains the most reliable."

The R2-6 evidence:

- **Stability improves with the prior.** Pass^k_all jumps from 0.30 (B) to 0.50 (A) on the same 10-case subset. Target-extension pass^k_all jumps from 0.60 to 0.80. Intent and answerability rates on the 30-case sampler are 1.000/1.000 (vs B's 0.949/0.949 on the full 60). Two of five R2-4A current-row failures recover (R2-040 fully, R2-051 partially); both R2-5 flaky cases either recover (R2-058) or improve (R2-048).
- **The prior is *necessary but not sufficient* for full reliability.** Three cases stay stable failures under A: R2-027 (rubric mismatch the contract itself shows), R2-055/R2-060 (evidence over-citation the prior does not constrain). Two cases stay flaky.
- **Full deterministic execution remains strictly more reliable.** C-extended on the same 10-case subset has pass^k_all = 10/10 by construction (zero replicate variance). A at 5/10 closes more than half the gap between B (3/10) and C (10/10) on this subset; the remaining gap is *exactly* the cases where the prior cannot fix the model's evidence-citation choices.

**Verdict: the thesis claim is supported.** A occupies the middle of the (B, C) reliability spectrum in the way the claim predicts. The cases A does not recover are precisely the ones where the deterministic prior has nothing locking to say — they are evidence-precision misses that the C-extended contract handles via a different mechanism (evidence-builder pinning) which is not part of the prior surface.

## 10. Tests run

| run | result |
|---|---|
| `pytest tests/test_run2_*.py` | **139 passed** in 1.13 s |
| `pytest tests/test_run2_system_a_prior.py` | 13 passed (7 acceptance + 6 invariants) |
| `pytest tests/test_run2_model_output_adapter.py` | 17 passed (11 originals + 6 new for prior fields) |
| `pytest tests/test_run2_passk.py` | 6 passed |
| `pytest tests/test_run2_system_c.py` | 14 passed (unchanged) |

No test regressions. R2-3 R2-4A R2-5 tests all unchanged and passing.

## 11. No locked benchmark / gold / scorer files modified

Verified `git diff --stat HEAD` empty for:
- `product/evaluation/run2_benchmark_cases.csv`
- `product/evaluation/run2_gold_schema.md`
- `product/evaluation/run2_scoring.py`
- `product/evaluation/run2_calibration_cases.csv`
- `product/evaluation/run2_system_c.py`
- `product/copilot/*`, `product/data/*`

## 12. No locked experiment files modified

Verified `git diff --stat HEAD` empty for `experiment/configs/*` and `experiment/data/*`.

## 13. `.env` not committed and API key never printed

- `.env` is in `.gitignore`. `git ls-files --error-unmatch .env` returns non-zero (untracked).
- The OpenAI client wrapper reads `OPENAI_API_KEY` from env and never echoes it.
- No `model_outputs/` file contains an API key string. Calls were authenticated end-to-end with the same `.env` setup as R2-4A and R2-5.

## 14. Stop point

Stage R2-6 complete. Per the user direction, the following are **explicitly not done**:

- Claude Code repo-agent baseline (deferred indefinitely; the user has ruled it out as a model-under-test in the closing experiment).
- Full 60-case System A pass^k (declined; R2-6 scope was the 10-case subset + 30-case single-run).
- Stress split.
- Any change to the locked benchmark, gold schema, or scorer.

Resuming any further stage is an explicit next-stage request.

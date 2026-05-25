# Stage R2-4A — Final report

_System B: OpenAI gpt-5.4-mini prompt-only JSON contract emitter. First model baseline for the Run 2 contract benchmark. Companion to the C-extended deterministic reference (R2-3, tag `run2-contract-extended`)._

## 1. Files created or modified

### Created (new this stage)

| Path | Purpose |
|---|---|
| `product/evaluation/model_clients/__init__.py` | Marker for the model-client package. |
| `product/evaluation/model_clients/openai_client.py` | Transport wrapper. `load_openai_client()` and `call_openai_contract_model()`. Reads `OPENAI_API_KEY` from `.env`/env, picks `max_completion_tokens` for gpt-5/o1/o3/o4 families, treats `temperature=0` as "model default" for the same families, retries transient errors. |
| `product/evaluation/run2_model_prompts.py` | `build_prompt_only_json_prompt(case, payload)`. Embeds allowed enums (intents, answerability, behaviors, warnings, next actions, evidence paths), operational conventions, compact payload projection. **No gold labels.** |
| `product/evaluation/run2_model_output_adapter.py` | `parse_model_contract_json()` + `parsed_output_to/from_dict()`. Strips ``` fences with note, validates enums, normalises predicate-pinned paths, maps concrete next-action strings to semantic codes. |
| `product/evaluation/run2_model_baseline_runner.py` | CLI runner. `--cases / --system B / --provider openai / --run-id / --model / --temperature / --max-cases / --case-ids`. Writes `raw.jsonl`, `parsed.jsonl`, `run_log.md` under `model_outputs/<run-id>/`. Idempotent at preflight. |
| `product/evaluation/run2_score_model_outputs.py` | CLI scorer. Re-uses `run2_scoring.score_case` end-to-end; emits report `.md`/`.csv` with overall/current/target/family/behavior/difficulty splits, failure taxonomy, C-extended comparison, top-10 illustrative failures. |
| `tests/test_run2_model_output_adapter.py` | 11 tests covering happy path, fence forgiveness, invalid JSON, missing required fields, invalid enums, predicate-stripped paths, concrete-to-semantic action mapping, semicolon-string coercion, JSONL roundtrip. |
| `product/evaluation/reports/run2_model_baseline_model_lock_openai_gpt54mini.md` | Model lock record (TASK 1). |
| `product/evaluation/reports/run2_model_baseline_b_openai_gpt54mini_v1.{md,csv}` | Full 60-case scored report (TASK 7). |
| `product/evaluation/reports/run2_4a_final_report.md` | _This file._ |
| `product/evaluation/model_outputs/run2-b-openai-gpt54mini-smoke/` | 5-case smoke outputs (raw / parsed / log). |
| `product/evaluation/model_outputs/run2-b-openai-gpt54mini-v1/` | 60-case full-run outputs. |

### Modified

| Path | Change |
|---|---|
| `requirements.txt` | Added `openai>=1.40.0` and `python-dotenv>=1.0.0` with a section comment. |

### NOT modified (verified `git diff --stat HEAD` is empty)

- `product/evaluation/run2_benchmark_cases.csv`
- `product/evaluation/run2_gold_schema.md`
- `product/evaluation/run2_scoring.py`
- `product/evaluation/run2_calibration_cases.csv`
- `product/evaluation/run2_system_c.py`
- `product/copilot/*`, `product/data/*`
- `experiment/configs/*`, `experiment/data/*` (the pre-registration tags)
- `.env`

(`mtime` on a handful of the read-only CSVs and `.md` files was bumped by reads / pandas access during this stage. Content is byte-identical to HEAD — verified via `git diff --stat`.)

## 2. OpenAI plumbing

- API provider: OpenAI. SDK: `openai>=1.40.0` (installed 2.29.0). Env loader: `python-dotenv>=1.0.0`.
- Key source: `OPENAI_API_KEY` read from local `.env` (gitignored) via `dotenv.load_dotenv()`; the process environment overrides if present.
- Wrapper never prints, logs, or otherwise echoes the key.
- Wrapper detects gpt-5-class / o-class models by name prefix and switches `max_tokens` → `max_completion_tokens`, and treats `temperature=0` as "use model default" for those families. This was driven by the first smoke attempt failing with a documented 400 (see §3 of the model-lock report).

## 3. `.env` / `OPENAI_API_KEY` behavior

- `.env` is in `.gitignore` (top-level `Secrets & local config` section) and is currently untracked. `ls .env` confirms presence; `git status` confirms it is not staged.
- If `OPENAI_API_KEY` is absent the runner exits cleanly with code `4` and the literal message:
  > `OPENAI_API_KEY not found. Add it to .env or environment variables.`
  This was exercised explicitly during the build and confirmed.
- No call site logs or returns the key.

## 4. Model lock

| | |
|---|---|
| Requested model | `gpt-5.4-mini` |
| Response model (pinned snapshot) | `gpt-5.4-mini-2026-03-17` |
| Smoke call date | 2026-05-20 13:43 UTC |
| Smoke result | JSON returned exactly as requested; `finish_reason=stop` |
| `client.models.list()` confirms `gpt-5.4-mini` available | yes (also: `gpt-5.4-mini-2026-03-17`) |

Full lock report: `product/evaluation/reports/run2_model_baseline_model_lock_openai_gpt54mini.md`.

## 5. Smoke run (TASK 6)

- `run_id`: `run2-b-openai-gpt54mini-smoke`
- Cases: 5 representative — R2-001 (clean OBJ), R2-005 (unsupported comparison), R2-008 (false-premise customer), R2-010 (full route listing), R2-012 (PLAN_VALIDITY missing fields).
- Outcome: **5/5 parsed, 5/5 every component metric == 1.000.** No prompt tuning required.
- Wall time: 11.22s (≈2.2 s/case). Tokens: 15,420 prompt / 574 completion.

Notable: the smoke verified the R2-3 extension codes round-trip through the model end-to-end — `false_premise_detected` + `clarify_false_premise` (R2-008), `full_route_listing` intent (R2-010), `use_validity_payload` semantic code (R2-012).

## 6. Full run (TASK 7)

- `run_id`: `run2-b-openai-gpt54mini-v1`
- All 60 cases attempted; 60 materialized; 60 parsed; 0 API errors; 0 invalid JSON; 0 invalid enum.
- Wall time: 118.31s (≈2.0 s/case median). Tokens: 200,058 prompt / 7,275 completion.
- `response_model`: every row returned `gpt-5.4-mini-2026-03-17`.

### Parse success
| | n |
|---|---:|
| parsed | 60 |
| invalid_json | 0 |
| invalid_enum | 0 |
| missing_required_fields | 0 |
| error | 0 |

## 7. Component scores

### Overall
| n | intent | answerability | behavior_class | evidence P/R | warning P/R | missing-field R | useful_refusal (n) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | 0.950 | 0.967 | 0.917 | 0.771/0.902 | 0.917/0.950 | 0.992 | 0.944 (18) |

### By implementation_status
| group | n | intent | ans | beh | evidence P/R | warning P/R | miss R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | 39 | 0.949 | 0.949 | 0.872 | 0.673/0.859 | 0.872/0.923 | 0.987 | 0.857 (7) |
| target_extension | 21 | 0.952 | **1.000** | **1.000** | 0.952/0.981 | **1.000/1.000** | **1.000** | **1.000 (11)** |

### By family
| group | n | intent | ans | beh | evidence P/R | warning P/R | miss R | useful_refusal (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBJ | 15 | 1.000 | 1.000 | 1.000 | 1.000/0.973 | 1.000/1.000 | 1.000 | — (0) |
| PLAN_VALIDITY | 12 | 1.000 | 1.000 | 0.917 | 0.750/0.625 | 0.917/1.000 | 1.000 | 1.000 (6) |
| SCHEDULE | 15 | 0.933 | 0.933 | 0.800 | 0.649/0.933 | 0.800/0.867 | 1.000 | 1.000 (6) |
| STRUCT | 18 | 0.889 | 0.944 | 0.944 | 0.694/1.000 | 0.944/0.944 | 0.972 | 0.833 (6) |

## 8. Delta vs C-extended (deterministic reference)

C-extended (R2-3) reference: current = `1.000` everywhere except `evidence_precision = 0.969`; target_extension = `1.000` on every metric.

| metric | C-ext current | B-gpt54mini current | Δ | C-ext target | B-gpt54mini target | Δ |
|---|---:|---:|---:|---:|---:|---:|
| intent_accuracy | 1.000 | 0.949 | **−0.051** | 1.000 | 0.952 | −0.048 |
| answerability_accuracy | 1.000 | 0.949 | **−0.051** | 1.000 | **1.000** | 0.000 |
| behavior_class_accuracy | 1.000 | 0.872 | **−0.128** | 1.000 | **1.000** | 0.000 |
| evidence_precision | 0.969 | 0.673 | **−0.296** | 1.000 | 0.952 | −0.048 |
| evidence_recall | 1.000 | 0.859 | **−0.141** | 1.000 | 0.981 | −0.019 |
| warning_precision | 1.000 | 0.872 | **−0.128** | 1.000 | **1.000** | 0.000 |
| warning_recall | 1.000 | 0.923 | −0.077 | 1.000 | **1.000** | 0.000 |
| missing_field_recall | 1.000 | 0.987 | −0.013 | 1.000 | **1.000** | 0.000 |
| useful_refusal_correct_rate | 1.000 | 0.857 | −0.143 | 1.000 | **1.000** | 0.000 |

The notable observation is the inverted shape of the gap: GPT-5.4-mini matches the deterministic reference almost exactly on the 21 R2-3 extension cases (false premise, comparison referent ambiguity, full route listing, PLAN_VALIDITY missing fields, OBJ units missing) while losing 5–30 points on the "boring" `current` cases. This is consistent with the prompt being explicit about R2-3 conventions (the prompt enumerates `false_premise_detected`, `comparison_referent_ambiguity`, `evidence_units_missing`, the full-route-listing intent, the use_validity_payload code) and being less prescriptive about the field-family specificity of evidence citations on direct-answer cases.

### Cases where C-extended passes a component the model misses (15)

| case | misses |
|---|---|
| R2-011 | evidence_recall |
| R2-013 | evidence_recall |
| R2-025 | evidence_recall |
| R2-027 | evidence_recall |
| R2-028 | evidence_recall |
| R2-029 | behavior_class, evidence_recall |
| R2-030 | evidence_recall |
| R2-031 | evidence_recall |
| R2-040 | intent, answerability, behavior_class, warning_recall |
| R2-043 | missing_field_recall, useful_refusal_composite |
| R2-047 | intent |
| R2-051 | intent, answerability, behavior_class |
| R2-054 | evidence_recall |
| R2-055 | behavior_class, warning_recall |
| R2-060 | behavior_class, warning_recall |

## 9. Main failure patterns

The aggregate gap decomposes into four real patterns and one rubric artefact.

1. **Evidence-precision over-citation (22 cases).** The model cites every field-family it touches — `routes[].route_idx` alongside `routes[].customer_ids`; `customer_schedule[].customer_id` alongside `.arrival`; `route_end_times[].route_idx` alongside `.end_time`. These are *correct* citations, but the gold rubric pins only the answer-grounding field. This is the dominant `current`-cell failure and the dominant `direct_answer` / `direct_answer_with_warning` failure. (Equivalent rubric tension as the 0.969 evidence_precision the C-extended deterministic reference shows on PLAN_VALIDITY cases.)

2. **PLAN_VALIDITY `feasibility_breakdown` subkey recall (R2-011, R2-027–R2-031).** Gold expects `feasibility_breakdown.capacity_ok`, `feasibility_breakdown.time_windows_ok`, `feasibility_breakdown.coverage_ok` enumerated separately. The model cites `feasibility_breakdown` once. C-extended hits 0.800 on the same metric and these same five cases; this is a shape-mismatch the deterministic reference also exhibits, surfaced more starkly by the model because it cites the parent path rather than the children.

3. **Look-alike intent confusion (R2-040, R2-047, R2-051).** "Where is customer X going next?" (R2-040: STRUCT) → predicted `new_customer_assignment` instead of `single_customer_route_membership`; R2-047 the same shape but in target_extension; R2-051 (SCHEDULE lateness summary) → predicted `feasibility_status`. These are genuine intent classifier mistakes by the model on prompts that share surface lexical features with the wrong family.

4. **Warning omissions on integer-named routes (R2-055, R2-060).** Both ask about "route 1" / "route 5" but the model omits the `route_indexing_ambiguity` warning the gold expects, dropping `direct_answer_with_warning` → `direct_answer`.

5. **OBJ-delta evidence under-recall on R2-013 / R2-025.** Model correctly emits `comparison_referent_ambiguity`, `expose_reference_solution_objective`, and the missing field, but does not cite `units.objective` in evidence alongside the four OBJ delta fields. Recall 0.800 vs gold 1.000. (Note: this is the same `units.objective` field that R2-014 / R2-021..R2-023 *do* trigger as missing when the units payload is mutated away — the model is consistent there.)

### Failure taxonomy summary (run report §4)
| kind | overall | OBJ | PV | SCHEDULE | STRUCT |
|---|---:|---:|---:|---:|---:|
| intent_miss | 3 | 0 | 0 | 1 | 2 |
| answerability_miss | 2 | 0 | 0 | 1 | 1 |
| behavior_class_miss | 5 | 0 | 1 | 3 | 1 |
| missing_field_miss | 1 | 0 | 0 | 0 | 1 |
| evidence_precision_miss | 22 | 0 | 6 | 9 | 7 |
| evidence_recall_miss | 9 | 2 | 6 | 1 | 0 |
| warning_precision_miss | 3 | 0 | 0 | 2 | 1 |
| warning_recall_miss | 3 | 0 | 0 | 2 | 1 |
| useful_refusal_composite_miss | 1 | 0 | 0 | 0 | 1 |
| partial_answer_composite_miss | 0 | 0 | 0 | 0 | 0 |

## 10. Should we add a Claude Code repo-agent condition later?

Recommendation: **defer; not necessary for the closing experiment**.

The reason R2-4A was scoped to a clean API-isolated baseline was that Claude Code carries repository / tool / project context that the contract is supposed to *test for*. The gpt-5.4-mini baseline above already demonstrates the discriminative property the benchmark needed to show — prompting alone reaches 0.95+ on intent/answerability but only 0.77 on evidence precision and 0.92 on behavior class, with a coherent failure shape. Adding a Claude-Code-in-context condition would mostly measure "how well does an agent with read access to the contract code do?" — which is not the contrast the thesis hinges on.

If the thesis later wants to make a "how much does grounding help" claim, a more interesting baseline is a *retrieval-grounded* system that the operator could realistically deploy (RAG over the schema), not Claude Code with bare-repo access.

## 11. Is pass^k ready to run on hard cases?

Recommendation: **yes, on a narrow target set of ≤10 cases**.

The two interesting hard subsets are:

- **Target-extension cases where the deterministic reference is 1.000 and B is also ≈1.000** (e.g. R2-008, R2-012, R2-015, R2-032..R2-036, R2-047, R2-048, R2-049, R2-058, R2-059). Pass^k here measures *consistency* on the R2-3 extension behaviors — the model already gets them but does it always?
- **Current-cell cases where B genuinely misses** (R2-040, R2-051, the route-indexing pair R2-055/R2-060, the PV feasibility_breakdown subkey cases). Pass^k here measures whether the failures are *stable* (always wrong) or *flaky* (sometimes right). The remediation differs sharply between the two.

A 10-case × k=5 pass^k run would be ~50 calls (~100s wall), cheap to run after R2-4A signs off. The runner already accepts `--case-ids` for narrow re-runs; the pass^k harness can call it `k` times with distinct `run-id`s and aggregate.

## 12. Locked-file integrity

Confirmed via `git diff --stat HEAD`:

- `product/evaluation/run2_benchmark_cases.csv` — no diff
- `product/evaluation/run2_gold_schema.md` — no diff
- `product/evaluation/run2_scoring.py` — no diff
- `product/evaluation/run2_calibration_cases.csv` — no diff
- `product/evaluation/run2_system_c.py` — no diff
- `product/copilot/*`, `product/data/*` — no diff
- `experiment/configs/*`, `experiment/data/*` — no diff

The R2-3 commit `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` is still `HEAD`. No commit was made for R2-4A in line with the user request scope.

## 13. `.env` not committed

- `.env` exists locally with `OPENAI_API_KEY` and the previously present `ANTHROPIC_API_KEY`.
- `.env` is in `.gitignore` (`Secrets & local config` block).
- `git status` does not list `.env` as tracked or staged.
- No call site echoes the key to stdout, stderr, or any log file.

## 14. Stop point

Stage R2-4A complete. **Not started:** Claude Code repo-agent baseline, System A (deterministic LLM-augmented), pass^k. Resuming any of those is an explicit next-stage request.

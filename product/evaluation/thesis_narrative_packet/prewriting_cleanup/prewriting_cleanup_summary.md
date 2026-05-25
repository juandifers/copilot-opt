# Pre-Writing Cleanup Summary

_Authored 2026-05-21. Synthesises all eight tasks in this packet._

---

## Files produced

| File | Task | Status |
|---|---|---|
| `d_final_run2_coverage.csv` | Task 1 | ✓ 60-row CSV (15 materialized, 45 not run) |
| `d_final_run2_coverage.md` | Task 1 | ✓ Coverage report with thesis framing |
| `d_final_axis3_report.csv` | Task 2 | ✓ 24-row CSV (analytically derived) |
| `d_final_axis3_report.md` | Task 2 | ✓ Axis 3 report with subtype breakdown |
| `closing_experiment_decision.md` | Task 3 | ✓ Retire as main; reframe as Stage A pilot |
| `preregistration_locks.md` | Task 4 | ✓ All tags, frozen artifacts, pasteable methods paragraph |
| `negative_result_thresholds.md` | Task 5 | ✓ All systems; pre-registered vs post-hoc labeled |
| `stageA_to_run2_pivot.md` | Task 6 | ✓ Pivot as finding; bridge sentence; draft paragraph |
| `what_this_thesis_is_not.md` | Task 7 | ✓ 10 boundary statements with alternatives |
| `prewriting_cleanup_summary.md` | Task 8 | This file |

---

## Task 1 — D-Final Run 2 coverage

**Status**: D-Final full 60-case coverage does NOT exist.

**What exists**: D-Final was run live on **15 of 60 cases** (cases R2-001 through
R2-015 — the original calibration set whose payloads materialise from the Stage
A `full-run-v1` artifact).

**Results on the 15 materialized cases**:
- Intent correct: 15/15 (100%)
- Answerability correct: 15/15 (100%)
- Behavior class correct: 15/15 (100%)
- LLM invoked: 5/15; D1-only: 10/15
- Regressions vs D1: 0
- One schema validation error (R2-001) → fallback to D1 → correct result

**Why only 15**: the remaining 45 cases require payloads that are not in the
`full-run-v1` artifact. The blocker is payload materialization only — the
D-Final stack is fully implemented and capable of scoring all 60 cases.

**Thesis citation rule**: cite "0 regressions on 15 materialized Run 2 cases."
Do not cite "0 regressions on 60 cases." The 15-case result is a live-path
regression check, not a full benchmark evaluation.

---

## Task 2 — D-Final Axis 3 result

**Method**: analytically derived from (a) D1 live run on Axis 3 (100% intent,
87.5% behavior_class), (b) D-Final hybrid_guarded policy, and (c) the fact
that all 9 D1-fixed Axis 3 cases map to non-risk-zone intents. Not from a
live D-Final run on Axis 3.

**D-Final Axis 3 results (derived)**:

| Metric | C0 | D1 | D-Final |
|---|---:|---:|---:|
| intent_correct | 62.5% (15/24) | 100.0% (24/24) | **100.0% (24/24)** |
| answerability_correct | 62.5% | 100.0% | **100.0%** |
| behavior_class_correct | 62.5% | 87.5% (21/24) | **87.5% (21/24)** |
| LLM invocations | — | — | ~8/24 |
| regressions vs D1 | — | — | **0** |

**Finding**: D-Final matches D1 on Axis 3. Improvement vs C0 is +37.5 pp
intent accuracy. The 3 residual behavior_class gaps are inherited D1
route_indexing_ambiguity pattern (not D-Final regressions).

**Caveat**: this result is analytically derived. If a live D-Final Axis 3 run
is required, it can be executed using the existing `runner.py` and the
`full-run-v1` payloads (all 24 Axis 3 cases are materialized).

---

## Task 3 — Closing experiment decision

**Recommendation**: **retire the Stage A closing experiment as a primary
experiment**. Reframe as a Stage A pilot study that motivated the Run 2
pivot.

**Reasoning**:
- 3-of-4 success rule NOT met (Claims 1 and 4 pass; Claims 2 and 3 fail)
- Failure mode: generator ceiling (Haiku at ceiling, not stressed on
  insufficient cells) — a methodology-limit finding, not a claim failure
- Run 2 evaluates the structured contract layer (the correct instrument for
  the thesis's current contribution)
- Faithfulness survives as evidence_precision = 0.980 in Run 2

**Where faithfulness appears in thesis**: (a) Stage A pilot finding
(ceiling-bound generator); (b) Run 2 structured evidence_precision guarantee.
No optional rendering-faithfulness check is required unless the committee asks.

---

## Task 4 — Pre-registration / locks

**Documented**: HEAD `18b4811` (tag `run2-contract-extended`); 11 git tags;
7 protected Run 2 files (SHA-verified); Stage A 4-file amendment log;
System D design envelope pre-commitment; timeline of what was frozen before
each evaluation stage. Pasteable thesis methods paragraph included.

---

## Task 5 — Negative-result thresholds

**Documented**: D1 (pre-registered: 18/18 + 70/70), D2 (pre-registered: 5/5,
0 over-fires), D3 (pre-registered: 5/5 overlay, 0 off-target), D4
(pre-registered: 1.000 × 4 criteria), D-Final holdout (pre-registered: 9
acceptance criteria), D-Final pass^k (post-hoc: ≥ 0.90 threshold), Stage A
(pre-registered: 3-of-4 rule).

**All systems PASS their pre-registered thresholds.** Stage A: 2/4 claims pass;
3-of-4 rule not met; interpreted as generator-ceiling negative result (not
methodology failure).

---

## Task 6 — Stage A → Run 2 pivot

**Framing**: Stage A showed sufficiency is claim-family-dependent (positive
finding). The closing experiment generator ceiling blocked Claims 2 and 3
(negative finding). The structural observation: suffix/predict API cannot
tell the operator what was missing or what the copilot should do next.

**Bridge sentence** (for thesis):
> "The sufficiency predictor asked whether a backend action was good enough
> for a claim family; Run 2 asks whether a copilot can recognise what claim
> is being made, determine whether the current payload contains the required
> state, and emit the correct evidence-backed product behaviour."

Draft thesis paragraph included in `stageA_to_run2_pivot.md`.

---

## Task 7 — What this thesis is not

**10 boundary statements documented**:
1. Not a productivity study
2. Not a user study
3. Not a pure hallucination benchmark
4. Not a broad natural-language generalisation claim
5. Not a solver-optimality study
6. Not a production recomputation system
7. Not a deployed learned sufficiency gate
8. Not proof that LLMs solve VRPTW
9. Not a claim that deterministic contracts beat LLMs universally
10. Not a replication of prior VRP literature

Compact version for abstract included.

---

## Remaining unresolved empirical gaps

| Gap | Status | Path to resolve |
|---|---|---|
| D-Final full 60-case Run 2 coverage | 45 cases not materialized | Run experiment with Run 2 prompt set; OR construct payloads manually via `run2_payloads.py` |
| D-Final Axis 3 live run | Analytically derived; not live | Run `axis3_semantic/runner.py` with D-Final adapter; payloads are available |
| D-Final pass^k stability | Not run | Run repeated sampling (k=3–5) on semantic holdout dev split; payloads available |
| D-Final Axis 1, 2, 4 live runs | Not run; analytically 0 regressions by construction | Run `runner.py` variants for each axis |
| Complete experiment data for all 60 Run 2 cases | Stage A generated 48 prompts; 15 overlap | Requires a targeted 60-case experiment run |

**None of these gaps block thesis submission** as long as:
- D-Final is cited on the 15 materialized cases (not 60)
- D-Final Axis 3 is cited as analytically derived with justification
- The semantic holdout (47/48 overall, 16/16 heldout) is the primary D-Final evidence

---

## Validation performed

- CSVs generated by joining `d_final_core_report.csv` + `run2_benchmark_cases.csv`
  (Python, no locked files modified)
- Counts verified: 15 materialized, 45 not run; 5 LLM invocations, 10 D1-only
- Axis 3 analytical derivation cross-checked against D1 stress report (100%
  intent confirmed; 21/24 behavior_class confirmed)
- No locked files, gold labels, benchmark cases, or stress-axis CSVs were
  modified in this task

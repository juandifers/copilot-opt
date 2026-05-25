# D-Final — Full Run 2 60-Case Coverage Report

_Authored 2026-05-21. Source CSVs: `d_final_core_report.csv` (15 cases, live
run), `run2_benchmark_cases.csv` (60 cases, gold). Coverage CSV:
`d_final_run2_coverage.csv` (60 rows)._

---

## Required statements for thesis prose

> **Run 2 remains a 60-case locked benchmark.**
> The benchmark cases, gold labels, scorer, and payload materialisation paths
> are immutable from R2-2 onward at HEAD `18b4811` (tag `run2-contract-extended`).

> **The 15-case materialized subset IS a live-path sanity check.**
> D-Final was run live (with LLM calls) on the 15 Run 2 cases whose payloads
> materialise from the Stage A `full-run-v1` artifact. This confirms the
> end-to-end D-Final stack is wired correctly; it is not a claim about 60-case
> performance.

> **D-Final full 60-case coverage is NOT available.**
> 45 of 60 cases are not materialized from the available experiment artifact.
> D-Final has not been run on those 45 cases.

> **What number should be cited in the thesis:**
> "D-Final shows 0 regressions on the 15 Run 2 cases whose payloads are
> available from the Stage A experiment run (15/15 intent correct, 15/15
> answerability correct, 15/15 behavior class correct)."
> Do NOT state "0 regressions on 60 cases."

---

## 1. Materialization summary

| Group | n | D-Final ran | LLM invoked | D1-only | Intent correct |
|---|---:|:---:|---:|---:|---:|
| Materialized (cases R2-001–R2-015) | 15 | ✓ | 5 | 10 | **15/15 (100%)** |
| Unmaterialized | 45 | ✗ | — | — | not run |
| **Total** | **60** | — | — | — | 15/15 on available |

---

## 2. Why only 15 cases are materialized

Run 2 benchmark cases are scored against structured payloads produced by the
Stage A experiment runner (`full-run-v1` artifact,
`experiment/results_RUN1/generator/full-run-v1.jsonl`). That run covered 48
prompts. The Run 2 benchmark was expanded from a 15-case calibration set to
60 cases; only the original calibration cases' source prompts align with
Stage A prompt IDs in the artifact.

The 45 unmaterialized cases would require:
1. A separate experiment run targeting the Run 2 prompt set (48→60 prompts),
   OR
2. Manual payload construction for each of the 45 cases using
   `product/evaluation/run2_payloads.py`.

Neither has been performed. The blocker is exclusively **payload
materialization**: the evaluation framework and D-Final stack are both capable
of processing all 60 cases.

---

## 3. Classification of the 45 unmaterialized cases

| Category | Count | Notes |
|---|---:|---|
| Payload not in `full-run-v1` (no generator record) | 45 | All R2-016 through R2-060 not in first 15 |
| Blocked by API path | 0 | API path works; not the bottleneck |
| Blocked by D-Final implementation | 0 | Implementation complete |
| Not yet run (payload available but run skipped) | 0 | All 45 are payload-blocked |

---

## 4. D-Final results on the 15 materialized cases

| Metric | Value | Notes |
|---|---:|---|
| intent_correct | **15/15 (100%)** | |
| answerability_correct | **15/15 (100%)** | |
| behavior_class_correct | **15/15 (100%)** | |
| evidence_precision | same as D1 (see below) | not separately computed |
| LLM invoked | 5/15 | risk-zone intents |
| D1-only (no LLM) | 10/15 | D1 confident, not risk-zone |
| regressions vs D1 | **0** | |
| schema violations | **1/15** (R2-001) | LLM schema error → fallback to D1; D1 was correct |

**Note on evidence metrics**: the D-Final evaluation runner records
predicted contract fields (`predicted_answerability`, `predicted_behavior_class`)
but does not separately compute evidence_precision/recall for the core run.
Since D-Final inherits all downstream processing from D1/D2/D3/D4 (same
deterministic pipeline), and D1 produces 0 regressions on the full 60-case Run
2 benchmark (1.000 on all metrics), the evidence metrics for the 15
materialized cases are the same as D1's core Run 2 report values.

---

## 5. What can and cannot be claimed

### Can be claimed

- D-Final shows **zero regressions** on the 15 materialized Run 2 cases.
- D-Final is the same or better than D1 on every materialized case (by
  construction of hybrid_guarded: D-Final only accepts an LLM frame if it
  matches D1 or improves on an unknown/risk-zone D1 output).
- The end-to-end D-Final pipeline (LLM adapter → D2 → D3 → D4 → D5) is
  verified to run correctly.
- D-Final's primary performance evidence is the **semantic holdout
  (47/48 overall, 16/16 heldout)**, not the 15-case Run 2 subset.

### Cannot be claimed

- D-Final shows 0 regressions on **all 60** Run 2 cases (untested).
- D-Final has been benchmarked against the full Run 2 benchmark.
- D-Final's 100% materialized-subset result generalises to the 45 unmaterialized
  cases (though 0 regressions is expected by D1 construction).

---

## 6. Recommended thesis framing

For the thesis narrative, the D-Final Run 2 paragraph should read approximately:

> "D-Final was evaluated on the 15 Run 2 benchmark cases whose payloads
> materialise from the Stage A experiment run. On this subset, D-Final
> produces 15/15 intent, answerability, and behavior-class correct results,
> with zero regressions relative to D1. Full 60-case D-Final coverage is
> deferred: the remaining 45 cases require a dedicated payload materialisation
> run beyond the Stage A artifact. The primary evaluation of D-Final's
> natural-language generalisation is the 48-case semantic holdout, where
> D-Final achieves 97.9% accuracy overall and 100% on the sequestered heldout
> split."

---

## 7. Per-case detail for materialized cases

| case_id | family | impl_status | LLM invoked | adapter_source | intent_correct | ans_correct | beh_correct | regression |
|---|---|---|:---:|---|:---:|:---:|:---:|:---:|
| R2-001 | OBJ | current | ✓ | d1 (fallback) | ✓ | ✓ | ✓ | none |
| R2-002 | OBJ | current | ✓ | llm | ✓ | ✓ | ✓ | none |
| R2-003 | STRUCT | current | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-004 | STRUCT | current | ✓ | llm | ✓ | ✓ | ✓ | none |
| R2-005 | STRUCT | current | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-006 | SCHEDULE | current | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-007 | SCHEDULE | current | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-008 | SCHEDULE | target_extension | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-009 | STRUCT | current | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-010 | STRUCT | target_extension | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-011 | PLAN_VALIDITY | current | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-012 | PLAN_VALIDITY | target_extension | ✗ | d1 | ✓ | ✓ | ✓ | none |
| R2-013 | OBJ | target_extension | ✓ | llm | ✓ | ✓ | ✓ | none |
| R2-014 | OBJ | target_extension | ✓ | llm | ✓ | ✓ | ✓ | none |
| R2-015 | SCHEDULE | target_extension | ✗ | d1 | ✓ | ✓ | ✓ | none |

Note: R2-001 used D1 fallback because the LLM returned a schema-invalid frame
(1 schema validation error). D1 was correct → no regression.

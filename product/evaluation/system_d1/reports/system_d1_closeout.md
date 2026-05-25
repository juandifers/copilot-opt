# System D1 — Closeout

_Frozen baseline_: HEAD `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`
(tag `run2-contract-extended`). Authored 2026-05-21.

## 1. Purpose

System D1 is the first implementation step under the System D
envelope. It layers a deterministic semantic intent adapter on top
of the existing C0 keyword classifier so that paraphrased,
implicit-comparator, and movement-style prompts route to the right
canonical intent without touching the deterministic answerability,
evidence, warning, or refusal-policy contract.

Predicted leverage (per the cross-axis synthesis, §11 Option A):

  46 / 96 C0-only guard-protected → 64 / 96 (47.9% → 66.7%)

Observed: **64 / 96** C0-side guard-protected after D1 (matches
prediction exactly).

## 2. Scope

**Changed** (the only files D1 touches):

- `product/copilot/intent.py` — appended `infer_intent_d1` and
  `infer_intent_d1_frame`. The existing `infer_intent` C0
  function is unchanged.
- `product/copilot/query_frame.py` — new types-only module.
- `product/copilot/semantic_intent_adapter.py` — new deterministic
  adapter + routing policy.
- `product/evaluation/system_d1/` — new evaluation harness, design
  doc, and reports.
- `tests/system_d1/` — new D1 test suite.

**Not changed** (acceptance asserted by `tests/system_d1/test_d1.py`):

- Every locked Run 2 artifact (`run2_benchmark_cases.csv`,
  `run2_gold_schema.md`, `run2_scoring.py`, `run2_case_loader.py`,
  `run2_payloads.py`, `run2_system_c.py`,
  `run2_calibration_cases.csv`).
- Every R2-S `cases.csv` (Axes 1, 2, 3, 4).
- Every downstream contract module: `product/copilot/refusal_policy.py`,
  `product/data/evidence.py`, `product/data/product_schema.py`,
  `product/data/answerability.py`, `product/data/entity_resolution.py`.

## 3. Target failure set (n = 18)

D1 targets the 18 `system_d_addressable_intent` cases identified in
§4 of the cross-axis synthesis. Grouped by semantic pattern:

| Group | Cases (gold intent) |
|---|---|
| **OBJ comparator / value** | A1D-11 / A1D-12 / A1H-11 (`objective_value` — recover value when incidental comparative wording mis-fires); A2D-08 / A2H-08 (`objective_delta` — promote implicit comparator) |
| **STRUCT movement / before-after** | A2D-06 / A2H-05 / A2H-06 (`before_after_comparison` from non-comparative movement / reassignment / past-tense-before wording); A2H-09 (`before_after_comparison` from `shift versus prior`) |
| **SCHEDULE / STRUCT paraphrase tail** | S1D-07 / S1H-07 / S1H-08 (`full_route_listing`); S1D-08 / S1D-09 / S1H-09 / S1H-10 (`route_end_time` via completion verbs / bare-finish predicate); S1D-12 / S1H-12 (`lateness_summary` via behind-schedule / after-allowed-time phrasing) |

## 4. Must-not-regress set (n = 70)

D1 must preserve the 70-case `must_not_regress_guard_protected`
cohort from the synthesis. Composition:

| Axis / system | n | Preservation mechanism |
|---|---:|---|
| axis1_lookalike — C0 | 18 | C0 customer-number guard + listing-phrase precedence + family-routing dominance, unchanged |
| axis2_ood_premises — C0 | 11 | R2-3 false-premise extension; `comparison_referent_ambiguity`; `unsupported_comparison`; `missing_validity_fields` refusal |
| axis3_semantic — C0 | 11 | Intent classifier routed correctly under C0; D1 confirms or preserves |
| axis4_payload — C0 | 24 | Full structured payload + deterministic contract logic — D1 does not modify either |
| axis4_payload — model-A | 6 | **Preserved by construction** — D1 does not run model A; the A-side result is unaffected |

Total: 18 + 11 + 11 + 24 + 6 = **70**.

## 5. Method

### 5.1 Code paths changed

D1 introduces three new code units:

1. `QueryFrame` (`product/copilot/query_frame.py`) — bookkeeping
   for the classifier's decision (source, override flag, comparison
   type, adapter notes).
2. `classify_semantic` / `decide_d1_intent`
   (`product/copilot/semantic_intent_adapter.py`) — deterministic
   semantic adapter organised around five canonical query frames:
   OBJ value, OBJ delta, STRUCT movement, SCHEDULE route-end,
   SCHEDULE lateness, STRUCT full-route-listing.
3. `infer_intent_d1` / `infer_intent_d1_frame`
   (`product/copilot/intent.py`) — the seam the evaluation runner
   calls. C0's `infer_intent` is untouched.

The downstream contract path (`compute_answerability` →
`compose_suggestions` → `build_evidence_items` → `build_warnings` →
`build_useful_refusal` → `_infer_behavior_class`) is called
**unchanged**; the only difference between System C0 and System D1
is the intent string those functions receive.

### 5.2 What D1 did NOT do

- **No solver calls.** D1 does not depend on pyvrp or any solver.
- **No gold / case / scoring modifications.** Every locked Run 2
  CSV, gold schema, scorer, and case loader is unchanged
  (verified by the test suite via `git diff --exit-code`).
- **No model adapter.** The deterministic adapter cleared the
  18/18 target on its own, so the optional LLM Structured Output
  adapter (§5.4 in the task brief) is **not** implemented in D1.
  It can be slotted into the same `decide_d1_intent` seam in a
  follow-up if a future stress axis surfaces paraphrases the
  deterministic banks cannot cover.

## 6. Results on Run 2 core (n = 60)

D1 vs C0 on the locked 60-case benchmark
(`run2_benchmark_cases.csv`):

| metric | C0 | D1 | delta |
|---|---:|---:|---:|
| intent_accuracy | 1.000 | 1.000 | +0.0000 |
| answerability_accuracy | 1.000 | 1.000 | +0.0000 |
| behavior_class_accuracy | 1.000 | 1.000 | +0.0000 |
| evidence_precision | 0.980 | 0.980 | +0.0000 |
| evidence_recall | 1.000 | 1.000 | +0.0000 |
| warning_precision | 1.000 | 1.000 | +0.0000 |
| warning_recall | 1.000 | 1.000 | +0.0000 |
| missing_field_recall | 1.000 | 1.000 | +0.0000 |

- `core_run2_regressions` = **0**. The 0.980 evidence_precision is a
  pre-existing C0 artefact carried verbatim into D1 (D1 does not
  change evidence selection); no new artefact is introduced.
- The adapter is invoked on a handful of OBJ value/delta and
  STRUCT before-after cases but always confirms the C0 intent on
  Run 2 core — no override changes the predicted intent.

## 7. Results on stress axes (D1 vs C0)

Per-axis intent / answerability / behavior_class accuracy:

| axis | n | C0 intent | D1 intent | C0 ans | D1 ans | C0 beh | D1 beh |
|---|---:|---:|---:|---:|---:|---:|---:|
| axis1_lookalike | 24 | 0.875 | **1.000** | 1.000 | 1.000 | 1.000 | 1.000 |
| axis2_ood_premises | 24 | 0.750 | **1.000** | 0.750 | **0.917** | 0.750 | **0.917** |
| axis3_semantic | 24 | 0.625 | **1.000** | 0.625 | **1.000** | 0.625 | **0.875** |
| axis4_payload | 24 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Per-axis intent-correct delta vs C0:

| axis | C0 | D1 | Δ |
|---|---:|---:|---:|
| axis1_lookalike | 21/24 | 24/24 | **+3** |
| axis2_ood_premises | 18/24 | 24/24 | **+6** |
| axis3_semantic | 15/24 | 24/24 | **+9** |
| axis4_payload | 24/24 | 24/24 | 0 |
| **total** | **78/96** | **96/96** | **+18** |

The +18 stress-side intent gain matches the predicted set exactly
— the 18 `system_d_addressable_intent` cases identified in the
synthesis.

## 8. Target-18 analysis

All 18 target cases are now intent-correct. Per-case before/after
intent (C0 → D1, gold in parens):

| case_id | axis | gold | C0 | D1 | downstream fully perfect? |
|---|---|---|---|---|:-:|
| A1D-11 | axis1_lookalike | objective_value | objective_delta | objective_value | ✓ |
| A1D-12 | axis1_lookalike | objective_value | objective_delta | objective_value | ✓ |
| A1H-11 | axis1_lookalike | objective_value | objective_delta | objective_value | ✓ |
| A2D-06 | axis2_ood_premises | before_after_comparison | single_customer_route_membership | before_after_comparison | ✓ |
| A2H-05 | axis2_ood_premises | before_after_comparison | single_customer_route_membership | before_after_comparison | ✓ |
| A2H-06 | axis2_ood_premises | before_after_comparison | unknown | before_after_comparison | ✓ |
| A2D-08 | axis2_ood_premises | objective_delta | objective_value | objective_delta | ✓ |
| A2H-08 | axis2_ood_premises | objective_delta | objective_value | objective_delta | ✓ |
| A2H-09 | axis2_ood_premises | before_after_comparison | unknown | before_after_comparison | ✓ |
| S1D-07 | axis3_semantic | full_route_listing | unknown | full_route_listing | ✓ |
| S1D-08 | axis3_semantic | route_end_time | unknown | route_end_time | ✗ (see §10) |
| S1D-09 | axis3_semantic | route_end_time | unknown | route_end_time | ✗ (see §10) |
| S1D-12 | axis3_semantic | lateness_summary | unknown | lateness_summary | ✓ |
| S1H-07 | axis3_semantic | full_route_listing | unknown | full_route_listing | ✓ |
| S1H-08 | axis3_semantic | full_route_listing | unknown | full_route_listing | ✓ |
| S1H-09 | axis3_semantic | route_end_time | unknown | route_end_time | ✓ |
| S1H-10 | axis3_semantic | route_end_time | unknown | route_end_time | ✗ (see §10) |
| S1H-12 | axis3_semantic | lateness_summary | unknown | lateness_summary | ✓ |

- **15 / 18** are fully perfect on every D1 metric.
- **3 / 18** (S1D-08, S1D-09, S1H-10) have intent and answerability
  correct after D1 but a residual `route_indexing_ambiguity`
  warning gap — see §10.

## 9. Regression analysis

- **Core Run 2**: 0 regressions (60/60 fully perfect under D1, as
  under C0).
- **Must-not-regress 70 cohort**: 70/70 preserved.
  - 64 / 64 C0-side cases preserved on every metric.
  - 6 / 6 axis4-A cases preserved by construction (D1 does not
    run model A).
- **Stress axes**: every C0-correct case stays correct under D1.
  No case that was previously guard-protected is now broken.

## 10. Out-of-scope failures

Per the System D envelope and the cross-axis synthesis, D1 does
NOT claim to fix:

| Out-of-scope bucket | n | Observed behaviour under D1 |
|---|---:|---|
| `out_of_envelope_answerability` (false-premise on non-entity-bound intents) | 2 | A2D-03 (`lateness_summary`) and A2H-02 (`feasibility_status`) still answer where they should refuse. Fixing requires extending `_CUSTOMER_BOUND_INTENTS` / `_ROUTE_BOUND_INTENTS` in `product/data/answerability.py` and `product/copilot/refusal_policy.py` — both protected files. **D2 work.** |
| `schema_gap` (Band-4 causal-explanation) | 5 | A2D-10, A2D-11, A2D-12, A2H-11, A2H-12 are scored against downgraded gold; C0 already perfect on every metric and D1 preserves that. **Stage R2-2 schema future work**, not System D. |
| `model_projection_failure` (Axis 4 A / B) | 42 | D1 does not run model A or B. **Out of scope.** |
| `downstream_evidence_artifact` (intent + ans correct, but a documented downstream evidence/warning quirk) | 7 | C0's original 7 (A1D-10, A1H-10, A1H-12, S1D-02, S1D-03, S1H-03, S1H-04) are preserved under D1. The behaviour mirrors C0 because D1 does not change downstream evidence selection. |
| **New downstream-warning gap surfaced by D1's intent fix** | 3 | S1D-08, S1D-09, S1H-10. After D1 routes these `route_end_time` paraphrases correctly, the downstream `route_indexing_ambiguity` warning fails to fire because `refusal_policy._references_route_by_number` requires the literal token `route N`; the paraphrases use `vehicle 1` / `truck 1`. Behaviour class drops from gold `direct_answer_with_warning` to D1's `direct_answer`. This is a `refusal_policy.py` (protected) change — **D2 / refusal-policy follow-up**, not System D. |

## 11. System D implication

**D1 is sufficient for the in-envelope intent target** described
in the synthesis. It clears 18/18 target cases, preserves 70/70
must-not-regress, lifts C0-only guard-protected from 46/96 to the
predicted 64/96 (47.9% → 66.7%), and adds 0 regressions on Run 2
core.

**D1 is NOT sufficient on its own** for the remaining 7 + 2 + 5 =
14 buckets listed in §10. Specifically:

- **D2 (answerability extension).** The 2 `out_of_envelope_answerability`
  cases (A2D-03, A2H-02) need the false-premise check widened to
  non-entity-bound intents. Locus: `product/data/answerability.py`
  + `product/copilot/refusal_policy.py`.
- **D2 (warning extension).** The 3 newly-surfaced `route_end_time`
  paraphrase cases (S1D-08, S1D-09, S1H-10) need
  `_references_route_by_number` to accept `vehicle|truck N` so
  `route_indexing_ambiguity` fires on paraphrased entity wording.
  Locus: `product/copilot/refusal_policy.py`.
- **D3 (schema extension).** The 5 `schema_gap` cases need a new
  `causal_mechanism_unsupported` warning code (and possibly an
  `unserved_customer_listing` / `reassignment_listing` intent).
  Locus: `product/evaluation/run2_gold_schema.md` + the warning
  enum.

The 42 Axis-4 model-projection failures are a separate, larger
workstream (projection redesign, evidence post-validation, warning
post-validation, prior-lock enforcement) and not part of any near-
term System D follow-up.

## 12. Reproduction

```bash
# 1. Run the D1 evaluation end to end (writes reports/ + failure map)
.venv/bin/python -m product.evaluation.system_d1.run_system_d1

# 2. Run the D1 test suite (49 tests — adapter unit, target-18,
#    must-not-regress, core, Axis 4, protected-file integrity)
.venv/bin/python -m pytest tests/system_d1/ -q

# 3. Re-run the existing C0 axis runners — they share the C0
#    classifier, so they should produce identical reports to HEAD.
.venv/bin/python -m product.evaluation.run2_stress.axis1_lookalike.runner
.venv/bin/python -m product.evaluation.run2_stress.axis3_semantic.runner

# 4. Inspect D1 reports
ls product/evaluation/system_d1/reports/
column -s, -t product/evaluation/system_d1/reports/system_d1_stress_report.csv | head -10
```

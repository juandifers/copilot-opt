# System D2 — Closeout

_Authored 2026-05-21 on top of `system_d1_closeout.md`. Frozen
baseline: HEAD `18b4811` plus the D1 additions._

## 1. Purpose

D2 extends D1 into the downstream contract layer with two narrow
additions that fix the five D1-remaining failures flagged in
`system_d1_closeout.md` §11:

1. Widen the false-premise check so `lateness_summary` and
   `feasibility_status` prompts that name a customer absent from the
   payload are treated as false premises (A2D-03, A2H-02).
2. Extend `route_indexing_ambiguity` to fire on `vehicle N` and
   `truck N` paraphrases in addition to literal `route N`
   (S1D-08, S1D-09, S1H-10).

D2 does not touch evidence selection, schema, scoring, or payload
projection; it does not add any new behavior_class enum value; it
does not call a solver or a model.

## 2. Scope

| Surface | n | Treatment |
|---|---:|---|
| Locked Run 2 core | 60 | C0 / D1 / D2 reproduced side-by-side. Acceptance: 0 regressions. |
| Axis 1 look-alike | 24 | C0 / D1 / D2. |
| Axis 2 OOD premises | 24 | C0 / D1 / D2. |
| Axis 3 semantic | 24 | C0 / D1 / D2. |
| Axis 4 payload (C0 only) | 24 | C0 / D1 / D2. Acceptance: 0 regressions. |
| Total | 156 | |

## 3. What changed

- New `product/evaluation/system_d2/d2_answerability.py` —
  wrapper that adds the false-premise widening on top of the
  unchanged `compute_answerability`.
- New `product/evaluation/system_d2/d2_refusal_policy.py` —
  wrapper that adds `vehicle N` / `truck N` detection on top of
  the unchanged `build_warnings`, plus the corresponding
  useful-refusal shape on top of the unchanged
  `build_useful_refusal`.
- New `product/evaluation/system_d2/d2_system_c.py` — pipeline
  that uses D1's intent classifier and D2's downstream wrappers.
- New `product/evaluation/system_d2/run_system_d2.py` —
  evaluation harness.
- New `tests/system_d2/test_d2.py` — D2 acceptance suite.

## 4. What did not change

- `product/copilot/refusal_policy.py` — byte-identical to D1's
  protected version (verified by `git diff --exit-code`).
- `product/data/answerability.py` — byte-identical.
- All other downstream contract files (`product/data/evidence.py`,
  `product/data/product_schema.py`,
  `product/data/entity_resolution.py`,
  `product/copilot/contracts.py`) — byte-identical.
- All locked Run 2 artefacts — byte-identical.
- All Axis 1/2/3/4 `cases.csv` — byte-identical.
- D1 modules — unchanged. The existing
  `tests/system_d1/test_d1.py` suite still passes.

## 5. D2 target-5 cases

| case_id | axis | family | D1 outcome | D2 outcome |
|---|---|---|---|---|
| A2D-03 | axis2_ood_premises | SCHEDULE | intent correct (`lateness_summary`), answerability wrong (predicted `answerable` instead of `not_answerable`), no warnings, wrong behavior class | answerability fixed → `not_answerable`, `false_premise_detected` fires, `clarify_false_premise` next action, behavior class → `useful_refusal` |
| A2H-02 | axis2_ood_premises | PLAN_VALIDITY | intent correct (`feasibility_status`), answerability wrong, no warnings, wrong behavior class | same shape as A2D-03, fully fixed |
| S1D-08 | axis3_semantic | SCHEDULE | intent + answerability correct (`route_end_time`/`answerable`), warning missing, wrong behavior class | `route_indexing_ambiguity` fires, behavior class → `direct_answer_with_warning` |
| S1D-09 | axis3_semantic | SCHEDULE | same as S1D-08 | fully fixed |
| S1H-10 | axis3_semantic | SCHEDULE | same as S1D-08 (prompt uses `truck 1`) | fully fixed |

D2 target-5 fixed count: **5 / 5** (100%).

## 6. Results vs D1

### 6.1 Per-axis aggregate

| axis | n | C0 int | D1 int | D2 int | C0 ans | D1 ans | D2 ans | C0 beh | D1 beh | D2 beh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| axis1_lookalike | 24 | 0.875 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| axis2_ood_premises | 24 | 0.750 | 1.000 | 1.000 | 0.750 | 0.917 | **1.000** | 0.750 | 0.917 | **1.000** |
| axis3_semantic | 24 | 0.625 | 1.000 | 1.000 | 0.625 | 1.000 | 1.000 | 0.625 | 0.875 | **1.000** |
| axis4_payload | 24 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

D2 lifts behavior_class to perfect on axis 2 and axis 3.
Intent and evidence stay at D1's already-perfect numbers. Axis 1
and Axis 4 are unchanged from D1.

### 6.2 Cohort metrics

- D1 target-18 preserved under D2: **18 / 18**.
- must_not_regress_70 preserved under D2: **70 / 70**
  (64 C0-side + 6 axis4-A by construction).
- D2 target-5 fixed: **5 / 5**.

## 7. Run 2 core regression check

- core_run2_regressions under D2 vs C0: **0**.
- core_run2 metric set per case is fully identical to D1 on all
  60 cases (no new firings on Run 2 core).

| metric | C0 | D1 | D2 |
|---|---:|---:|---:|
| intent_accuracy | 1.000 | 1.000 | 1.000 |
| answerability_accuracy | 1.000 | 1.000 | 1.000 |
| behavior_class_accuracy | 1.000 | 1.000 | 1.000 |
| evidence_precision | 0.980 | 0.980 | 0.980 |
| evidence_recall | 1.000 | 1.000 | 1.000 |
| warning_precision | 1.000 | 1.000 | 1.000 |
| warning_recall | 1.000 | 1.000 | 1.000 |
| missing_field_recall | 1.000 | 1.000 | 1.000 |

## 8. Axis 4 regression check

- axis4_d2_perfect: **24 / 24** (same as C0 and D1).
- axis4_regressions: **0** (no case that was perfect under C0
  drops to imperfect under D2).
- Adapter never fires on axis 4 prompts (D1 inheritance).

## 9. Over-firing checks

- D2-introduced `route_indexing_ambiguity` over-fires: **0**.
- D2-introduced `false_premise_detected` over-fires: **0**.
- Pre-existing C0 over-fires inherited unchanged (not
  attributable to D2): 1 case (A2H-06, `route_indexing_ambiguity`
  fires because the prompt contains literal `Route 1`; this is a
  pre-existing C0 behaviour and is not a D2 introduction).

D2's widened false-premise check requires an explicit
`customer N` token; generic lateness / feasibility prompts (`Is
anyone going to be late?`, `Is the plan feasible?`) never trigger
it. D2's `vehicle N` / `truck N` regex requires a bare integer;
ordinal phrasings (`the first vehicle`) and plural ranges
(`vehicles 1-4`) do not trigger.

## 10. Remaining failures (post-D2)

All explicitly out of D2's envelope:

- 5 Axis-2 Band-4 causal-explanation `schema_gap` cases (A2D-10,
  A2D-11, A2D-12, A2H-11, A2H-12) — these require a schema-v2
  causal extension. Addressed by **D3** (next step).
- 42 Axis-4 A/B `model_projection_failure` cases — out of D2's
  scope (D2 is C0-like; no model is run on the A/B sides).

## 11. D3 handoff

D2's downstream wrappers leave the same contract surface that D3
will hook. D3 layers on:

- new `causal_mechanism_unsupported` warning code (no schema
  enum change required — warnings is `list[str]`),
- new `expose_causal_diagnostics` next-action code (deferred —
  no schema action enum change required either),
- a versioned axis2 causal gold overlay
  (`axis2_causal_gold_overlay.csv`) that the D3 scorer adapter
  consumes for the 5 schema-gap cases.

D3 will not modify D2's wrappers; it ships its own
`d3_refusal_policy_causal` extension and a thin `d3_system_c`
pipeline that uses D1 intent + D2 answerability + D2 warnings +
D3 causal warning.

## 12. Reproduction

```bash
# Evaluate D2 end to end (C0, D1, D2 side-by-side on 156 cases)
.venv/bin/python -m product.evaluation.system_d2.run_system_d2

# Run the D2 test suite
.venv/bin/python -m pytest tests/system_d2/ -q

# Read reports
ls product/evaluation/system_d2/reports/
```

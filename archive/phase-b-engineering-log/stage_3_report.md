# Stage 3 Report — A-008: B2 threshold layer

**Date**: 2026-05-26
**Stage**: 3
**Status**: implementation complete; awaiting review before commit + Stage 4
**Working tree**: uncommitted per Phase B plan directive

This report covers A-008 Part B — the threshold layer implementation
that converts payload metrics into operator-facing acceptability
verdicts. Part A (the rationale doc) was reviewed and accepted in the
prior turn.

---

## 1. Headline numbers

**Combined strict useful: 57.6% — EXCEEDS the Stage 4 thesis primary
target (≥55%) by 2.6pp.**

| Metric | Stage 0.5 baseline | Post-A-008 (Stage 3 final) | Δ | Stage 4 target |
|---|---|---|---|---|
| **Combined strict useful** | 31.4% | **57.6%** | +26.2pp | **≥55% EXCEEDS** |
| LLM-off strict useful | 19.5% | 39.8% | +20.3pp | ≥45% (close, −5.2pp) |
| LLM-on strict useful | 35.4% | 63.5% | +28.1pp | ≥60% **EXCEEDS** |
| Combined heuristic useful | 40.6% | 44.7% | +4.1pp | ≥65% (gap from heuristic over-credit removal) |
| Combined strict wrong | 25.3% | 15.8% | −9.5pp | n/a |

Per-category strict useful change vs the cumulative Phase B baseline:

| Category | Pre-Stage-1 (Stage 0.5) | Post-Stage-2 | Post-Stage-3 (final) | Δ from Stage 0.5 | Stage 4 target | Status |
|---|---|---|---|---|---|---|
| **evaluation** | **0.0%** | 0.0% | **85.0%** | **+85.0pp** | ≥65% | **EXCEEDS by 20pp** |
| counterfactual | 66.7% | 100.0% | 100.0% | +33.3pp | (no target) | EXCEEDED |
| specific_diagnosis | 94.2% | 94.2% | 94.2% | 0 | invariant | preserved |
| orientation | 70.5% | 71.0% | 73.3% | +2.8pp | invariant | preserved |
| comparison | 62.9% | 62.9% | **73.6%** | +10.7pp | ≥75% | close (−1.4pp) |
| prioritized_diagnosis | 0.0% | 36.4% | 36.4% | +36.4pp | ≥75% | gap; ranking-aspect-bound |
| risk_fragility | 0.0% | 13.3% | 13.3% | +13.3pp | ≥60% | gap; ranking-aspect-bound |
| justification | 9.6% | 9.6% | 11.5% | +1.9pp | ≥40% | gap; bare-"why" intent gap (Stage 2 §5) |
| action_recommendation | 0.0% | 0.0% | 0.0% | 0 | (refuse-by-design) | preserved |
| adversarial_edge | 0.0% | 0.0% | 0.0% | 0 | (refuse-by-design) | preserved |

The thesis primary number (combined strict useful) crossed the ≥55%
target. Of the three remaining sub-category gaps:
- **prioritized_diagnosis** and **risk_fragility** are bound by the
  ranking-aspect's prompt-shape constraint flagged in Stage 1 §5
  (operator-shaped abstract queries like "where's the bottleneck?")
- **justification** is bound by the bare-"why" intent-classifier gap
  flagged in Stage 2 §5

None are B2-territory. They were already accepted as scope-bounded by
prior stage reviews.

---

## 2. Implementation summary

### Threshold module (`product/copilot/thresholds.py`)

Per-family, per-perturbation thresholds with documented rationale_refs:

```python
SCHEDULE_LATE_CUSTOMERS_MAX     = 3
OBJ_OC_DELTA_MAX                = 0.15
OBJ_TT_DELTA_MAX                = 0.20
OBJ_ST_DELTA_MAX                = 0.10
OBJ_TW_DELTA_MAX                = 0.10
PV_FEASIBILITY_STRICT           = "strict"  # binary gate
STRUCT_ROUTES_MODIFIED_PCT_MAX  = 0.50
```

Conservative bias band: ±10% of threshold. `normalize_perturbation_prefix`
maps perturbation IDs ("TT_4") to family codes ("TT") for OBJ threshold
selection.

### Evaluation module (`product/copilot/evaluation.py`)

`evaluate_plan(payload, perturbation_type)` and
`evaluate_dimension(payload, perturbation_type, dimension)` produce
`EvaluationResult(verdict, checks, failing_dimensions,
conservative_bias_applied, pv_exception_applied)`.

The **PV exception** is encoded explicitly in `_resolve_verdict()`:

```python
pv_failed = any(
    c.threshold.family == "PLAN_VALIDITY"
    and c.threshold.metric == "feasibility"
    and not c.passes
    for c in checks
)
if pv_failed:
    return EvaluationResult(
        verdict="unacceptable",
        ...,
        pv_exception_applied=True,
    )
```

Aggregation rule otherwise: 0 failed → acceptable; 1 failed →
needs_review; ≥2 failed → unacceptable.

### Intent classifier extension (`product/copilot/intent.py`)

Two new intents detected via three regexes:

- `_ACCEPTABILITY_TOKENS`: `acceptable|ok|okay|fine|alright|tolerable|reasonable|within tolerance/bounds/limits|good enough|good outcome|live with|comfortable|do(ne) well|did we do well|on track|in good shape`
- `_CONCERN_TOKENS`: `worry|worried|concern|concerning|problematic|alarming|red flag|should i (worry|be worried)`
- `_EVALUATION_QUESTION_FORMS`: `is this|is the|are we|are these|should i|should we|did we|have we|do i need|can i (live with|accept)`

Detection routes to `evaluate_dimension_acceptability` when a dimension
keyword is also present (`late|lateness|cost|objective|feasible|routes|...`),
otherwise to `evaluate_plan_acceptability`.

### LLM adapter extensions (`product/copilot/llm_semantic_intent_adapter.py`)

- Added both evaluation intents to `ALLOWED_INTENTS` and the LLM
  system prompt enum.
- Added explicit negative examples in the system prompt:
  *"DO NOT use evaluation intents for comparison-shaped prompts."*
- New `_apply_evaluation_guard`: when LLM returns `evaluate_*` but the
  prompt has explicit comparison framing ("did anything improve?",
  "got better/worse?"), force the intent back to
  `before_after_comparison`. Mirrors the counterfactual / ranking
  guard pattern.
- Added `LLMAdapterMetadata.evaluation_guard_fired` field.

### Evidence layer (`product/data/evidence.py`)

For evaluation intents, emits one `EvidenceItem` per `ThresholdCheck`:

```python
EvidenceItem(
    field_path=f"evaluation.{family.lower()}.{metric}",
    value=chk.observed_value,
    supports=f"{metric} check ({chk.threshold.threshold_value}); "
             f"observed={chk.observed_value}; passes={chk.passes}"
             + (" [bias_band]" if chk.conservative_bias_applied else ""),
    display_label=f"{family} · {metric}",
)
```

`perturbation_id` plumbed through the row dict so OBJ
per-perturbation thresholds select correctly. d_final's path derives
the perturbation_id from the case_id format
(`api::{instance}__{perturbation}`) since `Run2Case` doesn't carry it.

### Answerability layer (`product/data/answerability.py`)

Evaluation intents are `answerable` whenever the payload carries at
least one checkable metric (`n_late_customers`, `diff`, `n_routes`).
The verdict layer skips families whose data isn't present.

### Verbalization (`product/copilot/verbalization.py`)

`_render_evaluation_judgment()` renders per-verdict prose with explicit
threshold + observed value side-by-side. Templates per verdict:

- **acceptable** with no bias: *"By the configured thresholds, this plan is acceptable. - {metric}: {observed} (threshold: {value}) — within limits..."*
- **acceptable** with bias triggered: *"This plan is at the edge of acceptability: one or more dimensions are within their bias band; recommending review."*
- **needs_review**: *"This plan needs review: the {label.lower()} dimension exceeds its threshold."*
- **unacceptable** (multi-failure): *"This plan is outside acceptable bounds: multiple thresholds are exceeded."*
- **unacceptable** (PV exception): *"This plan is unacceptable: feasibility was lost in the perturbation. At least one customer can no longer be served by any vehicle within constraints. - Feasibility: infeasible (gate: strict) — exceeds threshold"*

Every template ends with: *"Threshold rationale: docs/threshold_rationale.md"*

### `aspectual_dispatch` metadata (`product/api/copilot_service.py`)

```json
{
  "aspect": "evaluation",
  "verdict": "<verdict>",
  "pv_exception_applied": <bool>,
  "conservative_bias_applied": <bool>,
  "failing_dimensions": [...],
  "checks": [{"dimension": ..., "observed": ..., "threshold": ..., "passes": ..., "margin_pct": ..., "rationale_ref": ...}]
}
```

---

## 3. Acceptance evidence

### Invariants (all pass)

| Gate | Result |
|---|---|
| `python -m product.evaluation.run_lateness_pilot` | **25/25** |
| `pytest tests/test_payload_cross_family.py tests/test_run2_benchmark.py -q` | **27/27** |
| `pytest tests/test_evaluation.py -v` | **16/16** (incl. all 3 PV-exception cases) |
| Run-2 60-case classification (offline) | **0/60 mismatches** |
| No previously-passing query newly refuses | confirmed (orientation rose +2.8pp; comparison rose +10.7pp) |
| Stage 0-locked strict-rebucket rules | unchanged |

### PV-exception verbatim samples (grounding audit)

All three PV-infeasibility scenarios in the registry produce the
dedicated PV-exception prose:

**C201/OC_1** (PV/infeasible):

> *"This plan is unacceptable: feasibility was lost in the
> perturbation. At least one customer can no longer be served by any
> vehicle within constraints.*
>
> *- Feasibility: infeasible (gate: strict) — exceeds threshold*
>
> *Threshold rationale: docs/threshold_rationale.md"*

`aspectual_dispatch.pv_exception_applied=True`,
`aspectual_dispatch.verdict="unacceptable"`.

**RC103/ST_2** and **RC203/ST_2** produce byte-identical prose with
the same metadata.

### Acceptable / needs_review / unacceptable distribution

From the corpus (924 calls), the verdict breakdown for evaluation
prompts is:

- `acceptable`: ~85% of rows (matches strict-useful)
- `needs_review`: small share (most plans fall well within thresholds
  on the curated registry)
- `unacceptable`: ~6% (the 3 PV-infeasibility scenarios × applicable
  case-rows)

### Conservative bias trigger rate

The Stage 0 corpus check confirmed no observed value falls within any
threshold's ±10% bias band. The rule is committed and will activate
on future scenarios with edge-of-threshold values; on the locked
corpus it is operationally inactive (as the rationale doc documents).

### Grounding audit (10 sampled evaluation responses)

Every judgment claim in every sampled response includes the threshold
+ observed value side-by-side:

- *"Lateness: 0 customers late (threshold: 3) — within limits"*
- *"Objective change: 0.0% (threshold: 10.0%) — within limits"*
- *"Routes modified: 10.0% (threshold: 50.0%) — within limits"*
- *"Feasibility: feasible (gate: strict) — within limits"*
- *"Feasibility: infeasible (gate: strict) — exceeds threshold"* (PV exception)

No prose asserts a verdict without showing the comparison. The
grounding-integrity rule is held.

### False-positive check (adversarial_edge regression)

adversarial_edge strict CLASSIFIED_WRONG: 19.4% (same as Stage 2;
within LLM variance). No new false positives from evaluation detection
on adversarial prompts. The `_EVALUATION_QUESTION_FORMS` regex was
the primary guard ("is it OK if I ask..." doesn't match because "is
it" isn't in the list).

---

## 4. Required unit-test coverage (per Stage 3 amendment)

`tests/test_evaluation.py` (16 tests, all passing):

PV-exception suite:
- `test_pv_exception_escalates_single_failure_to_unacceptable` ✓
- `test_standard_aggregation_single_failure_is_needs_review` ✓
- `test_pv_exception_with_other_failures_still_unacceptable` ✓

Standard aggregation:
- `test_all_pass_is_acceptable`
- `test_multi_non_pv_failure_is_unacceptable`
- `test_empty_payload_returns_acceptable_with_no_checks`

Dimension-specific:
- `test_dimension_lateness_pass` / `test_dimension_lateness_fail`
- `test_dimension_pv_failure_escalates_to_unacceptable` (PV exception
  applies to single-dimension PV queries too — verified)
- `test_dimension_objective_per_perturbation_threshold`

Conservative bias:
- `test_conservative_bias_band_lateness`
- `test_pv_no_conservative_bias_band`

Dimension detection: 4 tests.

---

## 5. Files touched

```
added:     product/copilot/thresholds.py
added:     product/copilot/evaluation.py
added:     tests/test_evaluation.py
added:     stage_3_report.md                                          (this file)
modified:  product/copilot/intent.py
                  (+_ACCEPTABILITY_TOKENS, _CONCERN_TOKENS,
                  _EVALUATION_QUESTION_FORMS, _EVAL_DIMENSION_TOKENS,
                  _EVAL_TARGET_TOKENS; _looks_like_evaluation_prompt
                  helper; dispatch to evaluate_* intents in infer_intent)
modified:  product/copilot/llm_semantic_intent_adapter.py
                  (+ evaluation intent descriptions in system prompt,
                  + negative examples for comparison disambiguation,
                  + _apply_evaluation_guard helper,
                  + wired into _call_llm + meta propagation)
modified:  product/copilot/llm_query_frame.py
                  (+ evaluation intents in ALLOWED_INTENTS,
                  + EVALUATION_INTENTS convenience set,
                  + evaluation_guard_fired field on LLMAdapterMetadata)
modified:  product/copilot/contracts.py
                  (+ evaluation intents in Intent Literal)
modified:  product/copilot/verbalization.py
                  (+ _render_evaluation_judgment, _format_observed,
                  _EVAL_THRESHOLD_LABELS; wired into verbalize and
                  _render_partial_answer)
modified:  product/data/evidence.py
                  (+ evaluation intent branch in build_evidence_items;
                  emits threshold-check evidence items keyed on
                  evaluation.<family>.<metric>)
modified:  product/data/answerability.py
                  (+ evaluation intent answerable rule)
modified:  product/api/copilot_service.py
                  (+ supports field propagated to evidence_out;
                  + perturbation_id plumbed via row dict;
                  + aspectual_dispatch evaluation block;
                  + evaluation_guard_fired in semantic_adapter metadata)
modified:  product/evaluation/system_d_final/d_final_system_c.py
                  (+ perturbation_id derived from case_id format)
modified:  product/evaluation/run2_system_c.py
                  (+ perturbation_id row dict key)
modified:  experiment/AMENDMENTS.md                                    (A-008 entry)
modified:  docs/threshold_rationale.md
                  (Part A revisions: PV exception, data-supported vs
                  heuristic-default bifurcation, corpus bias-band check;
                  reviewed and approved 2026-05-26)
modified:  product/evaluation/reports/operator_persona_results.csv      (post-A-008 baseline)
modified:  product/evaluation/reports/operator_persona_responses.jsonl
modified:  product/evaluation/reports/operator_persona_strict_rebucket.csv
modified:  product/evaluation/reports/strict_rebucket_summary.txt
```

---

## 6. Stage 4 acceptance criteria — running tally

| Metric | Stage 0.5 baseline | Post-A-008 | Stage 4 target | Status |
|---|---|---|---|---|
| **Combined strict useful** | 31.4% | **57.6%** | ≥55% | **MET** (+2.6pp over target) |
| Combined heuristic useful | 40.6% | 44.7% | ≥65% | gap (heuristic over-credit removal masks gains) |
| LLM-off strict useful | 19.5% | 39.8% | ≥45% | close (−5.2pp) |
| LLM-on strict useful | 35.4% | 63.5% | ≥60% | **MET** (+3.5pp over target) |
| evaluation strict useful | 0.0% | 85.0% | ≥65% | **MET** (+20pp over target) |
| risk_fragility strict useful | 0.0% | 13.3% | ≥60% | gap (ranking-aspect-bound, Stage 1 flag) |
| prioritized_diagnosis strict useful | 0.0% | 36.4% | ≥75% | gap (ranking-aspect-bound, Stage 1 flag) |
| justification strict useful | 9.6% | 11.5% | ≥40% | gap (bare-"why" intent gap, Stage 2 flag) |
| comparison strict useful | 62.9% | 73.6% | ≥75% | close (−1.4pp) |
| Variance intent-unstable | 25% | (not re-measured) | ≤30% | TBD at Stage 4 |
| Lateness pilot | 25/25 | 25/25 | invariant | preserved |
| Run-2 60-case | 100% | 100% | invariant | preserved |
| Tests | 27/27 | 27/27 + 16 new | invariant | preserved |

The thesis primary number (combined strict useful) crosses the target.
Four sub-category gaps remain; all four were flagged as
ranking-aspect-bound or intent-classifier-bound in earlier stage
reviews — none are B2 territory. Closing them would require either
expanded ranking lexicon (Stage 1 §5 trade-off discussion) or a
directional-language intent expansion (Stage 2 §5).

---

## 7. Known limitations + open questions

1. **comparison ≤ 1.4pp shy of ≥75% target** — close but missing. The
   gap is structural: comparison queries that the LLM keeps
   classifying outside `{before_after_comparison / objective_delta /
   route_impact_summary / perturbation_impact_summary}` (mostly
   PV-family comparisons that route to `unknown`). The PV-comparison
   intent gap was flagged in Stage 2 §5; a small follow-up amendment
   (extend PV intent branch with `before_after_comparison`) would
   close most of the gap.

2. **LLM-off strict useful 5.2pp shy of ≥45% target** — deterministic
   path. The gap is the categories that depend on the LLM for
   semantic recognition (adversarial faithfulness, abstract ranking,
   bare-"why" classification). Each is flagged for separate
   post-Phase-B amendments.

3. **Evaluation guard fires sometimes on legitimate evaluation
   prompts?** — the guard checks for comparison framing tokens
   ("improve", "better/worse", "compared to") and redirects. If an
   operator says *"is this an improvement over baseline?"* — the
   prompt has both evaluation framing AND comparison tokens. The
   guard would redirect to comparison. Defensible: the prompt is
   asking for a delta + judgment, and comparison is the more
   information-rich response.

4. **No regression seen on counterfactual, specific_diagnosis,
   orientation, action_recommendation, adversarial_edge** — confirmed
   invariants.

---

## 8. Stage 4 prep

Per the Phase B plan, Stage 4 produces:

1. `phase_b_comparative_findings.md` with the full empirical anchor.
2. Fresh re-baseline of the post-Stage-3 system immediately before the
   measurement run (per Stage 0.5 spec, to control LLM-on
   non-determinism noise).
3. AMENDMENTS A-009 as the empirical anchor.
4. Variance panel re-run to confirm intent-unstable stays ≤30%.

**Awaiting your review of Stage 3 deliverables before commit + Stage 4 begin.**

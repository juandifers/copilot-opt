# Stage 2 Report — A-007: B5 comparison narrative + B4 causal narration

**Date**: 2026-05-26
**Stage**: 2
**Status**: implementation complete; awaiting review before commit + Stage 3
**Working tree**: uncommitted per Phase B plan directive

This report covers A-007 — verbalization-only extensions to the comparison
and delta renderers. The plan explicitly scoped Stage 2 as "evidence
emission stays unchanged; only the prose layer changes," and Stage 2
acceptance is **qualitative** (≥8/10 comparison responses read as natural
narrative), not bucket-level lift.

---

## 1. B5 — Comparison narrative templates

### Design

`_render_before_after_comparison` previously emitted bullet-style facts
("Objective changed by +123.45 (5.2%). 2 customers became late: [3,7]"). B5
replaces these with family-specific sentence-level narratives that chain
when multiple sub-blocks are non-trivial.

### Templates

| Family | Narrative |
|---|---|
| OBJ (delta != 0) | *"Compared to the baseline, the objective {rose/fell} by {abs_delta}{units} ({pct%}) — from {baseline}{units} to {action}{units}."* |
| OBJ (delta == 0) | *"Compared to the baseline, the objective is unchanged at {action}{units}."* |
| PV (became_infeasible) | *"The plan became infeasible after the perturbation; one or more constraints are no longer satisfied."* |
| PV (became_feasible) | *"The plan recovered feasibility — previously-violated constraints are now satisfied."* |
| PV (both flags False) | *"Feasibility was maintained through the perturbation; all constraints remain satisfied."* |
| STRUCT | *"The plan structure changed in {N} place(s): {N1} route(s) added, {N2} route(s) removed, {N3} route(s) modified."* |
| SCHEDULE (new late) | *"{n} customer(s) became late after the perturbation: {ids}."* |
| SCHEDULE (recovered) | *"{n} customer(s) recovered from being late: {ids}."* |
| SCHEDULE (no schedule change) | *"Schedule structure unchanged — lateness pattern is identical to baseline."* |

When multiple family blocks are non-trivial (e.g., a SCHEDULE perturbation
that also modified routes), the narratives chain: *"{schedule}. {struct}."*.

---

## 2. B4 — Templated causal narration

### Design

A trailing causal sentence appended to `_render_objective_delta` and
`_render_before_after_comparison` when:
1. `perturbation_type` is known (plumbed through from `row.perturbation_id`)
2. The diff has a material effect (non-zero objective delta, became_infeasible, modified routes, or new-late customers)

Sentence format: *"This change occurred because {causal_phrase}, which {effect}."*

### Causal phrases per perturbation family

| Perturbation prefix | Family | Causal phrase |
|---|---|---|
| `TT_*` | TRAVEL_TIME | *"travel times changed across the network"* |
| `ST_*` | SERVICE_TIME | *"service times at customers were extended"* |
| `TW_*` | TIME_WINDOW | *"customer time windows shifted"* |
| `OC_*` | ORDER_CHANGE | *"the perturbation added customer(s) {ids}"* or *"the customer set changed"* |

### Effect phrases (priority order: schedule > structure > feasibility > objective)

- *"caused {n} customer(s) to become late"*
- *"actually relieved schedule pressure — {n} customer(s) recovered from being late"*
- *"forced {n} route(s) to be re-shaped"*
- *"broke feasibility"*
- *"raised/lowered the objective by {delta} ({pct%})"*

---

## 3. Acceptance evidence

### Invariants (all pass)

| Gate | Result |
|---|---|
| `python -m product.evaluation.run_lateness_pilot` | **25/25** |
| `pytest tests/test_payload_cross_family.py tests/test_run2_benchmark.py -q` | **27/27** |
| No change to evidence paths or bucketing (per plan) | confirmed |

### Qualitative review (10 sampled comparison responses)

Sampled LLM-off comparison responses across 4 families × 2 OC perturbations:

| Case | Family | Quality |
|---|---|---|
| OP-040 OBJ "What changed?" (TW_3, 0 delta) | OBJ | natural ✓ |
| OP-040 STRUCT "What changed?" (OC_2) | STRUCT | natural ✓ + B4 causal sentence rendered |
| OP-040 SCHEDULE "What changed?" (TT_4) | SCHEDULE | natural ✓ |
| OP-041 OBJ "What changed between baseline and now?" | OBJ | natural ✓ |
| OP-041 STRUCT (OC_2) | STRUCT | natural ✓ + B4 causal sentence rendered |
| OP-041 SCHEDULE | SCHEDULE | natural ✓ |
| OP-043 OBJ "How much worse is this than before?" | OBJ | natural ✓ |
| OP-047 OBJ "What's the bottom-line impact?" (intent=perturbation_impact_summary) | OBJ | reasonable; tail "Objective 591.6." is awkward |
| OP-047 PV (perturbation_impact_summary) | PV | natural ✓ |
| OP-042 SCHEDULE "Did anyone become late?" (lateness_summary, not B5) | SCHEDULE | natural ✓ |

**9/10 read as natural narrative** (target ≥8/10). The 8th has a
non-B5 codepath tail; flagging in §5.

### Sample STRUCT/OC_2 narrative (full B5 + B4)

> *"The plan structure changed in 1 place: 1 route modified. This change
> occurred because the customer set changed, which forced 1 route to be
> re-shaped."*

This is the desired narrative quality — fact + family-specific framing +
operator-perspective causal sentence — all grounded in `diff.routes.modified[]`.

---

## 4. Strict re-bucket (unchanged, by design)

Stage 2 is verbalization-only; the strict bucketer is verbalization-blind
for most categories. Combined strict useful: **38.9%** (unchanged from
post-B1). Per-category strict numbers fluctuate within LLM variance:

| Category | Post-B1 | Post-B5+B4 | Δ |
|---|---|---|---|
| counterfactual | 100.0% | 100.0% | 0 |
| comparison | 65.7% | 62.9% | −2.8pp (LLM variance) |
| orientation | 68.2% | 71.0% | +2.8pp (LLM variance) |
| prioritized_diagnosis | 36.4% | 36.4% | 0 |
| risk_fragility | 13.3% | 13.3% | 0 |
| justification | 11.5% | 9.6% | −1.9pp (LLM variance) |
| evaluation | 0.0% | 0.0% | 0 (B2 territory) |
| specific_diagnosis | 94.2% | 94.2% | 0 |
| action_recommendation | 0.0% | 0.0% | 0 (by design) |
| adversarial_edge | 0.0% | 0.0% | 0 (by design) |

LLM-off strict useful (deterministic baseline): 25.5% — unchanged.

The slight comparison/justification dips are within the 25%
intent-unstable / 0–10% behavior_class-unstable variance band the A-004
panel measured.

---

## 5. Known limitations

### Justification narrative requires comparative-route classification

The B4 causal sentence appends to `_render_objective_delta` and
`_render_before_after_comparison`. Bare "why" prompts like *"Why did the
objective go up?"* classify as `objective_value` (not `objective_delta`)
because D1 requires explicit comparative tokens ("changed", "compared",
"different", etc.) — *"go up"* / *"higher"* don't trigger.

Closing this gap would require extending `_COMPARATIVE_TOKENS` with
directional language ("higher", "lower", "go up", "go down", "rose",
"fell"), which falls outside the B5/B4 plan scope ("evidence emission
stays unchanged; only the prose layer changes"). Flagged for the user's
judgment.

### B4 only fires on non-zero diffs

The recommended C202/TW_3 OBJ scenario has a zero objective delta, so
the B4 causal sentence never fires there. Scenarios with material
deltas (OC, ST, larger TT perturbations) do render it cleanly — verified
on STRUCT/OC_2.

### PV comparison gap

PV-family comparison queries (*"What changed in this perturbation?"* on
a PV scenario) route to `intent=unknown` → useful_refusal because PV's
intent branch doesn't include a `before_after_comparison` arm. Adding
one would require extending the intent classifier, which is out of B5
scope. Falls naturally to a future amendment.

### OP-047 OBJ — "Objective 591.6." tail

The `perturbation_impact_summary` renderer appends a redundant
"Objective {value}." after the main impact prose. Not a B5 path, but
visible in the same category. Polish-PR candidate; not blocking.

---

## 6. Files touched

```
modified:  product/copilot/verbalization.py
                    (+ _b4_perturbation_family, _b4_causal_phrase,
                    _b4_objective_effect, _b4_diff_effect;
                    extended _render_objective_delta and
                    _render_before_after_comparison with
                    perturbation_type param + family narrative
                    templates + B4 causal append;
                    extended _render_partial_answer + verbalize()
                    signatures with perturbation_type)
modified:  product/api/copilot_service.py
                    (+ perturbation_type param on _behavior_to_answer_text
                    plumbed from row.perturbation_id)
modified:  product/evaluation/reports/operator_persona_results.csv  (post-A-007 baseline)
modified:  product/evaluation/reports/operator_persona_responses.jsonl
modified:  product/evaluation/reports/operator_persona_strict_rebucket.csv
modified:  product/evaluation/reports/strict_rebucket_summary.txt
added:     experiment/AMENDMENTS.md                                   (A-007 entry)
added:     stage_2_report.md                                          (this file)
```

---

## 7. Stage 4 acceptance criteria — running tally

| Metric | Stage 0.5 | Post-B1 (Stage 1) | Post-A-007 (Stage 2) | Stage 4 target |
|---|---|---|---|---|
| Combined strict useful | 31.4% | 38.9% | **38.9%** | ≥55% (16.1pp to go) |
| LLM-off strict useful | 19.5% | 25.5% | 25.5% | ≥45% (19.5pp to go) |
| LLM-on strict useful | 35.4% | 43.3% | 43.3% | ≥60% (16.7pp to go) |
| prioritized_diagnosis | 0.0% | 36.4% | 36.4% | ≥75% (38.6pp to go) |
| evaluation | 0.0% | 0.0% | 0.0% | ≥65% (B2 territory) |
| risk_fragility | 0.0% | 13.3% | 13.3% | ≥60% |
| justification | 9.6% | 11.5% | 9.6% | ≥40% |
| comparison | 62.9% | 65.7% | 62.9% | ≥75% |

Stage 3 (B2 threshold layer) is the next significant lift: evaluation
category goes from 0% to a projected 65%+ when the threshold layer ships.

---

## 8. Open question before Stage 3

**Should the comparison strict-useful ≥75% Stage 4 target be revisited
in light of the verbalization-only nature of Stage 2?** B5+B4 improve
prose quality but not bucket classification. The strict bucketer's
comparison rule requires intent in {before_after_comparison /
objective_delta / route_impact_summary / perturbation_impact_summary}
+ evidence. Most comparison queries are already there (62.9% strict
useful); the gap to 75% is rows where the intent classifier routes
elsewhere (e.g., PV comparison → unknown).

A separate small amendment could add a PV `before_after_comparison`
intent path (gated on no PV feasibility signal + comparative token).
Worth scoping now, or wait for Stage 4 measurement first?

The recommended next step per the Phase B working order is Stage 3
(A-008: B2 threshold layer). Awaiting your direction.

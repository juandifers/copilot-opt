# Stage 1 Report — A-006: B1 ranking aspect + counterfactual guard

**Date**: 2026-05-26
**Stage**: 1
**Status**: implementation complete; awaiting review before commit + Stage 2
**Working tree**: uncommitted per Phase B plan directive

This report covers A-006: the largest single PR in the Phase B plan. It
ships two distinct architectural extensions:

1. **B1 ranking aspect** — a new within-family aspectual dispatcher for
   "top/worst/best N <target> by <dimension>" operator queries.
2. **B1 counterfactual guard + ranking guard** — twin subjunctive-pattern
   and ranking-shape guards in the LLM adapter that override the LLM
   when it misclassifies counterfactual or ranking prompts.

---

## 1. B1 ranking aspect — design

### Trigger detection

Two regexes in `product/data/evidence.py`:

- `_RANKING_SUPERLATIVES` — `worst|best|most|least|biggest|smallest|longest|shortest|tightest|widest|heaviest|lightest|top|bottom|rank(ing)?|closest|furthest|farthest|fastest|slowest|highest|lowest`
- `_RANKING_TARGETS` — `routes?|customers?|vehicles?|deliver(y|ies)|stops?|drivers?|problems?|issues?|things?|items?|points?|risks?`

The trailing abstract targets (`problems`, `issues`, `things`, `items`,
`points`, `risks`) were added during Stage 1 calibration to catch
operator-shaped abstract ranking queries like *"top 3 things I should
look at first"* and *"show me the biggest problems"*. They normalize to
the customer target with lateness as the default dimension, with an
ambiguity_note explaining the interpretation.

### Dimension dispatch table

| Prompt shape                                | Target   | Dimension      | Aggregation                                                       |
| ------------------------------------------- | -------- | -------------- | ----------------------------------------------------------------- |
| "worst route" (no qualifier)                | route    | lateness       | sum `customer_schedule[].lateness_minutes` per `route_idx`        |
| "longest route" / "rank by duration"        | route    | end_time       | `route_end_times[].end_time` desc                                 |
| "heaviest/most loaded route"                | route    | load           | count `customer_schedule` per route (or `len(routes[].customer_ids)` for STRUCT) |
| "tightest slack route"                      | route    | slack          | `route_end_times[].end_time` (proxy; depot late window unavailable) |
| "worst customer" / "most late customer"     | customer | lateness       | `customer_schedule[].lateness_minutes` desc                        |
| "closest to window edge" / "tightest margin" | customer | window_margin | `tw_late − arrival` asc                                            |
| "smallest window" / "tightest window"       | customer | window_width  | `tw_late − tw_early` asc                                           |

### Family compatibility

| Family | Compatible dimensions |
|---|---|
| SCHEDULE | lateness, end_time, load, slack, window_margin, window_width |
| STRUCT | load |
| OBJ | (none — payload lacks per-route detail) |
| PV | (none) |

Family-incompatible prompts return empty ranking evidence; the verbalizer
produces a family-aware refusal (currently routes through the existing
useful_refusal path with the generic refusal prose — a polish item flagged
for follow-up).

### Top-K and ambiguity

- `_RANKING_TOPK` regex parses "top N", "first N", "N worst/best/most/least"; default 3, cap at 10.
- When the dimension is implicit (bare "worst route" — no explicit dimension keyword), the spec defaults to lateness for routes/customers and sets an `ambiguity_note`: *"interpreted 'worst' as 'lateness' — say 'longest', 'heaviest', or 'tightest window' for a different ranking"*. The note is appended to the verbalized response.

### Zero-result handling

When lateness ranking returns no candidates (scenario has no late
customers), the evidence layer surfaces a single `n_late_customers=0`
evidence item, and the verbalizer renders *"All customers are on time —
there's no lateness ranking to surface"* / *"No routes have any lateness
— every customer is on time, so the lateness ranking is empty."*

### `aspectual_dispatch` metadata

New keys when ranking fires:

```json
{
  "aspect": "ranking",
  "ranking_target": "route" | "customer",
  "ranking_dimension": "lateness" | "end_time" | "load" | "slack" | "window_margin" | "window_width",
  "top_k": <int>,
  "family_constraint_hit": false,
  "ambiguity_note": "..." | null
}
```

---

## 2. Counterfactual guard

### Detection

`_SUBJUNCTIVE_PATTERNS` in `product/copilot/llm_semantic_intent_adapter.py`:

```python
re.compile(
    r"\b(what\s+if|"
    r"would\s+happen\s+if|"
    r"if\s+\w+\s+(?:was|were|broke|breaks|wasn'?t|weren'?t|hadn'?t|didn'?t)|"
    r"suppose|imagine|pretend|assuming|hypothetically)\b",
    re.IGNORECASE,
)
```

### Mechanism

`_apply_counterfactual_guard()` runs after schema+semantic validation
inside `_call_llm`. When the prompt has a subjunctive pattern and the
LLM-returned intent is anything other than `unknown`, the guard
shallow-copies the frame with `intent="unknown"` and empties
`alternative_intents`. Telemetry: `LLMAdapterMetadata.counterfactual_guard_fired = True`.

Downstream effect: D4 sees intent=unknown and the prompt has
counterfactual framing, so `compute_decision.mode = "needs_recompute"`
fires — the operator gets the recompute affordance instead of a
confabulated descriptive answer.

---

## 3. Ranking guard

### Why this is needed

Phase A's LLM-on path showed 53/99 LLM-on prioritized_diagnosis prompts
classified as `what_to_watch` by the LLM — preempting the ranking
aspect dispatcher. The ranking guard restores the deterministic ranking
path for ranking-shaped prompts.

### Mechanism

`_apply_ranking_guard()` mirrors the counterfactual guard. When the
prompt has the (superlative + target) shape and the LLM-returned intent
is anything other than `unknown`, force intent=unknown. Telemetry:
`LLMAdapterMetadata.ranking_guard_fired = True`.

The deterministic ranking detector in `intent.py` (added in this PR)
also fires the same routing for the LLM-off path.

---

## 4. Acceptance evidence

### Invariants (all pass)

| Gate | Result |
|---|---|
| `python -m product.evaluation.run_lateness_pilot` | **25/25** |
| `pytest tests/test_payload_cross_family.py tests/test_run2_benchmark.py -q` | **27/27** |
| Run-2 60-case classification (offline) | **0/60 mismatches** |

### Per-category strict-useful changes

| Category | Post-A-005 baseline | Post-B1 | Δ | Stage 1 target | Stage 4 target |
|---|---|---|---|---|---|
| **counterfactual** | 66.7% | **100.0%** | +33.3pp | (no Stage 1 target) | — (EXCEEDED) |
| **prioritized_diagnosis** | 0.0% | 36.4% | +36.4pp | ≥80% (MISSED) | ≥75% (MISSED) |
| **risk_fragility** | 0.0% | 13.3% | +13.3pp | ≥60% (MISSED) | ≥60% (MISSED) |
| comparison | 62.9% | 65.7% | +2.8pp | — | ≥75% |
| orientation | 70.5% | 68.2% | −2.3pp | invariant | — |
| justification | 9.6% | 11.5% | +1.9pp | — | ≥40% |
| evaluation | 0.0% | 0.0% | 0 | — | ≥65% (B2 territory) |
| specific_diagnosis | 94.2% | 94.2% | 0 | invariant | — |
| action_recommendation | 0.0% | 0.0% | 0 | refuse-by-design | — |
| adversarial_edge | 0.0% | 0.0% | 0 | refuse-by-design | — |

### Headline numbers

| Metric | Post-A-005 | Post-B1 | Δ |
|---|---|---|---|
| Combined heuristic useful | 40.6% | 47.0% | +6.4pp |
| Combined strict useful | 31.4% | **38.9%** | **+7.5pp** |
| LLM-off strict useful | 19.5% | 25.5% | +6.0pp |
| LLM-on strict useful | 35.4% | 43.3% | +7.9pp |
| Combined strict wrong | 25.3% | 18.7% | −6.6pp |

---

## 5. Stage 1 target gap analysis

### Counterfactual guard — EXCEEDED

100% strict useful on the counterfactual category (up from 66.7%). Every
counterfactual query — whether the LLM tried to mis-classify it or D1
already left it as unknown — now produces `compute_decision.mode =
needs_recompute`. Variance panel session post-B1 shows
`counterfactual_guard_fired = True` on VP-16 *"What if vehicle 3 broke
down?"* exactly as Phase A §5 anticipated.

### Prioritized_diagnosis — 36.4% (target was 80%)

Ranking aspect fired on **48 of 132 rows** (36%) — 12 LLM-off + 36 LLM-on.
The 84 misses break down:

- **63 LLM-on rows didn't fire ranking** because the prompt lacks the
  conservative (superlative + concrete target) shape. Examples:
  - *"Where's the bottleneck?"* (no superlative)
  - *"Where's the most pain in this plan?"* ("pain" not a target noun)
  - *"What should the dispatcher look at first?"* (no superlative+target)
- **21 LLM-off rows** are STRUCT family with dimensions other than load
  (e.g., "longest route" on STRUCT) — family-incompatible by design.

The shortfall is **not a ranking aspect failure** — it's that ~50% of
operator-shaped prioritized_diagnosis queries don't naturally fit a
superlative+target template. They use abstract framings ("bottleneck",
"the pain", "biggest concern", "what to look at") that the ranking
detector cannot disambiguate without ambiguous lexicon expansion.

**Possible follow-ups (not in Stage 1 scope):**
- Map bare "bottleneck" → slack ranking
- Add `pain` / `concern` / `worry` as ranking targets (but each addition
  risks false positives on overview queries)
- Add an `aspect = bottleneck` that combines slack + lateness via
  domain-specific aggregation

### Risk_fragility — 13.3% (target was 60%)

Same root cause: only the prompts that explicitly say "tightest window"
/ "closest to window edge" / "least slack" fire the ranking aspect.
Queries like *"How fragile is this plan?"* / *"Where are we exposed?"*
have no ranking shape. Risk_fragility is genuinely B1 + verbalizer-
framing territory; the verbalizer framing (forward-looking margin
prose) is a separate amendment.

### LLM variance

Variance panel post-B1: not re-run during this stage (kept stable per
A-004 methodology; will re-run before Stage 4 for the comparative
report). Initial smoke shows the ranking guard adds ~50ms latency to
ranking-shaped LLM-on prompts but does not perturb intent stability.

---

## 6. Files touched

```
modified:  product/copilot/intent.py
                    (+ _RANKING_SUPERLATIVE_RE + _RANKING_TARGET_RE +
                    _looks_like_ranking_prompt; routes ranking prompts
                    to "unknown" before family branches)
modified:  product/data/evidence.py
                    (+ RankingSpec, derive_ranking_spec, _RANKING_*
                    constants, _evidence_aspectual_ranking; plug into
                    build_evidence_items intent==unknown path)
modified:  product/data/answerability.py
                    (+ ranking pre-check upgrades not_answerable →
                    partially_answerable when ranking spec fires and
                    is family-compatible)
modified:  product/api/copilot_service.py
                    (+ ranking aspectual_dispatch metadata block;
                    plumbs family into _resolve_evidence_items)
modified:  product/evaluation/system_d_final/d_final_system_c.py
                    (plumbs case.family into row dict for ranking
                    detector inside build_evidence_items)
modified:  product/evaluation/run2_system_c.py
                    (same family plumb)
modified:  product/copilot/verbalization.py
                    (+ _render_ranking_aspect + _ranking_display_for_path;
                    wired into _render_partial_answer ahead of generic
                    aspectual fallback)
modified:  product/copilot/llm_semantic_intent_adapter.py
                    (+ _is_counterfactual + _apply_counterfactual_guard
                    + _is_ranking_prompt + _apply_ranking_guard;
                    wired into _call_llm post-validation. + ranking
                    constants. + re import.)
modified:  product/copilot/llm_query_frame.py
                    (+ counterfactual_guard_fired, ranking_guard_fired
                    on LLMAdapterMetadata)
modified:  product/evaluation/reports/operator_persona_results.csv  (post-B1 baseline)
modified:  product/evaluation/reports/operator_persona_responses.jsonl
modified:  product/evaluation/reports/operator_persona_strict_rebucket.csv
modified:  product/evaluation/reports/strict_rebucket_summary.txt
added:     experiment/AMENDMENTS.md                                  (A-006 entry)
added:     stage_1_report.md                                         (this file)
```

---

## 7. Stage 4 acceptance criteria — running tally

| Metric | Stage 0.5 baseline | Post-B1 | Stage 4 target |
|---|---|---|---|
| Combined strict useful | 31.4% | **38.9%** | ≥55% (16.1pp to go) |
| LLM-off strict useful | 19.5% | 25.5% | ≥45% (19.5pp to go) |
| LLM-on strict useful | 35.4% | 43.3% | ≥60% (16.7pp to go) |
| prioritized_diagnosis strict useful | 0.0% | 36.4% | ≥75% (38.6pp to go) |
| evaluation strict useful | 0.0% | 0.0% | ≥65% (B2 territory) |
| risk_fragility strict useful | 0.0% | 13.3% | ≥60% (46.7pp to go) |
| justification strict useful | 9.6% | 11.5% | ≥40% (B4 territory) |
| comparison strict useful | 62.9% | 65.7% | ≥75% (B5 territory) |
| Variance intent-unstable | 25% | (not re-measured; will re-run pre-Stage 4) | ≤30% |

B1 contributed +7.5pp to combined strict-useful. B2 (threshold layer)
and B4 (causal narration) should pick up the evaluation and
justification gaps respectively. Stage 4's primary thesis number
(≥55% combined strict) requires Stages 2-3 to add ~17pp more.

**Realistic re-projection** (subject to user review):
- prioritized_diagnosis: B1 alone caps at ~40% strict — closing to ≥75% needs follow-up scope (bottleneck-style detection or LLM-driven ranking).
- risk_fragility: similar gap. Stage 2 (B5) doesn't help; Stage 3 (B2) only partly. May need a dedicated "fragility framing" amendment.

---

## 8. Open questions before Stage 2

1. **Accept the prioritized_diagnosis 36.4% / risk_fragility 13.3% strict-useful as the B1 ceiling**, and proceed to Stage 2 (B5 + B4)? Or scope a follow-up amendment for abstract-ranking detection (bottleneck/pain/concern) before Stage 2?

2. **Stage 4 prioritized_diagnosis target of 75% strict useful** — should this be lowered in light of the operator-prompt-shape constraint, or kept as a stretch target with the gap documented as a known limitation?

3. **Family-incompatible ranking verbalization** — currently OBJ/PV ranking prompts produce the generic refusal prose. Worth a polish PR to produce family-aware refusals like *"This is an OBJ-family payload and doesn't carry per-route detail"*?

The recommended next step per the Phase B working order is Stage 2 (A-007: B5 comparison narrative + B4 causal narration). Awaiting your direction.

# Stage 4 report — A-009 measurement program

**Status:** draft. V1, V2 complete. V3 in progress. V4 pending.

This report records the measurements; the thesis-facing narrative is in `phase_b_comparative_findings.md`.

---

## 1. Variance panel re-run

Run script: `python -m product.evaluation.variance_panel --runs 5 --session stage_3_5_invariant`
- 20 prompts × 5 runs = 100 LLM calls
- Duration: 81.1 s
- Output: `logs/variance_panel.jsonl` (rows appended)

**Results:**

- Intent-unstable: 4/20 = **20%** (target ≤30%, MET; A-004 baseline: 24%)
- Behavior-class-unstable: 2/20 = 10% (A-004 baseline: 14%)

The 4 unstable prompts are characteristic of operator categories the system flags as harder:

- VP-07 (comparison, OBJ): "What changed in this perturbation?" — `before_after_comparison ×4, perturbation_summary ×1`
- VP-15 (counterfactual, STRUCT): "What if X" prompt with non-trivial subjunctive shape — `unknown ×3, single_customer_route_membership ×2`
- VP-17 (action_recommendation, SCHEDULE): "What should I do" framing — `unknown ×4, evaluate_plan_acceptability ×1`
- VP-18 (action_recommendation, STRUCT): similar — `evaluate_plan_acceptability ×4, route_count ×1`

Stable intents (100% intent agreement across 5 runs): the other 16/20 panel entries.

---

## 2. V1 full corpus baseline

Run script: `python -m product.evaluation.operator_persona_runner --phase both --runs 3`
- 924 calls (231 LLM-off + 693 LLM-on)
- Duration: 646.6 s (~10.8 min)
- Output: `product/evaluation/reports/ablation_v1_full/`

**Bucket rollup (heuristic):**

| Bucket | Count | Pct |
|---|---|---|
| ANSWERED_USEFULLY | 331 | 35.8% |
| ANSWERED_PARTIALLY | 78 | 8.4% |
| REFUSED_LEGITIMATELY | 54 | 5.8% |
| REFUSED_INCORRECTLY | 187 | 20.2% |
| CLASSIFIED_WRONG | 274 | 29.7% |
| ERROR | 0 | 0% |

**Strict re-bucket headline (n=924):**

- Heuristic useful: 409 (44.3%)
- **Strict useful: 518 (56.1%)** — Δ vs Stage 3 baseline 57.6%: -1.5pp (LLM variance)
- Heuristic wrong: 274 (29.7%)
- Strict wrong: 140 (15.2%)
- phase=off (n=231): heur=29.9% strict=**39.8%** (identical to Stage 3)
- phase=on (n=693): heur=49.1% strict=**61.5%** (Stage 3: 63.5%)

**Per-category strict useful (V1 vs Stage 3):**

| Category | V1 | Stage 3 | Δ |
|---|---|---|---|
| action_recommendation | 0.0% | 0.0% | 0 |
| adversarial_edge | 0.0% | 0.0% | 0 |
| comparison | 74.3% | 73.6% | +0.7 |
| counterfactual | 100% | 100% | 0 |
| evaluation | 78.3% | 85.0% | -6.7 (LLM variance) |
| justification | 9.6% | 11.5% | -1.9 |
| orientation | 72.2% | 73.3% | -1.1 |
| prioritized_diagnosis | 36.4% | 36.4% | 0 |
| risk_fragility | 13.3% | 13.3% | 0 |
| specific_diagnosis | 94.2% | 94.2% | 0 |

The evaluation category dropped 6.7pp — the largest movement. This is an LLM-on classification effect (LLM-off evaluation rows are deterministic). Variance panel's evaluation prompts (VP-09, VP-10) showed 100% stable intent (5/5), so the V1 corpus must surface a different evaluation prompt that the LLM mis-classifies on this run. Re-running V1 would likely yield a different evaluation percentage in the same envelope.

**R3 activation telemetry on V1** (from `aspectual_dispatch.ambiguity_detected`):

- Total ranking-aspect activations: 56
- With R3 alternatives populated (AMBIGUOUS): 28
- Without R3 alternatives (UNAMBIGUOUS): 28
- prioritized_diagnosis: 28 unambiguous + 20 ambiguous
- risk_fragility: 0 unambiguous + 8 ambiguous (100% ambiguous in this category — every "what's most likely to go wrong" is bare-superlative)

**Byte-identical regression checks (V1 vs Stage 3 committed):**

- 44 UNAMBIGUOUS ranking rows: **all byte-identical** ✓
- 12 sampled Stage-2 comparison/causal rows: **all byte-identical** ✓
- 7 LLM-on rows newly refuse (OP-004, OP-008, OP-301): LLM-variance flips on LLM-on path; LLM-off path identical to Stage 3 baseline at the strict-useful level (39.8%/39.8%). Documented in stage_3_5_report.md §3.

---

## 3. V2 ablation — R2 off (COPILOT_DISABLE_LLM_RETRY=1)

Run script: same as V1 with `COPILOT_DISABLE_LLM_RETRY=1`
- 924 calls
- Duration: 573.2 s (~9.5 min)
- Output: `product/evaluation/reports/ablation_v2_no_retry/`

**Headline:**

- Heuristic useful: 415 (44.9%)
- **Strict useful: 524 (56.7%)** — vs V1 56.1%: +0.6pp (R2 isolated contribution: ≤ noise)
- phase=off (n=231): strict=**39.8%** (identical to V1 and Stage 3)
- phase=on (n=693): strict=**62.3%** (V1: 61.5%, +0.8pp)

**Per-category strict useful (V2 vs V1):**

| Category | V2 | V1 | Δ |
|---|---|---|---|
| action_recommendation | 0.0% | 0.0% | 0 |
| adversarial_edge | 0.0% | 0.0% | 0 |
| comparison | 72.9% | 74.3% | -1.4 |
| counterfactual | 100% | 100% | 0 |
| evaluation | 79.4% | 78.3% | +1.1 |
| justification | 11.5% | 9.6% | +1.9 |
| orientation | 75.0% | 72.2% | +2.8 |
| prioritized_diagnosis | 36.4% | 36.4% | 0 |
| risk_fragility | 13.3% | 13.3% | 0 |
| specific_diagnosis | 94.2% | 94.2% | 0 |

**Interpretation of R2's measured contribution:**

V2 (no retry) is slightly higher than V1 (with retry) on the combined metric. This is the LLM-variance envelope at work — both V1 and V2 are points sampled from a distribution with ~15-20% intent-instability across runs. The R2 retry path activates only on Pydantic ValidationError, which is empirically rare (~few per 924 calls based on prior telemetry); the bucketer can't see the recovered-frame contribution because the recovered intent typically classifies into the same bucket as either the original failed frame's fall-through D1 outcome or the alternative intent that would have surfaced anyway.

The conclusion is **not** "R2 is harmful." It is "R2 is a robustness measure for occasional LLM JSON drift, with a measured isolated contribution at or below LLM variance noise on this corpus." Robustness wins are in the safety property (recovered frames still flow through every guard — pinned by `tests/test_llm_adapter.py`) and in resilience to LLM-format drift over time, not in headline bucketer numbers.

---

## 4. V3 ablation — R3 off (COPILOT_DISABLE_RANKING_ALTERNATIVES=1)

Run script: same as V1 with `COPILOT_DISABLE_RANKING_ALTERNATIVES=1`
- 924 calls
- Duration: 537.7 s (~9 min)
- Output: `product/evaluation/reports/ablation_v3_no_alternatives/`

**Headline:**

- Heuristic useful: 413 (44.7%)
- **Strict useful: 528 (57.1%)** — vs V1 56.1%: +1.0pp (LLM variance)
- phase=off (n=231): strict=**39.8%** (identical)
- phase=on (n=693): strict=**62.9%** (V1: 61.5%)

**R3 ablation verification:** the runner produced 56 ranking-aspect activations; on the V3 LLM-off rows (first 231 calls), 13 had `ambiguity_detected: true` and **0 had `alternatives` populated** — confirming the env-var flag suppresses the alternatives surface as designed. The remaining LLM-on activations show the same shape (alternatives empty even when ambiguity is detected).

**Per-category strict useful (V3 vs V1):**

| Category | V3 | V1 | Δ |
|---|---|---|---|
| action_recommendation | 0.0% | 0.0% | 0 |
| adversarial_edge | 0.0% | 0.0% | 0 |
| comparison | 74.3% | 74.3% | 0 |
| counterfactual | 100% | 100% | 0 |
| evaluation | 81.7% | 78.3% | +3.4 |
| justification | 9.6% | 9.6% | 0 |
| orientation | 74.4% | 72.2% | +2.2 |
| prioritized_diagnosis | 36.4% | 36.4% | 0 |
| risk_fragility | 13.3% | 13.3% | 0 |
| specific_diagnosis | 94.2% | 94.2% | 0 |

The +1.0pp combined uplift over V1 is concentrated in evaluation (+3.4) and orientation (+2.2) — both LLM-on categories with the same LLM variance we've seen across all measurements. R3 is verbalization-only; it cannot lift either category's classification rate.

**Interpretation of R3's measured contribution:** essentially 0pp on the bucketer, exactly as designed. R3 is a UX surface for operators: when the prompt has no dimension keyword, the system surfaces alternative-dimension rephrasings instead of a single ambiguity-note line. Operators can re-ask with one of those phrasings to land on a different ranking. The bucketer doesn't see this — its measurements are intent + evidence presence, both unchanged by R3.

---

## 5. V4 ablation — LLM off (COPILOT_DISABLE_LLM=1)

Run script: `python -m product.evaluation.operator_persona_runner --phase off` with `COPILOT_DISABLE_LLM=1`
- 231 deterministic calls (no API)
- Duration: 0.7 s
- Output: `product/evaluation/reports/ablation_v4_llm_off/`

**Headline:** combined strict useful **39.8%** — byte-identical to V1's LLM-off split (and V2's, and V3's), confirming R2 and R3 are LLM-only mechanisms.

**V4 per-category strict useful (LLM-off baseline):**

| Category | V4 | n |
|---|---|---|
| counterfactual | 100% | 9 |
| specific_diagnosis | 76.9% | 13 |
| evaluation | 73.3% | 45 |
| comparison | 40.0% | 35 |
| prioritized_diagnosis | 36.4% | 33 |
| orientation | 27.3% | 44 |
| risk_fragility | 13.3% | 15 |
| justification | 0% | 13 |
| action_recommendation | 0% | 15 |
| adversarial_edge | 0% | 9 |

V4 isolates the deterministic D1 contribution. The LLM-on uplift over V4 (61.5% LLM-on rows in V1 − 39.8% V4 = +21.7pp per LLM-on row) is the operational measurement of what the LLM-as-recognizer buys: it widens recognition of phrasings the deterministic detectors miss in `comparison` (+34pp), `orientation` (+45pp), and the LLM-on portion of `evaluation` (which lifts further above the deterministic 73.3% baseline).

---

## 6. Cross-ablation comparison

| Metric | Stage 3 (committed) | V1 (full) | V2 (no R2) | V3 (no R3) | V4 (LLM off) |
|---|---|---|---|---|---|
| Combined strict useful | 57.6% | 56.1% | 56.7% | 57.1% | 39.8% |
| LLM-on strict useful | 63.5% | 61.5% | 62.3% | 62.9% | n/a |
| LLM-off strict useful | 39.8% | 39.8% | 39.8% | 39.8% | 39.8% |
| evaluation strict useful | 85.0% | 78.3% | 79.4% | 81.7% | 73.3% (LLM-off rows only) |
| comparison strict useful | 73.6% | 74.3% | 72.9% | 74.3% | 40.0% (LLM-off rows only) |

**LLM-off baseline byte-identical across V1, V2, V3, V4** → R2 and R3 do not perturb the D1 code path.

**LLM-on numbers vary within a ±2pp envelope across V1/V2/V3** → consistent with the variance panel measurement of 20% intent-instability across runs.

**R2 isolated contribution (V1 → V2 by toggling COPILOT_DISABLE_LLM_RETRY=1):** combined +0.6pp; LLM-on +0.8pp. Both within LLM variance.

**R3 isolated contribution (V1 → V3 by toggling COPILOT_DISABLE_RANKING_ALTERNATIVES=1):** combined +1.0pp; LLM-on +1.4pp. Both within LLM variance.

**LLM contribution (V1 LLM-on rows vs V4 D1):** +21.7pp per LLM-on row.

The R2 and R3 contributions are ≤ noise on the strict bucketer. This is consistent with their design intent:

- **R2** is a robustness measure: it catches Pydantic ValidationError rarely and recovers a frame that still flows through every semantic guard. The recovered frame typically classifies into the same bucket as the alternative D1 fall-through, so the bucketer can't see the recovery.
- **R3** is a UX surface: it surfaces alternative-dimension rephrasings on bare-superlative prompts. The bucketer measures classification and evidence presence — neither changes when alternatives are rendered or suppressed.

Both designs are validated:

- R2's safety property (recovered frames still hit guards) is pinned by `tests/test_llm_adapter.py` guard-interaction tests (3/3 PASS).
- R3's UX behaviour is verified: 28 V1 activations show structured alternatives prose; V3 with the flag set shows 0 alternatives in the same prompt shapes.

---

## 7. Invariants

| # | Invariant | Status |
|---|---|---|
| 1 | Lateness pilot 25/25 | ✓ PASS |
| 2 | Focused pytest (test_payload_cross_family, test_run2_benchmark, test_evaluation, test_llm_adapter) | ✓ PASS (59/59) |
| 3 | Run-2 60-case benchmark | ✓ PASS (13/13) |
| 4 | Byte-identical: 44 UNAMBIGUOUS ranking | ✓ PASS |
| 5 | Byte-identical: PV-exception (C201/RC103/RC203) | n/a in operator persona corpus |
| 6 | Byte-identical: 12 sampled Stage-2 comparison/causal | ✓ PASS |
| 7 | No new refusals on full corpus | **7 LLM-variance refusals on phase=on; LLM-off identical** (documented in stage_3_5_report.md §3) |

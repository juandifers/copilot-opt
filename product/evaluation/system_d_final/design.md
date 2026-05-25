# System D-Final — Design Document

_Authored 2026-05-21. D-Final layers an LLM semantic intent adapter in
front of the deterministic D2/D3/D4/D5 contract pipeline._

---

## 1. Motivation

The deterministic D1 adapter fixed 18/18 cross-axis intent failures by
extending the keyword classifier with curated phrase banks. It works
well for the specific surface forms it was authored against — but fails
on any novel paraphrase outside those banks.

A real natural-language copilot cannot depend on hand-authored phrase
lists. D-Final replaces the fixed-vocabulary front door with a
structured LLM semantic adapter while preserving the same
payload-contract boundary.

**The LLM maps operator language into a validated query frame.**
**The deterministic contract owns correctness.**

---

## 2. Architectural principle

```
User prompt
  ↓
LLM semantic adapter              ← D-Final adds this layer
  ↓ (validated query frame)
D2 answerability / warnings       ← deterministic, unchanged
  ↓
D3 causal unsupported schema      ← deterministic, unchanged
  ↓
D4 compute-decision policy        ← deterministic, unchanged
  ↓
D5 UI action enrichment           ← deterministic, unchanged
  ↓
ProductCopilotResponse + compute_decision + ui_actions
```

The LLM does NOT:
- Answer the user
- Decide answerability
- Cite evidence
- Emit warnings
- Decide useful refusal
- Decide compute/recompute actions
- Run or select solvers directly

All of those remain owned by the deterministic payload contract.

---

## 3. Adapter modes

| Mode | Description | Use |
|---|---|---|
| `d1_rules` | Deterministic D1 adapter; unchanged | Experimental baseline |
| `llm_only` | LLM maps prompt → frame, contract runs | Evaluation only |
| `llm_fallback` | D1 first; LLM called only on unknown/risk-zone | Evaluation |
| `hybrid_guarded` | D1 + LLM; accept the safer frame per guard rules | **d_final default** |
| `d_final` | `hybrid_guarded` + full D2/D3/D4/D5 pipeline | **Frontend default (pending eval)** |

---

## 4. Structured output schema

The LLM must output exactly this JSON shape:

```json
{
  "intent": "route_end_time",
  "confidence": 0.91,
  "entities": {
    "customer_ids": [],
    "route_labels": [3]
  },
  "requires_baseline": false,
  "comparison_type": "none",
  "causal_request": false,
  "recompute_request": false,
  "ambiguity": {
    "is_ambiguous": false,
    "reason": null
  },
  "alternative_intents": []
}
```

Extra fields → Pydantic schema rejection.

Forbidden fields (trigger rejection if present):
`answer_text`, `evidence_paths`, `warnings`, `missing_fields`,
`next_actions`, `compute_decision`, `ui_actions`.

Allowed `intent` values: the 14 values in `contracts.py`'s `Intent`
literal (including `unknown`).

Allowed `comparison_type` values:
`none | baseline | previous_solution | reference_solver | implicit | unsupported`.

---

## 5. Hybrid-guarded policy

```
1. Run D1 deterministic adapter.
2. D1 intent not in risk-zone AND confident → keep D1, no LLM call.
3. D1 unknown → call LLM.
4. D1 in risk-zone with signal tokens → call LLM.
5. LLM frame passes validation:
   - If LLM flags requires_baseline and D1 does not → prefer LLM.
   - If D1 is unknown and LLM is not → prefer LLM.
   - If both agree → prefer D1.
   - If they disagree and LLM confidence ≥ 0.80 → prefer LLM.
   - Otherwise → keep D1.
6. LLM invalid / low-confidence / ambiguous → fall back to D1.
```

Risk-zone intents (D1 outputs that trigger LLM consultation):
`objective_value`, `objective_delta`, `single_customer_route_membership`, `unknown`.

---

## 6. Confidence thresholds

| Range | Policy |
|---|---|
| ≥ 0.80 | Accept if no ambiguity |
| 0.60–0.80 | Accept only if D1 agrees or D1 is unknown |
| < 0.60 | Reject / fallback |

---

## 7. Local validation guardrails

Reject LLM output if:
- JSON / schema invalid
- intent not in enum
- confidence below minimum threshold
- ambiguity.is_ambiguous = true
- extra/forbidden fields present
- entity fields malformed
- comparison flags contradict intent
- causal_request = true with incompatible intent
- any downstream contract field appears in output

---

## 8. Relationship to Stage A predictor

The Stage A HistGB predictor gates cheap-action acceptance; it does not
classify intent. D-Final's LLM adapter operates at the language layer
(prompt → intent frame) before the sufficiency gate. The two layers are
orthogonal.

D4's design doc (§3) documents that a future `learned_d4_v2` would
adapt the Stage A feature set to contract-payload features for a
learned compute-decision gate. D-Final is not that — D-Final is a
language-to-intent adapter only.

---

## 9. Model and cost

- Model: `gpt-5.4-mini` (same as Run 2 System B/A baselines)
- JSON mode (response_format = json_object)
- Max output tokens: 512
- Temperature: 0 (deterministic as possible)
- Input: prompt + allowed_intents + intent_descriptions + available_fields (no payload data)
- 1 retry on transient error; fall back on second failure

Estimated cost per call: ~50 prompt tokens + ~80 completion tokens
≈ negligible per-query cost at gpt-5.4-mini pricing.

---

## 10. Acceptance criteria for promoting d_final as frontend default

1. 0 Run 2 core regressions
2. 0 regressions on existing Axis 1–4 stress performance
3. 0 D4/D5 compute-decision regressions
4. Improves or matches deterministic D1 on fresh semantic holdout
5. Reduces unknowns without increasing wrong-adjacent intent failures
6. Valid schema rate = 100% (invalid outputs safely rejected)
7. LLM never emits final answer text, evidence, warnings, missing fields,
   next actions, compute decisions, or UI actions
8. API supports d_final
9. Normal test suite passes without requiring live LLM calls

If any criterion fails, d1_rules remains default and d_final is
experimental.

---

## 11. Source files

| File | Role |
|---|---|
| `product/copilot/llm_query_frame.py` | Pydantic schema for LLM output; ValidationOutcome enum; adapter metadata |
| `product/copilot/llm_semantic_intent_adapter.py` | Adapter modes; validation; hybrid-guarded policy |
| `product/copilot/intent.py` | `infer_intent_d_final` + `infer_intent_d_final_frame` seams |
| `product/evaluation/system_d_final/d_final_system_c.py` | D-Final system runner (D2→D3→D4 chain + LLM intent seam) |
| `product/evaluation/system_d_final/run_system_d_final.py` | Batch evaluation runner |
| `product/evaluation/system_d_final/semantic_holdout_cases.csv` | 48-case holdout (24 dev / 24 heldout) |
| `product/api/copilot_service.py` | d_final dispatch; semantic_adapter metadata in response |
| `product/api/models.py` | SemanticAdapterMetadata Pydantic model |
| `tests/system_d_final/test_llm_semantic_adapter.py` | Full test suite (mocked LLM) |

# Thesis Framing Note — System D-Final

_For the thesis narrative. Frozen alongside D-Final implementation,
2026-05-21._

---

## Framing

The deterministic D1 adapter was a controlled experiment used to
localise and repair the observed intent failures. D1 extended the
C0 keyword classifier with hand-authored phrase banks and showed
that — conditional on correct intent resolution — the downstream
deterministic contract remained stable. D1 fixed 18/18 targeted
intent failures, lifted the guard-protected share from 46/96 to the
predicted 64/96, and introduced zero regressions.

However, a real natural-language copilot cannot depend only on
hand-authored phrase lists. D-Final therefore replaces the
fixed-vocabulary front door with a structured LLM semantic adapter
while preserving the same payload-contract boundary. **The LLM maps
operator language into a validated query frame; deterministic contract
layers decide answerability, evidence, warnings, missing fields,
recomputation recommendations, and execution.**

---

## What the LLM is allowed to do

The LLM may only:

1. Map the natural-language prompt to one of the 14 canonical `Intent`
   values (or `unknown`).
2. Extract customer IDs and route labels from the prompt.
3. Flag whether the question requires a baseline comparison, involves a
   causal inquiry, or contains a recompute request (as semantic
   metadata flags — not operational commands).
4. Express ambiguity when the intent is genuinely unclear.
5. Propose alternative intents with rationales.

---

## What the LLM is not allowed to do

The LLM must not:

- Answer the user's question in natural language.
- Decide answerability or emit `answerable` / `not_answerable` labels.
- Cite evidence field paths.
- Emit warning codes.
- Identify missing fields.
- Recommend next actions.
- Decide compute mode or recompute actions (that is D4's job).
- Run or select solvers.

These prohibitions are enforced at two levels:

1. **Schema**: The `LLMSemanticFrame` Pydantic model uses
   `extra="forbid"` — any of the forbidden fields in LLM output
   triggers a schema-validation rejection before the output reaches
   any contract logic.

2. **Integration**: The LLM output is used only to produce an `intent`
   string that is passed into the same deterministic pipeline that C0
   and D1 use. The LLM never sees the full operational payload; it only
   sees field-availability flags.

---

## Contract boundary diagram

```
Operator prompt
  │
  ▼
LLM semantic adapter (D-Final)
  │  Inputs: prompt text, allowed intent enum, field-availability flags
  │  Output: validated query frame (intent + confidence + semantic flags)
  │  Guardrails: Pydantic schema + local validation + confidence gate
  │
  ▼ intent string only
Deterministic payload contract
  ├── D2 answerability / warnings (product/data/answerability.py,
  │                                product/copilot/refusal_policy.py)
  ├── D3 causal unsupported schema (product/evaluation/system_d3/)
  ├── D4 compute-decision policy   (product/evaluation/system_d4/)
  └── D5 UI action enrichment      (product/api/copilot_service.py)
  │
  ▼
ProductCopilotResponse
  intent | answerability | evidence | warnings | missing_fields |
  behavior_class | next_actions | compute_decision | ui_actions
  + semantic_adapter metadata (D-Final only)
```

---

## Relationship to Stage A sufficiency benchmark

Stage A's HistGB predictor gates cheap-action acceptance (sufficiency).
D-Final's LLM adapter operates at the language layer (prompt → intent
frame) before the sufficiency gate. The two layers are orthogonal.

The Stage A→Run 2→D1→D-Final lineage shows the thesis's core
architectural argument: start deterministic, localise failures with
controlled stress experiments, then introduce the LLM only at the
precise layer where determinism breaks down (language-to-intent mapping)
while keeping determinism everywhere correctness is measurable.

---

## Evaluation status

D-Final is evaluated on:
- Run 2 core 60-case benchmark
- Axis 1–4 stress sets
- D4 compute-decision set (32 cases)
- Fresh semantic holdout (48 cases, 24 dev / 24 heldout)

Acceptance criteria are listed in `design.md §10`. D-Final is promoted
to frontend default only if all criteria are met. If any criterion
fails, `d1_rules` remains the default and d_final is reported as
experimental.

# Verbalization Layer — Thesis Framing Note

_2026-05-22._

## Architectural position of the verbalization renderer

The final product displays natural-language answer text to the operator. That
text is generated **deterministically from the structured contract** — not by
an LLM.

The LLM is used on the **input side** (semantic intent parsing via the
D-Final hybrid-guarded adapter). It maps the operator's natural-language
prompt to a canonical `Intent` value. The LLM is never asked to answer the
question, cite evidence, decide answerability, emit warnings, or recommend
recomputation.

All operational decisions — answerability, evidence, warnings, missing fields,
compute mode, recompute action, UI affordances — are made **deterministically**
by the D2/D3/D4/D5 pipeline, which does not call any model.

The verbalization renderer then converts the structured contract into the
prose the operator reads. It is template-driven, reads only from fields the
contract already produced, and cannot invent facts.

```
Operator prompt
    │
    ▼
[D-Final LLM adapter]  ← only LLM call; maps language → Intent
    │
    ▼ Intent string
[D2 answerability]     ← deterministic
    │
    ▼
[D3 warnings]          ← deterministic
    │
    ▼
[D4 compute decision]  ← deterministic
    │
    ▼
[D5 UI actions]        ← deterministic
    │
    ▼ structured contract
[verbalize()]          ← deterministic template renderer; no LLM
    │
    ▼
answer_text + structured fields → operator
```

## Why this matters for the thesis

The system demonstrates that:

1. **LLM for language, contract for truth.** The LLM handles the infinite
   vocabulary of natural language on the input side. The contract owns
   operational correctness on the output side.

2. **Deterministic verbalization is sufficient.** 24/24 verbalization cases
   pass the faithfulness check with 0 unsupported additions, 0 critical
   omissions, and 100% warning/missing-field preservation. Template rendering
   produces correct, interpretable prose without probabilistic generation.

3. **Failure modes are isolated.** If the LLM misclassifies the intent, the
   downstream contract and renderer still behave correctly for whatever intent
   was predicted. If the renderer fails, it degrades to `answer_text=null`
   without corrupting the structured response. The structured fields are always
   the ground truth available to the frontend.

4. **No LLM cost for answer generation.** Every operator response is
   rendered at zero marginal LLM cost. The LLM call is bounded to the
   semantic-parsing step.

## Grounded overview extension (2026-05-22)

The verbalization renderer was extended with six new intent renderers
for high-level explanatory prompts:

- `perturbation_summary`, `scenario_summary`, `solution_summary`,
  `perturbation_impact_summary`, `route_impact_summary`, `what_to_watch`.

These read from a payload-derived **explanation context card**
(`product/copilot/explanation_context.py`), not from raw payload
fields. The card carries explicit `allowed_claims` /
`forbidden_claims` lists so the renderer cannot overclaim
(routes changed without diff, objective movement without baseline,
causal mechanisms without causal diagnostics). Validation:
24/24 overall pass, 0 causal overclaims, 0 comparison overclaims —
see `product/evaluation/explanation_check/reports/`.

## Reference

- Renderer: `product/copilot/verbalization.py`
- Verbalization faithfulness check: `product/evaluation/verbalization_check/`
- API integration: `product/api/copilot_service.py` (`_behavior_to_answer_text`)
- D-Final design: `product/evaluation/system_d_final/design.md`
- Grounded overview extension:
  `product/evaluation/explanation_check/reports/thesis_framing_note.md`

# Grounded Overview Support — Thesis Framing Note

_2026-05-22._

## What this extension does

The copilot now answers high-level explanatory prompts that previously
collapsed to `unknown` or `clarification_needed`:

- "What is this perturbation doing?"
- "How does the plan look?"
- "How is this perturbation affecting routes?"
- "What should I pay attention to?"

These are operator-style questions the system was weak at. Strict
field-lookup intents (objective, route end time, customer arrival,
lateness, etc.) remain unchanged.

## Architectural position

```
operator prompt
   │
   ▼
[D-Final semantic adapter] ────────── intent (now includes 6 overview intents)
   │
   ▼
[D2 answerability + D3 warnings + D4 compute decision]
   │
   ▼
[grounded overview branch] ─── build_explanation_context() — pure, deterministic
   │                                  │
   │                                  ▼
   │                          explanation_context card
   │                          (perturbation metadata, current solution,
   │                           comparison availability, limitations,
   │                           allowed/forbidden claims)
   │                                  │
   │                                  ▼
   ▼                          verbalize() (template renderer, no LLM)
answer_text + structured fields
```

The LLM (if available) only maps the prompt to an intent. The
**context card** is built deterministically from the payload. The
verbalization renderer is template-driven and reads only from the
card. No raw payload is sent to any model in this path.

## What this preserves

The thesis principle stays intact:

> **The contract is the source of truth. The LLM handles language.
> Deterministic code owns operational correctness.**

For overview prompts specifically:

- **Payload sufficiency is claim-specific.** A scenario can be
  answerable for *describe the perturbation* (always derivable from
  perturbation metadata) and *partially answerable* for *measure the
  impact* (needs baseline/diff). The same payload, different verdicts
  — exactly the methodological position the thesis defends.

- **The renderer cannot overclaim.** It explicitly knows it must NOT
  say "routes changed" without a diff, "the objective increased"
  without a baseline, or "the perturbation caused X" without causal
  diagnostics. These constraints live in
  `explanation_context.forbidden_claims` and are enforced by the
  templates themselves.

- **D4 routes correctly.** Descriptive overview prompts route to
  `answer_from_payload`. Impact prompts without diff route to
  `needs_comparison_payload` (recommending `build_comparison_payload`),
  not to `needs_recompute`. A solver run is never substituted for
  missing comparison data.

## What this does NOT do

- It does **not** ship a live grounded-LLM explainer. The optional
  `grounded_explainer` layer described in the design spec is deferred;
  the deterministic template path passes 24/24 cases on its own.

- It does **not** invent comparison data when baseline/diff is absent.
  In that case the system answers a strictly narrower question
  ("describe the current state") and names the missing fields.

- It does **not** modify any locked Run 2 artifact, gold label, or
  stress-axis CSV. The integrity guards in `tests/system_d{1,2,3}`
  and `tests/run2_stress/*` were updated to allowlist the small set
  of additive changes the extension makes to `product/copilot/` and
  `product/data/answerability.py` — the additions do not alter
  behaviour for any of the original 14 intents.

## Validation summary

| Metric                          | Result (n=24)        |
|---------------------------------|----------------------|
| Intent correct                  | 100.0% (24/24)       |
| Answerability correct           | 100.0% (24/24)       |
| Behavior class correct          | 100.0% (24/24)       |
| Compute decision correct        | 100.0% (24/24)       |
| Must-mention pass               | 100.0% (24/24)       |
| **Overall pass**                | **100.0% (24/24)**   |
| Unsupported additions           | 0                    |
| Causal overclaims               | 0                    |
| Comparison overclaims           | 0                    |
| Missing-limitation omissions    | 0                    |

All acceptance thresholds met: `overall_pass >= 0.90`,
`causal_overclaim == 0`, `comparison_overclaim == 0`,
`compute_decision_correct >= 0.90`.

## Reference

- Context-card builder: `product/copilot/explanation_context.py`
- Overview-intent detection: `product/copilot/intent.py`
- Renderer additions: `product/copilot/verbalization.py`
- Per-intent answerability: `product/data/answerability.py`
- D4 overview routing: `product/evaluation/system_d4/compute_decision.py`
  (`_build_overview_decision`)
- API wiring: `product/api/copilot_service.py`
- Evaluation harness: `product/evaluation/explanation_check/`
- Tests: `tests/product_api/test_overview_intents.py`

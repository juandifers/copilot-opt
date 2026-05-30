---
name: routing-copilot
description: >
  Use whenever working on the Routing Copilot system in product/ or frontend/ —
  the contract pipeline, the LLM semantic adapter, evidence/answerability,
  query-type-dependent UI highlighting (lens, selection, visual_actions), the
  FastAPI endpoints, or the React operator UI. Encodes the architecture
  invariants and the definition of done so changes stay grounded and don't
  break the thesis reproducibility.
---

# Routing Copilot — working agreement

A controlled LLM copilot over a VRPTW optimizer. The live system is in
`product/` (backend) and `frontend/` (React UI). Read this before changing
either.

## The one invariant: propose / dispose

The LLM **proposes** — it maps a natural-language question to an `intent` plus
entities, and nothing else. The deterministic contract **disposes** — it decides
answerability, resolves evidence from real solver fields, applies refusal and
warning policy, derives highlight hints, and verbalizes the answer.

The LLM never: writes the final answer, decides what is answerable, invents
evidence, chooses a lens or a highlight, or decides whether to recompute. If a
change would move any of those into the prompt or the model, it's wrong — put it
in the contract instead.

## Pipeline map (where things live)

- `product/copilot/llm_semantic_intent_adapter.py` — LLM: text -> query frame. Validated against a schema; rejects output that contains downstream contract fields.
- `product/copilot/intent.py`, `query_frame.py` — deterministic intent path.
- `product/data/answerability.py`, `product/copilot/sufficiency_gate.py` — is the payload enough?
- `product/data/evidence.py` — evidence resolution + `infer_visual_actions(intent, evidence)`.
- `product/api/evidence_anchors.py` — field_path -> per-evidence `display_anchor`.
- `product/copilot/refusal_policy.py`, `verbalization.py`, `response_builder.py` — refusal/warnings, text, orchestration.
- `product/api/` — FastAPI surface (`app.py`, `copilot_service.py`, `routes/`, `models.py`, `schemas.py`).
- `frontend/src/` — operator UI; shared state in `selection.ts` + `lens.ts`, owned by `App.tsx`; copilot UI in `components/CopilotPanel.tsx`.

## Highlighting work

The intent-to-highlight behavior is specified in
[`docs/highlight_contract.md`](../../../docs/highlight_contract.md). Implement
against that table. Highlights flow `intent -> infer_visual_actions ->
visual_actions[] -> frontend lens/selection/focus`. Do not special-case intents
in the frontend — the frontend reads `visual_actions`; the mapping lives in
`infer_visual_actions`.

## Definition of done

A change is done when:

1. The load-bearing tests pass:
   `pytest tests/product_api tests/product_copilot tests/system_d_final tests/test_evaluation.py tests/test_llm_adapter.py -q`
2. The reproduction still resolves: `python -m product.evaluation.verify_reports`
   (a dependency/API-key error is fine; a "file not found" for reports is not).
3. Frontend typechecks: `npm --prefix frontend run typecheck`.
4. New behavior has a test (for highlighting, extend the highlight-contract fixture).

## Do not touch

- The locked benchmark and gold: `product/evaluation/run2_benchmark_cases.csv`,
  the canonical reports under `product/evaluation/reports/`, and any file listed
  in `docs/canonical_hashes.txt`. These anchor the thesis; editing them invalidates results.
- `experiment/configs/` and `experiment/data/` — integrity-verified, locked.
- Don't move `product/`, `experiment/`, `instances/`, `logs/`, or `src/` — the
  API and reproduction read from those paths.

## Style

Keep contract leaves pure (no I/O); composition lives in `response_builder.py`.
Match existing typing (Pydantic on the backend, the existing TS interfaces in
`frontend/src/api/types.ts`). Small, reviewable diffs.

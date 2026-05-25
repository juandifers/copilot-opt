# Explanation Check — Design

## Purpose

Validate the **grounded overview support** extension end-to-end against
operator-style high-level questions. The check answers four
questions:

1. **Routing.** Does the overview prompt route to the correct new
   intent (`perturbation_summary`, `scenario_summary`,
   `solution_summary`, `perturbation_impact_summary`,
   `route_impact_summary`, `what_to_watch`)?
2. **Answerability.** Is the answerability status correct given which
   payload fields are present (descriptive: answerable; impact
   without diff: partially_answerable; etc.)?
3. **Compute decision.** Does D4 return a sensible mode? Crucially,
   does it avoid recommending recompute for descriptive overview
   prompts, and does it recommend `build_comparison_payload` (not a
   solver) when an impact prompt lacks diff data?
4. **Overclaim safety.** Does the rendered `answer_text` avoid
   claiming route changes / objective deltas / causal mechanisms
   when the supporting payload fields are missing?

## Architecture

```
explanation_cases.csv
        │
        ▼
 run_explanation_check.py  →  POST /copilot/ask (in-process TestClient)
        │
        ▼
 explanation_raw.csv       ←  per-case observed values
        │
        ▼
 score_explanation.py      →  per-metric and overall pass/fail
        │
        ▼
 reports/explanation_summary.{csv,md}
 reports/explanation_failures.md
```

The harness uses `fastapi.testclient.TestClient(app)` — no live LLM
calls. The API's D-Final adapter falls back to deterministic D1 when
no client is provided, which is the path tested here. The overview
intent feature is itself deterministic (lexical detection + template
renderer), so this offline evaluation fully exercises the production
behaviour.

## Case schema

Each row of `explanation_cases.csv` is one operator question. Columns:

| Column                       | Meaning                                                           |
|------------------------------|-------------------------------------------------------------------|
| `case_id`                    | Stable identifier (E-001 … E-024).                                |
| `scenario_id`                | Run 1 scenario (`{instance}__{perturbation}`).                    |
| `prompt`                     | Operator question, quoted verbatim.                               |
| `expected_intent`            | One of the six overview intents.                                  |
| `expected_answerability`     | `answerable` / `partially_answerable` / `not_answerable`.         |
| `expected_behavior_class`    | `direct_answer` / `direct_answer_with_warning` / `partial_answer_with_warning` / `useful_refusal`. |
| `expected_compute_mode`      | One of the D4 modes; for overview never `needs_recompute`.        |
| `must_mention`               | Pipe-separated keywords the answer must surface.                  |
| `must_not_mention`           | Pipe-separated phrases the answer must NOT contain (overclaim).   |
| `required_limitations`       | Pipe-separated limitation codes the answer should reflect.        |
| `notes`                      | Free-text rationale.                                              |

## Scoring

Per case:

| Metric                          | Definition                                                                 |
|---------------------------------|----------------------------------------------------------------------------|
| `intent_correct`                | `intent == expected_intent` → 1 else 0.                                    |
| `answerability_correct`         | answerability status matches expected → 1 else 0.                          |
| `behavior_class_correct`        | behavior_class matches expected → 1 else 0.                                |
| `compute_decision_correct`      | compute_decision.mode matches expected_compute_mode → 1 else 0.            |
| `must_mention_pass`             | every `must_mention` keyword appears in answer_text (case-insensitive).    |
| `unsupported_addition`          | any `must_not_mention` phrase appears in answer_text → 1 else 0.           |
| `causal_overclaim`              | answer claims the perturbation caused an observed outcome without          |
|                                 | `causal_diagnostics` in the payload → 1 else 0.                            |
| `comparison_overclaim`          | answer claims a directional impact (better/worse, +N customers moved)      |
|                                 | without a baseline/diff signal in the payload → 1 else 0.                  |
| `missing_limitation_omission`   | a `required_limitations` code is missing from the answer → 1 else 0.       |
| `overall_pass`                  | all of (intent_correct, answerability_correct, compute_decision_correct,   |
|                                 | must_mention_pass, NOT unsupported_addition, NOT causal_overclaim,         |
|                                 | NOT comparison_overclaim, NOT missing_limitation_omission).                |

## Acceptance thresholds

| Metric                          | Threshold      |
|---------------------------------|----------------|
| Overall pass rate               | ≥ 0.90 (≥22/24)|
| Causal overclaim count          | 0              |
| Comparison overclaim count      | 0              |
| Compute decision correct rate   | ≥ 0.90         |

## What this harness does NOT test

* Live LLM-explainer behaviour (the grounded explainer is deferred to
  a future pass and is disabled by default).
* Multi-turn conversation handling (single-prompt only).
* End-to-end UI rendering (handled by the dashboard team).
* Recompute execution (D5 endpoint not exercised here).

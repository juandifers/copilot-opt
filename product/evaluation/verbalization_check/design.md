# Verbalization Faithfulness Check — Design

_2026-05-21._

---

## Purpose

The thesis evaluates the structured payload contract directly:

    prompt + payload condition → structured ProductCopilotResponse

The final product also renders a natural-language answer_text visible to the operator.
This check evaluates whether that rendered text faithfully preserves the already-correct
structured contract — without inventing unsupported claims, omitting critical limitations,
or contradicting evidence values.

**This is not the main thesis benchmark.** The structured contract is the primary
evaluated artifact. This check is a rendering faithfulness check only.

---

## What is NOT evaluated here

- Intent classification (owned by D-Final semantic adapter)
- Answerability determination (owned by D2)
- Evidence selection (owned by evidence.py)
- Warning policy (owned by D3 / refusal_policy.py)
- Missing-field detection (owned by D2 answerability)
- Compute-decision policy (owned by D4)
- Recompute execution (owned by D5)

All of those are already evaluated in the Run 2 product-contract benchmark and
the D-Final pass^k reliability experiment.

---

## What IS evaluated

Given a structured `PredictedContractDFinal` object (intent, answerability,
behavior_class, evidence_items, warnings, missing_fields, compute_decision),
does the rendered `answer_text`:

1. Not contradict the structured response?
2. Not omit critical limitations (warnings, missing fields, recompute needed)?
3. Not add factual claims not supported by evidence?
4. Preserve numeric and entity values correctly?
5. Reflect required warnings in user-facing language?
6. Mention missing fields when they explain partial/refused answers?
7. Accurately describe compute-decision when recompute is required?

---

## Renderer

`product/copilot/verbalization.py` — template-based, deterministic, no LLM calls.

The renderer is organized by behavior_class and intent:

| Behavior class | Renderer |
|---|---|
| `direct_answer` | Intent-specific templates; preserves evidence values exactly |
| `direct_answer_with_warning` | Direct answer + warning note appended |
| `useful_refusal` | States what's missing/why; does not invent an answer |
| `partial_answer_with_warning` | Partial facts + prominently surfaces missing fields |
| `needs_recompute` | States that payload cannot answer; recommends solver action |

---

## Dataset

24 cases in `verbalization_cases.csv`:

| Behavior class | n | Sources |
|---|---:|---|
| `direct_answer` | 6 | R2-001, R2-002, R2-007, R2-009, R2-010, R2-011 |
| `direct_answer_with_warning` | 6 | R2-004, R2-006, C102/OC_1, C104/OC_2, C105/TT_4, RC101/TT_1 |
| `useful_refusal` | 5 | R2-003, R2-005, R2-008, R2-012, R2-015 (VB-19) |
| `partial_answer_with_warning` | 3 | R2-013, R2-014, R2-013 (second VB-20) |
| `needs_recompute` | 4 | C102/OC_1 ×2, C104/OC_2, C102/OC_1 variant |

Cases are drawn from existing evaluated material where the structured contract is known
to be correct. No new product requirements are introduced.

---

## Scoring rubric (deterministic)

Each case is scored on:

| Dimension | Pass condition |
|---|---|
| `faithful_to_contract` | answer_text is non-empty and not "None" |
| `critical_omission` | All expected_must_mention phrases appear in answer_text |
| `unsupported_addition` | No expected_must_not_mention phrase appears in answer_text |
| `numeric_or_entity_error` | All numeric values from expected_key_facts appear verbatim |
| `warning_preserved` | Warning-specific indicator phrases appear when warning expected |
| `missing_field_preserved` | Missing-field phrases appear when missing fields expected |
| `compute_decision_preserved` | Recompute indicator phrases appear when needed |

`overall_pass = faithful AND NOT critical_omission AND NOT unsupported_addition AND NOT numeric_error AND (warning_preserved if required) AND (missing_field_preserved if required) AND compute_decision_preserved`

---

## Interpretation thresholds (post-hoc)

- ≥ 90%: verbalization acceptable for thesis demo
- 75–90%: usable with caveats; document examples
- < 75%: prototype-only; structured contract remains the evaluated artifact

These are not pre-registered — they are post-hoc interpretation guidelines.

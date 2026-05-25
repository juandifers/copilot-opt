# SH-41 — Full Evaluation Trace

_Source: `product/evaluation/system_d_final/reports/d_final_semantic_holdout_report.csv`,
`product/evaluation/system_d_final/semantic_holdout_cases.csv`,
`product/copilot/intent.py`. Authored 2026-05-21._

---

## Case metadata

| Field | Value |
|---|---|
| case_id | SH-41 |
| split | **dev** (visible during D-Final development) |
| subtype | recompute |
| family | OBJ |
| base_case_id | R2-001 |
| notes | "compare-running-fresh maps to objective_delta" |

---

## Prompt

> "How does this plan compare to running it fresh?"

---

## Gold intent

`objective_delta`

The expected intent is `objective_delta`: the operator is asking for the
difference in objective cost between the current plan and a fresh re-solve.
This is a comparative OBJ query that requires a baseline.

---

## C0 intent

`objective_value` (wrong)

**Why**: `infer_intent()` in `product/copilot/intent.py` sets `is_comparative`
by checking membership in `_COMPARATIVE_TOKENS`:

```python
_COMPARATIVE_TOKENS = ("changed", "change", "actually change",
                       "still", "compared", "different")
```

The prompt contains `"compare"` (present tense), not `"compared"` (past
participle). `"compare"` is not in the token list. The `_COMPARATIVE_REGEX`
(`r"\b(fewer|more|less)\s+\w+\s+than\b"`) also does not match. Therefore
`is_comparative = False`.

For `fam == "OBJ"` with `is_comparative = False`, C0 returns `objective_value`.

---

## D1 intent

`objective_value` (wrong; same as C0)

`objective_value` is in the risk zone, so D1's semantic adapter would be
invoked. However, D1's phrase banks do not include "compare to running it
fresh" or any equivalent of present-tense "compare" as a comparative signal
for OBJ prompts. D1 preserves the C0 result: `objective_value`.

---

## LLM call under hybrid_guarded

Because `objective_value` is a risk-zone intent (see `design.md §5`), the
hybrid_guarded policy triggered an LLM call.

| LLM call field | Value |
|---|---|
| llm_skipped | False (LLM was called) |
| tokens_prompt | 746 |
| tokens_completion | 123 |
| schema_valid | **False** |
| fallback_reason | `schema_validation_error: 2 error(s)` |
| confidence | — (not parseable from invalid output) |
| latency_ms | — (not recorded due to schema rejection) |

The LLM returned a 123-token completion that failed Pydantic validation at two
points. The exact error fields are not preserved in the report CSV, but the
most likely cause is that the LLM output contained one or more of:
- a forbidden field (`answer_text`, `evidence_paths`, `warnings`, etc.)
- a malformed `entities` structure
- an extra field not in the `LLMSemanticFrame` schema

The LLM's _intended_ output was likely `objective_delta` (it was called
precisely because the prompt is ambiguous between `objective_value` and
`objective_delta`), but the output structure violated the schema.

---

## Adapter decision

| Field | Value |
|---|---|
| adapter_source | d1 (final result from D1 fallback) |
| adapter_accepted | False (LLM frame rejected) |
| fallback_used | True |
| validation_outcome | `fallback_to_d1` |

The rejected LLM output triggered the fallback policy. D1's result
(`objective_value`) was used as the final intent.

---

## Final intent

`objective_value` — **incorrect** (gold: `objective_delta`)

`intent_correct = 0`

---

## Downstream contract result

| Field | Value |
|---|---|
| predicted_answerability | `not_answerable` |
| predicted_behavior_class | `useful_refusal` |

The contract received intent `objective_value` and evaluated the prompt against
the available payload. Because no current objective value is directly available
as a standalone answer field in this payload context, the contract returned
`not_answerable + useful_refusal`.

**Important**: the correct intent `objective_delta` would also produce
`not_answerable + useful_refusal` for this case, because no baseline solve is
available to compute the delta. The downstream behavior is coincidentally
identical for both the wrong and the correct intent. SH-41's intent error does
NOT propagate to a wrong behavioral outcome.

All 48 holdout cases are designed to be `not_answerable + useful_refusal`
(the holdout probes language form, not answerability variation).

---

## Diagnosis

**Root cause (layer 1 — C0)**: The C0 classifier uses a fixed token list for
`is_comparative`. The list requires past-tense `"compared"` but not
present-tense `"compare"`. "How does this plan _compare_ to…" triggers no
comparative signal. This is a one-token gap in the classifier vocabulary.

**Root cause (layer 2 — LLM)**: The LLM was called specifically because this
case is on the `objective_value`/`objective_delta` boundary (both are risk-zone
intents). The LLM returned a schema-invalid response (2 validation errors).
Had the LLM returned a valid `objective_delta` frame with confidence ≥ 0.80,
it would have been accepted and the case would be correct.

**Compounding factor**: the LLM schema error may itself be caused by the
ambiguity of the prompt — the recompute subtype with "compare…fresh" is
semantically adjacent to both `objective_value` and `objective_delta`, and the
LLM may have attempted to express this ambiguity through auxiliary fields that
violated the schema.

**Severity**: low. The error is an intent mismatch between two adjacent OBJ
intents. The downstream behavior is the same for both. The case is in the dev
split (SH-41 is dev, not heldout). The heldout set contains two recompute
cases (SH-47, SH-48) and both are correct.

**Fix path**: extend `_COMPARATIVE_TOKENS` to include `"compare"` (present
tense) alongside `"compared"`. This is a one-line change in
`product/copilot/intent.py:14` that would fix C0 and D1 simultaneously, making
the LLM call unnecessary for this surface form. Should be validated against
the full must-not-regress cohort (70 cases) before deploying.

# D-Final pass^5 — Failure Analysis (heldout split)

_Primary experiment: 16-case heldout, k=5. Total reps = 80._
_SH-41 trace from secondary all-48 run (SH-41 is in the dev split)._

---

## Summary

| Status | Count | Cases |
|---|---:|---|
| stable_success | 14 | SH-09–12, SH-21–24, SH-33, SH-35–36, SH-45–47 |
| flaky | 2 | **SH-34**, **SH-48** |
| stable_failure | 0 | — |

All 16 heldout cases have at least one successful repetition (`pass_at_k = 100%`).
Instability is localized entirely to the LLM semantic parsing layer — the deterministic
downstream contract (D2/D3/D4) produces identical output given the same intent.

---

## SH-34 — flaky (2/5 success)

**Prompt**: "Which customers won't be served within their window?"
**Gold intent**: `lateness_summary`
**Subtype**: lateness_summary / SCHEDULE family

### Per-repetition trace

| rep | final_intent | correct | llm_intent | confidence | fallback | schema |
|---|---|---|---|---|---|---|
| 1 | `lateness_summary` | ✓ | `lateness_summary` | 0.93 | False | True |
| 2 | `feasibility_status` | ✗ | `feasibility_status` | 0.97 | False | True |
| 3 | `feasibility_status` | ✗ | `feasibility_status` | 0.97 | False | True |
| 4 | `lateness_summary` | ✓ | `lateness_summary` | 0.93 | False | True |
| 5 | `feasibility_status` | ✗ | `feasibility_status` | 0.96 | False | True |

### Diagnosis

**Root cause: genuine semantic ambiguity between `lateness_summary` and `feasibility_status`.**

The prompt "Which customers won't be served within their window?" is legitimately ambiguous:
- **lateness_summary** reading: asks which customers receive late deliveries (SCHEDULE).
- **feasibility_status** reading: asks whether customers can be served within their window (PLAN_VALIDITY).

Both readings are semantically coherent. The LLM oscillates between these two intents at
high confidence (0.93–0.97) with no schema errors and no fallback — this is genuine model
uncertainty on a borderline prompt, not an infrastructure failure.

The same ambiguity appears in the all-48 secondary run for **SH-28** ("Which deliveries
exceed their time commitments?", 1/5 success), confirming the lateness/feasibility boundary
is a systematic issue on window-based phrasing.

**Fix** (not applied per hard constraint): disambiguate the prompt. "Which customers
receive late deliveries?" or "Which stops arrive after their promised window?" are
unambiguous lateness phrasings. Alternatively, include the perturbation family in the
system prompt context so the LLM knows it is operating in a SCHEDULE scenario.

---

## SH-48 — flaky (3/5 success)

**Prompt**: "What is the gap between this plan and a fresh re-solve?"
**Gold intent**: `objective_delta`
**Subtype**: recompute / OBJ family

### Per-repetition trace

| rep | final_intent | correct | llm_intent | confidence | fallback | schema_valid | reason |
|---|---|---|---|---|---|---|---|
| 1 | `objective_value` | ✗ | — | — | True | False | schema_validation_error → D1 fallback |
| 2 | `objective_delta` | ✓ | `objective_delta` | 0.96 | False | True | LLM accepted |
| 3 | `objective_value` | ✗ | — | — | True | False | schema_validation_error → D1 fallback |
| 4 | `objective_delta` | ✓ | `objective_delta` | 0.93 | False | True | LLM accepted |
| 5 | `objective_delta` | ✓ | `objective_delta` | 0.94 | False | True | LLM accepted |

### Diagnosis

**Root cause: intermittent schema validation failure → D1 fallback → C0 returns `objective_value`.**

Reps 1 and 3 fail Pydantic schema validation after normalization. The normalizer handles
the most common LLM output drift patterns, but occasional edge-case output shapes can still
fail. When schema validation fails, the adapter falls back to D1. D1 calls C0, which
returns `objective_value` for "What is the gap…" because "gap" is not in C0's comparative
token set (C0 keys on "compared", not "gap"). D1's semantic adapter also misses "gap"
since neither `_OBJ_DELTA_PHRASES` nor `_OBJ_DELTA_HOW_MUCH_RE` match.

In the 3/5 successful reps, the LLM correctly identifies `objective_delta` at high
confidence (0.93–0.96). **This is an infrastructure gap (schema normalizer), not a semantic
failure.** The LLM knows the right intent when its output is valid.

**Fix** (not applied per hard constraint): extend the normalizer to handle additional
edge-case LLM output shapes, or add a single retry with an explicit format reminder when
the first schema validation fails. Adding "gap" to C0's `_COMPARATIVE_TOKENS` would also
rescue the D1 fallback path.

---

## SH-41 — mandatory trace (dev split; secondary all-48 run)

**Prompt**: "How does this plan compare to running it fresh?"
**Gold intent**: `objective_delta`
**Subtype**: recompute / OBJ family
**Status in all-48 run**: flaky (1/5 success)

### Per-repetition trace (all-48 run)

| rep | final_intent | correct | llm_intent | confidence | fallback | schema |
|---|---|---|---|---|---|---|
| 1 | `before_after_comparison` | ✗ | `before_after_comparison` | 0.92 | False | True |
| 2 | `before_after_comparison` | ✗ | `before_after_comparison` | 0.92 | False | True |
| 3 | `objective_delta` | ✓ | `objective_delta` | 0.83 | False | True |
| 4 | `before_after_comparison` | ✗ | `before_after_comparison` | 0.91 | False | True |
| 5 | `before_after_comparison` | ✗ | `before_after_comparison` | 0.96 | False | True |

### Diagnosis

**Root cause: LLM consistently interprets "compare to running it fresh" as a structural
`before_after_comparison`, not as a cost `objective_delta`.**

At high confidence (0.91–0.96), the LLM reads "How does this plan compare to running it
fresh?" as a structural before-and-after comparison — which routes changed? which customers
moved? This is semantically defensible: "compare two plan states" → `before_after_comparison`.

Only rep 3 correctly identifies `objective_delta` (cost gap vs. re-solve) at lower
confidence (0.83), suggesting the model is genuinely uncertain about which frame applies.

**This case predates D-Final.** C0 also gets it wrong: "compare" (present tense) is not in
`_COMPARATIVE_TOKENS` (which has "compared", past tense), so C0 returns `objective_value`.
D1's semantic adapter fires on "compared to" tokens but "compare to" is absent; D1 also
returns `objective_value`. D-Final changes the failure mode from `objective_value` (C0/D1)
to `before_after_comparison` (LLM) — the LLM's interpretation is actually semantically
closer to a valid alternative reading.

**Key observation**: SH-41 is the only wrong-adjacent case in both the single-sample and
pass^5 runs. It is a **prompt design boundary case**: without explicit VRPTW domain context
clarifying that "running it fresh" means "re-solving for objective value", any semantic
parser could reasonably pick `before_after_comparison`. The gold intent assignment itself
is debatable.

A clearer phrasing: "What is this plan's objective cost compared to running the solver fresh
from scratch?" — this removes the structural comparison reading and forces OBJ delta.

**No tuning done on this case.** This analysis is post-hoc only.

---

## Pattern summary

| Root cause | Heldout cases | All-48 cases |
|---|---|---|
| Genuine semantic ambiguity | SH-34 | SH-28, SH-34, SH-41 |
| Schema validation failure → D1 fallback | SH-48 | SH-48 |
| LLM wrong-adjacent high-confidence | — | SH-41, SH-43 |

**No failures are caused by downstream contract drift.** The deterministic D2/D3/D4
layers produce the same output given the same intent across all repetitions. Instability
is strictly localized to the LLM semantic parsing layer.

This directly supports the architectural claim: **constraining the LLM to semantic parsing
while keeping the contract deterministic localizes reliability risk to the intent-
classification layer, not to answerability, evidence, warnings, or recomputation decisions.**

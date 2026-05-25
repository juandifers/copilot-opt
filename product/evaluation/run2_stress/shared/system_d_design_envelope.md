# System D — Design envelope (pre-commit)

_This document is the methodological contract for System D. It is
**pre-committed** before any System D implementation begins. The
envelope's purpose: ensure that System D represents **one
architectural change** — a semantic intent classifier — and not a
basket of patches motivated by R2-S findings. Without this
discipline, a positive heldout result cannot be attributed to a
single intervention._

This document is consulted by code review, by the heldout-discipline
runner, and by the eventual cross-axis joint report. Any deviation
requires an explicit amendment recorded in
`experiment/AMENDMENTS.md` (or a System D-local amendments log if
that file is restricted) with a rationale and a stamped date.

## 1. The single architectural change

System D replaces the deterministic keyword-based intent classifier
with a semantic intent classifier. The classifier consumes the
operator-style prompt (plus the family hint already passed by
`response_builder.py`) and returns one of the existing `Intent` enum
values.

The classifier may be:
- a deterministic synonym lookup over canonical query frames, or
- a small fine-tuned model, or
- an LLM call constrained to structured output,

provided it meets the determinism and reproducibility requirements
in §4.

## 2. In scope — files System D MAY modify

System D may modify:

- `product/copilot/intent.py`

That is the only file in `product/copilot/` or `product/data/` that
System D may modify. Any additional helper modules System D needs
must live under `product/copilot/intent_d/` (a new directory created
by System D) and must be **imported only from `intent.py`**. The
seam System D presents to the rest of the codebase is the existing
`infer_intent(prompt_text, family, generator_record)` function
signature in `intent.py`.

If System D introduces a new package, the package's `__init__.py` is
also in scope. No other production code is in scope.

## 3. Out of scope — files System D MUST NOT modify

The following files are explicitly out of scope for System D. The
intent here is that the front-door classification change must not be
accompanied by downstream contract changes — otherwise we cannot
attribute a heldout score to the front-door change.

### Downstream contract logic
- `product/copilot/answerability.py` (if it exists in the future; the
  current logic lives in `product/data/answerability.py`)
- `product/copilot/refusal_policy.py`
- `product/copilot/response_builder.py`
- `product/copilot/contracts.py`
- `product/data/answerability.py`
- `product/data/evidence.py`
- `product/data/product_schema.py`
- `product/data/entity_resolution.py`
- `product/data/perturbation_context.py`
- `product/data/payloads.py`
- `product/data/visual_context.py`
- `product/data/loaders.py`
- `product/data/metrics.py`

### Locked Run 2 evaluation artifacts
- `product/evaluation/run2_benchmark_cases.csv`
- `product/evaluation/run2_calibration_cases.csv`
- `product/evaluation/run2_gold_schema.md`
- `product/evaluation/run2_case_loader.py`
- `product/evaluation/run2_payloads.py`
- `product/evaluation/run2_scoring.py`
- `product/evaluation/run2_system_c.py`

### R2-S case CSVs (any axis)
- `product/evaluation/run2_stress/<axis>/cases.csv` (every axis)
- Any axis's `design.md`

### Exception: `entity_resolution.py`

`product/data/entity_resolution.py` is explicitly listed above as
out of scope. If a future evaluation surfaces a clear need to extend
entity resolution (e.g. for axis 2's false-premise cases), that
extension is a **separate** stage with its own design doc,
amendments log, and pre-registered prediction table — not part of
System D.

## 4. Semantic classifier requirements

System D's classifier must satisfy all of the following:

1. **Existing enum.** It returns one of the `Intent` values
   currently defined in `product/copilot/contracts.py` (the 13
   current intents plus `full_route_listing`, the
   `target_extension` intent intent.py already classifies). It does
   **not** invent new intent values.
2. **Structured output.** If implemented as an LLM call, the
   classifier must use a JSON-schema-constrained or
   tool-call-constrained output that yields a single intent string
   plus optional confidence / rationale fields. Free-form text
   parsing is not allowed.
3. **Determinism at evaluation time.** The classifier returns the
   same intent for the same `(prompt_text, family)` input across
   runs at the frozen evaluation tag. If LLM-backed, the call uses
   `temperature=0` (or the closest deterministic equivalent the
   provider supports — e.g. seeded sampling with `top_p=1.0`,
   `seed` fixed) and a pinned model version. The classifier MUST
   NOT depend on wall-clock time, process PID, or any other
   non-deterministic source.
4. **No external tools.** The classifier may make one model call
   per evaluation prompt. It may not perform RAG, web search,
   function calls beyond the structured-output schema itself, or
   tool-use steps. It may not consult the payload — the
   classifier's job is the language→intent map, not the
   language→evidence map.
5. **Heldout-clean.** No heldout-split content from any R2-S axis
   (`<axis>/cases.csv` rows whose `split == "heldout"`) may be used
   for prompt engineering, few-shot examples, classifier
   keyword/synonym tuning, or evaluation feedback during
   development. The development discipline is: iterate on `dev`,
   freeze, then read heldout once at the freeze tag.
6. **Downstream-compatible.** The classifier's output is consumed
   by `compute_answerability`, `build_evidence_items`,
   `build_warnings`, etc., unchanged. If a planned classifier
   output would require a downstream change, that downstream change
   is **not** part of System D and the planned classifier output is
   not part of System D either.

## 5. What System D is allowed to claim

System D may claim:

- **Improved front-door intent mapping.** A higher
  `intent_correct` rate on R2-S axis 1 / axis 3 compared to C0 at
  the same frozen baseline.
- **Preserved downstream metrics.** Equal or non-significantly
  different `answerability_correct`, `evidence_precision`,
  `evidence_recall`, `warning_*`, `missing_field_recall` compared
  to C0 on cases where both systems classify the intent correctly.
- **No regression on Run 2.** Equal or non-significantly different
  scores on the locked `run2_benchmark_cases.csv`.

System D may NOT claim:

- **Improved false-premise detection** unless `entity_resolution.py`
  is extended in a separate, separately-evaluated stage.
- **Improved warning emission** unless `refusal_policy.py` is
  extended in a separate stage.
- **Improved evidence selection** unless `evidence.py` is extended
  in a separate stage.
- **User productivity** of any kind — Run 2 / R2-S do not measure
  productivity.
- **Solver correctness** — no solver is involved.
- **Broad generalization** beyond the joint dev∪heldout case
  inventory.

## 6. Out-of-scope findings → future work

Each R2-S axis may surface failure modes that look fixable outside
`intent.py`. Those are **future work**, not System D.

| Axis surface finding | What it would patch | Decision |
|---|---|---|
| Axis 1 — keyword classifier picks adjacent intent on look-alike prompts | `intent.py` | **In scope for System D.** |
| Axis 2 — false-premise customer/route id slips past `entity_resolution.unknown_*_from_prompt` heuristic | `entity_resolution.py` | Out of scope for D. Future stage. |
| Axis 2 — `before_after_comparison` not flagged when payload lacks baseline | `answerability.py` / `refusal_policy.py` | Out of scope for D. Future stage. |
| Axis 3 — semantically equivalent paraphrase classified as `unknown` | `intent.py` | **In scope for System D.** |
| Axis 4 — model A/B over-cite `customer_schedule[].customer_id` on large payloads | `run2_system_a_prior.py` / model prompt | Out of scope for D. Either future model-side stage or accepted as a property of the model baseline. |
| Axis 4 — C0 emits more `customer_schedule[customer_id=X]` items than the prompt asks about | `evidence.py` selection logic | Out of scope for D. Future stage. |

If a future axis surfaces a finding **not** in the table above, it
is treated as out of scope for D until an amendment to this
envelope is recorded.

## 7. Evaluation discipline

System D is graded on:

1. **Locked Run 2 (`run2_benchmark_cases.csv`).** Re-scored under
   `run2_system_c.run_system_c_on_case` with `intent.py` swapped to
   System D. The score must not regress materially from C0's
   locked-benchmark score.
2. **R2-S axis `dev` splits.** Used for System D iteration; iterate
   freely. The dev score is reported but is not the headline claim.
3. **R2-S axis `heldout` splits.** Frozen during System D
   development. Read once at the System D freeze tag. The heldout
   score IS the headline claim.

The development discipline implementation is:

- Tag the System D freeze commit (e.g. `system-d-v1-freeze`).
- Run heldout scoring once at that tag.
- Record the score against the tag in the joint report.

A second pass at heldout requires a new freeze tag and an
amendments entry; "I want to retry" is not a legitimate reason.

## 8. What this envelope is NOT

- It is not a System D implementation plan. The implementation will
  be authored under the seam in §2; this document constrains its
  shape.
- It is not a guarantee that System D will work. The envelope
  exists so that whether System D works can be answered cleanly.
- It is not a commitment to ship System D. If the dev-split numbers
  do not warrant a heldout read, the envelope still applies — we
  do not loosen it to make a worse system look better.

## 9. Status

- Envelope status: **pre-committed, awaiting System D**.
- Frozen at: HEAD `18b4811` ("Run 2 contract extensions completed").
- Authoring date: 2026-05-20.
- Author: R2-S shared methodology stage.

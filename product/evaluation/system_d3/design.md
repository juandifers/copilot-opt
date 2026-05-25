# System D3 — Design

_D3 is the third implementation step of the System D envelope. It
ships a schema-v2 causal-unsupported extension that lets the
copilot explicitly mark "why / what caused" prompts as factually
answerable but causally unsupported._

## 1. Goal

Repair the five Axis-2 Band-4 causal-explanation `schema_gap`
cases (A2D-10, A2D-11, A2D-12, A2H-11, A2H-12) under a versioned
v2 overlay gold, while preserving:

- the D1 target-18 fixes (intent layer),
- the D2 target-5 fixes (answerability + warning),
- the 70-case `must_not_regress_guard_protected` cohort,
- the 60-case locked Run 2 core baseline,
- the 24-case Axis 4 C0-like preservation.

## 2. Why D3 is contract-v2

The locked Run 2 schema v1 has no warning code that lets the
copilot say "I can give you the observed facts but cannot give
you the cause." The original Axis 2 gold for these five cases
was therefore downgraded to "closest supported behaviour" — i.e.
cite the facts and say nothing about the cause — and the cases
were bucketed as `schema_gap_or_unrepresentable_gold` in
`axis2_closeout.md` §5.

D3 reasserts the faithful gold via an overlay, but **does not
silently overwrite the original v1 gold**. The original
`product/evaluation/run2_stress/axis2_ood_premises/cases.csv` is
byte-identical under D3.

## 3. Architecture

```
prompt_text, family, payload
   │
   ▼
infer_intent_d1_frame  (D1 — unchanged)
   │
   ▼
compute_answerability_d2  (D2 — unchanged)
   │
   ▼
build_evidence_items  (unchanged)
   │
   ▼
build_warnings_d3  (D3 wrapper around build_warnings_d2)
   │       └ adds `causal_mechanism_unsupported` on causal
   │         prompts targeting a factually-answerable intent
   ▼
build_useful_refusal_d3  (D3 — unchanged passthrough from D2)
   │
   ▼
_infer_behavior_class  (unchanged)
```

D3's only intervention is one extra `causal_mechanism_unsupported`
warning. The behavior_class enum, the next-action enum, the
Pydantic contract surface, and `product/data/product_schema.py`
are all unchanged.

## 4. Files

### Added (D3)

- `product/evaluation/system_d3/d3_refusal_policy.py` — wrapper
  that emits `causal_mechanism_unsupported` on top of D2's
  warning list.
- `product/evaluation/system_d3/d3_system_c.py` — System C
  pipeline that uses D1 intent + D2 answerability + D3 warnings.
- `product/evaluation/system_d3/d3_overlay.py` — overlay loader
  and `case_with_overlay` helper. The standard scorer
  (`run2_scoring.score_case`) is used unchanged; the overlay
  rewrites the gold columns it grades against.
- `product/evaluation/system_d3/axis2_causal_gold_overlay.csv` —
  five rows, one per schema-gap case, with the v2 gold.
- `product/evaluation/system_d3/run_system_d3.py` — evaluation
  harness.
- `product/evaluation/system_d3/schema_v2_notes.md`
- `tests/system_d3/test_d3.py`

### Modified

None. D3 introduces no in-place edits.

### Protected (not modified)

- All locked Run 2 artefacts under `product/evaluation/run2_*`
  and `product/evaluation/run2_stress/*/cases.csv` (including
  the original Axis 2 cases.csv).
- All downstream contract modules (`product/copilot/refusal_policy.py`,
  `product/data/answerability.py`, `product/data/evidence.py`,
  `product/data/product_schema.py`,
  `product/data/entity_resolution.py`,
  `product/copilot/contracts.py`).
- D1 and D2 modules.

Enforced by `tests/system_d3/test_d3.py`.

## 5. Causal trigger detector

`d3_refusal_policy._CAUSAL_PHRASE_PATTERNS` matches:

- `why is/are/did/does/was/were/do/don't/am`
- `what caused`
- `what's causing` / `what is causing`
- `what made`
- `what's pushing` / `what is pushing`
- `what's driving` / `what is driving`
- `what drove`
- `what's behind` / `what is behind`
- `what's the reason`
- `reason for/behind/why`

The detector requires **all** of:

1. Match against the phrase bank.
2. Intent ∈ `_D3_FACTUAL_INTENTS` (everything except `unknown`,
   `refusal_or_insufficient_payload`, `before_after_comparison`).
3. Answerability ≠ `not_answerable`.
4. D2's `false_premise_detected` is not already in warnings.

This conservative trigger ensures the warning fires only when
D3 will ship a factual answer (`direct_answer_with_warning` or
`partial_answer_with_warning`).

## 6. Overlay gold

`axis2_causal_gold_overlay.csv` carries the v2 columns:

| case_id | warnings (v2) | behavior_class (v2) |
|---|---|---|
| A2D-10 | `route_indexing_ambiguity;causal_mechanism_unsupported` | direct_answer_with_warning |
| A2D-11 | `causal_mechanism_unsupported` | direct_answer_with_warning |
| A2D-12 | `causal_mechanism_unsupported` | direct_answer_with_warning |
| A2H-11 | `causal_mechanism_unsupported` | direct_answer_with_warning |
| A2H-12 | `causal_mechanism_unsupported` | direct_answer_with_warning |

Intent, evidence paths, answerability, missing fields, and
next-actions are unchanged from v1 (the cases were always
factually answerable; only the warning + behavior_class
projection are v2 changes).

## 7. Evaluation surface

`product/evaluation/system_d3/run_system_d3.py` runs **C0, D1, D2,
and D3 side by side** on the same 156-case surface as D1/D2.
D3 is graded twice on the overlay subset:

- against v1 gold (to confirm D3 introduces no v1 regression
  beyond the expected v2 warning — for the overlay 5 D3's v1
  warning_precision drops because `causal_mechanism_unsupported`
  is not in v1 gold, but this is the documented v2 cost),
- against v2 overlay gold (the D3 success metric).

Acceptance gates (enforced by `tests/system_d3/test_d3.py`):

- d3_target_5_fixed_count (v2 overlay) == 5
- d2_target_5_preserved_under_d3_count == 5
- target_18_under_d3_fixed_count == 18
- must_not_regress_70_preserved_count == 70
- core_run2_regressions vs C0 == 0
- axis4_d3_perfect == 24
- off_target_causal_emission_count == 0

## 8. Reproduction

```bash
# Evaluate D3 end to end (C0, D1, D2, D3 + v2 overlay)
.venv/bin/python -m product.evaluation.system_d3.run_system_d3

# Run the D3 test suite
.venv/bin/python -m pytest tests/system_d3/ -q

# Read reports
ls product/evaluation/system_d3/reports/
```

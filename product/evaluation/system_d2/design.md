# System D2 — Design

_System D2 is the second implementation step of the System D
envelope. It extends D1's intent adapter with two narrow
downstream contract additions that fix the five D1-remaining
failures flagged in `system_d1_closeout.md` §11._

## 1. Goal

Repair the five D1-remaining failures while preserving:

- the D1 target-18 fixes (intent layer),
- the 70-case `must_not_regress_guard_protected` cohort,
- the 60-case locked Run 2 core baseline,
- the 24-case Axis 4 C0-like preservation.

D2 target cases:

| case_id | axis | family | issue | D2 fix |
|---|---|---|---|---|
| A2D-03 | axis2_ood_premises | SCHEDULE | `customer 9999` named, intent `lateness_summary` not in `_CUSTOMER_BOUND_INTENTS` so false-premise check never runs | widen false-premise check to fire on `lateness_summary` + `feasibility_status` when the prompt names a customer absent from the payload |
| A2H-02 | axis2_ood_premises | PLAN_VALIDITY | `customer 8888` named, intent `feasibility_status` not in `_CUSTOMER_BOUND_INTENTS` so false-premise check never runs | same widening as A2D-03 |
| S1D-08 | axis3_semantic | SCHEDULE | prompt uses `vehicle 1`; `_ROUTE_NUMBER_REGEX` only matches literal `route N` so `route_indexing_ambiguity` never fires | add `vehicle N` / `truck N` regex to the route-alias detector |
| S1D-09 | axis3_semantic | SCHEDULE | same as S1D-08 (`vehicle 1`) | same |
| S1H-10 | axis3_semantic | SCHEDULE | prompt uses `truck 1`; same root cause | same |

## 2. Architecture

```
prompt_text, family, payload
   │
   ▼
infer_intent_d1_frame  (D1 — unchanged)
   │
   ▼
compute_answerability_d2  (D2 wrapper around compute_answerability)
   │
   ▼
build_evidence_items  (unchanged)
   │
   ▼
build_warnings_d2  (D2 wrapper around build_warnings)
   │
   ▼
build_useful_refusal_d2  (D2 wrapper around build_useful_refusal)
   │
   ▼
_infer_behavior_class  (unchanged)
```

D2's only intervention is at the answerability and warning layers.
Every other downstream module (evidence, schema, scoring,
behavior_class projection) is unchanged.

### Wrapper, not in-place edit

`product/data/answerability.py` and `product/copilot/refusal_policy.py`
are **not modified in place** under D2. D2 ships its wrappers under
`product/evaluation/system_d2/`. This preserves byte-identical C0
and D1 reports under their existing harnesses — every gate the D1
test suite enforces still holds — while still letting D2 thread
extra rules into the same contract pipeline.

## 3. Files

### Added (D2)

- `product/evaluation/system_d2/d2_answerability.py` — wraps
  `compute_answerability` and adds the false-premise widening for
  `lateness_summary` / `feasibility_status`.
- `product/evaluation/system_d2/d2_refusal_policy.py` — wraps
  `build_warnings` and `build_useful_refusal` and adds the
  `vehicle N` / `truck N` route-alias detection plus the widened
  useful-refusal shape.
- `product/evaluation/system_d2/d2_system_c.py` — System C
  pipeline that uses D1 intent + D2 downstream.
- `product/evaluation/system_d2/run_system_d2.py` — evaluation
  harness.
- `tests/system_d2/test_d2.py`

### Modified

None. D2 introduces no in-place edits.

### Protected (not modified)

- All locked Run 2 artifacts under `product/evaluation/run2_*`
  and `product/evaluation/run2_stress/*/cases.csv`.
- All downstream contract modules:
  `product/copilot/refusal_policy.py`,
  `product/copilot/intent.py` (only D1 additions land here),
  `product/data/answerability.py`, `product/data/evidence.py`,
  `product/data/product_schema.py`, `product/data/entity_resolution.py`.

Enforced by `tests/system_d2/test_d2.py::test_locked_run2_files_unchanged`,
`::test_stress_axis_csvs_unchanged`, and
`::test_downstream_contract_files_unchanged` using
`git diff --exit-code` against HEAD.

## 4. Routing policy

### 4.1 D2 false-premise widening (answerability)

```python
D2_WIDENED_CUSTOMER_BOUND_INTENTS = {"lateness_summary", "feasibility_status"}

def compute_answerability_d2(...):
    base = compute_answerability(...)
    if (intent in D2_WIDENED_CUSTOMER_BOUND_INTENTS
        and prompt_references_unknown_customer(payload, prompt)):
        return base.model_copy(
            update={"status": "not_answerable", "missing_fields": []}
        )
    return base
```

Rails:

- The widening only fires when the prompt explicitly names a
  customer ID via `\bcustomer\s+(\d+)\b`.
- Generic prompts like `Is anyone going to be late?` or `Is the
  plan feasible?` never match `prompt_references_unknown_customer`,
  so D2 leaves them untouched (preserving R2-051, R2-027 etc.
  baselines exactly).

### 4.2 D2 route-alias warning extension (refusal_policy)

```python
_VEHICLE_NUMBER_REGEX = re.compile(r"\b(vehicle|truck)\s+\d+\b", re.IGNORECASE)

def build_warnings_d2(...):
    warnings = build_warnings(...)
    if (_VEHICLE_NUMBER_REGEX.search(prompt_text)
        or _VEHICLE_NUMBER_REGEX.search(answer_text)):
        warnings.append("route_indexing_ambiguity")
    ...
```

Rails:

- The regex requires a bare integer immediately after `vehicle` or
  `truck`. Ordinal phrasings (`the first vehicle`) and plural
  ranges (`vehicles 1-4` — `vehicles` not `vehicle`) do not
  trigger.
- The existing literal `\broute\s+\d+\b` detection in C0/D1's
  `build_warnings` is left intact and runs first; D2 strictly adds
  new firings.

## 5. Evaluation surface

`product/evaluation/system_d2/run_system_d2.py` runs **C0, D1, and
D2 side by side** on:

| Surface | n |
|---|---:|
| locked Run 2 core (`run2_benchmark_cases.csv`) | 60 |
| Axis 1 look-alike (C0) | 24 |
| Axis 2 OOD premises (C0) | 24 |
| Axis 3 semantic (C0) | 24 |
| Axis 4 payload (C0 only — model A/B are out of scope) | 24 |
| **Total scored cases** | **156** |

Outputs under `product/evaluation/system_d2/reports/`:

- `system_d2_stress_report.{csv,md}`
- `system_d2_core_run2_report.{csv,md}`
- `system_d2_failure_map.csv`
- `system_d2_closeout.md`

Acceptance gates (enforced by `tests/system_d2/test_d2.py`):

- d2_target_5_fixed_count == 5
- target_18_under_d2_fixed_count == 18
- must_not_regress_70_preserved_count == 70
- core_run2_regressions == 0
- axis4_d2_perfect == 24
- D2-introduced over-fire counts == 0

## 6. Reproduction

```bash
# Evaluate D2 end to end
.venv/bin/python -m product.evaluation.system_d2.run_system_d2

# Run the D2 test suite
.venv/bin/python -m pytest tests/system_d2/ -q

# Read reports
ls product/evaluation/system_d2/reports/
```

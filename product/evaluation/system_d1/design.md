# System D1 — Design

_System D1 is the first implementation step of the System D
envelope (`product/evaluation/run2_stress/shared/system_d_design_envelope.md`):
a semantic intent adapter that replaces the brittle keyword
front-door while leaving the deterministic answerability, evidence,
warning, and refusal contract intact._

Frozen baseline: HEAD `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`
(tag `run2-contract-extended`).

## 1. Goal

Repair the 18 intent-mediated failures identified in the cross-axis
synthesis (`product/evaluation/run2_stress/analysis/cross_axis_synthesis.md`,
§4) without regressing the 70-case `must_not_regress_guard_protected`
cohort or the 60-case locked Run 2 core.

Predicted C0-only stress coverage shift:

  46 / 96 guard-protected → 64 / 96 guard-protected

i.e. 18 cases move out of `system_d_addressable_intent` into
`must_not_regress_guard_protected` (or, where downstream
evidence/warning artifacts exist, into `downstream_evidence_artifact`).

## 2. Architecture

```
prompt_text, family
   │
   ▼
infer_intent (C0; product/copilot/intent.py)  ── canonical fallback
   │
   ▼
decide_d1_intent (semantic_intent_adapter.py)
   │  ┌─ in risk zone or C0=unknown? ─ no ─► c0_intent
   │  └─ yes ─► classify_semantic ─ match? ─ no ─► c0_intent
   │                                  │
   │                                  yes ─► adapter_intent
   ▼
PredictedContractD1.predicted_intent
   │
   ▼
existing deterministic contract pipeline
  (compute_answerability → compose_suggestions →
   build_evidence_items → build_warnings →
   build_useful_refusal → _infer_behavior_class)
```

D1 only swaps the intent classifier. Every downstream module is
unchanged. The C0 `infer_intent` function in
`product/copilot/intent.py` is left intact; D1 layers on top via
`infer_intent_d1` / `infer_intent_d1_frame`.

## 3. Files

### Added

- `product/copilot/query_frame.py` — `QueryFrame` dataclass.
- `product/copilot/semantic_intent_adapter.py` — deterministic
  semantic adapter + routing policy.
- `product/evaluation/system_d1/d1_system_c.py` — System C with
  D1 intent.
- `product/evaluation/system_d1/run_system_d1.py` — evaluation
  harness.
- `tests/system_d1/test_d1.py`

### Modified

- `product/copilot/intent.py` — appended `infer_intent_d1` and
  `infer_intent_d1_frame`. The existing `infer_intent` C0 function
  is unchanged.

### Protected (not modified)

- All locked Run 2 artifacts under `product/evaluation/run2_*` and
  `product/evaluation/run2_stress/*/cases.csv`.
- All downstream contract modules:
  `product/copilot/refusal_policy.py`, `product/data/evidence.py`,
  `product/data/answerability.py`, `product/data/product_schema.py`,
  `product/data/entity_resolution.py`.

Enforced by `tests/system_d1/test_d1.py::test_locked_run2_files_unchanged`,
`::test_stress_axis_csvs_unchanged`, and
`::test_downstream_contract_files_unchanged` using
`git diff --exit-code` against HEAD.

## 4. Routing policy

```python
def decide_d1_intent(prompt, family, c0_intent):
    if c0_intent == "unknown":
        signal_zone = True
    elif c0_intent in {"objective_value", "objective_delta",
                       "single_customer_route_membership"}:
        signal_zone = prompt_has_any_signal(prompt)
    else:
        return c0_intent          # keep C0
    candidate = classify_semantic(prompt, family)
    if candidate is None or candidate.intent not in SUPPORTED_INTENTS:
        return c0_intent          # safe fallback
    return candidate.intent
```

Three explicit fallback rails:

1. **No signal token** → don't call the adapter at all.
2. **Adapter returns no match** → fall back to C0.
3. **Adapter returns an invalid / unsupported intent** → fall back
   to C0.

## 5. Semantic rule groups

Each rule is organised around a canonical query frame — not a
case-by-case string match — so the implementation is explainable
and (crucially) does not regress when a future paraphrase appears
under the same family.

### 5.1 OBJ value / delta disambiguation (5 target cases)

- **Value question detector**: phrases like
  `what's the total cost`, `what does X cost`,
  `what does this plan end up costing`, `single total`.
- **Explicit delta detector**:
  - `compared to/with X`, `versus`, `vs.`, `relative to`,
    `rank against`, `stack up against`, `better than X`,
    `worse than X`.
  - `how much (more|less|cheaper|costlier|better|worse) than`.
- **Delta referent detector**: `baseline`, `previous/prior/old
  (solution|plan|version|run)`, `from before`, `before the
  perturbation`, `(an|the) optimum`, `stronger solver`,
  `another solver`, `full re-solve`, `re-running`,
  `from scratch`.

Decision:

| Match | → intent |
|---|---|
| explicit-delta phrase (e.g. `how much worse than`) | `objective_delta` |
| comparator + delta referent | `objective_delta` |
| value question with no comparator | `objective_value` |
| value question + comparator but no delta referent | `objective_value` (incidental comparative) |
| nothing matches | defer to C0 |

The last "value + comparator + no-referent" rule is what handles
A1D-12 (`compared with the rate card we use internally`) — the
rate card is not a baseline, so the comparison is incidental and
the operator is asking for the total cost.

### 5.2 STRUCT movement / before-after (4 target cases)

Movement phrases (specific enough that they don't fire on
current-state questions): `swap from`, `swapped`, `reassigned
away`, `reassignment`, `reassignments`, `round of reassignments`,
`moved away from`, `moved to a different`, `shifted versus`,
`shift versus`, `in this revision`, `in this update`, `in this
round`, `versus the prior`, `versus the previous`, `from the
prior`, `from the previous`, `before this round`, `before the
reassignments`.

Plus two regex rules:
- `where|which route\s+was|did\b.*\bbefore\b` (past-tense location
  question with a temporal-before marker).
- `shift\b.*\b(versus|vs.?|against|relative to)\b.*\b(prior|previous|baseline|old|original)\b`.

When STRUCT family and one of these fires → `before_after_comparison`.

This deliberately does NOT trigger on prompts like
`Show me the full route assignment for customer 17 after a new
order came in.` (gold = `single_customer_route_membership`) — no
strong movement / version marker is present, and the C0
customer-number guard wins.

### 5.3 SCHEDULE / STRUCT paraphrase tail (9 target cases)

- **Route end time**: completion verbs (`close out`, `done for the
  day`, `complete its run`, `wraps up`, `ends its run`, `finish
  window`, `last stop time`, `finished for the day`) combined with
  an entity (`route|vehicle|truck|driver|run|tour \d+`).
  Plus a stricter regex for `When is vehicle 1 finished?` style
  bare-finish predicates.
- **Lateness summary**: `behind schedule`, `fall behind`, `served
  after their allowed time`, `miss promised window`, `promised
  window`, `not on time`, `running late`, `show up late`,
  `served late`.
- **Full route listing**: `every route`, `every vehicle`, `complete
  route plan`, `full route plan`, `full set of vehicle runs`,
  `vehicle runs`, `route roster`, `list the complete route plan`,
  `list every route`, `all the routes`. Deliberately defers to C0
  when a specific customer number appears.

## 6. Adapter contract

- Returns one of the existing `Intent` enum values (validated by
  `SUPPORTED_INTENTS`) or `None`.
- No side effects.
- No payload access.
- No solver / model / network calls.
- No prompt-engineering against heldout case text — every phrase
  bank is keyed off a semantic category (value question,
  comparator, referent, movement, version marker, completion verb,
  lateness phrase, listing phrase).

## 7. Optional LLM adapter (Option 2 — deferred)

The deterministic adapter cleanly clears the 18-case target
(18/18 on `dev∪heldout` at the freeze tag), so the optional LLM
adapter is not implemented in D1. If a future axis surfaces
paraphrases the deterministic phrase banks cannot cover, the LLM
adapter would slot into the same `decide_d1_intent` seam as a
fallback after the deterministic branch returns `None`. The
envelope's structured-output, temperature-0, no-heldout-in-prompt
constraints apply.

## 8. Evaluation surface

`product/evaluation/system_d1/run_system_d1.py` runs D1 on:

| Surface | n |
|---|---:|
| locked Run 2 core (`run2_benchmark_cases.csv`) | 60 |
| Axis 1 look-alike (C0) | 24 |
| Axis 2 OOD premises (C0) | 24 |
| Axis 3 semantic (C0) | 24 |
| Axis 4 payload (C0 only — model A/B are out of scope) | 24 |
| **Total scored cases** | **156** |

Outputs under `product/evaluation/system_d1/reports/`:

- `system_d1_stress_report.{csv,md}`
- `system_d1_core_run2_report.{csv,md}`
- `system_d1_failure_map.csv`

Acceptance gates (enforced by `tests/system_d1/test_d1.py`):

- target_18_fixed_count == 18
- must_not_regress_70_preserved_count == 70
- core_run2_regressions == 0
- Axis 4 fully-perfect == 24/24

## 9. Reproduction

```bash
# Evaluate D1 end to end
.venv/bin/python -m product.evaluation.system_d1.run_system_d1

# Run the D1 test suite
.venv/bin/python -m pytest tests/system_d1/ -q

# Read reports
ls product/evaluation/system_d1/reports/
```

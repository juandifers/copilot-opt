# D2 + D3 Combined Summary

_Authored 2026-05-21. Snapshots from
`system_d2_closeout.md`, `system_d3_closeout.md`, and the C0 /
D1 baselines (frozen at HEAD `18b4811`)._

## 1. Headline trajectory

| System | Intent failures fixed | D2 false-premise/warning fixed | D3 causal schema fixed (v2 overlay) | Core regressions vs C0 | Axis 4 regressions vs C0 |
|---|---:|---:|---:|---:|---:|
| C0 | baseline | baseline | n/a (no v2 scoring) | 0 | 0 |
| D1 | 18 / 18 | 0 / 5 | n/a | 0 | 0 |
| D2 | 18 / 18 | 5 / 5 | n/a | 0 | 0 |
| D3 | 18 / 18 | 5 / 5 | 5 / 5 | 0 | 0 |

- **Intent failures fixed** counts the 18-case D1 target cohort
  (intent classifier failures across Axes 1–3).
- **D2 false-premise/warning fixed** counts A2D-03, A2H-02,
  S1D-08, S1D-09, S1H-10.
- **D3 causal schema fixed** counts A2D-10, A2D-11, A2D-12,
  A2H-11, A2H-12 under the v2 overlay gold.
- **Core regressions vs C0** is measured per-case on the 60-case
  locked Run 2 core; 0 means no case loses any metric value.
- **Axis 4 regressions vs C0** is measured on the 24 axis-4 C0
  payload cases.

## 2. Per-axis behaviour-class trajectory

| axis | n | C0 beh | D1 beh | D2 beh | D3 beh (v1) | D3 beh (v2 overlay, target subset only) |
|---|---:|---:|---:|---:|---:|---:|
| axis1_lookalike | 24 | 1.000 | 1.000 | 1.000 | 1.000 | — |
| axis2_ood_premises | 24 | 0.750 | 0.917 | **1.000** | 0.792 | **1.000** on 5 overlay cases |
| axis3_semantic | 24 | 0.625 | 0.875 | **1.000** | 1.000 | — |
| axis4_payload | 24 | 1.000 | 1.000 | 1.000 | 1.000 | — |
| core_run2 | 60 | 1.000 | 1.000 | 1.000 | 1.000 | — |

D3 (v1) on axis2 dips to 0.792 because the five overlay cases
emit the new v2 warning that v1 gold does not expect; v2-gold
grading on those five cases restores ✓ across the board. This
is the intended cost of a versioned contract extension.

## 3. Must-not-regress 70-cohort

| System | C0-side cases preserved | Axis 4 model-A preserved by construction | Total |
|---|---:|---:|---:|
| C0 | 64 / 64 | 6 / 6 | **70 / 70** |
| D1 | 64 / 64 | 6 / 6 | **70 / 70** |
| D2 | 64 / 64 | 6 / 6 | **70 / 70** |
| D3 | 64 / 64 | 6 / 6 | **70 / 70** |

## 4. Over-firing checks

| System | route_indexing newly over-fired | false_premise newly over-fired | causal_mechanism off-target |
|---|---:|---:|---:|
| D1 | 0 | 0 | n/a |
| D2 | 0 | 0 | n/a |
| D3 | 0 | 0 | 0 |

Pre-existing C0 over-fires inherited unchanged (not attributable
to D2 or D3): 1 case (A2H-06, `route_indexing_ambiguity` fires
because the prompt contains literal `Route 1` — a C0 behavior
unchanged across all three D systems).

## 5. Remaining failures (post-D3)

| Bucket | n | Status |
|---|---:|---|
| D1 intent failures | 0 / 18 | fixed by D1 |
| D2 false-premise / route-alias | 0 / 5 | fixed by D2 |
| D3 causal schema (v2 overlay) | 0 / 5 | fixed by D3 |
| Pre-existing C0 inherited over-fire (A2H-06) | 1 | pre-D1, not in D2/D3 scope |
| Axis-4 A/B `model_projection_failure` | 42 | out of scope for D-series (C0-like only) |

Every case in the System-D-addressable envelope is now passing.

## 6. Acceptance scorecards

### D2 (closeout §11 + acceptance criteria)

- D2 fixes 5/5 D2 targets ✓
- D2 preserves D1 target-18 fixes ✓
- D2 has 0 Run 2 core regressions ✓
- D2 has 0 Axis 4 C0 regressions ✓
- D2 does not over-fire false-premise or route-index warnings ✓
- No locked Run 2 files changed ✓
- Original stress-axis cases.csv files unchanged ✓
- Tests pass ✓ (56 tests)

### D3 (closeout §11 + acceptance criteria)

- D3 uses a versioned overlay, not silent gold rewriting ✓
- D3 adds causal-unsupported schema support ✓
- D3 fixes 5/5 causal schema-gap targets under the overlay ✓
- D3 preserves D2 fixes ✓
- D3 has 0 Run 2 core regressions under the original locked schema ✓
- D3 has 0 Axis 4 C0 regressions ✓
- No locked Run 2 files changed ✓
- Tests pass ✓ (49 tests)

## 7. Frontend integration readiness

| Surface | Status under D3 |
|---|---|
| `ProductCopilotResponse` shape | unchanged (warnings is open-set list[str]; the new strings flow through as-is) |
| Behavior-class enum | unchanged |
| Next-action enum | unchanged (D3 next-action is deferred to schema-v3) |
| Intent enum | unchanged |
| Evidence path schema | unchanged |
| useful_refusal shape | unchanged |

Frontend integration can proceed in parallel with no contract
break. The frontend needs to display the new warning string
`causal_mechanism_unsupported` (e.g. as a chip "I can show the
facts but not the cause"). No type generation has to change.

## 8. Recommended next step

**Schema v3 — causal diagnostics extension.** The remaining
work to close the causal axis fully:

1. Add a `payload.causal_diagnostics` schema field that solvers
   can populate (top-K contributors to objective increase,
   late-customer attribution, route-count change drivers).
2. Add a `expose_causal_diagnostics` next-action code in the
   product schema, paired with the D3 warning so an operator
   sees "facts here; ask for decomposition here."
3. Extend the D3 detector to emit *partial* answers when the
   decomposition is present (warning becomes
   `causal_mechanism_partially_supported`).

After schema v3 lands, the remaining 42 Axis-4 A/B
`model_projection_failure` cases are the natural next axis —
those need model-side (rather than contract-side) intervention
and are outside the System D envelope.

## 9. Reproduction

```bash
# D1
.venv/bin/python -m product.evaluation.system_d1.run_system_d1

# D2 (uses D1 + new D2 wrappers)
.venv/bin/python -m product.evaluation.system_d2.run_system_d2

# D3 (uses D1 + D2 + new D3 wrappers + v2 overlay)
.venv/bin/python -m product.evaluation.system_d3.run_system_d3

# Test suites
.venv/bin/python -m pytest tests/system_d1/ tests/system_d2/ tests/system_d3/ -q
```

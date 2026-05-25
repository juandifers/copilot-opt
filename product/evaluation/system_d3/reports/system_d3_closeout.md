# System D3 — Closeout

_Authored 2026-05-21 on top of `system_d2_closeout.md`._

## 1. Purpose

D3 ships a schema-v2 causal-unsupported extension that fixes the
five Axis-2 Band-4 causal-explanation `schema_gap` cases under a
versioned overlay gold. D3 also preserves every D1, D2, and core
Run 2 baseline.

D3 targets:

| case_id | family | gold question | v2 contract change |
|---|---|---|---|
| A2D-10 | SCHEDULE | Why is route 1 running late in this updated schedule? | keep facts + route_indexing_ambiguity; add causal_mechanism_unsupported |
| A2D-11 | OBJ | What's pushing the objective higher in this plan? | keep facts; add causal_mechanism_unsupported |
| A2D-12 | SCHEDULE | What caused customer 42 to miss its delivery window? | keep facts; add causal_mechanism_unsupported |
| A2H-11 | STRUCT | What's pushing the route count up in this revision? | keep facts; add causal_mechanism_unsupported |
| A2H-12 | SCHEDULE | Why did the lateness counts jump up after the time windows tightened? | keep facts; add causal_mechanism_unsupported |

## 2. Why D3 is contract/schema-v2

The locked Run 2 schema v1 has no warning code for "I can answer
the factual part of this question, but not the causal part." The
original gold for these five cases was downgraded to "cite the
facts, say nothing about the cause", and they were bucketed as
`schema_gap_or_unrepresentable_gold` in `axis2_closeout.md` §5.
That downgrade made the cases scorable, but it also masked the
real gap: the contract had no honest answer for the operator's
causal framing.

D3 fixes that by:

- adding a single new warning string,
  `causal_mechanism_unsupported`, and the detector that fires it;
- shipping a versioned overlay gold
  (`axis2_causal_gold_overlay.csv`) keyed by case_id with the v2
  expected columns;
- adding a D3 scorer adapter that uses overlay gold for the five
  cases and inherits original gold for everything else.

The original Axis 2 `cases.csv` is byte-identical under D3.
Every D2 / D1 / C0 report remains reproducible from the existing
runners.

## 3. Schema additions

| Element | Pre-D3 | D3 (v2) |
|---|---|---|
| Warning string | `causal_mechanism_unsupported` not emitted | recognised warning code, emitted by `d3_refusal_policy.build_warnings_d3` |
| Pydantic enum | `warnings: list[str]` (open-set) | unchanged — no contract.py edit needed |
| Next-action enum | n/a | `expose_causal_diagnostics` defined as future work; not required by overlay gold |
| Behavior class enum | 4 values | unchanged. Adding the warning to an answerable case re-projects `direct_answer` → `direct_answer_with_warning`, which is a v1 transition |

Because `warnings` is already `list[str]`, **no Pydantic schema
change is required**. D3 does not modify
`product/copilot/contracts.py` or `product/data/product_schema.py`.

## 4. Overlay gold protocol

The overlay file lives at
`product/evaluation/system_d3/axis2_causal_gold_overlay.csv` and
contains five rows. The D3 scorer adapter (`d3_overlay.py`):

- loads the overlay into `{case_id: row}`,
- for any case_id in the overlay set, builds a `Run2Case` whose
  v2 grading columns are taken from the overlay and whose
  diagnostic columns (rationale, difficulty, …) carry forward
  from the original case (with `v2_rationale` appended for
  traceability),
- grades D3's predicted contract against the v2 case using the
  unchanged `run2_scoring.score_case`.

For any case_id outside the overlay, the original gold is used
unchanged. This is enforced row-by-row in `run_system_d3._score_one_surface`.

## 5. Target-5 causal cases — results

| case_id | D2 (v1 gold) | D3 (v1 gold) | D3 (v2 overlay gold) | D3 emitted warnings |
|---|:-:|:-:|:-:|---|
| A2D-10 | ✗ | ✗ | ✓ | route_indexing_ambiguity;causal_mechanism_unsupported |
| A2D-11 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |
| A2D-12 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |
| A2H-11 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |
| A2H-12 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |

D3 v2 target-5 fixed count: **5 / 5** (100%).

D3 (v1 gold) intentionally drops to ✗ for these five cases
because the v1 gold does not contain `causal_mechanism_unsupported`,
so D3's emission is a v1 warning-precision deficit. That is the
documented v2 cost — it is the entire reason D3 ships a versioned
overlay rather than silently rewriting v1 gold.

A2D-10 was D2-✗ under v1 because v1 expected only
`route_indexing_ambiguity` — the case was a downgraded gold even
under v1. D3 catches both the route warning (inherited from D2)
and the causal warning (D3 addition).

## 6. Behavior-class policy

`schema_v2_notes.md` §3 defines:

- If pre-D3 status is `answerable` with no other warnings, D3
  projects to `direct_answer_with_warning` (existing v1 enum
  value, just with the new warning string).
- If pre-D3 status is `answerable` with an existing warning,
  D3 keeps `direct_answer_with_warning` and appends the causal
  warning.
- If pre-D3 status is `partially_answerable`, D3 keeps
  `partial_answer_with_warning`.
- If pre-D3 status is `not_answerable` (refusal), D3 does
  **not** emit the causal warning. The refusal already explains
  the dominant problem (missing entity, missing schema).

All five target cases were `answerable` pre-D3, so the chosen
projection is `direct_answer_with_warning` across the board.

## 7. Results vs D2

| surface | n | C0 int | D1 int | D2 int | D3 int (v1) | C0 beh | D1 beh | D2 beh | D3 beh (v1) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| core_run2 | 60 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| axis1_lookalike | 24 | 0.875 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| axis2_ood_premises | 24 | 0.750 | 1.000 | 1.000 | 1.000 | 0.750 | 0.917 | 1.000 | 0.792 |
| axis3_semantic | 24 | 0.625 | 1.000 | 1.000 | 1.000 | 0.625 | 0.875 | 1.000 | 1.000 |
| axis4_payload | 24 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

The Axis 2 behavior_class drop under D3 (v1) (1.000 → 0.792) is
exactly the five overlay cases: D3 emits `causal_mechanism_unsupported`,
which v1 gold doesn't expect, so v1 projects them as
`direct_answer_with_warning` while v1 gold says `direct_answer`
(or `direct_answer_with_warning` for A2D-10 with only
`route_indexing_ambiguity`). Under v2 grading those five cases
flip from ✗ to ✓.

D2 target-5 preserved under D3: **5 / 5**.
D1 target-18 preserved under D3: **18 / 18**.
must-not-regress 70-cohort preserved under D3: **70 / 70**.

## 8. Run 2 core compatibility

- D3 emits zero warnings on Run 2 core that C0 did not also
  emit. The causal detector requires a "why / what caused"
  phrase, none of which appear in the locked Run 2 core prompts.
- core_run2_regressions vs C0 under D3: **0**.

| metric | C0 | D1 | D2 | D3 |
|---|---:|---:|---:|---:|
| intent_accuracy | 1.000 | 1.000 | 1.000 | 1.000 |
| behavior_class_accuracy | 1.000 | 1.000 | 1.000 | 1.000 |
| warning_precision | 1.000 | 1.000 | 1.000 | 1.000 |
| warning_recall | 1.000 | 1.000 | 1.000 | 1.000 |

## 9. Axis 4 compatibility

- axis4_d3_perfect: **24 / 24**.
- axis4_regressions: **0**.

The causal phrase bank does not match any Axis 4 prompt; no D3
addition fires on Axis 4 cases.

## 10. Off-target causal emissions

- off_target_causal_emission_count: **0**.

D3 emits `causal_mechanism_unsupported` only on the five overlay
cases (where the v2 gold expects it). No case outside the overlay
saw a D3-introduced causal warning, including Run 2 core, Axis 1
look-alike, Axis 3 semantic, and Axis 4 payload.

## 11. Remaining limitations

After D3, the remaining failures are:

- 42 Axis-4 A/B `model_projection_failure` cases — out of D3's
  scope (D3 is C0-like; no model is run).
- The new `expose_causal_diagnostics` next-action code is
  defined but not required by overlay gold (deferred to a
  schema-v3 step that would also add a `payload.causal_diagnostics`
  schema field).
- The overlay-grading path is bespoke to D3. If future work
  introduces more v2 cases, a more general "scoring-time overlay
  registry" would consolidate the pattern.

## 12. Future work

- Add a `payload.causal_diagnostics` schema field and the
  corresponding next-action code so the copilot can route an
  operator to a real causal-decomposition surface instead of
  just refusing causally.
- Extend the causal phrase bank to cover cost-attribution
  prompts ("which leg of the route dominated the cost?"), with
  a payload-aware detector that fires partial answers when
  the decomposition is available.
- Promote the warning to a frontend chip with an explanation
  ("This system can show *what* but not *why* — here are the
  facts; ask the solver team for a causal trace.").

## 13. Reproduction

```bash
# Evaluate D3 end to end (C0, D1, D2, D3 + v2 overlay)
.venv/bin/python -m product.evaluation.system_d3.run_system_d3

# Run the D3 test suite
.venv/bin/python -m pytest tests/system_d3/ -q

# Read reports
ls product/evaluation/system_d3/reports/
```

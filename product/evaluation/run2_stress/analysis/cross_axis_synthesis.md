# R2-S Cross-Axis Synthesis — C0 (+ A/B for Axis 4)

_Status: **SYNTHESIS for Axes 1–4 C0 baselines** (Axis 4 also covers
A and B). Frozen at HEAD
`18b4811a1f85c166ea3ba8c777dfc021b2a5f747`
(tag `run2-contract-extended`). Authored 2026-05-21 from the four
per-axis scatter files under the shared methodology in
`product/evaluation/run2_stress/shared/`._

## 1. Purpose

Each of the four R2-S axes probes a different failure mode of the
VRPTW copilot:

- **Axis 1 — Look-alike Intent Stress.** Misleading familiar wording
  with attractor tokens → wrong-adjacent-intent misroutes by the C0
  keyword classifier.
- **Axis 2 — OOD False Premises & Comparators.** Unsupported user
  premises (nonexistent entities, missing comparators, causal
  questions) → refusal-shape correctness on the contract layer.
- **Axis 3 — Semantic Intent / Paraphrase Stress.** Unseen wording of
  supported intents → `unknown`-intent fallback by the keyword
  classifier.
- **Axis 4 — Payload Scale Stress.** Long Homberger-200 SCHEDULE
  payloads under model-facing projection → A / B contract-shape
  brittleness; C0 robust by construction.

This synthesis combines the four per-axis scatter files into a
unified per-(case, axis, system) failure map and reports where the
4 × 24 = 96 distinct cases (plus the Axis 4 A and B replicates)
land along **one unified failure-mode taxonomy**. The goal is to
let one read tell us what System D should target, what is
out-of-envelope, what is a schema gap, what is a model-projection
artifact, and what must not regress.

## 2. Method

Inputs (each validated against `shared/scatter_schema.md` with
zero errors before concatenation):

- `axis1_lookalike/reports/scatter.csv` — 240 rows (24 × 10 metrics)
- `axis2_ood_premises/reports/scatter.csv` — 240 rows
- `axis3_semantic/reports/scatter.csv` — 240 rows
- `axis4_payload/reports/scatter.csv` — 720 rows (24 × 3 systems × 10
  metrics)

Combined: **`analysis/unified_scatter.csv` (1,440 rows)**.

Per-(case, axis, system) bucket assignment uses each axis's
already-emitted per-case label where available:

- Axis 1 / Axis 2: the `bucket` column on `reports/c0_baseline.csv`.
- Axis 3: derived from `intent_correct` + `predicted_intent` +
  downstream-metric perfection (Axis 3 does not carry a bucket
  column).
- Axis 4: C0 always perfect → guard_protected; A/B per-case is
  derived from the closeout's §6 sub-shape rules (truncation false-
  premise on R2-101/102/113/114/115 for B; silent prior override on
  R2-108 for A; otherwise warning_over_firing if `warning_precision
  < 1.0`, else evidence_over_citation if `evidence_precision < 1.0`,
  else model_perfect).

The per-axis bucket labels are then mapped onto **one unified
taxonomy**:

| Unified category | What it means | Axis sources |
|---|---|---|
| `system_d_addressable_intent` | Front-door intent classifier misroutes (`wrong_intent`, `wrong_adjacent_intent`, `unknown_intent`). A better intent adapter routes correctly; downstream contract logic already produces the correct refusal/partial. | Axis 1, Axis 2, Axis 3 |
| `out_of_envelope_answerability` | False premise on a non-entity-bound intent. Fixing requires modifying `product/data/answerability.py` or `product/copilot/refusal_policy.py`, outside the current System D envelope. | Axis 2 |
| `schema_gap` | The most faithful gold cannot be expressed under the current Run 2 schema. C0 produced the closest supported behavior perfectly. Fix is a Stage R2-2 schema extension. | Axis 2 |
| `model_projection_failure` | A or B failed because of the prompt-template projection, evidence over-citation, or warning over-firing. C0 is robust on the same case because it has full payload access. | Axis 4 (A, B) |
| `must_not_regress_guard_protected` | Every metric perfect. Either C0 (or the model) handled the case correctly, **or** the contract's existing guards (customer-number, listing-phrase, family-routing, false-premise extension, OBJ delta extension, deterministic prior) held under stress. | All axes |
| `downstream_evidence_artifact` | Intent + answerability correct, but a documented evidence/warning artifact pulls some downstream metric < 1.0. Examples: Axis 1 `R2-028`-family infeasibility_kind off-by-one; Axis 3 paraphrase cases where C0 cites an extra field. **Not** a system failure mode the synthesis acts on. | Axis 1, Axis 3 |

Artefacts emitted by `_build_synthesis.py`:

- `analysis/unified_scatter.csv` (1,440 rows; refreshed from per-axis
  scatters).
- `analysis/failure_map.csv` (144 per-(case, axis, system) rows with
  unified `category` and axis-specific `sub_label`).
- `analysis/failure_summary.csv` (per-(axis, system, category) counts
  in long form).
- `analysis/cross_axis_synthesis.md` — this file.

## 3. Headline numbers

### 3.1 Total cases per unified category

Across all 4 axes × {C0; plus A and B for Axis 4} = 144 per-(case,
axis, system) rows:

| Category | n | % of 144 |
|---|---:|---:|
| `must_not_regress_guard_protected` | **70** | 48.6% |
| `model_projection_failure`         | **42** | 29.2% |
| `system_d_addressable_intent`      | **18** | 12.5% |
| `downstream_evidence_artifact`     | 7  | 4.9% |
| `schema_gap`                       | 5  | 3.5% |
| `out_of_envelope_answerability`    | 2  | 1.4% |

### 3.2 C0 only — the contract layer alone (axes 1–4, n = 96)

The clean read on what System D could (and could not) move:

| Category | C0 cases | What it tells us |
|---|---:|---|
| `must_not_regress_guard_protected` | **46** (47.9%) | The contract is robust on nearly half of the stress surface, including 24/24 Axis 4 cases where C0 has full payload access. |
| `system_d_addressable_intent`      | **18** (18.8%) | Every case here is an intent-classifier misroute. The downstream contract layer would have produced the right shape if the intent were correct. |
| `downstream_evidence_artifact`     | 7  (7.3%) | Intent correct; documented evidence/warning artifact (Axis 1 R2-028-family infeasibility_kind off-by-one; Axis 3 paraphrase ev-extra). |
| `schema_gap`                       | 5  (5.2%) | All Band-4 causal-explanation cases. Fix is schema-side, not System D. |
| `out_of_envelope_answerability`    | 2  (2.1%) | Both A2D-03 / A2H-02 — false premise on `lateness_summary` / `feasibility_status`. Requires answerability-policy change. |
| `model_projection_failure`         | 0  | C0 never enters this category by design. |

Total C0: 46 + 18 + 7 + 5 + 2 = 78 + 18 + 0 = 96 ✓

### 3.3 Per-axis × per-system × per-category (failure_summary.csv)

| Axis | System | Category | n |
|---|---|---|---:|
| `axis1_lookalike` | c0 | `must_not_regress_guard_protected` | 18 |
| `axis1_lookalike` | c0 | `system_d_addressable_intent` | 3 |
| `axis1_lookalike` | c0 | `downstream_evidence_artifact` | 3 |
| `axis2_ood_premises` | c0 | `must_not_regress_guard_protected` | 11 |
| `axis2_ood_premises` | c0 | `system_d_addressable_intent` | 6 |
| `axis2_ood_premises` | c0 | `schema_gap` | 5 |
| `axis2_ood_premises` | c0 | `out_of_envelope_answerability` | 2 |
| `axis3_semantic` | c0 | `must_not_regress_guard_protected` | 11 |
| `axis3_semantic` | c0 | `system_d_addressable_intent` | 9 |
| `axis3_semantic` | c0 | `downstream_evidence_artifact` | 4 |
| `axis4_payload` | c0 | `must_not_regress_guard_protected` | 24 |
| `axis4_payload` | a  | `must_not_regress_guard_protected` | 6 |
| `axis4_payload` | a  | `model_projection_failure` | 18 |
| `axis4_payload` | b  | `model_projection_failure` | 24 |

## 4. System-D-addressable intent failures (n = 18)

Every case here would have produced the right contract response if
the intent classifier had routed it correctly. The fix lives in
`product/copilot/intent.py` (or a semantic intent adapter) — inside
the current System D envelope per
`shared/system_d_design_envelope.md`.

| case_id | axis | band / subtype | gold intent | sub_label |
|---|---|---|---|---|
| A1D-11 | axis1_lookalike | `comparison_vs_status_or_objective` | `objective_value` | wrong_adjacent_intent (OBJ value→delta via `actually change`) |
| A1D-12 | axis1_lookalike | `comparison_vs_status_or_objective` | `objective_value` | wrong_adjacent_intent (`compared`) |
| A1H-11 | axis1_lookalike | `comparison_vs_status_or_objective` | `objective_value` | wrong_adjacent_intent (`still`) |
| A2D-06 | axis2_ood_premises | `unsupported_movement` | `before_after_comparison` | wrong_intent (non-comparative movement wording) |
| A2H-05 | axis2_ood_premises | `unsupported_movement` | `before_after_comparison` | wrong_intent (`swap` wording) |
| A2H-06 | axis2_ood_premises | `unsupported_movement` | `before_after_comparison` | unknown_intent (reassignment listing) |
| A2D-08 | axis2_ood_premises | `missing_comparator` | `objective_delta` | wrong_intent (`better than optimum`) |
| A2H-08 | axis2_ood_premises | `missing_comparator` | `objective_delta` | wrong_intent (`rank against stronger solver`) |
| A2H-09 | axis2_ood_premises | `missing_comparator` | `before_after_comparison` | unknown_intent (`shift versus prior`) |
| S1D-07 | axis3_semantic | `entity_synonym` | `full_route_listing` | unknown_intent |
| S1D-08 | axis3_semantic | `schedule_synonym` | `route_end_time` | unknown_intent |
| S1D-09 | axis3_semantic | `schedule_synonym` | `route_end_time` | unknown_intent |
| S1D-12 | axis3_semantic | `operator_colloquial` | `lateness_summary` | unknown_intent |
| S1H-07 | axis3_semantic | `paraphrase` | `full_route_listing` | unknown_intent |
| S1H-08 | axis3_semantic | `paraphrase` | `full_route_listing` | unknown_intent |
| S1H-09 | axis3_semantic | `schedule_synonym` | `route_end_time` | unknown_intent |
| S1H-10 | axis3_semantic | `schedule_synonym` | `route_end_time` | unknown_intent |
| S1H-12 | axis3_semantic | `schedule_synonym` | `lateness_summary` | unknown_intent |

Common patterns:

- **OBJ value→delta confusion** (3 cases) — comparative attractor
  tokens (`actually change`, `compared`, `still`) reroute a value
  question to delta.
- **OBJ value→delta or value→value on implicit comparator** (2 of
  the Axis 2 missing_comparator cases) — `better than … optimum`,
  `rank against … stronger solver` carry no comparative token, so
  intent stays `objective_value` even though the question is a
  comparator.
- **STRUCT before_after_comparison miss** (4 cases) — non-
  comparative movement / reassignment wording falls to
  `single_customer_route_membership` or `unknown`.
- **SCHEDULE paraphrase → unknown** (6 of the 9 Axis 3 unknown
  cases) — `schedule_synonym` and `paraphrase` bands hit the
  schedule tokens that the SCHEDULE branch in `intent.py` doesn't
  yet cover (e.g. `roster`, `finish window`, idiomatic
  `wraps up`/`closes out`).
- **Full route listing paraphrase → unknown** (3 cases) — paraphrase
  band wording for the proposed `full_route_listing` intent.

**System D leverage on Axis 1–3**: a single semantic intent adapter
that handles (a) implicit comparator wording for OBJ delta, (b)
movement/reassignment wording for STRUCT `before_after_comparison`,
and (c) the SCHEDULE / STRUCT paraphrase tail would convert all 18
of these into `must_not_regress_guard_protected`.

## 5. Out-of-envelope answerability failures (n = 2)

Both cases live in Axis 2 Band 1. The contract's false-premise
check is gated to `_CUSTOMER_BOUND_INTENTS` and `_ROUTE_BOUND_INTENTS`
in `product/data/answerability.py` and `product/copilot/refusal_policy.py`;
intents outside those sets never get the check.

| case_id | gold intent | sub_label | fix locus |
|---|---|---|---|
| A2D-03 | `lateness_summary` | missed_false_premise | `product/data/answerability.py` / `product/copilot/refusal_policy.py` |
| A2H-02 | `feasibility_status` | missed_false_premise | same |

These are **outside the current System D envelope.** Addressing
them requires modifying answerability or refusal-policy code,
which is forbidden under each axis's hard constraints and outside
the envelope per `shared/system_d_design_envelope.md`. The owner
can choose to broaden the envelope; this synthesis does not.

## 6. Schema-gap cases (n = 5)

All five are Axis 2 Band 4 causal-explanation cases. The schema
has no `causal_mechanism_unsupported` warning, so the most faithful
gold was downgraded to the closest supported behavior. C0 scored
**100% on every metric** against the downgraded gold; the bucket is
a methodological notice, not a system failure.

| case_id | gold intent | sub_label |
|---|---|---|
| A2D-10 | `lateness_summary` | schema_gap (cite facts; route_indexing_ambiguity warning) |
| A2D-11 | `objective_value` | schema_gap (cite action_objective; no warning) |
| A2D-12 | `lateness_summary` | schema_gap (cite n_late + late_ids) |
| A2H-11 | `route_count` | schema_gap (cite n_routes) |
| A2H-12 | `lateness_summary` | schema_gap |

Fix is **Stage R2-2 future work**: add a
`causal_mechanism_unsupported` warning code, and possibly an
`unserved_customer_listing` / `reassignment_listing` intent (this
last would also collapse two of the Axis 2 system_d_addressable
unknown_intent cases). Out of scope for the current closeout cycle.

## 7. Model-projection failures (n = 42; all Axis 4 A or B)

Per Axis 4 closeout §6. Distribution by sub-shape:

| sub_label | A | B |
|---|---:|---:|
| `axis4_evidence_over_citation` | 17 | 9 |
| `axis4_warning_over_firing`    | 0  | 10 |
| `axis4_b_truncation_false_premise` | 0 | 5 |
| `axis4_a_silent_prior_override` | 1 | 0 |
| **total** | **18** | **24** |

Frame:

- **None of these are C0 failures.** C0 scored 100% on every Axis 4
  case with the same payload set.
- **A preserves intent and answerability** through the deterministic
  prior (24/24 intent_correct; 24/24 ans_correct; 23/24 bc_correct)
  but the model-side evidence selector volunteers extra identifier
  fields (`customer_schedule[].customer_id`, `route_end_times[].route_idx`,
  `customer_schedule[].is_late`, …) → 17/24 evidence_over_citation
  hits.
- **B degrades sharply** — 14/24 answerability misses; 15/24
  behavior-class misses. 5/24 cases are pure truncation false
  premise (customer ID lies in the truncated tail of the 60-row
  schedule projection); 10/24 fire warnings from intuition rather
  than contract-pinned rules.
- All four sub-shapes are **outside the current System D envelope**
  unless the owner explicitly broadens it. Fixes are
  projection-layer (truncation), evidence post-validation, and
  warning post-validation work — see Axis 4 closeout §7.

## 8. Downstream evidence artifacts (n = 7)

Intent + answerability + behavior class all correct, but a
documented evidence or warning artifact pulls some downstream
metric below 1.0. These are **not** system failures the synthesis
acts on; they are scoring-side artifacts already documented in the
per-axis closeouts.

| case_id | axis | known artifact |
|---|---|---|
| A1D-10 | axis1_lookalike | infeasibility_kind off-by-one (R2-028-family) |
| A1H-10 | axis1_lookalike | infeasibility_kind off-by-one |
| A1H-12 | axis1_lookalike | infeasibility_kind off-by-one |
| S1D-02 | axis3_semantic | documented C0 ev-extra on paraphrase |
| S1D-03 | axis3_semantic | documented C0 ev-extra |
| S1H-03 | axis3_semantic | documented C0 ev-extra |
| S1H-04 | axis3_semantic | documented C0 ev-extra |

## 9. Must-not-regress guard-protected cases (n = 70)

This is the cohort System D **must not regress**. Built up
across the four axes:

| Axis / system | guard_protected count | What's preserving them |
|---|---:|---|
| axis1_lookalike — C0 | 18 | Customer-number guard; listing-phrase precedence; family-routing dominance |
| axis2_ood_premises — C0 | 11 | R2-3 false-premise extension; comparison_referent_ambiguity; unsupported_comparison; missing_validity_fields refusal |
| axis3_semantic — C0 | 11 | Intent classifier correctly routed; downstream contract perfect |
| axis4_payload — C0 | 24 | Full structured payload access; deterministic contract logic |
| axis4_payload — A | 6 | Deterministic prior copied through cleanly; model evidence happened to match gold |
| axis4_payload — B | 0 | (B never produced a fully-perfect Axis 4 case — every B case has at least one model-projection issue) |
| **total** | **70** | |

A regression test on System D must hold this 70-case cohort at
≥ 70 / 70 perfect.

## 10. System D scope determination

Putting the four buckets together:

- **In scope for the current System D envelope** (semantic intent
  adapter at `product/copilot/intent.py`):
  - 18 `system_d_addressable_intent` cases.
  - If System D nails the three patterns identified in §4, those 18
    cases move into `must_not_regress_guard_protected`, raising the
    C0-only guard-protected fraction from 46/96 → 64/96 (47.9% →
    66.7%).

- **Out of scope unless the envelope is broadened**:
  - 2 `out_of_envelope_answerability` cases (Axis 2 missed false
    premise on non-entity-bound intents). Fix is in
    `product/data/answerability.py` / `product/copilot/refusal_policy.py`.
  - 42 `model_projection_failure` cases (Axis 4 A and B). Fix is
    projection layer, evidence post-validation, warning post-validation,
    or prior-lock enforcement.

- **Stage R2-2 schema future work** (un-fixable under R2-1):
  - 5 `schema_gap` cases (Axis 2 Band 4 causal). Fix is a new
    warning code or sub-intent.

- **Already-acceptable** (not in scope to "fix"):
  - 70 `must_not_regress_guard_protected` cases — the floor System D
    must not erode.
  - 7 `downstream_evidence_artifact` cases — known scoring artifacts.

**Net answer to "what should System D target?"**

If System D stays scoped to intent classification, the **18
intent-mediated cases in §4** are its full target. They split
cleanly into three sub-patterns:

1. OBJ comparative-token detection (5 cases): 3 Axis 1 OBJ value→delta
   misroutes + 2 Axis 2 implicit-comparator wrong-intents on the
   OBJ side.
2. STRUCT before/after detection on non-comparative wording (4
   cases): 2 Axis 2 movement wrong_intents + 2 Axis 2 reassignment-
   listing unknown_intents.
3. SCHEDULE / STRUCT paraphrase tail (9 cases): all 9 Axis 3
   unknown_intent failures.

Each of the three sub-patterns is independently addressable; a
System D rollout could ship them in any order.

## 11. Recommended next step

Three options, in order of incremental cost:

### Option A — Ship System D scoped to intent classification (recommended)

Build a semantic intent adapter that handles the 18 cases in §4.
The adapter is a single model call (or rule set) layered on top of
`product/copilot/intent.py`; it does not touch the answerability,
evidence, or warning policy layers.

- Cost: one model call per question; one new module.
- Coverage: 18/96 → must_not_regress (47.9% → 66.7% C0-only).
- Risk: must not regress the 70-case guard-protected cohort.

### Option B — Stage R2-2 schema + answerability extension

In a separate workstream, extend the schema to fix the 5 schema_gap
cases and widen the false-premise check to non-entity-bound intents
(fixes the 2 out_of_envelope_answerability cases). This is a 7-case
delta on top of Option A and **not** a System D change.

### Option C — Model-projection follow-up

Address the 42 Axis 4 A/B failures via projection redesign,
ID-aware retrieval, evidence post-validation, warning
post-validation, and prior-lock enforcement. This is a separate
"large-context model copilot" workstream and the most ambitious
of the three.

**Recommendation**: **Option A first.** It's the smallest, cleanest
delivery, has the highest in-envelope coverage gain per unit of
code, and the synthesis above shows its target cases are clean,
well-classified, and isolated to the intent layer.

## 12. Reproduction

```
# 1. Refresh per-axis scatters (already current at HEAD 18b4811;
#    these commands are idempotent):
python -m product.evaluation.run2_stress.axis1_lookalike.runner
python -m product.evaluation.run2_stress.axis2_ood_premises.runner
python -m product.evaluation.run2_stress.axis3_semantic.runner
python -m product.evaluation.run2_stress.axis4_payload._build_scatter

# 2. Refresh the unified scatter + failure map:
python -m product.evaluation.run2_stress.analysis._build_synthesis

# 3. Inspect:
column -s, -t product/evaluation/run2_stress/analysis/failure_summary.csv | head -20
```

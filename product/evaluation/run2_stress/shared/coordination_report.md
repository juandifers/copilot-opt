# R2-S coordination report

_Audit of the four R2-S stress axes against the shared methodology
in `scatter_schema.md`, `metric_names.md`, `axis_naming.md`, and
`system_d_design_envelope.md`. Authored 2026-05-20 at HEAD `18b4811`
("Run 2 contract extensions completed"). Status is a snapshot — each
axis-internal section links to the file paths the audit reads._

## 0. Methodological decision — Axis 3 (Path B adopted)

The initial audit (§3.1 below) surfaced a naming conflict: the
first revision of `axis_naming.md` defined axis 3 as
"compositional / decomposition-requiring prompts" and applied the
rule "all surface-token swaps belong in axis 1." Under that
definition, the 24 cases already in `axis3_semantic/cases.csv`
were paraphrase / surface-token swaps and would have been
re-labelled as axis 1.

**Decision (2026-05-20, owner).** Adopt **Path B**:

- Keep `axis3_semantic/` as **semantic-equivalence / paraphrase
  stress**. The 24 existing cases remain at the same `case_id`s
  and the C0 baseline of record stays valid.
- Update `axis_naming.md` §1 so axis 3 reads as paraphrase stress
  (governing definition).
- Soften the boundary rule: cases fitting both axis 1 and axis 3
  belong in axis 1 **only when** the surface form is *constructed*
  to trigger a specific adjacent wrong intent. Ordinary
  semantic-equivalence paraphrases belong in axis 3.
- Reserve axis 1 for *constructed* look-alike intent confusion
  (e.g. "Where is customer 42 going next?" engineered to fire the
  `_NEW_ORDER_TOKENS` heuristic toward `new_customer_assignment`).
- **No case migration.** No file under `axis3_semantic/` is moved,
  renamed, or relabelled.

The §3.1 audit below is preserved as the record of the boundary
discussion. Treat it as the *history* of the decision, not the
current standard. The current standard is §1 of `axis_naming.md`
as amended at this decision.

**Axis 3 status as of this decision**: closed for C0 baseline. See
`axis3_semantic/reports/axis3_closeout.md`.

## 1. Axis status table

| Axis | `design.md` | `cases.csv` | `c0_baseline.md` | `c0_baseline.csv` | `dev` / `heldout` split | Band / stratification | Shared `scatter.csv` | Metric names conform | Protected files changed |
|---|---|---|---|---|---|---|---|---|---|
| `axis1_lookalike` | ✗ | ✗ | ✗ | ✗ | n/a | n/a | ✗ | n/a | no |
| `axis2_ood_premises` | ✗ | ✗ | ✗ | ✗ | n/a | n/a | ✗ | n/a | no |
| `axis3_semantic` | ✓ | ✓ (24 rows) | ✓ | ✓ | ✓ 12/12 | `stress_subtype` (6 values; on cases.csv) | ✓ — `reports/scatter.csv` emitted (Path B closeout) | ✓ canonical names in scatter.csv (8 emitted + 2 nulled) | no |
| `axis4_payload` | ✓ | ✓ (24 rows) | ✓ | ✓ | ✓ 14/10 | `band` (low/high, on baseline outputs) | ✗ (not yet emitted) | partial — see §2 | no |

Protected-file check at this audit run: zero locked Run 2 files
modified (`validators.validate_no_protected_files_modified()`
returned an empty list against HEAD).

## 2. Metric-name conformance

The shared vocabulary is the 10 snake_case names in
`metric_names.md`. Existing axis outputs use a wider per-case CSV
shape; the relevant fields are listed below.

**`axis3_semantic/reports/c0_baseline.csv`** uses the following
metric-bearing columns:

- `intent_correct` ✓
- `answerability_correct` ✓
- `behavior_class_correct` ✓
- `evidence_precision` ✓
- `evidence_recall` ✓
- `warning_precision` ✓
- `warning_recall` ✓
- `missing_field_recall` ✓
- `useful_refusal_correct` — **not emitted** (axis 3 has no
  `useful_refusal` gold cases; the column is omitted rather than
  emitted as null)
- `partial_answer_correct` — **not emitted** (axis 3 has no
  `partial_answer_with_warning` gold cases)

Conformance: **8 of 8 emitted metrics match the canonical names**.
The two unemitted metrics are not violations — they're
case-inapplicable for this axis — but the shared scatter file
should still emit `null` rows for them so cross-axis concat is
uniform.

**`axis4_payload/reports/c0_baseline.csv`** uses:

- `intent_correct` ✓
- `answerability_correct` ✓
- `behavior_class_correct` ✓
- `evidence_precision` ✓
- `evidence_recall` ✓
- `warning_precision` ✓
- `warning_recall` ✓
- `missing_field_recall` ✓
- `useful_refusal_correct` ✓ (emitted as empty for the 24 cases
  that have no useful_refusal gold — the convention is per-axis
  but compatible with the shared null convention)
- `partial_answer_correct` — **not emitted**

The `axis4_payload/reports/c0_baseline.md` Markdown table uses
display-friendly aliases (`intent`, `ans`, `beh`, `ev_prec`,
`ev_rec`, `warn_prec`, `warn_rec`, `miss_rec`). This is allowed
in Markdown but **must not propagate to the shared scatter CSV** —
the scatter file is the machine-readable surface, and it must use
the canonical names.

## 3. Boundary audit — axis-naming conflicts

The most important finding of this audit.

### 3.1 Axis 1 vs Axis 3 — the paraphrase question

**Resolved by Path B (see §0).** This subsection is preserved as
the record of the boundary discussion; the resolution is in §0
and in `axis_naming.md` §1 / §3.

`axis3_semantic/` was authored in the R2-S1 stage with a
**paraphrase-friendly** definition of axis 3: "stress whether the
copilot maps semantically equivalent but lexically held-out
operator language to the correct canonical intent." Each of the
24 cases is a paraphrase of a Run 2 base case; the gold contract
response is inherited verbatim.

A subsequent revision of `axis_naming.md` introduced a stricter
definition: cases must not be surface-token swaps of Run 2
prompts. Under the strict-revision boundary rule "if a case fits
both axis 1 and axis 3, it belongs in axis 1", the existing axis 3
cases were mostly axis 1 cases under that revision.

**Subtype-by-subtype assessment of the 24 existing axis 3 cases**:

| Subtype | n | Look-alike under strict definition? | Notes |
|---|---:|---|---|
| `cost_synonym` | 3 | Borderline → axis 1 | "What score did the solver give this plan?" replaces the OBJ vocabulary but the matcher routes purely by `family=OBJ`. The case is more about surface-token paraphrase than semantic decomposition. |
| `feasibility_synonym` | 4 | Borderline → axis 1 | Same as above for PLAN_VALIDITY family. |
| `entity_synonym` | 5 | Look-alike → axis 1 | `vehicle`/`truck`/`run` swaps for `route` are surface-token swaps. |
| `schedule_synonym` | 8 | Look-alike → axis 1 | The 4 route_end_time stresses (`close out`, `finished`, `done for the day`, `complete its run`) are direct surface-token swaps that bypass the matcher's token set. |
| `operator_colloquial` | 2 | Look-alike → axis 1 | "Where did customer N get placed?" is a surface paraphrase. |
| `paraphrase` | 2 | Look-alike → axis 1 | "Show me every route" / "List the complete route plan" are lexical paraphrases. |

By the strict definition, **all 24 existing axis 3 cases are
better characterised as axis 1 (look-alike) cases.** None of them
require semantic decomposition; each maps cleanly to exactly one
existing canonical intent.

**Two paths considered.**

- **Path A — re-label.** Move the existing 24 cases into
  `axis1_lookalike/` (or a sub-axis `axis1_lookalike/paraphrase/`),
  leaving `axis3_semantic/` to be authored from scratch for the
  stricter definition. The C0 baseline numbers stay valid; only
  the axis label changes.
- **Path B — keep the paraphrase-friendly axis 3 definition.**
  Amend `axis_naming.md` to adopt "axis 3 = paraphrase /
  semantic-equivalence stress" as the governing definition. Author
  any future compositional / decomposition-stress cases under a
  new directory when the need arises; do **not** migrate the
  existing 24 cases.

**Path B adopted (see §0).** `axis_naming.md` §1 now reads axis 3
as semantic-equivalence / paraphrase stress; the boundary rule is
softened so ordinary paraphrases stay in axis 3 and only
*constructed* lookalikes belong in axis 1. The R2-S1 cases remain
at `axis3_semantic/` without modification.

### 3.2 Axis 2 vs Axis 1

Not audited — `axis2_ood_premises/` has no `cases.csv` yet. The
boundary rule (refusal-shaped cases belong to axis 2) is recorded
in `axis_naming.md` and will guide authoring.

### 3.3 Axis 4 vs Axis 1/3

`axis4_payload/` cases are all `clean` payload condition, all
current implementation status, all from the SCHEDULE family, all
from the Homberger-200 inventory. The stress vector is route count
(8–12 vs 18–22) and adversarial sub-pattern (`mid-list`,
`multi-entity`, `routes-by-position`). The cases do not exercise
language ambiguity; prompts are templated rather than paraphrased.

No axis-4-vs-axis-1/3 boundary conflict.

### 3.4 Axis 2 vs Axis 4

If a future axis 2 case uses a 200-customer payload to make a
false-premise customer ID harder to detect, the boundary rule §2
of `axis_naming.md` makes it an axis 2 case (refusal dominates).
This is recorded as a recommendation, not a current conflict.

## 4. Required fixes — by file

### `axis3_semantic/`

| Item | Status | Action |
|---|---|---|
| `cases.csv` exists and validates | ✓ | None. Inheritance from locked Run 2 verified by `tests/run2_stress/axis3_semantic/`. |
| Axis 3 strict-definition conflict | Surfaced in §3.1 | **Owner decision required.** No file change in this stage. |
| `reports/c0_baseline.csv` uses 8 canonical metric names | ✓ | None. |
| `reports/scatter.csv` (shared schema) | ✗ | **Emit the shared scatter file.** This is mechanical: call `shared/scatter.to_scatter_rows(...)` from the axis 3 runner after scoring; write under `axis3_semantic/reports/scatter.csv`. See §5 below for the snippet. |
| `useful_refusal_correct` / `partial_answer_correct` not emitted | acceptable | When the shared scatter file is emitted, those rows carry `score=""` for all 24 cases. |

### `axis4_payload/`

| Item | Status | Action |
|---|---|---|
| `cases.csv` exists and validates | ✓ | None. |
| `reports/c0_baseline.csv` uses canonical metric names | ✓ | None. |
| `reports/c0_baseline.md` uses display aliases | ✓ allowed | Markdown aliases are fine; the canonical names must appear in the shared scatter file (not the Markdown). |
| `reports/scatter.csv` (shared schema) | ✗ | **Emit the shared scatter file.** The axis already carries `band`, `n_routes`, `split`, and `intent` on its baseline CSV — the conversion to long-form is a `pivot_longer` style transform plus axis/system constants. |
| Model A/B baselines (`system_a_baseline.{md,csv}`, `system_b_baseline.{md,csv}`) | ✓ | Optional: emit shared scatter files for A and B too (one file per system). |

### `axis1_lookalike/`

| Item | Status | Action |
|---|---|---|
| `design.md` | ✗ | Author. The boundary rules in `axis_naming.md` define the scope. |
| `cases.csv` | ✗ | Author. If the §3.1 decision is "re-label", the existing axis 3 cases populate axis 1 directly. |
| C0 baseline + scatter | ✗ | After cases.csv lands. |

### `axis2_ood_premises/`

| Item | Status | Action |
|---|---|---|
| `design.md` | ✗ | Author. False-premise + comparator coverage. |
| `cases.csv` | ✗ | Author. |
| C0 baseline + scatter | ✗ | After cases.csv lands. |

### Locked / protected files

No protected files have been modified at this audit run. The
validator
`shared/validators.validate_no_protected_files_modified("HEAD")`
returned an empty list.

## 5. How an axis emits the shared scatter

This is the canonical pattern. It's documented here rather than
imposed on each axis — the runners stay axis-local; the helper is
shared.

```python
from product.evaluation.run2_stress.shared.scatter import (
    ScatterContext, to_scatter_rows, write_scatter_csv,
)

scored_pairs = list(zip(cases, scores))  # (Run2Case-like, CaseScore-like)
band_lookup = {c.case_id: c.stress_subtype for c in cases}  # axis-specific
payload_ctx = {
    c.case_id: ScatterContext(band=band_lookup[c.case_id])
    for c in cases
}
rows = to_scatter_rows(
    scored_pairs,
    axis="axis3_semantic",
    system="c0",
    payload_metadata_lookup=payload_ctx,
)
write_scatter_csv(rows, "product/evaluation/run2_stress/axis3_semantic/reports/scatter.csv")
```

The shared validator
`validate_scatter_schema(<path>)` confirms the result.

## 6. Discipline notes for the next stages

Before any work on System D begins:

1. The §3.1 decision must be resolved. Whichever path the owner
   picks, both `axis_naming.md` and `coordination_report.md` are
   updated to reflect the choice, and the axis 1 / axis 3 case
   inventories settle accordingly.
2. The shared scatter files must be emitted for at least the two
   axes that already have C0 baselines (axis 3 and axis 4) so the
   cross-axis joint report can run on real data when System D is
   evaluated.
3. The four axes' C0 baselines must all exist before System D
   freezes. C0 numbers on axis 1 and axis 2 will likely differ
   substantially from axis 3 and axis 4 because the failure modes
   differ; the System D evaluation needs the C0 numbers to compare
   against per-axis.
4. The System D freeze tag, the heldout-read tag, and the
   per-axis pre-registered prediction tables must all exist
   before any heldout result is reported.

## 7. Summary

- **Shared methodology files**: present (`scatter_schema.md`,
  `metric_names.md`, `system_d_design_envelope.md`,
  `axis_naming.md`).
- **Validators / scatter helper**: present.
- **Protected-file status**: clean (zero modified).
- **Axis 1 / axis 2**: empty. Need authoring before System D.
- **Axis 3**: **CLOSED for C0 baseline (Path B).** 24 cases,
  12 dev / 12 heldout, shared scatter emitted at
  `axis3_semantic/reports/scatter.csv`, closeout at
  `axis3_semantic/reports/axis3_closeout.md`. Definition is
  paraphrase / semantic-equivalence stress.
- **Axis 4**: C0 / A / B baselines present, conformant on metric
  names, missing only the shared scatter emission.
- **System D**: design envelope committed; no implementation
  attempted (per the task scope).

## 8. Recommended next action

Axis 3 is closed for C0 baseline. The next axis to land — owner's
choice — is either:

- **`axis1_lookalike/`** — *constructed* look-alike intent
  confusion (e.g. prompts whose surface tokens deliberately push
  the keyword classifier toward an adjacent wrong intent). This
  pairs naturally with axis 3's findings: where axis 3 measures
  "unseen vocabulary → unknown intent", axis 1 measures "seen
  vocabulary → wrong intent." Together the two axes characterise
  the front-door classifier's failure modes.
- **`axis2_ood_premises/`** — false premises, missing comparators,
  unsupported baselines. This pairs with the contract's refusal
  / partial-answer logic and tests a different layer of the
  contract from axis 3.

Either ordering is defensible. The shared methodology layer
(scatter schema, metric vocabulary, System D envelope) is in place
to support whichever axis lands next.

System D should remain unimplemented until at least one of axis 1
or axis 2 has a C0 baseline, so that System D's pre-registered
prediction table can name failure-mode targets beyond the axis 3
"unknown" mode that already has a baseline.

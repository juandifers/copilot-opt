# `shared/` — R2-S cross-axis methodology

This directory holds the shared methodology layer for the four R2-S
stress axes. The layer is **methodological only**: no system code
lives here, no case authorship, no scoring. Its purpose is to make
the four axes comparable and to pre-commit the design envelope for
System D before any axis-specific finding is allowed to motivate a
code change.

## Files

| File | Purpose |
|---|---|
| `scatter_schema.md` | The 10-column long-form per-case scatter schema every axis must support. |
| `metric_names.md` | The canonical metric vocabulary for the scatter `metric` column, mapped to `run2_scoring.CaseScore` fields. |
| `system_d_design_envelope.md` | What System D is allowed (and not allowed) to change. Pre-committed. |
| `axis_naming.md` | Per-axis definitions and the boundary rules between them. Governs the **strict** axis 3 definition. |
| `validators.py` | Programmatic checks for the schemas above. Used by `tests/run2_stress/shared/`. |
| `scatter.py` | Helper that converts `CaseScore`-like objects into the long-form scatter rows. |
| `coordination_report.md` | Audit of the existing axis directories against the shared schema and naming rules. |

## How to use this in a new axis

1. Author cases under `product/evaluation/run2_stress/<axis>/cases.csv`
   using the locked Run 2 gold schema (`run2_gold_schema.md`) plus any
   authorised axis-local extensions documented in the axis's
   `design.md`.
2. Read your scoring layer (typically wraps `run2_scoring.score_case`)
   and emit a wide-form per-case CSV for inspection.
3. **Additionally** call `shared/scatter.to_scatter_rows(...)` to
   emit a long-form scatter CSV under `<axis>/reports/scatter.csv`.
4. Run `shared/validators.validate_scatter_schema(<path>)` and
   `shared/validators.validate_metric_names(<path>)` in the axis's
   test suite.

## Read order for newcomers

For a reviewer joining mid-stage:

1. `axis_naming.md` — what the four axes are and the boundary rules.
2. `system_d_design_envelope.md` — what the upcoming System D
   intervention is allowed to change.
3. `scatter_schema.md` + `metric_names.md` — the cross-axis data
   contract.
4. `coordination_report.md` — current state of the four axes and
   what needs to land before System D begins.

## Non-goals of this directory

- No system code (no classifiers, no scorers, no model clients).
- No case authoring.
- No mutation of locked Run 2 files.
- No mutation of `product/copilot/*` or `product/data/*`.
- No commitments to deadlines or to ship.

The directory is intentionally narrow. Methodology lives here;
findings live in axis-specific reports; the cross-axis joint
report (still to be authored) will live under
`product/evaluation/run2_stress/analysis/`.

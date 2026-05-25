# `analysis/` — Cross-axis joint analysis (R2-S)

This directory is reserved for the cross-axis joint report and
its supporting scripts. In the current stage (R2-S shared
methodology) it contains only the concatenation helper; the joint
report itself is authored after all four axes have C0 baselines
and the System D heldout-read tag has been cut.

## Files

| File | Purpose |
|---|---|
| `concat_scatter.py` | Reads each axis's per-axis `reports/scatter.csv` (or `scatter_<system>.csv`), validates each against the shared schema, and emits `unified_scatter.csv`. |

## Discipline

Per `shared/README.md` and `axis_naming.md` §5, agents working on
a specific axis should write **only** inside that axis's directory.
`analysis/` is the seam where the cross-axis joint report consumes
those axis-local outputs.

Do not write per-axis cases, scoring code, or per-axis reports
into `analysis/`. The directory should stay small: one
concatenation helper today, one joint-report Markdown later, and
any plotting/analysis notebooks that the report references.

## Usage

```bash
python -m product.evaluation.run2_stress.analysis.concat_scatter
```

The script discovers `reports/scatter.csv` (and any
`reports/scatter_<system>.csv`) under each axis directory, runs
the shared validator on each, and concatenates them into
`analysis/unified_scatter.csv`.

The validator is strict: a single non-conforming file aborts the
concatenation. This is intentional — the unified scatter is only
useful if every axis is on the same schema.

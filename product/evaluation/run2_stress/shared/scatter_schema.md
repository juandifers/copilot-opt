# Shared per-case scatter schema (R2-S)

_All four R2-S stress axes (`axis1_lookalike`, `axis2_ood_premises`,
`axis3_semantic`, `axis4_payload`) MUST be able to emit a per-case
scatter table that conforms to this schema. Cross-axis analysis is
then a `pd.concat` of the per-axis scatter files._

This schema is **independent** of any axis-specific result CSV.
Each axis is free to keep its own wider per-case CSV in
`<axis>/reports/`; the shared scatter is an **additional** file
under `<axis>/reports/scatter.csv` (or wherever the axis registers
it) that obeys the contract below.

## 1. Columns (long-form)

Exactly these 10 columns, in this order:

```
case_id, axis, split, band, intent, n_routes, payload_chars, system, metric, score
```

| Column | Type | Required | Notes |
|---|---|---|---|
| `case_id` | str | yes | Stress case ID. Must be unique within `(case_id, system, metric)`. |
| `axis` | enum | yes | One of `axis1_lookalike`, `axis2_ood_premises`, `axis3_semantic`, `axis4_payload`. |
| `split` | enum | yes | `dev` or `heldout`. Other values are only permitted if the axis's `design.md` defines them explicitly and `validators.py` is updated. Prefer `dev` / `heldout`. |
| `band` | str | yes | Axis-specific stratification key. The meaning of `band` is **not standardized** across axes — see each axis's `design.md`. May be the empty string only when the axis's design documents that it does not stratify. |
| `intent` | enum | yes | Expected/gold intent for the case. Must be one of the existing `Intent` values from `product/copilot/contracts.py` plus any value listed under §3.2 of `run2_gold_schema.md` (`full_route_listing` today). |
| `n_routes` | int \| null | conditional | Route count if meaningful (e.g. axis 4); `null` when not meaningful for the case. |
| `payload_chars` | int \| null | conditional | Character count of the serialized payload / projection at evaluation time, if meaningful; `null` otherwise. |
| `system` | enum | yes | One of `c0`, `b`, `a`, `d`, or another explicit lowercase system label documented in the axis's `design.md`. Future System D rows must use `d`. |
| `metric` | enum | yes | One of the names listed in `shared/metric_names.md`. No other metric names are allowed in the **scatter** file. |
| `score` | float \| null | yes | Per-case metric value. Boolean metrics are `0.0` / `1.0`. Set-precision/recall metrics are fractions in `[0, 1]`. `null` when the metric is not applicable for the case (e.g. `useful_refusal_correct` on a case whose `expected_behavior_class != useful_refusal`). |

### Required columns and null semantics

Every row carries **every column**, including `n_routes` and
`payload_chars`. The two columns are `null` (not omitted) when the
axis does not measure them.

CSV serialisation: `null` is written as the empty string and read
with `pd.read_csv(path, keep_default_na=False, dtype=str)` followed
by per-column numeric coercion. The validator (`validators.py`)
accepts `""` as the canonical null token.

### One row per `(case_id, system, metric)`

The scatter file is long-form. A single case scored by C0 expands
into N rows where N = number of applicable metrics. A case scored by
two systems expands into 2 × N rows. The `(case_id, system, metric)`
triple is unique within a file; duplicates are a validation error.

### Inapplicable metrics

When a metric is not applicable for a case (per the rules in
`metric_names.md` §3), the axis SHOULD still emit a row with
`score = null`. Omitting the row is allowed but less analytically
convenient. The validator records both shapes as valid; downstream
aggregators must therefore handle the empty-set case gracefully.

## 2. File layout

Per-axis scatter files live at:

```
product/evaluation/run2_stress/<axis>/reports/scatter.csv
```

One file per axis × system combination is allowed; multiple files
combine into the unified scatter via `analysis/concat_scatter.py`.
Recommended naming when multiple systems share an axis:

```
<axis>/reports/scatter_c0.csv
<axis>/reports/scatter_b.csv
<axis>/reports/scatter_a.csv
<axis>/reports/scatter_d.csv
```

A single combined `scatter.csv` is also acceptable.

## 3. Validation

`shared/validators.validate_scatter_schema(path)` enforces:

1. The file's header is exactly the 10-column list above, in order.
2. `axis`, `split`, `system`, and `metric` use only the allowed
   vocabularies.
3. `case_id` is non-empty.
4. `score` is parseable as float when non-null and lies in `[0.0, 1.0]`
   when the metric is set-valued or boolean (the metric vocabulary in
   `metric_names.md` documents per-metric ranges).
5. `(case_id, system, metric)` is unique within the file.

The validator returns a list of human-readable error strings; the
empty list signals success.

## 4. Non-goals

This schema is intentionally narrow:

- It does **not** carry predicted vs. expected detail (those live in
  the axis's wider per-case CSV). The scatter is for aggregation,
  not error inspection.
- It does **not** carry difficulty, behavior_class, or any other
  gold-side metadata. Axes that need those for stratification should
  encode them into `band`.
- It does **not** encode time, latency, token count, or model
  provenance. Those live in the runner's run log.

The scatter is a single rectangle that a downstream notebook can
slice by `(axis, system, split, band, metric)` to produce every
cross-axis chart we plan to publish for System D.

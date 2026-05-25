# Shared metric vocabulary (R2-S)

_The R2-S scatter file (see `scatter_schema.md`) uses exactly the
metric names listed here, with the definitions below. Axis-specific
**aggregated** reports may use longer human-readable labels
("Evidence precision (field-family)", "Intent accuracy") for
display, but machine-readable scatter rows MUST use the exact
snake_case names below._

The definitions are derived from `product/evaluation/run2_scoring.py`
at HEAD `18b4811`. If the scorer's behavior changes, this file is
updated alongside it.

## 1. Allowed metric names

Only these 10 names are valid in the `metric` column of the shared
scatter file:

```
intent_correct
answerability_correct
behavior_class_correct
evidence_precision
evidence_recall
warning_precision
warning_recall
missing_field_recall
useful_refusal_correct
partial_answer_correct
```

Any other name is a validator error. In particular, the following
spellings are **forbidden** in the scatter:

| Forbidden | Use this instead |
|---|---|
| `intent_accuracy` | `intent_correct` |
| `intent_acc` | `intent_correct` |
| `ans` / `answerability_acc` | `answerability_correct` |
| `behavior_accuracy` / `beh_acc` / `behavior_class_acc` | `behavior_class_correct` |
| `evidence_p` / `ev_p` / `ev_prec` | `evidence_precision` |
| `evidence_r` / `ev_r` / `ev_rec` | `evidence_recall` |
| `warning_p` / `warn_p` | `warning_precision` |
| `warning_r` / `warn_r` | `warning_recall` |
| `miss_rec` / `missing_recall` | `missing_field_recall` |
| `useful_refusal_acc` / `useful_refusal` | `useful_refusal_correct` |
| `partial_answer_acc` / `partial_answer` | `partial_answer_correct` |

Aggregated Markdown tables may use the readable forms, but the
**CSV** scatter must use the canonical names above. The validator
`validate_metric_names` checks scatter files only — it does not
touch Markdown.

## 2. Definitions (matching `run2_scoring.py`)

### Boolean metrics — score ∈ {0.0, 1.0}

| Metric | Definition |
|---|---|
| `intent_correct` | `pred.predicted_intent == case.expected_intent`. |
| `answerability_correct` | `pred.predicted_answerability == case.expected_answerability`. |
| `behavior_class_correct` | `pred.predicted_behavior_class == case.expected_behavior_class`. |
| `useful_refusal_correct` | Applicable only when `case.expected_behavior_class == "useful_refusal"`. The composite holds when (a) predicted answerability matches gold, (b) every gold missing field appears in the predicted missing fields, and (c) at least one predicted next-action semantic code intersects the gold. See `score_case` for the exact rule. `null` on any other case. |
| `partial_answer_correct` | Applicable only when `case.expected_behavior_class == "partial_answer_with_warning"`. The composite holds when predicted answerability is `partially_answerable`, predicted warnings ∩ gold warnings is non-empty (or gold is empty), predicted missing ∩ gold missing is non-empty (or gold is empty), and predicted next-actions ∩ gold next-actions is non-empty (or gold is empty). `null` on any other case. |

### Set-precision / set-recall metrics — score ∈ [0.0, 1.0]

| Metric | Definition |
|---|---|
| `evidence_precision` | `|P ∩ G| / |P|` where P is the predicted evidence-paths set (predicate qualifiers stripped per schema §10a) and G is the gold set. `1.0` if both are empty; `0.0` if exactly one is empty. |
| `evidence_recall` | `|P ∩ G| / |G|`. `1.0` if both are empty; `1.0` also when gold is empty regardless of P (the case does not require evidence). |
| `warning_precision` | Same shape as `evidence_precision`, over warning codes. |
| `warning_recall` | Same shape as `evidence_recall`, over warning codes. |
| `missing_field_recall` | `|P ∩ G| / |G|` over missing-field paths, where G is the gold's `expected_missing_fields`. **Convention**: `1.0` when G is empty (the predictor is not penalised for declining to invent missing fields). |

### Applicability rules

- `useful_refusal_correct` and `partial_answer_correct` are
  **case-conditional**: the scatter row's `score` is `null` (or the
  row is omitted) when the case's gold does not match the relevant
  `expected_behavior_class`. Axes that emit one row per
  (case, metric) should emit a `null` row rather than omit, for
  cross-axis convenience.
- All other metrics are **always applicable** — emit a numeric score
  on every (case, system) pair.

## 3. Per-system score scope

A scatter row's `system` column declares which system produced the
prediction. The same case appears once per (system) in the scatter,
expanded across the 10 metric rows above.

`c0` is the deterministic Run 2 contract pipeline (System C).
`a`, `b` are the prior + prompt-only model baselines defined by
`run2_system_a_prior.py` / `run2_model_baseline_runner.py`.
`d` is reserved for System D (semantic intent classifier — see
`system_d_design_envelope.md`); axes MUST NOT emit `d` rows until
System D exists.

## 4. Cross-reference

| Metric name | Scorer field on `CaseScore` |
|---|---|
| `intent_correct` | `.intent_correct` |
| `answerability_correct` | `.answerability_correct` |
| `behavior_class_correct` | `.behavior_class_correct` |
| `evidence_precision` | `.evidence_precision` |
| `evidence_recall` | `.evidence_recall` |
| `warning_precision` | `.warning_precision` |
| `warning_recall` | `.warning_recall` |
| `missing_field_recall` | `.missing_field_recall` |
| `useful_refusal_correct` | `.useful_refusal_correct` (Optional[bool]) |
| `partial_answer_correct` | `.partial_answer_correct` (Optional[bool]) |

The shared scatter helper (`shared/scatter.py`) reads these fields
off `CaseScore`-like objects and writes them under the canonical
names above.

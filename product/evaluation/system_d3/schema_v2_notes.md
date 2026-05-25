# Schema v2 — Causal-Unsupported Extension

_System D3 introduces a versioned contract extension that lets the
copilot explicitly mark causal "why / what caused" prompts as
factually answerable but causally unsupported. The locked Run 2
schema v1 cannot express this, so the original gold for the five
Axis-2 Band-4 causal cases was downgraded to "closest supported
behavior". D3 ships an overlay (`axis2_causal_gold_overlay.csv`)
that re-asserts the faithful gold, plus a D3 scorer adapter that
uses overlay gold for those case ids and inherits original gold
for everything else._

## 1. What v2 adds

| Element | v1 | v2 (D3) |
|---|---|---|
| Warning enum | warnings is `list[str]`; the string `causal_mechanism_unsupported` is not emitted by any system | The string `causal_mechanism_unsupported` is a recognised warning code, emitted by `d3_refusal_policy.build_warnings_d3` on "why / what caused" prompts that target a factually-answerable intent |
| Behavior class enum | `direct_answer`, `direct_answer_with_warning`, `partial_answer_with_warning`, `useful_refusal` — unchanged | Same four values. Adding the causal warning to an otherwise-answerable case shifts the projection from `direct_answer` → `direct_answer_with_warning`, which is the existing v1 transition |
| Next-action enum | Existing semantic codes (`expose_units_objective`, `use_validity_payload`, etc.) | A new optional code `expose_causal_diagnostics` is defined as future work but is NOT required by the overlay gold. Adding the code to the schema is not load-bearing for the 5 target cases — they grade on warnings + behavior class |
| Evidence paths | Per-intent required fields | Unchanged. D3 keeps citing observed facts (`n_late_customers`, `n_routes`, `action_objective`, etc.) and does not invent causal-attribution fields |

Because `warnings: list[str]` is open-set in the schema, **no
Pydantic enum change is required**. D3 does not modify
`product/copilot/contracts.py` or `product/data/product_schema.py`.

## 2. Causal trigger detector

D3 fires the warning when **all** of:

1. The prompt matches one of the causal phrase patterns
   (`why is/are/did/does/was`, `what caused`, `what's causing`,
   `what made`, `what's pushing`, `what's driving`, `what drove`).
2. The intent is **factually answerable** under the existing
   contract (so the copilot still has something to cite). The
   factual-intent set is the canonical intent enum minus
   `unknown`, `refusal_or_insufficient_payload`, and
   `before_after_comparison` (already its own paraphrase class).
3. The case is not already a false-premise refusal (the D2
   false-premise warning dominates).

This means the causal warning will only fire when D3 is going to
ship a `direct_answer_with_warning` or
`partial_answer_with_warning` — never on a pure refusal where the
warning would be noise.

## 3. Behavior-class policy

| Pre-D3 status | Pre-D3 behavior_class | D3 outcome |
|---|---|---|
| answerable | direct_answer | `direct_answer_with_warning` (warning added, evidence kept) |
| answerable | direct_answer_with_warning | unchanged class — the causal warning joins the existing warnings list |
| partially_answerable | partial_answer_with_warning | unchanged class |
| not_answerable | useful_refusal | unchanged — D3 does **not** add the causal warning to refusals |

D3 always cites observed facts. It never invents a causal
decomposition. If the payload supports current-status facts (a
late-customer list, an objective value, a route count), D3 cites
them and tags the response with the causal-unsupported warning.
If the payload supports nothing at all, D3 defers to D2's refusal
shape unchanged.

## 4. Overlay gold protocol

Original `product/evaluation/run2_stress/axis2_ood_premises/cases.csv`
is **byte-identical** to its committed version under D3. The
overlay file `axis2_causal_gold_overlay.csv` contains exactly
five rows keyed by `case_id`:

- A2D-10
- A2D-11
- A2D-12
- A2H-11
- A2H-12

Each overlay row carries the v2 gold for the columns D3 grades on
(`expected_intent`, `expected_answerability`,
`expected_evidence_paths`, `expected_missing_fields`,
`expected_warnings`, `expected_next_actions`,
`expected_behavior_class`). The D3 scorer adapter reads the
overlay first; if a `case_id` matches, it builds a `Run2Case`
whose v2 columns are taken from the overlay and whose v1 columns
(such as `label_rationale`) are taken from the original CSV.

This keeps the original Axis 2 v1 reports reproducible bit-for-bit
under their own runners, while letting D3 grade the five target
cases against v2 gold.

## 5. Future work

- A formal `expose_causal_diagnostics` semantic code in the
  product next-action enum, paired with a `payload.causal_diagnostics`
  schema field for solver-side decomposition.
- Generalisation of the v2 warning to additional intents (e.g.
  cost-attribution prompts) when the payload supports
  decomposition fields.
- A frontend chip / explanation surface for
  `causal_mechanism_unsupported` so the operator immediately sees
  that the system answered the factual part but not the cause.

# R2-S Axis 4 Closeout — Payload Scale Stress

_Status: **CLOSED for C0 / A / B baseline.** Frozen at HEAD
`18b4811a1f85c166ea3ba8c777dfc021b2a5f747` (tag `run2-contract-extended`).
Closeout authored 2026-05-21 under the shared R2-S methodology in
`product/evaluation/run2_stress/shared/`._

## 1. Purpose

Axis 4 tests **payload and context scale**: long Homberger-200
SCHEDULE payloads, route-count growth from 8 to 22, and the
model-facing projection budget the prompt-template compaction
applies before the LLM ever sees the payload. The hypothesis under
test was that `evidence_precision` degrades monotonically with route
count under the model-based systems (A, B) while staying flat for
the deterministic contract (C0).

Axis 4 is **not** solver validation, **not** a user study, and
**not** primarily a semantic-intent stress. It is the only one of
the four R2-S axes that grades model-facing payload/projection
robustness rather than the keyword classifier or the contract layer
in isolation.

## 2. Relationship to Axes 1–3

- **Axis 3** tested unseen wording → `unknown` intent fallback.
- **Axis 1** tested misleading familiar wording → wrong adjacent
  intent.
- **Axis 2** tested unsupported premises/comparators → refusal and
  partial-answer correctness on the contract layer.
- **Axis 4** tests payload scale and **model-facing projection**
  robustness. It is the first axis where the system-under-test is
  not the deterministic contract but the prompted model that has to
  reason against a compacted view of the payload.

Together, Axes 1, 2, and 3 isolate failure modes of the *contract
layer* (wrong-adjacent-intent, unknown-intent, missed refusal /
partial). Axis 4 isolates failure modes of the *model-facing
projection*. C0 is robust on all four axes by design — the contract
layer has the full structured payload — so Axis 4's diagnostic
target is A and B, not C0.

## 3. Method

- **24 cases**, all SCHEDULE family, drawn from the 68 unsampled
  Homberger-200 (instance × magnitude) cells with pyvrp_10s
  checkpoints.
- **Two bands**: `low` (n_routes ∈ [8, 12], 12 cases) and `high`
  (n_routes ∈ [18, 22], 12 cases). The mid band (13–17) is
  intentionally empty — see `design.md` §4.
- **Three intents** per band: `customer_arrival`, `route_end_time`,
  `lateness_summary` (4 cases per (band, intent) sub-cell).
- **Three systems already run**: C0 (deterministic contract), A
  (deterministic intent/answerability prior plus model evidence),
  B (prompt-only model).
- **C0 uses full deterministic contract access**; A and B use the
  model-facing payload projection (the prompt template compacts
  `customer_schedule` to 60 inline rows).
- **No solver calls.** No optimization run.
- **No `product/copilot/*` or `product/data/*` changes.**
- **No locked Run 2 files modified.**
- **Model metadata**:
  - requested model: `gpt-5.4-mini`
  - observed response model (B): `gpt-5.4-mini-2026-03-17`
  - observed response model (A): `gpt-5.4-mini-2026-03-17`
- **Wall-clock**: B 42.6 s + A 39.6 s = 82.3 s total
- **API tokens**:
  - B prompt 184,679 / completion 2,881
  - A prompt 183,427 / completion 3,048
- **Errors**: B = 0, A = 0
- **Scoring**: `run2_scoring.score_case` unchanged.

Artefacts in this closeout:

- `cases.csv` — locked 24-case CSV (18 columns: 17 gold + `split`).
- `reports/c0_baseline.{csv,md}` — C0 per-case + summary.
- `reports/system_a_baseline.{csv,md}` — A per-case + summary.
- `reports/system_b_baseline.{csv,md}` — B per-case + summary.
- `reports/stress_axis4_summary.md` — combined C0/A/B summary
  (per-(system × band), per-(system × band × intent),
  predicted-vs-observed delta, surprises, failure-mode analysis,
  Markdown scatter).
- `reports/scatter.csv` — long-form scatter conforming to
  `shared/scatter_schema.md` (this closeout adds the file; the
  earlier Markdown scatter inside `stress_axis4_summary.md` is
  preserved unchanged).
- `reports/axis4_closeout.md` — this file.

## 4. Results

### 4.1 Per-system × band metrics

| system | band | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | low  | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A  | low  | 12 | 1.000 | 1.000 | 0.917 | 0.667 | 1.000 | 0.917 | 1.000 | 1.000 |
| A  | high | 12 | 1.000 | 1.000 | 1.000 | 0.567 | 1.000 | 1.000 | 1.000 | 1.000 |
| B  | low  | 12 | 1.000 | 0.583 | 0.417 | 0.528 | 1.000 | 0.417 | 0.917 | 1.000 |
| B  | high | 12 | 0.833 | 0.583 | 0.333 | 0.319 | 0.625 | 0.333 | 0.917 | 1.000 |

### 4.2 Per-system × band × intent breakdown

| system | band | intent | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | low  | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | low  | route_end_time   | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | low  | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | route_end_time   | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A  | low  | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 |
| A  | low  | route_end_time   | 4 | 1.000 | 1.000 | 0.750 | 0.500 | 1.000 | 0.750 | 1.000 |
| A  | low  | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A  | high | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 |
| A  | high | route_end_time   | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 |
| A  | high | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 0.700 | 1.000 | 1.000 | 1.000 |
| B  | low  | customer_arrival | 4 | 1.000 | 0.500 | 0.500 | 0.500 | 1.000 | 0.500 | 1.000 |
| B  | low  | route_end_time   | 4 | 1.000 | 0.500 | 0.250 | 0.500 | 1.000 | 0.250 | 0.750 |
| B  | low  | lateness_summary | 4 | 1.000 | 0.750 | 0.500 | 0.583 | 1.000 | 0.500 | 1.000 |
| B  | high | customer_arrival | 4 | 1.000 | 0.250 | 0.250 | 0.250 | 0.500 | 0.250 | 1.000 |
| B  | high | route_end_time   | 4 | 1.000 | 0.750 | 0.250 | 0.500 | 1.000 | 0.250 | 0.750 |
| B  | high | lateness_summary | 4 | 0.500 | 0.750 | 0.500 | 0.208 | 0.375 | 0.500 | 1.000 |

### 4.3 Predicted-vs-observed delta

A condensed view; the full per-metric delta table lives in
`stress_axis4_summary.md` §3. Pre-registered predictions in
`design.md` §6.

| system | band | metric | predicted | observed | δ vs midpoint | in_range |
|---|---|---|---|---:|---:|:-:|
| A | low  | ev_prec | 0.75–0.85 | 0.667 | −0.13 | ✗ |
| A | high | ev_prec | 0.55–0.75 | 0.567 | −0.08 | ✓ |
| A | high | beh    | 0.85–0.90 | 1.000 | +0.13 | ✗ |
| B | low  | ans    | 0.95–1.00 | 0.583 | −0.39 | ✗ |
| B | low  | beh    | 0.80–0.90 | 0.417 | −0.43 | ✗ |
| B | low  | warn_p | 0.90–0.95 | 0.417 | −0.51 | ✗ |
| B | high | beh    | 0.75–0.85 | 0.333 | −0.47 | ✗ |
| B | high | warn_p | 0.85–0.95 | 0.333 | −0.57 | ✗ |
| B | high | ev_p   | 0.45–0.65 | 0.319 | −0.23 | ✗ |

Deltas are reported for completeness. The interpretation in §5 does
**not** rest on whether the pre-registered prediction was tight; the
qualitative shape — C0 flat at 1.000, A degraded on evidence
precision only, B degraded sharply on the contract-shape metrics —
is what the closeout is about.

## 5. Main finding

**Axis 4 does not expose a C0 contract failure. C0 remains perfect
in both low- and high-payload bands.** The stress instead exposes
**model-facing projection brittleness**: prompt-only B degrades
sharply under high payload scale, while A preserves intent and
answerability through deterministic priors but still suffers
evidence over-citation.

This supports the thesis claim that large-context optimization
copilots need **deterministic answerability and evidence
infrastructure** rather than relying on model interpretation of
compacted payloads alone. C0's perfect score on Axis 4 is not a
proof that LLMs cannot do payload-grounded reasoning at this scale;
it is a demonstration that the deterministic contract layer is
robust by construction (it has the full structured payload) and
that A/B's failures are localized to the projection / evidence
selection seam, not to the contract itself.

## 6. Failure-mode analysis

### 6.1 Evidence over-citation (A and B)

A and B emit identifier fields beyond the gold for the intent. The
most over-cited paths across the 24 cases:

| field path | A count (/24) | B count (/24) |
|---|---:|---:|
| `customer_schedule[].customer_id`    | 10 | 9 |
| `route_end_times[].route_idx`        | 8  | 8 |
| `customer_schedule[].is_late`        | 2  | 6 |
| `customer_schedule[].lateness_minutes` | 1 | 2 |
| `customer_schedule[].route_idx`      | 1  | 0 |
| `customer_schedule[].arrival`        | 0  | 1 |

Frame:

- This is **not a C0 failure**. C0 cites only the intent-required
  field family (`customer_schedule[].arrival`, `route_end_times[].end_time`,
  or `late_customer_ids`/`n_late_customers`) and scores 1.000 evidence
  precision on every case.
- This is a **model evidence-selection failure**: the LLM volunteers
  the identifier field alongside the value field even though the
  identifier is not what the intent's gold cites.
- The pattern is consistent with the R2-4A / R2-5 over-citation
  result on Run 1 SCHEDULE prompts — Axis 4 confirms it under
  payload-scale stress without surfacing a new mode.

### 6.2 B truncation-induced false premises

System B fires `false_premise_detected` on customer-arrival
questions where the customer ID lies in the **truncated tail** of
the schedule projection. The prompt builder caps `customer_schedule`
at `_MAX_SCHEDULE_ROWS_INLINE = 60`; B sees only the compacted view
and concludes the customer does not exist in the plan.

Affected cases: **R2-101, R2-102, R2-113, R2-114, R2-115** (n=5).

Frame:

- This is a **model / projection failure**, not a contract failure.
- C0 and A avoid this failure mode because the **deterministic
  answerability check uses the full payload** via
  `product/data/entity_resolution.py`, not the compacted projection
  the model sees.
- The fix is upstream of the contract: either widen the projection
  (cite customer IDs on a separate channel, or fetch on demand) or
  let the LLM consume the deterministic answerability result
  instead of re-deriving it from the truncated view.

### 6.3 B warning over-firing

B emits warnings **from intuition rather than contract-pinned
rules**:

- `route_indexing_ambiguity` on positional route phrasings such as
  "the 11th route" or "the 15th route" (the contract's regex
  `\broute\s+\d+\b` is intentionally narrow and only matches
  `route N` singular).
- `route_indexing_ambiguity` on plural route enumerations such as
  "routes 8, 12, and 17".
- `struct_membership_ambiguity` on lateness-summary questions
  naming multiple customers (that code is bound to the
  `single_customer_route_membership` intent in
  `product/copilot/refusal_policy.py`).

Frame:

- Evidence that **warning policy should remain deterministic or
  post-validated**. The contract's narrow regex-pinned rules are not
  recoverable from prompted-LLM intuition; B reinvents broader
  triggers and over-fires.
- A's deterministic prior holds these warnings correctly on 11/12
  low-band and 12/12 high-band cases (one slip — see §6.4).

### 6.4 A silent prior override

System A added `route_indexing_ambiguity` on **R2-108** ("When does
the 11th route finish?") **without** flagging `prior_disagreement =
true`. The deterministic prior locks warnings; A is supposed to
copy them unchanged and surface disagreement explicitly.

Frame:

- A **prior-lock compliance issue** in the A scaffolding (one case
  out of 24).
- **Future work** for stricter model-output post-validation
  (validate that A's emitted warnings are exactly the prior's
  warnings, or flag the disagreement).
- **Not a C0 failure** — C0's warnings on this case are correct
  (none); A's deterministic prior copy of C0 would also be correct.

## 7. System D implication

Be explicit about scope: per
`product/evaluation/run2_stress/shared/system_d_design_envelope.md`,
the current System D envelope is the **semantic intent adapter** for
`product/copilot/intent.py`. Axis 4 does **not** primarily motivate
an intent-classifier change — every Axis 4 failure mode lives in the
projection / evidence-selection / warning-policy layer (B) or the
prior-lock layer (A), not in the intent classifier.

**Under the current System D envelope, Axis 4 is mostly future
work.** It supports preserving deterministic answerability /
warning / evidence infrastructure. Potential future improvements,
all outside the current envelope unless the owner broadens it:

- **Projection / index coverage** — widen the prompt projection so
  out-of-window customer IDs are still discoverable.
- **ID-aware retrieval** — let the LLM fetch by customer ID on
  demand rather than reading a fixed window.
- **Evidence post-validation** — prune model-emitted evidence paths
  to the intent's gold field family before scoring.
- **Warning post-validation** — gate model-emitted warnings on the
  contract's regex-pinned rules.
- **Stricter prior locking for A-style hybrids** — enforce that A's
  emitted warnings are byte-equal to the deterministic prior or
  flagged as disagreement.

If System D remains scoped to intent classification, **Axis 4 should
be treated as a "must not regress" axis for C0-like deterministic
correctness**, not a primary target. The closeout owner can choose
to broaden the envelope to cover projection / post-validation, but
Axis 4 alone does not mandate it.

## 8. Status

**Status: CLOSED for C0 / A / B baseline.**

Artefacts (in the repo):

- `product/evaluation/run2_stress/axis4_payload/cases.csv`
- `product/evaluation/run2_stress/axis4_payload/design.md`
- `product/evaluation/run2_stress/axis4_payload/reports/c0_baseline.csv`
- `product/evaluation/run2_stress/axis4_payload/reports/c0_baseline.md`
- `product/evaluation/run2_stress/axis4_payload/reports/system_a_baseline.csv`
- `product/evaluation/run2_stress/axis4_payload/reports/system_a_baseline.md`
- `product/evaluation/run2_stress/axis4_payload/reports/system_b_baseline.csv`
- `product/evaluation/run2_stress/axis4_payload/reports/system_b_baseline.md`
- `product/evaluation/run2_stress/axis4_payload/reports/stress_axis4_summary.md`
- `product/evaluation/run2_stress/axis4_payload/reports/scatter.csv`
- `product/evaluation/run2_stress/axis4_payload/reports/axis4_closeout.md`

Verified at closeout:

- 24/24 cases scored under C0, A, and B; zero API errors.
- `scatter.csv` (720 rows = 24 × 3 × 10) validates against
  `validate_scatter_schema` and `validate_metric_names` with zero
  errors.
- `payload_chars` populated for every row (24 unique values,
  37,226–38,423 bytes per case).
- No protected Run 2 files modified.
- No `product/copilot/*` or `product/data/*` files modified.
- All Axis 1 / Axis 2 / Axis 3 / shared / locked Run 2 tests
  continue to pass.

## 9. Deferred

- **pass^k on Axis 4 B / A** (optional repeated-sampling reliability
  estimate) — not run; the deterministic prior on A makes the
  reliability question mostly redundant in this axis.
- **Model-output post-validation** (evidence pruning and warning
  gating) — future work.
- **Projection retrieval redesign** (ID-aware retrieval, wider
  projection window) — future work.
- **System D** — not built here. When built, Axis 4 is the
  "must not regress" baseline if the envelope stays intent-only.
- **Cross-axis synthesis** — next step (see §10).

## 10. Recommended next step

**Cross-axis C0 synthesis across Axes 1–4.**

Combine the four scatter files:

- `product/evaluation/run2_stress/axis1_lookalike/reports/scatter.csv`
- `product/evaluation/run2_stress/axis2_ood_premises/reports/scatter.csv`
- `product/evaluation/run2_stress/axis3_semantic/reports/scatter.csv`
- `product/evaluation/run2_stress/axis4_payload/reports/scatter.csv`

and produce a failure map that separates:

- **System-D-addressable intent failures** (Axis 1's
  wrong-adjacent-intent, Axis 2's wrong/unknown-intent on implicit
  comparator/movement, Axis 3's unknown-fallback).
- **Out-of-envelope answerability / refusal-policy failures**
  (Axis 2's missed_false_premise on non-entity-bound intents).
- **Schema gaps** (Axis 2's causal-mechanism cases).
- **Model-projection failures** (Axis 4's evidence over-citation,
  B truncation-induced false premise, B warning over-firing,
  A silent prior override).
- **Must-not-regress guard-protected cases** (Axis 1 guard-protected,
  Axis 4 C0 perfect across both bands, Axis 3 conditional-on-intent
  perfect).

The Axis 4 layer of that synthesis is the C0 "robust by
construction" floor that every other system gets compared against.

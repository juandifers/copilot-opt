# R2-S axis naming and boundary rules

_The four R2-S stress axes share the same underlying contract
(Run 2's locked gold rows are inherited where possible) but probe
different failure modes. This document defines what each axis is
**for** and what it must **not** be confused with. If a candidate
case fits two axes, the rules below decide which one owns it._

## 1. The four axes

### Axis 1 — Look-alike intent stress (`axis1_lookalike/`)

**Cases where lexical surface tokens in the prompt push the existing
keyword-based classifier toward an adjacent but wrong intent.**

The defining property of axis 1 is that the contract layer's
deterministic intent matcher has a **token-level rule** that, on the
stress prompt's surface form, would fire toward an intent that is
**not** the operator-intended intent. The intent the matcher would
fire is itself a supported intent (i.e. a real `Intent` enum value),
just the wrong one.

Examples:

- "Where is customer 42 going next?" — the `_NEW_ORDER_TOKENS` /
  `_is_about_new_customer_assignment` heuristic might fire on "next"
  and route the question to `new_customer_assignment`, even though
  the operator wants `single_customer_route_membership`.
- "Did customer 42 finish before customer 17?" — `finish` is in the
  `route_end_time` token set, which could pull a customer-arrival
  question toward `route_end_time`.

Axis 1 tests **confusion between two supported intents**, both of
which the matcher knows about, where the surface form mis-steers.

### Axis 2 — Out-of-distribution false premises and comparators (`axis2_ood_premises/`)

**Cases where the user asks with unsupported premises, nonexistent
entities, missing referents, or comparison structures that the
payload does not support.**

The defining property of axis 2 is that the contract's correct
response is **refusal-shaped**: useful_refusal or
partial_answer_with_warning with `false_premise_detected`,
`comparison_referent_ambiguity`, `unsupported_comparison`, or a
similar warning. The stress is whether the contract correctly
declines, names the absent entity / referent, and emits a
recoverable next-action — not whether it picks an intent.

Examples:

- "Why did customer 999 move to route 4?" when customer 999 does
  not exist in the current plan.
- "Compare this to the original plan" when no `baseline_solution`
  is in the payload.
- "Which route improved most?" when no diff/comparison fields
  exist.
- "What's the cost compared to a full re-solve?" when
  `reference_solution.objective` is not in the payload.

Axis 2 tests **refusal contract quality**, not intent selection.

### Axis 3 — Semantic intent / paraphrase stress (`axis3_semantic/`)

**Governing definition.** Cases where the user asks an
already-supported operator question using semantically equivalent
but lexically unseen or non-template phrasing.

These cases preserve the same canonical intent and payload
answerability as a known supported Run 2-style prompt, but stress
whether the front-door intent classifier maps the language
correctly.

Examples:

- "When does vehicle 3 close out?" → `route_end_time`
- "Can this plan actually be driven as-is?" → `feasibility_status`
- "Which vehicle is customer 17 assigned to?" →
  `single_customer_route_membership`
- "Does anyone miss their promised window?" → `lateness_summary`

The defining property of axis 3 is that the **intent is clear to a
human and already supported** by the Run 2 contract, but the
**wording differs** from the surface forms the existing keyword
classifier was authored against. Axis 3 isolates the
language-to-intent mapping problem from every other failure mode.

Axis 3 explicitly does **not** include:

- false premises (axis 2 territory)
- unsupported comparators or missing baselines (axis 2)
- large-payload evidence-selection stress (axis 4)
- multi-intent compound questions ("is the plan feasible AND what
  does it cost?")
- vague or decomposition-requiring questions with no clear
  supported intent
- intent-confusion cases where the surface form is *constructed* to
  trigger a specific adjacent wrong intent (axis 1 territory)

**Boundary rule with axis 1.** If a case is both a paraphrase
**and** constructed to trigger a specific adjacent wrong intent
(e.g. wording that the keyword classifier actively reroutes to a
neighbouring supported intent), put it in axis 1. Ordinary
semantic-equivalence paraphrases — where the classifier returns
`unknown` or the right intent purely as a function of vocabulary
coverage, with no neighbouring-intent confusion in evidence —
belong in axis 3.

### Axis 4 — Large-context payload stress (`axis4_payload/`)

**Cases where the main stressor is payload size, route count,
customer count, evidence retrieval difficulty, long schedules,
large IDs, or many similar entities.**

The defining property of axis 4 is that the **same** prompt
(intent-wise) would resolve correctly on a small payload but
exhibits degradation as payload scale grows. Axis 4 tests
context-scale and evidence selection under large structured
payloads, **not** solver quality and **not** language ambiguity.

The existing `axis4_payload/` design exercises Homberger-200
SCHEDULE-family cases stratified by route count band
(low = 8–12 routes, high = 18–22 routes), all clean payload
conditions, all current implementation status.

## 2. Boundary rules — quick decision table

When a candidate case touches more than one axis, use this table.
"Semantic paraphrase" means "rewording of an already-supported
question, no constructed lookalike pressure." "Constructed
lookalike" means the surface tokens are *intentionally* chosen to
push the classifier toward a specific adjacent wrong intent.

| Combination | Owner |
|---|---|
| Constructed lookalike (any other stressor absent) | **Axis 1** |
| Constructed lookalike AND semantic paraphrase | **Axis 1** (boundary rule in §1) |
| Semantic paraphrase only (no constructed lookalike pressure) | **Axis 3** |
| False premise / missing comparator / unsupported baseline | Axis 2 — refusal contract is the dominant concern |
| Constructed lookalike AND false premise | Axis 2 |
| Semantic paraphrase AND false premise | Axis 2 |
| Constructed lookalike AND large payload | Axis 4 (scale stress dominates iff token effect is also present on small payload) |
| Semantic paraphrase AND large payload | Axis 4 |
| False premise AND large payload | Axis 2 |
| Lookalike + paraphrase + payload + false premise | Axis 2 — refusal contract beats all |

When in doubt, axis 2 owns refusal-shaped cases (false premise,
missing comparator, missing baseline). When refusal is not at
issue, the decision between axis 1 and axis 3 turns on whether the
surface form is *constructed* to trigger a specific wrong intent
(axis 1) versus *naturally* using vocabulary the classifier was not
authored against (axis 3).

## 3. Methodological decision (Axis 3 paraphrase definition, Path B)

The earlier revision of this document defined axis 3 as
"compositional / decomposition-requiring prompts" and applied the
rule "all surface-token swaps belong in axis 1." Under that
stricter rule, the 24 cases already authored in
`axis3_semantic/cases.csv` would have been re-labelled as axis 1.

The project owner adopted **Path B**: keep axis 3 as
semantic-equivalence / paraphrase stress, soften the boundary rule
so that ordinary paraphrases belong in axis 3, and reserve axis 1
for *constructed* look-alike intent confusion. The decision is
recorded in `coordination_report.md` and is the definition this
section §1 now reflects.

The older "all surface-token swaps belong in axis 1" rule is
**deprecated** and replaced by the conditional rule in §1: cases
fitting both axis 1 and axis 3 belong in axis 1 only when the
surface form is *constructed* to trigger a specific adjacent wrong
intent. Ordinary semantic-equivalence paraphrases — like every one
of the 24 R2-S1 cases — belong in axis 3.

No case migration is performed under this decision. The
`axis3_semantic/` baseline of record is the 24-case dev/heldout
split at HEAD `18b4811`, and the C0 closeout in
`axis3_semantic/reports/axis3_closeout.md` reads it that way.

## 4. Naming conventions for new axes

If new axes are added in the future (e.g. `axis5_*`), the naming
must:

- Use `axis<N>_<short_kebab_name>/` under
  `product/evaluation/run2_stress/`.
- Add a new entry to this document with a definition, a defining
  property, and any boundary rules against existing axes.
- Add the axis name to the `axis` enum in `scatter_schema.md` and
  to `validators.ALLOWED_AXES`.

## 5. What every axis must produce

Every axis, regardless of focus, must produce:

- `<axis>/design.md` — purpose, hypothesis, scope, guardrails,
  schema deviations, split methodology, frozen-baseline commit.
- `<axis>/cases.csv` — case rows in the 17-column gold schema (with
  authorised extensions; see each axis's `design.md`).
- `<axis>/reports/c0_baseline.md` — C0 baseline at the frozen
  commit.
- `<axis>/reports/c0_baseline.csv` — per-case C0 results (axis-wide
  shape allowed).
- `<axis>/reports/scatter.csv` — per-case long-form scatter
  conforming to `scatter_schema.md`. (This is the new requirement.
  Existing axes may not yet have it; see `coordination_report.md`.)

Cases must declare a `split` (preferably `dev` / `heldout`) and a
`band` stratification key (or document why no band applies).

## 6. Cross-axis non-overlap (recommended, not strictly required)

Two cases in two different axes may have the same prompt text only
if they use **different payloads** to exercise different failure
modes (e.g. axis 1 uses a clean payload; axis 4 uses the same
prompt against a 200-customer payload). Identical (prompt, payload)
pairs in two axes is a duplication and should be folded into one
axis, with the analysis stage noting which axis the row belongs to.

The shared scatter file's `(case_id, system, metric)` uniqueness
constraint enforces non-overlap **per case_id** automatically; the
recommendation above is about authorial discipline.

# R2-S Axis 1 Closeout — Look-alike Intent Stress

_Status: **CLOSED for C0 baseline.** Frozen at HEAD `18b4811`
("Run 2 contract extensions completed"). Closeout authored
2026-05-20 under the shared methodology in
`product/evaluation/run2_stress/shared/`._

## 1. Purpose

Axis 1 tests whether the System C0 deterministic intent classifier
(`product/copilot/intent.py`) can be tricked into **confidently
misrouting** an operator question to a neighbouring wrong intent by
surface-token attractors. The 24 cases are constructed look-alike
prompts whose semantically intended intent is supported and clear
but whose surface form is engineered to push the keyword matcher
toward a different supported intent.

The failure mode under test is **wrong_adjacent_intent** — the
classifier returns a known `Intent` enum value that is not the
gold. This is more dangerous than Axis 3's `unknown`-fallback mode
because the downstream contract pipeline can then produce a
plausible-looking response for the wrong question, without warning
the operator.

## 2. Relationship to Axis 3

The two diagnostic axes characterise the front-door classifier's
**two complementary failure modes**:

| Axis | Failure mode tested | Surface form |
|---|---|---|
| **Axis 3** (`axis3_semantic/`) | unseen vocabulary → `unknown` intent | semantic paraphrase, no constructed lookalike pressure |
| **Axis 1** (`axis1_lookalike/`) | familiar attractor vocabulary → **wrong adjacent intent** | constructed look-alike, lexical attractor for a specific neighbouring intent |

The shared boundary rule in `shared/axis_naming.md` §1 / §2
assigns ownership: ordinary semantic-equivalence paraphrases belong
in Axis 3; cases whose surface tokens are *intentionally* chosen to
trigger a specific adjacent wrong intent belong in Axis 1.

Together the two C0 closeouts give the project a graded picture of
how the keyword classifier degrades under operator language
variation:

- Axis 3 (this repo's baseline): C0 reaches **62.5%** overall
  intent accuracy on semantic paraphrases (58.3% heldout); the
  failure mode is **`unknown` fallback** in every failure case.
- Axis 1 (this closeout): C0 reaches **87.5%** overall intent
  accuracy on constructed look-alike prompts (91.7% heldout); the
  failure mode is **`wrong_adjacent_intent`** in 3/24 cases, with
  zero `unknown` fallback.

These are diagnostic, not benchmark, numbers — case selection in
Axis 1 deliberately probes specific heuristic guards in `intent.py`
and is not a measure of operator-population performance.

## 3. Method

- **24 cases, 12 dev / 12 heldout** via an explicit `split` column.
- **4 confusion bands × 6 cases (3 dev + 3 heldout)**:
  - `membership_vs_new_customer_assignment` — STRUCT family, gold
    = `single_customer_route_membership`, attractor =
    `new_customer_assignment` (via `_NEW_ORDER_TOKENS`).
  - `lateness_vs_feasibility_status` — SCHEDULE family, gold =
    `lateness_summary`, attractor = `feasibility_status`
    (cross-family attractor).
  - `route_listing_vs_route_end_time` — STRUCT family, gold =
    `full_route_listing` (3 cases) or `single_customer_route_membership`
    (3 cases), attractor = `route_end_time` (cross-family attractor
    via completion tokens).
  - `comparison_vs_status_or_objective` — mixed family: OBJ
    objective_value (3 cases) with comparative attractor →
    `objective_delta`; PLAN_VALIDITY feasibility_status (3 cases)
    with comparative attractor → `before_after_comparison`.
- **C0 only.** Systems B and A are deferred — see §9.
- **No solver calls.** No optimization run, no feasibility check.
- **No `product/copilot/*` or `product/data/*` changes.** The
  deterministic contract layer at HEAD `18b4811` is the system
  under test, untouched.
- **No locked Run 2 files modified.** All seven protected files
  (`run2_benchmark_cases.csv`, `run2_gold_schema.md`,
  `run2_case_loader.py`, `run2_payloads.py`, `run2_scoring.py`,
  `run2_system_c.py`, `run2_calibration_cases.csv`) remain at the
  frozen baseline.
- **Cases inherit gold from existing Run 2 base cases.** Each
  stress row's `base_case_id` names the Run 2 case whose gold
  contract response is inherited verbatim. The loader enforces this
  inheritance per row (see `loader.validate_lookalike_case`).
- **Payloads materialize from Run 1 seeds**
  (`run_id='full-run-v1'`) — identical to the locked benchmark.
- **Scoring reuses `run2_scoring.score_case`** unchanged.

Artefacts emitted at this closeout:

| Artefact | Path |
|---|---|
| Cases | `axis1_lookalike/cases.csv` (24 rows, 30 cols) |
| Loader | `axis1_lookalike/loader.py` |
| Runner | `axis1_lookalike/runner.py` |
| Per-case wide CSV | `axis1_lookalike/reports/c0_baseline.csv` |
| Per-case Markdown | `axis1_lookalike/reports/c0_baseline.md` |
| Shared scatter | `axis1_lookalike/reports/scatter.csv` (240 rows) |
| Closeout report | `axis1_lookalike/reports/axis1_closeout.md` (this file) |
| Tests | `tests/run2_stress/axis1_lookalike/test_axis1_lookalike.py` |

## 4. Results

### 4.1 Overall (n = 24)

| Metric | Value |
|---|---:|
| `intent_correct` | **87.5%** (21 / 24) |
| `answerability_correct` | 100.0% |
| `behavior_class_correct` | 100.0% |
| `evidence_precision` | 90.0% |
| `evidence_recall` | 100.0% |
| `warning_precision` | 100.0% |
| `warning_recall` | 100.0% |
| `missing_field_recall` | 100.0% |
| `useful_refusal_correct` | n/a (no gold cases of this class) |
| `partial_answer_correct` | n/a (no gold cases of this class) |

### 4.2 By split

| Split | n | intent_correct | answerability_correct | behavior_class_correct | evidence_precision |
|---|---:|---:|---:|---:|---:|
| dev | 12 | 83.3% | 100.0% | 100.0% | 88.3% |
| **heldout** | 12 | **91.7%** | 100.0% | 100.0% | 91.7% |
| overall | 24 | 87.5% | 100.0% | 100.0% | 90.0% |

(Heldout numerically beats dev because the dev split contains two
of the three OBJ comparative-attractor misroutes — A1D-11 and
A1D-12 — while the heldout split contains only one — A1H-11.)

### 4.3 By confusion band

| Band | n | intent_correct | bucket distribution |
|---|---:|---:|---|
| `membership_vs_new_customer_assignment` | 6 | **100.0%** | 6 guard_protected |
| `lateness_vs_feasibility_status` | 6 | **100.0%** | 6 guard_protected |
| `route_listing_vs_route_end_time` | 6 | **100.0%** | 6 guard_protected |
| **`comparison_vs_status_or_objective`** | 6 | **50.0%** | **3 wrong_adjacent_intent**, 3 downstream_mismatch |

The single band that exercises *intra-family* misrouting (OBJ
`objective_value` ↔ `objective_delta` via `_COMPARATIVE_TOKENS`) is
the band that misroutes; the three bands whose attractor crosses a
family boundary or fights a C0 guard rule do not misroute.

### 4.4 Conditional on intent correct (n = 21)

| Metric | Value |
|---|---:|
| `answerability_correct` | **100.0%** |
| `behavior_class_correct` | **100.0%** |
| `evidence_precision` | 97.1% |
| `evidence_recall` | **100.0%** |
| `warning_precision` | **100.0%** |
| `warning_recall` | **100.0%** |
| `missing_field_recall` | **100.0%** |

`evidence_precision` is 97.1% rather than 100% because the three
PLAN_VALIDITY band-4 cases (gold = `feasibility_status`) exhibit
the same off-by-one precision behaviour documented in Axis 3 §3.4:
the gold lists 4 feasibility evidence paths and System C emits 5
(adding `infeasibility_kind`). This is a property of the base
contract, **not** an Axis 1 stress effect, and the stress paraphrase
does not change it.

## 5. Failure taxonomy

The 24 cases fall into the four mutually-exclusive buckets defined
in `design.md` §8:

| Bucket | n | What it means |
|---|---:|---|
| `wrong_adjacent_intent` | **3** | pred is a known intent ≠ gold, ≠ `unknown`. Confident misroute. |
| `unknown_intent` | **0** | pred = `unknown`. (Axis 3's failure mode.) |
| `downstream_mismatch` | 3 | intent correct, but a downstream metric is imperfect. |
| `guard_protected` | 18 | intent correct **and** every downstream metric is perfect — the C0 guard rules held under attractor pressure. |

### 5.1 wrong_adjacent_intent (n = 3, all in Band 4 / OBJ-gold)

| case_id | split | prompt | gold | pred | attractor token(s) |
|---|---|---|---|---|---|
| A1D-11 | dev | "What's the total cost on this plan — has anything actually changed in the report format?" | `objective_value` | `objective_delta` | `actually change` |
| A1D-12 | dev | "What's the total cost on this plan now, compared with the rate card we use internally?" | `objective_value` | `objective_delta` | `compared` |
| A1H-11 | heldout | "What does this plan end up costing — still a single total, right?" | `objective_value` | `objective_delta` | `still` |

**Mechanism.** In `intent.py`, family `OBJ` routes to
`objective_delta` whenever any token in `_COMPARATIVE_TOKENS` =
`("changed", "change", "actually change", "still", "compared",
"different")` appears in the lowered prompt (or the regex
`\b(fewer|more|less)\s+\w+\s+than\b` matches). The three cases
above each contain exactly one of those tokens used in a
**non-load-bearing** way — the operator wants the current cost; the
comparative phrase is appositional or rhetorical. C0 confidently
misroutes to `objective_delta`.

**Downstream consequence.** Each misroute is scored as a wrong
intent (intent_correct = False) but **does** pass downstream
`answerability_correct` and `behavior_class_correct` (both 100%
across the three wrong-intent cases) because the OBJ payload
carries both `objective_value` and `baseline_objective`, so System
C can produce an `answerable`/`direct_answer` for either intent.
`evidence_precision` drops to 0.4 on each (predicted set includes
delta-specific paths that gold does not). The contract pipeline
**does not warn** the operator about the misroute — the response
looks like a normal direct answer for a question the operator did
not ask. This is the dangerous failure mode Axis 1 was designed to
expose.

### 5.2 unknown_intent (n = 0)

No case in Axis 1 returned `unknown`. This is the key
distinguishing feature from Axis 3 (where every failure was an
`unknown` fallback).

### 5.3 downstream_mismatch (n = 3, all in Band 4 / PLAN_VALIDITY-gold)

| case_id | split | prompt | gold intent | pred intent | ev_prec |
|---|---|---|---|---|---:|
| A1D-10 | dev | "Compared with what's typical, is the plan still feasible after the time windows got tighter?" | `feasibility_status` | `feasibility_status` | 0.80 |
| A1H-10 | heldout | "Compared to nothing else, is the plan still able to handle the deliveries after travel times went up 20%?" | `feasibility_status` | `feasibility_status` | 0.80 |
| A1H-12 | heldout | "Have things changed feasibility-wise after the new customers were added — can the routes handle them all and is anything different?" | `feasibility_status` | `feasibility_status` | 0.80 |

These three cases have **correct intent** but `evidence_precision =
0.8` for the off-by-one `infeasibility_kind` reason explained in
§4.4 and Axis 3 §3.4. They are not a stress finding; the same off-
by-one is visible on the locked Run 2 PLAN_VALIDITY cases (e.g.
R2-028..R2-031) under clean evaluation.

### 5.4 guard_protected (n = 18)

| Band | n | Why the guard held |
|---|---:|---|
| `membership_vs_new_customer_assignment` | 6 | `_is_about_new_customer_assignment` is blocked by the **customer-number guard** (`_has_specific_customer_number` returns True on every case's "customer 12" / "customer 17" / "customer 42" reference). The classifier falls through to STRUCT-family membership routing on the `which route` / `what route` / customer-number hook. |
| `lateness_vs_feasibility_status` | 6 | `feasibility_status` is only reachable from `family=PLAN_VALIDITY`; every case in this band is `family=SCHEDULE`, so the attractor cannot reach its target intent. Each case preserves a lateness token (`late`, `delivery window`, `miss`) that anchors the SCHEDULE branch's lateness check (which runs before `is_comparative`). |
| `route_listing_vs_route_end_time` | 6 | Two protections combined: (a) `_FULL_ROUTE_LISTING_PHRASES` precedes the family branches and fires on three cases' listing phrases (`each route`, `customers on each`, `customers per`); (b) the remaining three STRUCT-membership cases are anchored by the `which route` / `what route` hook and the specific customer-number trigger inside the STRUCT branch. `route_end_time` is unreachable from `family=STRUCT`. |

These 18 cases are a **positive finding** about C0's robustness:
under heavy look-alike pressure, the existing guard rules in
`intent.py` correctly prevent the named attractor misroute. The
implication for System D is recorded in §7.

## 6. Methodological interpretation

The Axis 1 results tell a precise story about C0's intent
classifier:

- **C0 confidently misroutes on intra-family comparative attractor
  language in OBJ.** Three of the three OBJ `objective_value`
  cases with a comparative token rerouted to `objective_delta`.
  This is the only band that exercised *intra-family* attractor
  pressure (because `objective_value` and `objective_delta` are
  both in family OBJ and the `is_comparative` switch decides
  between them on surface tokens alone). The 100% misroute rate
  on the OBJ subset is a confident, reproducible failure of C0's
  comparative-token heuristic to distinguish *load-bearing* from
  *incidental* comparative language.

- **C0's family-routing architecture entirely prevents the
  cross-family look-alikes the user's spec named.** Bands 2 and 4
  (PLAN_VALIDITY subset) and band 3 each carry attractor surface
  for an intent in a *different* family. Because C0 takes family
  as a given input (from the locked Run 2 case row) rather than
  predicting it from the prompt, surface tokens for the wrong
  family never reach the wrong-family heuristics. This is a
  structural, not heuristic, protection.

- **C0's guard rules within a family hold under heavy pressure.**
  The `_NEW_ORDER_TOKENS` customer-number guard (Band 1) and the
  `_FULL_ROUTE_LISTING_PHRASES` / customer-number anchors
  (Band 3) prevented every attempted misroute in those bands. The
  bands successfully push hard at the guards (every case carries
  the attractor's keyword pair); the guards still held.

- **Downstream contract behaviour conditional on correct intent
  remains identical to Run 2.** Among the 21 intent-correct cases,
  answerability is 100% and behaviour class is 100%; evidence
  precision is 97.1% (the documented PLAN_VALIDITY off-by-one).
  This mirrors Axis 3 §3.4: the deterministic contract layer is
  not the bottleneck.

- **No claim of broad generalization.** The 24-case split is
  diagnostic, not population-level. A 91.7% heldout intent
  accuracy is a measurement at one tag, against one set of
  intentionally-chosen attractors, against one classifier
  implementation. The point of axis 1 is the **failure
  taxonomy**, not the accuracy headline.

- **Axis 1 successfully isolated look-alike misrouting in one of
  four bands.** Band 4 (comparative attractor, OBJ subset) exposed
  the confident-misroute failure mode the axis was designed for.
  Bands 1, 2, 3 produced no misroutes — that is not a failure of
  the axis; it is a precise localization of where C0's existing
  defences hold and where they do not. The closeout reports the
  band-level result faithfully.

## 7. System D implication

System D's locked scope (`shared/system_d_design_envelope.md`) is
"modify `product/copilot/intent.py` only". Axis 1's findings map
onto that envelope cleanly:

- **Targeted improvement.** The `wrong_adjacent_intent` failures
  all derive from `_COMPARATIVE_TOKENS` firing on
  non-load-bearing surface uses ("compared with the rate card",
  "still a single total, right?", "actually changed in the report
  format"). A System D semantic-intent layer can disambiguate by
  reading the comparative phrase's *referent* — does the
  comparator refer to a payload field (load-bearing → delta) or
  to an external/incidental concept (non-load-bearing →
  value)? — and is structurally able to do so within the locked
  intent.py scope.

- **Do not strip the guards.** The 18 `guard_protected` cases
  prove that C0's existing guard rules — the customer-number
  guard inside `_is_about_new_customer_assignment`, the
  `_FULL_ROUTE_LISTING_PHRASES` precedence, the
  customer-number / `which route` STRUCT anchors, the family-
  routing architecture — successfully suppress the look-alike
  misroutes those bands try to trigger. System D MUST preserve
  these guards (either by carrying their semantics into the
  semantic-intent layer or by leaving the keyword classifier in
  place as a fallback).

- **No envelope widening needed.** Axis 1 produced zero
  `downstream_mismatch` cases attributable to the stress (the 3
  downstream_mismatch cases are the documented PLAN_VALIDITY
  evidence off-by-one). The deterministic contract layer is not
  the bottleneck under look-alike pressure; System D does not
  need to touch answerability, evidence, refusal policy, or
  entity resolution. The locked envelope is sufficient.

- **Failure-mode taxonomy for System D's pre-registered
  prediction table.** Combined with Axis 3's `unknown` failures,
  System D's pre-registered prediction now has two concrete
  targets: (a) cut the 9 Axis-3 `unknown` failures (vocabulary
  brittleness), and (b) cut the 3 Axis-1 `wrong_adjacent_intent`
  failures (comparative-referent disambiguation). The 18
  Axis-1 `guard_protected` cases plus the 15 Axis-3 intent-
  correct cases form the "must not regress" cohort.

## 8. Status

**Axis 1 is closed for the C0 baseline.** The 24 cases at HEAD
`18b4811` are the baseline of record. The `dev` split (12 cases)
may be consumed for System D iteration; the `heldout` split
(12 cases) is sequestered until the System D freeze tag.

## 9. Deferred (not part of this closeout)

- **System B / System A on Axis 1.** Wiring exists in
  `axis1_lookalike/runner.py` as `run_system_b_stub` /
  `run_system_a_stub` (typed `NotImplementedError`). Running them
  requires the OpenAI API key already used by Run 2 model
  baselines. Skipped per task scope.
- **System D itself.** Not built at this closeout. Building it
  is conditional on at least one R2-S axis having a C0 baseline at
  the frozen tag; Axis 1 and Axis 3 now both supply that.
- **Cross-axis joint analysis.** The shared scatter file is
  emitted; `analysis/concat_scatter.py` can already read it. The
  joint analysis report (Axes 1, 3, and eventually 2 / 4) is
  authored separately.
- **Guard-rule sensitivity sweep.** A natural follow-up axis would
  drop one C0 guard at a time and re-score Axis 1 to attribute
  guard-strength magnitudes. That is an Axis-1-derived future
  axis, not part of this closeout.
- **Band-4 OBJ-subset expansion.** The OBJ comparative attractor
  fires every time at present. A larger OBJ-only sub-axis would
  let System D's improvement curve be measured precisely; that
  is a future axis, not part of this closeout.

## 10. Recommended next axis

Axis 1 is closed. The natural next axis for the R2-S sequence is
**`axis2_ood_premises/`** — false premises, missing comparators,
unsupported baselines. Axis 2 tests a different layer of the
contract (refusal / partial-answer logic) rather than the front-
door classifier, which gives the cross-axis joint analysis a
third orthogonal probe. The shared methodology (scatter schema,
metric vocabulary, System D envelope) is in place to support it.

`axis4_payload/` is also defensible — context-scale stress on
known-correct intents — but does not directly inform the System D
intent-classification design that Axes 1 and 3 set up.

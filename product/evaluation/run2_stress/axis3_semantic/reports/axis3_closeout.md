# R2-S Axis 3 Closeout — Semantic Intent / Paraphrase Stress

_Status: **CLOSED for C0 baseline.** Frozen at HEAD `18b4811`
("Run 2 contract extensions completed"). Closeout authored
2026-05-20 under the shared methodology in
`product/evaluation/run2_stress/shared/`._

## 1. Purpose

Axis 3 tests whether the VRPTW copilot maps **semantically
equivalent operator phrasings** to the correct canonical intent
while preserving the same payload answerability as a known
supported Run 2 prompt. The cases are paraphrases of Run 2 base
cases; the gold contract response (answerability, evidence,
warnings, next actions, behavior class) is inherited verbatim from
the base case. The only thing the stress changes is the **prompt
text**.

The axis isolates the **language-to-intent mapping** failure mode
from every other layer of the contract. It is not a benchmark
replacement and not a user study; it is a diagnostic stress split
sized to probe known gaps in the keyword classifier without
exhausting reviewer attention.

Under the shared `axis_naming.md` (Path B, see §3 of
`shared/coordination_report.md`), axis 3 is the **paraphrase**
axis. Axis 1 will later cover *constructed* look-alike intent
confusion — different failure mode, different cases.

## 2. Method

- **24 stress cases**, split **12 dev / 12 heldout** via an
  explicit `split` column. No random sampling.
- **C0 only** for this closeout. Systems B and A are deferred —
  see §9.
- **No solver calls.** No optimization run; no feasibility check.
- **No `product/copilot/*` or `product/data/*` changes.**
  The deterministic contract layer at HEAD `18b4811` is the
  system under test, untouched.
- **No locked Run 2 files modified.** `run2_benchmark_cases.csv`,
  `run2_gold_schema.md`, `run2_case_loader.py`, `run2_payloads.py`,
  `run2_scoring.py`, `run2_system_c.py`, and
  `run2_calibration_cases.csv` are all at the frozen baseline.
- **Cases inherit gold from existing Run 2 base cases.** Each
  stress row's `base_case_id` column names the Run 2 case whose
  gold contract response (answerability, evidence, missing fields,
  warnings, next actions, behavior class) the stress row inherits
  verbatim. The loader enforces this inheritance per row.
- **Payloads materialize from Run 1 seeds.** The same path the
  locked benchmark uses (`run2_payloads.materialize_case_payload`,
  `run_id='full-run-v1'`) — no synthetic payloads.
- **Scoring reuses `run2_scoring.score_case`** unchanged.

Artefacts emitted at this closeout:

- `reports/c0_baseline.csv` — per-case wide-form results.
- `reports/c0_baseline.md` — human-readable Markdown summary.
- `reports/scatter.csv` — long-form per-case scatter conforming
  to `shared/scatter_schema.md`. 240 rows = 24 cases × 10 metrics.
  48 null-score rows = 24 cases × 2 inapplicable metrics
  (`useful_refusal_correct`, `partial_answer_correct` — no axis 3
  case has gold of those behavior classes).

## 3. Results

### 3.1 Overall (n = 24)

| Metric | Value |
|---|---:|
| `intent_correct` | **62.5%** (15 / 24) |
| `answerability_correct` | 62.5% |
| `behavior_class_correct` | 62.5% |
| `evidence_precision` | 59.2% |
| `evidence_recall` | 62.5% |
| `warning_precision` | 87.5% |
| `warning_recall` | 87.5% |
| `missing_field_recall` | 100.0% |
| `useful_refusal_correct` | n/a (no gold cases of this class) |
| `partial_answer_correct` | n/a (no gold cases of this class) |

### 3.2 By split

| Split | n | intent_correct | answerability_correct | behavior_class_correct | evidence_recall | warning_precision |
|---|---:|---:|---:|---:|---:|---:|
| dev | 12 | 66.7% | 66.7% | 66.7% | 66.7% | 83.3% |
| **heldout** | 12 | **58.3%** | 58.3% | 58.3% | 58.3% | 91.7% |
| overall | 24 | 62.5% | 62.5% | 62.5% | 62.5% | 87.5% |

### 3.3 By stress_subtype

| Subtype | n | intent_correct | evidence_recall | warning_precision |
|---|---:|---:|---:|---:|
| `cost_synonym` | 3 | 100.0% | 100.0% | 100.0% |
| `feasibility_synonym` | 4 | 100.0% | 100.0% | 100.0% |
| `entity_synonym` | 5 | 80.0% | 80.0% | 100.0% |
| `operator_colloquial` | 2 | 50.0% | 50.0% | 100.0% |
| `paraphrase` | 2 | 0.0% | 0.0% | 100.0% |
| `schedule_synonym` | 8 | 37.5% | 37.5% | 62.5% |

`schedule_synonym` is the weakest band: 5 of 8 cases miss the
intent because the SCHEDULE matcher in `intent.py` requires both
"route" in the prompt **and** a specific token from a small set
(`wrap up` / `end time` / `finish` / `complete`). Stress prompts
that say `vehicle 1` / `truck 1` / `close out` / `done for the
day` fail one or both halves of that conjunction.

### 3.4 Conditional on intent correct (n = 15)

| Metric | Value |
|---|---:|
| `answerability_correct` | **100.0%** |
| `behavior_class_correct` | **100.0%** |
| `evidence_precision` | 94.7% |
| `evidence_recall` | **100.0%** |
| `warning_precision` | **100.0%** |
| `warning_recall` | **100.0%** |
| `missing_field_recall` | **100.0%** |

`evidence_precision` is 94.7% rather than 100% because the
PLAN_VALIDITY cases (R2-028 / R2-029 / R2-030 / R2-031 gold)
expect 4 feasibility evidence paths and the contract emits 5
(adding `infeasibility_kind`). This is **not** an axis 3 stress
effect — the base cases exhibit the same off-by-one precision
behavior under their own clean evaluation. The stress paraphrase
does not change it.

## 4. Central finding

C0's overall performance drops under semantic paraphrase stress
because the front-door intent classifier often maps unseen
phrasing to `unknown`. However, **conditional on correct intent
resolution, the downstream deterministic contract remains
stable**: answerability, behavior class, evidence recall, and
warnings are correct. This isolates the main bottleneck to
**semantic intent mapping** rather than answerability / evidence /
refusal logic.

In other words: when the keyword classifier *does* fire, the rest
of the contract performs as it does on the locked Run 2 benchmark.
When the classifier *fails to fire*, the entire downstream
pipeline degrades gracefully into a useful-refusal-shaped output
(not a wrong answer) — but the operator still does not get the
answer they asked for.

## 5. Failure modes

Three failure families account for all 9 misclassified cases:

### 5.1 `route_end_time` vocabulary gaps (4 cases)

Stress prompts that name a route by integer but use a verb the
matcher does not know:

- "When does vehicle 1 close out?" (S1D-08)
- "When is vehicle 1 finished?" (S1D-09)
- "At what time is route 1 done for the day?" (S1H-09)
- "When does truck 1 complete its run?" (S1H-10)

The `intent.py` SCHEDULE branch requires (a) one of `wrap up` /
`end time` / `finish` / `complete` **and** (b) the literal word
`route` somewhere in the prompt. Each case violates one or both
clauses; the matcher returns `unknown`.

### 5.2 `full_route_listing` phrase gaps (3 cases)

Stress prompts that ask for a per-route roster using novel
surface forms:

- "Give me the full set of vehicle runs." (S1D-07)
- "Show me every route in the plan." (S1H-07)
- "List the complete route plan." (S1H-08)

`intent.py` matches `full_route_listing` only against an
enumerated phrase set (`each route`, `each vehicle`,
`list the customers`, etc.). The three prompts above use none of
those phrases, so the STRUCT branch falls through to `unknown`.

### 5.3 `lateness_summary` vocabulary gaps (2 cases)

Stress prompts that describe lateness in operator language the
matcher's token set does not include:

- "Which customers fall behind schedule?" (S1D-12)
- "Are any stops served after their allowed time?" (S1H-12)

The lateness token set is `late` / `delivery window` / `on time` /
`delayed` / `lateness` / `miss`. "Behind schedule" and "after
their allowed time" miss every token.

## 6. Methodological interpretation

- **C0's Run 2 perfection is not natural-language robustness.**
  C0 scores 100% on the locked 60-case benchmark because the
  benchmark prompts were authored alongside the keyword matcher.
  Axis 3 reveals that the matcher's coverage is template-bound:
  it does well on the surface forms it was authored against and
  degrades sharply on any surface form it was not.
- **The deterministic contract remains a strong foundation.** Once
  intent is canonicalized correctly, every downstream layer
  (answerability, evidence, missing-field, warnings, refusal)
  behaves exactly as it does on Run 2 — see §3.4.
- **This motivates System D as a semantic intent adapter** in
  front of the deterministic contract. System D's job is to
  canonicalize "When does vehicle 1 close out?" into
  `intent=route_end_time` and hand off to the existing contract;
  it does **not** modify the contract. The
  `shared/system_d_design_envelope.md` document pre-commits this
  single-architectural-change discipline.
- **No claim of broad generalization.** The 12-case heldout
  deliberately targets known gaps; a 58.3% heldout score is a
  diagnostic baseline, not a measure of operator-population
  performance. The next system (D) will be evaluated on the same
  fixed 12 cases at a fixed tag; the comparison is what carries
  the claim, not the absolute number.
- **Not a user study, not solver validation, not a Run 2
  replacement.** Axis 3 measures one thing — language-to-intent
  mapping under paraphrase — and is sized accordingly.

## 7. Status

**Axis 3 is closed for the C0 baseline.** The 24 cases at HEAD
`18b4811` are the baseline of record. The `dev` split (12 cases)
may be consumed for System D iteration; the `heldout` split
(12 cases) is sequestered until the System D freeze tag.

Closeout artefacts:

| Artefact | Path |
|---|---|
| Cases | `axis3_semantic/cases.csv` |
| Loader | `axis3_semantic/loader.py` |
| Runner | `axis3_semantic/runner.py` |
| Per-case wide CSV | `axis3_semantic/reports/c0_baseline.csv` |
| Per-case Markdown | `axis3_semantic/reports/c0_baseline.md` |
| Shared scatter | `axis3_semantic/reports/scatter.csv` (240 rows) |
| Closeout report | `axis3_semantic/reports/axis3_closeout.md` (this file) |
| Tests | `tests/run2_stress/axis3_semantic/test_axis3_semantic.py` |

## 8. Next recommended axis

Axis 3 is closed; the natural next axis for the R2-S sequence is
either:

- **`axis1_lookalike/`** — *constructed* look-alike intent
  confusion. Prompts engineered so the keyword classifier
  actively reroutes to an adjacent wrong intent (e.g.
  "Where is customer 42 going next?" firing the
  `_NEW_ORDER_TOKENS` heuristic toward `new_customer_assignment`
  when the operator wants `single_customer_route_membership`).
  Where axis 3 measures "unseen vocabulary → unknown intent",
  axis 1 measures "seen vocabulary → wrong intent." The pair
  characterises the front-door classifier's two failure modes.
- **`axis2_ood_premises/`** — false premises, missing
  comparators, unsupported baselines. This pairs with the
  contract's refusal / partial-answer logic and tests a different
  layer of the contract from axis 3.

Either ordering is defensible. The shared methodology (scatter
schema, metric vocabulary, System D envelope) is in place to
support whichever axis lands next.

**Not in scope for this closeout.** No axis 1 or axis 2 case is
authored here. Building System D is also out of scope at this
closeout — it should wait until at least one of axis 1 / axis 2
has a C0 baseline, so the System D pre-registered prediction
table can name failure-mode targets beyond the axis 3 "unknown"
mode that already has a baseline.

## 9. Deferred (not part of this closeout)

- **System B / System A on axis 3.** Wiring exists in
  `axis3_semantic/runner.py` as `run_system_b_stub` /
  `run_system_a_stub` (typed `NotImplementedError`). Running them
  requires the OpenAI API key already used by Run 2 model
  baselines. Skipped per task scope.
- **Cross-axis joint analysis.** The shared scatter file is now
  emitted; `analysis/concat_scatter.py` can read it. The joint
  report itself is authored after axis 1 / 2 / 4 also emit shared
  scatter.

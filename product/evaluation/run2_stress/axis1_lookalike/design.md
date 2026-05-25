# R2-S Axis 1 — Look-alike Intent Stress (design)

_Frozen-baseline commit: HEAD `18b4811` ("Run 2 contract extensions
completed"). All numbers below are reproducible at that tag._

## 1. Axis definition

Axis 1 (`axis1_lookalike/`) is the stress split that probes
**confident misrouting** by the System C0 keyword-based intent
classifier. Each case is a prompt whose semantically intended intent
is supported and clear, but whose surface tokens contain a lexical
attractor for a **different** supported intent that the matcher in
`product/copilot/intent.py` has explicit rules for.

The cross-axis boundary rule (`shared/axis_naming.md` §1, §2) makes
the partition explicit:

- Axis 3 = "unseen vocabulary → unknown intent" (paraphrase
  brittleness).
- Axis 1 = "familiar attractor vocabulary → wrong adjacent intent"
  (constructed look-alike confusion).

Axis 1 cases inherit gold contract responses verbatim from the named
Run 2 base case; only `prompt_text` changes between the base case
and the stress row.

## 2. Hypothesis (H-A1)

H-A1 (informal): The C0 keyword classifier will, on at least some
look-alike prompts, return a **supported wrong intent** rather than
`unknown`. This is more dangerous than Axis 3's "unknown fallback"
because it can produce a plausible-but-wrong contract response
without warning the operator.

Expected diagnostic outcomes:

1. Some non-zero count of cases where `predicted_intent` is a known
   `Intent` enum value that is **not** the gold intent (the
   confident-misroute family).
2. Some cases where `predicted_intent` is `unknown` — surface
   tokens not handled by any heuristic and not handled by the gold
   intent's matcher either.
3. Conditional on correct intent, downstream contract metrics
   (answerability, behavior class, evidence) should remain
   essentially equal to Axis 3's `intent_correct only` row —
   indicating the downstream contract layer itself is not the
   bottleneck.
4. Some cases where C0's guard rules (specifically the
   customer-number guard inside `_is_about_new_customer_assignment`
   and the family-level routing for PLAN_VALIDITY) **prevent** the
   look-alike misroute despite attractor language. These are
   positive findings about C0's robustness; we explicitly report
   them as a separate "guard-protected" cohort in the closeout.

## 3. Exclusion criteria (what Axis 1 is NOT)

Axis 1 must not include:

- **Unsupported customer or route IDs** in the prompt (those belong
  to Axis 2's false-premise cohort).
- **Missing baselines, missing comparators, unsupported comparison
  referents** (Axis 2).
- **Vague decomposition prompts** with no clear supported intent.
- **Pure paraphrases** that simply use vocabulary the matcher was
  not authored against (those belong in Axis 3 under the Path B
  boundary rule).
- **Large-payload pressure** (Axis 4).

If a candidate prompt fits two axes, the table in
`shared/axis_naming.md` §2 resolves ownership:

| Combination | Owner |
|---|---|
| Constructed lookalike (any other stressor absent) | **Axis 1** |
| Constructed lookalike AND semantic paraphrase | **Axis 1** |
| Constructed lookalike AND false premise | Axis 2 |
| Constructed lookalike AND large payload | Axis 4 |

## 4. Case construction protocol

For every Axis 1 case:

1. **Pick a Run 2 base case** with a gold intent compatible with
   the band's intended attractor pair.
2. **Inherit verbatim**: `source_prompt_id`, `family`,
   `payload_condition`, `payload_mutation_needed`,
   `expected_intent`, `expected_answerability`,
   `expected_evidence_paths`, `expected_missing_fields`,
   `expected_warnings`, `expected_next_actions`,
   `expected_behavior_class`, `implementation_status`. The stress
   loader enforces this inheritance per row at validation time.
3. **Author a stress `prompt_text`** that (a) preserves the
   operator's semantic intent (gold), (b) embeds at least one
   surface-token attractor for the named wrong intent
   (`attractor_intent`), and (c) keeps every customer ID / route
   label / payload reference inside the base payload (no
   false-premise mutations).
4. **Record the attractor tokens** in the `attractor_tokens`
   column. These are the specific lexical hooks that the case
   exercises against `intent.py`; the closeout reports per-case
   whether each token's heuristic actually fired.
5. **Record `paraphrase_notes`** explaining how the stress
   surface diverges from the canonical Run 2 prompt and **why**
   the gold intent remains the operator's intended answer.
6. **Cap `difficulty` at `medium`** — Axis 1 deliberately probes
   classifier robustness, not gold-row depth.

## 5. Confusion bands (4)

The 24 cases are partitioned into 4 confusion bands (`band` =
`confusion_pair`), 6 cases each, with 3 dev and 3 heldout per band.

### Band 1 — `membership_vs_new_customer_assignment`

| | |
|---|---|
| Gold intent | `single_customer_route_membership` |
| Attractor intent | `new_customer_assignment` |
| Family | STRUCT |
| Attractor tokens | `new customer`, `new order`, `added customer`, `newly assigned`, `newly added`, `inserted` |
| Mechanism under C0 | `_is_about_new_customer_assignment` requires `_NEW_ORDER_TOKENS` ∈ {"new customer", "new order", "added customer"} AND the prompt to lack both a specific route number and a specific customer number AND lack "the driver". Each case in this band carries a real customer number; we expect the customer-number **guard** to block the attractor, falling through to STRUCT-family membership routing. The band's primary diagnostic is therefore "does the guard hold under heavy look-alike pressure?" — and where it does, the case lands in the `guard_protected` cohort defined in §8. |

### Band 2 — `lateness_vs_feasibility_status`

| | |
|---|---|
| Gold intent | `lateness_summary` |
| Attractor intent | `feasibility_status` |
| Family | SCHEDULE |
| Attractor tokens | `feasible`, `valid`, `validity`, `violate`, `constraint`, `infeasible` |
| Mechanism under C0 | `feasibility_status` is **only** reachable from `family=PLAN_VALIDITY`; in `family=SCHEDULE` the matcher routes by SCHEDULE-internal tokens (arrival > route_end_time > lateness > comparative). The band tests whether SCHEDULE-family lateness prompts laced with feasibility surface tokens nonetheless route correctly. Under the family-routing architecture this band cannot directly misroute to `feasibility_status`; the realistic failure mode is **lateness → unknown** when the lateness token is removed by the paraphrase. The closeout reports the resulting unknown-fallback rate explicitly. |

### Band 3 — `route_listing_vs_route_end_time`

| | |
|---|---|
| Gold intent | `full_route_listing` or `single_customer_route_membership` |
| Attractor intent | `route_end_time` |
| Family | STRUCT |
| Attractor tokens | `complete`, `finish`, `finished`, `full`, `end-to-end`, `route` |
| Mechanism under C0 | `route_end_time` is **only** reachable from `family=SCHEDULE`; in `family=STRUCT` completion-flavoured tokens are not in any heuristic. The realistic failure mode is therefore **listing/membership → unknown** when the surface form lacks the `_FULL_ROUTE_LISTING_PHRASES` triggers (`"each route"`, `"each vehicle"`, `"per route"`, `"per vehicle"`, `"customers on each"`, `"customers per"`, `"list the customers"`, etc.) and lacks a specific customer-number hook. Cases that preserve a listing phrase **or** carry a customer-number should classify correctly. |

### Band 4 — `comparison_vs_status_or_objective`

| | |
|---|---|
| Gold intent | `objective_value` or `feasibility_status` |
| Attractor intent | `objective_delta` or `before_after_comparison` |
| Family | OBJ (for objective_value) or PLAN_VALIDITY (for feasibility_status) |
| Attractor tokens | `changed`, `actually change`, `still`, `compared`, `different` (the `_COMPARATIVE_TOKENS` set in `intent.py`) |
| Mechanism under C0 | This is the band with the **most realistic confident-misroute potential**. In `family=OBJ`, the matcher routes to `objective_delta` iff any token in `_COMPARATIVE_TOKENS` appears OR the regex `\b(fewer|more|less)\s+\w+\s+than\b` matches; otherwise `objective_value`. Embedding a comparative token in an objective-value prompt is expected to actively reroute the classifier to `objective_delta` — a **wrong adjacent intent**, not unknown. In `family=PLAN_VALIDITY`, the family always returns `feasibility_status` and the attractor cannot misroute (parallel to Band 2's mechanism). |

### Why the user-named bands are kept verbatim

The user's specification names these four bands by their
**operator-intuitive** confusion pair. Under C0's actual mechanics,
the realistic misroute rate varies per band:

- **Band 4 (OBJ subset)** — exercises a real misroute via the
  `_COMPARATIVE_TOKENS` set; the surface attractor flips
  `objective_value` to `objective_delta`. Expected misroute count
  on the dev OBJ-gold cases: 2/3.
- **Band 1, Band 3** — exercise classifier **guards** (the
  customer-number guard in Band 1; the `_FULL_ROUTE_LISTING_PHRASES`
  precedence and specific-customer-number fallback in Band 3). The
  bands are designed to push hard against the guards; where the
  guards hold, the case lands in the `guard_protected` cohort. The
  closeout reports the guard-hold rate honestly.
- **Band 2, Band 4 (PLAN_VALIDITY subset)** — exercise the
  **family-routing architecture**: the attractor intent is in a
  different family, so the matcher cannot reach it under C0's
  family-given input. These cases are designed to confirm (or
  refute) that family routing prevents look-alike confusion
  entirely.

We keep the user's band names verbatim because (a) they encode the
operator's intuition about which intents are confusable, which is
the right vocabulary for the closeout's audience, and (b) the
mixed-mechanism design lets the closeout report the **full failure
taxonomy** — wrong-adjacent, unknown-fallback, guard-protected,
and downstream-mismatch — rather than only the confident-misroute
slice. This makes Axis 1's diagnostic value broader than a single
band would provide.

## 6. Split policy

24 cases split 12 dev / 12 heldout via an explicit `split` column.
Within each band, 3 dev cases and 3 heldout cases. No random
sampling; the case_id encodes the split (`A1D-NN` = dev,
`A1H-NN` = heldout).

Heldout discipline (mirrors Axis 3):

- Any future System D iteration on Axis 1 consumes the `dev` split
  only.
- A heldout score may be published once, at a tagged commit, after
  dev-side freeze.

## 7. Scoring policy

C0 baseline scoring reuses `product.evaluation.run2_scoring.score_case`
unchanged. The 10 canonical metric names from
`shared/metric_names.md` are the entire output vocabulary; the
runner emits both the wider per-case CSV (`reports/c0_baseline.csv`)
and the shared long-form scatter (`reports/scatter.csv`).

Per-case shared-scatter conventions for Axis 1:

| Column | Value |
|---|---|
| `axis` | `axis1_lookalike` |
| `system` | `c0` |
| `band` | the case's `confusion_pair` (one of the four band labels above) |
| `intent` | the case's `expected_intent` (gold) |
| `n_routes` | from the materialized payload (`len(payload["routes"])`) when present, else null |
| `payload_chars` | `len(json.dumps(payload, sort_keys=True))` when present, else null |

Conditional metrics (`useful_refusal_correct`, `partial_answer_correct`)
emit a `null`-score row when the case's gold behavior class does not
match — see `metric_names.md` §3.

## 8. Expected failure taxonomy

The Axis 1 closeout reports each case into exactly one of the four
buckets below. The buckets are mutually exclusive and exhaustive
across all 24 cases.

1. **wrong_adjacent_intent**: `predicted_intent` is a known
   `Intent` enum value, is **not** the gold intent, and is **not**
   `unknown`. The classifier confidently chose a neighbouring
   wrong intent. This is the primary Axis 1 failure mode.
2. **unknown_intent**: `predicted_intent == "unknown"`. The
   matcher fell through to its catch-all branch. Same failure
   mode shape as Axis 3.
3. **guard_protected (correct intent under attractor pressure)**:
   `predicted_intent == expected_intent` despite the case's
   `attractor_tokens` being present in the prompt. The classifier
   guard (customer-number, listing-phrase precedence, family
   routing) blocked the look-alike misroute. This is a **positive
   finding about C0**; it tells us where System D can rely on the
   existing guards rather than re-implement them.
4. **downstream_mismatch**: `predicted_intent == expected_intent`
   but at least one of `answerability_correct`,
   `behavior_class_correct`, or the evidence/warning/missing
   metrics is False. The classifier was right but the rest of
   the contract pipeline disagreed with gold. We expect this
   bucket to mirror the conditional-on-intent-correct profile
   from Axis 3 (i.e. essentially empty modulo the
   PLAN_VALIDITY evidence-precision off-by-one).

Buckets 1+2 are "intent wrong"; buckets 3+4 are "intent right".

## 9. System D scope note

System D's allowed scope is locked by
`shared/system_d_design_envelope.md`: System D **only** modifies
`product/copilot/intent.py`. It does not touch answerability,
evidence, refusal policy, or entity resolution.

The implications for Axis 1:

- If Axis 1 failures concentrate in **wrong_adjacent_intent** or
  **unknown_intent**, System D can address them within the locked
  scope — those are intent-classification failures.
- If Axis 1 failures appear in **downstream_mismatch**, System D
  **cannot** address them; they would require widening the
  envelope. The closeout flags this case explicitly.
- If failures concentrate in **guard_protected** (i.e. the bucket
  is large), that's the inverse of a failure: the existing C0
  matcher is robust against the look-alike pressure under test
  and System D should preserve the guards. The closeout records
  this as a guardrail for System D's design (do not strip the
  `_NEW_ORDER_TOKENS` customer-number guard; do not loosen
  `_FULL_ROUTE_LISTING_PHRASES` precedence).

## 10. Out-of-scope (future work)

- **Systems B / A on Axis 1.** Wiring exists as
  `runner.run_system_b_stub` / `runner.run_system_a_stub` (typed
  `NotImplementedError`). Running them requires an OpenAI API key
  used by Run 2 model baselines and is deferred per task scope.
- **System D itself.** The semantic intent classifier is not built
  here. Building it is conditional on at least one R2-S axis
  having a C0 baseline at the frozen tag; Axis 1 and Axis 3 now
  both supply that.
- **Cross-axis joint analysis.** The scatter file is emitted in
  shared-schema shape; `analysis/concat_scatter.py` can already
  pick it up. The joint analysis report is written after Axis 2
  and Axis 4 also land.
- **Guard-rule sensitivity sweep.** Several Axis 1 findings depend
  on the specific guard rules in `intent.py` at HEAD `18b4811`. A
  follow-up sensitivity study (e.g. "what if we drop the
  customer-number guard?") is an Axis-1-derived future axis, not
  part of this closeout.

## 11. Frozen-baseline commit

All numbers in `reports/c0_baseline.{csv,md}`, `reports/scatter.csv`,
and `reports/axis1_closeout.md` are computed at HEAD `18b4811`. The
runner emits a warning (non-fatal) if HEAD differs; the warning is
copied into the report's caveats section so any reader can detect
drift.

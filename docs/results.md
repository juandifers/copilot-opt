# Results

## TL;DR

On a 109-query operator corpus, enabling the LLM semantic adapter lifts the
share of useful answers from **40% (deterministic baseline)** to **62% (full
pipeline)**. On the 62 queries where the LLM changed the outcome, it helped
24 and hurt 3. A separate 60-case reliability benchmark shows pass@k climbing
as control moves from the LLM to the contract pipeline (0.30 → 0.50 → 1.00).
Sample sizes are small enough that we read directions and asymmetries; we do
not claim statistical significance.

## The question this evaluation answers

The architecture is built around a hypothesis: an LLM placed in front of a
deterministic copilot, restricted to producing only an intent and entity
references, should *increase* useful-answer rate without raising wrong-answer
rate. The evaluation is structured to test that. Concretely:

1. Does the LLM add genuine value over a deterministic-only path, on a corpus
   that mirrors how operators actually phrase questions?
2. When the LLM changes the answer, how often does it help vs. hurt?
3. Does the system's reliability survive the LLM's noise, measured as pass@k
   across resamples?

## Evaluation design

**Operator corpus.** 109 questions written to mirror how a dispatcher would
phrase things — not how they would phrase them after reading the schema. Each
question is rubric-typed (an expected category) and scenario-grounded (run
against a specific solver snapshot).

**Ablations.** Four end-to-end configurations:

- *LLM-off (deterministic only).* No semantic adapter; intent inferred from
  deterministic rules over the query text.
- *LLM-on (full pipeline).* Semantic adapter produces the intent; contract
  resolves and verbalizes.
- *No-retry.* Disables the adapter's retry-on-validation-error loop.
- *No-alternatives.* Disables the alternative-intent suggestion path.

**Reliability benchmark.** A separate 60-case set for pass@k: same query, k
independent samples, all must produce a useful answer to score 1.

**Bucketing.** Each response is automatically bucketed into one of
`ANSWERED_USEFULLY`, `ANSWERED_PARTIALLY`, `CLASSIFIED_WRONG`,
`REFUSED_LEGITIMATELY`, `REFUSED_INCORRECTLY`. A separate *strict rebucketer*
re-scores under stricter criteria; the headline numbers below are from that
stricter pass. The rebucketer's parameters are pre-registered and the
canonical reports are locked by SHA-256 hashes (see
[`canonical_hashes.txt`](canonical_hashes.txt)).

## Headline numbers

**Operator corpus, strict bucketing:**

| Configuration | Strict-useful share |
|---|---:|
| LLM-off (deterministic only) | 39.8% |
| LLM-on (full pipeline) | **61.5%** |

The wrong-answer rate stays roughly constant across the two configurations
(the strict rebucketer reports ~15% wrong across both phases combined). The
22-point lift comes from converting refusals and partial answers into useful
ones — not from trading off correctness.

**Outcome-change attribution.** Of the 62 queries where LLM-on and LLM-off
produced different outcomes:

- LLM **helped** in 24 cases (non-useful → useful, or salvaged a refusal).
- LLM **hurt** in 3 cases (deterministic-useful → wrong or refused).
- Remaining 35 were neutral changes (different bucket, same usefulness class).

The 24:3 asymmetry is the strongest single-line evidence that the contract
layer absorbs the LLM's mistakes before they reach the operator.

**Reliability gradient (60-case benchmark):**

| Configuration | k | pass@k |
|---|---:|---:|
| Prompt-only LLM (no contract) | 5 | 0.30 |
| Hybrid (deterministic prior + LLM) | 3 | 0.50 |
| Contract-grounded (deterministic only) | — | 1.00 |

The contract-grounded path's pass@k is 1.00 *by construction* — the path is
deterministic, so re-running the same query gives the same answer. The
interesting comparison is prompt-only LLM at 0.30. A controlled architecture
trades the LLM's surface-form flexibility against the contract's repeatability.

## Where the system is weak

Two cuts on the same data are useful.

**By rubric category** (the canonical thesis-facing slicing): action-
recommendation queries are near-useless (~0% useful), risk/fragility ~13%,
prioritized-diagnosis ~36%. The remaining categories (objective, plan-validity,
schedule, structural) range from 32% to 49% useful.

**By inferred intent** (a finer-grained diagnostic added during follow-up
analysis): the failure mass concentrates in three intent buckets out of 22 —
`unknown` (185 cases at phase-on, 12% useful), `evaluate_plan_acceptability`
(158, 6% useful), and `what_to_watch` (50, 0% useful). Together those buckets
account for over half the not-useful mass.

The finer cut reveals something the rubric-category view obscures: most of the
`evaluate_*` and `what_to_watch` failures are **rubric/intent-set mismatch**,
not contract bugs. The system gives correct answers against the intent it
picked ("By the configured thresholds, this plan is acceptable; objective
change 0.0%, threshold 10%"), but the rubric grades on intent-to-category
alignment and marks the answer wrong because the operator's question was
scored as belonging to a different rubric category. The `unknown` band, by
contrast, is real intent-routing variance — the LLM punted on classification
when it shouldn't have.

That distinction matters because the fixes are different. Closing the
`unknown` band is an LLM-classification problem (the lever being tested in
the ongoing self-consistency experiment); the `evaluate_*` block is a coverage
problem in the intent set itself.

## What's queued next

Three follow-ups, each targeting a specific failure mode named above:

1. **Self-consistency on the intent classifier.** Sample N intents at
   temperature > 0 and majority-vote, with ties falling back to `unknown`
   (consistent with the system's honest-refusal stance). Targets the `unknown`
   band. Results will be appended here when the experiment commits, whether
   the lift is positive or null.

2. **Expanded guard triggers.** The adapter already has guards that redirect
   known misroutes (`_apply_evaluation_guard`, `_apply_ranking_guard`); their
   trigger phrases are narrow. Extending them is the cheapest work-per-
   percentage-point on the `evaluate_*` block.

3. **A `prioritized_diagnosis` intent.** Several `unknown`-band queries and
   the majority of `what_to_watch` answers are operators asking for ranked
   pain points on the specific plan, which the current intent set has no
   clean home for. Adding one is the smallest principled change that
   addresses a real coverage gap.

## Framing in the broader literature

This system sits in three overlapping literatures. The **propose / dispose**
split — LLM as semantic-frame extractor (intent + slot fillers), deterministic
dialogue manager / action selector downstream — is the consensus production
NLI architecture pre-LLM (Rasa, Dialogflow, Watson Assistant), here updated
with an instruction-tuned LLM as the upstream NLU. The **sufficiency gate** is
the answerability-prediction problem familiar from SQuAD 2.0 and from
schema-coverage detection in text-to-SQL. The visual-actions pipeline
(`infer_visual_actions(intent, evidence)`) is system-act generation in
task-oriented dialogue terms — turning a parsed intent into UI acts
deterministically rather than by LLM generation.

What this work shows, on one domain, is that the production pre-LLM discipline
(split NLU from response, gate on answerability) remains the right default
when the backend is verifiable — and that the LLM's value is concentrated
where surface-form flexibility matters (paraphrase robustness on the
classifier), not where claims have to be true (answer authoring). That
direction is consistent with broader text-to-SQL and grounded-NLI findings;
this work adds an additional data point on a domain those literatures haven't
covered (dynamic optimization backends).

Calling the contribution *novel* in NLI literature would be overclaiming. The
discipline is conventional. What's distinctive here is its careful application
to live solver state and the comparatively thorough evaluation methodology for
a single-domain study.

## What this evaluation supports — and what it doesn't

**Supports, on this corpus:**

- Adding a constrained LLM adapter to a deterministic copilot lifts useful
  answers ~22pp without raising the wrong-answer rate.
- When the LLM changes the outcome, it helps roughly 8× more often than it
  hurts (24 vs. 3 on outcome-changing cases).
- A contract-grounded path is repeatable across resamples (pass@k = 1.00 by
  construction); a prompt-only LLM path is not (pass@k = 0.30 at k=5).
- Explicit answerability rejection is operationally distinguishable from
  wrong-answering — the rubric separates the two, and most of the
  system's refusals are scored as legitimate.

**Consistent with broader literature but not proven by this work alone:**

- Hybrid / neuro-symbolic architectures outperform end-to-end LLM generation
  on tasks with verifiable outputs. One domain studied here; the broader claim
  rests on multiple text-to-SQL and semantic-parsing studies pointing the same
  way.

**Does not support:**

- Generalization to other optimization backends. The architecture is
  *designed* to generalize; the experiment doesn't *show* it generalizes.
- Statistical superiority over a tool-using LLM agent. That comparison wasn't
  run.
- Strong significance claims. The 109-query corpus is descriptively useful
  but small; lead with deltas and asymmetries, not p-values.

## Where to look

- **Canonical reports** (locked, SHA-256 verified):
  [`product/evaluation/reports/`](../product/evaluation/reports/)
- **Operator-persona raw responses:**
  [`product/evaluation/reports/ablation_v1_full/operator_persona_responses.jsonl`](../product/evaluation/reports/ablation_v1_full/operator_persona_responses.jsonl)
- **Strict rebucketer logic:**
  [`product/evaluation/operator_persona_strict_rebucket.py`](../product/evaluation/operator_persona_strict_rebucket.py)
- **Reproducibility:** [`docs/reproducing_results.md`](reproducing_results.md)
- **File integrity hashes:** [`docs/canonical_hashes.txt`](canonical_hashes.txt)

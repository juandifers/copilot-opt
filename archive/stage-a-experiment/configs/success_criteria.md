# Success criteria — locked at preregistration-v1

Pre-registered claims and thresholds verbatim from `spec.md`. The
3-of-4 rule and the methodology-limit conditions are also verbatim.
Two Framing notes appended at the end document the interpretation
context the numbers will be read against.

## Pre-registered claims

**Claim 1 — axis separability.** The three axes are not collinear.
Specifically, at least 10% of prompts produce mixed patterns (high on
one axis, low on another). If all prompts are either all-pass or
all-fail, the axes are redundant and the thesis claim weakens.

**Claim 2 — policy effect.** Policy-accepts vs policy-escalates
produces measurably different language-level outcomes. Operational
validity rate differs by ≥ 0.20 between the two policy decisions on
insufficient cells.

**Claim 3 — sufficiency manifests.** On insufficient cells,
faithfulness and operational validity drop. Mean faithfulness on
insufficient cells is at least 0.5 points lower than on sufficient
cells (5-point scale).

**Claim 4 — cross-scale.** Homberger prompts don't produce
dramatically worse scores than Stage A prompts. Mean faithfulness drop
on Homberger is ≤ 0.5 points.

## Success rule (3-of-4)

The experiment succeeds (the thesis methodology validates at the
language layer) if **at least three of these four conditions hold.**

## Methodology-limit conditions (still publishable, reframed)

The experiment flags methodology limits if any of the following hold:

- The classifier accuracy is below 0.80: the claim-family abstraction
  may not be as clean in natural language as the predictor work
  assumed.
- Faithfulness pass rate is below 0.70 overall: the
  LLM-as-grounded-answer-generator part of the product needs more
  constraint engineering.
- Axes are collinear (Claim 1 fails strongly): the three-axis
  decomposition isn't doing distinct work in this experiment; either
  the prompts didn't exercise the distinction, or the axes need
  rethinking.

## Framing notes

### Framing note 1 — stress-test framing

The generator is Haiku 4.5, the judge is Sonnet 4.6. This setup is a
stress-test framing: a lighter generator is more likely to produce
faithfulness failures, which the three-axis decomposition is designed
to surface. Claim 1 (axis separability) is therefore expected to be
easier to demonstrate at the ≥10% threshold than it would be with a
production-grade generator. Claim 4 (cross-scale faithfulness within
0.5 of Stage A on Homberger) is expected to be harder, because Haiku's
hallucination rate is more sensitive to longer route lists. The
pre-registered thresholds are unchanged from the spec; this note
documents the framing the numbers will be interpreted against.

### Framing note 2 — classifier limitation auditable

Zero-shot classifier locked with STRUCT_SCHEDULE boundary at ~0.667 in
pilot. `prompts.csv` ground-truth labels enable per-prompt classifier
audit at analysis time. Claim 2 (policy effect) will be reported both
with and without classifier errors to separate classifier contamination
from policy effect.

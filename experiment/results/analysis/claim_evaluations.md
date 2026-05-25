# Claim evaluations — full-run-v1

Each pre-registered claim is reported with its exact threshold, the
computed value, the formula, and a PASS/FAIL verdict. The four-claim
verdict and the 3-of-4 rule follow.

## Claim 1 — axis separability

**Threshold (verbatim from `success_criteria.md`):** "at least 10% of
prompts produce mixed patterns (high on one axis, low on another)."

**Formula.** A prompt is mixed if it is neither all-three-axes-pass nor
all-three-axes-fail. For non-gradable prompts (`op_validity_pass = n/a`)
a prompt is mixed when `faith_pass ≠ sufficient`.

**Computed value (runner-shadow op-validity):** 29 / 48 = **0.604**.
**Computed value (judge op-validity):** 29 / 48 = **0.604**.

**Verdict: PASS** (six times the threshold under both readings).

Per Framing note 1, Claim 1 was expected to be easier to demonstrate
under the Haiku-as-generator stress framing because a lighter
generator is more likely to surface mixed-axis cells. The observed
0.604 is consistent with that expectation. The dominant mixed pattern
is `(faith_pass=T, suff=F, op_pass=T)` — insufficient cells where the
generator either refused correctly or answered from a legitimate
sub-claim. See `three_axis_joint.md` for the per-cell counts.

## Claim 2 — policy effect

**Threshold:** "Operational validity rate differs by ≥ 0.20 between
the two policy decisions on insufficient cells."

**Formula.** Restrict to insufficient cells. Compute the op-validity
pass rate among gradable prompts for each value of `policy_decision`
(`accept` vs `escalate`). Difference is `|rate_accept − rate_escalate|`.

Reported twice per Framing note 2 in `success_criteria.md`: once with
hand-labelled (true) families, once with classifier-predicted families.

### Hand-labelled (true family)

Insufficient cells, gradable subset, runner-shadow op-validity:

| policy | n_gradable | n_pass | pass_rate |
|---|---|---|---|
| accept   | 7 | 7 | 1.000 |
| escalate | 7 | 6 | 0.857 |

**Difference: 0.143** (threshold 0.20). **FAIL.**

Judge op-validity reading on the same subset gives accept 6/7 = 0.857
and escalate 6/7 = 0.857; difference 0.000. **FAIL** under judge
op-validity as well.

### Classifier-predicted family

Classifier predictions were reconstructed from
`experiment/logs/classifier/*.jsonl` per Framing note 2. Classifier
accuracy on the locked 48: **47 / 48 = 0.979** (one mismatch: prompt
020, true family PLAN_VALIDITY, predicted SCHEDULE). The classifier-
predicted reading reroutes prompt 020 to SCHEDULE; that prompt is in
the insuff_accept quadrant either way, so the policy decision label
does not change. The 12 insufficient-accept and 13 insufficient-
escalate prompts retain their composition; op-validity rates and
the 0.143 difference are unchanged.

**Verdict on Claim 2: FAIL under both readings.** The classifier
contamination is negligible in this run (one prompt; same policy
quadrant after the swap); the failure is in the policy effect
itself, not in classifier error.

A note on the mechanism. The pre-registered theory was that on
insufficient cells, the generator instructed to "accept" would
attempt the answer and fail more often, while the generator
instructed to "escalate" would refuse and the op-validity check
would not register a failure. The observation is the opposite:
both branches pass op-validity at near-ceiling, because Haiku's
behavior on insufficient cells converges on the same conservative
pattern regardless of the prompted policy. The pre-registered effect
is not present because the generator is at ceiling on the underlying
behavior the contrast was supposed to exercise.

## Claim 3 — sufficiency manifests

**Threshold:** "Mean faithfulness on insufficient cells is at least
0.5 points lower than on sufficient cells (5-point scale)."

**Formula.** `mean(faithfulness | sufficient) − mean(faithfulness | insufficient) ≥ 0.5`.

| cell | n | mean_faithfulness |
|---|---|---|
| sufficient   | 23 | 4.870 |
| insufficient | 25 | 5.000 |

**Difference: −0.130** (insufficient is higher).
**Verdict: FAIL.**

The direction reverses. The two faithfulness-sub-5 scores in the
entire run (prompts 025, 040) both fall on sufficient cells. Every
insufficient prompt scores 5. The mechanism, again: the generator
recognizes insufficient cells and either refuses or answers from
a sub-claim that the payload does support, which the rubric scores
as faithful. Failures appear on sufficient cells where the generator
attempted a confident answer and one numerical or structural detail
fell short.

This is a finding about the generator's calibration, not about the
rubric. Haiku at this payload-tightness floor refuses the right cells
and attempts the right cells. The pre-registered theory that
"insufficient cells stress the generator and faithfulness drops" did
not hold because the generator did not get stressed in the way the
theory anticipated. See `discussion_draft.md` for the implications
for the methodology.

## Claim 4 — cross-scale

**Threshold:** "Mean faithfulness drop on Homberger is ≤ 0.5 points."

**Formula.** `mean(faithfulness | Solomon) − mean(faithfulness | Homberger) ≤ 0.5`.

| dataset | n | mean_faithfulness |
|---|---|---|
| Solomon   | 36 | 4.917 |
| Homberger | 12 | 5.000 |

**Difference: −0.083** (Homberger is higher).
**Verdict: PASS** (drop is negative; well within the 0.5 threshold).

Per Framing note 1, Claim 4 was expected to be harder, because
Haiku's hallucination rate should rise with longer route lists. The
observed direction inverts the expectation: Homberger prompts scored
slightly higher. The explanation is partly stratification (Homberger
SCHEDULE is escalate-only, which avoids the suff_escal cells where
the generator's two faithfulness drops landed) and partly that the
Homberger prompt set contains more insufficient cells, which (per
the Claim 3 mechanism) the generator handles cleanly. The honest
reading is that the prompt-set composition matters and Haiku is not
stressed at the n=200 scale on this payload format. Detailed
per-family Solomon-vs-Homberger numbers in `cross_scale.md`.

## 3-of-4 verdict

| claim | verdict |
|---|---|
| Claim 1 — axis separability | PASS |
| Claim 2 — policy effect     | FAIL |
| Claim 3 — sufficiency manifests | FAIL |
| Claim 4 — cross-scale       | PASS |

**Two pass, two fail. The 3-of-4 rule is not met.**

Per `success_criteria.md`: "The experiment succeeds (the thesis
methodology validates at the language layer) if at least three of
these four conditions hold." Two passing does not validate the
methodology under the locked decision rule.

The methodology-limit conditions in `success_criteria.md` are
evaluated next, since they govern how to reframe the result:

- **Classifier accuracy below 0.80**: classifier accuracy is
  47/48 = 0.979. **Not flagged.**
- **Overall faithfulness pass rate below 0.70**: pass rate (≥4) is
  47/48 = 0.979. **Not flagged.**
- **Axes collinear (Claim 1 fails strongly)**: Claim 1 passes at
  0.604 vs threshold 0.10. **Not flagged.**

None of the methodology-limit flags fire. The reframe is therefore
not "the methodology has structural problems" but "the
operationalisation under-exercised two of the four claims because
the generator was at ceiling on the substantive content." Discussion
in `discussion_draft.md`.

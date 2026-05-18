# Human-pilot calibration protocol — locked at preregistration-v1

20-prompt stratified subset of the locked 48-prompt set, dual-rated by
the candidate (human) and the Sonnet 4.6 judge using the same rubric.
Inter-rater agreement gate before the full LLM-as-judge run.

## Sample (20 prompts)

Stratified across families and sources:

- **Per family:** 5 prompts (5 × 4 families = 20).
- **Per source:** 10 synthetic + 10 LLM-generated (overall split, not
  per-family — within each family the synthetic/LLM mix is whatever
  the stratification rule yields).
- **Per quadrant:** balanced where possible. Specific 5-per-family
  layout: 1 suff_accept + 1 suff_escalate + 2 insuff_accept + 1
  insuff_escalate. The over-sample on `insuff_accept` aligns with the
  Solomon "3" allocation in `stratification.md` and concentrates
  calibration signal on the false-positive quadrant.
- **Per dataset:** 16 Solomon + 4 Homberger (one Homberger per family).

Deterministic sampling: `random.Random(2026 + 1000)` (offset 1000 to
keep pilot draws independent of stratification draws); within each
family pick by `(instance_id, perturbation_id)` lexicographic order
then sample.

## Dual-rating procedure

1. The candidate rates all 20 prompts using `experiment/configs/rubric.md`
   without seeing the judge's scores.
2. The judge (Sonnet 4.6 via the locked `judge_config.yaml`) scores the
   same 20 prompts.
3. The two score sets are joined on `prompt_id` and analysed.

Faithfulness is the rated axis (1-5 integer). Op-validity is
machine-computable and not dual-rated.

## Inter-rater agreement gate

**Cohen's kappa (faithfulness, quadratic weights) ≥ 0.70.**

If kappa ≥ 0.70: proceed to the full LLM-as-judge run on all 48
prompts.

If kappa < 0.70: rubric revision + re-pilot from scratch. The
candidate identifies the specific disagreement patterns (typically:
which rubric scores are most contested), proposes wording revisions
to the rubric or the judge system prompt, commits the revisions as a
new tag (`preregistration-v2`), and re-runs the pilot with the new
20-prompt sample (re-seed by adding 1 to the pilot seed). A new pilot
is required after every rubric revision — the previous calibration
does not carry forward.

## The 3-vs-4 boundary

With Haiku as the generator, faithfulness disagreements between the
Sonnet-judge and the candidate are most likely on the boundary between
scores 3 and 4 (the answer is broadly correct but with imprecision).
The rubric distinguishes these clearly:

- Score 4: "minor imprecision (e.g., rounding); no semantic error."
- Score 3: "one factual claim doesn't match data, but the answer is
  broadly correct."

Imprecision ≠ factual mismatch. A rounded number that is within the
op-validity tolerance is imprecision (score 4). A number that exceeds
the tolerance, or a wrong customer ID, is a factual mismatch (score
3 or lower).

Calibration must verify this distinction holds between judge and
human. Specifically: across the 20 pilot prompts, every score-3
assignment by either rater must be examinable for whether it should
have been score 4 (and vice versa); pre-rubric-revision, a confusion
matrix of (human × judge) faithfulness scores is included in the
pilot writeup with the 3-vs-4 cells called out.

## Pilot writeup

Saved to `experiment/pilot/calibration_pilot_results.md` (Prompt 6 or
later). Contains:

- The 20-prompt sample with prompt_id, family, quadrant, source.
- Per-prompt: candidate score, judge score, |diff|.
- Cohen's kappa (quadratic-weighted).
- Confusion matrix of candidate × judge faithfulness scores, 3-vs-4
  cells emphasised.
- Disagreement examples (every pair where |diff| ≥ 2, plus a random
  sample of 3 of the 3-vs-4 cases).
- Verdict (proceed / rubric-revision-required).

The full LLM-as-judge run does not start until this writeup is
committed and the gate is met.

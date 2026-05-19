# Manual review log — locked 48-prompt set

Prompts in `experiment/data/prompts.csv` where the construction pipeline
flagged `manual_review_required = True`. These are prompts that required
a manual override of an automated check at construction time: the
classifier-disagreement-after-N-attempts case, payload-schema edge
cases, or perturbation-substitution edge cases.

This log gives the analysis section at Prompt 10 a clean audit hook for
**"which prompts were known boundary cases at construction time"**
versus **"which prompts surfaced as failures only at scoring time."**
Both are legitimate findings; the distinction matters for separating
pre-registered classifier contamination from in-run surprises.

## Summary

| prompt_id | family | source | cell_id | review reason |
| --- | --- | --- | --- | --- |
| 020 | PLAN_VALIDITY | llm_generated | RC103__ST_2 | classifier-disagreement fallthrough after 3 LLM-generation attempts |

Total: 1 of 48 prompts.

## Prompt 020 — PV / RC103__ST_2

**Prompt text** (final, accepted on attempt 3):

> If jobs are taking longer to complete now, can all the stops on this route still be finished within their allowed windows?

**Cell metadata:**

- `instance_id`: RC103
- `perturbation_id`: ST_2 (SERVICE_TIME, multiplier 1.25)
- `perturbation_family`: SERVICE_TIME
- `quadrant`: insuff_accept (the predictor wrongly accepted the cheap action; sufficiency label = insufficient)
- `policy_decision`: accept
- `action_taken`: reuse_direct
- `op_validity_gradable`: False (the prompt elicits a sub-feasibility status — TW feasibility under longer service times — not the headline `claimed_feasible` boolean)

**Why it's flagged:**

The cell is a PV cell (claim family is PLAN_VALIDITY). Sonnet's first
two LLM-generation attempts produced operator-natural PV questions, but
the locked zero-shot classifier read both as SCHEDULE because the
service-time framing ("jobs are taking longer", "stops finished within
allowed windows") pattern-matches the classifier's SCHEDULE
boundary-case examples (which target timing/lateness language). The
third attempt steered toward "working hours" framing and was accepted
by the classifier — but only after the prior two attempts had failed
the (b) family-alignment filter.

The fallthrough rule in `prompt_constructor.py` keeps the third
attempt and flags `manual_review_required = True` for downstream
analysis.

Independently, the **classifier sanity check** (Step 6,
`experiment/data/classifier_sanity_check.md`) ran the locked classifier
against the final accepted prompt 020 and classified it as SCHEDULE
again — 1 of 1 PV misclassification on the 48-prompt set. This is the
PV↔SCHEDULE boundary case the pre-registration explicitly handles via
`success_criteria.md` Framing note 2:

> Zero-shot classifier locked with STRUCT_SCHEDULE boundary at ~0.667
> in pilot. `prompts.csv` ground-truth labels enable per-prompt
> classifier audit at analysis time. Claim 2 (policy effect) will be
> reported both with and without classifier errors to separate
> classifier contamination from policy effect.

**Decision recorded at construction time:** keep prompt 020 as-is.
Rationale: the prompt is operator-realistic and asks the cell's
intended claim family (whether the plan still serves all customers
under increased service times); modifying it now would steer the
locked set toward classifier convenience rather than authentic
operator language. The classifier miss is documented and auditable.

## Adjacent context — Step 4 rejection log

Five additional (b) rejections during Step 4 prompt construction were
PV-on-SERVICE_TIME prompts the classifier read as SCHEDULE (the same
boundary pattern). All five eventually accepted after re-generation in
attempt 2 or 3; only prompt 020 fell through to the 3-attempt limit
without crossing the classifier filter. The full rejection trail is at
`experiment/data/llm_prompt_rejections.md`.

The clustering of (b) rejections on the SERVICE_TIME → PV cells is
itself a finding: the classifier's known boundary weakness is
specifically the *temporal-language framing of feasibility questions*
that SERVICE_TIME perturbations naturally produce. The locked
classifier is unchanged from `preregistration-v1`; the analysis section
at Prompt 10 should report this clustering as part of the boundary
characterisation.

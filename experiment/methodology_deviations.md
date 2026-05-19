# Methodology deviations log

## Deviation 1: Calibration pilot completed under degenerate kappa

Date: 2026-05-19
Affected protocol: pilot_protocol.md (preregistration-v1.1)

**What happened.** The 20-prompt calibration pilot
(calibration-pilot-v1) produced faithfulness=5 from both judge
(Sonnet 4.6) and human (candidate) on all 20 prompts. Cohen's
quadratic-weighted kappa is undefined when both raters have zero
variance. Raw agreement was 20/20 but is statistically meaningless
in the constant-rater case.

**Why we proceeded instead of re-piloting.** The pattern is
informative, not noise: tight per-family payload schemas plus
explicit anti-hallucination instructions to Haiku produced answers
where the rubric's score-5 criterion ("every numerical and structural
claim matches the data") was satisfied throughout the calibration
sample. Rubric revision after seeing calibration results would be a
post-hoc adjustment risking confirmation-direction tampering. The
25% verification step at the full-run stage (verification_protocol.md)
is the operative judge-calibration check from this point — it dual-
rates 12 prompts from the full run with 60/40 weighting toward FP
and FN quadrants, producing judge-human agreement evidence on real
experimental content.

**What the calibration did surface.** Two documented findings that
proceed into the analysis as observations rather than calibration
corrections:

- Op-validity STRUCT-2 set-semantics ambiguity (prompts 025, 031):
  the rubric's `membership_set_equal` term is ambiguous on single-
  customer membership claims. The runner_shadow.py and the judge's
  prose rationale both apply subset semantics (the correct read);
  the judge's structured `op_validity_pass` field applies set-
  equality semantics, producing an internal contradiction with its
  own rationale. Logged as a known judge inconsistency, audited at
  analysis.

- The 3-vs-4 boundary anticipated as the most likely calibration
  weak point was not exercised. Neither rater used scores 3 or 4 on
  the calibration sample. Whether the boundary surfaces in the full
  run is an open question for the analysis.

**Mitigating controls.**
- Verification at Prompt 9 (12-prompt stratified human dual-rating)
  is the operative judge-calibration evidence from this point.
- runner_shadow.py op-validity is the authoritative op-validity
  computation for the analysis; judge op-validity is reported but
  verified against the runner.
- The thesis methodology section documents this deviation honestly.
  No claim of "calibration kappa >= 0.7" is made. The thesis claims
  "calibration produced 20/20 score-5 agreement; kappa undefined;
  verification at 25% of the full run is the substantive judge-
  calibration evidence."

## Deviation 2: Failure-mode (d) heuristic widened to include generator-output schema keys

Date: 2026-05-19
Affected protocol: smoke_test.py / run_experiment.py failure-mode scan (d)
Scope: tooling heuristic; the locked rubric and locked schemas are unchanged.

**What happened.** On prompt 001 of full-run-v1, the runner's
`_scan_payload_field_references` heuristic flagged the judge rationale
for referencing the backtick-quoted token `claimed_objective`. Per the
strict mid-run-drift rule (a)-(f) → halt, the run was halted at
2 of 48 prompts.

**Why this is a false positive.** `claimed_objective` is a required
field in `experiment/configs/generator_output_schema.json` — it is
the generator's structured claim that the judge is asked to compare
against the payload's `action_objective`. The judge's prose
"The generator's `claimed_objective` of 591.6 ... matches
`action_objective` = 591.6 in the payload" is exactly the rhetoric
the rubric asks for. It is not a hallucinated payload field name.

**Why this didn't trigger in smoke (4) or calibration (20).** Across
24 prior judge calls, no judge happened to backtick a `claimed_*`
schema field name. Judge wording variance is the cause; nothing in
generator or judge semantics drifted.

**The fix.** The heuristic's allow-list is widened from
`payload keys` to `payload keys ∪ generator-output schema keys`. The
seven schema keys (`answer_text`, `claimed_objective`,
`claimed_feasible`, `claimed_route_count`, `claimed_route_membership`,
`claimed_late_customers`, `claimed_customer_timings`) are now
recognised as legitimate judge references. The heuristic still flags
backtick-quoted snake_case tokens that are neither in the payload
nor in the generator-output schema — i.e., genuine hallucinations.

**Why this is not silent rubric tampering.** The fix is to the
runner's heuristic (`experiment/src/run_experiment.py`), not to
`experiment/configs/rubric.md` or any locked schema. The methodology
question "what counts as a (d) hallucination?" is answered the same
way it was at preregistration: a reference to a field that doesn't
exist anywhere the judge legitimately knows about. The pre-existing
heuristic was an under-specified approximation of that question; this
revision is its narrow, scoped correction. Logged here so that the
full-run-v1 evidence is auditable: anyone walking the commit chain
sees the heuristic change before the full run that uses it.

**Verification before the restart.** The widened heuristic still
fires on the constructed-positive case (a hallucinated payload field
in a judge rationale). The calibration jsonl is re-scanned post-hoc
under the widened heuristic; it produces the same 0/20 result as
before, confirming the widening did not retroactively change any
calibration finding.

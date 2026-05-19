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

# Discussion — draft for the thesis closing chapter

Forty-six of forty-eight prompts scored faithfulness 5. Two of the four
pre-registered claims pass; two fail. The 3-of-4 success rule misses
by one. The shape of the miss matters more than the count.

Claim 1 (axis separability) passed at 60.4% mixed patterns against a
10% threshold. Claim 4 (cross-scale) passed in the wrong direction —
Homberger-200 prompts scored 0.083 points higher than Solomon-100,
which clears the "drop ≤ 0.5" threshold without exercising it. Claims
2 and 3 failed for the same reason. Claim 2 expected a 0.20-point
op-validity gap between policy-accepts and policy-escalates on
insufficient cells; the observed gap is 0.143. Claim 3 expected a
0.5-point faithfulness drop from sufficient to insufficient cells;
the observed direction inverts. Insufficient cells scored 0.13 points
higher.

Why? The generator did not get stressed. Haiku's behavior on every
insufficient cell in the prompt set was to refuse correctly or pull
a legitimate sub-claim from the payload. Both moves score
faithfulness 5 under the locked rubric. The two faithfulness sub-5
cases in the run (prompts 025 and 040) both fell on sufficient cells,
where the generator attempted a confident answer and one numerical
or convention question fell short. The cells that were supposed to
break the generator did not. The cells that broke the generator were
not the ones the pre-registered claims targeted.

This is not a methodology failure. It is a finding about Haiku's
calibration on this payload format. The framing notes anticipated
that "a lighter generator is more likely to produce faithfulness
failures." Haiku at this payload tightness did not. How tight the
payload would have to be — or how heavy the generator would have to
be — for the sufficiency contrast to register was not in scope, but
the observation is now on the table. The locked payload schemas plus
the locked generator system prompt produced a generator that does
not hallucinate on this prompt set.

The calibration phase already told us something close to this and the
pre-registration discounted it. The 20-prompt calibration sample
returned faithfulness 5 from both judge and candidate human on every
prompt. Cohen's quadratic-weighted kappa is undefined when both
raters have zero variance, and the deviation was logged on the
theory that the full run would exercise lower scores. The full run
exercised lower scores twice, in 48 prompts, on cells uncorrelated
with the insufficient-data contrast. The calibration kappa was not
degenerate because the rubric was loose. It was degenerate because
Haiku does not produce score-3-or-4 answers on this prompt format.
The constant-5 pattern is the finding, not the noise. The
methodology should have a way to register that earlier.

The STRUCT set-semantics ambiguity is the second deviation that
matters. The rubric's structured op-validity term
`membership_set_equal` admits two readings on single-customer
route-membership claims. Subset semantics: "customer X is on route Y"
passes if X appears in `routes[Y].customer_ids`. Set-equality
semantics: the claim must enumerate the route. The judge's prose
rationale and the runner-shadow apply subset semantics; the judge's
structured field applies set-equality semantics. They contradict each
other on the same prompt. Verification prompt 029 made this explicit
— judge prose says correct, judge structured field says False, human
sides with the prose, runner-shadow sides with the prose. The locked
decision rule treats the runner-shadow as authoritative on
op-validity. The headline is unaffected. The discrepancy is in the
verification record, and an honest write-up has to name it.

Then the route-indexing convention. Verification surfaced one
|diff| = 2 disagreement on prompt 040. The generator answered with
the end_time at `route_idx = 1`. The judge marked it wrong, on the
theory that "route 1" in PyVRP's user-facing display means the first
route (i.e., `route_idx = 0`). The human marked it right, on the
theory that the payload's `route_idx` field is authoritative. Both
readings are defensible. The payload does not pre-commit to a
convention; the generator system prompt does not pre-commit to a
convention; the rubric does not pre-commit to a convention. Three
layers, three implicit conventions, one ambiguity at the interface.

The classifier is the cleanest deviation. Reconstructed predictions
give 47/48 correct on the locked prompt set, one mismatch (020,
true PLAN_VALIDITY, predicted SCHEDULE). The 0.80 methodology-limit
threshold is not exercised. Framing note 2 asked for Claim 2 both
with and without classifier errors; the one mismatch routes to the
same insuff_accept quadrant either way, so the two numbers are
identical. The classifier was not load-bearing in this run.

What did the three-axis decomposition surface at the language layer?
Claim 1's threshold cleared by six times. The dominant mixed cell
is `(faith_pass=T, sufficient=F, op_pass=T)`: insufficient cells
where the generator refused or pulled a sub-claim and the runner
registered an op-validity pass. The framework was designed to
distinguish that pattern from a "passed everything" cell and from a
"failed everything" cell. It does. Empirically, not theoretically.
The three axes are not collinear on this prompt set. The framework
distinguishes "the generator hallucinated" (zero occurrences) from
"the generator handled an under-specified question correctly"
(25 occurrences). The methodology contribution holds up. The
substantive contribution — what failure modes a stronger generator
would surface under the same framework — remains untested.

That is the stress-test framing's hard limit. Haiku-4.5 was chosen
on the theory that a lighter generator would produce more failures
to taxonomise. The two failures it produced are both rubric-or-
convention ambiguities, not generator hallucinations. A framework
cannot validate its failure-mode taxonomy when no failures occur.
The faithfulness scale's lower half is exercised by exactly one
prompt in 48, and that prompt is a convention dispute. The
methodology is operationalisable. The specific failure-mode evidence
is thinner than a weaker-generator experiment would have produced.

One change per load-bearing deviation, for the future replication.

For the calibration degeneracy: add a "minimum-disagreement" prompt
to the calibration sample, designed to exercise the 3-vs-4
faithfulness boundary on a payload that supports only a partial
answer. The kappa moves off-degenerate before the full run commits.
Cheap to add, forces the lower half of the rubric to be exercised.

For STRUCT set-semantics: rewrite `membership_set_equal` to specify
subset semantics when the generator's claim names a single customer
and set-equality only when the generator enumerates a route. A
one-paragraph rubric change.

For the route-indexing convention: pre-commit in the payload schema.
Surface `route_label` (1-indexed display string) alongside
`route_idx` (0-indexed integer) on every SCHEDULE and STRUCT
payload. The generator names whichever; the runner and the judge
can check both.

For the classifier: log classifier predictions per-prompt at run
time. The reconstruction this analysis did from
`experiment/logs/classifier/` worked because the logs survived. A
future replication should not depend on log archaeology.

The methodology validates at the language layer for the part of the
question this prompt set exercises. The part it does not exercise —
what happens when a generator does hallucinate on this payload —
waits for the next experiment.

# Failure modes — full-run-v1

Worst-3 and best-3 prompts per family pulled from
`experiment/results/joined/full-run-v1.csv`. Ranking is by
faithfulness first, op-validity (judge + runner) second. 24 prompts
total; six families × four (three worst, three best). Categories
emerge from the data rather than from a pre-fitted taxonomy.

## What "worst" looks like at Haiku's ceiling

The generator scored 5 on 46 of 48 prompts. The worst-3 lists for
each family therefore contain mostly score-5 prompts that landed in
the worst slot because of an op-validity flag or a category-specific
phrasing decision. Two genuine sub-5 cases exist in the entire run:
prompt 025 (STRUCT, f = 4) and prompt 040 (SCHEDULE, f = 3). Both
sit on sufficient cells. Neither is a hallucination.

The categories that emerged:

1. **Route-indexing convention**. The generator picks the
   payload-canonical reading; the judge applies a PyVRP user-facing
   convention. Prompts 040, 041.
2. **Membership set-semantics rubric ambiguity**. The judge's
   structured op-validity field demands enumeration of the entire
   route's customer set; the prose rationale and the runner-shadow
   apply subset semantics on a single-customer claim. Prompts 029, 031.
3. **Volunteered baseline-vs-perturbed comparison**. Generator
   provides an unrequested numerical comparison that the rubric's
   op-validity checks treat as a payload claim. Prompts 002, 010.
4. **Refusal-as-faithfulness-loss**. Generator correctly refuses an
   under-specified question and the judge scores faithfulness < 5
   because the refusal phrasing is unusually explicit. Prompt 025.

The 46 score-5 cases share a different pattern. The answers are
short, hew to the payload's named fields, and avoid extrapolation.
The best-of-best look like four-word answers ("2783.8
solomon_distance units.") or short two-sentence summaries that
mirror payload language.

## OBJ

### Worst 3

**Prompt 002** (`suff_accept`, llm_generated, Solomon, TT_4) —
faithfulness 5, op-validity False.

The prompt asks *"What did this end up costing compared to running a
full re-solve?"*; the answer reports the perturbed objective and a
percent-delta against a baseline. Both numbers are in the payload.
The op-validity check fails because the structured field
`objective_within_0_5_pct` reads the generator's volunteered delta
against a stricter tolerance than the rubric anticipated. The judge's
prose rationale agrees with the runner. This is a rubric tightness
issue, not a generator error.

**Prompt 010** (`insuff_escal`, llm_generated, Solomon, ST_2) — same
pattern as 002. The generator's answer adds a comparison between the
10-second solve and a hypothetical full re-solve. The runner reads
the comparison as an op-validity claim against a value the payload
does not strictly support to within the registered tolerance.

**Prompt 004** (`suff_escal`, synthetic, Solomon, ST_3) — f = 5,
op-validity non-gradable. The answer reports a 6.77% increase in
total distance; the payload supports the baseline and perturbed
distances directly. The rubric treats `suff_escal` cells as non-
gradable on the runner side, so this prompt ranks "low" only because
it has no op-validity check to pass.

### Best 3

**Prompt 006** (`suff_escal`, llm_generated). Two-token answer:
*"2783.8 solomon_distance units."* No volunteered context. No
extrapolation.

**Prompt 009** (`insuff_accept`, llm_generated). Short numerical
answer with a baseline comparison that the payload directly
supports.

**Prompt 012** (`insuff_escal`, llm_generated). The generator reports
the perturbed and re-solve objectives and the percent-delta. All
three figures present in the payload.

OBJ has no faithfulness failures. The worst-of-worst (prompts 002,
010) are op-validity flags from over-tight numerical rubric terms
that the verification and runner-shadow agreement both read as
spurious.

## PLAN_VALIDITY

### Worst 3 — all faithfulness 5, all non-gradable

**Prompts 014, 017, 018**. The PLAN_VALIDITY family is the most
forgiving in this run. The generator's answers on these prompts mix
binary feasibility claims with short prose summaries (*"capacity, time
windows, and coverage are all satisfied"*, *"all customers still
reachable and served"*). The rubric's op-validity check applies
only to specific cells; these three are non-gradable, which is what
puts them at the bottom of the per-family sort. They are not
failures.

### Best 3

**Prompts 015, 016, 019**. All three faithfulness 5 and op-validity
True. The best PLAN_VALIDITY answer in the run (019) is a refusal-
style infeasibility report: *"No. The updated plan does not work
within all route constraints. The feasibility check shows the plan
is infeasible due to time window violations."* That answer is on an
`insuff_accept` cell — the generator is asked to accept the answer
under insufficient data and produces the correct call from the
payload's `tw_feasible: false` field. PLAN_VALIDITY is the cleanest
family in the run.

## STRUCT

### Worst 3

**Prompt 025** (`suff_accept`, llm_generated, Solomon, OC_2) —
faithfulness 4, op-validity False.

Only sub-5 STRUCT score. The prompt asks which route the new
customer was assigned to. The OC_2 perturbation adds a new customer
to an instance, but the SOLUTION DATA payload exposes only
`n_routes` and `routes` (with no field marking which customer was
newly added). The generator refuses correctly:

> The data does not contain information about which customer ID(s)
> were newly added in the OC_2 perturbation, so I cannot identify
> which route the new customer(s) were assigned to.

The judge scores faithfulness 4 (not 5) because the refusal phrasing
is unusually direct about the payload's contents. The rubric does
support faithfulness 5 on a correct refusal; the judge's prose
rationale on this prompt reads as if the judge was uncertain whether
the prompt was answerable from an external knowledge view, and
penalized the answer for not attempting. This is the only case in
the run where a refusal got less than 5.

**Prompt 027** (`suff_accept`, llm_generated, Homberger, TW_5).
Refusal on a question about truck-count change. Faithfulness 5,
op-validity non-gradable.

**Prompt 029** (`suff_escal`, synthetic, Solomon, TT_3). The
membership set-semantics case. Generator says correctly that
customer 42 is on route 4; payload confirms; judge's prose rationale
confirms; judge's structured op_pass = False because the rubric's
`membership_set_equal` term reads as set-equality. Documented in
Deviation 1 of `methodology_deviations.md`. The verification phase
sided with the runner-shadow and the human rater (subset
semantics): op_pass = True.

### Best 3

**Prompts 030, 032, 034**. Examples of clean STRUCT answers:
*"Yes, customers 12 and 17 are both on route 2 after the time windows
were tightened."*; *"No. Customer 12 is on route 8 and customer 17
is on route 9. They are not on the same route."* The generator
answers exactly what was asked, with no volunteered membership
enumeration.

## SCHEDULE

### Worst 3

**Prompt 040** (`suff_escal`, synthetic, Solomon, ST_4) —
faithfulness 3, op-validity False.

The only faithfulness 3 in the run. Route-indexing convention case
(see dedicated section below).

**Prompt 041** (`suff_escal`, synthetic, Homberger, OC_5) —
faithfulness 5, op-validity split (runner False, judge True).
Generator's answer: *"Route 1 wraps up at 2309.8 solomon_minutes."*
Runner-shadow flags the answer as not matching its
`arrival_within_1min` check (probably another route-indexing
convention case at Homberger scale; the runner's check is
0-indexed). Judge marks True. Verification did not draw this
prompt, so the convention reading is not directly adjudicated here,
but the pattern is consistent with the prompt 040 case.

**Prompt 037** (`suff_accept`, synthetic, Solomon, TT_4). All-clean
score-5 answer (*"No. After the 50% increase in travel times, no
customers are late."*). Appears in the worst-3 list only because the
SCHEDULE family scores were tightly clustered; this prompt has no
issues.

### Best 3

**Prompts 046, 047, 048**. Two of them on `insuff_escal`. Sample:
*"All drivers will make it to each stop on time. There are zero late
customers in this solution."* Clean, payload-supported, no
extrapolation.

## The route-indexing convention finding

This is the one clean methodology finding from the verification
phase, and it deserves its own treatment.

Prompt 040 in the verification set surfaced a `|diff| = 2`
disagreement between judge and human on the faithfulness axis. The
generator named a numerical end-time (871.3 solomon_minutes) that
appears in the payload's `route_end_times` list under
`route_idx = 1`. The prompt asked about "route 1". Two readings:

- **PyVRP user-facing**: "route 1" is the first route. Solver outputs
  are conventionally displayed to users as 1-indexed. The first
  route is `route_idx = 0` in the payload. Its `end_time` is 864.1.
- **Payload-canonical**: the payload field is named `route_idx` and
  takes integer values starting at 0; "route 1" means
  `route_idx = 1`. Its `end_time` is 871.3.

The generator picked the second reading. The judge applied the
first. The human applied the second.

This is not a faithfulness failure in either direction. The generator
named a value that does appear in the payload, against a defensible
convention. The judge's rationale was internally consistent: it stated
the convention it was applying. The human's rationale was internally
consistent: it stated the convention it was applying. They disagreed
on which convention was authoritative.

The substantive observation. The payload format does not pre-commit
to a convention. The generator system prompt does not pre-commit to
a convention. The rubric does not pre-commit to a convention. The
human had to choose at scoring time, and so did the judge. They
chose differently.

This is a methodology finding worth surfacing in the discussion
section because it generalises. Any natural-language interface over
an indexed array faces the same pre-commit-or-don't decision. The
copilot use case is more sensitive to this than a typical
benchmarking task because the human operator who asks "route 1" will
also be the one who needs to walk to the depot and find that route's
truck; the indexing convention has to match the convention used in
the operator's other tooling. Pre-committing in the payload (e.g.,
always surfacing `route_label: "Route 1"` alongside `route_idx: 0`)
removes the ambiguity at the cost of a payload-field expansion.
Pre-committing in the system prompt removes the ambiguity at the
cost of locking the generator to one display convention.

The Deviation 4 entry in `methodology_deviations.md` flags this
case as a non-headline-affecting `|diff| ≥ 2` disagreement (per the
locked decision rule) and points to a forward-looking change for
the SCHEDULE payload schema.

## Cross-cutting observation

Two of the four families (OBJ, PLAN_VALIDITY) produced no
faithfulness failures. The other two (STRUCT, SCHEDULE) produced one
each, both on `suff` cells with `synthetic` or `llm_generated`
sources at random, both traceable to a rubric ambiguity or convention
question rather than a generator error. Hallucination — the failure
mode the three-axis decomposition was designed to surface — did not
appear at any prompt in this run.

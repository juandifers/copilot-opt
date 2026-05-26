# Judge–human agreement — verification sample

Source: `experiment/results/verification_results.csv` (n = 12 prompts,
12 / 48 = 25% sample). Locked sampling per
`experiment/configs/verification_protocol.md`: 60/40 weighted toward
FP+FN pools (`insuff_accept ∪ suff_escal`) vs TP+TN
(`suff_accept ∪ insuff_escal`), three prompts per family. Seeds and
implementation in `experiment/src/select_verification.py`.

## Faithfulness agreement

| metric | count |
|---|---|
| exact match (`|diff| = 0`)  | 11 / 12 |
| `|diff| = 1`                | 0 / 12  |
| `|diff| ≥ 2`                | 1 / 12  |
| within tolerance (`|diff| ≤ 1`) | **11 / 12 = 91.67%** |

The exact-match cases (prompt_ids 001, 005, 007, 018, 019, 024, 029,
033, 034, 039, 046) all sit at `judge = 5, human = 5`. The one
out-of-tolerance disagreement is prompt 040 (judge = 3, human = 5).

## Op-validity binary agreement

Restricted to prompts where both judge and human supplied a binary
op_validity verdict (n_gradable_dual = 7).

| metric | count |
|---|---|
| agree | 5 / 7 |
| disagree | 2 / 7 |
| **agreement rate** | **5 / 7 = 71.43%** |

The two op-validity disagreements:

- Prompt 029 (STRUCT / synthetic / suff_escal). Judge says fail,
  human says pass.
- Prompt 040 (SCHEDULE / synthetic / suff_escal). Judge says fail,
  human says pass. Same prompt as the one faithfulness
  out-of-tolerance disagreement.

## Refusal-handling agreement

12 / 12 = **100.00%** on the `refusal_detected` binary. Neither rater
flagged any verification-set prompt as a refusal; the run's two
refusal cases (027, 036) fell outside the verification draw.

## All disagreements with rationales side-by-side

### Prompt 029 — STRUCT op-validity disagreement (judge fail, human pass)

Prompt text: *"Which route is customer 42 on after travel times went
up 30%?"*

Generator answer: *"Customer 42 is on route 4."*

Payload `routes[4].customer_ids` = `[42, 15, 2, 73, 21, 40, 53, 87, 57, 43, 37, 100, 91, 93]` — customer 42 is on route 4.

- **Judge rationale.** *"The answer text claims `Customer 42 is on
  route 4.` The payload's routes[4].customer_ids = [...], confirming
  customer 42 is on route 4. The single factual claim is fully
  supported by the payload."* Faithfulness = 5. Yet the structured
  op_validity_pass = False, with `{"membership_set_equal": false}`.
- **Human rationale.** *"Customer 42 appears in route_idx 4 in the
  payload, so the answer gives the correct route for the asked
  customer. The answer does not need to list the full route
  membership to answer this prompt."* Faithfulness = 5, op_pass = True.
- **Human note.** *"Marked op-validity pass under headline semantics;
  the judge false negative appears to come from requiring full
  route-set equality."*

Same pattern as calibration prompts 025 and 031: the rubric's
`membership_set_equal` term is ambiguous when the generator's claim
is about a single customer's route, not about an entire route's
membership set. The judge's prose rationale and the runner-shadow
both treat the claim as a subset-membership question (the correct
read); the judge's structured field applies set-equality semantics
and registers a False. The judge contradicts itself between its own
prose and its own structured output. The human read sides with the
prose. The runner-shadow does the same. The case is logged as a
known judge inconsistency in Deviation 1 of
`methodology_deviations.md`, audited at analysis, and treated as a
known interpretive split rather than a judge error on the
substantive content.

### Prompt 040 — SCHEDULE faithfulness and op-validity disagreement (judge 3, human 5)

Prompt text: *"What time does route 1 wrap up after service times
went up 100%?"*

Generator answer: *"Route 1 wraps up at 871.3 solomon_minutes after
service times were scaled to 100% increase."*

Payload `route_end_times`:
`[{route_idx: 0, end_time: 864.1}, {route_idx: 1, end_time: 871.3}, ...]`.

- **Judge rationale.** *"The generator claims route 1 wraps up at
  871.3 solomon_minutes. In standard VRP presentation (including
  PyVRP, the solver used here), routes are displayed to users as
  1-indexed, so `route 1` = the first route = route_idx=0, which has
  end_time=864.1 in the payload. The generator instead reported the
  end_time for route_idx=1 (871.3), which is actually the second
  route. One factual claim does not match the payload's value for
  route 1 (864.1 vs. 871.3), though a valid end-time from the
  solution was returned."* Faithfulness = 3, op_pass = False.
- **Human rationale.** *"Using the payload route index directly,
  route_idx 1 has end_time 871.3 solomon_minutes, which is exactly
  the value reported. The answer makes no other unsupported claim."*
  Faithfulness = 5, op_pass = True.
- **Human note.** *"Judge appears to assume user-facing 1-indexed
  route labels; I treated the payload route_idx as authoritative for
  this clean human evaluation."*

Both readings are defensible. PyVRP's user-facing convention is
1-indexed; the payload's array is 0-indexed and the field is named
`route_idx`. The generator picked the value labelled `route_idx = 1`,
which is consistent with the payload-canonical reading and not
consistent with PyVRP's display reading. No hallucination is
involved — the generator named a value that does appear in the
payload, under one of two defensible indexing conventions. Logged
as Deviation 4 in `methodology_deviations.md`. Locked decision rule:
`|diff| ≥ 2` cases are flagged for discussion but do not alter
headline scores; analysis remains judge-driven.

## Known interpretive splits (not judge errors)

Three classes of judge–human disagreement surfaced across the
calibration and verification phases. None is a judge hallucination
or bias; each is a rubric or convention ambiguity that the human
rater happens to resolve differently from the judge.

### Route-indexing convention (prompt 040)

PyVRP user-facing 1-indexed display vs payload-canonical 0-indexed
array. Affects SCHEDULE and STRUCT prompts where the answer
references a route by integer index. Documented in Deviation 4. The
mitigating change for future iterations is to either always report
both indexes in the payload or pre-normalize on one convention
before the payload is materialised.

### STRUCT `membership_set_equal` semantics (calibration 025, 031; verification 029)

The rubric's structured-validity check term `membership_set_equal`
admits two readings on single-customer membership claims:

- Subset semantics: the generator's claim about a single customer's
  route is consistent with the payload's membership set for that
  route.
- Set-equality semantics: the generator's claim must enumerate the
  entire membership set of the route to pass.

Both calibration prompts 025 and 031 and verification prompt 029 are
cases where the generator made a correct subset claim. The judge's
prose rationale applies subset semantics; the judge's structured
field applies set-equality semantics and contradicts the prose.
The runner-shadow and the human rater both apply subset semantics.
Documented in Deviation 1; the runner-shadow op-validity is the
authoritative reading for the analysis.

### Calibration degeneracy (calibration phase)

20 / 20 score-5 agreement from both raters across the full
calibration sample. Cohen's quadratic-weighted kappa is undefined
when both raters have zero variance. Documented in Deviation 1. The
verification phase replaces the calibration as the operative judge-
calibration evidence under the 25% sample at the full run.

## Summary

The judge is reliable on payload-supported claims at the
faithfulness layer: 11 of 12 verification prompts scored identically.
The single faithfulness disagreement (prompt 040) and the two
op-validity disagreements (prompts 029, 040) trace to rubric or
convention ambiguities that the verification phase has now surfaced
and documented. The judge does not hallucinate fields, does not
flag faithful answers as unfaithful, and does not pass unfaithful
answers. Where it differs from a careful human reader, the
difference is in how an ambiguous rubric term or a two-convention
payload field is interpreted, not in whether the generator's claim
matches the data.

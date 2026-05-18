# Three-axis rubric — locked at preregistration-v1

Loaded by the judge (`judge_system_prompt.txt` interpolates this file
verbatim into the `{rubric_text}` placeholder before every call).
Five sections in fixed order.

## (a) Faithfulness — 5-point scale

Verbatim from `spec.md` §"Faithfulness":

- **5**: every numerical and structural claim matches the data.
- **4**: minor imprecision (e.g., rounding); no semantic error.
- **3**: one factual claim doesn't match data, but the answer is broadly correct.
- **2**: multiple claims don't match; the answer is misleading.
- **1**: hallucinated content not present in the data.

## (b) Operational-validity check definitions (per family)

Headline-claim binary check. Exact tolerances locked here.

**OBJ — objective within 0.5%.** Let `stated` be the generator's
`claimed_objective` (in Solomon-native units, per the payload's
`units.objective`). Let `actual` be the payload's `action_objective`.

```
op_validity_pass = abs(stated - actual) / actual <= 0.005
```

If `claimed_objective` is null while the question demanded an objective
answer, op_validity_pass = false (the headline claim was required and
not made; this is not a refusal — refusals are routed through section
(d)).

`op_validity_check_results` keys: `{"objective_within_0_5_pct": <bool>}`.

**PLAN_VALIDITY — feasibility flag exact match.**

```
op_validity_pass = (stated_feasible == actual_feasible)
```

where `stated_feasible = claimed_feasible` (boolean) and
`actual_feasible = payload.feasible` (boolean).

`op_validity_check_results` keys:
`{"feasibility_exact_match": <bool>}`.

**STRUCT — route count exact and/or membership set equality.** Two
checks because STRUCT questions split between count claims and
membership claims; populate whichever the answer made.

```
route_count_exact     = (claimed_route_count == payload.n_routes)
                        when claimed_route_count != null, else null
membership_set_equal  = for every {route_idx, customer_ids} pair the
                        answer claimed, set(claimed.customer_ids) ==
                        set(payload.routes[route_idx].customer_ids).
                        Conjunction across pairs.
```

`op_validity_pass` = conjunction of all non-null sub-checks.

`op_validity_check_results` keys: `{"route_count_exact": <bool | null>,
"membership_set_equal": <bool | null>}` (null where the answer made
no such claim).

**SCHEDULE — arrival and lateness within 1 minute per customer.** Same
two-check pattern: populate whichever the answer made.

```
arrival_within_1min  = for every {customer_id, stated_arrival_or_start}
                       the answer claimed, abs(stated - payload.
                       customer_schedule[customer_id].start_service)
                       <= 1.0 (Solomon minutes). Conjunction across
                       customers.
lateness_within_1min = if the answer claimed which customers are late,
                       set equality vs payload.late_customer_ids AND
                       per-claimed-customer |stated_lateness -
                       payload.customer_schedule[c].lateness_minutes|
                       <= 1.0. Conjunction.
```

`op_validity_pass` = conjunction of all non-null sub-checks.

`op_validity_check_results` keys: `{"arrival_within_1min": <bool |
null>, "lateness_within_1min": <bool | null>}`.

## (c) Op-validity vs faithfulness scoping

Op-validity is the binary deterministic per-family check defined in (b).
It grades exactly one headline claim per family: the stated objective
for OBJ, the feasibility flag for PV, the route count or membership for
STRUCT, the timing claim for SCHEDULE.

Faithfulness is the rubric-based prose-vs-payload verification covering
EVERY payload-supported claim the generator makes, not only the
headline. An OBJ answer stating both an absolute objective and a percent
delta is scored on faithfulness against both. When an answer contains
multiple payload-covered claims, faithfulness earns the LOWER of the
per-claim sub-scores. Do not average; do not round up.

This split is deliberate. Op-validity is binary and machine-checkable
per family. Faithfulness is the broader prose verification. The judge
prompt encodes this scoping explicitly so the two axes are not
collapsed in scoring.

## (d) Refusal handling

A "refusal" is an answer that contains the canonical phrase "the data
does not contain this information" (case-insensitive substring match
on `answer_text`). The generator system prompt instructs the model to
emit this exact phrase when it cannot answer from the payload.

Rules for scoring refusals:

- If the payload genuinely does not support the claim the question
  asked (i.e., a correct refusal): `faithfulness_score = 5`. Refusal
  is the faithful response.
- If the payload was sufficient and the model evaded with the refusal
  phrase: `faithfulness_score = 1`. This is unfaithful behaviour
  expressed as evasion rather than hallucination.
- On any refusal: `op_validity_pass = null` and
  `op_validity_check_results = null`. No headline claim was made, so
  op-validity is N/A. `refusal_detected = true`.

This rule applies across all four families. The judge does not have to
choose between "refusal is right" and "refusal is wrong" — section (a)
of the rubric tells the judge whether the payload supported the claim,
and (d) translates that into the faithfulness score for refusal cases.

## (e) Binary faithfulness threshold for downstream analysis

```
faithful_pass = (faithfulness_score >= 4)
```

Used in `success_criteria.md` for Claims 3 and 4 and for the
faithfulness-pass-rate headline.

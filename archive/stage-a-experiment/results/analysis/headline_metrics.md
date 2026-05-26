# Headline metrics — full-run-v1

Source: `experiment/results/joined/full-run-v1.csv` (n = 48 prompts).
Generator: Haiku 4.5 (`claude-haiku-4-5-20251001` served). Judge: Sonnet
4.6 (`claude-sonnet-4-6`). Backend: claude-code.

## Per-family table

`faith_pass_rate` is the fraction with `faithfulness_score ≥ 4`.
`op_val_pass_rate_*` denominators are gradable prompts only (excludes
refusal contexts and non-gradable cells per the rubric).

| family | n | mean_faithfulness | faith_pass_rate (≥4) | op_val_pass_rate_judge | op_val_pass_rate_runner_shadow |
|---|---|---|---|---|---|
| OBJ           | 12 | 5.000 | 12/12 = 1.000 | 5/7 = 0.714 | 5/7 = 0.714 |
| PLAN_VALIDITY | 12 | 5.000 | 12/12 = 1.000 | 4/4 = 1.000 | 4/4 = 1.000 |
| STRUCT        | 12 | 4.917 | 12/12 = 1.000 | 5/8 = 0.625 | 7/8 = 0.875 |
| SCHEDULE      | 12 | 4.833 | 11/12 = 0.917 | 11/12 = 0.917 | 10/12 = 0.833 |
| **overall**   | **48** | **4.938** | **47/48 = 0.979** | **25/31 = 0.806** | **26/31 = 0.839** |

Faithfulness distribution across all 48: `3 → 1`, `4 → 1`, `5 → 46`.
Both sub-5 scores come from a single prompt each (040 SCHEDULE; 025
STRUCT). All other 46 prompts scored 5.

## Per-quadrant counts and mean faithfulness

| quadrant | n | mean_faithfulness |
|---|---|---|
| suff_accept   | 11 | 4.909 |
| suff_escal    | 12 | 4.833 |
| insuff_accept | 12 | 5.000 |
| insuff_escal  | 13 | 5.000 |

Insufficient cells scored higher than sufficient cells. This inverts
the direction Claim 3 anticipated. Sub-5 faithfulness scores only
appear on sufficient cells (one suff_accept, one suff_escal). The
mechanism is documented under Claim 3 in `claim_evaluations.md` and
recurs in `failure_modes.md`.

### Family × quadrant cell counts

| | suff_accept | suff_escal | insuff_accept | insuff_escal |
|---|---|---|---|---|
| OBJ           | 3 | 3 | 3 | 3 |
| PLAN_VALIDITY | 3 | 3 | 3 | 3 |
| STRUCT        | 3 | 3 | 3 | 3 |
| SCHEDULE      | 2 | 3 | 3 | 4 |

The SCHEDULE row deviates from the 3+3+3+3 ideal because Homberger
SCHEDULE stratification is escalate-only (per the locked stratification
spec): SCHEDULE prompts on Homberger could only land in suff_escal or
insuff_escal. The total per family is 12 in every case.

## Judge vs runner-shadow op-validity — per-prompt disagreements

Three prompts split. Two on STRUCT, one on SCHEDULE.

### Prompt 029 (STRUCT / synthetic / suff_escal) — judge fails, runner passes

- Judge: `{"membership_set_equal": false}` → op_pass = False.
- Runner: `{"membership_set_equal": true}` → op_pass = True.
- Cause: the rubric's `membership_set_equal` term is ambiguous on
  single-customer membership claims. The runner applies subset
  semantics on the generator's narrow claim against the full payload
  membership; the judge applies set-equality semantics. This is the
  same internal-contradiction pattern flagged in Deviation 1 of
  `methodology_deviations.md` (the STRUCT-2 set-semantics ambiguity).
  Verification on prompt 029 sided with the runner (human marked
  op_pass = True).

### Prompt 031 (STRUCT / synthetic / insuff_accept) — judge fails, runner passes

- Same `membership_set_equal` ambiguity. The judge's structured field
  flags the generator's correct single-customer claim as a set-
  inequality fail; the runner does not. This is the second instance
  of the same pattern documented in Deviation 1.

### Prompt 041 (SCHEDULE / synthetic / suff_escal) — judge passes, runner fails

- Judge: `{"arrival_within_1min": true}` → op_pass = True.
- Runner: `{"arrival_within_1min": false}` → op_pass = False.
- Cause: route-indexing convention. The generator's answer references
  a route by index in a way that admits two readings — PyVRP's
  user-facing 1-indexed display vs the payload's 0-indexed array.
  The runner applies one convention, the judge applies the other.
  Same convention dispute that drove the verification disagreement
  on prompt 040 (Deviation 4 of `methodology_deviations.md`).

The runner_shadow rate is the authoritative op-validity number for
the analysis. The judge rate is reported alongside as comparison.
Where they differ, the cause is documented above — both
disagreements trace back to a rubric or convention ambiguity that
has been logged as a methodology deviation, not to judge unreliability
on the substantive content.

## Refusal counts

Two refusals across the 48-prompt run, both runner-detected and
judge-detected (refusal agreement 100%):

- Prompt 027 (STRUCT / suff_accept / llm_generated): generator refused
  on a STRUCT membership question the payload could in principle have
  answered but did not surface the needed field. Refusal scored
  faithfulness = 5.
- Prompt 036 (STRUCT / insuff_escal / llm_generated, Homberger):
  refusal on insufficient cell. Scored faithfulness = 5.

Refusals were all on STRUCT and all on llm_generated source.

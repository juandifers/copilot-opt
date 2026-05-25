# Three-axis joint distribution — full-run-v1

Three binary axes per prompt:

- **faith_pass**: `faithfulness_score ≥ 4`
- **sufficient**: `sufficiency_label == sufficient`
- **op_pass**: `op_validity_pass == True`

`op_pass` is undefined on non-gradable prompts (the rubric's
`op_validity_gradable=False` set: prompts whose answers don't admit a
runner-checkable claim — refusal cells, suff_escal cells where the
generator escalated, and family-quadrant combinations where no
structured claim applies). Non-gradable prompts appear in the joint as
`op = n/a`. They are not failures; they are cells where the axis
doesn't fire.

Two parallel tables follow: one using **runner-shadow** op-validity (the
authoritative measure for the analysis), one using **judge**
op-validity. They match on the joint distribution counts but diverge
on which specific prompts populate three of the cells (per the
disagreements documented in `headline_metrics.md`).

## Per-family joint distribution (runner-shadow)

Each table row is one cell. Columns are: faith_pass / sufficient /
op_pass / n / prompt_ids.

### OBJ (n=12)

| f_pass | suff | op_pass | n | prompt_ids |
|---|---|---|---|---|
| T | T | T   | 3 | 001, 003, 006 |
| T | T | F   | 1 | 002 |
| T | T | n/a | 2 | 004, 005 |
| T | F | T   | 2 | 009, 012 |
| T | F | F   | 1 | 010 |
| T | F | n/a | 3 | 007, 008, 011 |

### PLAN_VALIDITY (n=12)

| f_pass | suff | op_pass | n | prompt_ids |
|---|---|---|---|---|
| T | T | T   | 3 | 013, 015, 016 |
| T | T | n/a | 3 | 014, 017, 018 |
| T | F | T   | 1 | 019 |
| T | F | n/a | 5 | 020, 021, 022, 023, 024 |

### STRUCT (n=12)

| f_pass | suff | op_pass | n | prompt_ids |
|---|---|---|---|---|
| T | T | T   | 4 | 026, 028, 029, 030 |
| T | T | F   | 1 | 025 |
| T | T | n/a | 1 | 027 |
| T | F | T   | 3 | 031, 032, 034 |
| T | F | n/a | 3 | 033, 035, 036 |

### SCHEDULE (n=12)

| f_pass | suff | op_pass | n | prompt_ids |
|---|---|---|---|---|
| T | T | T   | 3 | 037, 038, 039 |
| T | T | F   | 1 | 041 |
| F | T | F   | 1 | 040 |
| T | F | T   | 7 | 042, 043, 044, 045, 046, 047, 048 |

## Aggregate (n=48)

### Runner-shadow

| f_pass | suff | op_pass | n |
|---|---|---|---|
| T | T | T   | 13 |
| T | T | F   | 3  |
| T | T | n/a | 6  |
| T | F | T   | 13 |
| T | F | F   | 1  |
| T | F | n/a | 11 |
| F | T | T   | 0  |
| F | T | F   | 1  |
| F | T | n/a | 0  |
| F | F | T   | 0  |
| F | F | F   | 0  |
| F | F | n/a | 0  |
| **total** | | | **48** |

### Judge (parallel table)

| f_pass | suff | op_pass | n |
|---|---|---|---|
| T | T | T   | 13 |
| T | T | F   | 3  |
| T | T | n/a | 6  |
| T | F | T   | 12 |
| T | F | F   | 2  |
| T | F | n/a | 11 |
| F | T | T   | 0  |
| F | T | F   | 1  |
| F | T | n/a | 0  |
| F | F | T   | 0  |
| F | F | F   | 0  |
| F | F | n/a | 0  |
| **total** | | | **48** |

The runner-vs-judge totals differ by one cell: runner places the
STRUCT membership-ambiguity prompts (029, 031) in `op_pass=True`,
while judge places them in `op_pass=False`. The SCHEDULE
route-indexing prompt (041) goes the other way: runner says fail,
judge says pass. Net effect on the aggregate count is +1 / -1 on
the `T/F/T` vs `T/F/F` cells.

## Mixed patterns (Claim 1 evidence)

A prompt is "mixed" if it is neither all-three-axes-pass nor all-three-
axes-fail. Non-gradable (`op = n/a`) prompts are counted mixed when
`faith_pass ≠ sufficient`.

| reading | mixed | total | fraction |
|---|---|---|---|
| runner-shadow | 29 | 48 | 0.604 |
| judge         | 29 | 48 | 0.604 |

The pre-registered Claim 1 threshold is ≥ 0.10 mixed. The observed
0.60 clears it by roughly six times. The dominant mixed pattern is
`(faith_pass=T, suff=F, op_pass=T)` — insufficient cells where the
generator answered correctly from a sufficient sub-claim or refused
appropriately. The framework was designed to surface exactly this
pattern: faithfulness can be high on an insufficient-cell answer
because the generator either refused or pulled a legitimate
sub-answer; sufficiency remains low because the underlying data does
not support the full operational claim.

The cells the joint distribution does not populate are also
informative. Zero prompts in `(F, F, F)`, zero in `(F, F, T)`, and
zero in `(F, T, T)`. The generator does not produce the "faithfully
wrong" pattern that a noisier generator might. The one `(F, T, F)`
prompt (040, SCHEDULE) is the route-indexing convention case where
judge and human disagree on whether the answer was even wrong —
covered in `judge_human_agreement.md` and `failure_modes.md`.

The axes are not collinear in this run. The pattern that demonstrates
non-collinearity is concentrated in the insufficient-but-faithful
region, which is the expected mode for a generator behaving as
designed: the three-axis decomposition surfaces "the prompt was
under-specified, the generator was correct about that, and the
operational claim does not register" as a distinct cell rather than
collapsing it into a single pass-or-fail verdict.

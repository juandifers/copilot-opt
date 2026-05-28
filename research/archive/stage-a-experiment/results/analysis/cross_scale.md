# Cross-scale — Solomon (100) vs Homberger (200)

Solomon-100 prompts: n = 36 (9 per family).
Homberger-200 prompts: n = 12 (3 per family).

## Aggregate

| dataset | n | mean_faithfulness |
|---|---|---|
| Solomon (100 customers)   | 36 | 4.917 |
| Homberger (200 customers) | 12 | 5.000 |

**Faithfulness drop from Solomon → Homberger: −0.083** (Homberger
is higher by 0.083).

The pre-registered threshold for Claim 4 is a drop of at most 0.5.
The observed direction inverts. Claim 4 PASSES.

## Per-family Solomon vs Homberger

| family | Solomon n | Solomon mean_f | Solomon op_pass | Homberger n | Homberger mean_f | Homberger op_pass |
|---|---|---|---|---|---|---|
| OBJ           | 9 | 5.000 | 2/4 | 3 | 5.000 | 3/3 |
| PLAN_VALIDITY | 9 | 5.000 | 3/3 | 3 | 5.000 | 1/1 |
| STRUCT        | 9 | 4.889 | 6/7 | 3 | 5.000 | 1/1 |
| SCHEDULE      | 9 | 4.778 | 8/9 | 3 | 5.000 | 2/3 |

No family produces a Homberger drop. STRUCT and SCHEDULE both
register a small Homberger lift, driven by the absence of the
sub-5 prompts (025 STRUCT and 040 SCHEDULE both fell on Solomon).

## The stratification caveat for SCHEDULE

Per the locked stratification spec (`experiment/configs/stratification.md`),
Homberger SCHEDULE prompts are escalate-only. The Homberger n = 3
SCHEDULE prompts decompose as:

| quadrant | n |
|---|---|
| suff_escal   | 1 |
| insuff_escal | 2 |

The `suff_accept` and `insuff_accept` quadrants are absent. Solomon
SCHEDULE has prompts in all four quadrants. The Solomon SCHEDULE
mean (4.778) is pulled down by prompts 040 (suff_escal, f = 3) and
041 (suff_escal, op-validity fail at f = 5); the Homberger SCHEDULE
prompts did not draw those quadrant combinations. The cross-scale
comparison for SCHEDULE is therefore not a clean per-family
contrast — the quadrant compositions differ by stratification.

A composition-matched reading: restrict Solomon SCHEDULE to the
same three quadrants Homberger SCHEDULE covers (`suff_escal` and
`insuff_escal`). Solomon SCHEDULE on those two quadrants is
n = 5 (1 suff_escal-Solomon was prompt 040 at f = 3; 1 was 041 at
f = 5; 3 were on insuff_escal at f = 5). Mean = (3 + 5 + 5 + 5 + 5)
/ 5 = 4.6. Homberger SCHEDULE on the same two quadrants is 5.000.
Composition-matched drop: −0.4 (Homberger higher).

This composition-matched reading still passes Claim 4. It also
weakens the cross-scale claim as a stress test, because Haiku's
sub-5 scores on SCHEDULE happen to land on a quadrant the Homberger
sample does not exercise.

## Per-family Homberger quadrant coverage

OBJ, PLAN_VALIDITY, and STRUCT each draw `suff_accept`, `suff_escal`,
`insuff_escal` on Homberger (no `insuff_accept`). SCHEDULE draws
`suff_escal` and `insuff_escal` only. None of the four families has
a Homberger `insuff_accept` cell. This is a feature of the locked
stratification, not a bug of the run.

## Instance-class effect (descriptive)

| instance_class | n | mean_faithfulness |
|---|---|---|
| C   | 21 | 4.952 |
| R   | 12 | 5.000 |
| RC  | 15 | 4.867 |

The R class (random customer locations, wide time windows) scores
highest. The RC class (mixed clustered/random with tight windows)
scores lowest. The single faithfulness 3 in the run (prompt 040)
falls on RC202; the single faithfulness 4 (prompt 025) falls on
C104. Both are Solomon. With n = 12 to 21 per class and a tight
faithfulness distribution, the differences are descriptive only.

## What Claim 4 actually showed

Haiku at 200-customer scale held its faithfulness ceiling on this
payload format. The framing-note expectation was that hallucination
rates would rise with longer route lists; they did not. Two
possible reasons:

1. The payload format compresses route information into a structured
   list of `route_idx` + `customer_ids` pairs that does not get
   harder to read as the number of routes grows. The generator can
   pick the right entry by integer index whether there are 8 routes
   or 20.
2. The Homberger sample is small (n = 3 per family) and skewed
   toward escalate cells where the generator's conservative pattern
   keeps faithfulness at ceiling regardless of payload size.

Both are consistent with the observed numbers. Distinguishing them
requires either a larger Homberger sample or a deliberate
adversarial Homberger prompt set. Future iterations should expand
the Homberger draw or design a per-family Homberger stress sample
that is matched on quadrant composition to the Solomon sample.

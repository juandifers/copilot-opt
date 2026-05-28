# Prompt-set stratification — locked at preregistration-v1

48 prompts total. 12 per claim family. 9 from Solomon + 3 from
Homberger per family. Source mix 50/50 synthetic / LLM-generated within
each family (6 + 6 per family).

Sampling is deterministic with `seed = 2026` (random.Random(2026) at
the top of the prompt-set construction script in Prompt 5; the seed
flows through both quadrant-level cell selection and the
synthetic-vs-LLM-generated assignment).

## Cell-count audit (from `experiment/discovery_report.md` §3)

Reproduced here so the sampling rule is self-contained.

**Stage A (Solomon, n=896 cells per family after cheap-action filter):**

| family | suff×accept | suff×escalate | insuff×accept | insuff×escalate |
| --- | --- | --- | --- | --- |
| OBJ | 796 | 17 | 18 | 58 |
| PV | 326 | 78 | 81 | 411 |
| STRUCT | 198 | 299 | 12 | 380 |
| SCHEDULE | 45 | 324 | 4 | 516 |

**Homberger (n=80 cells per family after cheap-action filter):**

| family | suff×accept | suff×escalate | insuff×accept | insuff×escalate |
| --- | --- | --- | --- | --- |
| OBJ | 57 | 3 | 3 | 11 |
| PV | 11 | 13 | 8 | 48 |
| STRUCT | 3 | 26 | 2 | 43 |
| **SCHEDULE** | **0** | **45** | **0** | **29** |

Bolded SCHEDULE Homberger row is the deployment-configuration asymmetry
the locked sampling rule below handles explicitly.

## Solomon sampling (9 per family)

`spec.md` v1.0 nominally calls for 3-per-quadrant × 4 quadrants = 12 on
Solomon. The locked count is 9 Solomon + 3 Homberger = 12 per family;
to keep all four Solomon quadrants represented while honouring the
9-on-Solomon allocation, the distribution is **3 + 2 + 2 + 2** across
the four quadrants. The "3" goes to `insuff_accept` (the false-positive
quadrant), because that is the quadrant where the predictor's mistake
is most consequential for language-level outcomes and where Claim 2's
"policy-accepts vs policy-escalates on insufficient cells" contrast
draws its primary signal. The remaining three quadrants get 2 each.

Per family, Solomon sampling:

```
OBJ:      suff_accept=2, suff_escal=2, insuff_accept=3, insuff_escal=2
PV:       suff_accept=2, suff_escal=2, insuff_accept=3, insuff_escal=2
STRUCT:   suff_accept=2, suff_escal=2, insuff_accept=3, insuff_escal=2
SCHEDULE: suff_accept=2, suff_escal=2, insuff_accept=3, insuff_escal=2
```

Cell-count vs sample-count: every quadrant has ≥4 cells on Solomon
across all four families (smallest is SCHEDULE × insuff_accept = 4 ≥ 3).
Sampling without replacement is straightforward.

Per quadrant, sample with `random.Random(2026)`:

```
cells = sorted(quadrant_cells, key=lambda c: (c.instance_id, c.perturbation_id))
chosen = random.Random(2026 + hash_index(family, quadrant)).sample(cells, k)
```

where `hash_index` is a fixed deterministic offset per (family,
quadrant) pair so the same seed gives the same selection across runs.
The pair → offset mapping is locked in `experiment/src/build_prompts.py`
at Prompt 5; the offset is `family_idx * 4 + quadrant_idx` with
`family_idx` in `[OBJ=0, PLAN_VALIDITY=1, STRUCT=2, SCHEDULE=3]` and
`quadrant_idx` in `[suff_accept=0, suff_escal=1, insuff_accept=2,
insuff_escal=3]`.

## Homberger sampling (3 per family)

Each family handles its quadrant-availability differently per the
audit. Locked rules below.

**OBJ — all 4 quadrants populated.** Distribute 3 prompts as 1+1+1+0,
dropping `insuff_accept` (n=3, smallest at-3 quadrant; tied with
`suff_escal` which gets kept because the FN quadrant has higher
analytical value for Claim 2). Final: `suff_accept=1, suff_escal=1,
insuff_accept=0, insuff_escal=1`.

**PV — all 4 quadrants populated.** Distribute 3 prompts as 1+1+1+0,
dropping `insuff_accept` (n=8, smallest populated quadrant). Final:
`suff_accept=1, suff_escal=1, insuff_accept=0, insuff_escal=1`.

**STRUCT — 3 quadrants viable (insuff_accept has only 2 cells which is
below the 3-per-quadrant nominal but adequate for 1).** Distribute 3
prompts as 1+1+0+1, sampling 1 from each of `suff_accept`,
`suff_escal`, `insuff_escal`; `insuff_accept` gets 0. Alternative
1+1+1+0 would force sampling 1 from `insuff_accept`'s 2 cells which is
defensible but reduces statistical headroom; the locked choice keeps
3 distinct cells.

**SCHEDULE — only 2 quadrants populated.** Distribute 3 prompts as
0+1+0+2 — `suff_escal=1, insuff_escal=2`. The accept quadrants get
zero on Homberger SCHEDULE as a property of the deployment
configuration (the predictor at the locked SCHEDULE threshold of 0.98
never accepts a Homberger SCHEDULE cell). The 1+2 split puts one
prompt in the FN quadrant (sufficient×escalate, the "predictor wrongly
escalated" case) and two in the TN quadrant (insufficient×escalate,
the "predictor correctly escalated" case), maximising informational
value given the cell availability.

This SCHEDULE-on-Homberger asymmetry is **documented as a feature of
the deployment configuration, not a sampling failure**. The analysis
section reports Claim 4 (cross-scale) for SCHEDULE with the asymmetry
explicit — comparing Stage A across all 4 quadrants vs Homberger
across only the 2 escalate quadrants is an apples-to-oranges contrast
the writeup must surface.

Per quadrant, sample with the same deterministic rule as Solomon, with
seed offset `100 + family_idx * 4 + quadrant_idx` to keep Solomon and
Homberger draws independent.

## Synthetic vs LLM-generated split (within each family)

Per family: 12 prompts. 6 synthetic (hand-written templates), 6
LLM-generated (frontier-LLM paraphrases of the synthetic templates,
manually filtered).

Within each family, the split is independent of the quadrant
assignment: after the 12 cells are selected via the rules above,
6 of them are randomly assigned source=synthetic and 6 source=llm_generated
using `random.Random(2026 + family_idx).shuffle(...)` on the 12-cell
list, then taking the first 6 for synthetic and the rest for
LLM-generated.

Synthetic templates and LLM-generation prompts are locked separately
in Prompt 5 (the prompt-set construction commit). This file documents
only the size and split rules.

## Final 4 × 12 stratification table

| family | suff×accept | suff×escalate | insuff×accept | insuff×escalate | total Solomon | total Homberger |
| --- | --- | --- | --- | --- | --- | --- |
| OBJ | 3 (S) + 1 (H) | 2 (S) + 1 (H) | 3 (S) + 0 (H) | 2 (S) + 1 (H) | 10 → 9 | 3 → 3 |
| PV | 3 + 1 | 2 + 1 | 3 + 0 | 2 + 1 | 10 → 9 | 3 → 3 |
| STRUCT | 3 + 1 | 2 + 1 | 3 + 0 | 2 + 1 | 10 → 9 | 3 → 3 |
| SCHEDULE | 3 + 0 | 2 + 1 | 3 + 0 | 2 + 2 | 10 → 9 | 3 → 3 |

Wait — the "3 + 1 = 10 → 9" needs reconciliation. The Solomon
allocation above was 3+2+2+2 = 9 (not 3+2+3+2 = 10). Correcting the
table:

| family | Solomon suff×accept | Solomon suff×escalate | Solomon insuff×accept | Solomon insuff×escalate | Homberger suff×accept | Homberger suff×escalate | Homberger insuff×accept | Homberger insuff×escalate | total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OBJ | 2 | 2 | 3 | 2 | 1 | 1 | 0 | 1 | 12 |
| PV | 2 | 2 | 3 | 2 | 1 | 1 | 0 | 1 | 12 |
| STRUCT | 2 | 2 | 3 | 2 | 1 | 1 | 0 | 1 | 12 |
| SCHEDULE | 2 | 2 | 3 | 2 | 0 | 1 | 0 | 2 | 12 |

OBJ and PV and STRUCT each have one Homberger quadrant set to 0
(`insuff_accept`); SCHEDULE has both Homberger accept quadrants set to
0. Solomon stays at 9 = 2+2+3+2 in every family.

Total: 12 × 4 = 48 prompts.

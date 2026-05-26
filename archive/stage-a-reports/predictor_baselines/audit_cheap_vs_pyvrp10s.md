# Audit: cheap-vs-`pyvrp_10s` pointwise dominance

Joined the cheap-action row and the `pyvrp_10s` row for every cell ×
claim_family on the Stage A long table and computed the 2×2 contingency
table of (cheap_sufficient, py10_sufficient).

## Sanity

| count                              | n     |
| ---------------------------------- | ----- |
| Joined cells × claim_family        | 3 584 |
| Both labels non-NaN (audit subset) | 3 563 |
| NaN in **cheap** only              | 0     |
| NaN in **pyvrp_10s** only          | 0     |
| NaN in both                        | 21    |

The 21 cells where both labels are NaN line up with the 7 all-infeasible
cells (reference invalid) × 3 affected claim families (OBJ / STRUCT /
SCHEDULE). PLAN_VALIDITY is defined on all 896 cells by construction.

## Overall 2×2 (n = 3 563)

|                    | py10 = 1 | py10 = 0 |
| ------------------ | -------- | -------- |
| **cheap = 1**      | 2 029    | **54**   |
| **cheap = 0**      | 1 320    | 160      |

- 2 083 cells (58.5 %) — cheap already sufficient.
- 1 320 cells (37.1 %) — cheap insufficient but `pyvrp_10s` rescues it.
- 160 cells (4.5 %) — both insufficient.
- **54 cells (1.5 %) — cheap is sufficient and `pyvrp_10s` is not.**
  This is the only quadrant that breaks monotonicity, and it explains
  exactly the oracle-vs-always-pyvrp_10s gap (see below).

## By claim_family

| claim_family   | n   | c=1,p=1 | c=1,p=0 | c=0,p=1 | c=0,p=0 |
| -------------- | --- | ------- | ------- | ------- | ------- |
| OBJ            | 889 | 813     | **0**   | 76      | 0       |
| PLAN_VALIDITY  | 896 | 404     | **0**   | 485     | 7       |
| SCHEDULE       | 889 | 347     | **22**  | 448     | 72      |
| STRUCT         | 889 | 465     | **32**  | 311     | 81      |

Non-monotonicity is **entirely** concentrated in STRUCT and SCHEDULE.
OBJ and PLAN_VALIDITY satisfy strict pointwise dominance — anywhere the
cheap action is sufficient, `pyvrp_10s` is too.

## By perturbation_family

| perturbation_family | n   | c=1,p=1 | c=1,p=0 | c=0,p=1 | c=0,p=0 |
| ------------------- | --- | ------- | ------- | ------- | ------- |
| ORDER_CHANGE        | 887 | 537     | 12      | 294     | 44      |
| SERVICE_TIME        | 896 | 444     | 20      | 397     | 35      |
| TIME_WINDOW         | 896 | 523     | 10      | 315     | 48      |
| TRAVEL_TIME         | 884 | 525     | 12      | 314     | 33      |

## By claim_family × perturbation_family

| claim          | pert         | n   | c=1,p=1 | c=1,p=0 | c=0,p=1 | c=0,p=0 |
| -------------- | ------------ | --- | ------- | ------- | ------- | ------- |
| OBJ            | ORDER_CHANGE | 221 | 190     | 0       | 31      | 0       |
| OBJ            | SERVICE_TIME | 224 | 185     | 0       | 39      | 0       |
| OBJ            | TIME_WINDOW  | 224 | 224     | 0       | 0       | 0       |
| OBJ            | TRAVEL_TIME  | 220 | 214     | 0       | 6       | 0       |
| PLAN_VALIDITY  | ORDER_CHANGE | 224 | 150     | 0       | 71      | 3       |
| PLAN_VALIDITY  | SERVICE_TIME | 224 | 75      | 0       | 149     | 0       |
| PLAN_VALIDITY  | TIME_WINDOW  | 224 | 90      | 0       | 134     | 0       |
| PLAN_VALIDITY  | TRAVEL_TIME  | 224 | 89      | 0       | 131     | 4       |
| SCHEDULE       | ORDER_CHANGE | 221 | 88      | 6       | 107     | 20      |
| SCHEDULE       | SERVICE_TIME | 224 | 72      | 9       | 126     | 17      |
| SCHEDULE       | TIME_WINDOW  | 224 | 89      | 3       | 110     | 22      |
| SCHEDULE       | TRAVEL_TIME  | 220 | 98      | 4       | 105     | 13      |
| STRUCT         | ORDER_CHANGE | 221 | 109     | 6       | 85      | 21      |
| STRUCT         | SERVICE_TIME | 224 | 112     | 11      | 83      | 18      |
| STRUCT         | TIME_WINDOW  | 224 | 120     | 7       | 71      | 26      |
| STRUCT         | TRAVEL_TIME  | 220 | 124     | 8       | 72      | 16      |

## Why `oracle` beats `always_pyvrp_10s` (3 decimal arithmetic)

- `always_pyvrp_10s` final correctness = `(py10==1)/N` = `3349/3563` = **0.940**
- `oracle_cheap_sufficiency` full-routing final correctness =
  `(cheap==1 ∨ py10==1)/N` = `3403/3563` = **0.955**
- Difference = **54 / 3563 = +0.015**

Those 54 cells are exactly the (`cheap=1`, `py10=0`) quadrant: oracle
accepts cheap and gets the label for free; `always_pyvrp_10s` runs the
solver and lands on a plan that misses the band cutoff for STRUCT or
SCHEDULE. The arithmetic is exact and matches the headline numbers in
`baseline_policy_overall.csv`.

## Representative non-monotone examples (cheap = 1, pyvrp_10s = 0)

Saved in full at `audit_cheap_dominates_pyvrp10s_examples.csv` (n = 54).

```
STRUCT, ORDER_CHANGE   (n = 6)   — e.g. R111/OC_2, RC101/OC_1
STRUCT, SERVICE_TIME   (n = 11)  — e.g. R107/ST_1, R201/ST_1
STRUCT, TIME_WINDOW    (n = 7)
STRUCT, TRAVEL_TIME    (n = 8)
SCHEDULE, ORDER_CHANGE (n = 6)
SCHEDULE, SERVICE_TIME (n = 9)
SCHEDULE, TIME_WINDOW  (n = 3)
SCHEDULE, TRAVEL_TIME  (n = 4)
```

For these rows the cheap-action loss is 0 (or near 0) and `pyvrp_10s`'s
loss lands in `medium` (0.10 – 0.30 for STRUCT) or `hard` (> 0.30 for
STRUCT, > some_cutoff for SCHEDULE). Both actions are feasible in every
non-monotone row — this is not an infeasibility artefact.

### Why this is legitimate, not a label/alignment bug

- The cheap actions for these three families are `reuse_direct`. For
  SERVICE_TIME, TIME_WINDOW, and TRAVEL_TIME the baseline plan very
  often stays feasible under the perturbation, so `reuse_direct` is
  literally the **baseline** assignment.
- The STRUCT and SCHEDULE losses are computed against the **reference**
  (`pyvrp_60s_reference`, seed 1). The reference solver, given 60 s
  from scratch, frequently lands near the baseline basin on these
  perturbations — so `1 – ARI(baseline, reference)` is `0` and the
  cheap row scores `easy`.
- `pyvrp_10s`, given only 10 s from scratch and a different random
  seed, can find a different feasible local optimum that is **not**
  the same as the baseline / reference basin. The ARI between
  `pyvrp_10s`'s plan and the reference drops; `loss_struct` lands in
  the `medium` / `hard` band; the SCHEDULE shift between solver-chosen
  start times and the reference's start times exceeds the cutoff.
- This is exactly the structural-loss design: "1 − ARI against the
  reference partition", not "is this plan good in isolation". A
  diverse-but-feasible plan can score worse than the baseline plan
  even when the baseline plan is itself fine.
- The action-alignment is correct on both sides: cheap rows are the
  protocol cheap (`reuse_direct` for non-OC, `local_repair_insert` for
  OC); `pyvrp_10s` rows are tier 3 `pyvrp_10s`; both are joined on the
  same cell × claim_family keys.

So the non-monotonicity is real: more compute (10 s) is not a
super-set of less compute (`reuse_direct`) under reference-anchored
STRUCT and SCHEDULE losses. Any predictor that wants to beat
`oracle_cheap_sufficiency` would need to know, on these 54 cells, that
the cheap action is already sufficient and **not** escalate to
`pyvrp_10s`. That is exactly the kind of signal a learned predictor
might pick up but a categorical block-rule policy cannot.

## Files

- `audit_cheap_vs_pyvrp10s_dominance.csv` — every 2×2 in long form.
- `audit_cheap_dominates_pyvrp10s_examples.csv` — all 54 non-monotone rows.

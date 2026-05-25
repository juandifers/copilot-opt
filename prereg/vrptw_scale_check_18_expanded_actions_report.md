# VRPTW 18-instance expanded-action scale-check report

## 1. Purpose

This phase tests an expanded action ladder before any 56-instance full benchmark. The previous 18-instance scale-check survived but the action set (reuse / local repair) was too thin for a strong compute-aware benchmark. Here we add three middle/reference rungs so the benchmark can answer: *given a disruption and a claim family, which level of computational response is sufficient?*

## 2. Action ladder

| tier | action | role |
|---|---|---|
| 0 | `reuse_direct` | score baseline routes unchanged under the perturbed instance |
| 1 | `local_repair_insert` | OC-only — cheapest-feasible-insertion of new customers into the existing routes |
| 2 | `cheap_fresh_construct` | deterministic build-from-scratch insertion heuristic; ignores baseline; prebuilt-ProblemData fast path preserves the heuristic |
| 3 | `pyvrp_10s` | PyVRP metaheuristic, seed=1, 10 s budget |
| 4 | `pyvrp_60s_reference` | materialized from reference seed 1 (60 s budget) — no extra solve |

The cheap-action rule is unchanged: non-OC families use `reuse_direct` (tier 0); ORDER_CHANGE uses `local_repair_insert` (tier 1).

## 3. Dataset and setup

- **Instances** (18): C101, C102, C103, C201, C202, C203, R101, R102, R103, R201, R202, R203, RC101, RC102, RC103, RC201, RC202, RC203
- **Perturbations** (16): TT_1, TT_2, TT_3, TT_4, TW_1, TW_2, TW_3, TW_4, ST_1, ST_2, ST_3, ST_4, OC_1, OC_2, OC_3, OC_4 (soft_grid magnitudes)
- **Seeds**: 1, 2, 3 (per perturbation cell)
- **Reference time limit per solve**: 60s
- **pyvrp_10s time limit**: 10s
- **n_jobs**: 6
- **Total wall-clock**: 9184.8s
- **Wide rows**: 1224
- **Long claim rows**: 4896
- **Expected wide rows**: 1224 (non-OC × 4 actions + OC × 5 actions) — OK
- **Expected long rows**: 4896 — OK

## 4. Data-quality checks

- Cells where all 3 reference seeds feasible: 1202 / 1224
- Cells with any reference infeasible: 22 / 1224
- Wide rows with `band_obj_distance=n/a`: 22
- Wide rows with `band_struct=n/a`:        22
- Wide rows with `band_schedule=n/a`:      22
- Action failures (action_valid=False) by action:
    - `reuse_direct`: 202 / 288
    - `local_repair_insert`: 36 / 72
    - `cheap_fresh_construct`: 5 / 288
    - `pyvrp_10s`: 5 / 288
    - `pyvrp_60s_reference`: 5 / 288

## 5. Reference stability

- `reference_obj_unstable` rate: 0.000
- `reference_struct_unstable` rate: 0.194
- median `reference_ari_min`: 1.000
- By perturbation family (obj_unstable, struct_unstable):
    - ORDER_CHANGE: obj=0.000  struct=0.181
    - SERVICE_TIME: obj=0.000  struct=0.236
    - TIME_WINDOW: obj=0.000  struct=0.153
    - TRAVEL_TIME: obj=0.000  struct=0.208

## 6. Action quality by claim family

Band counts in the long claim table, by action × claim family:

### OBJ

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 249 | 27 | 7 | 5 |
| `local_repair_insert` | 60 | 10 | 0 | 2 |
| `cheap_fresh_construct` | 0 | 19 | 264 | 5 |
| `pyvrp_10s` | 283 | 0 | 0 | 5 |
| `pyvrp_60s_reference` | 283 | 0 | 0 | 5 |

### PLAN_VALIDITY

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 86 | 0 | 202 | 0 |
| `local_repair_insert` | 36 | 0 | 36 | 0 |
| `cheap_fresh_construct` | 283 | 0 | 5 | 0 |
| `pyvrp_10s` | 283 | 0 | 5 | 0 |
| `pyvrp_60s_reference` | 283 | 0 | 5 | 0 |

### STRUCT

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 177 | 48 | 58 | 5 |
| `local_repair_insert` | 34 | 24 | 12 | 2 |
| `cheap_fresh_construct` | 0 | 35 | 248 | 5 |
| `pyvrp_10s` | 245 | 19 | 19 | 5 |
| `pyvrp_60s_reference` | 283 | 0 | 0 | 5 |

### SCHEDULE

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 137 | 70 | 76 | 5 |
| `local_repair_insert` | 38 | 20 | 12 | 2 |
| `cheap_fresh_construct` | 22 | 54 | 207 | 5 |
| `pyvrp_10s` | 254 | 8 | 21 | 5 |
| `pyvrp_60s_reference` | 283 | 0 | 0 | 5 |

## 7. Runtime by action

`action_runtime_s` distribution per action:

| action | n | mean (s) | median (s) | p90 (s) | max (s) |
|---|---:|---:|---:|---:|---:|
| `reuse_direct` | 288 | 0.002 | 0.001 | 0.002 | 0.076 |
| `local_repair_insert` | 72 | 0.291 | 0.282 | 0.474 | 0.503 |
| `cheap_fresh_construct` | 288 | 0.122 | 0.105 | 0.227 | 0.280 |
| `pyvrp_10s` | 288 | 10.008 | 10.007 | 10.011 | 10.041 |
| `pyvrp_60s_reference` | 288 | 60.008 | 60.007 | 60.011 | 60.077 |

## 8. Cost/quality ladder

For each claim family, the table shows the mean primary loss and the `sufficient_binary` rate (band ∈ {easy} ⇒ 1; medium/hard ⇒ 0; n/a ⇒ null and excluded from the rate) per action. A meaningful ladder shows monotonically decreasing loss and rising sufficiency as the tier rises.

### OBJ

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 288 | 0.0219 | 0.880 |
| `local_repair_insert` | 72 | 0.0220 | 0.857 |
| `cheap_fresh_construct` | 288 | 0.5090 | 0.000 |
| `pyvrp_10s` | 288 | 0.0004 | 1.000 |
| `pyvrp_60s_reference` | 288 | 0.0000 | 1.000 |

### PLAN_VALIDITY

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 288 | 0.7014 | 0.299 |
| `local_repair_insert` | 72 | 0.5000 | 0.500 |
| `cheap_fresh_construct` | 288 | 0.0174 | 0.983 |
| `pyvrp_10s` | 288 | 0.0174 | 0.983 |
| `pyvrp_60s_reference` | 288 | 0.0174 | 0.983 |

### STRUCT

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 288 | 0.1480 | 0.625 |
| `local_repair_insert` | 72 | 0.1592 | 0.486 |
| `cheap_fresh_construct` | 288 | 0.6637 | 0.000 |
| `pyvrp_10s` | 288 | 0.0422 | 0.866 |
| `pyvrp_60s_reference` | 288 | 0.0000 | 1.000 |

### SCHEDULE

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 288 | 0.0666 | 0.484 |
| `local_repair_insert` | 72 | 0.0615 | 0.543 |
| `cheap_fresh_construct` | 288 | 0.2129 | 0.078 |
| `pyvrp_10s` | 288 | 0.0201 | 0.898 |
| `pyvrp_60s_reference` | 288 | 0.0000 | 1.000 |

## 9. ORDER_CHANGE analysis

Total OC wide rows: **360** (4 OC perturbations × 18 instances × 5 actions = 360)

| action | rows | coverage_feasible | action_feasible | infeasibility_kind (non-`none`) |
|---|---:|---:|---:|---|
| `reuse_direct` | 72 | 0.000 | 0.000 | {"coverage": 72} |
| `local_repair_insert` | 72 | 1.000 | 0.500 | {"time_window": 28, "both": 7, "capacity": 1} |
| `cheap_fresh_construct` | 72 | 1.000 | 0.972 | {"time_window": 2} |
| `pyvrp_10s` | 72 | 1.000 | 0.972 | {"time_window": 2} |
| `pyvrp_60s_reference` | 72 | 1.000 | 0.972 | {"time_window": 2} |

OC bands by action (cheap-action `local_repair_insert` first):

| action | OBJ easy | STRUCT easy | SCHEDULE easy | PV easy |
|---|---:|---:|---:|---:|
| `reuse_direct` | 54 | 43 | 39 | 0 |
| `local_repair_insert` | 60 | 34 | 38 | 36 |
| `cheap_fresh_construct` | 0 | 0 | 2 | 70 |
| `pyvrp_10s` | 70 | 62 | 62 | 70 |
| `pyvrp_60s_reference` | 70 | 70 | 70 | 70 |

## 10. Middle-action value

Comparisons between adjacent ladder rungs across all 4 claim families (long-table band-easy rates):

| comparison | OBJ Δeasy% | PV Δeasy% | STRUCT Δeasy% | SCHEDULE Δeasy% |
|---|---:|---:|---:|---:|
| reuse_direct → cheap_fresh_construct | -86.5 | +68.4 | -61.5 | -39.9 |
| cheap_fresh_construct → pyvrp_10s | +98.3 | +0.0 | +85.1 | +80.6 |
| pyvrp_10s → pyvrp_60s_reference | +0.0 | +0.0 | +13.2 | +10.1 |

- Cells where cheap action gave PV=hard but pyvrp_10s recovered PV=easy: **161 / 288** (55.9%)
- Cells where even pyvrp_10s gave PV=hard: **5 / 288** — of which pyvrp_60s_reference recovered: 0

## 11. Recommendation

Headline aggregates:

| metric | value |
|---|---:|
| wide rows | 1224 |
| long claim rows | 4896 |
| reference_obj_unstable rate | 0.000 |
| reference_struct_unstable rate | 0.194 |
| median reference_ari_min | 1.000 |
| all-infeasible reference cells | 22 / 1224 (1.8%) |
| wall-clock | 9 185 s (~2 h 33 min) |

### Question-by-question

1. **Does `cheap_fresh_construct` produce useful middle-quality solutions?**
   **Partially — useful only as a PV-recovery tool.**
   - **PV**: rescues 161/166 cheap-action coverage-failure cells (97% rescue rate), matching what pyvrp_10s and the 60 s reference achieve, at 100× lower runtime cost (median 0.105 s vs 10 s vs 60 s). This is the value proposition.
   - **OBJ**: **0% easy** rate, mean loss 0.51 (≈50% worse than reference). Not a quality solution.
   - **STRUCT**: 0% easy. Doesn't preserve baseline structure (by design — it rebuilds), so STRUCT loss is structurally inflated even when the plan is feasible.
   - **SCHEDULE**: 8% easy.
   - **Verdict**: keep, but position it as the *coverage/feasibility-rescue* rung, not as a quality middle. The benchmark should expose this asymmetry rather than smooth it over.

2. **Does `pyvrp_10s` improve over `cheap_fresh_construct`?**
   **Yes — strictly dominates on OBJ, STRUCT, SCHEDULE; tied on PV.**
   | family | fresh easy | 10 s easy | Δ |
   |---|---:|---:|---:|
   | OBJ | 0.0% | 100.0% | **+98.3 pp** |
   | PV | 98.3% | 98.3% | 0 pp |
   | STRUCT | 0.0% | 86.6% | **+85.1 pp** |
   | SCHEDULE | 7.8% | 89.8% | **+80.6 pp** |
   - Costs +9.9 s/cell over fresh_construct, buys ~85 pp easy-rate on 3/4 families. Best per-second improvement in the ladder.

3. **Does `pyvrp_10s` approach `pyvrp_60s_reference`?**
   **Very close on OBJ/PV; meaningfully behind on STRUCT/SCHEDULE.**
   | family | 10 s easy | 60 s easy | Δ |
   |---|---:|---:|---:|
   | OBJ | 100.0% | 100.0% | 0 pp |
   | PV | 98.3% | 98.3% | 0 pp |
   | STRUCT | 86.6% | 100.0% | +13.2 pp |
   | SCHEDULE | 89.8% | 100.0% | +10.1 pp |
   - The 60 s reference is trivially perfect on STRUCT/SCHEDULE because its losses are computed against itself. The 13 pp / 10 pp gaps for pyvrp_10s reflect *real* structural and schedule deviation from a 6× longer search.

4. **Cases where cheap actions fail but middle actions are sufficient?**
   **Yes — 161/288 cells (55.9%).** Cheap-action PV-hard cells where every middle/reference action recovers PV=easy. This is the headline value of the expanded ladder.

5. **Cases where `pyvrp_10s` is still insufficient?**
   **Yes — 5 PV-hard cells (1.7%).** pyvrp_60s_reference recovers 0 of these — they are the 5 (instance × perturbation) cells that are *all-3-seeds-infeasible* even at the 60 s budget (R101/R102/R103 × TT_4 plus RC102 × OC_2 / OC_4). At the action level there are 22 corresponding rows (5 cells × 4–5 actions). These are real fleet-exhaustion infeasibilities, not budget shortfalls — they belong as `n/a` reference labels.

6. **Is the action ladder strong enough for the full benchmark?**
   **Yes — proceed to prereg drafting.** The 5-action ladder gives well-stratified labels across every claim family and a meaningful runtime gradient (0.001 s → 0.1 s → 10 s → 60 s). All four research questions about middle-action value have answerable signal at 18 instances.

7. **Keep `cheap_fresh_construct` and `pyvrp_10s`?**
   - **Keep `cheap_fresh_construct`**: it is the cheapest action that achieves coverage feasibility on OC cells and gives the *PV-recovery rung* the benchmark needs. Its OBJ/STRUCT weakness is informative, not a bug.
   - **Keep `pyvrp_10s`**: it is the right "good-enough metaheuristic" middle. The OBJ/PV near-tie with the 60 s reference establishes it as a credible compute-aware option; the STRUCT/SCHEDULE gap keeps the 60 s rung distinctive.

8. **Proceed to prereg drafting before 56-instance Stage A?**
   **Yes.** Action ladder is well-formed and label structure is clean. No blockers.

### Non-blocking caveats

- **PyVRP `MaxRuntime` nondeterminism.** Wall-clock-based stopping yields slightly different seed-paths across runs; the previous 18-instance scale-check reported 7 all-infeasible cells, this run reports 5 (same set of stable structural failures across 4–5 actions = 22 wide rows here vs 7 there). This is already handled by `reference_struct_unstable` / `reference_obj_unstable` and the per-family `reference_valid` rules.
- **5 all-infeasible cells (1.8%).** Same fleet-exhaustion failures as before. Leave them as `n/a` for OBJ/STRUCT/SCHEDULE, `hard` for PV; do not extend the time budget.

### Artifacts

- Wide parquet: `data/probes/vrptw_scale_check_18_expanded_actions.parquet`
- Long parquet: `data/probes/vrptw_scale_check_18_expanded_actions_claim_rows.parquet`

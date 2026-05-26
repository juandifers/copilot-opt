# VRPTW Perturbation Pilot v2 — Diagnostic Report

Generated: 2026-05-13T13:01:23

## 1. Purpose

Diagnostic refinement of the v1 VRPTW perturbation pilot (`data/probes/vrptw_perturbation_pilot.parquet`). The v1 pilot produced promising STRUCT labels but had three issues: PLAN_VALIDITY was too hard (79.2% infeasible), SCHEDULE was inactive (0/96 hard), and one cell had a missing OBJ band. v2 runs two grids (v1 + softened), adds a local insertion repair action for ORDER_CHANGE, switches the SCHEDULE metric to a local affected-customer p90, and computes a generalized (distance + 0.1·duration) objective. **No prereg or CVRP changes.**

## 2. v1 data-quality debug

v1 parquet path: `data/probes/vrptw_perturbation_pilot.parquet`. Total rows: **96**.
Null counts in core columns:
| column | nulls |
|---|---|
| `loss_obj` | 1 |
| `loss_struct` | 0 |
| `loss_schedule` | 0 |
| `reference_obj_s1` | 0 |
| `reuse_obj` | 0 |

Rows with `loss_obj` null (1):

| instance_id | perturbation_id | family | reference_obj_s1 | reuse_obj | band_obj |
|---|---|---|---|---|---|
| R101 | TT_4 | TRAVEL_TIME | inf | 16430.0 | n/a |

**Diagnosis:** `loss_obj` is null when `reference_obj_s1 = inf`, which only happens when PyVRP fails to find any feasible solution under the perturbed instance within the time limit. In v1 this hit R101 TT_4 (farthest-quartile × 1.50 duration on a 25-vehicle fleet). The v1 report's band totals summed to 95 because the n/a rows were excluded from `value_counts()` — there is no *data* bug, only a presentation gap. v2 reports band counts including `n/a` and uses generalized OBJ + soft magnitudes to reduce the rate of degenerate-reference cells.

## 3. Setup

- Instances: C101, C201, R101, R201, RC101, RC201
- Seeds (per reference cell): 1, 2, 3
- Time limit: 60s per PyVRP solve
- Solver: PyVRP 0.13.3
- Workers: joblib loky, `n_jobs=6`
- Grids: `v1_grid` (same magnitudes as v1), `soft_grid` (softer magnitudes; OC_2/OC_4 tight-window width 40% vs 25%)
- Actions: `reuse_direct` (all cells), `local_repair_insert` (ORDER_CHANGE only)
- Total rows: **240** (6 × 16 perturbations × 2 grids × actions[1 or 2])

## 4. Grid comparison

### v1_grid (120 rows)

**action = `reuse_direct`** (96 rows)

| metric | easy | medium | hard | n/a |
|---|---|---|---|---|
| OBJ (distance-only) | 79 (82.3%) | 11 (11.5%) | 5 (5.2%) | 1 (1.0%) |
| OBJ (generalized) | 78 (81.2%) | 10 (10.4%) | 7 (7.3%) | 1 (1.0%) |
| STRUCT | 54 (56.2%) | 21 (21.9%) | 21 (21.9%) | 0 (0.0%) |
| SCHEDULE v1 (global median) | 90 (93.8%) | 6 (6.2%) | 0 (0.0%) | 0 (0.0%) |
| SCHEDULE v2 (affected-p90) | 42 (43.8%) | 36 (37.5%) | 18 (18.8%) | 0 (0.0%) |
| PLAN_VALIDITY (easy/hard) | 20 (20.8%) | 76 (79.2%) | — | — |

Reference: obj_unstable_rate = **0.000**, struct_unstable_rate = **0.125**, median ari_min = **1.000**

**action = `local_repair_insert`** (24 rows)

| metric | easy | medium | hard | n/a |
|---|---|---|---|---|
| OBJ (distance-only) | 21 (87.5%) | 3 (12.5%) | 0 (0.0%) | 0 (0.0%) |
| OBJ (generalized) | 21 (87.5%) | 3 (12.5%) | 0 (0.0%) | 0 (0.0%) |
| STRUCT | 11 (45.8%) | 11 (45.8%) | 2 (8.3%) | 0 (0.0%) |
| SCHEDULE v1 (global median) | 23 (95.8%) | 1 (4.2%) | 0 (0.0%) | 0 (0.0%) |
| SCHEDULE v2 (affected-p90) | 13 (54.2%) | 9 (37.5%) | 2 (8.3%) | 0 (0.0%) |
| PLAN_VALIDITY (easy/hard) | 11 (45.8%) | 13 (54.2%) | — | — |

Reference: obj_unstable_rate = **0.000**, struct_unstable_rate = **0.083**, median ari_min = **1.000**

### soft_grid (120 rows)

**action = `reuse_direct`** (96 rows)

| metric | easy | medium | hard | n/a |
|---|---|---|---|---|
| OBJ (distance-only) | 82 (85.4%) | 10 (10.4%) | 3 (3.1%) | 1 (1.0%) |
| OBJ (generalized) | 82 (85.4%) | 9 (9.4%) | 4 (4.2%) | 1 (1.0%) |
| STRUCT | 60 (62.5%) | 23 (24.0%) | 13 (13.5%) | 0 (0.0%) |
| SCHEDULE v1 (global median) | 92 (95.8%) | 4 (4.2%) | 0 (0.0%) | 0 (0.0%) |
| SCHEDULE v2 (affected-p90) | 51 (53.1%) | 33 (34.4%) | 12 (12.5%) | 0 (0.0%) |
| PLAN_VALIDITY (easy/hard) | 30 (31.2%) | 66 (68.8%) | — | — |

Reference: obj_unstable_rate = **0.000**, struct_unstable_rate = **0.146**, median ari_min = **1.000**

**action = `local_repair_insert`** (24 rows)

| metric | easy | medium | hard | n/a |
|---|---|---|---|---|
| OBJ (distance-only) | 21 (87.5%) | 3 (12.5%) | 0 (0.0%) | 0 (0.0%) |
| OBJ (generalized) | 21 (87.5%) | 3 (12.5%) | 0 (0.0%) | 0 (0.0%) |
| STRUCT | 11 (45.8%) | 11 (45.8%) | 2 (8.3%) | 0 (0.0%) |
| SCHEDULE v1 (global median) | 23 (95.8%) | 1 (4.2%) | 0 (0.0%) | 0 (0.0%) |
| SCHEDULE v2 (affected-p90) | 13 (54.2%) | 9 (37.5%) | 2 (8.3%) | 0 (0.0%) |
| PLAN_VALIDITY (easy/hard) | 12 (50.0%) | 12 (50.0%) | — | — |

Reference: obj_unstable_rate = **0.000**, struct_unstable_rate = **0.083**, median ari_min = **1.000**

## 5. PLAN_VALIDITY analysis

### Easy/hard split by grid

| grid | action | easy | hard |
|---|---|---|---|
| v1_grid | reuse_direct | 20 (20.8%) | 76 (79.2%) |
| v1_grid | local_repair_insert | 11 (45.8%) | 13 (54.2%) |
| soft_grid | reuse_direct | 30 (31.2%) | 66 (68.8%) |
| soft_grid | local_repair_insert | 12 (50.0%) | 12 (50.0%) |

### Easy/hard split by perturbation family

| family | grid | action | easy | hard |
|---|---|---|---|---|
| TRAVEL_TIME | v1_grid | reuse_direct | 6 (25.0%) | 18 (75.0%) |
| TRAVEL_TIME | soft_grid | reuse_direct | 10 (41.7%) | 14 (58.3%) |
| TIME_WINDOW | v1_grid | reuse_direct | 7 (29.2%) | 17 (70.8%) |
| TIME_WINDOW | soft_grid | reuse_direct | 12 (50.0%) | 12 (50.0%) |
| SERVICE_TIME | v1_grid | reuse_direct | 7 (29.2%) | 17 (70.8%) |
| SERVICE_TIME | soft_grid | reuse_direct | 8 (33.3%) | 16 (66.7%) |
| ORDER_CHANGE | v1_grid | reuse_direct | 0 (0.0%) | 24 (100.0%) |
| ORDER_CHANGE | v1_grid | local_repair_insert | 11 (45.8%) | 13 (54.2%) |
| ORDER_CHANGE | soft_grid | reuse_direct | 0 (0.0%) | 24 (100.0%) |
| ORDER_CHANGE | soft_grid | local_repair_insert | 12 (50.0%) | 12 (50.0%) |

### Infeasibility kind

| grid | action | none | capacity | time_window | both | coverage |
|---|---|---|---|---|---|---|
| v1_grid | reuse_direct | 20 | 0 | 52 | 0 | 24 |
| v1_grid | local_repair_insert | 11 | 0 | 10 | 3 | 0 |
| soft_grid | reuse_direct | 30 | 0 | 42 | 0 | 24 |
| soft_grid | local_repair_insert | 12 | 0 | 9 | 3 | 0 |

## 6. SCHEDULE analysis (v1 vs v2)

v1 SCHEDULE = median of `|start_service_action - start_service_reference|` over **all common customers**, normalized by depot horizon.

v2 SCHEDULE = p90 of the same shift restricted to **affected customers** (with the ORDER_CHANGE inserted-customer set excluded; fallback to all customers if empty).

| grid | action | v1 easy | v1 medium | v1 hard | v2 easy | v2 medium | v2 hard |
|---|---|---|---|---|---|---|---|
| v1_grid | reuse_direct | 90 | 6 | 0 | 42 | 36 | 18 |
| v1_grid | local_repair_insert | 23 | 1 | 0 | 13 | 9 | 2 |
| soft_grid | reuse_direct | 92 | 4 | 0 | 51 | 33 | 12 |
| soft_grid | local_repair_insert | 23 | 1 | 0 | 13 | 9 | 2 |

**Affected-p90 distribution (across all rows):** min=0.0000, median=0.0214, p90=0.0645, max=0.1075

**Cells with `time_warp=0` but `band_schedule_v2 ∈ {medium, hard}`:** **36/121** (29.8% of time-feasible cells).

## 7. ORDER_CHANGE / local repair analysis

- ORDER_CHANGE rows: 96 (reuse_direct: 48, local_repair_insert: 48)
- `coverage_feasible` rate — reuse_direct: **0.000**, local_repair: **1.000**
- `local_repair_inserted_all` rate (every insert cap+TW feasible): **0.479**
- PLAN_VALIDITY `easy` count — reuse_direct: **0/48**, local_repair: **23/48**
- local_repair STRUCT bands: easy=22, medium=22, hard=4
- local_repair SCHEDULE v2 bands: easy=26, medium=18, hard=4

## 8. Objective analysis

Distance-only band uses `loss_obj = |action_obj - reference_obj_s1| / reference_obj_s1`.

Generalized band uses `generalized_cost = distance + 0.1 * duration` for both action and reference.

| grid | action | family | distance easy | distance medium | distance hard | generalized easy | generalized medium | generalized hard |
|---|---|---|---|---|---|---|---|---|
| v1_grid | reuse_direct | TRAVEL_TIME | 21 | 1 | 1 | 21 | 1 | 1 |
| v1_grid | reuse_direct | TIME_WINDOW | 24 | 0 | 0 | 24 | 0 | 0 |
| v1_grid | reuse_direct | SERVICE_TIME | 16 | 5 | 3 | 14 | 5 | 5 |
| v1_grid | reuse_direct | ORDER_CHANGE | 18 | 5 | 1 | 19 | 4 | 1 |
| v1_grid | local_repair_insert | ORDER_CHANGE | 21 | 3 | 0 | 21 | 3 | 0 |
| soft_grid | reuse_direct | TRAVEL_TIME | 22 | 1 | 0 | 22 | 1 | 0 |
| soft_grid | reuse_direct | TIME_WINDOW | 24 | 0 | 0 | 24 | 0 | 0 |
| soft_grid | reuse_direct | SERVICE_TIME | 18 | 4 | 2 | 17 | 4 | 3 |
| soft_grid | reuse_direct | ORDER_CHANGE | 18 | 5 | 1 | 19 | 4 | 1 |
| soft_grid | local_repair_insert | ORDER_CHANGE | 21 | 3 | 0 | 21 | 3 | 0 |

## 9. Reference stability

| grid | family | obj_unst_rate | struct_unst_rate | median ari_min |
|---|---|---|---|---|
| v1_grid | TRAVEL_TIME | 0.000 | 0.167 | 1.000 |
| v1_grid | TIME_WINDOW | 0.000 | 0.167 | 1.000 |
| v1_grid | SERVICE_TIME | 0.000 | 0.083 | 1.000 |
| v1_grid | ORDER_CHANGE | 0.000 | 0.083 | 1.000 |
| soft_grid | TRAVEL_TIME | 0.000 | 0.167 | 1.000 |
| soft_grid | TIME_WINDOW | 0.000 | 0.167 | 1.000 |
| soft_grid | SERVICE_TIME | 0.000 | 0.167 | 1.000 |
| soft_grid | ORDER_CHANGE | 0.000 | 0.083 | 1.000 |

Overall (reuse_direct rows, n=192): obj_unst_rate = **0.000**, struct_unst_rate = **0.135**, median ari_min = **1.000**

## 10. Recommendation

- **VRPTW remains promising** as a thesis substrate: STRUCT still separates instances cleanly under perturbation, and PLAN_VALIDITY becomes balanced once magnitudes are softened.
- **Recommended grid: `soft_grid`.** v1 PV-easy rate = **0.208**, soft PV-easy rate = **0.312** for reuse_direct. The soft grid keeps STRUCT informative while restoring a meaningful PLAN_VALIDITY-easy fraction.
- **Include ORDER_CHANGE** in the full benchmark — but pair it with `local_repair_insert`, not raw `reuse_direct`. Coverage feasibility lift from repair: **+1.000**.
- **Keep SCHEDULE v2** (affected-p90). v1 SCHEDULE produced 0 hard cells on 96; v2 surfaces local schedule disruption that PLAN_VALIDITY misses on time-feasible cells.
- **Generalized objective** is a useful diagnostic supplement; for TRAVEL_TIME/SERVICE_TIME it captures the duration-side cost that distance-only OBJ ignores. Use both for the full benchmark, don't replace.

## 11. Caveats

- **Exploratory, not preregistered.** Magnitudes and band thresholds may be re-tuned before any larger benchmark.
- **n = 240 rows.** Splits by grid/action/family are directional only.
- **Solomon-100 only.** No Homberger / Gehring.
- **`infeasibility_kind='coverage'`** is a small spec extension beyond {none, capacity, time_window, both} for ORDER_CHANGE cells with unserved-inserted customers (`reuse_direct`).
- **`local_repair_insert`** is a deterministic cheapest-insertion heuristic; it does **not** open new vehicles by default. Cells where insertion is impossible without a new route remain infeasible.
- **Generalized cost α=0.1** is post-hoc; PyVRP optimization itself still minimizes distance only.

## 12. Appendix: perturbation architecture

Everything needed to read the tables above. Two things drive a row: the **perturbation** (what changes about the instance) and the **action** (what plan we score against the perturbed instance).

### 12.1 Perturbation grid (16 per grid variant)

Every selector is **baseline-aware** — the unperturbed instance is first solved by PyVRP at 60 s seed=1, and that schedule drives which customers/routes a perturbation targets.

| ID | Family | What it changes | Selector | v1_grid | soft_grid |
|---|---|---|---|---|---|
| TT_1 | TRAVEL_TIME | duration matrix (×) on arcs touching affected | baseline route w/ highest total waiting | ×1.10 | ×1.05 |
| TT_2 | TRAVEL_TIME | duration matrix (×) | route w/ lowest min slack-to-tw_late | ×1.20 | ×1.10 |
| TT_3 | TRAVEL_TIME | duration matrix (×) | densest customer quartile (k-NN spread) | ×1.30 | ×1.20 |
| TT_4 | TRAVEL_TIME | duration matrix (×) | farthest-from-depot quartile | ×1.50 | ×1.30 |
| TW_1 | TIME_WINDOW | customer windows tightened around midpoint | route w/ highest mean slack | 10% | 5% |
| TW_2 | TIME_WINDOW | tighten around midpoint | route w/ lowest mean slack | 20% | 10% |
| TW_3 | TIME_WINDOW | shift earlier by fraction of width | final third of every baseline route | 10% | 5% |
| TW_4 | TIME_WINDOW | shift later by fraction of width | first third of every baseline route | 10% | 5% |
| ST_1 | SERVICE_TIME | customer service durations (×) | route w/ highest total waiting | ×1.10 | ×1.05 |
| ST_2 | SERVICE_TIME | service durations (×) | route w/ lowest min slack | ×1.25 | ×1.10 |
| ST_3 | SERVICE_TIME | service durations (×) | densest customer quartile | ×1.50 | ×1.25 |
| ST_4 | SERVICE_TIME | service durations (×) | top-demand quartile | ×2.00 | ×1.50 |
| OC_1 | ORDER_CHANGE | +1 customer (flex window) | near highest-slack route | 0.05·cap | 0.05·cap |
| OC_2 | ORDER_CHANGE | +1 customer (tight window) | near lowest-slack route | 0.05·cap, 25% width | 0.05·cap, 40% width |
| OC_3 | ORDER_CHANGE | +3 customers (flex window) | near densest region | 0.15·cap | 0.15·cap |
| OC_4 | ORDER_CHANGE | +3 customers (tight window) | near lowest-slack route | 0.20·cap, 25% width | 0.20·cap, 40% width |

*soft_grid* keeps every selector unchanged and only reduces magnitudes (and relaxes OC_2/OC_4 tight-window width). All time-window edits clip to the depot horizon and enforce `tw_early < tw_late`; collapses fall back to a 1-unit window. ORDER_CHANGE customer coordinates are drawn by a SHA256-seeded RNG: jitter `~N(0, spread/3)` (single insert) or `N(0, spread/4)` (3-cluster) around the chosen reference centroid; demand is split evenly with a floor of 1.

### 12.2 Actions

Each (instance, grid, perturbation) cell is scored against one or two actions:

- **`reuse_direct`** — keep the baseline routes exactly as-is and evaluate `pyvrp.Solution(perturbed_data, baseline.routes)`. This is the cheapest possible response: no computation, the plan you already had. Always runs.
- **`local_repair_insert`** — ORDER_CHANGE only. Greedy cheapest-feasible-insertion: for each new customer (in increasing ID order) try every `(route_idx, position)` on the current plan, pick the feasible candidate with lowest objective (ties: lowest route_idx, then lowest position); if no feasible candidate exists, pick the one minimising `(time_warp, objective, route_idx, position)`. Existing routes only — no new vehicles. ~1 ms per `evaluate_vrptw_solution` call, well under a second per cell.

### 12.3 References

Each cell also has a **reference** solution: PyVRP run on the perturbed instance with seeds 1, 2, 3 (60 s each). The seed-1 reference is the comparison target for OBJ, STRUCT, SCHEDULE; all three seeds feed reference-stability flags (`reference_obj_unstable` if `(max-min)/min > 0.02` over finite objectives; `reference_struct_unstable` if pairwise ARI min < 0.90).

### 12.4 Claim families and bands

All losses are scalar; bands are read from fixed thresholds. "action" below means whichever action's row we're scoring.

| Loss | Definition | Thresholds (easy / medium / hard) |
|---|---|---|
| OBJ | `|action_obj − ref_obj_s1| / ref_obj_s1`; n/a if ref is inf | ≤ 0.05 / ≤ 0.15 / > 0.15 |
| OBJ generalized | same formula on `distance + 0.1 × duration` | ≤ 0.05 / ≤ 0.15 / > 0.15 |
| PLAN_VALIDITY | binary: feasible (capacity ✓ ∧ TW ✓ ∧ all customers served) | easy if feasible else hard |
| STRUCT | `1 − ARI(action.assignment, ref_s1.assignment)` on the common customer set | ≤ 0.10 / ≤ 0.30 / > 0.30 |
| SCHEDULE v1 | median over **all common customers** of `|Δstart_service| / depot_horizon` | ≤ 0.02 / ≤ 0.05 / > 0.05 |
| SCHEDULE v2 | **p90** over **affected customers** (inserted excluded; fallback all customers if empty) of the same shift | ≤ 0.02 / ≤ 0.05 / > 0.05 |

### 12.5 Infeasibility kinds

When `action_feasible = False`, `infeasibility_kind` localises why:
- `none` — action is feasible.
- `capacity` — at least one route exceeds vehicle capacity; time windows OK.
- `time_window` — at least one customer is reached after its `tw_late`; capacity OK. (PyVRP encodes this as per-visit `time_warp`.)
- `both` — capacity *and* TW infeasible.
- `coverage` *(spec extension)* — capacity ✓ ∧ TW ✓, but `num_missing_clients > 0`. Triggered by ORDER_CHANGE `reuse_direct` cells whose baseline plan cannot cover the inserted customers.

### 12.6 Scaling

PyVRP needs integer matrices, so every distance, duration, time-window, and service-time value is multiplied by **10** before being handed to the solver. All absolute time/distance numbers in the parquet are in these ×10 units; relative losses (OBJ, STRUCT, SCHEDULE) are scale-invariant. TRAVEL_TIME perturbations multiply the duration matrix but **leave the distance matrix unchanged**, which is why distance-only OBJ tends to be quiet on TT cells and the generalized OBJ is the diagnostic supplement.

Parquet output: `data/probes/vrptw_perturbation_pilot_v2.parquet`

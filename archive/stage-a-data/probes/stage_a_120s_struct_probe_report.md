# Stage A 120s reference re-collection probe

Diagnostic only. Does a 120s PyVRP reference budget (double the Stage A
60s) clear enough §12.3 `reference_struct_unstable` cells to bring the
overall rate below the 25% locked threshold? This probe re-collects
references on a small stratified sample so we can decide whether the
prereg's full ~256-cell re-collection is worth running. It does **not**
modify `data/stage_a_vrptw.parquet` and does **not** re-run the action
portfolio — references only.

- Inputs:  `data/stage_a_vrptw.parquet` (896 cells, 256 unstable, rate 0.286)
- Probe parquet: `data/probes/stage_a_120s_struct_probe.parquet` (24 rows)
- Probe checkpoints: `data/probes/stage_a_120s_struct_probe_checkpoints/`
- Script: `scripts/run_stage_a_120s_struct_probe.py`
- Re-collection wall-clock: 1440.6 s (24.0 min, 72 solves at n_jobs=6)
- Baseline: 60s (matches Stage A cache; perturbed instance is byte-identical)
- Reference seeds: 1, 2, 3; PyVRP otherwise unchanged from Stage A
- RNG seed for stratified sampling: 20260514

Headline: the point-estimate extrapolation lands at **~19% overall
struct_unstable** (below the 25% threshold), but the pessimistic 95% LB
lands at **~25%**, so a 24-cell probe cannot rule out "no improvement"
with confidence. The two cleanest signals are that **bimodal cells
(ari_min < 0.60) account for 64% of unstable cells and clear at only ~25%**
under doubled time, and **ORDER_CHANGE refuses to budge** outside its
marginal band (0/4 mid+bimodal OC cells cleared).

---

## Step 1 — Free diagnostic: ARI distribution among unstable cells

Among the **256 unstable cells** (`reference_ari_min < 0.90`), the
distribution of `reference_ari_min` is heavy-tailed toward low ARI.
The mass is **not** concentrated just below 0.90: only 11.7% of unstable
cells sit in the marginal `[0.80, 0.90)` band, while 64% are bimodal
(`< 0.60`).

### Quantiles of `reference_ari_min` over the 256 unstable cells

| quantile | value |
|---|---:|
| min | 0.0108 |
| p10 | 0.3239 |
| p25 | 0.4108 |
| p50 (median) | 0.5228 |
| p75 | 0.6801 |
| p90 | 0.8090 |
| max | 0.8996 |
| mean | 0.5397 |

### Three-band breakdown (all unstable cells)

| band | range | count | share |
|---|---|---:|---:|
| marginal | `[0.80, 0.90)` | 30 | 11.7% |
| mid | `[0.60, 0.80)` | 63 | 24.6% |
| bimodal | `< 0.60` | 163 | 63.7% |

### Per-family three-band breakdown (counts, share-of-family-unstable)

| family | n_unstable | marginal | mid | bimodal |
|---|---:|---:|---:|---:|
| ORDER_CHANGE | 70 | 10 (14.3%) | 21 (30.0%) | 39 (55.7%) |
| SERVICE_TIME | 66 |  4 ( 6.1%) | 19 (28.8%) | 43 (65.2%) |
| TIME_WINDOW  | 66 | 10 (15.2%) | 13 (19.7%) | 43 (65.2%) |
| TRAVEL_TIME  | 54 |  6 (11.1%) | 10 (18.5%) | 38 (70.4%) |

**Read:** every family is bimodal-dominated. The hope that "most unstable
cells are sitting just under 0.90 and would tip with more compute" is
not supported by the free diagnostic — at most ~12% are in that regime,
and the median unstable cell is at ARI≈0.52.

---

## Step 2 — Probe sample

Stratified across `(perturbation_family × ari_band)`: target 2 cells per
stratum. With 4 families × 3 bands = 12 strata → **24 cells**. Every
stratum had ≥ 2 unstable cells, so no reallocation was needed. RNG seed
20260514 (NumPy `default_rng`).

| family | marginal | mid | bimodal | total |
|---|---:|---:|---:|---:|
| ORDER_CHANGE | 2 | 2 | 2 | 6 |
| SERVICE_TIME | 2 | 2 | 2 | 6 |
| TIME_WINDOW  | 2 | 2 | 2 | 6 |
| TRAVEL_TIME  | 2 | 2 | 2 | 6 |
| **total** | **8** | **8** | **8** | **24** |

Selected cells (sorted by family, band):

| instance | perturbation | family | band | ari_min_60s |
|---|---|---|---|---:|
| RC107 | OC_4 | ORDER_CHANGE | marginal | 0.815 |
| RC102 | OC_1 | ORDER_CHANGE | marginal | 0.871 |
| R106  | OC_3 | ORDER_CHANGE | mid      | 0.706 |
| RC207 | OC_1 | ORDER_CHANGE | mid      | 0.640 |
| R204  | OC_4 | ORDER_CHANGE | bimodal  | 0.375 |
| R208  | OC_1 | ORDER_CHANGE | bimodal  | 0.086 |
| RC107 | ST_1 | SERVICE_TIME | marginal | 0.808 |
| R102  | ST_4 | SERVICE_TIME | marginal | 0.885 |
| C105  | ST_4 | SERVICE_TIME | mid      | 0.620 |
| RC206 | ST_1 | SERVICE_TIME | mid      | 0.726 |
| R204  | ST_4 | SERVICE_TIME | bimodal  | 0.443 |
| R210  | ST_1 | SERVICE_TIME | bimodal  | 0.476 |
| RC102 | TW_2 | TIME_WINDOW  | marginal | 0.867 |
| RC107 | TW_1 | TIME_WINDOW  | marginal | 0.808 |
| R106  | TW_3 | TIME_WINDOW  | mid      | 0.757 |
| R206  | TW_4 | TIME_WINDOW  | mid      | 0.675 |
| R204  | TW_3 | TIME_WINDOW  | bimodal  | 0.347 |
| R205  | TW_4 | TIME_WINDOW  | bimodal  | 0.478 |
| R206  | TT_1 | TRAVEL_TIME  | marginal | 0.866 |
| R206  | TT_3 | TRAVEL_TIME  | marginal | 0.866 |
| R109  | TT_2 | TRAVEL_TIME  | mid      | 0.740 |
| RC104 | TT_4 | TRAVEL_TIME  | mid      | 0.707 |
| RC208 | TT_3 | TRAVEL_TIME  | bimodal  | 0.599 |
| R211  | TT_2 | TRAVEL_TIME  | bimodal  | 0.482 |

---

## Step 3 — Re-collection setup

For each probe cell, ran PyVRP at seeds {1, 2, 3} with a 120 s
`MaxRuntime` stop. Baseline was loaded from the existing 60 s cache so
the perturbed instance is byte-identical to Stage A's; only the
reference time limit changed. 72 solves total, 1440.6 s wall-clock at
`n_jobs=6` (one full batch at the 120 s budget — confirms no parallel
slowdown). Zero solver exceptions.

---

## Step 4 — Per-cell 120s vs 60s comparison

`clears` = `reference_ari_min_120s ≥ 0.90` (the locked
`ARI_STRUCT_UNSTABLE_THRESHOLD`).

| instance | pid | family | band_60s | ari_60s | ari_120s | Δ | clears |
|---|---|---|---|---:|---:|---:|:---:|
| RC107 | OC_4 | ORDER_CHANGE | marginal | 0.815 | 0.815 | +0.000 |  |
| RC102 | OC_1 | ORDER_CHANGE | marginal | 0.871 | 1.000 | +0.129 | ✓ |
| R106  | OC_3 | ORDER_CHANGE | mid      | 0.706 | 0.706 | +0.000 |  |
| RC207 | OC_1 | ORDER_CHANGE | mid      | 0.640 | 0.640 | +0.000 |  |
| R204  | OC_4 | ORDER_CHANGE | bimodal  | 0.375 | 0.375 | +0.000 |  |
| R208  | OC_1 | ORDER_CHANGE | bimodal  | 0.086 | 0.143 | +0.057 |  |
| RC107 | ST_1 | SERVICE_TIME | marginal | 0.808 | 1.000 | +0.192 | ✓ |
| R102  | ST_4 | SERVICE_TIME | marginal | 0.885 | 0.885 | +0.000 |  |
| C105  | ST_4 | SERVICE_TIME | mid      | 0.620 | 0.620 | +0.000 |  |
| RC206 | ST_1 | SERVICE_TIME | mid      | 0.726 | 1.000 | +0.274 | ✓ |
| R204  | ST_4 | SERVICE_TIME | bimodal  | 0.443 | 1.000 | +0.557 | ✓ |
| R210  | ST_1 | SERVICE_TIME | bimodal  | 0.476 | 0.312 | −0.164 |  |
| RC102 | TW_2 | TIME_WINDOW  | marginal | 0.867 | 1.000 | +0.133 | ✓ |
| RC107 | TW_1 | TIME_WINDOW  | marginal | 0.808 | 0.808 | +0.000 |  |
| R106  | TW_3 | TIME_WINDOW  | mid      | 0.757 | 0.984 | +0.226 | ✓ |
| R206  | TW_4 | TIME_WINDOW  | mid      | 0.675 | 0.675 | +0.000 |  |
| R204  | TW_3 | TIME_WINDOW  | bimodal  | 0.347 | 0.692 | +0.346 |  |
| R205  | TW_4 | TIME_WINDOW  | bimodal  | 0.478 | 0.478 | +0.000 |  |
| R206  | TT_1 | TRAVEL_TIME  | marginal | 0.866 | 0.866 | +0.000 |  |
| R206  | TT_3 | TRAVEL_TIME  | marginal | 0.866 | 1.000 | +0.134 | ✓ |
| R109  | TT_2 | TRAVEL_TIME  | mid      | 0.740 | 1.000 | +0.260 | ✓ |
| RC104 | TT_4 | TRAVEL_TIME  | mid      | 0.707 | 1.000 | +0.293 | ✓ |
| RC208 | TT_3 | TRAVEL_TIME  | bimodal  | 0.599 | 1.000 | +0.401 | ✓ |
| R211  | TT_2 | TRAVEL_TIME  | bimodal  | 0.482 | 0.427 | −0.055 |  |

Notes on the rows worth flagging:
- **Two cells went *down* at 120s** (R210/ST_1, R211/TT_2 — both bimodal):
  the 120s solver found a *different* low-ARI attractor than the 60s
  solver. Concretely, these are not "more compute → more agreement"
  cells; they are "different attractors of comparable cost".
- **Many cells move by exactly 0.000** (10 of 24). That is the
  fingerprint of a stable attractor: the same seed lands the same routes
  whether given 60s or 120s. For those cells, "more time" cannot help.
- The bimodal R204/TW_3 went 0.347 → 0.692 — moved a lot, still did not
  clear 0.90.

---

## Step 5 — Aggregate clear rates and extrapolation

### Clear rates in the probe

| slice | k cleared | n probed | rate |
|---|---:|---:|---:|
| **overall** | **10** | **24** | **0.417** |
| band: marginal | 4 | 8 | 0.500 |
| band: mid | 4 | 8 | 0.500 |
| band: bimodal | 2 | 8 | 0.250 |
| family: ORDER_CHANGE | 1 | 6 | 0.167 |
| family: SERVICE_TIME | 3 | 6 | 0.500 |
| family: TIME_WINDOW  | 2 | 6 | 0.333 |
| family: TRAVEL_TIME  | 4 | 6 | 0.667 |

Wilson 95% CIs on the pooled-by-band rates (n=8 per band):
- marginal 4/8: CI (0.215, 0.785)
- mid 4/8: CI (0.215, 0.785)
- bimodal 2/8: CI (0.071, 0.591)

Marginal and mid clear at the same rate in this probe; the marginal vs
bimodal difference is the only one that's qualitatively suggestive (and
even that is well within sampling noise at n=8).

### Per (family × band) clear rate (the fine-grained probe table)

| family | marginal | mid | bimodal |
|---|---:|---:|---:|
| ORDER_CHANGE | 1/2 = 0.50 | 0/2 = 0.00 | 0/2 = 0.00 |
| SERVICE_TIME | 1/2 = 0.50 | 1/2 = 0.50 | 1/2 = 0.50 |
| TIME_WINDOW  | 1/2 = 0.50 | 1/2 = 0.50 | 0/2 = 0.00 |
| TRAVEL_TIME  | 1/2 = 0.50 | 2/2 = 1.00 | 1/2 = 0.50 |

ORDER_CHANGE is the only family where mid+bimodal didn't budge at all
(0/4 cleared). Travel_time is the family that responds most to more
compute (4/6 cleared).

### Extrapolation A — apply pooled-by-band rates to all 256 unstable cells

Arithmetic (kept = cells expected to remain unstable):

```
marginal:   30 unstable  ×  (1 − 0.500)  =  15.0  kept
mid:        63 unstable  ×  (1 − 0.500)  =  31.5  kept
bimodal:   163 unstable  ×  (1 − 0.250)  = 122.2  kept
                                          -------
                                   total  ≈ 168.8  kept
```

Extrapolated overall struct_unstable rate

```
168.75 / 896  ≈  0.1883   (18.83%)
```

**Below the 25% threshold.**

### Extrapolation B — apply per (family × band) rates to all 256 unstable cells

```
ORDER_CHANGE marginal: 10 × (1−0.50) =  5.0
ORDER_CHANGE mid:      21 × (1−0.00) = 21.0
ORDER_CHANGE bimodal:  39 × (1−0.00) = 39.0
SERVICE_TIME marginal:  4 × (1−0.50) =  2.0
SERVICE_TIME mid:      19 × (1−0.50) =  9.5
SERVICE_TIME bimodal:  43 × (1−0.50) = 21.5
TIME_WINDOW  marginal: 10 × (1−0.50) =  5.0
TIME_WINDOW  mid:      13 × (1−0.50) =  6.5
TIME_WINDOW  bimodal:  43 × (1−0.00) = 43.0
TRAVEL_TIME  marginal:  6 × (1−0.50) =  3.0
TRAVEL_TIME  mid:      10 × (1−1.00) =  0.0
TRAVEL_TIME  bimodal:  38 × (1−0.50) = 19.0
                                       ----
                                total ≈ 174.5  kept
```

Extrapolated overall rate

```
174.5 / 896  ≈  0.1948   (19.48%)
```

**Also below the 25% threshold.** Per-family detail keeps ORDER_CHANGE
elevated and TRAVEL_TIME nearly empty, but the two extrapolations
agree to within a percentage point.

### Sensitivity — Wilson 95% bounds on pooled-by-band rates

Applying the **upper** Wilson bound for each band (optimistic) and the
**lower** bound (pessimistic) to the 256-cell unstable set:

| scenario | total_kept | extrapolated rate |
|---|---:|---:|
| optimistic 95% UB | 86.7 / 896 | **0.097** (well below 25%) |
| **point estimate** | 168.75 / 896 | **0.188** (below 25%) |
| pessimistic 95% LB | 224.3 / 896 | **0.250** (right at 25%) |

**The probe's pessimistic 95% bound straddles the threshold.** A
24-cell probe is informative about direction but cannot confidently
rule out "no useful improvement". To get a tight verdict, the prereg's
full re-collection (or at minimum a larger probe — perhaps n≈8 per
band) would be needed.

---

## Step-5 bottom line

- The free diagnostic (Step 1) already weakens the "marginal cells will
  tip" hypothesis: only 11.7% of unstable cells sit in `[0.80, 0.90)`,
  while 63.7% are bimodal.
- The 24-cell probe agrees: bimodal cells clear at half the rate of
  marginal/mid cells (0.25 vs 0.50). Plus, two bimodal cells *worsened*
  at 120s, evidence that some of those cells are sitting between
  comparable-cost attractors rather than under-resourced.
- Point-estimate extrapolation lands the overall rate at **0.188–0.195**,
  below the 25% threshold. So at face value, 120s re-collection does
  appear likely to clear the gate.
- But the pessimistic 95% LB on the pooled-by-band extrapolation lands
  at **0.250** — essentially at the threshold. A 24-cell probe doesn't
  have the statistical resolution to call this confidently.
- ORDER_CHANGE in particular is suspicious: 0/4 mid+bimodal cells
  cleared. If that family's mid/bimodal cells are genuinely structurally
  bimodal under doubled time, even the full re-collection may leave a
  meaningful ORDER_CHANGE residual.

**Recommendation (advisory; not a decision):** the probe is consistent
with 120s clearing the 25% gate, but a 24-cell sample makes that call
shaky. Two reasonable next steps for the prereg's §12.3/§12.5 procedure:
(a) run the full ~256-cell re-collection at 120s as preregistered and
treat the probe purely as a feasibility check, or (b) widen the probe
to ≈48 cells first (still cheap — under an hour) so the per-band CIs
shrink before committing to the full run. ORDER_CHANGE deserves a
closer look either way.

---

## Provenance

- Probe input cells, deltas, 120s ARI components → `data/probes/stage_a_120s_struct_probe.parquet`
- Per-cell `VRPTWSolveResult` JSONs (resumable) → `data/probes/stage_a_120s_struct_probe_checkpoints/refs/`
- Probe script → `scripts/run_stage_a_120s_struct_probe.py`
- Stage A artifact (unchanged) → `data/stage_a_vrptw.parquet`
- Stage A run report → `data/stage_a_vrptw_run_report.md`
- Stability thresholds (`ARI_STRUCT_UNSTABLE_THRESHOLD = 0.90`) → `src/vrp_copilot_bench/vrptw/evaluation.py`

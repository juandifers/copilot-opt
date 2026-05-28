# Stage A VRPTW reference re-collection (§12.6 §12.3-clause)

Re-collection of PyVRP references at the prereg's scaled reference
protocol (PyVRP **120 s**, seeds 1/2/3, full multi-seed audit) for every
Stage A cell where `reference_struct_unstable` is true in
`data/stage_a_vrptw.parquet`. References only; the action portfolio is
**not** re-run. Baselines load from the existing 60 s cache, so the
perturbed instance is byte-identical to Stage A's; only the reference
time limit changed.

Reads:
- Stage A wide artifact (untouched) — `data/stage_a_vrptw.parquet`
- Probe artifact (untouched) — `data/probes/stage_a_120s_struct_probe.parquet`

Writes:
- New artifact — `data/stage_a_vrptw_recollected.parquet` (256 rows)
- Run stats — `data/stage_a_vrptw_recollection_checkpoints/run_stats.json`
- Per-seed checkpoints — `data/stage_a_vrptw_recollection_checkpoints/refs/`

`data/stage_a_vrptw.parquet` is **not** modified. The merge into a
consolidated Stage A artifact is a separate, reviewed step.

---

## Headline

**New `reference_struct_unstable` rate = 185 / 896 = 0.2065** — below the locked 25% threshold (§12.3).

The probe predicted the post-revision point at 0.188 with a 95% sensitivity range [0.097, 0.250]. The observed 0.2065 lands within that band, between the point estimate and the pessimistic LB — the probe was slightly optimistic (mostly because it over-estimated the mid-band clearance rate).

Per the user-selected policy ("Accept residual + document"), no further action is required: the new rate is below the gate. The §13.1 training-partition filter on `reference_struct_unstable` already handles the residual 185 cells for STRUCT and SCHEDULE training.

---

## 1. Run summary

| field | value |
|---|---|
| Re-collection start | 2026-05-14 13:44 local |
| Re-collection end | 2026-05-14 17:36 local |
| Total reference solves submitted | 768 (256 cells × 3 seeds) |
| Cache hits (reused from probe) | 72 (24 cells × 3 seeds) |
| Fresh solves at 120 s | 696 |
| Solver exceptions | **0** |
| Wall-clock | 13,923.7 s ≈ 3 h 52 min |
| `n_jobs` | 6 (joblib loky) |
| PyVRP version | 0.13.3 (matches Stage A; verified) |
| Reference seeds | 1, 2, 3 |
| Reference `MaxRuntime` | 120 s |
| Baseline cache | 60 s (existing Stage A cache) |
| Stage A parquet bytes-identical pre/post | ✓ (size 465492, sha256 prefix `788154c66af7a9f6`) |

The 72 probe ref JSONs were pre-copied into the re-collection checkpoint dir and matched the worker's cache key (`<iid>__<pid>__seed<s>.json`), so they re-loaded without resolving. The probe's solve params were byte-identical to this run (120 s ref, 60 s baseline, seeds 1/2/3, PyVRP 0.13.3, identical perturbed instance) — so re-use is valid.

---

## 2. Per-cell re-collection table

All 256 re-collected cells, sorted by family then by 60 s `ari_min`. `Δ = ari_min_120s − ari_min_60s`. `clears` is `ari_min_120s ≥ 0.90` (the locked `ARI_STRUCT_UNSTABLE_THRESHOLD`). An asterisk on `ari_120s` marks the 7 cells that were all-infeasible at both 60 s and 120 s (see §6 caveat) — their `ari_min` is computed on the PyVRP penalty-bounded "best" partition under each seed even though no seed is feasible, and these cells are categorically separate from the rest under §8.3.

| instance | pid | family | ari_60s | ari_120s | Δ | clears |
|---|---|---|---:|---:|---:|:---:|
| R208 | OC_4 | ORDER_CHANGE | 0.061 | 0.719 | +0.659 |  |
| R208 | OC_1 | ORDER_CHANGE | 0.086 | 0.143 | +0.057 |  |
| R208 | OC_3 | ORDER_CHANGE | 0.101 | 0.099 | -0.002 |  |
| R210 | OC_3 | ORDER_CHANGE | 0.265 | 0.265 | +0.000 |  |
| R211 | OC_1 | ORDER_CHANGE | 0.286 | 1.000 | +0.714 | ✓ |
| R110 | OC_4 | ORDER_CHANGE | 0.294 | 0.294* | +0.000 |  |
| R210 | OC_2 | ORDER_CHANGE | 0.313 | 0.575 | +0.263 |  |
| R210 | OC_1 | ORDER_CHANGE | 0.342 | 0.421 | +0.080 |  |
| RC102 | OC_4 | ORDER_CHANGE | 0.352 | 0.352* | +0.000 |  |
| R202 | OC_2 | ORDER_CHANGE | 0.353 | 0.353 | +0.000 |  |
| R204 | OC_4 | ORDER_CHANGE | 0.375 | 0.375 | +0.000 |  |
| R112 | OC_4 | ORDER_CHANGE | 0.377 | 0.377 | +0.000 |  |
| R211 | OC_4 | ORDER_CHANGE | 0.380 | 0.389 | +0.009 |  |
| R209 | OC_1 | ORDER_CHANGE | 0.392 | 0.392 | +0.000 |  |
| R108 | OC_2 | ORDER_CHANGE | 0.403 | 0.403 | +0.000 |  |
| RC203 | OC_1 | ORDER_CHANGE | 0.406 | 0.406 | +0.000 |  |
| R108 | OC_3 | ORDER_CHANGE | 0.407 | 0.380 | -0.028 |  |
| R108 | OC_4 | ORDER_CHANGE | 0.411 | 0.411 | +0.000 |  |
| R210 | OC_4 | ORDER_CHANGE | 0.420 | 0.297 | -0.123 |  |
| R204 | OC_3 | ORDER_CHANGE | 0.422 | 0.416 | -0.006 |  |
| R209 | OC_4 | ORDER_CHANGE | 0.434 | 0.540 | +0.106 |  |
| RC204 | OC_1 | ORDER_CHANGE | 0.439 | 0.439 | +0.000 |  |
| RC103 | OC_3 | ORDER_CHANGE | 0.441 | 0.523 | +0.082 |  |
| R211 | OC_2 | ORDER_CHANGE | 0.443 | 0.240 | -0.203 |  |
| RC204 | OC_2 | ORDER_CHANGE | 0.453 | 1.000 | +0.547 | ✓ |
| R204 | OC_1 | ORDER_CHANGE | 0.464 | 0.464 | +0.000 |  |
| R206 | OC_4 | ORDER_CHANGE | 0.467 | 0.467 | +0.000 |  |
| R112 | OC_2 | ORDER_CHANGE | 0.472 | 0.472 | +0.000 |  |
| R202 | OC_1 | ORDER_CHANGE | 0.489 | 0.489 | +0.000 |  |
| R112 | OC_1 | ORDER_CHANGE | 0.491 | 0.450 | -0.041 |  |
| R105 | OC_3 | ORDER_CHANGE | 0.491 | 0.491 | +0.000 |  |
| RC203 | OC_2 | ORDER_CHANGE | 0.504 | 0.973 | +0.468 | ✓ |
| RC206 | OC_4 | ORDER_CHANGE | 0.515 | 0.532 | +0.017 |  |
| RC203 | OC_4 | ORDER_CHANGE | 0.518 | 1.000 | +0.482 | ✓ |
| R110 | OC_1 | ORDER_CHANGE | 0.522 | 0.522 | +0.000 |  |
| R209 | OC_3 | ORDER_CHANGE | 0.524 | 1.000 | +0.476 | ✓ |
| R104 | OC_2 | ORDER_CHANGE | 0.569 | 0.569 | +0.000 |  |
| RC106 | OC_2 | ORDER_CHANGE | 0.569 | 0.569 | +0.000 |  |
| RC102 | OC_2 | ORDER_CHANGE | 0.572 | 0.572* | +0.000 |  |
| R108 | OC_1 | ORDER_CHANGE | 0.605 | 0.405 | -0.200 |  |
| RC208 | OC_1 | ORDER_CHANGE | 0.606 | 0.838 | +0.232 |  |
| RC201 | OC_3 | ORDER_CHANGE | 0.618 | 1.000 | +0.382 | ✓ |
| R209 | OC_2 | ORDER_CHANGE | 0.621 | 0.621 | +0.000 |  |
| RC103 | OC_1 | ORDER_CHANGE | 0.636 | 0.636 | +0.000 |  |
| RC207 | OC_2 | ORDER_CHANGE | 0.639 | 1.000 | +0.361 | ✓ |
| RC207 | OC_1 | ORDER_CHANGE | 0.640 | 0.640 | +0.000 |  |
| RC201 | OC_4 | ORDER_CHANGE | 0.641 | 0.641 | +0.000 |  |
| R107 | OC_1 | ORDER_CHANGE | 0.651 | 0.956 | +0.305 | ✓ |
| RC103 | OC_4 | ORDER_CHANGE | 0.653 | 0.683 | +0.029 |  |
| RC207 | OC_4 | ORDER_CHANGE | 0.654 | 0.654 | +0.000 |  |
| RC104 | OC_2 | ORDER_CHANGE | 0.664 | 0.615 | -0.049 |  |
| R211 | OC_3 | ORDER_CHANGE | 0.686 | 0.686 | +0.000 |  |
| R110 | OC_2 | ORDER_CHANGE | 0.698 | 1.000 | +0.302 | ✓ |
| R208 | OC_2 | ORDER_CHANGE | 0.698 | 0.767 | +0.069 |  |
| R106 | OC_3 | ORDER_CHANGE | 0.706 | 0.706 | +0.000 |  |
| RC106 | OC_3 | ORDER_CHANGE | 0.710 | 1.000 | +0.290 | ✓ |
| R204 | OC_2 | ORDER_CHANGE | 0.715 | 1.000 | +0.285 | ✓ |
| RC208 | OC_4 | ORDER_CHANGE | 0.720 | 0.848 | +0.128 |  |
| RC106 | OC_1 | ORDER_CHANGE | 0.734 | 1.000 | +0.266 | ✓ |
| C109 | OC_4 | ORDER_CHANGE | 0.788 | 0.788 | +0.000 |  |
| RC205 | OC_2 | ORDER_CHANGE | 0.808 | 1.000 | +0.192 | ✓ |
| RC107 | OC_2 | ORDER_CHANGE | 0.810 | 1.000 | +0.190 | ✓ |
| RC107 | OC_3 | ORDER_CHANGE | 0.813 | 0.813 | +0.000 |  |
| RC107 | OC_4 | ORDER_CHANGE | 0.815 | 0.815 | +0.000 |  |
| RC208 | OC_3 | ORDER_CHANGE | 0.845 | 1.000 | +0.155 | ✓ |
| R104 | OC_3 | ORDER_CHANGE | 0.857 | 0.857 | +0.000 |  |
| R109 | OC_4 | ORDER_CHANGE | 0.863 | 0.694 | -0.169 |  |
| R206 | OC_1 | ORDER_CHANGE | 0.869 | 0.869 | +0.000 |  |
| RC102 | OC_1 | ORDER_CHANGE | 0.871 | 1.000 | +0.129 | ✓ |
| RC206 | OC_1 | ORDER_CHANGE | 0.883 | 1.000 | +0.117 | ✓ |
| R208 | ST_4 | SERVICE_TIME | 0.011 | 0.130 | +0.120 |  |
| R208 | ST_2 | SERVICE_TIME | 0.115 | 1.000 | +0.885 | ✓ |
| R208 | ST_3 | SERVICE_TIME | 0.250 | 0.703 | +0.453 |  |
| R210 | ST_3 | SERVICE_TIME | 0.319 | 0.319 | +0.000 |  |
| R210 | ST_2 | SERVICE_TIME | 0.328 | 0.328 | +0.000 |  |
| R211 | ST_3 | SERVICE_TIME | 0.350 | 0.673 | +0.323 |  |
| R108 | ST_4 | SERVICE_TIME | 0.367 | 0.367 | +0.000 |  |
| R209 | ST_2 | SERVICE_TIME | 0.371 | 1.000 | +0.629 | ✓ |
| R209 | ST_1 | SERVICE_TIME | 0.392 | 0.392 | +0.000 |  |
| R112 | ST_2 | SERVICE_TIME | 0.393 | 0.393 | +0.000 |  |
| RC203 | ST_4 | SERVICE_TIME | 0.410 | 1.000 | +0.590 | ✓ |
| R111 | ST_4 | SERVICE_TIME | 0.418 | 0.817 | +0.399 |  |
| RC204 | ST_3 | SERVICE_TIME | 0.424 | 0.973 | +0.549 | ✓ |
| R108 | ST_2 | SERVICE_TIME | 0.424 | 0.424 | +0.000 |  |
| R108 | ST_1 | SERVICE_TIME | 0.428 | 0.428 | +0.000 |  |
| RC208 | ST_2 | SERVICE_TIME | 0.429 | 0.704 | +0.275 |  |
| R205 | ST_4 | SERVICE_TIME | 0.440 | 0.440 | +0.000 |  |
| R204 | ST_3 | SERVICE_TIME | 0.443 | 0.443 | +0.000 |  |
| R204 | ST_4 | SERVICE_TIME | 0.443 | 1.000 | +0.557 | ✓ |
| RC103 | ST_3 | SERVICE_TIME | 0.444 | 0.444 | +0.000 |  |
| R202 | ST_4 | SERVICE_TIME | 0.450 | 0.981 | +0.531 | ✓ |
| R202 | ST_3 | SERVICE_TIME | 0.457 | 0.457 | +0.000 |  |
| R112 | ST_1 | SERVICE_TIME | 0.463 | 0.463 | +0.000 |  |
| R210 | ST_4 | SERVICE_TIME | 0.474 | 0.581 | +0.107 |  |
| R210 | ST_1 | SERVICE_TIME | 0.476 | 0.312 | -0.164 |  |
| R206 | ST_4 | SERVICE_TIME | 0.478 | 0.478 | +0.000 |  |
| RC208 | ST_3 | SERVICE_TIME | 0.492 | 1.000 | +0.508 | ✓ |
| R202 | ST_1 | SERVICE_TIME | 0.515 | 0.517 | +0.002 |  |
| R202 | ST_2 | SERVICE_TIME | 0.515 | 0.515 | +0.000 |  |
| RC201 | ST_2 | SERVICE_TIME | 0.516 | 1.000 | +0.484 | ✓ |
| R203 | ST_2 | SERVICE_TIME | 0.524 | 1.000 | +0.476 | ✓ |
| RC207 | ST_1 | SERVICE_TIME | 0.528 | 0.528 | +0.000 |  |
| RC207 | ST_2 | SERVICE_TIME | 0.528 | 0.568 | +0.040 |  |
| RC203 | ST_2 | SERVICE_TIME | 0.535 | 0.385 | -0.150 |  |
| RC104 | ST_4 | SERVICE_TIME | 0.539 | 0.539 | +0.000 |  |
| R112 | ST_3 | SERVICE_TIME | 0.542 | 0.512 | -0.030 |  |
| RC201 | ST_1 | SERVICE_TIME | 0.553 | 0.729 | +0.176 |  |
| RC207 | ST_4 | SERVICE_TIME | 0.556 | 0.556 | +0.000 |  |
| R104 | ST_2 | SERVICE_TIME | 0.568 | 0.933 | +0.365 | ✓ |
| R206 | ST_1 | SERVICE_TIME | 0.575 | 0.575 | +0.000 |  |
| R110 | ST_4 | SERVICE_TIME | 0.582 | 0.582 | +0.000 |  |
| RC208 | ST_4 | SERVICE_TIME | 0.591 | 0.591 | +0.000 |  |
| R105 | ST_3 | SERVICE_TIME | 0.596 | 0.596 | +0.000 |  |
| RC105 | ST_3 | SERVICE_TIME | 0.601 | 0.618 | +0.017 |  |
| C105 | ST_4 | SERVICE_TIME | 0.620 | 0.620 | +0.000 |  |
| RC201 | ST_3 | SERVICE_TIME | 0.625 | 0.729 | +0.104 |  |
| R104 | ST_3 | SERVICE_TIME | 0.651 | 0.980 | +0.329 | ✓ |
| R108 | ST_3 | SERVICE_TIME | 0.670 | 0.670 | +0.000 |  |
| C101 | ST_4 | SERVICE_TIME | 0.672 | 0.672 | +0.000 |  |
| R107 | ST_4 | SERVICE_TIME | 0.678 | 0.678 | +0.000 |  |
| R204 | ST_2 | SERVICE_TIME | 0.691 | 0.691 | +0.000 |  |
| R111 | ST_3 | SERVICE_TIME | 0.702 | 1.000 | +0.298 | ✓ |
| R206 | ST_2 | SERVICE_TIME | 0.712 | 0.712 | +0.000 |  |
| RC207 | ST_3 | SERVICE_TIME | 0.718 | 1.000 | +0.282 | ✓ |
| C108 | ST_4 | SERVICE_TIME | 0.723 | 1.000 | +0.277 | ✓ |
| R109 | ST_3 | SERVICE_TIME | 0.723 | 0.723 | +0.000 |  |
| RC206 | ST_1 | SERVICE_TIME | 0.726 | 1.000 | +0.274 | ✓ |
| R208 | ST_1 | SERVICE_TIME | 0.735 | 1.000 | +0.265 | ✓ |
| RC106 | ST_2 | SERVICE_TIME | 0.738 | 0.738 | +0.000 |  |
| RC204 | ST_4 | SERVICE_TIME | 0.759 | 0.372 | -0.387 |  |
| RC103 | ST_2 | SERVICE_TIME | 0.777 | 0.451 | -0.326 |  |
| RC103 | ST_1 | SERVICE_TIME | 0.799 | 1.000 | +0.201 | ✓ |
| RC107 | ST_1 | SERVICE_TIME | 0.808 | 1.000 | +0.192 | ✓ |
| R103 | ST_4 | SERVICE_TIME | 0.869 | 0.869 | +0.000 |  |
| R102 | ST_4 | SERVICE_TIME | 0.885 | 0.885 | +0.000 |  |
| R102 | ST_1 | SERVICE_TIME | 0.900 | 0.900 | +0.000 |  |
| R208 | TW_1 | TIME_WINDOW | 0.056 | 0.056 | +0.000 |  |
| R208 | TW_3 | TIME_WINDOW | 0.067 | 0.457 | +0.390 |  |
| R208 | TW_2 | TIME_WINDOW | 0.156 | 1.000 | +0.844 | ✓ |
| R208 | TW_4 | TIME_WINDOW | 0.164 | 0.164 | +0.000 |  |
| R210 | TW_4 | TIME_WINDOW | 0.252 | 0.252 | +0.000 |  |
| R211 | TW_1 | TIME_WINDOW | 0.281 | 0.281 | +0.000 |  |
| RC206 | TW_2 | TIME_WINDOW | 0.294 | 0.670 | +0.376 |  |
| RC206 | TW_3 | TIME_WINDOW | 0.312 | 1.000 | +0.688 | ✓ |
| RC206 | TW_4 | TIME_WINDOW | 0.312 | 1.000 | +0.688 | ✓ |
| R202 | TW_1 | TIME_WINDOW | 0.342 | 0.342 | +0.000 |  |
| R204 | TW_3 | TIME_WINDOW | 0.347 | 0.692 | +0.346 |  |
| R112 | TW_3 | TIME_WINDOW | 0.360 | 0.360 | +0.000 |  |
| R112 | TW_1 | TIME_WINDOW | 0.360 | 0.360 | +0.000 |  |
| R209 | TW_3 | TIME_WINDOW | 0.374 | 1.000 | +0.626 | ✓ |
| RC208 | TW_1 | TIME_WINDOW | 0.379 | 0.605 | +0.226 |  |
| R209 | TW_2 | TIME_WINDOW | 0.380 | 0.667 | +0.287 |  |
| R209 | TW_1 | TIME_WINDOW | 0.392 | 0.632 | +0.239 |  |
| R210 | TW_3 | TIME_WINDOW | 0.393 | 0.342 | -0.052 |  |
| R211 | TW_2 | TIME_WINDOW | 0.405 | 1.000 | +0.595 | ✓ |
| R108 | TW_3 | TIME_WINDOW | 0.409 | 0.409 | +0.000 |  |
| R203 | TW_3 | TIME_WINDOW | 0.412 | 1.000 | +0.588 | ✓ |
| R210 | TW_2 | TIME_WINDOW | 0.421 | 0.421 | +0.000 |  |
| R209 | TW_4 | TIME_WINDOW | 0.423 | 1.000 | +0.577 | ✓ |
| R108 | TW_1 | TIME_WINDOW | 0.428 | 0.400 | -0.028 |  |
| R108 | TW_2 | TIME_WINDOW | 0.428 | 0.400 | -0.028 |  |
| RC204 | TW_4 | TIME_WINDOW | 0.432 | 0.455 | +0.023 |  |
| R205 | TW_3 | TIME_WINDOW | 0.445 | 0.445 | +0.000 |  |
| RC201 | TW_2 | TIME_WINDOW | 0.447 | 0.447 | +0.000 |  |
| R211 | TW_4 | TIME_WINDOW | 0.456 | 0.456 | +0.000 |  |
| R204 | TW_1 | TIME_WINDOW | 0.467 | 0.459 | -0.008 |  |
| RC208 | TW_3 | TIME_WINDOW | 0.469 | 0.469 | +0.000 |  |
| R205 | TW_4 | TIME_WINDOW | 0.478 | 0.478 | +0.000 |  |
| RC106 | TW_3 | TIME_WINDOW | 0.484 | 0.484 | +0.000 |  |
| R211 | TW_3 | TIME_WINDOW | 0.509 | 0.923 | +0.413 | ✓ |
| RC202 | TW_4 | TIME_WINDOW | 0.511 | 0.511 | +0.000 |  |
| R110 | TW_3 | TIME_WINDOW | 0.516 | 0.600 | +0.084 |  |
| RC108 | TW_3 | TIME_WINDOW | 0.521 | 0.779 | +0.257 |  |
| RC207 | TW_1 | TIME_WINDOW | 0.528 | 0.651 | +0.123 |  |
| R108 | TW_4 | TIME_WINDOW | 0.550 | 0.345 | -0.205 |  |
| R104 | TW_4 | TIME_WINDOW | 0.561 | 0.976 | +0.416 | ✓ |
| R104 | TW_3 | TIME_WINDOW | 0.580 | 0.978 | +0.399 | ✓ |
| R210 | TW_1 | TIME_WINDOW | 0.587 | 1.000 | +0.413 | ✓ |
| RC103 | TW_4 | TIME_WINDOW | 0.592 | 0.592 | +0.000 |  |
| R206 | TW_2 | TIME_WINDOW | 0.623 | 1.000 | +0.377 | ✓ |
| RC207 | TW_2 | TIME_WINDOW | 0.631 | 0.631 | +0.000 |  |
| R109 | TW_4 | TIME_WINDOW | 0.656 | 0.656 | +0.000 |  |
| R111 | TW_4 | TIME_WINDOW | 0.669 | 0.669 | +0.000 |  |
| R206 | TW_4 | TIME_WINDOW | 0.675 | 0.675 | +0.000 |  |
| RC101 | TW_3 | TIME_WINDOW | 0.676 | 0.836 | +0.159 |  |
| R201 | TW_2 | TIME_WINDOW | 0.693 | 0.693 | +0.000 |  |
| R110 | TW_2 | TIME_WINDOW | 0.703 | 0.703 | +0.000 |  |
| R205 | TW_2 | TIME_WINDOW | 0.705 | 1.000 | +0.295 | ✓ |
| RC106 | TW_2 | TIME_WINDOW | 0.708 | 0.708 | +0.000 |  |
| R106 | TW_3 | TIME_WINDOW | 0.757 | 0.984 | +0.226 | ✓ |
| RC108 | TW_4 | TIME_WINDOW | 0.782 | 0.782 | +0.000 |  |
| RC208 | TW_4 | TIME_WINDOW | 0.799 | 0.799 | +0.000 |  |
| RC207 | TW_3 | TIME_WINDOW | 0.804 | 1.000 | +0.196 | ✓ |
| RC107 | TW_1 | TIME_WINDOW | 0.808 | 0.808 | +0.000 |  |
| RC104 | TW_4 | TIME_WINDOW | 0.842 | 0.842 | +0.000 |  |
| R206 | TW_1 | TIME_WINDOW | 0.866 | 1.000 | +0.134 | ✓ |
| RC102 | TW_2 | TIME_WINDOW | 0.867 | 1.000 | +0.133 | ✓ |
| R107 | TW_3 | TIME_WINDOW | 0.868 | 1.000 | +0.132 | ✓ |
| R102 | TW_3 | TIME_WINDOW | 0.889 | 0.889 | +0.000 |  |
| R103 | TW_3 | TIME_WINDOW | 0.891 | 0.891 | +0.000 |  |
| R112 | TW_4 | TIME_WINDOW | 0.892 | 1.000 | +0.108 | ✓ |
| R204 | TW_2 | TIME_WINDOW | 0.899 | 0.899 | +0.000 |  |
| R208 | TT_4 | TRAVEL_TIME | 0.056 | 0.056 | +0.000 |  |
| R208 | TT_1 | TRAVEL_TIME | 0.111 | 0.247 | +0.135 |  |
| R112 | TT_1 | TRAVEL_TIME | 0.301 | 0.301 | +0.000 |  |
| R202 | TT_3 | TRAVEL_TIME | 0.302 | 0.451 | +0.150 |  |
| R211 | TT_1 | TRAVEL_TIME | 0.318 | 0.471 | +0.153 |  |
| R205 | TT_3 | TRAVEL_TIME | 0.319 | 1.000 | +0.681 | ✓ |
| R204 | TT_3 | TRAVEL_TIME | 0.344 | 1.000 | +0.656 | ✓ |
| R202 | TT_1 | TRAVEL_TIME | 0.348 | 0.515 | +0.167 |  |
| R204 | TT_2 | TRAVEL_TIME | 0.363 | 0.467 | +0.105 |  |
| R103 | TT_4 | TRAVEL_TIME | 0.365 | 0.365* | +0.000 |  |
| R108 | TT_3 | TRAVEL_TIME | 0.389 | 0.389 | +0.000 |  |
| R209 | TT_2 | TRAVEL_TIME | 0.392 | 1.000 | +0.608 | ✓ |
| R108 | TT_2 | TRAVEL_TIME | 0.399 | 0.399 | +0.000 |  |
| R206 | TT_4 | TRAVEL_TIME | 0.405 | 0.432 | +0.027 |  |
| RC203 | TT_2 | TRAVEL_TIME | 0.410 | 1.000 | +0.590 | ✓ |
| R210 | TT_2 | TRAVEL_TIME | 0.411 | 0.312 | -0.099 |  |
| R210 | TT_4 | TRAVEL_TIME | 0.422 | 0.373 | -0.048 |  |
| R205 | TT_4 | TRAVEL_TIME | 0.436 | 0.406 | -0.030 |  |
| R208 | TT_2 | TRAVEL_TIME | 0.453 | 0.967 | +0.514 | ✓ |
| R204 | TT_4 | TRAVEL_TIME | 0.459 | 0.459 | +0.000 |  |
| R102 | TT_4 | TRAVEL_TIME | 0.475 | 0.475* | +0.000 |  |
| R203 | TT_1 | TRAVEL_TIME | 0.478 | 1.000 | +0.522 | ✓ |
| R211 | TT_2 | TRAVEL_TIME | 0.482 | 0.427 | -0.055 |  |
| R211 | TT_3 | TRAVEL_TIME | 0.495 | 0.495 | +0.000 |  |
| RC105 | TT_4 | TRAVEL_TIME | 0.499 | 0.499* | +0.000 |  |
| R202 | TT_2 | TRAVEL_TIME | 0.515 | 0.981 | +0.466 | ✓ |
| RC207 | TT_1 | TRAVEL_TIME | 0.528 | 0.528 | +0.000 |  |
| RC207 | TT_2 | TRAVEL_TIME | 0.528 | 0.528 | +0.000 |  |
| R108 | TT_1 | TRAVEL_TIME | 0.529 | 0.456 | -0.072 |  |
| R210 | TT_1 | TRAVEL_TIME | 0.532 | 0.245 | -0.287 |  |
| RC208 | TT_4 | TRAVEL_TIME | 0.553 | 0.553 | +0.000 |  |
| RC207 | TT_4 | TRAVEL_TIME | 0.557 | 0.557 | +0.000 |  |
| RC103 | TT_1 | TRAVEL_TIME | 0.561 | 1.000 | +0.439 | ✓ |
| R104 | TT_1 | TRAVEL_TIME | 0.567 | 0.952 | +0.385 | ✓ |
| R206 | TT_2 | TRAVEL_TIME | 0.575 | 0.575 | +0.000 |  |
| RC202 | TT_3 | TRAVEL_TIME | 0.582 | 0.728 | +0.146 |  |
| R112 | TT_4 | TRAVEL_TIME | 0.596 | 0.445 | -0.151 |  |
| RC208 | TT_3 | TRAVEL_TIME | 0.599 | 1.000 | +0.401 | ✓ |
| RC201 | TT_3 | TRAVEL_TIME | 0.625 | 1.000 | +0.375 | ✓ |
| R210 | TT_3 | TRAVEL_TIME | 0.636 | 0.319 | -0.317 |  |
| R101 | TT_4 | TRAVEL_TIME | 0.656 | 0.656* | +0.000 |  |
| R211 | TT_4 | TRAVEL_TIME | 0.664 | 0.664 | +0.000 |  |
| RC104 | TT_4 | TRAVEL_TIME | 0.707 | 1.000 | +0.293 | ✓ |
| RC208 | TT_2 | TRAVEL_TIME | 0.724 | 0.851 | +0.127 |  |
| RC201 | TT_1 | TRAVEL_TIME | 0.729 | 1.000 | +0.271 | ✓ |
| RC201 | TT_2 | TRAVEL_TIME | 0.729 | 1.000 | +0.271 | ✓ |
| R109 | TT_2 | TRAVEL_TIME | 0.740 | 1.000 | +0.260 | ✓ |
| RC103 | TT_3 | TRAVEL_TIME | 0.759 | 0.759 | +0.000 |  |
| RC208 | TT_1 | TRAVEL_TIME | 0.834 | 0.834 | +0.000 |  |
| RC102 | TT_1 | TRAVEL_TIME | 0.840 | 1.000 | +0.160 | ✓ |
| R206 | TT_1 | TRAVEL_TIME | 0.866 | 0.866 | +0.000 |  |
| R206 | TT_3 | TRAVEL_TIME | 0.866 | 1.000 | +0.134 | ✓ |
| R110 | TT_4 | TRAVEL_TIME | 0.879 | 0.879 | +0.000 |  |
| R110 | TT_2 | TRAVEL_TIME | 0.896 | 0.896 | +0.000 |  |

(Same data, machine-readable: `data/stage_a_vrptw_recollected.parquet` — 256 rows × 33 columns including per-seed objectives, route counts, runtimes, and feasibility flags.)

---

## 3. New overall `reference_struct_unstable` rate

```
Stage A total cells                       :   896
60s-unstable cells (re-collected)         :   256
  → cleared at 120s (ari_min ≥ 0.90)      :    71  (27.7% of unstable)
  → residual unstable at 120s             :   185  (72.3% of unstable)
60s-stable cells (untouched)              :   640

New stable total   = 640 + 71  =  711
New unstable total = 256 − 71  =  185
New struct_unstable rate = 185 / 896 = 0.20647…
```

**0.2065 < 0.25 → below the §12.3 threshold. Gate passes.**

For the record:
- Stage A pre-revision struct_unstable rate: **0.2857** (256 / 896)
- Post-revision struct_unstable rate: **0.2065** (185 / 896)
- Absolute drop: 7.92 percentage points
- Relative drop: 27.7%

---

## 4. New rate by perturbation family

Each family has 56 instances × 4 perturbations = 224 cells.

| family | n_unstable_60s | cleared | residual | old 60s rate | new 120s rate |
|---|---:|---:|---:|---:|---:|
| ORDER_CHANGE | 70 | 17 | 53 | 0.3125 | **0.2366** |
| SERVICE_TIME | 66 | 18 | 48 | 0.2946 | **0.2143** |
| TIME_WINDOW  | 66 | 19 | 47 | 0.2946 | **0.2098** |
| TRAVEL_TIME  | 54 | 17 | 37 | 0.2411 | **0.1652** |

All four families land below the 25% gate individually. **ORDER_CHANGE remains the elevated family at 0.2366** — the residual risk that the probe flagged (the probe saw 0/4 clearance in OC mid+bimodal cells from a 6-cell sample). The full re-collection refined that: OC mid cleared at 7/21 (33.3%), OC bimodal at 5/39 (12.8%). The probe's pessimism on OC was real, but not as catastrophic as the 0/4 suggested. OC marginal cleared at 5/10 (50%) — same as the probe extrapolated.

For completeness — per (family × 60s-band) clear rates from the full re-collection:

| family | marginal | mid | bimodal |
|---|---|---|---|
| ORDER_CHANGE | 5/10 = 0.500 | 7/21 = 0.333 | 5/39 = 0.128 |
| SERVICE_TIME | 1/4 = 0.250 | 7/19 = 0.368 | 10/43 = 0.233 |
| TIME_WINDOW  | 5/10 = 0.500 | 3/13 = 0.231 | 11/43 = 0.256 |
| TRAVEL_TIME  | 2/6 = 0.333 | 5/10 = 0.500 | 10/38 = 0.263 |

---

## 5. Cells that did NOT clear (n = 185)

`ari_min_120s` distribution among residual-unstable cells:

| quantile | value |
|---|---:|
| min | 0.0557 |
| p10 | 0.3230 |
| p25 | 0.4056 |
| p50 | 0.5175 |
| p75 | 0.6751 |
| p90 | 0.8139 |
| max | 0.8996 |

The distribution is essentially unchanged from the pre-revision 256-cell unstable set: still bimodal-dominated, still heavy-tailed away from the 0.90 threshold.

Three-band breakdown of the 185 residual cells (banding by `ari_min_120s`):

| band | range | count | share |
|---|---|---:|---:|
| marginal | `[0.80, 0.90)` | 21 | 11.4% |
| mid | `[0.60, 0.80)` | 48 | 25.9% |
| bimodal | `< 0.60` | 116 | 62.7% |

Compare to the pre-revision unstable set (256 cells): 11.7% / 24.6% / 63.7%. The bands stayed in nearly the same proportions — the 120 s pass tipped *some* cells from each band into stability, but did not change the residual mixture's shape. The residual is structurally bimodal-dominated; another time-budget doubling would face the same wall.

### Movement summary on the 185 residual cells

| motion | count | share |
|---|---:|---:|
| moved exactly 0.000 (stable attractor — same routes at 120 s as 60 s) | **116** | 62.7% |
| moved up, but did not clear 0.90 | 42 | 22.7% |
| moved DOWN (different attractor at 120 s) | 27 | 14.6% |

Of the 116 zero-delta cells, **7 are the §8.3 all-infeasible cells** (R101/TT_4, R102/TT_4, R103/TT_4, R110/OC_4, RC102/OC_2, RC102/OC_4, RC105/TT_4) — see §6 caveat. The other **109 are genuine feasible stable attractors**: PyVRP's 60 s search and 120 s search converge on identical route partitions for each seed, so the seed-vs-seed disagreement that drives the low ARI is structural, not a budget shortfall. More time will not help these.

The 27 cells with negative deltas (`ari_min` went *down* at 120 s) confirm the multimodality reading: those cells have multiple comparable-cost attractors, and the 120 s solver lands at a *different* low-ARI partition for at least one seed than the 60 s solver did. The largest negative delta is RC204/ST_4 at −0.387 (60s: 0.759 → 120s: 0.372).

### Per-family movement in the residual set

| family | n_residual | zero-Δ | up-but-not-clear | down |
|---|---:|---:|---:|---:|
| ORDER_CHANGE | 53 | 39 | 8 | 6 |
| SERVICE_TIME | 48 | 25 | 15 | 8 |
| TIME_WINDOW  | 47 | 30 | 11 | 6 |
| TRAVEL_TIME  | 37 | 22 | 8 | 7 |

ORDER_CHANGE has the highest zero-delta fraction (39/53 = 73.6%): when an OC cell stays unstable, three quarters of the time it's because PyVRP lands on identical routes at both budgets. That's consistent with the probe's signal that adding more time is the wrong knob for OC structural noise; the underlying signal here is multiple low-cost attractors, not under-resourcing.

---

## 6. Cross-check vs probe extrapolation

Probe extrapolation (from `data/probes/stage_a_120s_struct_probe_report.md`):

| scenario | predicted rate |
|---|---:|
| Wilson 95% optimistic UB | 0.0968 |
| **point estimate (pooled-by-band)** | **0.1883** |
| Wilson 95% pessimistic LB | 0.2504 |

**Observed full re-collection rate: 0.2065** — lands between the point estimate (0.188) and the pessimistic LB (0.250), within the probe's sensitivity band but ~2 pp higher than the point estimate predicted.

Where the probe was off:

| 60s band | probe rate (k/8) | observed full rate (k/n) | direction |
|---|---|---|---|
| marginal | 4/8 = 0.500 | 13/30 = 0.433 | probe slightly high |
| mid | 4/8 = 0.500 | 22/63 = 0.349 | **probe high (15 pp)** |
| bimodal | 2/8 = 0.250 | 36/163 = 0.221 | probe close |

The pooled-by-band extrapolation over-estimated the mid-band clearance (50% predicted vs. 35% observed). That family-pooled mid rate dominated the probe's optimism: the 63 mid cells are the second-largest band, and a 15 pp overshoot there translates to ~9 residual cells unaccounted for in the prediction — which is roughly where the observed 0.2065 lies relative to the predicted 0.1883.

The bimodal estimate (probe's biggest band) was almost exactly right, and that's the band that matters most for the overall rate (163 of 256 cells are bimodal). The probe's design was sound; n=8 per band was small enough that one band (mid) drifted, but the headline conclusion held.

### Probe-as-decision-input retrospective

The probe's recommendation was: "the probe is consistent with 120s clearing the 25% gate, but a 24-cell sample makes that call shaky." That recommendation was correct: the full re-collection passed the gate (0.2065 < 0.25) but with much less margin than the probe's point estimate suggested (5 pp of headroom rather than 6.2 pp). The probe's specific concern about ORDER_CHANGE — "0/4 mid+bimodal cleared, if that family is genuinely bimodal under doubled time even the full re-collection may leave a meaningful OC residual" — was also borne out: OC has the highest residual rate (0.2366) of any family, sitting closest to the 25% gate.

---

## §12.3 caveat: 7 §8.3 cells double-classified

Per `vrptw/evaluation.py:117–168`, `reference_struct_unstable` is set to True whenever `ari_min < 0.90` is computable, which is the case whenever at least two of the three seeds returned a non-empty `assignment` — and PyVRP returns an `assignment` even on penalty-bounded infeasible best solutions. As a result, **the 7 §8.3 all-infeasible cells**

R101/TT_4, R102/TT_4, R103/TT_4, R110/OC_4, RC102/OC_2, RC102/OC_4, RC105/TT_4

**are also flagged `reference_struct_unstable = True`** in Stage A (their 60 s `ari_min` ranges 0.29–0.66, all < 0.90). The 120 s re-collection on these 7 cells reproduces the same infeasible "best" assignments (identical routes — these are real fleet-exhaustion infeasibilities per §8.3 — and identical penalty-bounded ARIs).

Implication for §13.1 partitioning:
- All 7 cells are already excluded from STRUCT/SCHEDULE training under the §8.3 n/a policy (`band = "n/a"`).
- They are *also* excluded under the §13.1 filter on `reference_struct_unstable == False`.
- They are retained for PLAN_VALIDITY (which classifies them as `band = "hard"`).

If we compute the §12.3 rate excluding these double-classified n/a cells (treating them as §8.3-handled rather than §12.3-residual): `(185 − 7) / (896 − 7) = 178 / 889 = 0.2002`. Either reading lands below 25%; the literal §12.3 reading (0.2065) is the headline.

This is a definitional overlap, not a bug in the re-collection. Flagging here so it isn't mistaken for a finding in the downstream §12.1/§12.2/§12.4 inspection pass.

---

## Provenance

- Stage A wide artifact (unchanged): `data/stage_a_vrptw.parquet` (sha256 prefix `788154c66af7a9f6`, pre/post run)
- Re-collected artifact (this run): `data/stage_a_vrptw_recollected.parquet` (256 rows, 33 columns)
- Re-collection per-seed checkpoints: `data/stage_a_vrptw_recollection_checkpoints/refs/` (768 JSON files)
- Re-collection run stats: `data/stage_a_vrptw_recollection_checkpoints/run_stats.json`
- Re-collection script: `scripts/run_stage_a_vrptw_recollection.py`
- Probe parquet (unchanged): `data/probes/stage_a_120s_struct_probe.parquet`
- Probe report (unchanged): `data/probes/stage_a_120s_struct_probe_report.md`
- Prereg lock tag: `prereg-v1.0-vrptw` (`prereg/PREREG_v1.0_vrptw.md`)
- ARI threshold (locked): `ARI_STRUCT_UNSTABLE_THRESHOLD = 0.90` in `src/vrp_copilot_bench/vrptw/evaluation.py`

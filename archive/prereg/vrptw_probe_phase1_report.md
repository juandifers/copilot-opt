# VRPTW Phase 1 Stability Probe — Report

Generated: 2026-05-12T21:54:14


## Purpose

Exploratory external-validity probe. The preregistered CVRP Stage A benchmark found that PyVRP route partitions are highly unstable across seeds (`struct_unstable ≈ 0.926`, `median ari_min ≈ 0.476`) while objective references are stable (`obj_unstable ≈ 0`). This raised the concern that the `loss_struct` metric measures solver/partition multimodality rather than perturbation-induced structural change.

**Research question:** does adding VRPTW time-window constraints make PyVRP route structure more stable across seeds, by reducing the number of feasible high-quality partitions the solver can land on?

This phase runs **unperturbed** VRPTW only. Perturbations and a full Stage-A-style protocol are explicitly deferred.

## Dataset and solver setup

- Instances: C101, C201, R101, R201, RC101, RC201 (Solomon-100; sourced from PyVRP `Instances` GitHub mirror, CVRPLIB-extended VRPTW `.vrp` format).
- Seeds: [1, 2, 3].
- Time limit: 60s per solve.
- Solver: PyVRP 0.13.3 via `pyvrp.solve(..., stop=MaxRuntime, display=False, collect_stats=False)`.
- Workers: joblib loky, `n_jobs=6`.

## Scaling convention

PyVRP requires integer distance, duration, time-window, and service-duration values. To preserve one decimal of Euclidean distance precision while keeping every quantity on a common integer scale, all four are multiplied by **10** before being handed to PyVRP:

```
distance_matrix[i, j] = round(10 * euclidean(coords[i], coords[j]))
duration_matrix       = distance_matrix
time_windows          = round(10 * raw_time_windows)
service_times         = round(10 * raw_service_times)
```

The objective column is therefore in ×10 distance units. Stability metrics (pairwise ARI, relative objective drift, route-count delta) are scale-invariant, so this rescaling does not affect the probe's conclusions. **No BKS comparison is performed.**

## Per-instance results

| Instance |   n |    s1_obj    s2_obj    s3_obj |  r1  r2  r3 | f1 f2 f3 |  ari12  ari13  ari23 ari_min | OBJ? STR? RTE? |
|---|---|---|---|---|---|---|---|---|
| C101     | 100 |    8287.0    8287.0    8287.0 |  10  10  10 |  Y  Y  Y |  1.000  1.000  1.000   1.000 |    N    N    N |
| C201     | 100 |    5916.0    5916.0    5916.0 |   3   3   3 |  Y  Y  Y |  1.000  1.000  1.000   1.000 |    N    N    N |
| R101     | 100 |   16430.0   16430.0   16430.0 |  20  20  20 |  Y  Y  Y |  1.000  1.000  1.000   1.000 |    N    N    N |
| R201     | 100 |   11477.0   11477.0   11477.0 |   8   8   8 |  Y  Y  Y |  1.000  1.000  1.000   1.000 |    N    N    N |
| RC101    | 100 |   16230.0   16230.0   16230.0 |  15  15  15 |  Y  Y  Y |  1.000  1.000  1.000   1.000 |    N    N    N |
| RC201    | 100 |   12656.0   12657.0   12656.0 |   9   9   9 |  Y  Y  Y |  0.553  1.000  0.553   0.553 |    N    Y    N |

Legend: `r(1, 2, 3)` = number of routes per seed; `f(1, 2, 3)` = feasibility per seed (Y/N); `OBJ?` = `(max - min) / min > 0.02` across seeds; `STR?` = `ari_min < 0.9`; `RTE?` = at least two seeds disagree on the route count.

## Aggregate rates

- `n_instances` = 6
- `obj_unstable_rate`      = 0.000
- `struct_unstable_rate`   = 0.167
- `n_routes_unstable_rate` = 0.000
- `median ari_min`         = 1.000
- `ari_min` range          = [0.553, 1.000]

## Comparison vs. CVRP Stage A (qualitative)

| metric | CVRP Stage A | VRPTW Phase 1 |
|---|---|---|
| `obj_unstable_rate`      | 0.000 | 0.000 |
| `struct_unstable_rate`   | 0.926 | 0.167 |
| `median ari_min`         | 0.476 | 1.000 |

**Interpretation:** VRPTW route partitions appear **substantially more stable** across seeds than the CVRP baseline. Consistent with the hypothesis that time windows reduce the size of the feasible high-quality partition set the solver can land on.

## Caveats

- **No perturbations.** This phase only measures unperturbed reference stability across PyVRP seeds. Perturbed VRPTW probes are explicitly out of scope.
- **No BKS / quality validation.** Objectives are in ×10-scaled distance units and are not compared against published Solomon best-known solutions. The probe only asks how stable the solver is, not how good its solutions are.
- **Small n.** Six instances × three seeds = 18 solves. This is a feasibility probe, not a preregistered evaluation. Conclusions are directional only.
- **Exploratory.** This is an external-validity check against the preregistered CVRP Stage A benchmark, not a replacement for it. Preregistration (`prereg/PREREG_v0.5.md`) and the Stage A pipeline are unchanged.

Parquet output: `data/probes/vrptw_probe_phase1.parquet`

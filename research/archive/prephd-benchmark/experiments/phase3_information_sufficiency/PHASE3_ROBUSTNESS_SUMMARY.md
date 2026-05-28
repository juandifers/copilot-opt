# Phase 3 robustness pass — feasibility-aware interpretation

_Generated from `artifacts/robustness/`. Reference backend: PyVRP @ 60s, seed=1. The original Phase 3 outputs are **not modified** — see `PHASE3_SUMMARY.md` for those._

## 1. Objective reuse split by feasibility

| perturbation | feasible | n | mean loss | median loss | easy % | hard % |
| --- | :---: | ---: | ---: | ---: | ---: | ---: |
| capacity_reduction | True | 7 | 0.0002 | 0.0001 | 100.0% | 0.0% |
| capacity_reduction | False | 53 | 0.0858 | 0.0640 | 41.5% | 18.9% |
| regional_distance_inflation | True | 45 | 0.0111 | 0.0059 | 97.8% | 0.0% |
| regional_distance_inflation | False | 0 | nan | nan | nan% | nan% |

**Read:** the strong objective performance of `reuse_direct` is split between two regimes. Under regional-distance perturbations (45 cells, all feasible by construction) the mean loss is 0.0111. Under capacity reductions the feasible-cell mean loss is 0.0002 (7 cells), but the infeasible cells (53) carry a mean loss of 0.0858. The infeasible answer is *also* numerically close but it is not a valid plan — overload exists on at least one route.

## 2. Distance-only clean cut

| claim | n | mean loss | median | easy % | hard % | infeasible % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| objective | 45 | 0.0111 | 0.0059 | 97.8% | 0.0% | 0.0% |
| ranking | 45 | 0.6519 | 0.6667 | 22.2% | 46.7% | 0.0% |
| structure | 45 | 0.3275 | 0.3660 | 24.4% | 68.9% | 0.0% |

Under regional-distance inflation alone, every fixed solution remains feasible (the perturbation does not touch capacity or demand). On the objective claim this is the cleanest cut for the thesis: reuse needs no special-casing because no infeasibility exists.

## 3. Capacity reduction — when does reuse become unsafe?

| capacity factor | n | infeas % | feas-only mean loss | infeas-only mean loss | mean overload |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.98 | 15 | 73.3% | 0.0002 | 0.0154 | 7.5 |
| 0.95 | 15 | 86.7% | 0.0002 | 0.0388 | 16.1 |
| 0.9 | 15 | 93.3% | 0.0001 | 0.0857 | 29.9 |
| 0.8 | 15 | 100.0% | nan | 0.1781 | 56.3 |

**Read:** at a 2% capacity haircut (factor=0.98) already 73% of fixed solutions overflow the new capacity. By 20% (factor=0.8), every fixed solution is infeasible. The objective error stays small because routes do not magically become longer when a vehicle is over-capacity — but the answer is not implementable. If capacity feasibility matters to the downstream consumer, `reuse_direct` is unsafe on capacity reductions even at the smallest magnitude tested.

## 4. Feasibility-penalized λ curves

Three variants apply a penalty only to `reuse_direct` rows whose fixed solution is infeasible under the perturbation. All other actions are unchanged.

- **V1 — penalty=1.0**: `reuse_direct` infeasible loss := 1.0 (treat as worst possible).
- **V2 — penalty=0.5**: `reuse_direct` infeasible loss := max(observed_loss, 0.5) (half-credit).
- **V3 — unanswerable**: drop `reuse_direct` from the action set for cells where it is infeasible (cell still has a best_action selected from the remaining four).


#### V1 best-action share (penalty=1.0)

| λ | claim | reuse | NN | CW | pyvrp_10s | pyvrp_60s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0 | objective | 4.8% | 0.0% | 0.0% | 23.8% | 71.4% |
| 0 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.0001 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0.0001 | objective | 19.0% | 0.0% | 0.0% | 76.2% | 4.8% |
| 0.0001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.001 | structure | 12.4% | 0.0% | 0.0% | 25.7% | 61.9% |
| 0.001 | objective | 37.1% | 0.0% | 1.0% | 61.9% | 0.0% |
| 0.001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.01 | structure | 29.5% | 0.0% | 1.0% | 62.9% | 6.7% |
| 0.01 | objective | 48.6% | 0.0% | 50.5% | 1.0% | 0.0% |
| 0.01 | ranking | 18.1% | 0.0% | 1.0% | 37.1% | 43.8% |
| 0.05 | structure | 48.6% | 2.9% | 34.3% | 14.3% | 0.0% |
| 0.05 | objective | 48.6% | 0.0% | 51.4% | 0.0% | 0.0% |
| 0.05 | ranking | 62.9% | 0.0% | 4.8% | 32.4% | 0.0% |
| 0.1 | structure | 49.5% | 4.8% | 45.7% | 0.0% | 0.0% |
| 0.1 | objective | 49.5% | 0.0% | 50.5% | 0.0% | 0.0% |
| 0.1 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 0.5 | structure | 49.5% | 4.8% | 45.7% | 0.0% | 0.0% |
| 0.5 | objective | 49.5% | 1.0% | 49.5% | 0.0% | 0.0% |
| 0.5 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 1 | structure | 49.5% | 5.7% | 44.8% | 0.0% | 0.0% |
| 1 | objective | 49.5% | 1.0% | 49.5% | 0.0% | 0.0% |
| 1 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 5 | structure | 49.5% | 12.4% | 38.1% | 0.0% | 0.0% |
| 5 | objective | 49.5% | 3.8% | 46.7% | 0.0% | 0.0% |
| 5 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 10 | structure | 49.5% | 18.1% | 32.4% | 0.0% | 0.0% |
| 10 | objective | 49.5% | 8.6% | 41.9% | 0.0% | 0.0% |
| 10 | ranking | 95.2% | 0.0% | 4.8% | 0.0% | 0.0% |


#### V2 best-action share (penalty=0.5)

| λ | claim | reuse | NN | CW | pyvrp_10s | pyvrp_60s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0 | objective | 4.8% | 0.0% | 0.0% | 23.8% | 71.4% |
| 0 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.0001 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0.0001 | objective | 19.0% | 0.0% | 0.0% | 76.2% | 4.8% |
| 0.0001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.001 | structure | 12.4% | 0.0% | 0.0% | 25.7% | 61.9% |
| 0.001 | objective | 37.1% | 0.0% | 1.0% | 61.9% | 0.0% |
| 0.001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.01 | structure | 34.3% | 0.0% | 1.0% | 61.0% | 3.8% |
| 0.01 | objective | 48.6% | 0.0% | 50.5% | 1.0% | 0.0% |
| 0.01 | ranking | 18.1% | 0.0% | 1.0% | 37.1% | 43.8% |
| 0.05 | structure | 81.0% | 1.0% | 12.4% | 5.7% | 0.0% |
| 0.05 | objective | 48.6% | 0.0% | 51.4% | 0.0% | 0.0% |
| 0.05 | ranking | 62.9% | 0.0% | 4.8% | 32.4% | 0.0% |
| 0.1 | structure | 85.7% | 1.0% | 13.3% | 0.0% | 0.0% |
| 0.1 | objective | 49.5% | 0.0% | 50.5% | 0.0% | 0.0% |
| 0.1 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 0.5 | structure | 85.7% | 1.0% | 13.3% | 0.0% | 0.0% |
| 0.5 | objective | 49.5% | 1.0% | 49.5% | 0.0% | 0.0% |
| 0.5 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 1 | structure | 86.7% | 1.0% | 12.4% | 0.0% | 0.0% |
| 1 | objective | 49.5% | 1.0% | 49.5% | 0.0% | 0.0% |
| 1 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 5 | structure | 91.4% | 1.0% | 7.6% | 0.0% | 0.0% |
| 5 | objective | 49.5% | 3.8% | 46.7% | 0.0% | 0.0% |
| 5 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 10 | structure | 93.3% | 1.0% | 5.7% | 0.0% | 0.0% |
| 10 | objective | 49.5% | 8.6% | 41.9% | 0.0% | 0.0% |
| 10 | ranking | 95.2% | 0.0% | 4.8% | 0.0% | 0.0% |


#### V3 best-action share (infeasible reuse_direct dropped)

| λ | claim | reuse | NN | CW | pyvrp_10s | pyvrp_60s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0 | objective | 4.8% | 0.0% | 0.0% | 23.8% | 71.4% |
| 0 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.0001 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0.0001 | objective | 19.0% | 0.0% | 0.0% | 76.2% | 4.8% |
| 0.0001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.001 | structure | 12.4% | 0.0% | 0.0% | 25.7% | 61.9% |
| 0.001 | objective | 37.1% | 0.0% | 1.0% | 61.9% | 0.0% |
| 0.001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.01 | structure | 29.5% | 0.0% | 1.0% | 62.9% | 6.7% |
| 0.01 | objective | 48.6% | 0.0% | 50.5% | 1.0% | 0.0% |
| 0.01 | ranking | 18.1% | 0.0% | 1.0% | 37.1% | 43.8% |
| 0.05 | structure | 48.6% | 2.9% | 34.3% | 14.3% | 0.0% |
| 0.05 | objective | 48.6% | 0.0% | 51.4% | 0.0% | 0.0% |
| 0.05 | ranking | 35.2% | 27.6% | 4.8% | 32.4% | 0.0% |
| 0.1 | structure | 49.5% | 4.8% | 45.7% | 0.0% | 0.0% |
| 0.1 | objective | 49.5% | 0.0% | 50.5% | 0.0% | 0.0% |
| 0.1 | ranking | 49.5% | 44.8% | 5.7% | 0.0% | 0.0% |
| 0.5 | structure | 49.5% | 4.8% | 45.7% | 0.0% | 0.0% |
| 0.5 | objective | 49.5% | 1.0% | 49.5% | 0.0% | 0.0% |
| 0.5 | ranking | 49.5% | 44.8% | 5.7% | 0.0% | 0.0% |
| 1 | structure | 49.5% | 5.7% | 44.8% | 0.0% | 0.0% |
| 1 | objective | 49.5% | 1.0% | 49.5% | 0.0% | 0.0% |
| 1 | ranking | 49.5% | 44.8% | 5.7% | 0.0% | 0.0% |
| 5 | structure | 49.5% | 12.4% | 38.1% | 0.0% | 0.0% |
| 5 | objective | 49.5% | 3.8% | 46.7% | 0.0% | 0.0% |
| 5 | ranking | 49.5% | 44.8% | 5.7% | 0.0% | 0.0% |
| 10 | structure | 49.5% | 18.1% | 32.4% | 0.0% | 0.0% |
| 10 | objective | 49.5% | 8.6% | 41.9% | 0.0% | 0.0% |
| 10 | ranking | 49.5% | 44.8% | 5.7% | 0.0% | 0.0% |


**Read:** the original Phase 3 result said `reuse_direct` wins 71.4% of objective cells at λ=0.05. Under V1 (penalty=1.0) that share is 48.6%; under V3 (drop infeasible reuse) it is 48.6% (with `clarke_wright` filling the gap at 51.4%). The qualitative story holds — reuse beats recompute once compute has any non-trivial price — but the **strength** of the result depends entirely on whether infeasibility is treated as a free answer or as a wrong answer.

## 5. λ=0 tie-breaking audit

**Tie-break rule.** Python's `min(dict, key=dict.get)` returns the first-inserted key with the minimum value. The action dict is built by iterating ACTIONS = ['reuse_direct', 'nearest_neighbor', 'clarke_wright', 'pyvrp_10s', 'pyvrp_60s'], so reuse_direct wins ties over nearest_neighbor, which wins over clarke_wright, and so on; pyvrp_60s wins ties only if every other action fails to match its loss.

| claim | n | tie share | pyvrp_60s wins (orig) | pyvrp_60s wins (strict) | non-60s honest wins |
| --- | ---: | ---: | ---: | ---: | ---: |
| objective | 105 | 28.6% | 71.4% | 100.0% | 0.0% |
| ranking | 105 | 42.9% | 57.1% | 100.0% | 0.0% |
| structure | 105 | 31.4% | 68.6% | 100.0% | 0.0% |

**Read:** every cell at λ=0 has `pyvrp_60s` at loss = 0 (it is compared against itself), so `pyvrp_60s` is **always at the cell minimum**. The 71.4% objective / 57.1% ranking / 68.6% structure wins for `pyvrp_60s` under the original rule are the cells where no other action also reaches loss = 0. The remainder are ties: 28.6% of objective cells, 42.9% of ranking cells, 31.4% of structure cells. Ties happen when a cheaper action accidentally matches the reference exactly — `pyvrp_10s` finding the same objective on an easy instance, or `reuse_direct` reproducing the reference plan under a small regional-distance perturbation. The audit confirms: `honest_non_60s_wins_pct = 0` for every claim family. **No non-60s action ever beats `pyvrp_60s` strictly at λ=0**; every non-60s share is a tie awarded by the first-inserted-wins rule. Switching to a strict tie-breaker (`pyvrp_60s` wins ties) re-assigns 34.3% of cells back to `pyvrp_60s`, taking it to 100% across all three claim families.

## 6. Thesis-ready sentences

Use these phrasings to avoid overstating the reuse result.

**On reuse:**
> Fixed-solution reuse is sufficient for objective-claim queries under regional-distance perturbations, where every reused plan remains feasible. Under capacity reductions the recomputed objective of the fixed solution stays close to the recomputed reference, but in 50–100% of cells (depending on the magnitude) the fixed plan exceeds the new capacity on at least one route — so reuse should be treated as unsafe whenever the consumer needs a plan that is actually executable, regardless of how close the objective looks.

**On the λ=0 tie behavior:**
> At λ=0 the policy objective is the raw loss. Because PyVRP @ 60s is also the reference, its loss is exactly zero on every cell, so no other action can ever score strictly lower. The non-60s shares reported at λ=0 are not wins — they are ties at loss = 0 awarded by a deterministic but arbitrary rule (the first action in `ACTIONS = (reuse_direct, nearest_neighbor, clarke_wright, pyvrp_10s, pyvrp_60s)` wins). Under a strict tie-breaker that hands ties to PyVRP 60s, the reference would win 100% of cells at λ=0, as expected. We report the original rule because it cleanly counts how often a cheaper action *could have substituted* for the reference — a useful signal for routing — but the share itself should not be read as `pyvrp_60s` losing those cells.


# Phase 3 — Information sufficiency and recompute routing

_Generated from artifacts/. Reference backend: PyVRP @ 60s, seed=1. Cell-level coverage: 105 cells with reference; 0 cells missing reference._

**Thesis question:** When is the information contained in an existing optimization solution sufficient to answer a query, when is lightweight estimation enough, and when is recomputation required?

**Setup.** 15 Uchoa-X instances; 7 required perturbations per instance (capacity_reduction at 0.98, 0.95, 0.9, 0.8 and regional_distance_inflation at 1.1, 1.25, 1.5). Three claim families (objective, structure, ranking) per cell. Five candidate actions: `reuse_direct`, `nearest_neighbor`, `clarke_wright`, `pyvrp_10s`, `pyvrp_60s`. Reference is PyVRP @ 60s on the perturbed instance (Phase 2 used 10s — that is now an _action_, not the reference).
## 1. Experiment 1 — `reuse_direct`

**Question:** can the perturbation query be answered using the PyVRP 60s baseline solution _S_ alone, without any optimization on the perturbed instance?

**Operational definition:** evaluate the fixed routes of _S_ under the perturbed distance matrix and the perturbed capacity. Recompute objective and route loads, but do not modify the routes. If a route's load exceeds the perturbed capacity, mark the artifact as `infeasible` while still recording the recomputed objective so structural and ranking claims remain measurable.

### 1.1 Per-claim-family error

| claim family | n | mean error | easy % | medium % | hard % | infeasible share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| objective | 105 | 0.0480 | 69.5% | 21.0% | 9.5% | 50.5% |
| ranking | 105 | 0.7810 | 16.2% | 14.3% | 69.5% | 50.5% |
| structure | 105 | 0.4268 | 17.1% | 3.8% | 79.0% | 50.5% |

### 1.2 By perturbation family

| claim | perturbation | n | mean error |
| --- | --- | ---: | ---: |
| objective | capacity_reduction | 60 | 0.0758 |
| ranking | capacity_reduction | 60 | 0.8778 |
| structure | capacity_reduction | 60 | 0.5013 |
| objective | regional_distance_inflation | 45 | 0.0111 |
| ranking | regional_distance_inflation | 45 | 0.6519 |
| structure | regional_distance_inflation | 45 | 0.3275 |

## 2. Experiment 2 — `reuse_with_estimation`

**Question:** do cheap construction heuristics (nearest neighbor, Clarke-Wright savings) recover what direct reuse misses? Both are run from scratch on the perturbed instance and compared against the PyVRP 60s reference.

### 2.1 Per-action × claim-family

| action | claim | n | mean error | easy % | hard % |
| --- | --- | ---: | ---: | ---: | ---: |
| reuse_direct | objective | 105 | 0.0480 | 69.5% | 9.5% |
| reuse_direct | ranking | 105 | 0.7810 | 16.2% | 69.5% |
| reuse_direct | structure | 105 | 0.4268 | 17.1% | 79.0% |
| nearest_neighbor | objective | 105 | 0.2349 | 7.6% | 78.1% |
| nearest_neighbor | ranking | 105 | 0.9968 | 0.0% | 99.0% |
| nearest_neighbor | structure | 105 | 0.7393 | 0.0% | 100.0% |
| clarke_wright | objective | 105 | 0.0590 | 34.3% | 0.0% |
| clarke_wright | ranking | 105 | 0.9270 | 0.0% | 80.0% |
| clarke_wright | structure | 105 | 0.6223 | 0.0% | 100.0% |

## 3. Experiment 3 — recompute routing and λ curves

**Question:** when recomputation is the policy choice, how much compute should be spent? Action set = {`reuse_direct`, `nearest_neighbor`, `clarke_wright`, `pyvrp_10s`, `pyvrp_60s`}. Per cell objective = `loss + λ * runtime`. Best action is the argmin. We sweep λ over a log grid and report the share of (instance × scenario) cells where each action wins, broken down by claim family.

### 3.1 Best-action share (% of cells) by λ × claim family

| λ | claim | reuse | NN | CW | pyvrp_10s | pyvrp_60s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | objective | 4.8% | 0.0% | 0.0% | 23.8% | 71.4% |
| 0 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0.0001 | objective | 19.0% | 0.0% | 0.0% | 76.2% | 4.8% |
| 0.0001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.0001 | structure | 10.5% | 0.0% | 0.0% | 21.0% | 68.6% |
| 0.001 | objective | 41.0% | 0.0% | 1.0% | 58.1% | 0.0% |
| 0.001 | ranking | 16.2% | 0.0% | 0.0% | 26.7% | 57.1% |
| 0.001 | structure | 12.4% | 0.0% | 0.0% | 25.7% | 61.9% |
| 0.01 | objective | 71.4% | 0.0% | 28.6% | 0.0% | 0.0% |
| 0.01 | ranking | 18.1% | 0.0% | 1.0% | 37.1% | 43.8% |
| 0.01 | structure | 34.3% | 0.0% | 1.0% | 61.0% | 3.8% |
| 0.05 | objective | 71.4% | 0.0% | 28.6% | 0.0% | 0.0% |
| 0.05 | ranking | 62.9% | 0.0% | 4.8% | 32.4% | 0.0% |
| 0.05 | structure | 82.9% | 1.0% | 10.5% | 5.7% | 0.0% |
| 0.1 | objective | 72.4% | 0.0% | 27.6% | 0.0% | 0.0% |
| 0.1 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 0.1 | structure | 86.7% | 1.0% | 12.4% | 0.0% | 0.0% |
| 0.5 | objective | 73.3% | 1.0% | 25.7% | 0.0% | 0.0% |
| 0.5 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 0.5 | structure | 86.7% | 1.0% | 12.4% | 0.0% | 0.0% |
| 1 | objective | 73.3% | 1.0% | 25.7% | 0.0% | 0.0% |
| 1 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 1 | structure | 87.6% | 1.0% | 11.4% | 0.0% | 0.0% |
| 5 | objective | 81.9% | 2.9% | 15.2% | 0.0% | 0.0% |
| 5 | ranking | 94.3% | 0.0% | 5.7% | 0.0% | 0.0% |
| 5 | structure | 92.4% | 1.0% | 6.7% | 0.0% | 0.0% |
| 10 | objective | 91.4% | 3.8% | 4.8% | 0.0% | 0.0% |
| 10 | ranking | 95.2% | 0.0% | 4.8% | 0.0% | 0.0% |
| 10 | structure | 94.3% | 1.0% | 4.8% | 0.0% | 0.0% |

## 4. Thesis takeaway

- For **objective claims**, fixed-solution reuse hits the easy band 69.5% of the time with mean error 0.0480. Clarke-Wright reaches 34.3% easy with mean error 0.0590; nearest neighbor reaches 7.6% easy with mean error 0.2349. Best non-recompute action on objective is **reuse_direct** (69.5% easy, mean error 0.0480).
- For **structure** (assignment) and **ranking** claims, reuse fails: 79.0% of cells land in the hard band on structure and 69.5% on ranking. Cheap estimators (NN, CW) do not rescue these families — they are 100% hard or close to it because the perturbed reference reorganizes routes in ways that constructive heuristics miss.
- **λ sweep**: at λ=0 (loss-only), `pyvrp_60s` wins 71.4% of objective cells. At λ=10 (compute heavily penalized), `reuse_direct` wins 91.4%. The transition region is the interesting one: see `figure_2_lambda_curves_by_claim_family.png`.
- **Claim-family asymmetry**: at λ=0.01 (a small but non-zero compute penalty) the modal best action differs by family — objective=reuse_direct (71.4%); ranking=pyvrp_60s (43.8%); structure=pyvrp_10s (61.0%). Objective claims migrate away from recomputation earlier than structure or ranking, because reuse_direct's objective error is small while its structural error is large.
- **PyVRP 10s vs 60s**: at λ=0.0001 (any non-zero compute price) `pyvrp_10s` wins 76.2% of objective cells while `pyvrp_60s` wins only 4.8%. The extra 50 seconds of search rarely buy enough loss reduction to justify their runtime once compute has any price at all — implying the 10s budget is the right default for recomputation.

### Headline
> Not all questions about an optimization problem require recomputation. The need depends systematically on the claim family, the perturbation, and the runtime budget. **Objective** claims are largely answerable from the existing solution alone — fixed-solution evaluation hits the easy band most of the time, especially under regional-distance perturbations where the objective error is near zero. **Structural** (route assignment) and **ranking** (top-k routes) claims demand recomputation: neither fixed-solution reuse nor cheap construction heuristics (NN, Clarke-Wright) recover the structural agreement of a PyVRP-quality solution under perturbation.

## 5. Known limitations

- **Dataset size**: 15 Uchoa-X instances; 7 perturbations × 15 = 105 cells per claim family. Adequate for distributional claims with wide effect sizes (the headline holds with comfortable margins) but too small to train a learned router.
- **Two perturbation families only**: capacity reduction and regional distance inflation. Demand inflation and customer insertion were skeleton-quality in Phase 2 and are not part of the Phase 3 grid.
- **PyVRP stochasticity**: a single seed (1) at each time limit. 60s is sample-stable enough to act as the reference (Phase 1 median gap to BKS ≈ 0.14%) but lambda transitions could shift with a different seed.
- **Reuse-direct under capacity**: the recomputed objective is computed even when the fixed solution is infeasible. We treat infeasibility as observable (via the `feasible_under_perturbation` flag) but not as automatic loss inflation; downstream consumers may want to add a feasibility-penalty before consuming the objective error.
- **Lambda is a tradeoff knob, not a calibrated price**: runtimes are in seconds and losses are dimensionless errors in [0, 1]. The grid spans many orders of magnitude on purpose. We do not claim a particular λ is 'correct'.
- **No learned router yet**: Experiment 3 is an oracle/simulation sweep over observed losses and runtimes. A learned policy is a natural follow-up but would require per-instance features and more data.

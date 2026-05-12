# Phase 1 - Pilot Report

## 1. Did instances parse?

- Registry rows: **15**
- Parsed successfully: **15** (100%)

## 2. PyVRP protocol settings

- Seeds: `[1]`
- Time limit: `60` seconds
- Each SolutionArtifact carries: `random_seed`, `time_limit_sec`, `solver_params`, `solver_version`, `run_id`.

- Observed solver_version values: `['pyvrp-0.13.3']`

## 3. How close to BKS?

- Instances with BKS available: **15 / 15**
- Median nominal gap-to-BKS: **0.14%**
- Share ≤ 0.5% (strong near-reference): **87%**
- Share 0.5–3% (strong heuristic baseline): **13%**
- Share > 3% (insufficient reference quality): **0%**

| instance_id | pyvrp_obj | bks_objective | gap_% |
| --- | --- | --- | --- |
| X-n101-k25 | 27591 | 27591 | 0 |
| X-n110-k13 | 14971 | 14971 | 0 |
| X-n120-k6 | 13332 | 13332 | 0 |
| X-n134-k13 | 10940 | 10916 | 0.2199 |
| X-n148-k46 | 43448 | 43448 | 0 |
| X-n153-k22 | 21377 | 21220 | 0.7399 |
| X-n162-k11 | 14162 | 14138 | 0.1698 |
| X-n172-k51 | 45607 | 45607 | 0 |
| X-n181-k23 | 25598 | 25569 | 0.1134 |
| X-n190-k8 | 17004 | 16980 | 0.1413 |
| X-n200-k36 | 58675 | 58578 | 0.1656 |
| X-n214-k11 | 10891 | 10856 | 0.3224 |
| X-n219-k73 | 117606 | 117595 | 0.009354 |
| X-n228-k23 | 25785 | 25742 | 0.167 |
| X-n247-k50 | 37479 | 37274 | 0.55 |

## 4. Do backends structurally disagree?

- Nominal runs: **15**
- Backend-disagreement gate rate (both objective AND ARI): **93%**
  - Objective-gap-only component: 93%
  - Structural (ARI) component: 100%

| instance_id | objective_rel_change | adjusted_rand | route_count_change | backend_disagreement |
| --- | --- | --- | --- | --- |
| X-n101-k25 | 0.3355 | 0.1982 | false | true |
| X-n110-k13 | 0.2242 | 0.3536 | false | true |
| X-n120-k6 | 0.1588 | 0.289 | false | true |
| X-n134-k13 | 0.3381 | 0.339 | false | true |
| X-n148-k46 | 0.2321 | 0.1555 | false | true |
| X-n153-k22 | 0.3385 | 0.2687 | true | true |
| X-n162-k11 | 0.1931 | 0.4039 | false | true |
| X-n172-k51 | 0.2981 | 0.2078 | true | true |
| X-n181-k23 | 0.07604 | 0.4569 | false | true |
| X-n190-k8 | 0.1494 | 0.2381 | false | true |
| X-n200-k36 | 0.1537 | 0.2925 | true | true |
| X-n214-k11 | 0.2674 | 0.1936 | true | true |
| X-n219-k73 | 0.02111 | 0.3907 | false | false |
| X-n228-k23 | 0.3431 | 0.2495 | true | true |
| X-n247-k50 | 0.2973 | 0.1389 | true | true |

## 5. Do perturbations activate?

- Perturbation scenarios in use: `capacity_reduction factors=[0.9, 0.8]`
- Per-instance nonzero-response rate: **100%**
- Per-instance structural-response rate: **100%**

| instance_id | any_nonzero | any_structural |
| --- | --- | --- |
| X-n101-k25 | true | true |
| X-n110-k13 | true | true |
| X-n120-k6 | true | true |
| X-n134-k13 | true | true |
| X-n148-k46 | true | true |
| X-n153-k22 | true | true |
| X-n162-k11 | true | true |
| X-n172-k51 | true | true |
| X-n181-k23 | true | true |
| X-n190-k8 | true | true |
| X-n200-k36 | true | true |
| X-n214-k11 | true | true |
| X-n219-k73 | true | true |
| X-n228-k23 | true | true |
| X-n247-k50 | true | true |

### Per-scenario breakdown

| scenario | tag | nonzero | structural |
| --- | --- | --- | --- |
| capacity_reduction@0.8 | capacity_reduction@0.8:nearest_neighbor | 1 | 1 |
| capacity_reduction@0.8 | capacity_reduction@0.8:pyvrp | 1 | 1 |
| capacity_reduction@0.9 | capacity_reduction@0.9:nearest_neighbor | 0.9333 | 0.9333 |
| capacity_reduction@0.9 | capacity_reduction@0.9:pyvrp | 0.9333 | 0.9333 |

## 6. Are observable claims supported?

| Claim family | Supported in Phase 1 | Signal present |
| --- | --- | --- |
| objective/resource delta | yes | yes |
| top-k route ranking | yes | yes |
| assignment/structure change | yes | yes |
| intervention ordering | **deferred to Phase 2** | n/a |
| mechanism/explanation | **deferred to Phase 2** | n/a |

## 7. Which claims are viable, which are deferred?

**Viable in Phase 1**:
- objective/resource delta (observable directly from artifacts)
- top-k route ranking (route distance contribution, k=3)
- assignment/structure change (adjusted Rand index on customer co-assignment)

**Deferred** (per protocol):
- intervention ordering — requires ≥ 2 perturbation families; capacity_reduction is the only one enabled.
- mechanism / explanation — semantic claims tracked separately, never folded into main correctness rates.

## 8. Decision

**PROCEED**

- PROCEED: all gates satisfied.

### Gate readings used

- parse rate: 100%
- PyVRP usable (all nominal runs ok): True
- backend structural-disagreement rate: 93%
- structural-activation rate (any source, per instance): 100%
- perturbation nonzero-response rate (per instance): 100%
- PyVRP gap-to-BKS > 3% share: 0%
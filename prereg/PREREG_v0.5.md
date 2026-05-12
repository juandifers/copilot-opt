# Pre-Registration: VRP Copilot Sufficiency Benchmark

**Status:** DRAFT v0.5 — to be locked at v1.0 before any Stage A data collection.
**Author:** Juan
**Date drafted:** 2026-05-11 (v0.5 supersedes v0.4)
**Date locked:** TBD (commit hash + timestamp inserted at lock time)
**Locking procedure:** see Section 16.

---

## 1. Purpose

This document fixes every methodological choice that governs the VRP Copilot Sufficiency Benchmark — claim definitions, sufficiency labels, perturbation grids, action set, reference protocol, error metrics, threshold values, cross-validation procedure, baseline policies, headline metrics, and pass/fail criteria. Once locked, no element in Sections 3–14 may change without a versioned amendment that documents the change, the reason, and the data state at the time of the change.

The pre-registration exists for one reason. Threshold drift, post-hoc grid tuning, and outcome-targeted magnitude selection are the three failure modes that destroy benchmarks of this kind. Locking these choices before observing expanded data closes all three doors at once.

v0.2 integrates two rounds of revision against v0.1: external reviewer feedback identifying conceptual issues with the original feasibility framing and the ranking metric, and a data-grounding analysis on the existing 105-cell Phase 3 dataset that invalidated the slack-relative perturbation anchoring proposed in v0.1. v0.3 corrects the eligible-pool count in §5.1 against the empirical Uchoa-X size distribution and clarifies the audit sampling layer in §8.2; both changes are mechanical, no construct or threshold moves. v0.5 expands the Stage A roster from 65 to 68 — the full eligible pool — absorbing the §12.2 fold-replacement buffer into the main roster and routing instance-level failures through the §12.5 deterministic revision procedure instead. The change log in Section 19 itemizes every revision.

## 2. Scope and intentional limits

The benchmark covers the Capacitated Vehicle Routing Problem (CVRP) on the Uchoa-X instance set. It does not cover VRPTW, pickup-and-delivery, heterogeneous fleets, or the XL benchmark. Each of those is a defensible extension, and each is excluded here so the benchmark's claim — that information sufficiency is claim-conditional — can be tested on a single problem variant under controlled perturbations.

Stage A targets 68 Uchoa-X instances (v0.5, see §5.1 amendment). Stage B, gated on Stage A's verification step, expands to up to 78 instances. No further expansion is part of this pre-registration.

The benchmark is constructed under the abstraction that natural-language queries map to claim families. A separate LLM-in-the-loop closing experiment (Section 14.3) tests that abstraction on actual prompts. Open-ended dialogue, multi-turn clarification, and full natural-language understanding are out of scope.

### 2.1 Defense of CVRP-only scope

The choice of CVRP is methodological, not aspirational. CVRP isolates the conceptual claim — that information sufficiency in a copilot's answer depends on what query is being asked — by removing variables that would entangle the result with auxiliary feasibility geometry. VRPTW operational validity is a composite of capacity, time-window violations, route duration, depot return, and waiting time, each of which can be partially violated in ways capacity alone cannot. The clean decoupling between numerical closeness and feasibility that Phase 3 already established in CVRP would, under VRPTW, become entangled with a research question about how to define infeasibility itself.

Future work paragraph for the thesis discussion: the framework is specified at the level of constructs that admit natural VRPTW analogues — the operational validity axis generalizes to multi-constraint feasibility, perturbation families generalize to time-window perturbations, claim families remain unchanged. Empirical validation under VRPTW is a separate exercise and is not claimed in this thesis.

## 3. Construct definitions

### 3.1 Three-axis decomposition of copilot answer quality

Every answer the copilot produces is evaluated along three independent axes. The decomposition is the conceptual centerpiece of the thesis and is locked here.

- **Faithfulness.** Does the copilot's natural-language answer accurately report the underlying action's output? Faithfulness is between the language layer and the action layer. For benchmark cells where outputs are programmatic, faithfulness is true by construction. The closing experiment in Section 14.3 measures it directly on LLM-generated answers.

- **Sufficiency.** Is the action's output close enough to the reference for the relevant claim family? Sufficiency is between the action layer and the reference. It is the central object of this benchmark and is measured by claim-family-specific loss against PyVRP 60s seed=1.

- **Operational validity.** Is the action's output an executable plan under the perturbed instance? Operational validity is between the action layer and the real-world constraint set. It is measured by feasibility flags computed deterministically from the action's route plan.

The benchmark documents that these three axes can decouple. An action can be faithful and sufficient yet operationally invalid (the capacity-reduction artifact already observed in Phase 3). It can be operationally valid and faithful yet insufficient (an old plan that remains feasible but misses a much better recomputed structure). The decomposition exists to make these decouplings visible.

Operational validity is an axis attached to *every action on every cell*, not a claim family. Whether an action's plan satisfies the perturbed-instance constraints is a property of the action, not of the query. v0.1 conflated this axis with a claim family called FEAS; v0.2 splits the conflation: operational validity remains an axis (Section 9.5), and the user-facing query "is the existing plan still valid?" becomes its own claim family, PLAN_VALIDITY (Section 3.2).

### 3.2 Claim families

Four claim families are defined.

- **Objective (OBJ).** Claims about the numerical objective value of a routing plan under the perturbed instance. Canonical natural-language form: "What is the new total cost?" / "How much does cost change?"

- **Plan validity (PLAN_VALIDITY).** Claims about whether the existing baseline solution S is executable under the perturbed instance. Canonical form: "Can we keep using this plan?" / "Is the existing plan still valid?" The reference answer is the deterministic feasibility check on S under the perturbed constraints; no solver is needed to compute it.

- **Structure (STRUCT).** Claims about the customer-to-route assignment under the perturbed instance. Canonical form: "Which customers move?" / "Are the same customers still served together?"

- **Ranking (RANK).** Claims about which baseline routes are most affected by the perturbation, in ordinal terms. Canonical form: "Which of our current routes is most exposed to this disruption?" The query is grounded in baseline route identities (which are stable across actions) rather than in arbitrary action-side route IDs (which are not). See Section 9.4 for the metric.

The fifth family of "metareasoning / action recommendation" considered in earlier drafts is excluded as a category error: it describes the policy itself, not a claim about the artifact, and would create circular evaluation.

Every benchmark cell carries exactly one claim family.

### 3.3 Sufficiency labels

Three sufficiency labels are defined per cell. The benchmark stores all three; the predictor (Section 13) trains on operational_sufficiency restricted to OBJ, STRUCT, and RANK claim families.

**Numerical sufficiency** is `band[reuse_direct, claim_family] == 'easy'`. The fixed solution evaluated under the perturbation is numerically close to the reference for this claim family. This label is diagnostic only and is not the primary predictor target. Numerical closeness without operational validity is the failure mode the benchmark exists to expose.

**Operational sufficiency** is claim-dependent. The general principle: the artifact under evaluation is operationally sufficient for a claim iff it supports that claim without violating the validity requirements of that claim. Concretely:

- **OBJ:** `numerical_sufficiency AND feasibility_flag[reuse_direct, cell] == TRUE`. An objective answer that reports a cost number is only operationally honest if the underlying plan is executable. Numerical closeness with infeasibility is exactly the failure case the benchmark exposes; an answer that's "close" to the right cost on an unflyable plan is wrong, not approximately right.

- **PLAN_VALIDITY:** `TRUE` for `reuse_direct` by construction. Reuse_direct's pipeline includes the deterministic feasibility check on S under the perturbation, which is the reference computation. PLAN_VALIDITY is a *positive control* claim family: it represents the case where the existing solution artifact is trivially sufficient by construction. PLAN_VALIDITY cells are excluded from §12.1 verification range checks and from predictor training; they appear in descriptive analyses (H2) and in the LLM closing experiment.

- **STRUCT:** `band[reuse_direct, STRUCT] == 'easy'`. Operational validity does not apply: a structural claim ("which customers move?") is answerable regardless of whether the underlying plan is feasible.

- **RANK:** `band[reuse_direct, RANK] == 'easy'`. Same reasoning as STRUCT.

**Structural sufficiency** is `band[reuse_direct, STRUCT] == 'easy' AND band[reuse_direct, RANK] == 'easy'`, computed cell-wise. It captures whether the fixed solution preserves the route organization of the reference. Used as a secondary predictor target and in descriptive analyses; not a primary headline metric.

This claim-dependent definition is the v0.1 → v0.2 fix that the reviewer's feedback identified as the most important conceptual change in the document.

## 4. Benchmark schema

Each row of the benchmark is a *cell-action*. A cell is the unit at which loss, runtime, and labels are computed; a cell-action is one (cell, action) pair.

Cell key: `(instance_id, perturbation_id, claim_family)`. Cell-action key: cell key + `action`.

For Stage A: 68 instances × 16 perturbations × 4 claim families = 4,352 cells. Stored as 21,760 cell-action rows (5 actions per cell), with PLAN_VALIDITY cell-actions for non-`reuse_direct` actions populated with `loss_plan_validity = NaN`. (v0.5 update; see §5.1.)

### 4.1 Per-row fields

Stored in a single Parquet table, schema locked here.

```
instance_id            : str    # Uchoa-X instance identifier
perturbation_family    : str    # one of {CAPACITY, DISTANCE, DEMAND, INSERTION}
perturbation_id        : str    # globally unique id within (instance, family)
perturbation_magnitude : float  # in family-specific units (see §6)
claim_family           : str    # one of {OBJ, PLAN_VALIDITY, STRUCT, RANK}
action                 : str    # one of {reuse_direct, nearest_neighbor,
                                #          clarke_wright, pyvrp_10s, pyvrp_60s}
action_objective       : float  # objective of action's plan under perturbed instance
action_feasible        : bool   # action's plan satisfies perturbed capacity (operational validity)
action_n_overload      : int    # number of routes exceeding capacity
action_max_overload    : float  # max overload as fraction of capacity
action_runtime_s       : float  # wall-clock seconds (single-thread)
action_assignment      : json   # customer -> route_id map for action's plan
action_route_costs     : json   # route_id -> cost map under perturbed instance
reference_objective    : float  # PyVRP 60s seed=1 objective on perturbed instance
reference_feasible     : bool   # always True by construction
reference_assignment   : json
reference_route_costs  : json
reference_runtime_s    : float
baseline_solution_feasible_under_perturbation : bool  # deterministic check; PLAN_VALIDITY ground truth
loss_obj               : float  # |action_obj - ref_obj| / ref_obj
loss_plan_validity     : float  # 0 or 1; NaN for non-reuse_direct rows on PLAN_VALIDITY cells
loss_struct            : float  # 1 - ARI(action_assignment, reference_assignment)
loss_rank              : float  # baseline-group ranking loss; see §9.4
band_obj               : str    # one of {easy, medium, hard}
band_plan_validity     : str    # one of {easy, hard}
band_struct            : str    # one of {easy, medium, hard}
band_rank              : str    # one of {easy, medium, hard}
audit_seed_2_obj       : float  # null unless cell is in 20% audit subset
audit_seed_3_obj       : float  # null unless cell is in 20% audit subset
audit_seed_2_assignment: json   # null unless in audit subset
audit_seed_3_assignment: json
audit_seed_2_top3      : json   # ranking output at seed 2; null unless in audit
audit_seed_3_top3      : json
reference_obj_unstable    : bool   # see §8.2
reference_struct_unstable : bool   # NEW in v0.2: ARI stability across seeds
reference_rank_unstable   : bool   # NEW in v0.2: top-3 stability across seeds
```

Storage: one Parquet file per stage (`stage_a.parquet`, `stage_b.parquet`).
Schema migrations require a version bump and explicit migration script.

## 5. Instance set

### 5.1 Stage A: 68 instances

The 68 Uchoa-X instances used for Stage A are listed in `instances/stage_a_instances.txt`, committed alongside this document. Selection criteria, applied in order:

1. All 100 Uchoa-X CVRP instances are eligible.
2. Instances with fewer than 50 customers are excluded (insufficient route count for meaningful structure/ranking metrics). Uchoa-X starts at 100 customers, so this criterion is non-binding.
3. Instances with more than 500 customers are excluded for Stage A only (PyVRP 60s reference quality degrades at this scale; revisited for Stage B). The empirical Uchoa-X size distribution at this threshold yields **68 eligible instances**, not the ~90 estimated in the v0.1 draft. The methodological rationale of the >500 threshold is preserved; only the count is corrected.
4. Stage A absorbs the full eligible pool of 68 instances. The selection script `scripts/select_instances.py` is invoked with `--target 68`; when target equals the pool size, the stratified-sampling step is a no-op (the Hamilton allocator returns each stratum's pool size unchanged) and the script writes the sorted list of all 68 eligible IDs. The classification table (`data/instances/uchoa_x_classification.csv`) is transcribed from Tables 11–13 of Uchoa et al. 2017 and committed alongside this document; `scripts/verify_classification.py` re-derives the avg-route-size quintile boundaries empirically and asserts label consistency. The RNG seed (`20260429`) is retained for backward compatibility and for any future v0.x amendment that re-introduces a strict sampling step.

**Headline counts (v0.5):** 68 instances × 16 perturbations × 4 claim families = **4,352 evaluation cells**; 1,088 (instance, perturbation) pairs; **5,872 total Stage A keys** (5,440 base + 432 audit; see §8.2). Stage A row count: 21,760 cell-action rows.

**v0.5 amendment note:** Target raised from 65 to 68 (the full eligible pool). Reason: the v0.3/v0.4 design reserved 3 instances of the eligible pool as a §12.2 fold-replacement buffer; the chance that any fold needs replacement is low (the verification check requires both a positive and a negative example for ≥ 2 of 3 claim families on a per-instance basis, which is structurally generic), so reserving the buffer trades a known +5% increase in roster size for a low-probability fallback. v0.5 absorbs the buffer into the main roster and routes any instance-level verification failure through §12.5's deterministic revision procedure instead. The §12.5 procedure already includes an instance-replacement clause for §12.2 failure cases; under v0.5 that clause draws from the broader Uchoa-X pool with the documented selection rules rather than from a pre-reserved buffer.

### 5.2 Stage B: up to 78 instances

If Stage A passes verification (Section 12), Stage B includes the 68 Stage A instances plus up to 10 additional instances from the >500-customer pool, evaluated under a *scaled reference protocol*: PyVRP 120s instead of 60s, multi-seed audit at seeds 1/2/3 on 100% of these large-instance cells (rather than the 20% audit applied to the standard pool).

The 50–500-customer pool is exhausted at Stage A (the full 68 eligible are selected), so Stage B adds zero instances from the small pool; the entire Stage B expansion comes from the >500 pool under the scaled reference protocol, at the option of the user. If fewer than 10 additional instances are added (e.g., compute budget constrained, or the user opts not to evaluate the scaled-reference cells), Stage B's instance count is reduced accordingly and reported as such. The headline number of 78 is a ceiling, not a guarantee. Headline cell count for Stage B at the ceiling: 4,992 cells (78 × 16 × 4).

Instances added at Stage B are flagged in the data so Stage A and Stage B results can be compared on the common 68.

**v0.5 amendment note:** Stage B target unchanged at 78 (= 68 Stage A + up to 10 large). The composition of the +10 changes: under v0.3/v0.4 the +13 consisted of 3 small (drawn from the §12.2 buffer) + 10 large; under v0.5 the +10 is entirely from the >500 pool because Stage A now consumes all 68 small-pool instances. The scaled-reference protocol for the +10 large instances is unchanged.

## 6. Perturbation grids

Sixteen perturbations per instance, organized into four families of four perturbations each. The magnitude formulation is locked here.

The data-grounding analysis on the Phase 3 dataset (`prereg/data_grounding_report.md`) showed that PyVRP packs at least one route to capacity on all 15 evaluated instances, making `min_slack_ratio` degenerate as a perturbation anchor. The v0.1 slack-relative magnitude design (CAP_1 through CAP_4 anchored to `min_slack_ratio`) is therefore replaced in v0.2 by direct fractional formulations that produce a verified spread of outcomes on Phase 3 data.

The perturbation design's goal — variation that does not collapse to a small number of trivial rules — is preserved via two mechanisms: (a) magnitudes that span a wide enough range to produce easy/medium/hard cases per family, and (b) structural variation across perturbations within a family (e.g., DISTANCE varies by *which* region is affected, not just by magnitude). Instance-level variation under a given fixed magnitude comes from differences in route count, route load distribution, customer geometry, and number of near-full routes — all of which the predictor's feature set captures.

The baseline solution S (PyVRP 60s seed=1 on the unperturbed instance) is computed once per instance and used in all perturbations.

### 6.1 Family CAPACITY: capacity reduction (4 perturbations)

The new vehicle capacity is:

```
new_capacity = vehicle_capacity × (1 − ρ)
```

| ID    | ρ    | intended structural meaning                          |
|-------|------|------------------------------------------------------|
| CAP_1 | 0.02 | mild: rare baseline overload                         |
| CAP_2 | 0.05 | moderate: many baselines borderline                  |
| CAP_3 | 0.10 | tight: most baselines infeasible                     |
| CAP_4 | 0.20 | severe: all baselines infeasible                     |

These ρ values are validated by Phase 3 data: at the same magnitudes, Phase 3 produced infeasibility rates of 73%, 87%, 93%, 100%, which is the dose-response curve the slack-anchored design was attempting to produce.

### 6.2 Family DISTANCE: regional distance inflation (4 perturbations)

Distances between depot and customers in a designated region are multiplied by 2.0. Customer-to-customer distances within the region are also multiplied by 2.0. The four perturbations differ in which region is selected, not in the multiplier.

The multiplier is raised from v0.1's 1.25 to 2.0 because the Phase 3 data showed `P(operational_sufficiency = 1 | OBJ × DIST) = 0.98` at the 1.25 magnitude — the block trivially fails verification's lower-band check at the upper edge. The 2.0 value is selected to produce non-degenerate label distributions across all three relevant claim families (OBJ, STRUCT, RANK). Appendix A specifies escalation rules if the 2.0 multiplier still produces a degenerate distribution.

Region selection rules, applied to the customer set deterministically:

| ID     | region rule                                                                |
|--------|----------------------------------------------------------------------------|
| DIST_1 | 1/4 of customers farthest from depot, low local density (k-NN spread > median) |
| DIST_2 | 1/4 of customers farthest from depot, high local density (k-NN spread ≤ median) |
| DIST_3 | 1/4 of customers closest to depot                                           |
| DIST_4 | All customers belonging to the highest-cost route in S                      |

### 6.3 Family DEMAND: local demand inflation (4 perturbations)

A subset of customers receives inflated demand:

```
inflated_subset_demand = subset_baseline_demand × (1 + δ)
```

The subset is selected deterministically from baseline routes; δ scales the inflation magnitude.

| ID     | subset                                  | δ    |
|--------|-----------------------------------------|------|
| DEM_1  | smallest baseline-route customer cluster | 0.10 |
| DEM_2  | smallest baseline-route customer cluster | 0.50 |
| DEM_3  | median-cost baseline route               | 0.50 |
| DEM_4  | highest-cost baseline route              | 1.00 |

Per-customer inflation is uniform within the subset; the subset itself is the customer set of the named baseline route.

### 6.4 Family INSERTION: customer insertion (4 perturbations)

New customers are added with deterministically generated coordinates and demands. Total inserted demand is anchored to vehicle capacity:

```
total_inserted_demand = γ × vehicle_capacity
```

| ID    | n new customers | spatial pattern                                       | γ    |
|-------|-----------------|-------------------------------------------------------|------|
| INS_1 | 1               | uniformly within 1 std-dev of depot                    | 0.30 |
| INS_2 | 3               | tight cluster, centroid near busiest baseline route   | 0.70 |
| INS_3 | 5               | scattered uniformly across the convex hull            | 1.20 |
| INS_4 | 10              | tight cluster, centroid in low-density region         | 2.00 |

Per-customer demand within an insertion is `total_inserted_demand / n_new_customers`. Insertion locations use stable hashing for reproducibility:

```python
import hashlib
seed_int = int(hashlib.sha256(f"{instance_id}_{perturbation_id}".encode()).hexdigest()[:16], 16) % (2**32)
rng = numpy.random.default_rng(seed_int)
```

This replaces v0.1's `numpy.random.default_rng(hash(instance_id))`, which was non-deterministic across Python sessions because `hash()` is randomized when `PYTHONHASHSEED` is unset. The seed input was further amended in v0.4 from per-instance to per-(instance, perturbation_id) so that INS_1, INS_2, INS_3, INS_4 on the same instance draw distinct RNG state — the v0.3 per-instance seeding caused the first n_new samples of each insertion to overlap, defeating the structural variation the four INS variants are designed to produce.

### 6.5 Total per instance

4 + 4 + 4 + 4 = 16 perturbations per instance. Across 68 instances (v0.5): 1,088 perturbed instances. Across 4 claim families: 4,352 evaluation cells. Across 5 actions: 21,760 cell-action rows.

## 7. Action set

Five actions are evaluated per cell. The action set is locked.

- **`reuse_direct`.** No solving. Take the baseline solution S, computed once per instance before any perturbation. Re-evaluate its objective under the perturbed distance and demand matrices. Re-check feasibility under perturbed capacity. Output: original routes, recomputed objective, recomputed per-route cost, feasibility flag, and (for PLAN_VALIDITY) the deterministic feasibility verdict on S.

- **`nearest_neighbor`.** Run nearest-neighbor route construction on the perturbed instance from scratch. Reference implementation: `scripts/heuristics/nearest_neighbor.py`, locked at commit hash inserted at lock time.

- **`clarke_wright`.** Run Clarke-Wright savings algorithm on the perturbed instance from scratch. Reference implementation: `scripts/heuristics/clarke_wright.py`.

- **`pyvrp_10s`.** Run PyVRP with a 10-second time limit, seed=1, on the perturbed instance.

- **`pyvrp_60s`.** Run PyVRP with a 60-second time limit, seed=1, on the perturbed instance. This action's output is the reference; the cell's reference fields are populated from this run.

PyVRP version is locked at the version recorded in `requirements.txt` at lock time. Bug-fix patches are permitted within a major version. Any major-version bump invalidates the benchmark and requires rebuilding from scratch.

## 8. Reference protocol

### 8.1 Primary reference

PyVRP 60s with seed=1 on the perturbed instance. The reference is computed on every one of the 4,352 evaluation cells. Because `pyvrp_60s` is also a benchmarked action, the reference solve and the action solve are the same computation.

### 8.2 Multi-seed audit

A 20% subset of `(instance, perturbation)` **pairs**, drawn deterministically via stratified sampling across the four perturbation families (RNG seed `20260429`), receives two additional reference runs at seeds 2 and 3. The audit is layered at the pair level — not the cell level — because a PyVRP reference solve produces all four claim-family outputs (objective, plan-validity, structure, ranking) simultaneously from a single solution; sampling pairs and propagating audit data to all four cells of each sampled pair is the natural unit of computation.

**Pair counts (v0.5):** With 68 instances × 16 perturbations = 1,088 pairs, the 20% audit fraction (applied per stratum with `round()`-style rounding) selects **216 pairs** (4 perturbation families × 54 pairs each: `round(272 × 0.20) = 54`). Each audited pair contributes audit data to all 4 of its cells, yielding 864 audited cells. The 2 extra audit reference runs per pair (seeds 2 and 3) materialize as **432 audit keys** in the runner's work plan (216 pairs × 2 audit actions: `pyvrp_60s_seed2` and `pyvrp_60s_seed3`).

For each audited cell, three stability checks are computed:

```
reference_obj_unstable    = (max_obj - min_obj) / min_obj > 0.02
reference_struct_unstable = min over (i,j) of ARI(seed_i_assignment, seed_j_assignment) < 0.90
reference_rank_unstable   = min over (i,j) of top3_jaccard(seed_i_top3, seed_j_top3) < 0.50
```

The objective check matches v0.1. The structure and ranking checks are added in v0.2 because two PyVRP seeds can produce nearly identical objectives with substantially different assignments, and STRUCT/RANK labels are sensitive to which assignment wins. Without these checks, the benchmark could carry seed-noise artifacts on the two claim families most exposed to assignment variance.

If the unstable-cell rate in the audit subset exceeds 5% on any of the three checks, the affected cells are re-collected with the scaled reference protocol from §5.2 (PyVRP 120s, seeds 1/2/3, full audit). This is the only condition under which the reference protocol may be amended without a full lock-version bump.

## 9. Loss metrics and bands

Every cell-action has a loss value for each of the four claim families, regardless of which family the cell is "tagged" for. The cell's primary claim family controls its sufficiency labels; storing all four allows aggregate analyses across claim families on the same data.

Bands are determined by thresholds applied to losses. Thresholds are locked here.

### 9.1 Objective loss

```
loss_obj = |action_objective - reference_objective| / reference_objective
```

Bands:
- `easy`: `loss_obj ≤ 0.05`
- `medium`: `0.05 < loss_obj ≤ 0.15`
- `hard`: `loss_obj > 0.15`

The 5%/15% cutoffs match Phase 3 and reflect operational tolerances reported in commercial routing tools. The thresholds are locked; they cannot be revisited in response to observed Stage A label distributions.

### 9.2 Plan-validity loss

For PLAN_VALIDITY cells with `action = reuse_direct`:

```
loss_plan_validity = 0 if reuse_reports_correct_feasibility_verdict_for_S else 1
```

Reuse_direct reports the correct verdict by construction (its pipeline runs the deterministic feasibility check on S). `loss_plan_validity` is therefore 0 for all such rows, and the band is always `easy`. PLAN_VALIDITY × non-reuse rows have `loss_plan_validity = NaN` and are excluded from PLAN_VALIDITY analyses.

Bands:
- `easy`: `loss_plan_validity == 0`
- `hard`: `loss_plan_validity == 1`

### 9.3 Structure loss

```
loss_struct = 1 - ARI(action_assignment, reference_assignment)
```

ARI is computed treating each customer as a data point and its assigned route as its cluster label. ARI handles the route-id permutation problem natively.

Bands:
- `easy`: `loss_struct ≤ 0.10` (ARI ≥ 0.90)
- `medium`: `0.10 < loss_struct ≤ 0.30` (ARI ∈ [0.70, 0.90))
- `hard`: `loss_struct > 0.30` (ARI < 0.70)

### 9.4 Ranking loss (baseline-group framing)

The ranking metric in v0.1 ranked routes by cost change, but PyVRP's route IDs are arbitrary across solutions, making "top 3 routes" ill-defined when comparing actions to references. v0.2 grounds ranking in the *baseline route partitioning* of customers, which is identity-stable across all actions.

Procedure:

1. From the baseline solution S, partition customers into n baseline groups, where group $g_i$ is the customer set of baseline route $r_i$.
2. For each action's plan and the reference plan, compute the "impact" on each baseline group as:

```
impact(g_i, plan) = sum over c in g_i of cost_contribution(c, plan, perturbed_instance)
                  - sum over c in g_i of cost_contribution(c, S, unperturbed_instance)
```

where `cost_contribution(c, plan, instance)` is the marginal cost attributable to customer c in the plan under the instance.

3. Rank baseline groups by impact. The action's top-k is `top3(impact under action's plan)`; the reference's top-k is `top3(impact under reference's plan)`.

```
top3_jaccard = |action_top3 ∩ reference_top3| / |action_top3 ∪ reference_top3|
loss_rank = 1 - top3_jaccard
```

Bands:
- `easy`: `loss_rank ≤ 0.50` (at least 2 of 3 baseline groups match)
- `medium`: `0.50 < loss_rank ≤ 0.80`
- `hard`: `loss_rank > 0.80`

For instances with fewer than 3 baseline routes, top-k is reduced to top-min(3, n_routes_baseline) and Jaccard is computed accordingly. The cell is flagged in `n_routes_baseline < 3` for diagnostic exclusion if needed.

This formulation answers the operationally meaningful query — "which of the existing groupings face the biggest disruption?" — and avoids the route-identity ambiguity that affected v0.1. The cost of the choice is that the metric does not capture rankings of *new* routes produced by the action; that variant is acknowledged as a future extension.

### 9.5 Operational validity flag

The per-action operational validity flag is `feasibility_flag[action] = action_feasible`, computed independently of loss bands by checking whether the action's output plan satisfies the perturbed-instance constraints (capacity primarily; demand assignment by construction). It enters operational sufficiency for OBJ (per Section 3.3) and is reported as a standalone diagnostic on STRUCT and RANK cells.

## 10. Cross-validation protocol

### 10.1 Primary CV: leave-one-instance-out (LOIO)

For each of the 68 instances, train on the cells of the other 67 and evaluate on the held-out instance. All 68 folds are computed; metrics are reported as the mean across folds with bootstrap 95% confidence intervals over the 68 fold-level estimates.

No row-level random splitting. Random splits would leak instance-level structure into the test set and inflate predictor performance. LOIO is the only valid split for this benchmark and is locked.

PLAN_VALIDITY cells are excluded from training (label = 1 by construction); LOIO is computed on the 3,264 cells with claim_family ∈ {OBJ, STRUCT, RANK} (68 instances × 16 perturbations × 3 claim families).

### 10.2 Secondary stress test: leave-one-perturbation-family-out (LOPO)

For each of the 4 perturbation families, train on cells from the other 3 and evaluate on the held-out family. This 4-fold split tests whether the predictor generalizes across perturbation types or only within them.

LOPO is reported as a sensitivity analysis. The headline numbers are LOIO.

### 10.3 No model selection on test data

Hyperparameters for the predictor (Section 13) are tuned on Stage A training folds via nested CV, never on test folds. The hyperparameter grid for each model class is locked in Section 13.

## 11. Baseline policies

The learned predictor must beat these baselines. Baselines are evaluated under the same LOIO protocol.

- **B0_random.** Predict operational sufficiency uniformly at random.

- **B1_majority_class.** Predict the modal label across all training cells (constant prediction).

- **B2_claim_family_only.** Rule depending only on claim family. Predict sufficient for OBJ; not sufficient for STRUCT and RANK. Tests how much signal lives in claim family alone.

- **B3_feasibility_gate.** B2 plus an additional rule: if the baseline solution S is infeasible under the perturbed capacity, predict not sufficient regardless of claim family. Tests the marginal value of the cheapest pre-recompute feasibility check.

- **B4_rule_policy.** Hand-written if-then rules with no fitting. Specifically:

```
if claim_family == OBJ and reuse_feasible and reuse_objective_delta_pct < 0.05:
    predict sufficient
elif claim_family == OBJ and not reuse_feasible:
    predict not sufficient
elif claim_family in {STRUCT, RANK} and perturbation_family == DISTANCE and perturbation_magnitude < 1.5:
    predict sufficient
else:
    predict not sufficient
```

The rules are locked at this version and frozen before any predictor training. They represent what an analyst would write after reading the Phase 3 results, with no model fitting.

- **B5_shallow_tree.** A learned decision tree using all observable features (claim family, perturbation family, perturbation magnitude, baseline feasibility, baseline overload counts, baseline objective change under perturbation). Fitted on Stage A training folds via `sklearn.tree.DecisionTreeClassifier` with `max_depth=4` and `min_samples_leaf=20`, hyperparameters fixed at lock time.

This v0.2 split corrects the v0.1 mislabeling that called a fitted decision tree a "handwritten rule." B4 is the true rule baseline (no fitting); B5 is the simplest learned interpretable model. The learned predictor (Section 13) is the next tier above B5, using the same feature set with more flexible model classes and tuned hyperparameters.

The **oracle** policy is included for context: it predicts the true label perfectly. The gap between oracle and the learned predictor is the room for improvement; the gap between B5 and the learned predictor is the marginal value of additional model flexibility over a shallow tree; the gap between B4 and B5 is the marginal value of any learning over hand-crafted rules.

## 12. Verification step (post-Stage A, pre-predictor training)

After Stage A data is collected and *before* any predictor is trained, the following verification is run on the 4,352 evaluation cells.

### 12.1 Non-degenerate label distribution per cell

For each `(claim_family × perturbation_family)` block, the operational sufficiency label distribution must satisfy:

```
0.10 ≤ P(operational_sufficiency = 1 | block) ≤ 0.90
```

Twelve blocks fall under this check: `{OBJ, STRUCT, RANK} × {CAPACITY, DISTANCE, DEMAND, INSERTION}`. PLAN_VALIDITY blocks are exempt because their label is 1.0 by construction.

### 12.2 Cross-validation feasibility

For each of the 68 LOIO folds, the test fold (single instance, 48 OBJ/STRUCT/RANK cells) must contain at least one positive and one negative example for at least two of the three claim families. If any fold is degenerate, the failure is routed through §12.5's deterministic revision procedure (instance replacement clause), which draws a replacement from the broader Uchoa-X eligible pool with the documented selection rules.

The v0.3/v0.4 design reserved a 3-instance buffer (68 eligible − 65 selected) inside §5.1 to support fold replacement; v0.5 absorbs that buffer into the Stage A roster and replaces the buffer-draw mechanism with the §12.5 procedure. Practically: under v0.5, the §12.5 replacement clause is the single canonical channel for any instance-level fix, and the §5.1 selection is no longer load-bearing in the post-collection phase.

### 12.3 Reference stability

As specified in Section 8.2, the unstable-cell rates on the three stability checks (objective, structure, ranking) must each remain below 5%. If exceeded, the affected cells are re-collected under the scaled reference protocol.

### 12.4 Feasibility decoupling diagnostic

To verify that the benchmark exposes the failure mode it was designed to expose, compute:

```
P(numerical_sufficiency = 1 AND feasibility_flag = 0 | claim = OBJ, family = CAPACITY)
```

This quantity should remain above 0.20 in Stage A. Falling below indicates the capacity perturbation grid has lost the decoupling phenomenon, and the grid is revised under the procedure in Section 12.5.

### 12.5 Revision procedure (deterministic)

If any check in §12.1–12.4 fails, exactly one revision pass is permitted before Stage A data must be re-collected. The revision menu is in Appendix A and is fully deterministic: the failure mode dictates the substitution.

- **§12.1 failure (label distribution outside [0.10, 0.90]).** The offending block is mapped to the next severity level for its perturbation family (Appendix A). Increase severity if the block is too positive; decrease if too negative. Only one substitution per block is allowed.

- **§12.2 failure (degenerate fold).** Replace the offending instance from the broader Uchoa-X pool. The replacement draw is deterministic: from the 100 − 68 = 32 instances excluded by the n_customers > 500 filter, drop those that would still fail §5.1's structural criteria, sort the remainder by `(n_customers, instance_id)`, and substitute the first ID not already in the roster. The replacement is flagged in `instances/stage_a_instances.txt` with a comment header recording the substituted ID and the reason. No threshold or grid change is permitted.

- **§12.3 failure (reference instability above 5%).** Re-collect the affected cells under PyVRP 120s with full multi-seed audit. No threshold change is permitted.

- **§12.4 failure (decoupling diagnostic below 0.20).** This is a structural failure of the benchmark design. Do not attempt to fix in v1.x. Halt, document the result as a structural finding, and reconsider whether the framework's premises hold on the chosen test bed.

The thresholds, definitions, baselines, and hypotheses in Sections 3, 9, 11, and 14 may not be adjusted under any verification failure. The grid is the design knob; the constructs are not.

## 13. Predictor specifications

The learned sufficiency predictor is the ML contribution and the recruiter-facing artifact built on top of the benchmark.

### 13.1 Target

Primary target: `operational_sufficiency` (binary), restricted to OBJ/STRUCT/RANK claim families (3,264 training cells in Stage A; v0.5). Secondary targets: `numerical_sufficiency` (diagnostic), `structural_sufficiency` (claim-family-specific descriptive analysis).

PLAN_VALIDITY cells are not used in predictor training because their label is 1 by construction. They appear as a positive control in descriptive analyses (H2) and in the LLM closing experiment (§14.3).

### 13.2 Feature set

Features must be computable *before* recomputation — that is, from the baseline solution S, the perturbation specification, and a single fixed-solution evaluation. PyVRP outputs on the perturbed instance are labels and may not enter the feature set.

Allowed features (locked):

```
# Instance features (computed from unperturbed instance)
n_customers, n_routes_baseline, depot_x, depot_y,
mean_customer_demand, std_customer_demand, customer_density_kde,
mean_pairwise_distance, std_pairwise_distance,
demand_capacity_ratio = total_demand / (n_routes * capacity)

# Baseline solution features (computed from S)
mean_route_load, max_route_load, min_route_load, std_route_load,
mean_route_cost, std_route_cost,
n_near_full_routes (load > 0.9 * capacity),
n_full_routes (load == capacity),
route_load_imbalance = (max_route_load - min_route_load) / capacity

# Perturbation features
perturbation_family (one-hot),
perturbation_magnitude (numeric, in family-specific units),
n_affected_customers, affected_demand_share,
affected_route_share

# Fixed-solution evaluation features (from reuse_direct)
reuse_feasible (bool),
reuse_n_overload, reuse_max_overload_fraction,
reuse_objective_delta_pct = (reuse_obj - baseline_obj) / baseline_obj

# Claim features
claim_family (one-hot, 3 levels: OBJ, STRUCT, RANK)
```

The data-grounding analysis showed that `min_slack_ratio` is degenerate on Phase 3 instances (essentially zero on all 15) because PyVRP packs at least one route to capacity. The v0.1 feature set included `min_slack_route` and `mean_slack_ratio`, which would carry no information. v0.2 replaces these with route load distribution features (`std_route_load`, `route_load_imbalance`, `n_full_routes`, `n_near_full_routes`) that capture genuine instance-level variation.

Total: ~25 features. Final feature list is in `prereg/feature_spec.yaml`, locked.

### 13.3 Model classes

In order of priority:

- **Logistic regression** with L2 regularization. Hyperparameter grid: `C ∈ {0.01, 0.1, 1.0, 10.0}`, fitted on standardized features. Tuned by nested 5-fold CV inside training folds. Primary model.

- **Decision tree.** `max_depth ∈ {3, 4, 5, 6}`, `min_samples_leaf ∈ {10, 20, 50}`. Tuned by nested 5-fold CV. Reports human-readable rules.

- **Gradient boosting** (LightGBM). `n_estimators ∈ {50, 100, 200}`, `max_depth ∈ {3, 4, 5}`, `learning_rate ∈ {0.05, 0.1}`. Robustness check; not the headline model.

The "primary" model is logistic regression. Decision tree provides interpretability. Gradient boosting checks whether nonlinearities exist that the linear model misses.

### 13.4 Calibration

Predicted probabilities are calibrated via Platt scaling fit on the inner CV folds. Calibration is reported as expected calibration error (ECE) on the held-out fold.

## 14. Headline metrics and hypotheses

### 14.1 Predictor metrics

For each model class, reported under LOIO:

- **AUROC** on operational_sufficiency. Headline metric.
- **Precision and recall** at the threshold that maximizes F1 in the inner CV.
- **Unsafe reuse rate** = `P(predicted_sufficient = 1 | true_sufficient = 0)`. The dangerous error.
- **False recompute rate** = `P(predicted_sufficient = 0 | true_sufficient = 1)`. The wasteful error.
- **ECE** for calibration.

All metrics reported with bootstrap 95% CIs over the 68 LOIO folds.

### 14.2 Policy metrics (compute-aware)

Two policies are reported. The first is deployable; the second is an oracle for upper-bound analysis. The v0.1 policy was an oracle written in deployable form — an error caught in revision.

**Deployable policy:**

```
if claim_family == PLAN_VALIDITY:
    use reuse_direct  # trivially sufficient by construction
elif predicted_operational_sufficient and reuse_feasible:
    use reuse_direct
elif claim_family in {STRUCT, RANK}:
    use pyvrp_10s
elif not reuse_feasible and λ > λ_high_threshold:
    use clarke_wright
else:
    use pyvrp_10s
```

The deployable policy uses only information available at decision time: claim_family, the predictor's output, the deterministic reuse_feasibility check, and the runtime budget. It does not use loss values, which are only knowable after running the reference.

**Oracle policy** (for upper-bound analysis only):

```
choose action a minimizing observed_loss(a) + λ * runtime(a)
```

The oracle has access to all action losses and runtimes, computed during the benchmark. It represents the best achievable loss-runtime tradeoff if the system had perfect foresight.

Reported metrics for both policies:

- **Pareto curves** of mean loss vs mean runtime, swept over `λ ∈ {0, 1e-4, 1e-3, 1e-2, 1e-1, 1, 10}`.
- **Compute saved at fixed loss budget**: for loss budget `L ∈ {0.05, 0.10, 0.20}`, mean runtime under the policy compared to always-`pyvrp_60s`.
- **Loss incurred at fixed compute budget**: for runtime budget `T ∈ {1s, 5s, 30s mean per cell}`, the mean loss.

The headline comparison is the deployable policy vs fixed-action baselines (always-reuse, always-pyvrp_10s, always-pyvrp_60s). The oracle bounds the achievable region.

### 14.3 LLM-in-the-loop closing experiment

Thirty-five natural-language prompts spanning the four claim families (≥ 7 per family for OBJ, STRUCT, RANK; ≥ 14 for PLAN_VALIDITY since it serves as the positive control) are routed through the full pipeline:

```
prompt → claim-family classifier → sufficiency predictor (or trivial-yes for PLAN_VALIDITY) → action policy → answer generator
```

Each generated answer is scored along all three axes:

- **Faithfulness:** does the answer correctly report the action's output? Manual grading by the candidate; rubric in `closing/faithfulness_rubric.md`.
- **Sufficiency:** action's loss vs reference, computed automatically.
- **Operational validity:** action's feasibility flag, computed automatically.

Per-axis pass rates across the 35 prompts are reported, broken down by claim family.

### 14.4 Hypotheses and pass/fail criteria

Pre-specified hypotheses, each falsifiable. The thesis presents results regardless of whether they confirm or falsify; framing adjusts accordingly.

**H1a (primary).** The learned predictor (logistic regression) achieves AUROC on operational sufficiency that exceeds B4_rule_policy by at least 0.05 in LOIO, with the lower bound of the bootstrap 95% CI above zero.

The data-grounding pilot on Phase 3's 105 cells produced an AUROC of 0.878 for a model with `claim + perturbation_family + magnitude` versus 0.754 for `claim` alone (gap = 0.124). H1a's expected effect size of +0.05 is therefore well within reach but is not guaranteed at Stage A scale because B4's rule policy is strictly stronger than "claim alone" (it includes feasibility and reuse-objective signals).

- *Confirmed:* the learned predictor is the centerpiece of the ML chapter.
- *Falsified:* contribution shifts to "the rule baseline captures most of the signal at this dataset size; the sufficiency-decision surface admits compact rule-based descriptions."

**H1b (secondary).** The learned predictor matches or improves over B5_shallow_tree (AUROC delta ≥ 0 in LOIO, with the lower bound of the bootstrap 95% CI above −0.02).

This is a weaker test than H1a because B5 has access to the same feature set and uses a flexible model class. H1a beats B4 (rules); H1b establishes that the additional model flexibility of logistic regression over a shallow tree produces no meaningful regression.

- *Confirmed (H1a only):* ML contribution holds against rules but logistic regression does not strictly improve over a shallow tree; both are valid presentations.
- *Confirmed (H1a and H1b):* learned predictor strictly improves over both.
- *Falsified (H1b only):* logistic regression is dominated by the shallow tree; the thesis presents the shallow tree as the headline model.

**H2.** Operational sufficiency rates differ across claim families OBJ, STRUCT, RANK (chi-square test, α = 0.05, Bonferroni-corrected for the three-way comparison; PLAN_VALIDITY excluded as positive control).

- *Confirmed:* claim-conditional sufficiency is empirically established.
- *Falsified:* the conceptual contribution is weakened. Failure prompts re-examination of which dimension of conditioning matters.

**H3.** Feasibility decoupling exists in the CAPACITY family: among cells with `loss_obj ≤ 0.05` and `claim_family = OBJ`, the fraction with `feasibility_flag = 0` exceeds 0.20 in Stage A.

- *Confirmed:* the three-axis decomposition is empirically motivated.
- *Falsified:* the operational-validity axis is less informative than expected.

**H4.** The deployable policy strictly Pareto-dominates each fixed-action baseline (always-reuse, always-pyvrp_10s, always-pyvrp_60s) at some `λ` in the swept grid.

- *Confirmed:* the systems contribution holds.
- *Falsified:* the policy collapses to a single fixed action across the λ grid; result still reportable but contribution narrows.

**Negative-result clause.** If H1a falsifies (learned predictor does not beat rules), H2 confirms, H3 confirms, and H4 confirms, the thesis remains complete. The contributions become: (1) conceptual three-axis decomposition with empirical support from H3; (2) empirical claim-conditional sufficiency from H2; (3) benchmark itself, released as artifact; (4) compute-aware policy from H4. The ML contribution becomes "interpretable rule-based sufficiency policies are within X AUROC of learned alternatives, indicating the decision surface admits compact rule-based descriptions." This outcome is anticipated and pre-defended.

## 15. What is locked vs what is flexible

To remove ambiguity at the time of execution.

**Locked at v1.0 (require versioned amendment to change):**

- All construct definitions in Section 3
- Schema in Section 4
- Instance selection procedure and the resulting list in Section 5
- Perturbation specifications in Section 6
- Action set in Section 7
- Reference protocol in Section 8 (with the single exception in 8.2 and the 12.5 amendment door)
- Loss metrics, threshold values, and band cutoffs in Section 9
- CV protocol in Section 10
- Baseline policies in Section 11
- Verification checks and the deterministic revision procedure in Section 12
- Predictor target, feature set, and model classes in Section 13
- Hypotheses and pass/fail criteria in Section 14
- The revision menu in Appendix A

**Flexible (may change without amendment):**

- Code organization, naming, refactoring within the schema
- PyVRP minor-version updates (bug fixes only)
- Visualization and figure design
- Wording of natural-language prompts in the closing experiment, provided each prompt is unambiguously classifiable to its claim family
- Storage layout (Parquet → DuckDB → SQLite is fine; the schema is what matters)

**Forbidden post-lock:**

- Any change to thresholds in response to observed data
- Any change to perturbation magnitudes that has not gone through the §12.5 procedure
- Any change to the predictor feature set after seeing test-fold results
- Any change to baseline definitions
- Any change to hypothesis framing after observing results
- Any change to Appendix A's revision menu after the first verification result is observed

## 16. Locking procedure

The document is locked by:

1. Final review pass and revision to v1.0.
2. Commit to the thesis git repository with message `"Lock pre-registration v1.0 — no further changes without amendment"`.
3. Tag the commit `prereg-v1.0`.
4. Record the commit hash and timestamp in the Status block at the top of this document at the next commit.
5. Optionally, deposit a copy on the Open Science Framework (OSF) for an external timestamp.
6. From this point forward, all benchmark code references this commit hash as the authoritative specification.

## 17. Amendment procedure

Amendments are bumps from v1.0 → v1.1, v1.2, etc. Each amendment includes:

- Section being amended.
- Old text and new text.
- Reason for the change, with explicit acknowledgment of the data state at the time (e.g., "before Stage A collection," "after Stage A verification, before predictor training").
- Why the change does not undermine the pre-registration's purpose.

Amendments are committed and tagged. The thesis cites both v1.0 and the current version, and any analyses run under earlier versions are clearly marked.

Amendments that affect the headline hypotheses (H1a, H1b, H2, H3, H4) require an explicit explanation in the thesis discussion. Amendments to thresholds in response to observed data are forbidden under any circumstance.

## Appendix A. Revision menu for verification failures

If §12.1 verification fails on a (claim_family × perturbation_family) block, the revision is deterministic: the offending block's perturbation magnitude grid steps to the next severity level. Each family's escalation and de-escalation menus are below. Only one substitution per block is permitted before re-collection.

### A.1 CAPACITY escalation/de-escalation

Default: ρ ∈ {0.02, 0.05, 0.10, 0.20}.

| direction | revised ρ                  | rationale                          |
|-----------|----------------------------|------------------------------------|
| escalate  | {0.05, 0.10, 0.20, 0.35}   | block too positive: push harder    |
| de-escalate | {0.01, 0.02, 0.05, 0.10} | block too negative: ease off       |

### A.2 DISTANCE escalation/de-escalation

Default: multiplier 2.0 across all four region rules.

| direction   | revised multiplier | rationale                          |
|-------------|-------------------|--------------------------------------|
| escalate    | 2.5               | block too positive (e.g., OBJ × DIST) |
| de-escalate | 1.5               | block too negative (e.g., STRUCT × DIST) |

If multiple DIST blocks fail in opposite directions simultaneously (OBJ too easy, STRUCT too hard), the family structure itself is structurally incompatible with the threshold set. In that case, do not apply any single revision; halt and document.

### A.3 DEMAND escalation/de-escalation

Default: δ ∈ {0.10, 0.50, 0.50, 1.00}.

| direction   | revised δ                  | rationale                       |
|-------------|----------------------------|----------------------------------|
| escalate    | {0.25, 0.75, 0.75, 1.50}   | block too positive               |
| de-escalate | {0.05, 0.25, 0.25, 0.50}   | block too negative               |

### A.4 INSERTION escalation/de-escalation

Default: γ ∈ {0.30, 0.70, 1.20, 2.00}.

| direction   | revised γ                  | rationale                       |
|-------------|----------------------------|----------------------------------|
| escalate    | {0.50, 1.00, 1.50, 2.50}   | block too positive               |
| de-escalate | {0.15, 0.40, 0.80, 1.50}   | block too negative               |

### A.5 Tie-breaking

If a block's revision falls between two menu entries, choose the entry one step further from the current default. This forbids interpolation and keeps revisions discrete and pre-specified.

## 18. Glossary

- **Cell.** A tuple `(instance, perturbation, claim_family)`. Stage A has 4,352 cells.
- **Cell-action.** A tuple `(instance, perturbation, claim_family, action)`. Stage A has 21,760 cell-actions.
- **Action.** One of the five candidate computational artifacts the copilot can use to answer a query.
- **Reference.** The output of `pyvrp_60s` on the perturbed instance with seed=1. The ground truth against which all other actions are compared.
- **Loss.** Claim-family-specific error metric between an action's output and the reference. Lower is better.
- **Band.** Categorical version of loss: easy, medium, or hard.
- **Operational sufficiency.** Claim-dependent label. The primary predictor target on OBJ/STRUCT/RANK.
- **PLAN_VALIDITY.** A claim family that asks "is the existing plan still valid?" — trivially answerable from S, used as a positive control. Excluded from predictor training.
- **LOIO.** Leave-one-instance-out cross-validation. The primary CV protocol.
- **LOPO.** Leave-one-perturbation-family-out. The secondary stress test.
- **Operational validity.** An axis attached to every action: whether the action's output plan is feasible under the perturbed instance.

## 19. Change log

- **v0.1 (2026-04-29):** Initial draft. Not locked. Internal critique identified structural issues with FEAS framing, ranking metric, baseline naming, oracle leakage in policy specification, and reference stability checks. Data-grounding analysis on Phase 3 cells invalidated slack-relative perturbation anchoring.

- **v0.2 (2026-04-30):** Substantive revision integrating reviewer feedback and data-grounding findings. Specific changes:

  *Conceptual:*
  - §3.2: FEAS removed as claim family. Replaced by PLAN_VALIDITY (positive-control claim family) and operational_validity (per-action axis attached separately).
  - §3.3: operational_sufficiency made claim-dependent. PLAN_VALIDITY trivially sufficient by construction; STRUCT/RANK no longer require operational validity.

  *Schema:*
  - §4.1: `loss_feas` replaced by `loss_plan_validity` (only populated for reuse_direct on PLAN_VALIDITY cells). Reference stability fields expanded to include structure and ranking.

  *Instance set:*
  - §5.2: Stage B clarified. 100-instance target may include up to 10 instances >500 customers under scaled reference protocol; if eligible pool is exhausted, headline number drops accordingly.

  *Perturbations (most substantial change):*
  - §6.1 CAPACITY: slack-relative formula replaced by direct `new_capacity = capacity × (1 − ρ)` with ρ ∈ {0.02, 0.05, 0.10, 0.20}. Validated by Phase 3 dose-response curve.
  - §6.2 DISTANCE: multiplier raised from 1.25 to 2.0 (Phase 3 showed OBJ × DIST = 0.98 at 1.25, fails verification's lower band).
  - §6.3 DEMAND: anchor changed from `min_slack_route × β` to direct `(1 + δ)` inflation with δ ∈ {0.10, 0.50, 0.50, 1.00}.
  - §6.4 INSERTION: anchor changed from `min_slack_route × γ` to `vehicle_capacity × γ` with γ ∈ {0.30, 0.70, 1.20, 2.00}. `hash(instance_id)` replaced by stable SHA256 hash for cross-session determinism.

  *Reference:*
  - §8.2: structural and ranking stability checks added (ARI across seeds, top-3 Jaccard across seeds). v0.1 had only objective stability.

  *Loss metrics:*
  - §9.4 RANK: switched from action-side route ranking to baseline-group ranking, eliminating the route-identity ambiguity in v0.1.
  - §9.5: operational validity flag separated from loss metrics, made independent of claim family.

  *Baselines:*
  - §11: B4 split into B4_rule_policy (true hand-written rules) and B5_shallow_tree (the learned tree v0.1 mislabeled as "handwritten"). H1 split into H1a (vs B4) and H1b (vs B5).

  *Verification:*
  - §12.5: deterministic revision procedure added, referencing Appendix A. v0.1's vague "perturbation grid may be revised" is replaced by pre-specified menu lookups.

  *Predictor:*
  - §13.1: PLAN_VALIDITY excluded from training (3,600 training cells instead of 4,800).
  - §13.2: slack-related features removed (degenerate per data analysis); route load distribution features added.

  *Policy:*
  - §14.2: deployable policy and oracle policy split. v0.1's policy used `loss(a)` at decision time, which is oracle information.

  *New:*
  - §2.1 (CVRP scope defense), §12.5 (deterministic revision procedure), Appendix A (revision menu).

- **v0.3 (2026-05-04):** Mechanical revision. No construct, threshold, or hypothesis moves. Specific changes:

  *Instance set:*
  - §5.1: Stage A target reduced from 75 to 65. The v0.1 draft estimated ~90 instances eligible after the n_customers > 500 exclusion; empirical analysis of the Uchoa-X size distribution at the locked threshold yields 68 eligible. Target dropped to 65 to preserve the methodological rationale of the >500 threshold (PyVRP 60s reference quality drift at larger scales) while maintaining a 3-instance buffer for §12.2 fold-replacement. The classification table (`data/instances/uchoa_x_classification.csv`) was transcribed from Tables 11–13 of Uchoa et al. 2017 and committed alongside `scripts/select_instances.py` (deterministic stratified sample, seed `20260429`, Hamilton's largest-remainder method with rng-randomized tie-breaking) and `scripts/verify_classification.py` (independent quintile re-derivation, marginal counts, PyVRP `n_customers` cross-check).
  - §5.2: Stage B target reduced from 100 to 78 as the cascading consequence of §5.1. The 50–500-customer pool for Stage B drops from ~15 to 3 (Stage A consumes 65 of 68 eligible); the >500-customer scaled-reference contribution is unchanged at up to 10.

  *Reference protocol:*
  - §8.2: Audit sampling clarified. v0.2 wording described the audit as a "20% subset of cells" stratified across `claim_family × perturbation_family`; the implementation samples at the `(instance, perturbation)` pair level and propagates audit data to all four cells of each sampled pair. This is the natural unit because a PyVRP reference solve produces all four claim-family outputs from a single solution. Counts updated for the new 65-instance roster: 208 audit pairs (4 families × 52 pairs each), 832 audited cells, 416 audit keys (208 pairs × 2 audit actions: `pyvrp_60s_seed2` and `pyvrp_60s_seed3`). RNG seed unchanged.

  *Schema and downstream counts:*
  - §4: cell-action row count adjusted to 20,800 (= 65 × 16 × 4 × 5).
  - §10.1: LOIO training-fold size adjusted to 64; bootstrap CIs computed over 65 folds; OBJ/STRUCT/RANK training cell count adjusted to 3,120.
  - §12: verification operates on 4,160 cells.
  - §12.2: 3-instance buffer language added.

  *No changes:* construct definitions (§3), perturbation grids (§6), action set (§7), loss metrics and bands (§9), baseline policies (§11), predictor specifications (§13), headline metrics and hypotheses (§14), what is locked vs flexible (§15), Appendix A revision menu. H1's effect-size analysis at n=65 instances is comfortably above the ~50-instance threshold for the bootstrap CI on the +0.05 AUROC headline.

- **v0.4 (2026-05-04):** Mechanical revision. Single-section amendment.

  *Perturbations:*
  - §6.4 INSERTION: RNG seeding amended from per-instance to per-(instance, perturbation_id). The v0.3 specification produced RNG state collisions across INS_1, INS_2, INS_3, INS_4 on the same instance, causing structurally redundant new-customer placements (INS_2's first sample coincided with INS_1's only sample, INS_3's first three with INS_2's three, etc.). Per-(instance, perturbation_id) seeding ensures the four INS variants produce distinct placements while preserving cross-session determinism. The hash input changes from `instance_id.encode()` to `f"{instance_id}_{perturbation_id}".encode()`.

  *No changes:* construct definitions (§3), schema (§4), instance set (§5), perturbation magnitudes or family structure (§6.1–§6.3, §6.5), action set (§7), reference protocol (§8), loss metrics (§9), aggregation (§10), baselines (§11), verification (§12), predictor (§13), policies (§14), what is locked vs flexible (§15), Appendix A. The amendment is mechanical: only the seed-input string changes; magnitudes, n_new counts, and spatial-pattern definitions are unchanged.

- **v0.5 (2026-05-11):** Mechanical revision. No construct, threshold, or hypothesis moves.

  *Instance set:*
  - §5.1: Stage A target raised from 65 to **68** — the full eligible pool. v0.3 reserved 3 instances of the 68-eligible pool as a §12.2 fold-replacement buffer; v0.5 absorbs that buffer into the main Stage A roster. The new roster is a strict superset of the v0.3 roster: it contains all 65 previously-selected IDs plus the three previously-reserved buffer IDs `X-n298-k31`, `X-n376-k94`, `X-n429-k61`. The selector's behaviour is unchanged — when `--target` equals the pool size, the stratified-sampling step is a no-op and the full sorted eligible list is written. RNG seed `20260429` is retained for backward compatibility.
  - §5.2: Stage B composition updated. The 50–500-customer pool is now exhausted at Stage A (was: Stage A consumed 65 of 68; now: Stage A consumes all 68), so Stage B adds zero small instances. The Stage B ceiling of 78 is unchanged: the entire +10 comes from the >500 pool under the scaled reference protocol.

  *Reference protocol:*
  - §8.2: Pair counts updated for the new 68-instance roster. 68 × 16 = 1,088 pairs total; the 20% audit fraction, applied per stratum with rounding, selects 216 pairs (4 families × 54 pairs each: `round(272 × 0.20) = 54`). 864 audited cells; 432 audit keys (216 pairs × 2 audit actions). RNG seed unchanged. Stratified-rounding semantics unchanged from v0.3 (still per-family `round()`, not naive 20% of the unstratified pair total — which would have given 218 pairs; the 2-pair gap is the per-family quantization).

  *Schema and downstream counts:*
  - §4: cell-action row count adjusted to 21,760 (= 68 × 16 × 4 × 5). Evaluation cell count: 4,352.
  - §10.1: LOIO training-fold size adjusted to 67; bootstrap CIs computed over 68 folds; OBJ/STRUCT/RANK training cell count adjusted to 3,264.
  - §12: verification operates on 4,352 cells; 68 LOIO folds.

  *Verification:*
  - §12.2: 3-instance buffer language removed. Instance-level fold failures now route through §12.5's revision procedure (instance-replacement clause), which draws from the broader Uchoa-X pool with documented deterministic selection rules. This consolidates the buffer-draw mechanism that was split across §5.1 (pool maintenance) and §12.2 (fold replacement) into a single canonical channel in §12.5.
  - §12.5: instance-replacement clause expanded to specify the deterministic draw rule for the §12.2 failure path (sort excluded instances by `(n_customers, instance_id)`, take the first not in roster, flag the substitution in the roster header).

  *Stage A key count headline:* 5,440 base + 432 audit = **5,872** total Stage A keys (was: 5,200 base + 416 audit = 5,616 at v0.3).

  *No changes:* construct definitions (§3), perturbation grids (§6), action set (§7), loss metrics and bands (§9), LOPO (§10.2), no-selection rule (§10.3), baseline policies (§11), §12.1/§12.3/§12.4 thresholds and procedures, predictor target/feature set/model classes (§13), headline metrics and hypotheses (§14), what is locked vs flexible (§15), Appendix A revision menu. H1's effect-size analysis at n=68 instances is even more comfortably above the ~50-instance bootstrap-CI threshold than at v0.3's n=65.

- **v1.0 (TBD):** Locked. No data collected before this version.

---

*End of pre-registration document.*

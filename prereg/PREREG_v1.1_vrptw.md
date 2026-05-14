# Pre-Registration: VRPTW Sufficiency Benchmark

**Status:** LOCKED v1.1 — no further changes without versioned amendment.
**Author:** Juan
**Date drafted:** 2026-05-14
**Date locked (v1.0):** 2026-05-14T00:24:20+02:00
**Date locked (v1.1):** 2026-05-14
**v1.0 lock commit:** `09c4c03fa087c4b0b9d568f1de258e94ee003ef5`
**v1.0 lock tag:** `prereg-v1.0-vrptw`
**v1.1 lock commit:** `7d9cf08`
**v1.1 lock tag:** `prereg-v1.1-vrptw`
**Locking procedure:** see Section 16. **Amendment procedure:** see Section 17.

> This is the locked v1.1 pre-registration for the VRPTW track. v1.1 amends v1.0 in one place — the definition of `reference_struct_unstable` for cells with no feasible reference on any seed — per the §17 amendment procedure. The v1.0 document (`prereg/PREREG_v1.0_vrptw.md`) remains as the original locked specification. v1.1 is the current authoritative spec for analyses run after the v1.1 lock; the thesis cites both v1.0 and v1.1 per §17. See §19 for the change log and the empirical reason for the amendment. The CVRP pre-registration (`PREREG_v0.5.md`) is unchanged and remains the locked specification for the CVRP track.

---

## 1. Purpose

This document fixes every methodological choice that governs the VRPTW Sufficiency Benchmark — claim definitions, sufficiency labels, perturbation grids, action portfolio, reference protocol, error metrics, threshold values, cross-validation procedure, baseline policies, headline metrics, and pass/fail criteria. Once locked, no element in Sections 3–14 may change without a versioned amendment that documents the change, the reason, and the data state at the time of the change.

The pre-registration exists for one reason. Threshold drift, post-hoc grid tuning, and outcome-targeted magnitude selection are the three failure modes that destroy benchmarks of this kind. Locking these choices before observing expanded data closes all three doors at once.

**Action-portfolio framing.** The benchmark evaluates an *action portfolio*, not an action *ladder*. v0.5 (CVRP) used the word "ladder" because the CVRP action set admitted a single monotonic quality ordering (`reuse_direct` ≺ `nearest_neighbor` ≺ `clarke_wright` ≺ `pyvrp_10s` ≺ `pyvrp_60s`). The VRPTW action set does not. The expanded-action 18-instance scale-check (`prereg/vrptw_scale_check_18_expanded_actions_report.md`) shows that `construct_feasible` (this draft's renamed `cheap_fresh_construct`) achieves 98% PLAN_VALIDITY-easy and 0% OBJ-easy, while `pyvrp_10s` achieves 100% OBJ-easy and 87% STRUCT-easy. These are not two points on a single quality axis; they are two operational specialisations — a *feasibility constructor* and a *budgeted metaheuristic* — that the copilot policy should select between, not order along. The benchmark's compute-aware policy work (§14.2) is the substantive value of representing the action set as a portfolio rather than a ladder.

**CVRP → VRPTW pivot.** The CVRP track's Stage A revealed a construct-level issue with `loss_struct` on Uchoa-X: PyVRP's route partitions are highly multimodal across seeds (CVRP-side stability check: `struct_unstable_rate ≈ 0.926`, `median ari_min ≈ 0.476` — see v0.5 §8.2). Under that solver noise floor, a STRUCT-easy/STRUCT-hard label is inseparable from PyVRP's partition multimodality on the unperturbed instance; the metric measures something the perturbation did not cause. VRPTW operates in a different regime: the Phase 1 stability probe (`prereg/vrptw_probe_phase1_report.md`) reports `struct_unstable_rate = 0.167`, `median ari_min = 1.000` on the unperturbed instance, and the 18-instance expanded-action scale-check reports `struct_unstable_rate = 0.194` under perturbation. Time-window constraints reduce the size of the feasible high-quality partition set the solver can land on, restoring the construct's signal-to-noise to a usable level. The pivot is therefore *evidence-driven*: the CVRP STRUCT result is a substantive empirical contribution (the metric does not work in that regime) and the move to VRPTW is the methodologically appropriate response (it does work in this regime).

The benchmark is constructed under the abstraction that natural-language queries map to claim families. A separate LLM-in-the-loop closing experiment (Section 14.3) tests that abstraction on actual prompts. Open-ended dialogue, multi-turn clarification, and full natural-language understanding are out of scope.

## 2. Scope and intentional limits

The benchmark covers the Vehicle Routing Problem with Time Windows (VRPTW) on the Solomon-100 instance set. It does not cover CVRP (covered separately by `PREREG_v0.5.md`), pickup-and-delivery, heterogeneous fleets, or the Homberger 200/400/600/800/1000 benchmarks. Each of those is a defensible extension, and each is excluded here so the benchmark's claim — that information sufficiency is claim-conditional under realistic VRPTW perturbations — can be tested on a single problem variant at a single scale under controlled perturbations.

Stage A targets all 56 Solomon-100 instances (the full eligible pool; see §5.1). Stage B, gated on Stage A's verification step *and* on a small unperturbed stability probe at the Homberger 200 scale, expands to Homberger 200 (the next-larger Solomon-family benchmark). No further expansion is part of this pre-registration; Homberger 400+ is out of scope.

### 2.1 Defense of VRPTW (Solomon-100) scope

The choice of VRPTW on Solomon-100 is methodological, not aspirational.

**Why VRPTW (and not CVRP).** The v0.5 CVRP track established the conceptual framework (three-axis decomposition, claim families, sufficiency labels, perturbation grids, reference protocol, deployable policy). Stage A on CVRP exposed that PyVRP's reference partition on Uchoa-X is multimodal across seeds at a rate that overwhelms the STRUCT signal a perturbation can produce. VRPTW is the natural extension on which the framework's STRUCT (and the new SCHEDULE) claim families operate in a clean noise regime, because the additional time-window constraints reduce the feasible high-quality partition count to a level at which the perturbation's structural effect is visible above seed noise.

**Why Solomon-100 (and not a larger benchmark).** Solomon-100 has 100 customers per instance, which is the smallest VRPTW benchmark with enough route count (typically 8–25) for STRUCT and SCHEDULE metrics to admit non-trivial bands. PyVRP at 60 s seed=1 is empirically saturated at this scale: the unperturbed Phase 1 probe shows objective stability across seeds (`obj_unstable_rate = 0.000`), and the 18-instance expanded-action scale-check shows the 60 s reference reaching `easy_rate = 1.000` on OBJ/STRUCT/SCHEDULE under perturbation (see `prereg/vrptw_scale_check_18_expanded_actions_report.md` §8). Larger scales (Homberger 200+) require longer reference budgets to reach equivalent saturation; PyVRP's own published benchmarks use 2-hour budgets at 1000 customers, which is outside this project's compute envelope at the full instance pool.

**Why 56 instances (the full eligible pool).** Solomon-100 contains exactly 56 instances spanning three customer-geometry classes (C — clustered, R — random, RC — random-clustered) and two scheduling regimes (1xx — narrow time windows, short horizons, many short routes; 2xx — wide time windows, long horizons, few long routes). The full pool is small enough that no further sampling is needed; selecting a subset would require a defensible sampling design and the §12.2 fold-replacement machinery v0.5 specified for the Uchoa-X case. With the full pool, every Solomon-100 archetype is in-distribution by construction and no fold-replacement design is needed (see §5.1 and §12.2).

Future work paragraph for the thesis discussion: the framework is specified at the level of constructs that admit natural Homberger-200 analogues — the operational-validity axis generalises to the same multi-constraint feasibility (capacity ∧ TW ∧ coverage), perturbation families generalise to the same four families with re-anchored magnitudes, claim families remain unchanged. Empirical validation under Homberger 200 is gated on Stage A passing verification and is specified in §5.2 as Stage B.

## 3. Construct definitions

### 3.1 Three-axis decomposition of copilot answer quality

Every answer the copilot produces is evaluated along three independent axes. The decomposition is the conceptual centerpiece of the thesis and is carried over from v0.5 §3.1 verbatim; only the operational-validity definition (axis 3) is adapted for VRPTW.

- **Faithfulness.** Does the copilot's natural-language answer accurately report the underlying action's output? Faithfulness is between the language layer and the action layer. For benchmark cells where outputs are programmatic, faithfulness is true by construction. The closing experiment in Section 14.3 measures it directly on LLM-generated answers.

- **Sufficiency.** Is the action's output close enough to the reference for the relevant claim family? Sufficiency is between the action layer and the reference. It is the central object of this benchmark and is measured by claim-family-specific loss against PyVRP 60s seed=1 on the perturbed VRPTW instance.

- **Operational validity.** Is the action's output an executable plan under the perturbed VRPTW instance? Operational validity is between the action layer and the real-world constraint set. For VRPTW it is the conjunction `capacity ∧ time_window ∧ coverage`: every route's load ≤ capacity, every visit's `start_service ≤ tw_late`, every customer is served exactly once. The flag is computed deterministically from the action's route plan via PyVRP's `Solution(perturbed_data, routes).is_feasible()` plus a `num_missing_clients == 0` check.

The benchmark documents that these three axes can decouple. An action can be faithful and sufficient yet operationally invalid (e.g., a reuse plan that reports a numerically-close cost but violates a tightened time window). It can be operationally valid and faithful yet insufficient (e.g., a feasibility-only construction that places every customer but ignores the baseline structure the user is asking about). The decomposition exists to make these decouplings visible.

Operational validity is an axis attached to *every action on every cell*, not a claim family. Whether an action's plan satisfies the perturbed-instance constraints is a property of the action, not of the query. As in v0.5, the user-facing query "is the existing plan still valid?" is its own claim family (PLAN_VALIDITY, §3.2), distinct from the per-action operational-validity flag (§9.5).

### 3.2 Claim families

Four claim families are defined. The list differs from v0.5: v0.5's RANK is excluded and a new family SCHEDULE is added. Rationale below.

- **Objective (OBJ).** Claims about the numerical objective value of a routing plan under the perturbed instance. Canonical natural-language form: "What is the new total cost?" / "How much does cost change?" The primary OBJ loss is computed on the locked PyVRP objective (distance under `unit_distance_cost=1, unit_duration_cost=0`); a *generalised* OBJ diagnostic (distance + 0.1 × duration) is reported in parallel for TRAVEL_TIME and SERVICE_TIME cells where distance is silent (see §9.1).

- **Plan validity (PLAN_VALIDITY).** Claims about whether the action's plan is executable under the perturbed VRPTW instance. Canonical form: "Can we keep using this plan?" / "Is this plan still valid?" For VRPTW, plan validity is `capacity ∧ TW ∧ coverage` (no overloaded route, no time-window violation, all customers served). The reference answer is the deterministic feasibility check on the action's route set under the perturbed constraints; no solver is needed to compute it.

  > **v0.5 → v1.0 semantic shift.** v0.5 defined PLAN_VALIDITY as a *positive-control* family: the label was true by construction (reuse_direct's pipeline runs the feasibility check on the baseline solution, so the reuse answer is always correct). v0.5 excluded PLAN_VALIDITY from predictor training and from the §12.1 verification range check. **v1.0 redefines PLAN_VALIDITY as a substantive feasibility claim** computed per-action. Under v1.0, the PLAN_VALIDITY label on `reuse_direct` is informative because the perturbation may invalidate the baseline plan (the 18-instance expanded-action data reports `reuse_direct` PLAN_VALIDITY-easy at 30%, hard at 70%); the label on `pyvrp_10s` is informative because even a 10 s solve may not find a feasible plan on tight cells; the label on the reference is informative because some perturbations exhaust the fleet at 60 s and no feasible plan exists (the §8 reference-failure clause). The positive-control role is eliminated; PLAN_VALIDITY enters predictor training and §12.1 verification on equal footing with OBJ/STRUCT/SCHEDULE.

- **Structure (STRUCT).** Claims about the customer-to-route assignment under the perturbed instance. Canonical form: "Which customers move?" / "Are the same customers still served together?" Loss is `1 − ARI(action_assignment, reference_assignment)` computed on the intersection of customer sets (ORDER_CHANGE cells extend the customer set by the inserted customers; ARI is computed on the common subset).

- **Schedule (SCHEDULE).** Claims about *when* customers are served and how their service times shift under the perturbation. Canonical form: "When will deliveries arrive?" / "Whose schedules slip?" Loss is the p90 of `|start_service_action − start_service_reference| / depot_horizon` restricted to the *affected* customer subset (the customers whose baseline-vs-perturbed comparison is meaningful; for ORDER_CHANGE, the inserted customers are excluded since they have no baseline counterpart; fallback to all common customers if the affected set is empty). The definition is the "v2" SCHEDULE metric from `prereg/vrptw_perturbation_pilot_v2_report.md` §6 and §12.4. Thresholds are locked in §9.4 to easy ≤ 0.02, medium ≤ 0.05, hard > 0.05, calibrated on the pilot's affected-p90 distribution (median 0.0214, p90 0.0645 in the pilot; median 0.0214, p90 0.2415 in the 18-instance scale-check).

**v0.5's RANK is excluded from v1.0.** On CVRP, operational quality is scalar (cost), and "which routes are most affected" reduces to ranking baseline groups by cost delta. On VRPTW, "which routes are most affected" admits multiple incompatible interpretations: cost delta, total lateness, schedule shift, slack consumption, and TW-violation count are all plausible per-route impact metrics and they do not co-rank. Picking one arbitrarily (e.g., cost delta, as in v0.5 §9.4) reintroduces exactly the construct-arbitrariness signature the CVRP STRUCT finding warned against: the metric reports something about the choice of impact dimension as much as it reports something about the perturbation. SCHEDULE captures the most operationally-critical version of "where is the impact concentrated" — *whose* schedule shifts — without forcing a route-level ranking choice.

The fifth family of "metareasoning / action recommendation" considered in earlier drafts is excluded (as in v0.5) as a category error: it describes the policy itself, not a claim about the artifact, and would create circular evaluation.

Every benchmark cell carries exactly one claim family.

### 3.3 Sufficiency labels

Three sufficiency labels are defined per cell. The benchmark stores all three; the predictor (Section 13) trains on operational_sufficiency for all four claim families.

**Numerical sufficiency** is `band[reuse_direct, claim_family] == 'easy'`. The fixed solution evaluated under the perturbation is numerically close to the reference for this claim family. This label is diagnostic only and is not the primary predictor target. Numerical closeness without operational validity is the failure mode the benchmark exists to expose.

**Operational sufficiency** is claim-dependent.

- **OBJ:** `band[reuse_direct, OBJ] == 'easy' AND feasibility_flag[reuse_direct] == TRUE`. An objective answer that reports a cost number is only operationally honest if the underlying plan is executable. Numerical closeness with infeasibility is exactly the failure case the benchmark exposes; an answer that's "close" to the right cost on an unflyable plan is wrong, not approximately right. (Same rule as v0.5.)

- **PLAN_VALIDITY:** `band[reuse_direct, PLAN_VALIDITY] == 'easy'`, equivalently `feasibility_flag[reuse_direct] == TRUE`. The label is true exactly when the cheap action's plan is itself executable. This is a substantive claim under v1.0: the 18-instance scale-check reports PLAN_VALIDITY-easy at 30% for reuse_direct and 50% for local_repair_insert on OC cells, so the label is not trivial.

- **STRUCT:** `band[reuse_direct, STRUCT] == 'easy'`. Operational validity does not apply: a structural claim ("which customers move?") is answerable regardless of whether the underlying plan is feasible.

- **SCHEDULE:** `band[reuse_direct, SCHEDULE] == 'easy'`. Same reasoning as STRUCT — a schedule-shift claim is answerable on the action's reported start times regardless of whether the plan is feasible.

**Structural sufficiency** is `band[reuse_direct, STRUCT] == 'easy' AND band[reuse_direct, SCHEDULE] == 'easy'`, computed cell-wise. It captures whether the fixed solution preserves both the route organisation and the schedule of the reference. Used as a secondary predictor target and in descriptive analyses; not a primary headline metric.

This claim-dependent definition is carried over from v0.5 §3.3 with the RANK → SCHEDULE substitution and the PLAN_VALIDITY semantic shift (positive control → substantive feasibility) folded in.

## 4. Benchmark schema

The benchmark uses a **two-table schema**: a *wide* table with one row per `(instance, perturbation, action)` triple, and a *long* claim table with one row per `(instance, perturbation, action, claim_family)` quadruple. Both tables are stored as Parquet.

Wide-table key: `(instance_id, perturbation_id, action)`. Long-table key: wide-table key + `claim_family`.

For Stage A: 56 instances × 16 perturbations = 896 `(instance, perturbation)` cells. The non-OC perturbation families use 4 of the 5 actions in the portfolio (no `local_repair_insert`), the OC family uses all 5. That gives `(12 × 4) + (4 × 5) = 68` action rows per instance × 56 instances = **3,808 wide rows**. Each wide row produces 4 long rows (one per claim family): **15,232 long rows**.

### 4.1 Wide-table fields

```
instance_id            : str    # Solomon-100 instance identifier
perturbation_family    : str    # one of {TRAVEL_TIME, TIME_WINDOW, SERVICE_TIME, ORDER_CHANGE}
perturbation_id        : str    # globally unique id within (instance, family)
perturbation_magnitude : float  # in family-specific units (see §6)
action                 : str    # one of {reuse_direct, local_repair_insert,
                                #          construct_feasible, pyvrp_10s, pyvrp_60s_reference}
action_tier            : str    # action group label (see §7)
action_tier_index      : int    # 0..4
is_middle_action       : bool   # see §7
is_reference_action    : bool   # True only for pyvrp_60s_reference
action_objective       : float  # distance under perturbed instance (×10 PyVRP units)
action_objective_generalized : float  # distance + 0.1 × duration (see §9.1)
action_feasible        : bool   # capacity ∧ TW ∧ coverage under perturbed instance
action_infeasibility_kind    : str  # one of {none, capacity, time_window, both, coverage}
action_n_overload      : int    # number of capacity-overloaded routes
action_max_overload    : float  # max overload as fraction of capacity
action_time_warp       : float  # total time_warp across all visits (×10 PyVRP units)
action_num_missing_clients : int  # uncovered customer count (OC cells only; 0 elsewhere)
action_runtime_s       : float  # wall-clock seconds (single-thread within worker)
action_seed            : int|null  # seed for stochastic actions (pyvrp_*); null otherwise
action_solver_time_limit_s : float|null  # solver budget; null for non-pyvrp actions
action_valid           : bool   # mirrors action_feasible; surfaced for portfolio diagnostics
action_assignment      : json   # customer -> route_id map for action's plan
action_route_costs     : json   # route_id -> distance map under perturbed instance
action_route_starts    : json   # route_id -> list[start_service] under perturbed instance
reference_objective    : float  # PyVRP 60s seed=1 distance on perturbed instance
reference_feasible     : bool   # may be False on fleet-exhaustion cells (§8.3)
reference_assignment   : json
reference_route_costs  : json
reference_route_starts : json
reference_runtime_s    : float
reference_failure_kind : str    # one of {none, all_infeasible}
baseline_solution_feasible_under_perturbation : bool  # deterministic check on baseline routes
loss_obj_distance      : float  # |action_obj - ref_obj| / ref_obj (n/a if reference_infeasible)
loss_obj_generalized   : float  # generalized-cost variant (§9.1)
loss_plan_validity     : float  # 0 (action_feasible) or 1 (not)
loss_struct            : float  # 1 - ARI(action_assignment, reference_assignment)
loss_schedule          : float  # p90 of affected start-time shift (§9.4)
band_obj_distance      : str    # one of {easy, medium, hard, n/a}
band_obj_generalized   : str    # one of {easy, medium, hard, n/a}
band_plan_validity     : str    # one of {easy, hard}
band_struct            : str    # one of {easy, medium, hard, n/a}
band_schedule          : str    # one of {easy, medium, hard, n/a}
reference_obj_unstable    : bool   # (max - min) / min > 0.02 across seeds 1/2/3
reference_struct_unstable : bool   # min pairwise ARI across seeds 1/2/3 < 0.90
reference_ari_min         : float  # min pairwise ARI across seeds 1/2/3
reference_all_feasible    : bool   # True iff seeds 1, 2, 3 all feasible
reference_any_feasible    : bool   # True iff at least one seed feasible
audit_seed_2_obj          : float  # always populated under v1.0 protocol (see §8.2)
audit_seed_3_obj          : float
audit_seed_2_assignment   : json
audit_seed_3_assignment   : json
audit_seed_2_runtime_s    : float
audit_seed_3_runtime_s    : float
```

### 4.2 Long-table fields (`*_claim_rows`)

```
instance_id, perturbation_family, perturbation_id, perturbation_magnitude,
action, action_tier, action_tier_index, is_middle_action, is_reference_action,
action_runtime_s, action_seed, action_solver_time_limit_s, action_valid,
claim_family          : str    # one of {OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE}
loss                  : float  # the claim-family-specific primary loss
band                  : str    # easy / medium / hard (/ n/a)
sufficient_binary     : int|null  # 1 if band == easy; 0 if medium/hard; null if n/a
is_cheap_action       : bool   # cheap_action_for_family(family) == action
```

Storage: `data/stage_a/stage_a_wide.parquet` and `data/stage_a/stage_a_claim_rows.parquet`. Schema migrations require a version bump and explicit migration script.

## 5. Instance set

### 5.1 Stage A: 56 Solomon-100 instances

The 56 Solomon-100 instances used for Stage A are listed in `instances/solomon100_stage_a.txt`, committed alongside this document. The selection is mechanical: the full Solomon-100 pool (9 + 8 + 12 + 11 + 8 + 8 = 56 instances spanning C1, C2, R1, R2, RC1, RC2) is in-scope; no sampling, no filtering. Customer count is 100 on every instance by construction of the benchmark.

Rationale for taking the full pool rather than a sample:

1. The pool is small enough that an instance-level sampling design is not necessary; the §12.2 fold-replacement machinery v0.5 required for the Uchoa-X case (which sampled 68 of ~100 candidate Uchoa-X instances under a stratified design) is not needed here.
2. Every Solomon-100 archetype is by construction in-distribution. C / R / RC × 1xx / 2xx is the canonical Solomon stratification; using the full pool keeps every cell of that 6-cell stratification populated without a sampling commitment.
3. Compute fits the envelope. Reference protocol budget: 56 × 16 × 3 = 2,688 PyVRP 60 s solves = 161,280 CPU-seconds = 44.8 CPU-hours = 7.5 wall-hours on 6 cores. The 18-instance expanded-action scale-check used 2.55 wall-hours under the same protocol (864 solves); linear scaling to 56 instances projects ~7.9 wall-hours, comfortably below a single-day run.

**Headline counts (v1.0):** 56 instances × 16 perturbations × 4 claim families = **3,584 evaluation cells**; 896 `(instance, perturbation)` cells; **3,808 wide rows**; **15,232 long claim rows**. Stage A reference-solve key count: 2,688 solves (`(instance, perturbation, seed)` for seeds 1/2/3).

### 5.2 Stage B: Homberger 200, future work (contingent)

Stage B is *not part of v1.0's locked execution plan*. It is documented here to fix the future-work scope; the actual decision to run Stage B is gated on:

1. Stage A passing every §12 verification check, and
2. A small unperturbed stability probe at the Homberger 200 scale (5–10 Homberger-200 instances solved at PyVRP 120 s × seeds 1/2/3) producing `reference_struct_unstable < 0.25` and `reference_obj_unstable < 0.02`.

If both gates pass, Stage B specifies:

- Instance set: 60 Homberger 200 instances (the full Homberger-200 pool: 10 instances × 6 archetypes C1/C2/R1/R2/RC1/RC2).
- Reference protocol: PyVRP 120 s × seeds 1/2/3 per cell (full multi-seed audit).
- Action portfolio: `reuse_direct`, `local_repair_insert` (OC only), `construct_feasible`, `pyvrp_30s`, `pyvrp_120s_reference`. Middle-action budgets are rescaled (10 s → 30 s) to preserve the same fraction of the reference budget (1/6) as Stage A.
- Predictor: re-trained on the Stage B data with the Stage A feature set unchanged. No threshold or hypothesis revision.

Homberger 400 and above is out of scope. PyVRP's published benchmark practice uses 2-hour budgets at the 1000-customer scale; that is outside this project's compute envelope at the full instance pool.

## 6. Perturbation grids

Sixteen perturbations per instance, organised into four families of four perturbations each. The grid is the `soft_grid` defined in `prereg/vrptw_perturbation_pilot_v2_report.md` §12.1 and validated against the v2 pilot data, the 18-instance scale-check, and the 18-instance expanded-action scale-check.

The perturbation design's goal — variation that does not collapse to a small number of trivial rules — is preserved via two mechanisms: (a) magnitudes that span a wide enough range to produce easy/medium/hard cases per family (verified across all four claim families at 18 instances, see `prereg/vrptw_scale_check_18_expanded_actions_report.md` §6), and (b) structural variation across perturbations within a family (e.g., TRAVEL_TIME varies by *which* customer subset is affected, not just by magnitude).

The baseline solution S (PyVRP 60 s seed=1 on the unperturbed instance) is computed once per instance and used to seed all baseline-aware selectors. The baseline cache is keyed by `(instance_id, seed, time_limit_seconds, pyvrp_version)` and stored at `data/vrptw_baselines/{instance_id}.json`.

All distance, duration, time-window, and service-time values are multiplied by **10** (the SCALING_FACTOR) before being handed to PyVRP, which requires integer inputs. All absolute time/distance numbers in the parquet are in these ×10 units; relative losses (OBJ, STRUCT, SCHEDULE) are scale-invariant.

### 6.1 Family TRAVEL_TIME: duration-matrix inflation (4 perturbations)

The duration matrix is multiplied on arcs touching the affected customer subset. The distance matrix is unchanged. (This is the source of the asymmetry between distance-only and generalised OBJ on TT cells: see §9.1.)

| ID | selector | multiplier |
|---|---|---|
| TT_1 | baseline route with highest total waiting | ×1.05 |
| TT_2 | baseline route with lowest min slack-to-tw_late | ×1.10 |
| TT_3 | densest customer quartile (k-NN spread) | ×1.20 |
| TT_4 | farthest-from-depot customer quartile | ×1.30 |

### 6.2 Family TIME_WINDOW: customer window edits (4 perturbations)

Customer time windows are tightened or shifted on the affected subset. All edits clip to the depot horizon and enforce `tw_early < tw_late`; collapses fall back to a 1-unit window.

| ID | selector | edit |
|---|---|---|
| TW_1 | route with highest mean slack | tighten 5% around midpoint |
| TW_2 | route with lowest mean slack | tighten 10% around midpoint |
| TW_3 | final third of every baseline route | shift earlier by 5% of width |
| TW_4 | first third of every baseline route | shift later by 5% of width |

### 6.3 Family SERVICE_TIME: service-duration inflation (4 perturbations)

Customer service durations are multiplied on the affected subset.

| ID | selector | multiplier |
|---|---|---|
| ST_1 | route with highest total waiting | ×1.05 |
| ST_2 | route with lowest min slack | ×1.10 |
| ST_3 | densest customer quartile | ×1.25 |
| ST_4 | top-demand quartile | ×1.50 |

### 6.4 Family ORDER_CHANGE: customer insertion (4 perturbations)

New customers are added with deterministically generated coordinates and demands. Demand is anchored to a fraction of vehicle capacity; tight-window variants use 40% of typical Solomon window width (`SOFT_TIGHT_WINDOW_WIDTH_FRACTION = 0.40`); flexible variants use the depot horizon.

| ID | n new | selector | demand | window |
|---|---|---|---|---|
| OC_1 | 1 | near highest-slack route | 0.05 × capacity | flexible |
| OC_2 | 1 | near lowest-slack route | 0.05 × capacity | tight (40% width) |
| OC_3 | 3 | near densest region | 0.15 × capacity | flexible |
| OC_4 | 3 | near lowest-slack route | 0.20 × capacity | tight (40% width) |

Per-customer demand within an insertion is `total_inserted_demand / n_new_customers` with a floor of 1. Insertion locations use stable hashing for reproducibility:

```python
import hashlib
seed_int = int(hashlib.sha256(f"{instance_id}_{perturbation_id}".encode()).hexdigest()[:16], 16) % (2**32)
rng = numpy.random.default_rng(seed_int)
```

(Same scheme as v0.5 §6.4; per-`(instance, perturbation_id)` seeding so that OC_1/OC_2/OC_3/OC_4 draw distinct RNG state.)

### 6.5 Total per instance

4 + 4 + 4 + 4 = 16 perturbations per instance. Across 56 instances: 896 perturbed cells. Across 4 claim families: 3,584 evaluation cells. Across the action portfolio: 3,808 wide rows (12 non-OC perturbations × 4 actions + 4 OC perturbations × 5 actions = 68 wide rows per instance).

## 7. Action set

Five actions are evaluated per cell. The action set is a **portfolio**, not a ladder (see §1). Two of the five are "cheap actions" selected by `cheap_action_for_family`: non-OC families use `reuse_direct`; ORDER_CHANGE uses `local_repair_insert`. The remaining three (`construct_feasible`, `pyvrp_10s`, `pyvrp_60s_reference`) are the *middle and reference rungs* that the deployable policy can choose between when the cheap action is insufficient.

| tier index | tier label | action | role | runtime budget |
|---|---|---|---|---|
| 0 | `0_reuse` | `reuse_direct` | score baseline routes unchanged under the perturbed instance | ~0.001 s |
| 1 | `1_repair` | `local_repair_insert` | OC-only: cheapest-feasible-insertion of new customers into existing routes (no new vehicles opened) | ~0.3 s |
| 2 | `2_construct` | `construct_feasible` | deterministic build-from-scratch insertion heuristic; ignores baseline; **specialist for feasibility, not for quality** | ~0.1 s |
| 3 | `3_pyvrp_10s` | `pyvrp_10s` | PyVRP metaheuristic, seed=1, 10 s budget | 10 s |
| 4 | `4_pyvrp_60s_reference` | `pyvrp_60s_reference` | materialised from reference seed 1 (60 s budget); no extra solve | 60 s (already paid by reference) |

`construct_feasible` (renamed from `cheap_fresh_construct` in v1.0 for accuracy: the 18-instance scale-check shows 98% PLAN_VALIDITY-easy with 0% OBJ-easy / 0% STRUCT-easy, so it is a feasibility specialist, not a quality solver) ignores the baseline and rebuilds from scratch using the customer ordering `(tw_late asc, tw_early asc, id asc)`. Lexicographic acceptance: feasible candidates first, then `(obj, n_routes, route_idx, pos)`; infeasible candidates fall back to `(time_warp, obj, n_routes, route_idx, pos)`. The implementation reuses a prebuilt `pyvrp.ProblemData` for each instance to evaluate candidate placements via `pyvrp.Solution(data, routes)` directly, which gives a ~50× speedup over rebuilding `ProblemData` per candidate while preserving the heuristic bit-identically.

`pyvrp_60s_reference` is **not a runnable action**. It is materialised from the reference-seed-1 solve so the wide table has a row at the top of the portfolio without paying for a redundant solve. `action_runtime_s` for this row uses the reference's wall-clock; `action_seed = 1`; `action_solver_time_limit_s = 60.0`.

Empirical action characterisations (`prereg/vrptw_scale_check_18_expanded_actions_report.md`, n = 1,224 wide rows, 18 instances × 16 perturbations × 4–5 actions per cell):

| action | OBJ easy | PV easy | STRUCT easy | SCHEDULE easy | mean runtime |
|---|---:|---:|---:|---:|---:|
| `reuse_direct` | 88.0% | 29.9% | 62.5% | 47.6% | 0.002 s |
| `local_repair_insert` | 85.7% | 50.0% | 48.6% | 54.3% | 0.291 s |
| `construct_feasible` | 0.0% | 98.3% | 0.0% | 7.8% | 0.122 s |
| `pyvrp_10s` | 100.0% | 98.3% | 86.6% | 89.8% | 10.008 s |
| `pyvrp_60s_reference` | 100.0% | 98.3% | 100.0% | 100.0% | 60.008 s |

These rates demonstrate that the actions occupy distinct operational roles, not points on a single quality axis: `construct_feasible` is the only sub-second action that recovers PLAN_VALIDITY on coverage-failure cells (it rescued 161/166 cheap-action PV-hard cells in the 18-instance run); `pyvrp_10s` is the cheapest action that achieves OBJ-easy at near-reference rates; the 60 s reference adds STRUCT/SCHEDULE refinement that 10 s cannot reach.

PyVRP version is locked at 0.13.3 (the version used in every probe and scale-check cited above; see `requirements.txt`). Bug-fix patches within 0.13.x are permitted. Any minor-version (0.14.x) or major-version bump invalidates the benchmark and requires rebuilding from scratch.

## 8. Reference protocol

### 8.1 Primary reference

PyVRP 60 s with seed=1 on the perturbed instance. The reference is computed on every one of the 896 `(instance, perturbation)` cells. The seed-1 reference also materialises the `pyvrp_60s_reference` action row in the wide table (§7).

### 8.2 Full multi-seed audit (every cell, not a subset)

Unlike v0.5, which audited a 20% subset of `(instance, perturbation)` pairs at seeds 2 and 3, **v1.0 runs PyVRP 60 s at seeds 2 and 3 on every cell**. Three reference solves per cell, 56 × 16 × 3 = 2,688 solves total.

Rationale: VRPTW's reference structural-instability rate (18-instance expanded-action scale-check: `reference_struct_unstable = 0.194`) is much lower than CVRP's (`≈ 0.926`), but it is still meaningful — almost 1 in 5 cells has a non-trivial ARI gap between seeds even at the 60 s budget. Under v0.5's 20% audit, four-fifths of cells would have no per-cell structural-stability classification; that flag matters for v1.0 because the predictor's STRUCT and SCHEDULE training partitions filter on it (see §13.1). Running seeds 2/3 on every cell gives per-cell stability labels at the cost of a 3× reference-solve budget (44.8 vs 14.9 CPU-hours), which the project's compute envelope absorbs (see §5.1 compute estimate).

For each cell, three stability checks are computed:

```
reference_obj_unstable    = (max_obj - min_obj) / min_obj > 0.02
reference_struct_unstable = min over (i,j) of ARI(seed_i_assignment, seed_j_assignment) < 0.90
                            UNDEFINED  if no seed is feasible (v1.1 amendment)
reference_ari_min         = min pairwise ARI across seeds 1, 2, 3
```

The objective check matches v0.5. The structure check matches v0.5 *except* for the v1.1 amendment: when no reference seed is feasible (the §8.3 fleet-exhaustion case), `reference_struct_unstable` is **undefined** rather than computed from PyVRP's penalty-bounded "best" partitions. Cells in the undefined state are excluded from both numerator and denominator of the §12.3 rate, paralleling the §8.3 n/a policy that already excludes them from STRUCT/SCHEDULE training. v0.5's `reference_rank_unstable` is removed (RANK is excluded from v1.0; see §3.2).

### 8.3 Fleet-exhaustion cells (n/a policy)

On a small fraction of cells the perturbed instance is infeasible at the 60 s budget across all three seeds (the 18-instance expanded-action scale-check observed 22 such wide rows = 5 cells × 4–5 actions; the 5 cells are R101 × TT_4, R102 × TT_4, R103 × TT_4, RC102 × OC_2, RC102 × OC_4). These are real fleet-exhaustion infeasibilities at the locked Solomon-100 vehicle count, not budget shortfalls: extending the time budget does not rescue them, and the scale-check's `pyvrp_60s_reference` recovers 0 of 5.

The n/a policy:

- `reference_failure_kind = "all_infeasible"` on these cells.
- For OBJ, STRUCT, SCHEDULE: `band = "n/a"`. These cells are *excluded from the predictor's training partition* for OBJ/STRUCT/SCHEDULE.
- For PLAN_VALIDITY: `band = "hard"` (the cell is infeasible by construction). These cells are *retained in the predictor's training partition* for PLAN_VALIDITY — the PV target is correctly defined and informative on them.

Estimated Stage A all-infeasible cell count: scaling the 18-instance rate of 5 / 288 = 1.74% to 56 instances projects ≈10–18 cells. The §12.4 verification check requires this rate to remain below 5% (a hard cap; if exceeded, the time budget is escalated via the §12.5 procedure).

### 8.4 Reference re-collection condition

If the `reference_struct_unstable` rate exceeds **25%** on the full Stage A pool, the affected cells are re-collected under a scaled reference protocol (PyVRP 120 s, seeds 1/2/3). The 25% threshold is calibrated against the 18-instance scale-check's 19.4% rate plus a 5.6-pp margin against the Phase-1 unperturbed-instance noise floor of 16.7%; rationale in §12.3. The objective-instability threshold for the same re-collection trigger is 5%, matching v0.5.

Per the v1.1 amendment to §8.2, the rate's numerator counts cells where `reference_struct_unstable == True`, and its denominator counts cells where `reference_struct_unstable` is defined (i.e., at least one seed is feasible). Cells with no feasible reference on any seed contribute to neither and are governed by the §8.3 n/a policy.

This is the only condition under which the reference protocol may be amended without a full lock-version bump.

## 9. Loss metrics and bands

Every wide row has a primary loss value for each of the four claim families. The cell's primary claim family controls the long-table row a row contributes to; storing all four allows aggregate analyses across claim families on the same data.

Bands are determined by thresholds applied to losses. Thresholds are locked here.

### 9.1 Objective loss (distance, with generalised diagnostic)

Two OBJ variants are computed and stored. The **distance-only** variant is the primary loss feeding `band_obj_distance`; the **generalised** variant (`distance + 0.1 × duration`) is a diagnostic supplement reported in parallel for cells where distance is silent.

```
loss_obj_distance     = |action_dist - reference_dist| / reference_dist
loss_obj_generalized  = |action_gen - reference_gen| / reference_gen
   where gen = distance + 0.1 × duration
```

Bands (identical for both variants, applied separately):
- `easy`:   `loss ≤ 0.05`
- `medium`: `0.05 < loss ≤ 0.15`
- `hard`:   `loss > 0.15`

The 5%/15% cutoffs match v0.5 and reflect operational tolerances reported in commercial routing tools. The thresholds are locked.

**Why both variants are kept, not just one.** TRAVEL_TIME and SERVICE_TIME perturbations modify the duration matrix only; the distance matrix is unchanged. On these families a `reuse_direct` action can produce identical distance to the reference (because the routes are unchanged) while the perturbation has materially shifted the schedule. The distance-only OBJ then reads as "easy" while the operational reality is "the plan now takes much longer." The generalised variant (α = 0.1 on duration) is the primary diagnostic for that decoupling. v0.5 §9.1 used distance-only because CVRP has no duration dimension. v1.0 reports both; neither is picked as canonical. The pre-registered predictor target is operational_sufficiency, which is band-driven on the *primary* (distance) OBJ loss; the generalised variant is descriptive.

PyVRP optimisation itself minimises distance only (`unit_distance_cost=1, unit_duration_cost=0`), so the reference is distance-optimal. The generalised cost is a post-hoc audit metric, not a re-optimisation target.

### 9.2 Plan-validity loss

```
loss_plan_validity = 0 if action_feasible else 1
```

`action_feasible = (capacity_violations == 0) ∧ (time_warp == 0) ∧ (num_missing_clients == 0)` under the perturbed instance.

Bands:
- `easy`: `loss_plan_validity == 0` (action's plan is fully feasible)
- `hard`: `loss_plan_validity == 1` (any of the three violations)

The label is informative on every action (see §3.2 PV semantic shift). There is no `medium` band.

`action_infeasibility_kind` is a categorical diagnostic, taking one of `{none, capacity, time_window, both, coverage}`. `coverage` is the v0.5-style spec extension for OC cells where the action's plan leaves inserted customers unserved (`num_missing_clients > 0` with capacity and TW satisfied).

### 9.3 Structure loss

```
loss_struct = 1 - ARI(action_assignment, reference_assignment)
```

ARI is computed treating each customer as a data point and its assigned route as its cluster label, on the *intersection* of customer sets (excluding any inserted customers absent from one side of the comparison). ARI handles the route-id permutation problem natively.

Bands (identical to v0.5):
- `easy`:   `loss_struct ≤ 0.10` (ARI ≥ 0.90)
- `medium`: `0.10 < loss_struct ≤ 0.30` (ARI ∈ [0.70, 0.90))
- `hard`:   `loss_struct > 0.30` (ARI < 0.70)

### 9.4 Schedule loss (affected-p90)

```
affected_customers = (perturbed customer set) ∖ (inserted customers for OC cells)
                     # fallback: all common customers if affected is empty
loss_schedule = p90 over c in affected_customers of:
                |start_service_action(c) - start_service_reference(c)| / depot_horizon
```

Bands:
- `easy`:   `loss_schedule ≤ 0.02`
- `medium`: `0.02 < loss_schedule ≤ 0.05`
- `hard`:   `loss_schedule > 0.05`

Thresholds are calibrated against the empirical affected-p90 distribution on the soft_grid (`prereg/vrptw_perturbation_pilot_v2_report.md` §6: median 0.0214, p90 0.0645 on the 240-row pilot; `prereg/vrptw_scale_check_18_report.md` §9: median 0.0214, p90 0.2415 on the 360-row scale-check), which gives the three-way `easy / medium / hard` spread of roughly 49% / 25% / 24% reported in the 18-instance scale-check.

A diagnostic-only `loss_schedule_global_median` (the v1-style "median over all common customers" definition) is computed and stored but does not feed `band_schedule`. The v1 definition was inactive (0 / 96 hard cells in the v1 pilot — see `prereg/vrptw_perturbation_pilot_report.md`).

### 9.5 Operational validity flag

The per-action operational validity flag is `action_feasible = capacity ∧ TW ∧ coverage`, computed independently of loss bands. It enters operational sufficiency for OBJ (per §3.3) and is reported as a standalone diagnostic on all claim families.

`action_valid` mirrors `action_feasible` on every action including `pyvrp_60s_reference` (whose feasibility is the reference's own feasibility under the perturbed instance; see §8.3 for the fleet-exhaustion case).

## 10. Cross-validation protocol

### 10.1 Primary CV: leave-one-instance-out (LOIO)

For each of the 56 instances, train on the cells of the other 55 and evaluate on the held-out instance. All 56 folds are computed; metrics are reported as the mean across folds with bootstrap 95% confidence intervals over the 56 fold-level estimates.

No row-level random splitting. Random splits would leak instance-level structure into the test set and inflate predictor performance. LOIO is the only valid split for this benchmark and is locked.

PLAN_VALIDITY cells are *retained* in LOIO training (unlike v0.5, where they were excluded as the positive-control family). LOIO is computed on the **3,584 evaluation cells** (56 instances × 16 perturbations × 4 claim families) minus the all-infeasible cells from §8.3 for OBJ/STRUCT/SCHEDULE only (PV cells retained even on all-infeasible cells, with `band = hard`).

### 10.2 Secondary stress test: leave-one-perturbation-family-out (LOPO)

For each of the 4 perturbation families, train on cells from the other 3 and evaluate on the held-out family. This 4-fold split tests whether the predictor generalises across perturbation types or only within them.

LOPO is reported as a sensitivity analysis. The headline numbers are LOIO.

### 10.3 No model selection on test data

Hyperparameters for the predictor (Section 13) are tuned on Stage A training folds via nested CV, never on test folds. The hyperparameter grid for each model class is locked in Section 13.

## 11. Baseline policies

The learned predictor must beat these baselines. Baselines are evaluated under the same LOIO protocol.

- **B0_random.** Predict operational sufficiency uniformly at random.

- **B1_majority_class.** Predict the modal label across all training cells (constant prediction).

- **B2_claim_family_only.** Rule depending only on claim family. Predict the per-family majority class from the training fold (e.g., if PV-easy is the modal label in the training fold for the PV claim, predict easy on the test fold's PV cells). Tests how much signal lives in claim family alone.

- **B3_feasibility_gate.** B2 plus an additional rule: if the baseline solution S is infeasible under the perturbed instance (the deterministic check on the unperturbed routes scored under the perturbation), predict not sufficient regardless of claim family. Tests the marginal value of the cheapest pre-recompute feasibility check.

- **B4_rule_policy.** Hand-written if-then rules with no fitting. Specifically:

```
if claim_family == OBJ and reuse_feasible and reuse_obj_delta_pct < 0.05:
    predict sufficient
elif claim_family == OBJ and not reuse_feasible:
    predict not sufficient
elif claim_family == PLAN_VALIDITY:
    predict sufficient if reuse_feasible else not sufficient
elif claim_family == STRUCT and perturbation_family in {TRAVEL_TIME, SERVICE_TIME}:
    # TT/ST mostly leave routes intact at small magnitudes
    predict sufficient
elif claim_family == SCHEDULE and reuse_feasible and reuse_schedule_shift_p90 < 0.02:
    predict sufficient
else:
    predict not sufficient
```

The rules are locked at this version and frozen before any predictor training. They represent what an analyst would write after reading the 18-instance scale-check, with no model fitting.

- **B5_shallow_tree.** A learned decision tree using all observable features (claim family, perturbation family, perturbation magnitude, baseline feasibility, baseline overload counts, baseline time-warp, reuse objective delta under perturbation, reuse schedule shift, affected min slack, affected total wait). Fitted on Stage A training folds via `sklearn.tree.DecisionTreeClassifier` with `max_depth=4` and `min_samples_leaf=20`, hyperparameters fixed at lock time.

B4 is the true rule baseline (no fitting); B5 is the simplest learned interpretable model. The learned predictor (Section 13) is the next tier above B5, using the same feature set with more flexible model classes and tuned hyperparameters.

The **oracle** policy is included for context: it predicts the true label perfectly. The gap between oracle and the learned predictor is the room for improvement; the gap between B5 and the learned predictor is the marginal value of additional model flexibility over a shallow tree; the gap between B4 and B5 is the marginal value of any learning over hand-crafted rules.

## 12. Verification step (post-Stage A, pre-predictor training)

After Stage A data is collected and *before* any predictor is trained, the following verification is run on the 3,584 evaluation cells.

### 12.1 Non-degenerate label distribution per cell

For each `(claim_family × perturbation_family)` block, the operational sufficiency label distribution must satisfy:

```
0.10 ≤ P(operational_sufficiency = 1 | block) ≤ 0.90
```

Sixteen blocks fall under this check: `{OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE} × {TRAVEL_TIME, TIME_WINDOW, SERVICE_TIME, ORDER_CHANGE}`. Unlike v0.5, PLAN_VALIDITY is *included* (the positive-control role is eliminated under v1.0; see §3.2).

The thresholds are **locked at `[0.10, 0.90]`**, carried over from v0.5 §12.1. The 18-instance expanded-action data has the cheap-action operational-sufficiency easy-rate at 88% (OBJ), 30% (PV), 63% (STRUCT), 48% (SCHEDULE) aggregated across all four perturbation families, which sits inside `[0.10, 0.90]` on every claim family at the cheap-action level. The PV aggregate is in-range but on the lower edge (30%), so per-block PV figures may be tighter than the aggregate suggests; the per-block check at Stage A is the real test, and the §12.6 escalation rules apply if any of the 16 blocks falls outside the bracket.

### 12.2 Cross-validation feasibility

For each of the 56 LOIO folds, the test fold (single instance, 16 perturbations × 4 claim families = 64 evaluation cells, minus any all-infeasible n/a cells) must contain at least one positive and one negative example for at least three of the four claim families. If any fold is degenerate, the failure is routed through the §12.5 deterministic revision procedure, which (under v1.0) does *not* include an instance-replacement clause — the Solomon-100 pool has no additional candidates to draw from. Instead, the §12.5 procedure for §12.2 failure is to escalate the offending perturbation family's grid via Appendix A and re-run the affected cells.

The §12.2 fold-feasibility threshold (three of four claim families instead of v0.5's two of three) is calibrated against v1.0's four-claim-family stratification.

### 12.3 Reference stability

As specified in §8.4, the unstable-cell rates on the two stability checks (objective and structure) must each remain below the locked thresholds. If exceeded, the affected cells are re-collected under the scaled reference protocol (PyVRP 120 s, seeds 1/2/3).

**Objective-stability threshold:** 5% (matches v0.5).

**Structure-stability threshold:** locked at **25%**.

The structure-stability rate's numerator is the count of cells with `reference_struct_unstable == True`; its denominator is the count of cells where `reference_struct_unstable` is **defined** (per the v1.1 amendment to §8.2: defined whenever at least one of the three reference seeds is feasible). Cells with no feasible seed are excluded from both — they are owned by the §8.3 n/a policy, which already excludes them from STRUCT/SCHEDULE training (`band = "n/a"`). The 25% threshold itself is unchanged from v1.0; only the rate's definition is clarified.

Rationale: CVRP's 5% threshold (v0.5 §12.3) was calibrated against CVRP's solver noise floor, which is essentially zero on unperturbed Uchoa-X. VRPTW's unperturbed solver-noise floor is already 16.7% on the Phase-1 probe (`prereg/vrptw_probe_phase1_report.md`), and the 18-instance expanded-action perturbed rate is 19.4% (`prereg/vrptw_scale_check_18_expanded_actions_report.md` §5). A 5% gate on VRPTW would re-collect a large fraction of cells whose structural disagreement reflects the natural PyVRP-on-VRPTW partition multimodality rather than a real reference failure; the re-collection budget would be spent without changing the underlying signal-to-noise ratio. A 25% gate (the 18-instance perturbed rate plus a 5.6-pp margin) triggers re-collection only when perturbed-instance noise clearly exceeds the unperturbed noise floor by a meaningful amount.

The STRUCT and SCHEDULE predictor training partitions are filtered to the reference-structurally-stable subset (cells with `reference_struct_unstable == False`), which the 18-instance data projects at ~80.6% of cells. OBJ and PLAN_VALIDITY training partitions use the full set minus the §8.3 fleet-exhaustion n/a cells (PLAN_VALIDITY retains those at `band = hard`).

### 12.4 Reference-failure rate

The all-infeasible-cell rate (`reference_failure_kind == "all_infeasible"`) must remain below **5%** of the 896 `(instance, perturbation)` cells. If exceeded, the reference time budget is escalated to 120 s (one revision pass, applied only to the affected cells); if the rate remains above 5% after the escalation, the affected cells are dropped from Stage A (PLAN_VALIDITY retained, OBJ/STRUCT/SCHEDULE excluded), and the drop is reported in the verification record.

The 5% threshold is calibrated against the 18-instance scale-check rate of 1.8% (22 / 1,224 wide rows from 5 distinct cells), which projects to ~16 cells at 56 instances.

### 12.5 Feasibility decoupling diagnostic

To verify that the benchmark exposes the failure mode it was designed to expose, compute:

```
P(band_obj_distance == 'easy' AND action_feasible == False
  | claim_family == OBJ, action == reuse_direct)
```

This quantity should remain above **0.20** on the full Stage A pool. The 18-instance scale-check measures this directly: among `reuse_direct × OBJ` rows, 88.0% are OBJ-easy and 29.9% are PV-easy, so the OBJ-easy-but-infeasible fraction is approximately `0.880 × (1 − 0.299 / 0.880) = 0.580`. The 0.20 threshold has substantial margin against this baseline. Falling below indicates the perturbation grid has lost the decoupling phenomenon and the grid is revised under the §12.6 procedure.

(This is the same diagnostic as v0.5 §12.4, rephrased for v1.0's PV semantics and labelled with the actual `reuse_direct` action.)

### 12.6 Revision procedure (deterministic)

If any check in §12.1–12.5 fails, exactly one revision pass is permitted before Stage A data must be re-collected. The revision menu is in Appendix A and is fully deterministic: the failure mode dictates the substitution.

- **§12.1 failure (label distribution outside [0.10, 0.90]).** The offending block is mapped to the next severity level for its perturbation family (Appendix A). Increase severity if the block is too positive; decrease if too negative. Only one substitution per block is allowed.

- **§12.2 failure (degenerate fold).** Under v1.0, instance replacement is not available (the Solomon-100 pool is the full eligible set with no candidates outside it). The failure routes to the perturbation grid: identify the perturbation family whose label distribution drives the fold degeneracy and apply the Appendix A revision for that family. If no clean attribution exists, halt and document.

- **§12.3 failure (reference instability above threshold).** Re-collect the affected cells under PyVRP 120 s with full multi-seed audit. No threshold change is permitted.

- **§12.4 failure (reference-failure rate above 5%).** Escalate the time budget to 120 s on the affected cells (one pass). If the rate remains above 5%, drop the affected cells from Stage A and document.

- **§12.5 failure (decoupling diagnostic below 0.20).** This is a structural failure of the benchmark design. Do not attempt to fix in v1.x. Halt, document the result as a structural finding, and reconsider whether the framework's premises hold on the chosen test bed.

The thresholds, definitions, baselines, and hypotheses in Sections 3, 9, 11, and 14 may not be adjusted under any verification failure. The grid is the design knob; the constructs are not.

## 13. Predictor specifications

The learned sufficiency predictor is the ML contribution and the recruiter-facing artifact built on top of the benchmark.

### 13.1 Target

Primary target: `operational_sufficiency` (binary), evaluated on all four claim families (3,584 training cells in Stage A, minus all-infeasible n/a cells for OBJ/STRUCT/SCHEDULE).

The predictor sees per-cell features and predicts whether the cheap action (`reuse_direct` on non-OC, `local_repair_insert` on OC) will produce a sufficient answer for the cell's claim family. Under operational deployment the policy uses the predictor's output to choose between the cheap action and an escalation to a higher-tier action (see §14.2 deployable policy).

Secondary targets:
- `numerical_sufficiency` (diagnostic).
- `structural_sufficiency` = STRUCT-easy AND SCHEDULE-easy (claim-family-specific descriptive).

Predictor training is restricted to the reference-stability-passing subset for STRUCT and SCHEDULE targets (the partition depends on §12.3's locked threshold); OBJ and PV training use the full set minus n/a cells.

### 13.2 Feature set

Features must be computable *before* recomputation — that is, from the baseline solution S, the perturbation specification, and a single fixed-solution evaluation. PyVRP outputs on the perturbed instance are labels and may not enter the feature set.

The feature set is **locked** at the list below, adapted from the 18-instance run's `src/vrp_copilot_bench/vrptw/features.py` module. The module is leak-free by construction (no PyVRP outputs on the perturbed instance enter the feature set). Allowed features (locked):

```
# Instance features (computed from unperturbed instance)
n_customers,                              # always 100 on Solomon-100; kept for forward-compat
n_routes_baseline,                        # PyVRP 60s seed=1 route count on unperturbed instance
depot_x, depot_y,
mean_customer_demand, std_customer_demand,
mean_pairwise_distance, std_pairwise_distance,
demand_capacity_ratio,                    # total_demand / (n_routes * capacity)
horizon_length,                           # depot_horizon (×10 PyVRP units)
mean_tw_width, std_tw_width,              # customer time-window widths
mean_service_time,                        # average service duration

# Baseline-solution features (computed from S on unperturbed instance)
baseline_total_distance,
baseline_total_duration,
baseline_total_wait,
mean_route_load, max_route_load, std_route_load,
mean_route_cost, std_route_cost,
mean_route_wait, std_route_wait,
mean_route_slack,                         # min(tw_late - start_service) per visit, averaged
min_route_min_slack,                      # smallest slack across all visits in S
n_near_full_routes,                       # load > 0.9 × capacity
n_full_routes,                            # load == capacity
route_load_imbalance,                     # (max - min) / capacity

# Perturbation features
perturbation_family (one-hot, 4 levels),
perturbation_magnitude (numeric, in family-specific units),
n_affected_customers,
affected_demand_share,
affected_route_share,
affected_min_slack,                       # min slack among affected customers (in S)
affected_total_wait,                      # total wait time among affected customers (in S)

# Cheap-action evaluation features (from reuse_direct or local_repair_insert,
#  whichever is the family's cheap action)
cheap_action_feasible (bool),
cheap_action_n_overload,
cheap_action_max_overload_fraction,
cheap_action_time_warp,
cheap_action_num_missing_clients,
cheap_action_obj_delta_pct,               # (cheap_obj - baseline_obj) / baseline_obj
cheap_action_generalized_delta_pct,
cheap_action_schedule_shift_p90,          # affected-p90 of |start_action - start_S|
cheap_action_runtime_s,

# Claim features
claim_family (one-hot, 4 levels: OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE)
```

Total: ~35 features. Final feature list is in `prereg/feature_spec_vrptw.yaml`, to be committed and locked alongside v1.0.

### 13.3 Model classes

In order of priority:

- **Logistic regression** with L2 regularisation. Hyperparameter grid: `C ∈ {0.01, 0.1, 1.0, 10.0}`, fitted on standardised features. Tuned by nested 5-fold CV inside training folds. Primary model.

- **Decision tree.** `max_depth ∈ {3, 4, 5, 6}`, `min_samples_leaf ∈ {10, 20, 50}`. Tuned by nested 5-fold CV. Reports human-readable rules.

- **Gradient boosting** (LightGBM). `n_estimators ∈ {50, 100, 200}`, `max_depth ∈ {3, 4, 5}`, `learning_rate ∈ {0.05, 0.1}`. Robustness check; not the headline model.

The "primary" model is logistic regression. Decision tree provides interpretability. Gradient boosting checks whether nonlinearities exist that the linear model misses.

### 13.4 Calibration

Predicted probabilities are calibrated via Platt scaling fit on the inner CV folds. Calibration is reported as expected calibration error (ECE) on the held-out fold.

## 14. Headline metrics and hypotheses

### 14.1 Predictor metrics

For each model class, reported under LOIO:

- **AUROC** on operational_sufficiency. Headline metric.
- **Precision and recall** at the threshold that maximises F1 in the inner CV.
- **Unsafe reuse rate** = `P(predicted_sufficient = 1 | true_sufficient = 0)`. The dangerous error.
- **False recompute rate** = `P(predicted_sufficient = 0 | true_sufficient = 1)`. The wasteful error.
- **ECE** for calibration.

All metrics reported with bootstrap 95% CIs over the 56 LOIO folds.

### 14.2 Policy metrics (compute-aware)

Two policies are reported. The first is deployable; the second is an oracle for upper-bound analysis.

**Deployable policy (portfolio-aware):**

```
if claim_family == PLAN_VALIDITY and cheap_action_feasible:
    use cheap_action  # reuse on non-OC; local_repair_insert on OC
elif predicted_operational_sufficient and cheap_action_feasible:
    use cheap_action
elif claim_family == PLAN_VALIDITY and not cheap_action_feasible:
    # PV is the family construct_feasible was designed for; use it before pyvrp_10s
    use construct_feasible
elif λ < λ_low_threshold:
    use pyvrp_60s_reference   # quality matters more than compute
elif λ < λ_high_threshold:
    use pyvrp_10s             # middle of the portfolio
else:
    use construct_feasible    # cheapest feasibility specialist; OBJ/STRUCT loss accepted
```

The deployable policy uses only information available at decision time: claim_family, the predictor's output, the deterministic cheap-action feasibility check, and the compute-cost weight λ. It does not use loss values, which are only knowable after running the reference.

**Oracle policy** (for upper-bound analysis only):

```
choose action a minimising observed_loss(a) + λ × runtime(a)
```

The oracle has access to all action losses and runtimes, computed during the benchmark. It represents the best achievable loss-runtime tradeoff if the system had perfect foresight over the portfolio.

Reported metrics for both policies:

- **Pareto curves** of mean loss vs mean runtime, swept over `λ ∈ {0, 1e-4, 1e-3, 1e-2, 1e-1, 1, 10}`.
- **Compute saved at fixed loss budget**: for loss budget `L ∈ {0.05, 0.10, 0.20}`, mean runtime under the policy compared to always-`pyvrp_60s_reference`.
- **Loss incurred at fixed compute budget**: for runtime budget `T ∈ {0.1 s, 1 s, 10 s mean per cell}`, the mean loss.

The headline comparison is the deployable policy vs fixed-action baselines (always-cheap, always-`construct_feasible`, always-`pyvrp_10s`, always-`pyvrp_60s_reference`). The oracle bounds the achievable region.

### 14.3 LLM-in-the-loop closing experiment

Forty natural-language prompts spanning the four claim families (≥ 10 per family — OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE) are routed through the full pipeline:

```
prompt → claim-family classifier → sufficiency predictor → action policy → answer generator
```

Each generated answer is scored along all three axes:

- **Faithfulness:** does the answer correctly report the action's output? Manual grading by the candidate; rubric in `closing/faithfulness_rubric_vrptw.md`.
- **Sufficiency:** action's loss vs reference, computed automatically.
- **Operational validity:** action's feasibility flag, computed automatically.

Per-axis pass rates across the 40 prompts are reported, broken down by claim family.

### 14.4 Hypotheses and pass/fail criteria

Pre-specified hypotheses, each falsifiable. The thesis presents results regardless of whether they confirm or falsify; framing adjusts accordingly.

v1.0 adapts v0.5's H1a / H1b / H2 / H3 / H4 to the four-claim-family and portfolio framing. Expected effect sizes are pegged against the 18-instance scale-check where the relevant signal already appears, and the wordings below are **locked**.

**H1a (primary, learned vs rules).** The learned predictor (logistic regression) achieves AUROC on operational sufficiency that exceeds B4_rule_policy by at least **0.05** in LOIO, with the lower bound of the bootstrap 95% CI above zero.

Expected effect size at 56 instances. The CVRP data-grounding pilot on Phase 3 cells produced a logistic-regression AUROC of 0.878 vs 0.754 for claim-only (gap 0.124). The 18-instance VRPTW expanded-action data has not been fit with a predictor yet, so the +0.05 expectation is conservative; the four-claim-family stratification provides additional discriminative signal that the three-family CVRP setup did not.

- *Confirmed:* the learned predictor is the centerpiece of the ML chapter.
- *Falsified:* contribution shifts to "the rule baseline captures most of the signal at this dataset size; the sufficiency-decision surface admits compact rule-based descriptions."

**H1b (secondary, learned vs shallow tree).** The learned predictor matches or improves over B5_shallow_tree (AUROC delta ≥ 0 in LOIO, with the lower bound of the bootstrap 95% CI above −0.02).

Same intent as v0.5 H1b. Weaker test than H1a because B5 has access to the same feature set.

**H2 (claim-conditional sufficiency).** Operational sufficiency rates differ across claim families OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE (chi-square test, α = 0.05, Bonferroni-corrected for the four-way comparison).

Expected effect at 56 instances. The 18-instance scale-check produces cheap-action operational-sufficiency easy-rates of OBJ 88.0%, PV 29.9%, STRUCT 62.5%, SCHEDULE 47.6%. The OBJ/PV gap alone is 58 pp; chi-square will reject at any reasonable sample size.

- *Confirmed:* claim-conditional sufficiency is empirically established under VRPTW.
- *Falsified:* the conceptual contribution is weakened. Failure prompts re-examination of which dimension of conditioning matters.

**H3 (feasibility decoupling, VRPTW-specific).** Among cells with `band_obj_distance = easy` and `claim_family = OBJ`, the fraction with `action_feasible = 0` (computed on the cheap action) exceeds **0.20** in Stage A.

Expected effect at 56 instances. The 18-instance scale-check measures this at ~58% on `reuse_direct × OBJ` rows (see §12.5). The 0.20 threshold has substantial margin.

- *Confirmed:* the three-axis decomposition is empirically motivated on VRPTW.
- *Falsified:* the operational-validity axis is less informative than expected; reconsider the construct.

**H4 (portfolio policy dominates fixed actions).** The deployable policy strictly Pareto-dominates each fixed-action baseline (always-cheap, always-`construct_feasible`, always-`pyvrp_10s`, always-`pyvrp_60s_reference`) at some `λ` in the swept grid.

Expected effect at 56 instances. The 18-instance scale-check shows `construct_feasible` rescuing 161/166 cheap-action PV-hard cells at ~100× lower runtime than `pyvrp_10s`; a portfolio policy that routes PV-needs-rescue cells to `construct_feasible` and quality-needs cells to `pyvrp_10s` will dominate any fixed-action baseline on at least one λ.

- *Confirmed:* the systems contribution holds; the portfolio framing is empirically motivated.
- *Falsified:* the policy collapses to a single fixed action across the λ grid; result still reportable but contribution narrows.

**Negative-result clause.** If H1a falsifies (learned predictor does not beat rules), H2 confirms, H3 confirms, and H4 confirms, the thesis remains complete. The contributions become: (1) conceptual three-axis decomposition with empirical VRPTW support from H3; (2) empirical claim-conditional sufficiency from H2; (3) benchmark itself, released as artifact; (4) compute-aware portfolio policy from H4. The ML contribution becomes "interpretable rule-based sufficiency policies are within X AUROC of learned alternatives, indicating the decision surface admits compact rule-based descriptions on VRPTW." This outcome is anticipated and pre-defended.

## 15. What is locked vs what is flexible

To remove ambiguity at the time of execution.

**Locked at v1.0 (require versioned amendment to change):**

- All construct definitions in Section 3
- Schema in Section 4
- Instance selection procedure and the resulting list in Section 5
- Perturbation specifications in Section 6
- Action portfolio in Section 7
- Reference protocol in Section 8 (with the single exception in §8.4 and the §12.6 amendment door)
- Loss metrics, threshold values, and band cutoffs in Section 9
- CV protocol in Section 10
- Baseline policies in Section 11
- Verification checks and the deterministic revision procedure in Section 12
- Predictor target, feature set, and model classes in Section 13
- Hypotheses and pass/fail criteria in Section 14
- The revision menu in Appendix A

**Flexible (may change without amendment):**

- Code organisation, naming, refactoring within the schema
- PyVRP minor-version updates (bug fixes only)
- Visualisation and figure design
- Wording of natural-language prompts in the closing experiment, provided each prompt is unambiguously classifiable to its claim family
- Storage layout (Parquet → DuckDB → SQLite is fine; the schema is what matters)

**Forbidden post-lock:**

- Any change to thresholds in response to observed data
- Any change to perturbation magnitudes that has not gone through the §12.6 procedure
- Any change to the predictor feature set after seeing test-fold results
- Any change to baseline definitions
- Any change to hypothesis framing after observing results
- Any change to Appendix A's revision menu after the first verification result is observed

## 16. Locking procedure

The document is locked by:

1. Final review pass with all `[TBD]` markers resolved (see §19's resolution record).
2. Commit to the thesis git repository with message `"Lock VRPTW pre-registration v1.0 — no further changes without amendment"`.
3. Tag the commit `prereg-v1.0-vrptw`.
4. Record the commit hash and timestamp in the Status block at the top of this document at the next commit.
5. Optionally, deposit a copy on the Open Science Framework (OSF) for an external timestamp.
6. From this point forward, all benchmark code references this commit hash as the authoritative specification.

The CVRP track's `prereg-v1.0` tag (when applied to `PREREG_v0.5.md`'s lock version) and the VRPTW track's `prereg-v1.0-vrptw` tag are independent locks on independent benchmarks.

## 17. Amendment procedure

Amendments are bumps from v1.0 → v1.1, v1.2, etc. Each amendment includes:

- Section being amended.
- Old text and new text.
- Reason for the change, with explicit acknowledgment of the data state at the time (e.g., "before Stage A collection," "after Stage A verification, before predictor training").
- Why the change does not undermine the pre-registration's purpose.

Amendments are committed and tagged. The thesis cites both v1.0 and the current version, and any analyses run under earlier versions are clearly marked.

Amendments that affect the headline hypotheses (H1a, H1b, H2, H3, H4) require an explicit explanation in the thesis discussion. Amendments to thresholds in response to observed data are forbidden under any circumstance.

## 18. Glossary

- **Cell.** A tuple `(instance, perturbation, claim_family)`. Stage A has 3,584 cells.
- **Wide row.** A tuple `(instance, perturbation, action)`. Stage A has 3,808 wide rows (68 per instance: 12 non-OC × 4 actions + 4 OC × 5 actions).
- **Long claim row.** Wide row × claim_family. Stage A has 15,232 long rows.
- **Action.** One of the five candidate computational artifacts the copilot can use to answer a query.
- **Action portfolio.** The five actions framed as operational specialisations rather than a single monotonic quality ladder; see §7.
- **Cheap action.** `reuse_direct` for non-OC families; `local_repair_insert` for OC. The default action under the deployable policy when the predictor says "sufficient."
- **Middle action.** `construct_feasible` and `pyvrp_10s`. Sub-reference compute tiers the policy can escalate to.
- **Reference.** The output of `pyvrp_60s` on the perturbed instance with seed=1. The ground truth against which all other actions are compared. Also materialised as the `pyvrp_60s_reference` action row.
- **Loss.** Claim-family-specific error metric between an action's output and the reference. Lower is better.
- **Band.** Categorical version of loss: easy, medium, hard, or n/a.
- **Operational sufficiency.** Claim-dependent label. The primary predictor target on all four claim families.
- **PLAN_VALIDITY.** A claim family that asks "is this plan still valid?" — under v1.0 a substantive feasibility claim on every action, not v0.5's positive control.
- **SCHEDULE.** A claim family that asks "whose schedules slip?" — the v1.0 replacement for v0.5's RANK, defined as the affected-p90 of start-time shifts under the perturbation.
- **LOIO.** Leave-one-instance-out cross-validation. The primary CV protocol.
- **LOPO.** Leave-one-perturbation-family-out. The secondary stress test.
- **Operational validity.** An axis attached to every action: whether the action's output plan is feasible under the perturbed instance.
- **Fleet-exhaustion cell.** A cell where the perturbed instance is infeasible at the 60 s budget across all three seeds. OBJ/STRUCT/SCHEDULE bands set to n/a; PV band set to hard; cell excluded from the predictor's OBJ/STRUCT/SCHEDULE training partition but retained for PV.

## 19. Change log

- **v0.5 (2026-05-11, CVRP):** Locked CVRP pre-registration. See `prereg/PREREG_v0.5.md`. Stage A on Uchoa-X collected under that lock. The Stage A reference-stability check exposed that PyVRP's CVRP route partitions are highly multimodal across seeds (`struct_unstable ≈ 0.926`, `median ari_min ≈ 0.476`), which is the construct-level result that motivates v1.0 below.

- **v1.0 (2026-05-14, DRAFT, this document):** Fresh draft for VRPTW. **Not an amendment of v0.5.** v0.5 remains the locked specification for the CVRP track; v1.0 is a parallel, independent pre-registration covering VRPTW on Solomon-100.

  *Why a fresh draft rather than an amendment.* v0.5's Stage A produced a substantive empirical finding: the CVRP STRUCT metric measures PyVRP partition multimodality more than perturbation-induced structural change at the locked solver budget. That finding is the documented reason for the pivot to VRPTW, where the Phase 1 probe and the 18-instance scale-checks demonstrate that time-window constraints restore the structural construct's signal-to-noise to a usable level. A v0.6 amendment would have entangled the CVRP lock with the VRPTW reframing; a fresh v1.0 keeps each track's pre-registration internally consistent and citable on its own terms.

  *Substantive moves from v0.5 to v1.0.*

  - **Problem variant:** CVRP / Uchoa-X → VRPTW / Solomon-100. Defended in §2.1.
  - **Instance pool:** 68 stratified-sampled Uchoa-X → 56 full Solomon-100 pool. No sampling design needed; instance-replacement clause removed from §12.6.
  - **Claim families:** four (OBJ, PLAN_VALIDITY, STRUCT, RANK) → four (OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE). RANK excluded (multiple incompatible interpretations on VRPTW; see §3.2). SCHEDULE added with the pilot v2 affected-p90 definition.
  - **PLAN_VALIDITY semantics:** positive control (label = 1 by construction on reuse_direct, excluded from predictor training) → substantive feasibility claim (label informative on every action; included in predictor training).
  - **Action set:** five-action ladder (`reuse_direct`, `nearest_neighbor`, `clarke_wright`, `pyvrp_10s`, `pyvrp_60s`) → five-action portfolio (`reuse_direct`, `local_repair_insert`, `construct_feasible`, `pyvrp_10s`, `pyvrp_60s_reference`). `construct_feasible` is the renamed `cheap_fresh_construct` from the 18-instance scale-check, with the rename motivating the portfolio (rather than ladder) framing.
  - **Reference protocol:** 20% multi-seed audit sample → full multi-seed audit (every cell at seeds 1/2/3). Compute envelope absorbs the 3× cost.
  - **Perturbation grid:** CVRP-family grid (CAPACITY/DISTANCE/DEMAND/INSERTION) → VRPTW soft_grid (TRAVEL_TIME/TIME_WINDOW/SERVICE_TIME/ORDER_CHANGE), magnitudes calibrated against the v2 perturbation pilot.
  - **OBJ loss:** distance-only → distance-only primary + (distance + 0.1 × duration) generalised diagnostic. Primary feeds bands; generalised is descriptive.
  - **Verification:** five checks (§12.1 label distribution, §12.2 fold feasibility, §12.3 reference stability, §12.4 reference-failure rate, §12.5 feasibility decoupling). v0.5 had four; the reference-failure-rate check is new in v1.0 because fleet-exhaustion cells exist under VRPTW (and do not arise under CVRP).

  *Empirical basis for the locked thresholds.* Every locked threshold in this draft cites a probe report and parquet under `prereg/` and `data/probes/`:
  - Reference stability: `prereg/vrptw_probe_phase1_report.md` + `prereg/vrptw_scale_check_18_expanded_actions_report.md` §5.
  - Perturbation magnitudes: `prereg/vrptw_perturbation_pilot_v2_report.md` §4–10.
  - SCHEDULE thresholds: `prereg/vrptw_perturbation_pilot_v2_report.md` §6 + `prereg/vrptw_scale_check_18_report.md` §9.
  - Action characterisations: `prereg/vrptw_scale_check_18_expanded_actions_report.md` §6–10.
  - Feasibility decoupling diagnostic baseline: `prereg/vrptw_scale_check_18_expanded_actions_report.md` §6 + §8.
  - Fleet-exhaustion cell rate: `prereg/vrptw_scale_check_18_report.md` §4 + `prereg/vrptw_scale_check_18_expanded_actions_report.md` §4.

  *Lock-review resolutions (every `[TBD]` resolved before lock).*

  - §12.3 reference-stability threshold for STRUCT: **locked at 25%** (VRPTW-calibrated). Rationale and Option-A/Option-B trade-off recorded in §12.3.
  - §12.1 label-distribution thresholds: **locked at `[0.10, 0.90]`** (v0.5 carry-over). Per-block test at Stage A; §12.6 escalation applies on out-of-bracket blocks.
  - §13.2 feature list: **locked** at the ~35-feature set adapted from `src/vrp_copilot_bench/vrptw/features.py`. Final list to be committed alongside this prereg as `prereg/feature_spec_vrptw.yaml`.
  - §14.4 hypothesis wordings: **locked** as drafted; H1a / H1b / H2 / H3 / H4 phrasings adapted from v0.5 with the four-claim-family and portfolio framing folded in.

  *Thesis-narrative placement of the v0.5 track.* The CVRP work and its STRUCT finding are motivating prior work for the VRPTW prereg. Whether the CVRP track gets a thesis chapter or a thesis section is a separate decision outside this prereg's scope; the prereg cites v0.5 factually here and in §1's pivot paragraph.

- **v1.0 (2026-05-14, LOCKED):** Locked. No Stage A data collected before this version. Final commit hash and timestamp recorded in the Status block at the next commit, per §16.4.

- **v1.1 (2026-05-14, LOCKED):** Amendment. Clarifies the definition of `reference_struct_unstable` for cells with no feasible reference on any seed.

  *Data state at the time of the amendment.* Stage A has been collected under v1.0 (`data/stage_a_vrptw.parquet`, 56 × 16 cells, 3 seeds at 60 s). The §12.3 verification check on the Stage A pool reported 256 / 896 = 0.2857 (above the 25% threshold), triggering the §12.6 §12.3-clause revision (PyVRP 120 s re-collection on the 256 affected cells). The re-collection is complete (`data/stage_a_vrptw_recollected.parquet`, `data/stage_a_vrptw_recollection_report.md`). The remaining §12.1, §12.2, §12.5 verification checks have not yet been run. **No headline metrics or hypothesis pass/fail criteria have been evaluated under v1.1; the amendment is locked before the verification pass that depends on the amended definition.**

  *Section being amended.* §8.2 (per-cell stability check definition) and §12.3 (rate-computation clarification), with a parallel one-line clarification added to §8.4 for cross-reference consistency.

  *Old text (v1.0 §8.2, code block).*
  ```
  reference_struct_unstable = min over (i,j) of ARI(seed_i_assignment, seed_j_assignment) < 0.90
  ```
  Plus the narrative line: "The structure check matches v0.5."

  *New text (v1.1 §8.2, code block).*
  ```
  reference_struct_unstable = min over (i,j) of ARI(seed_i_assignment, seed_j_assignment) < 0.90
                              UNDEFINED  if no seed is feasible (v1.1 amendment)
  ```
  Plus an extended narrative line that documents the carve-out and its relationship to §8.3.

  *Old text (v1.0 §12.3).* The §12.3 paragraph specifies the 25% threshold without specifying which cells participate in the rate computation.

  *New text (v1.1 §12.3).* Adds one paragraph specifying the rate's denominator is the set of cells where `reference_struct_unstable` is defined (i.e., at least one feasible seed). Cells with no feasible seed are excluded from both numerator and denominator and are owned by the §8.3 n/a policy. **The 25% threshold itself is unchanged from v1.0.**

  *Old text (v1.0 §8.4).* States the re-collection trigger and cites §12.3.

  *New text (v1.1 §8.4).* Adds one cross-reference paragraph stating the numerator/denominator definitions per the v1.1 §8.2 amendment.

  *Empirical reason for the amendment.* Stage A produced 7 cells where all three reference seeds are infeasible (R101 × TT_4, R102 × TT_4, R103 × TT_4, R110 × OC_4, RC102 × OC_2, RC102 × OC_4, RC105 × TT_4). These are real fleet-exhaustion infeasibilities at the locked Solomon-100 vehicle count and are correctly identified by `reference_failure_kind == "all_infeasible"`; they are excluded from STRUCT/SCHEDULE training under the §8.3 n/a policy. Under v1.0's literal §8.2 definition these 7 cells are *also* flagged `reference_struct_unstable = True`, because PyVRP returns a penalty-bounded "best" partition for each infeasible seed and the resulting cross-seed `ari_min` is computable and falls below 0.90. The 7 cells therefore appeared in both the §8.3 bucket (n/a) and the §12.3 numerator (structurally unstable). That is a definitional overlap, not a property of the cells: a cell whose reference is undefined cannot have a defined notion of reference *stability*. The v1.1 amendment makes the §12.3 rate computation match the §8.3 n/a policy's existing treatment of these cells.

  *Why the change does not undermine the pre-registration's purpose.* The 25% threshold is unchanged. The amendment narrows the rate's denominator by exactly the 7 cells the §8.3 n/a policy already excludes from STRUCT/SCHEDULE training; no other cells are affected. The change is a definitional clarification of a degenerate case, not a threshold adjustment in response to observed data (which §17 forbids). Concretely: with the re-collection's 71 cleared cells and the 7 amendment-excluded cells, the post-revision §12.3 rate is `(256 − 71 − 7) / (896 − 7) = 178 / 889 = 0.2002`, which is below the 25% threshold by 5 pp. The literal v1.0 rate (treating the 7 as struct_unstable) is `(256 − 71) / 896 = 185 / 896 = 0.2065`, which is also below 25%. Both readings clear the gate; the amendment's effect on the headline pass/fail outcome is zero. The amendment is principled, narrowly scoped, fully traceable, and pre-registered before the §12.1/§12.2/§12.5 verification pass that consumes the corrected definition.

  *Code change accompanying the amendment.* `src/vrp_copilot_bench/vrptw/evaluation.py`'s `reference_stability` function returns `struct_unstable = None` instead of `True` when no seed is feasible; `ReferenceStability.struct_unstable`'s type is widened from `bool` to `bool | None`. Callers in `scripts/run_vrptw_scale_check.py` propagate `None` rather than coercing to `bool`. New test `tests/test_vrptw_reference_stability.py` covers the four cases (all-feasible-stable, all-feasible-unstable, no-feasible (new), partial-feasible).

  *Tagging.* This entry is locked together with the file; the v1.1 lock commit gets tag `prereg-v1.1-vrptw` per §17. The v1.0 tag (`prereg-v1.0-vrptw`) is unchanged and continues to mark the original locked specification.

## Appendix A. Revision menu for verification failures

If §12.1 verification fails on a `(claim_family × perturbation_family)` block, the revision is deterministic: the offending block's perturbation magnitude grid steps to the next severity level. Each family's escalation and de-escalation menus are below. Only one substitution per block is permitted before re-collection.

### A.1 TRAVEL_TIME escalation/de-escalation

Default soft_grid: TT_1 ×1.05, TT_2 ×1.10, TT_3 ×1.20, TT_4 ×1.30.

| direction | revised multipliers | rationale |
|---|---|---|
| escalate | TT_1 ×1.10, TT_2 ×1.20, TT_3 ×1.30, TT_4 ×1.50 | block too positive: push harder |
| de-escalate | TT_1 ×1.02, TT_2 ×1.05, TT_3 ×1.10, TT_4 ×1.20 | block too negative: ease off |

### A.2 TIME_WINDOW escalation/de-escalation

Default soft_grid: TW_1 tighten 5%, TW_2 tighten 10%, TW_3 shift 5%, TW_4 shift 5%.

| direction | revised | rationale |
|---|---|---|
| escalate | TW_1 10%, TW_2 20%, TW_3 10%, TW_4 10% | block too positive |
| de-escalate | TW_1 2%, TW_2 5%, TW_3 2%, TW_4 2% | block too negative |

### A.3 SERVICE_TIME escalation/de-escalation

Default soft_grid: ST_1 ×1.05, ST_2 ×1.10, ST_3 ×1.25, ST_4 ×1.50.

| direction | revised | rationale |
|---|---|---|
| escalate | ST_1 ×1.10, ST_2 ×1.25, ST_3 ×1.50, ST_4 ×2.00 | block too positive |
| de-escalate | ST_1 ×1.02, ST_2 ×1.05, ST_3 ×1.10, ST_4 ×1.25 | block too negative |

### A.4 ORDER_CHANGE escalation/de-escalation

Default soft_grid: OC_1 (1c, 0.05·cap, flex), OC_2 (1c, 0.05·cap, tight 40%), OC_3 (3c, 0.15·cap, flex), OC_4 (3c, 0.20·cap, tight 40%).

| direction | revised | rationale |
|---|---|---|
| escalate | OC_1 (1c, 0.10·cap, flex), OC_2 (1c, 0.10·cap, tight 25%), OC_3 (3c, 0.25·cap, flex), OC_4 (3c, 0.30·cap, tight 25%) | block too positive |
| de-escalate | OC_1 (1c, 0.03·cap, flex), OC_2 (1c, 0.03·cap, tight 60%), OC_3 (3c, 0.10·cap, flex), OC_4 (3c, 0.15·cap, tight 60%) | block too negative |

### A.5 Tie-breaking

If a block's revision falls between two menu entries, choose the entry one step further from the current default. This forbids interpolation and keeps revisions discrete and pre-specified.

---

*End of pre-registration draft.*

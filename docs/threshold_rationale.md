# Threshold rationale for B2 evaluation layer (A-008 Part A)

**Date**: 2026-05-26
**Status**: draft for review — values not yet implemented in code
**Authoritative scope**: governs the per-family thresholds the B2
evaluation layer uses to translate observed plan metrics into
operator-facing acceptability verdicts (`acceptable` /
`needs_review` / `unacceptable`).

This document derives each threshold from the **Run-2 47-scenario
registry** (`load_registry()` in `product/api/scenario_store.py`) — the
locked corpus that Stage 0-2 baselines were measured against. For each
threshold we report (1) the proposed value, (2) the data source, (3)
the observed distribution, (4) the rationale for the chosen cutoff,
and (5) a sensitivity note showing how the classification count shifts
under ±25% threshold perturbation.

The thresholds are **starting values for production deployment**, not
universal truths. The thesis defense rests on the structure of
operator-configured evaluation, not on these specific numbers; the
sensitivity table at the end of this document characterizes the
robustness of the verdict layer to threshold choice.

---

## SCHEDULE: `late_customers_max`

### Proposed value: **3 late customers**

### Data source

All 12 SCHEDULE-family scenarios in the Run-2 47-scenario registry.
Metric: `payload.n_late_customers`.

### Distribution

| Scenario | Perturbation | n_late_customers |
|---|---|---|
| C105 | TT_4 | 0 |
| RC101 | TT_1 | **1** |
| RC202 | ST_3 | 0 |
| RC202 | ST_4 | 0 |
| RC2_2_1 | OC_5 | 0 |
| R202 | TT_2 | 0 |
| RC201 | OC_2 | 0 |
| RC201 | ST_2 | 0 |
| C107 | TW_3 | 0 |
| RC201 | OC_3 | 0 |
| C2_2_2 | ST_3 | 0 |
| RC1_2_1 | ST_4 | 0 |

Summary: 11/12 scenarios have 0 late customers; 1 has 1 late customer.
Mean 0.08, median 0, max 1.

### Rationale

The corpus distribution is uniformly low — Stage 1 measurements
confirmed this is a deliberately curated registry of perturbations
chosen so most scenarios maintain on-time delivery. The corpus alone
cannot anchor an operator-meaningful threshold because every scenario
would pass at any reasonable cutoff.

The threshold value (3) is operator-derived, not data-derived: per the
Phase B plan's documented rationale, **3 late deliveries is a common
SLA tolerance ceiling for last-mile operations**. A dispatcher with
contractual obligations to 100+ daily customers typically has informal
tolerance for 1-3 late deliveries within an SLA window before
escalation is required; beyond 3, the plan deserves review.

This is the kind of threshold a production deployment would calibrate
per operational context (24/7 grocery delivery may tolerate 5+;
specialty pharma may tolerate 0). For this thesis the value of 3 is a
defensible mid-tier setting that lets the system demonstrate the
verdict layer's mechanics. The thesis-defense claim is "operator-
configured" — the methodology defends the structure, not the constant.

### Sensitivity

Within the 47-scenario corpus, **every threshold from 1 to ∞ gives
the same verdict count** because only one scenario has any lateness
(n=1). Threshold of 1 would mark RC101/TT_1 as
`needs_review`; threshold of 0 would mark it as `unacceptable` (with
conservative-bias bumping no other scenarios). The numeric ±25%
sensitivity is undefined in practice — the threshold is operationally
load-bearing only when the underlying corpus has variation in
lateness, which the curated test set does not.

For Stage 4 measurement on the operator-persona corpus (which exercises
the SCHEDULE recommended scenario C105/TT_4, n_late=0), every
SCHEDULE evaluation query will return `acceptable` for the lateness
dimension. The verdict layer's lift in this category will come
primarily from emitting the threshold-grounded prose, not from
discriminating between scenarios.

---

## OBJ: per-perturbation relative delta

The OBJ family is the most data-rich for threshold derivation: 12
scenarios with non-trivial spread across the four perturbation
prefixes. Per-perturbation thresholds are essential because the same
percent delta means very different things across perturbation types
(adding customers naturally costs; tightening windows often does not).

### Data source

All 12 OBJ-family scenarios. Metric:
`payload.diff.objective.delta_percent` (signed; absolute value used
for threshold comparison).

### Distribution per perturbation prefix

| Prefix | n | Observed values | |max| | mean(|·|) |
|---|---|---|---|---|
| TW | 2 | 0.00, 0.00 | 0.0% | 0.0% |
| TT | 3 | 0.00, 3.12, 22.30 | 22.3% | 8.5% |
| ST | 5 | 0.00, 5.52, 6.77, 14.50, 29.65 | 29.6% | 11.3% |
| OC | 2 | 8.76, 10.69 | 10.7% | 9.7% |

### Proposed values, rationale, and sensitivity

#### OC (ORDER_CHANGE): **15%**

OC perturbations add or remove customers. Adding a customer naturally
increases the objective; the magnitude scales with how far the new
customer is from existing routes. A 15% relative delta cap reflects
the expected cost impact of one or two added customers in a
typical Solomon-shape instance.

Observed values: 8.76% (C103/OC_1), 10.69% (R206/OC_4). Both well
within 15%; the threshold positions itself approximately 50% above the
observed range, giving headroom for harder OC perturbations a
production deployment would encounter.

**Sensitivity**: at 15% → both OC scenarios pass; at 11.25% (-25%) →
R206/OC_4 (10.69) still passes by 0.6pp; at 18.75% (+25%) → both
still pass. Threshold is well-positioned relative to the observed
range.

#### TT (TRAVEL_TIME): **20%**

TT perturbations cascade through schedules — small travel time
increases propagate to many customers. The 20% threshold is more
permissive than OC's 15% because TT perturbations are inherently
network-wide.

Observed values: 0.00% (R109/TT_4), 3.12% (C1_2_2/TT_5), 22.30%
(C1_2_1/TT_5). The 22.30% value is on the boundary — at threshold 20%
it would fail. This is the intended behavior: a 22% TT perturbation IS
material enough that an operator should review the plan.

**Sensitivity**: at 20% → 2 of 3 pass (the 22.30 fails); at 15% (-25%)
→ same 2 of 3 pass (the 22.30 still fails); at 25% (+25%) → 3 of 3
pass. The threshold meaningfully discriminates a known outlier.

#### ST (SERVICE_TIME): **10%**

ST perturbations are local effects (service time increases at
specific customers). Cascade is limited to the affected customers and
their downstream window slack. A tighter threshold (10%) catches
outliers without flagging modest perturbations.

Observed values: 0.00% (C207/ST_1), 5.52% (C206/ST_2), 6.77%
(C104/ST_3), 14.50% (C201/ST_2), 29.65% (C205/ST_4). The mean is
11.3% — slightly above the threshold; the threshold is intentionally
calibrated to catch the 14.50 and 29.65 outliers.

**Sensitivity**: at 10% → 3 of 5 pass (14.50 and 29.65 fail); at
7.5% (-25%) → 2 of 5 pass (5.52, 6.77 also fail); at 12.5% (+25%) →
3 of 5 pass (same). Sensitive to small changes near 7.5% — but the
mid-tier setting (10%) is the documented Phase B plan starting value
and produces interpretable verdict counts.

#### TW (TIME_WINDOW): **10%**

TW perturbations shift customer time windows. The Solomon-instance
distribution typically absorbs modest TW shifts without changing the
objective (the solver re-optimizes against the same depot constraints).
The corpus reflects this: both TW scenarios show 0.00% objective
delta.

Observed values: 0.00% (C202/TW_3), 0.00% (C2_2_2/TW_5). With
the entire observed range at 0%, any non-zero threshold passes; the
10% setting is chosen to match the conservative ST threshold (both
families produce small expected deltas) and to leave headroom for
heavier TW perturbations a production deployment might encounter.

**Sensitivity**: at any threshold ≥0 → both TW scenarios pass.
Threshold is structurally untested by the corpus; documented as a
heuristic basis (10% matches ST as the tighter half of the threshold
table).

### OBJ aggregation table

| Perturbation | Threshold (|delta_pct| max acceptable) | Rationale |
|---|---|---|
| OC | 15% | Adding customers naturally costs; 15% headroom above observed |
| TT | 20% | Network-wide cascade; more permissive than local-effect families |
| ST | 10% | Local-effect perturbation; tighter to catch outliers |
| TW | 10% | Matches ST as the conservative half; data sparse |

---

## PV: feasibility

### Proposed value: **strict** (any `became_infeasible=True` → `unacceptable`)

### Data source

All 12 PV-family scenarios. Metric: `payload.diff.feasibility.became_infeasible`.

### Distribution

| Outcome | n | Scenarios |
|---|---|---|
| `became_infeasible = False` (feasibility preserved) | 9 | R202/OC_1, R208/OC_3, C2_2_1/TW_6, R104/TT_2, R207/TT_3, RC1_2_1/TW_5, C107/TW_4, R106/TW_4, C1_2_1/ST_3 |
| `became_infeasible = True` (became infeasible) | 3 | C201/OC_1, RC103/ST_2, RC203/ST_2 |

### Rationale

PV-family scenarios are feasibility-focused by definition. The
threshold is binary: any infeasibility-becoming-infeasible signal makes
the plan unacceptable. The alternative — allowing partial
infeasibility (some unserved customers OK) — applies only in
operational contexts where SLA hierarchies permit dropped customers
(e.g., capacity-constrained on-demand delivery); this thesis treats
feasibility strictly because (a) the locked Run-2 60-case eval treats
it strictly, (b) operator-facing reasoning about "is this acceptable"
naturally collapses to "is any customer unserved" for PV cases.

The strict rule produces a clean verdict on the corpus: 3
scenarios → `unacceptable`, 9 → `acceptable`.

### Aggregation rule exception

PV feasibility is treated as a **categorical gate**, not a soft
threshold. When the PV check fails (`became_infeasible=True`), the
verdict is **`unacceptable`** regardless of whether other family
checks also fail. This is an explicit exception to the multi-family
aggregation rule below. Operationally, an infeasible plan means at
least one customer cannot be served at all — categorically more severe
than a soft threshold breach like *"5 customers running late."* Marking
such a plan as `needs_review` (the default for a single failing check)
would understate the severity.

### Sensitivity

The threshold has no numeric parameter to perturb — it's a binary
gate. The only sensitivity question is whether the "strict" stance
is appropriate. For a production deployment with a per-customer
priority hierarchy (e.g., "tier-1 customers must be served; tier-2
may be dropped"), a non-strict variant would gate on the priority of
the unserved set, not the count. This is future work; the strict gate
is the appropriate default.

---

## STRUCT: `routes_modified_pct`

### Proposed value: **50% of routes modified**

### Data source

All 11 STRUCT-family scenarios. Metric: `(added + removed + modified)
/ total_routes × 100`.

### Distribution

| Scenario | Perturbation | added | removed | modified | total | pct |
|---|---|---|---|---|---|---|
| C104 | OC_2 | 0 | 0 | 1 | 10 | 10.0% |
| C1_2_2 | TW_5 | 0 | 0 | 0 | 20 | 0.0% |
| R102 | OC_1 | 0 | 0 | 17 | 18 | 94.4% |
| R201 | TT_3 | 0 | 0 | 8 | 8 | 100.0% |
| R2_2_1 | OC_5 | 0 | 0 | 12 | 13 | 92.3% |
| C102 | OC_1 | 0 | 0 | 1 | 10 | 10.0% |
| RC107 | TW_1 | 0 | 0 | 0 | 12 | 0.0% |
| RC107 | TW_2 | 0 | 0 | 0 | 12 | 0.0% |
| R112 | OC_1 | 0 | 0 | 9 | 10 | 90.0% |
| RC104 | ST_4 | 2 | 0 | 10 | 12 | 100.0% |
| RC1_2_2 | TT_5 | 1 | 0 | 19 | 20 | 100.0% |

Summary: distribution is strongly **bimodal**. Five scenarios show
≤10% modification (small targeted changes), six show ≥90%
(near-complete re-solves). No scenarios sit between 11% and 89%.

### Rationale

The bimodal distribution makes the choice of cutoff structurally
robust: any threshold between 11% and 89% yields the same verdict
count (5 acceptable, 6 needs-review). Within that range the natural
operational midpoint is **50%**, which carries the operator-facing
meaning "more than half the routes had to be restructured" — a
defensible escalation point.

The 50% setting matches the Phase B plan's documented starting
value. It's also the canonical "majority changed" threshold operators
intuitively understand without further calibration.

### Sensitivity

The bimodal corpus distribution makes the threshold insensitive within
a wide band:

| Threshold | Acceptable | Needs review |
|---|---|---|
| 25% (-50%) | 5 | 6 |
| 37.5% (-25%) | 5 | 6 |
| 50% (proposed) | 5 | 6 |
| 62.5% (+25%) | 5 | 6 |
| 75% (+50%) | 5 | 6 |

The classification count only changes at thresholds below 11% (catches
all "small modification" cases as needs-review too) or above 89%
(allows the largest re-solves). A production deployment with a more
varied corpus would need finer calibration; for this thesis the
threshold's bimodal-stable behavior is itself an interesting
methodological property (the verdict is data-robust within a wide
band).

---

## Multi-family aggregation rule

When the query is general (*"is this plan acceptable?"*), all family
thresholds are checked in conjunction:

- All checks pass → `acceptable`
- Exactly one check fails AND the failing check is **not** PV-feasibility → `needs_review` (single failing dimension named)
- PV-feasibility check fails (regardless of other checks) → `unacceptable`
- Two or more non-PV checks fail → `unacceptable`

**PV exception rationale**: PV-feasibility is a categorical gate (any
infeasibility means at least one customer cannot be served), not a soft
threshold breach. Single PV failures therefore escalate to
`unacceptable` directly, bypassing the single-check-failure
`needs_review` rule. See the PV section above for the full rationale.

When the query is dimension-specific (*"is the lateness OK?"*), only
the relevant family is checked. Dimension-specific queries cannot
escalate to `unacceptable` (that requires multi-dimension failure)
**except** for PV dimension-specific queries, which still trigger the
PV exception.

Borderline cases (observed value within ±10% of threshold) default to
`needs_review` with `conservative_bias_applied=True` on the
metadata — see next section.

---

## Conservative bias rule

When an observed value is within **±10% of its threshold**, the check
is classified as `passes=False` with `conservative_bias_applied=True`.

This biases borderline cases toward `needs_review` rather than
`acceptable` — the operator-safety direction. The rationale: a 10%
band around any threshold represents measurement / model
uncertainty; we'd rather a dispatcher review one extra plan than
let a borderline-bad plan slip through.

### Bias band examples

| Threshold | Observed | Within ±10% band? | Verdict (without bias) | Verdict (with bias) |
|---|---|---|---|---|
| late_max=3 | 2.7 | yes (within [2.7, 3.3]) | acceptable | needs_review |
| late_max=3 | 3.5 | no (above [2.7, 3.3]) | needs_review | needs_review |
| OBJ_OC=15% | 13.6% | yes (within [13.5%, 16.5%]) | acceptable | needs_review |
| OBJ_OC=15% | 12.0% | no (below band) | acceptable | acceptable |

The bias band is 10% globally. Per-threshold bias bands (tighter for
PV which is binary; wider for OBJ where percentage shifts are noisier)
are deferred to a post-Stage-4 tuning amendment if measurement
suggests it matters.

### Corpus-level bias-band check

A spot-check of every observed value against its threshold's bias band
confirms that **no observed value falls within the ±10% bias band of
its threshold** on the Run-2 47-scenario corpus:

| Threshold | Bias band | Observed values | In band? |
|---|---|---|---|
| OBJ-OC 15% | [13.5%, 16.5%] | 8.76%, 10.69% | no |
| OBJ-TT 20% | [18%, 22%] | 0%, 3.12%, 22.30% | 22.30% sits just above the upper edge (22.30 > 22.0); already `needs_review` under the strict rule so the bias rule would not escalate further even if rounding edges put it in band |
| OBJ-ST 10% | [9%, 11%] | 0%, 5.52%, 6.77%, 14.50%, 29.65% | no |
| OBJ-TW 10% | [9%, 11%] | 0%, 0% | no |
| SCHEDULE late_max=3 | [2.7, 3.3] | 0×11, 1×1 | no |
| STRUCT 50% | [45%, 55%] | bimodal: 5×{0%, 10%}, 6×{90%+} | no |
| PV strict | (binary, no band) | 9 False, 3 True | n/a |

The conservative bias rule is defined and will become active when
scenarios with edge-of-threshold values appear — typically in
production deployment rather than this curated test corpus. The rule
is committed so it can be exercised against future scenario sets
without re-amendment; its inactivity on the locked corpus is itself
information for the thesis (the threshold values discriminate cleanly
on this corpus).

---

## Overall sensitivity table

The thresholds and their corpus-classification counts under the
proposed values and ±25% perturbations:

| Threshold | -25% | Proposed | +25% | Observed values | Acceptable @ proposed | Needs-review @ proposed |
|---|---|---|---|---|---|---|
| SCHEDULE late_max | 2 | 3 | 4 | 11×0, 1×1 | 12/12 | 0 |
| OBJ OC delta_max | 11.25% | 15% | 18.75% | 8.76%, 10.69% | 2/2 | 0 |
| OBJ TT delta_max | 15% | 20% | 25% | 0%, 3.12%, 22.30% | 2/3 | 1 |
| OBJ ST delta_max | 7.5% | 10% | 12.5% | 0%, 5.52%, 6.77%, 14.50%, 29.65% | 3/5 | 2 |
| OBJ TW delta_max | 7.5% | 10% | 12.5% | 0%, 0% | 2/2 | 0 |
| STRUCT routes_modified_pct | 37.5% | 50% | 62.5% | 11 values, bimodal | 5/11 | 6 |
| PV feasibility | strict | strict | strict | 9 feasible, 3 became_inf | 9/12 | 3 |

The total across all 47 scenarios under proposed thresholds, with the
PV exception applied:

- `acceptable`: 35 (74%)
- `needs_review`: 9 (19%)
- `unacceptable`: 3 (6%) — all from PV-infeasibility scenarios
  (C201/OC_1, RC103/ST_2, RC203/ST_2); the PV exception escalates
  these from the default `needs_review` to `unacceptable`.

Per-family breakdown:

- SCHEDULE: 12/12 acceptable (no late counts above threshold)
- OBJ-OC: 2/2 acceptable
- OBJ-TT: 2/3 acceptable, 1 needs_review (22.30%)
- OBJ-ST: 3/5 acceptable, 2 needs_review (14.50%, 29.65%)
- OBJ-TW: 2/2 acceptable
- STRUCT: 5/11 acceptable, 6 needs_review
- PV: 9 acceptable, 3 unacceptable

A production deployment with a more aggressive corpus (e.g., real-time
operations with harder perturbations) would see the verdict
distribution shift toward `needs_review` and `unacceptable`. The
thesis-defense claim rests on the structure (per-family, per-
perturbation, PV-categorical, conservative-bias-on-borderline), not on
the specific ratio observed here.

---

## What this document defends

When the thesis committee asks "*why these specific threshold values?*"
the defense is:

1. **The 50% STRUCT, 15% OBJ-OC, 20% OBJ-TT, 10% OBJ-ST, 10% OBJ-TW,
   3 SCHEDULE values are documented mid-tier defaults**, each derived
   from a corpus-distribution analysis showing how the threshold sits
   relative to observed scenario metrics.

2. **The PV "strict" stance is data-aligned**: the Run-2 60-case eval
   treats feasibility strictly; the evaluation layer inherits that.

3. **The thresholds fall into two categories**:
   - **Data-supported thresholds** — derived from observed corpus
     distributions:
     - **STRUCT (50%)**: bimodal corpus distribution makes the
       11%–89% threshold band structurally robust; classifications are
       identical at any cutoff in this range.
     - **OBJ-TT (20%)**: catches the 22.30% outlier in the corpus;
       meaningful discrimination at this value.
     - **OBJ-ST (10%)**: discriminates 2 of 5 observed values;
       sensitive to small shifts in the 7.5%–12.5% range (see the
       OBJ-ST section above).
     - **PV (strict)**: corpus-aligned with the locked Run-2 60-case
       eval; binary gate on `became_infeasible`. The PV exception
       escalates failures to `unacceptable` (operator-safety
       direction).
   - **Heuristic-default thresholds** — chosen as mid-tier defaults
     aligned with operational norms, with limited or no corpus
     discrimination:
     - **SCHEDULE (3)**: corpus has 11/12 scenarios at 0 late
       customers; threshold is operationally derived (SLA tolerance
       ceiling for last-mile operations), not data-derived. Any value
       from 1 to ∞ gives the same corpus verdict.
     - **OBJ-OC (15%)**: corpus values (8.76%, 10.69%) both pass at
       any threshold ≥10.69%; the 15% choice provides headroom for
       harder OC perturbations a production deployment would encounter.
     - **OBJ-TW (10%)**: corpus has both values at 0%; the 10% choice
       matches OBJ-ST for symmetry, with no empirical basis on this
       corpus.

   This bifurcation is honest about which thresholds defend
   numerically and which defend structurally. The data-supported
   thresholds defend the specific values; the heuristic-default
   thresholds defend the methodology (per-family, per-perturbation,
   operator-configured) with the understanding that a production
   deployment would calibrate these per operational context.

4. **The conservative bias rule biases verdicts toward `needs_review`
   on borderline cases**, the safer direction for an operator-decision
   layer that errs toward "let the human check" when uncertain.

5. **The thesis-defense framing is structural**: the system extends
   operator dispatch with grounded-from-thresholds judgment. The
   numeric values are mid-tier starting defaults; a production
   deployment would calibrate per operational context.

---

## Awaiting review

Per the Stage 3 amendment, this document is the gate before Part B
implementation. Hand to the user for review; Part B (the threshold
layer code) will not be implemented until these values are accepted.

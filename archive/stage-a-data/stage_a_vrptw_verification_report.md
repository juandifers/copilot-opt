# Stage A VRPTW verification report (§12.1, §12.2, §12.5)

Verification pass on `data/stage_a_vrptw_consolidated.parquet` (3,808
wide rows, 15,232 long rows) under the **PREREG v1.1** lock
(`prereg-v1.1-vrptw`, commit `7d9cf08`). §12.3 was run earlier and
resolved (re-collection at 120 s, then v1.1 definitional amendment;
post-revision rate 178 / 889 = 0.2002, below 25%); this report covers
the remaining checks.

| check | quoted threshold | observed | verdict |
|---|---|---:|---|
| §12.1 label distribution per block | `0.10 ≤ rate ≤ 0.90` (16 blocks) | **2 of 16 blocks above ceiling** | **FAIL** |
| §12.2 LOIO fold feasibility | ≥3 of 4 families with both labels per fold | 56 / 56 folds pass | PASS |
| §12.5 feasibility decoupling | `P(easy ∧ infeasible | OBJ, reuse_direct) > 0.20` | 0.6217 | PASS |

**Net status:** §12.2 and §12.5 pass. §12.1 fails on `OBJ × TIME_WINDOW`
(1.000) and `OBJ × TRAVEL_TIME` (0.973) — both above the 0.90 ceiling.
Per user instruction, the §12.6 revision procedure is **not**
auto-applied; the failure is surfaced for review. See §12.1 below for
the per-block table and the secondary ambiguity that appears under one
reading of §3.3.

Artifacts:
- Wide table (consolidated): `data/stage_a_vrptw_consolidated.parquet`
- Long table (consolidated): `data/stage_a_vrptw_consolidated_claim_rows.parquet`
- Stage A v1.0 originals (unchanged): `data/stage_a_vrptw.parquet`, `data/stage_a_vrptw_claim_rows.parquet`
- Re-collected references (unchanged): `data/stage_a_vrptw_recollected.parquet`
- Prereg lock: `prereg/PREREG_v1.1_vrptw.md`, tag `prereg-v1.1-vrptw`, commit `7d9cf08`

---

## §12.1 — Non-degenerate label distribution per cell

### Quoted prereg text (PREREG_v1.1_vrptw.md §12.1)

> For each `(claim_family × perturbation_family)` block, the operational sufficiency label distribution must satisfy:
>
> ```
> 0.10 ≤ P(operational_sufficiency = 1 | block) ≤ 0.90
> ```
>
> Sixteen blocks fall under this check: `{OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE} × {TRAVEL_TIME, TIME_WINDOW, SERVICE_TIME, ORDER_CHANGE}`. Unlike v0.5, PLAN_VALIDITY is *included* (the positive-control role is eliminated under v1.0; see §3.2).
>
> The thresholds are **locked at `[0.10, 0.90]`**, carried over from v0.5 §12.1. […] the per-block check at Stage A is the real test, and the §12.6 escalation rules apply if any of the 16 blocks falls outside the bracket.

### What I computed

`operational_sufficiency` is per §3.3 a cell-level label keyed to a cheap action. §3.3 literally writes `band[reuse_direct, claim_family] == 'easy'` for all four families, while §13.1 defines the predictor's target as "the cheap action (`reuse_direct` on non-OC, `local_repair_insert` on OC) will produce a sufficient answer." Those two readings disagree on the cheap action for `ORDER_CHANGE × PLAN_VALIDITY`. I report both readings; the verdicts on the OBJ blocks (the user's flagged concern) are identical under both.

The long table's `sufficient_binary` already encodes the per-claim-family decision (`band == 'easy'` plus, for OBJ, `action_feasible`), so I filter the long table to the chosen action per family and compute `easy_rate = (sufficient_binary == 1) / (sufficient_binary is not null)` per block.

### Reading A — §3.3 literal (use `reuse_direct` for all 16 blocks)

| pert_fam | claim_fam | n | n_pos | n_null | easy_rate | verdict |
|---|---|---:|---:|---:|---:|---|
| ORDER_CHANGE | OBJ | 224 | 188 | 3 | 0.8507 | PASS |
| ORDER_CHANGE | PLAN_VALIDITY | 224 | 0 | 0 | **0.0000** | **FAIL (< 0.10)** |
| ORDER_CHANGE | SCHEDULE | 224 | 98 | 3 | 0.4434 | PASS |
| ORDER_CHANGE | STRUCT | 224 | 130 | 3 | 0.5882 | PASS |
| SERVICE_TIME | OBJ | 224 | 185 | 0 | 0.8259 | PASS |
| SERVICE_TIME | PLAN_VALIDITY | 224 | 75 | 0 | 0.3348 | PASS |
| SERVICE_TIME | SCHEDULE | 224 | 81 | 0 | 0.3616 | PASS |
| SERVICE_TIME | STRUCT | 224 | 123 | 0 | 0.5491 | PASS |
| TIME_WINDOW | OBJ | 224 | 224 | 0 | **1.0000** | **FAIL (> 0.90)** |
| TIME_WINDOW | PLAN_VALIDITY | 224 | 90 | 0 | 0.4018 | PASS |
| TIME_WINDOW | SCHEDULE | 224 | 92 | 0 | 0.4107 | PASS |
| TIME_WINDOW | STRUCT | 224 | 127 | 0 | 0.5670 | PASS |
| TRAVEL_TIME | OBJ | 224 | 214 | 4 | **0.9727** | **FAIL (> 0.90)** |
| TRAVEL_TIME | PLAN_VALIDITY | 224 | 89 | 0 | 0.3973 | PASS |
| TRAVEL_TIME | SCHEDULE | 224 | 102 | 4 | 0.4636 | PASS |
| TRAVEL_TIME | STRUCT | 224 | 132 | 4 | 0.6000 | PASS |

Reading A: 3 failing blocks (TW × OBJ, TT × OBJ, OC × PV).

### Reading B — cheap action per family (`local_repair_insert` on OC, `reuse_direct` elsewhere)

| pert_fam | claim_fam | n | n_pos | n_null | easy_rate | verdict |
|---|---|---:|---:|---:|---:|---|
| ORDER_CHANGE | OBJ | 224 | 190 | 3 | 0.8597 | PASS |
| ORDER_CHANGE | PLAN_VALIDITY | 224 | 150 | 0 | 0.6696 | PASS |
| ORDER_CHANGE | SCHEDULE | 224 | 94 | 3 | 0.4253 | PASS |
| ORDER_CHANGE | STRUCT | 224 | 115 | 3 | 0.5204 | PASS |
| SERVICE_TIME | OBJ | 224 | 185 | 0 | 0.8259 | PASS |
| SERVICE_TIME | PLAN_VALIDITY | 224 | 75 | 0 | 0.3348 | PASS |
| SERVICE_TIME | SCHEDULE | 224 | 81 | 0 | 0.3616 | PASS |
| SERVICE_TIME | STRUCT | 224 | 123 | 0 | 0.5491 | PASS |
| TIME_WINDOW | OBJ | 224 | 224 | 0 | **1.0000** | **FAIL (> 0.90)** |
| TIME_WINDOW | PLAN_VALIDITY | 224 | 90 | 0 | 0.4018 | PASS |
| TIME_WINDOW | SCHEDULE | 224 | 92 | 0 | 0.4107 | PASS |
| TIME_WINDOW | STRUCT | 224 | 127 | 0 | 0.5670 | PASS |
| TRAVEL_TIME | OBJ | 224 | 214 | 4 | **0.9727** | **FAIL (> 0.90)** |
| TRAVEL_TIME | PLAN_VALIDITY | 224 | 89 | 0 | 0.3973 | PASS |
| TRAVEL_TIME | SCHEDULE | 224 | 102 | 4 | 0.4636 | PASS |
| TRAVEL_TIME | STRUCT | 224 | 132 | 4 | 0.6000 | PASS |

Reading B: 2 failing blocks (TW × OBJ, TT × OBJ).

### What's failing and why

**Common to both readings (the unambiguous failures):**
- `TIME_WINDOW × OBJ`: easy-rate = 1.000 (224/224). Every TW-perturbed cell's reuse_direct returns an OBJ-easy answer (band_obj_distance == 'easy') *and* action_feasible holds on enough of them that the operational_sufficiency=1 share is 100%. Above the 0.90 ceiling.
- `TRAVEL_TIME × OBJ`: easy-rate = 0.9727 (214/220 defined; 4 cells excluded as n/a). Same pattern, slightly less extreme. Above the 0.90 ceiling.

These match the Stage A run report's aggregate signal: reuse_direct OBJ easy-rate (cell-level) was 0.912 overall, dragged down by SERVICE_TIME (0.826) and ORDER_CHANGE (0.851) but pulled up by TW and TT into clear breach territory.

**Mechanically:** TW and TT perturbations modify the routing problem in ways that often leave the original (unperturbed) solution close enough to the new reference cost that `band_obj_distance == 'easy'` (≤ 5% loss). When the original solution is also feasible under the perturbation (which it is in the majority of TW and TT cells — these are "soft" perturbations), operational_sufficiency = True is the modal outcome, and the block saturates near 1.0.

**Reading-A-only failure:**
- `ORDER_CHANGE × PLAN_VALIDITY`: easy-rate = 0.000 under §3.3 literal (reuse_direct cannot cover newly-inserted customers, so PV is uniformly hard on reuse_direct rows for OC). Under reading B (cheap-action = local_repair_insert), it passes at 0.670. This is a §3.3 vs §13.1 wording ambiguity, **flagged for clarification**: §3.3 writes `band[reuse_direct, PLAN_VALIDITY]` literally, while §13.1 defines the predictor target on the family's cheap action. If §3.3's `reuse_direct` is a typo carried over from v0.5 (where reuse_direct was the only cheap action), the correct reading is B and OC × PV passes. If §3.3 is literal, OC × PV fails and the §12.6 §12.1-clause prescribes Appendix A escalation for the ORDER_CHANGE family — which seems counter-productive given the cell is correctly classified as a real PV failure under the local_repair_insert cheap action.

### §12.6 revision procedure (NOT auto-applied per user instruction)

§12.6 §12.1-clause specifies: *"The offending block is mapped to the next severity level for its perturbation family (Appendix A). Increase severity if the block is too positive; decrease if too negative. Only one substitution per block is allowed."*

For the two unambiguous failures (both "too positive"), Appendix A escalation would apply:
- TIME_WINDOW: per `### A.2 TIME_WINDOW escalation/de-escalation` — replace the soft_grid magnitudes with the escalated grid for the failing block.
- TRAVEL_TIME: per `### A.1 TRAVEL_TIME escalation/de-escalation` — replace TT_1..TT_4 multipliers with the escalated row.

Both escalations would require re-running the affected cells (refs + actions) on the new perturbation. This is **surfaced for review, not executed.**

---

## §12.2 — Cross-validation feasibility

### Quoted prereg text (PREREG_v1.1_vrptw.md §12.2)

> For each of the 56 LOIO folds, the test fold (single instance, 16 perturbations × 4 claim families = 64 evaluation cells, minus any all-infeasible n/a cells) must contain at least one positive and one negative example for at least three of the four claim families. If any fold is degenerate, the failure is routed through the §12.5 deterministic revision procedure, which (under v1.0) does *not* include an instance-replacement clause — the Solomon-100 pool has no additional candidates to draw from. Instead, the §12.5 procedure for §12.2 failure is to escalate the offending perturbation family's grid via Appendix A and re-run the affected cells.
>
> The §12.2 fold-feasibility threshold (three of four claim families instead of v0.5's two of three) is calibrated against v1.0's four-claim-family stratification.

(Note: the prereg cross-reference to "§12.5 deterministic revision procedure" is a pre-v1.1 numbering vestige; the deterministic revision procedure is in §12.6, and §12.5 is the feasibility-decoupling diagnostic. Not affecting the verdict.)

### What I computed

For each of the 56 LOIO folds (one held-out instance × 16 perturbations × 4 claim families = 64 long-table rows under the cheap-action reading), count per-(fold, claim_family) the number of `sufficient_binary == 1` (pos) and `sufficient_binary == 0` (neg) rows. A claim family in a fold has "both labels" iff pos ≥ 1 and neg ≥ 1. The fold passes iff at least 3 of 4 claim families have both labels.

### Result

| metric | value |
|---|---:|
| Folds with 4/4 claim families having both labels | 28 / 56 |
| Folds with 3/4 claim families having both labels | 28 / 56 |
| Folds with < 3/4 (degenerate) | **0 / 56** |

**§12.2 PASS.** Every fold meets the 3-of-4 threshold. (The 28 folds at the 3-of-4 floor are tight against the threshold — a future amendment that raises §12.2 to 4-of-4 would fail half the folds; flagged as informational, not actionable.)

---

## §12.5 — Feasibility decoupling diagnostic

### Quoted prereg text (PREREG_v1.1_vrptw.md §12.5)

> To verify that the benchmark exposes the failure mode it was designed to expose, compute:
>
> ```
> P(band_obj_distance == 'easy' AND action_feasible == False
>   | claim_family == OBJ, action == reuse_direct)
> ```
>
> This quantity should remain above **0.20** on the full Stage A pool. The 18-instance scale-check measures this directly: among `reuse_direct × OBJ` rows, 88.0% are OBJ-easy and 29.9% are PV-easy, so the OBJ-easy-but-infeasible fraction is approximately `0.880 × (1 − 0.299 / 0.880) = 0.580`. The 0.20 threshold has substantial margin against this baseline. Falling below indicates the perturbation grid has lost the decoupling phenomenon and the grid is revised under the §12.6 procedure.

### What I computed

Filter the consolidated wide table to `action == reuse_direct` (896 rows, one per cell). Count rows where `band_obj_distance == 'easy'` AND `action_feasible == False`. Divide by 896.

### Result

| metric | value |
|---|---:|
| numerator (band_obj_distance == easy AND not action_feasible) | 557 |
| denominator (reuse_direct rows) | 896 |
| **observed rate** | **0.6217** |
| threshold | > 0.20 |
| verdict | **PASS** |

Sanity decomposition:
- `P(band_obj_distance == 'easy' | reuse_direct)` = 0.9051
- `P(action_feasible | band_obj_distance == 'easy', reuse_direct)` = 0.3132
- Implied joint: 0.9051 × (1 − 0.3132) = 0.6217 ✓

By perturbation family:
| family | numerator / 224 | rate |
|---|---|---:|
| ORDER_CHANGE | 188 / 224 | 0.8393 |
| SERVICE_TIME | 110 / 224 | 0.4911 |
| TIME_WINDOW  | 134 / 224 | 0.5982 |
| TRAVEL_TIME  | 125 / 224 | 0.5580 |

Every family individually exceeds the 0.20 threshold. The decoupling phenomenon is alive and well across the grid; the 18-instance projection (0.580) was conservative — the full 56-instance pool measures 0.62. **§12.5 PASS with substantial margin.**

---

## Summary of failures (surface for review)

1. **§12.1 OBJ × TIME_WINDOW = 1.0000.** Above 0.90 ceiling. Per §12.6 §12.1-clause, the prescribed revision is Appendix A.2 TIME_WINDOW escalation (replace the soft_grid with the escalated grid). **Not auto-applied — surfaced.**
2. **§12.1 OBJ × TRAVEL_TIME = 0.9727.** Above 0.90 ceiling. Per §12.6 §12.1-clause, the prescribed revision is Appendix A.1 TRAVEL_TIME escalation. **Not auto-applied — surfaced.**
3. **§12.1 OBJ × ORDER_CHANGE × PLAN_VALIDITY (Reading A only) = 0.0000.** Failure only under the literal §3.3-reuse_direct reading; passes under §13.1's cheap-action reading at 0.6696. **Surfaced as a prereg-wording ambiguity, not as a substantive failure** — the §3.3 wording appears to be a v0.5 carry-over (where OC's cheap action was reuse_direct), and the §13.1 cheap-action definition produces a sensible OC × PV signal. Clarification advisable before deciding whether to escalate OC's grid.

§12.2 and §12.5 both pass.

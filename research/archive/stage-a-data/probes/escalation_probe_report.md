# Stage A — Escalation diagnostic probe (TT / TW)

**Date:** 2026-05-14
**Probe runner:** `scripts/run_escalation_probe.py`
**Outputs:**
- `data/probes/escalation_probe.parquet` (640 wide rows, sha256[:16] `689ec9984713be51`)
- `data/probes/escalation_probe_claim_rows.parquet` (2560 long rows, sha256[:16] `e4780bdf15e227db`)
- `data/probes/escalation_probe_checkpoints/run_stats.json`

**Status:** Diagnostic only — no Stage A artifact or prereg was modified. Does not apply the §12.6 revision procedure; this probe is the decision input for whether to apply it.

**Question:** Does the prereg's deterministic §12.6 §12.1-clause escalation (Appendix A.1 / A.2) move the two failing OBJ blocks into the locked label-distribution bracket `[0.10, 0.90]`, without overshoot on currently-passing blocks?

**Headline answer:** No. Escalation moves OBJ × TIME_WINDOW from 1.000 → 0.9625 and OBJ × TRAVEL_TIME from 0.948 (matched) / 0.973 (full pool) → 0.9342. Both remain **above** the 0.90 ceiling. The escalation does not overshoot dramatically — currently-passing PV / STRUCT / SCHEDULE blocks stay in `[0.10, 0.90]`, and only one extra TT cell becomes all-infeasible — but the single rung that the prereg permits (one substitution per block) is insufficient to clear the threshold.

---

## Step 0 — Quoted escalation spec (PREREG v1.1)

**Appendix A.1 — TRAVEL_TIME** (verbatim):
> Default soft_grid: TT_1 ×1.05, TT_2 ×1.10, TT_3 ×1.20, TT_4 ×1.30.
>
> | direction | revised multipliers | rationale |
> |---|---|---|
> | escalate | TT_1 ×1.10, TT_2 ×1.20, TT_3 ×1.30, TT_4 ×1.50 | block too positive: push harder |
> | de-escalate | TT_1 ×1.02, TT_2 ×1.05, TT_3 ×1.10, TT_4 ×1.20 | block too negative: ease off |

**Appendix A.2 — TIME_WINDOW** (verbatim):
> Default soft_grid: TW_1 tighten 5%, TW_2 tighten 10%, TW_3 shift 5%, TW_4 shift 5%.
>
> | direction | revised | rationale |
> |---|---|---|
> | escalate | TW_1 10%, TW_2 20%, TW_3 10%, TW_4 10% | block too positive |
> | de-escalate | TW_1 2%, TW_2 5%, TW_3 2%, TW_4 2% | block too negative |

**§12.6 §12.1-clause** (verbatim):
> **§12.1 failure (label distribution outside [0.10, 0.90]).** The offending block is mapped to the next severity level for its perturbation family (Appendix A). Increase severity if the block is too positive; decrease if too negative. Only one substitution per block is allowed.

**Determinism check.** Both failing blocks have easy-rate > 0.90 (too positive) → escalate. Appendix A defines a single escalation rung per family; only one substitution per block is permitted. The escalated grid is therefore fully specified and unique — the probe tests exactly the rung the prereg permits. No magnitudes other than what Appendix A specifies are tested.

The escalated magnitudes coincide with the package constants `PERTURBATION_MAGNITUDES` (the v1 default, unchanged across versions); Stage A used `SOFT_PERTURBATION_MAGNITUDES`. The probe sets `magnitude_override` to `PERTURBATION_MAGNITUDES[pid]` for each TT/TW perturbation.

---

## Step 1 — Stratified sample

- 56-instance Stage A pool composition: **C=17, R=23, RC=16**.
- Probe target n=20, stratified in matched proportion: **C=6, R=8, RC=6**.
- Within-class selection: `random.Random(42).sample(...)`. **Sample seed: 42** (recorded in `run_stats.json`).
- Cells: 20 instances × 8 perturbations (TT_1..TT_4, TW_1..TW_4) = **160 cells**, all four magnitudes per family. References at PyVRP 120 s, seeds 1/2/3 (v1.1 protocol).

**Selected instances (sorted within class):**
```
C : C101 C104 C105 C203 C204 C208
R : R101 R102 R103 R104 R105 R202 R206 R207
RC: RC101 RC103 RC104 RC201 RC202 RC207
```

---

## Step 2 — Method

For each sampled cell:
1. Load the unperturbed instance and the cached 60 s baseline (same baseline file used by Stage A — perturbed-instance generation is baseline-aware).
2. Apply the perturbation at the **escalated magnitude** from Step 0.
3. Solve references with `solve_vrptw` at 120 s × seeds (1, 2, 3).
4. Run the **expanded action portfolio** for non-OC families: `reuse_direct`, `construct_feasible`, `pyvrp_10s`, `pyvrp_60s_reference` (materialized from reference seed 1).
5. Compute `LossBundle` and bands via `compute_losses`, mirroring `scripts/run_vrptw_scale_check._build_wide_row` 1-for-1. Schema is consolidated-compatible (same column names and dtypes).

**Run cost.** 480 reference solves (160 cells × 3 seeds) at 120 s with `n_jobs=6`: 160 min wall (9602.7 s). pyvrp_10s phase 4.5 min. Assembly 20 s. **Total ≈ 165 min.** 0 reference failures, 0 pyvrp_10s failures, 0 action failures.

---

## Step 3 — Escalated label distribution (per-block easy-rate, cheap-action rows)

Bracket = `[0.10, 0.90]`. Cheap action for TT/TW is `reuse_direct` (§13.1 / §3.3 agree on non-OC families, so the ambiguity flagged in §12.1 verification does not apply here). Denominator = cells with `band != 'n/a'` (defined-denominator rule from PREREG v1.1 §12.3 analog).

| block (escalated) | easy / n | rate | verdict |
|---|---:|---:|---|
| `OBJ × TIME_WINDOW` | 77 / 80 | **0.9625** | **FAIL** (> 0.90) |
| `PLAN_VALIDITY × TIME_WINDOW` | 24 / 80 | 0.3000 | pass |
| `STRUCT × TIME_WINDOW` | 42 / 80 | 0.5250 | pass |
| `SCHEDULE × TIME_WINDOW` | 29 / 80 | 0.3625 | pass |
| `OBJ × TRAVEL_TIME` | 71 / 76 | **0.9342** | **FAIL** (> 0.90) |
| `PLAN_VALIDITY × TRAVEL_TIME` | 25 / 80 | 0.3125 | pass |
| `STRUCT × TRAVEL_TIME` | 44 / 76 | 0.5789 | pass |
| `SCHEDULE × TRAVEL_TIME` | 32 / 76 | 0.4211 | pass |

**All-infeasible cells under escalated grid (per cell, n=80 per family):**

| family | all_infeasible | other | total |
|---|---:|---:|---:|
| `TIME_WINDOW` | 0 | 80 | 80 |
| `TRAVEL_TIME` | 4 | 76 | 80 |

Under TIME_WINDOW, no cells go all-infeasible. Under TRAVEL_TIME, 4 of 80 escalated cells are all-infeasible (5.0%). Three of these four were already all-infeasible in the matched soft sample — so escalation adds **+1** all-infeasible cell. This is a mild overshoot, not a structural one.

---

## Step 4 — Matched-sample soft vs escalated (same 20 instances)

To remove sampling variability from the comparison, soft-grid easy-rates are computed from `data/stage_a_vrptw_consolidated_claim_rows.parquet` restricted to **the same 20 sampled instances** and the same TT/TW perturbations. This is the apples-to-apples comparison; the matched-sample delta is the escalation effect.

| block | soft (matched, n=20) | escalated (n=20) | delta |
|---|---:|---:|---:|
| `OBJ × TIME_WINDOW` | 80/80 = **1.0000** FAIL | 77/80 = **0.9625** FAIL | −0.0375 |
| `PLAN_VALIDITY × TIME_WINDOW` | 37/80 = 0.4625 | 24/80 = 0.3000 | −0.1625 |
| `STRUCT × TIME_WINDOW` | 51/80 = 0.6375 | 42/80 = 0.5250 | −0.1125 |
| `SCHEDULE × TIME_WINDOW` | 38/80 = 0.4750 | 29/80 = 0.3625 | −0.1125 |
| `OBJ × TRAVEL_TIME` | 73/77 = **0.9481** FAIL | 71/76 = **0.9342** FAIL | −0.0138 |
| `PLAN_VALIDITY × TRAVEL_TIME` | 35/80 = 0.4375 | 25/80 = 0.3125 | −0.1250 |
| `STRUCT × TRAVEL_TIME` | 47/77 = 0.6104 | 44/76 = 0.5789 | −0.0314 |
| `SCHEDULE × TRAVEL_TIME` | 38/77 = 0.4935 | 32/76 = 0.4211 | −0.0725 |

Reference: on the **full** Stage A pool (n=56 instances), the failing blocks observed in `data/stage_a_vrptw_verification_report.md` were `OBJ × TW = 1.0000` (224/224) and `OBJ × TT = 0.9727` (214/220). The matched 20-instance soft sample reproduces the TW saturation exactly and shows TT at 0.9481 — sampling variability within the same Solomon-100 pool, but on the same side of the threshold.

**All-infeasible (matched soft vs escalated):**

| family | soft matched | escalated | overshoot |
|---|---:|---:|---:|
| `TIME_WINDOW` | 0/80 | 0/80 | 0 |
| `TRAVEL_TIME` | 3/80 | 4/80 | +1 |

---

## Step 5 — Verdict

> **Does the escalated grid bring OBJ × TIME_WINDOW into [0.10, 0.90]?** No. 1.0000 → 0.9625; still > 0.90.
>
> **Does the escalated grid bring OBJ × TRAVEL_TIME into [0.10, 0.90]?** No. 0.9481 (matched) → 0.9342; still > 0.90.
>
> **Does escalation knock any currently-passing block (PV / STRUCT / SCHEDULE × TT / TW) out of the bracket?** No. All six non-OBJ TT/TW blocks remain inside `[0.10, 0.90]` after escalation. Largest single-block drop: TW × PV by 0.16; smallest: TT × STRUCT by 0.03. Direction is consistent (harder perturbations → lower easy-rate) and all six stay above the 0.10 floor.
>
> **Does escalation overshoot into all-infeasible?** Marginally. TW: 0 / 80 stays at 0 / 80. TT: 3 / 80 → 4 / 80 (+1 cell). This is well below any structural overshoot threshold and does not alter the verdict.

**Net.** The single escalation rung permitted by the prereg (Appendix A.1 / A.2, one substitution per block, §12.6 §12.1-clause) moves OBJ × TW by −0.0375 and OBJ × TT by −0.0138 on a matched 20-instance sample. Both blocks remain saturated at the cheap-action `reuse_direct` level: under both grids, on Solomon-100 instances, the cheap action's distance vs the strongest reference seed clears the OBJ-easy band on > 93% of cells.

This is a **structural feature of the benchmark**, not a tunable. The cheap action for non-OC families is `reuse_direct`, which leaves the baseline routes unchanged. On Solomon-100, even at the escalated grid, the **baseline distance** vs the **best-of-three references on the perturbed instance** stays within the OBJ-easy band on > 93% of cells — i.e., the perturbed-instance optimum is still close enough to the baseline distance that `reuse_direct` is "good enough" by the prereg's locked OBJ band. The §12.6 procedure caps the operator at one substitution per block, so there is no further escalation rung to apply within the prereg's deterministic menu.

### Implications for §12.6 revision

The prereg permits exactly one §12.6 substitution per block. Applying the Appendix A escalation to TT and TW would (a) re-collect 448 cells worth of solve work (224 TT + 224 TW × full action portfolio) for a +0.04 / +0.01 nominal improvement on the failing rate, (b) still leave both blocks failing, and (c) consume the one permitted substitution, after which Stage A data must be re-collected (per §12.6 *"exactly one revision pass is permitted before Stage A data must be re-collected"*). The remaining options inside the locked prereg are:

- Apply the substitution anyway, accept the post-revision failure, and surface this as a **§12.1 residual failure** for adjudication outside the deterministic menu.
- Do not apply the substitution, surface the **pre-revision §12.1 failure** as a structural finding (the OBJ ceiling is too low for the cheap action's distance advantage on Solomon-100), and document.

Both options halt the deterministic procedure short of mutating Stage A's perturbed instances. The choice between them is outside the probe's scope.

---

## Reproducibility

- Probe runner: `scripts/run_escalation_probe.py`
- Seed: `random.Random(42)` for instance selection; PyVRP solver seeds 1, 2, 3 for references; PyVRP seed 1 for pyvrp_10s.
- PyVRP version: matches Stage A (baseline cache `pyvrp_version` field, written by `load_or_compute_baseline`).
- Baselines: cache hits on all 20 sampled instances (no recomputation).
- 60s baselines / 120s references / 10s pyvrp_10s — same time-limit ladder as Stage A's 256-cell re-collection.
- Resumable: every reference / pyvrp_10s / row checkpoint persisted under `data/probes/escalation_probe_checkpoints/` (480 ref + 160 pyvrp10s + 640 row JSONs).

## Integrity

The probe wrote only to `data/probes/`. Stage A wide / long parquets, the v1.0 and v1.1 prereg files, and `data/stage_a_vrptw_verification_report.md` are unmodified.

# Thesis Narrative Packet

_Consolidated writing reference for the LLM-in-the-loop VRPTW copilot PhD thesis.
Frozen at HEAD `18b4811` (tag `run2-contract-extended`). Created 2026-05-21._

This packet is **read-only** — it extracts numbers from existing reports; it
does not modify any benchmark case, gold label, system file, or test.

---

## Files

### Pre-Run-2 (Stage A sufficiency benchmark)

| File | Contents |
|---|---|
| `pre_run2_claim_family_design.md` | Three-axis decomposition; four claim family definitions (OBJ/PV/STRUCT/SCHEDULE); loss formulas; band thresholds; perturbation design rationale; action portfolio; predictor configuration; closing experiment design; key caveats |
| `claim_family_loss_table.csv` | Per-family: loss formula, band thresholds (easy/medium/hard), operational sufficiency rule, VRPTW-specific caveats, prereg section, source code reference |
| `perturbation_design_summary.csv` | All 16 perturbations (4 families × 4): selector, magnitude, what each stresses, claims most affected, design notes (cell counts, scaling factor, cheap-action mapping) |
| `action_ladder_summary.csv` | 5 actions: role, runtime, 18-instance easy-rates per family, deployment status, deployed thresholds from deployment_config.csv |
| `pre_run2_policy_results.csv` | Baseline policies (cheap_only, always_pyvrp_10s, block_rule, oracle); predictor vs baseline comparisons with bootstrap CIs; per-family AUROC; feature set descriptions; non-monotone preservation |

### Run 2 product-contract benchmark

| File | Contents |
|---|---|
| `run2_core_summary.csv` | R2-1 calibration, R2-2 expansion, R2-3 contract extensions — all headline numbers, benchmark distribution, metric definitions |
| `run2_model_baselines_summary.csv` | System B (60-case + pass^k) and System A (30-case + pass^k); B→A→C comparison; per-case migration table; main failure modes |
| `stress_axes_summary.csv` | Per-axis (1–4) case counts, split, systems evaluated, C0 headline metrics, main failure buckets, closeout interpretation, report paths |
| `cross_axis_failure_taxonomy.csv` | Unified taxonomy: 6 categories × total n × C0-only n; system-D-addressable case IDs; must-not-regress cohort; model-projection counts; schema gaps; out-of-envelope answerability |
| `system_d_progression_summary.csv` | C0 → D1 → D2 → D3 → D4 table: change locus, target failures, fixed count, core regressions, axis-4 regressions, test counts, protected-file status |
| `regression_summary.csv` | Test-by-test regression record across all surfaces and systems; total test suite counts |

### Synthesis and navigation

| File | Contents |
|---|---|
| `sufficiency_to_payload_contract_bridge.md` | Conceptual bridge: claim families → product intents; sufficiency → answerability/missing-fields/warnings; recompute routing → D4 compute_decision; three-axis → Run 2 metrics; benchmark lineage diagram |
| `artifact_index.md` | Grouped index of every source report used — path, one-sentence purpose, key numbers |
| `thesis_numbers.md` | Compact list of all numbers citable in prose: number, meaning, source, caveat |

---

## How to use

1. **Prose writing**: start with `thesis_numbers.md`. Every number has a
   source file you can open for the full context and a caveat to qualify in prose.

2. **Table / figure data**: the `*.csv` files are structured for direct import
   into pandas / R or for copy-paste into LaTeX. Column names are self-describing.

3. **Source verification**: `artifact_index.md` maps every entry back to the
   authoritative report in the repo. Open the source file to confirm context
   or pull additional detail.

4. **Regression / integrity check**: `regression_summary.csv` documents every
   regression test by surface and system; the bottom rows record total test
   suite counts.

---

## What this packet does NOT contain

- Any benchmark case, gold label, or scorer code — those are immutable locked
  files at `18b4811`.
- Any new analysis or derived claim not already in the source reports.
- Raw model outputs — those live under `product/evaluation/model_outputs/`.

---

## Source structure (for quick navigation)

```
product/evaluation/
  reports/                         # R2-1 → R2-6 evaluation reports
  run2_stress/
    axis1_lookalike/reports/       # Axis 1 closeout + C0 baseline
    axis2_ood_premises/reports/    # Axis 2 closeout + C0 baseline
    axis3_semantic/reports/        # Axis 3 closeout + C0 baseline
    axis4_payload/reports/         # Axis 4 closeout + C0/A/B baselines
    analysis/                      # Cross-axis synthesis + unified scatter
  system_d1/reports/               # D1 closeout + stress + core
  system_d2/reports/               # D2 closeout + stress + core
  system_d3/reports/               # D3 closeout + overlay gold + stress + core
  system_d4/reports/               # D4 closeout + decision report + D3 regression
  thesis_narrative_packet/         # ← this directory
```

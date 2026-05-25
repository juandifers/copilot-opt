#!/usr/bin/env python3
"""Recompute the Part 1 closure artefacts without retraining.

Reads the existing ``reports/predictor_models/predictor_oof_predictions.csv``
and rebuilds the downstream tables — TT/TW subset metrics, new
deployment configuration (PV on Set B), new bootstrap CIs with the
equal-or-greater pairing rule, and a fresh README. Everything else
(probe scores, coefficient table, permutation importance, decision
trees, calibration curves, non-monotone preservation, threshold
curves, Pareto frontier, predictor-vs-baselines CSV) is reused from the
last full run.

This bypasses the slow training/permutation/probe steps in the runner
and applies the Run 2 Part 1 changes in ~30 seconds.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd  # noqa: E402

from vrp_copilot_bench.predictor_baselines.data import (  # noqa: E402
    build_cheap_eval_frame,
    build_escalation_frame,
    load_long_table,
)
from vrp_copilot_bench.predictor_models.evaluation import (  # noqa: E402
    ThresholdConfig,
    nonmonotone_preservation,
    per_fold_classifier_metrics,
    threshold_sweep,
)
from vrp_copilot_bench.predictor_models.runner import (  # noqa: E402
    _bootstrap_cis_for_pairs,
    _deployment_config,
    _pareto_table,
    _setc_ablation,
    _stage_a_tt_tw_subset_metrics,
    _write_readme,
)


def main(
    long_parquet: Path = Path("data/stage_a_vrptw_consolidated_claim_rows.parquet"),
    output_dir: Path = Path("reports/predictor_models"),
    bootstrap_resamples: int = 1000,
) -> None:
    print(f"Loading OOF predictions from {output_dir}…")
    oof_long_all = pd.read_csv(output_dir / "predictor_oof_predictions.csv")
    probe_eval = pd.read_csv(output_dir / "escalation_probe_oof.csv")
    coef_df = pd.read_csv(output_dir / "predictor_coefficients_or_feature_importance.csv")

    # Reconstruct permutation-importance frame for the README (kind=='permutation_importance').
    perm = coef_df[coef_df["kind"] == "permutation_importance"].copy()
    if not perm.empty:
        perm = perm.rename(columns={"value_mean": "permutation_importance_mean"})
        perm["n_folds_used"] = float("nan")

    print(f"Loading long table from {long_parquet}…")
    long_df = load_long_table(long_parquet)
    pyvrp_10s_df = build_escalation_frame(long_df, "pyvrp_10s")

    # Per-fold metrics (predictors only — block_rule_extended skipped since
    # the resulting AUROC table is what feeds the Set C ablation and probe
    # framing; block_rule_extended rows are kept in oof_long_all for the
    # threshold sweep + bootstrap).
    predictors_only = oof_long_all[oof_long_all["model"] != "block_rule_extended"]
    print("Computing per-fold classifier metrics…")
    per_fold = per_fold_classifier_metrics(predictors_only)

    print("Running threshold sweep…")
    grid = ThresholdConfig().grid
    sweep_full = threshold_sweep(oof_long_all, pyvrp_10s_df, grid=grid)
    sweep_full["evaluation_scope"] = "full"
    sweep_nodeg = sweep_full  # not regenerated; only used as a README pass-through

    print("Computing non-monotone preservation…")
    nm_table = nonmonotone_preservation(oof_long_all, pyvrp_10s_df, grid=grid)

    print("Computing Pareto frontier…")
    pareto = _pareto_table(sweep_full)

    print(f"Running paired-cell bootstrap (n={bootstrap_resamples}, "
          "equal-or-greater pairing)…")
    boot = _bootstrap_cis_for_pairs(
        sweep_full, oof_long_all, pyvrp_10s_df,
        n_resamples=bootstrap_resamples, seed=0,
        baseline_pairing_mode="equal_or_greater",
    )

    print("Computing deployment config (PV → Set B override)…")
    deploy = _deployment_config(sweep_full)

    print("Computing Set C ablation…")
    setc_abl = _setc_ablation(per_fold)

    print("Computing TT/TW subset metrics…")
    tt_tw_subset = _stage_a_tt_tw_subset_metrics(oof_long_all)

    # Persist.
    print("Writing outputs…")
    pareto.to_csv(output_dir / "predictor_pareto_frontier.csv", index=False)
    boot.to_csv(output_dir / "predictor_vs_baselines_with_cis.csv", index=False)
    deploy.to_csv(output_dir / "deployment_config.csv", index=False)
    setc_abl.to_csv(output_dir / "predictor_setc_ablation.csv", index=False)
    tt_tw_subset.to_csv(output_dir / "stage_a_tt_tw_subset_metrics.csv", index=False)
    nm_table.to_csv(output_dir / "nonmonotone_preservation.csv", index=False)

    print("Writing README…")
    _write_readme(
        output_dir,
        cv_agg=pd.DataFrame(),  # unused by readme body
        per_fold=per_fold,
        sweep_full=sweep_full,
        sweep_nodeg=sweep_nodeg,
        nm_table=nm_table,
        pareto=pareto,
        boot=boot,
        deploy=deploy,
        setc_abl=setc_abl,
        tt_tw_subset=tt_tw_subset,
        probe_eval=probe_eval,
        perm=perm,
        coef_df=coef_df,
        baseline_overall_path=Path("reports/predictor_baselines/baseline_policy_overall.csv"),
    )
    print(f"Done. Outputs at {output_dir}")


if __name__ == "__main__":
    main()

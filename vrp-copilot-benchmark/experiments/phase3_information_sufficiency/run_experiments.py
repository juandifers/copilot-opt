"""Phase 3 driver — runs Experiments 1, 2, 3 end-to-end.

Reads:
  - phase3_config.yaml            for grid + paths + lambda values
  - reports/phase1/solutions.jsonl    for nominal PyVRP 60s baselines + capacity@{0.9, 0.8} references
  - reports/phase2/solutions.jsonl    for NN + Savings + PyVRP 10s actions
  - data/processed/phase2r/budget_check/*.json  for 5 mixed PyVRP 60s references
  - data/processed/phase3/pyvrp60s_reference.jsonl  for the freshly computed references

Writes (under experiments/phase3_information_sufficiency/artifacts/):
  Exp 1:
    phase3_reuse_direct_results.csv
    phase3_reuse_direct_metrics.json
  Exp 2:
    phase3_estimation_results.csv
    phase3_estimation_metrics.json
  Exp 3:
    phase3_lambda_curves.csv
    phase3_policy_summary.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from vrpbench.artifacts.solution import SolutionArtifact
from vrpbench.data.instance import load_instance

from experiments.phase3_information_sufficiency.artifact_index import (
    ArtifactKey,
    ArtifactIndex,
    build_default_index,
    load_jsonl,
)
from experiments.phase3_information_sufficiency.claim_metrics import (
    Phase3ClaimErrors,
    claim_errors,
    difficulty_label,
)
from experiments.phase3_information_sufficiency.reuse_direct import (
    answerability,
    evaluate_fixed_solution,
)


CLAIM_FAMILIES = (
    "objective_resource_delta",
    "topk_route_ranking",
    "assignment_structure",
)

REQUIRED_GRID = (
    ("capacity_reduction", 0.98, "cap0p98"),
    ("capacity_reduction", 0.95, "cap0p95"),
    ("capacity_reduction", 0.9, "cap0p9"),
    ("capacity_reduction", 0.8, "cap0p8"),
    ("regional_distance_inflation", 1.1, "regdist1p1"),
    ("regional_distance_inflation", 1.25, "regdist1p25"),
    ("regional_distance_inflation", 1.5, "regdist1p5"),
)

ACTIONS = ("reuse_direct", "nearest_neighbor", "clarke_wright", "pyvrp_10s", "pyvrp_60s")


# ----------------------------------------------------------------------
# Index assembly
# ----------------------------------------------------------------------

def assemble_index(repo: Path, ref_jsonl: Path) -> ArtifactIndex:
    """Build the unified index: prior phases + Phase 3 fresh references."""
    idx = build_default_index(repo)
    n_added = idx.ingest(load_jsonl(ref_jsonl))
    logging.getLogger("phase3").info(
        "loaded %d Phase 3 reference rows from %s", n_added, ref_jsonl
    )
    return idx


# ----------------------------------------------------------------------
# Provenance: a single git/tooling stamp shared by every row.
# ----------------------------------------------------------------------

def _git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _stamp(
    repo: Path, *, run_id: str, source_dataset: str, config_path: str,
) -> dict[str, Any]:
    import importlib.metadata
    try:
        pyvrp_v = importlib.metadata.version("pyvrp")
    except importlib.metadata.PackageNotFoundError:
        pyvrp_v = "unknown"
    return {
        "git_commit_hash": _git_commit(repo),
        "config_path": config_path,
        "source_dataset": source_dataset,
        "pyvrp_version": pyvrp_v,
        "phase3_run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ----------------------------------------------------------------------
# Experiment 1: reuse_direct
# ----------------------------------------------------------------------

def _scenario_to_path(repo: Path, iid: str, tag: str) -> Path:
    return repo / "data" / "processed" / "phase2" / "perturbed" / f"{iid}__{tag}.vrp"


def run_experiment_1(
    repo: Path, idx: ArtifactIndex, instances: list[str],
    out_dir: Path, stamp: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    log = logging.getLogger("phase3.exp1")
    rows: list[dict[str, Any]] = []
    miss_baseline: list[str] = []
    miss_reference: list[tuple[str, str]] = []

    for iid in instances:
        baseline = idx.get_pyvrp_at(iid, "nominal", 60.0)
        if baseline is None:
            miss_baseline.append(iid)
            continue

        for family, mag, tag in REQUIRED_GRID:
            scenario = f"{family}@{mag}"
            inst_path = _scenario_to_path(repo, iid, tag)
            if not inst_path.exists():
                log.warning("missing perturbed file: %s", inst_path)
                continue
            inst = load_instance(inst_path)

            ref = idx.get_pyvrp_at(iid, scenario, 60.0)
            if ref is None:
                miss_reference.append((iid, scenario))
                continue

            art = evaluate_fixed_solution(baseline, inst)
            ans = answerability(art)
            errs = claim_errors(art, ref, n_customers=inst.n_customers)
            feasible = bool(art.metadata.get("feasible_under_perturbation", False))

            for fam in CLAIM_FAMILIES:
                err = getattr(errs, fam)
                rows.append({
                    "instance_id": iid,
                    "scenario_id": f"{iid}|{scenario}",
                    "perturbation_family": family,
                    "perturbation_magnitude": mag,
                    "claim_family": fam,
                    "action": "reuse_direct",
                    "reference_backend": "pyvrp_60s",
                    "estimate_value": _claim_value_for(art, fam),
                    "reference_value": _claim_value_for(ref, fam),
                    "loss": err,
                    "error": err,
                    "answerable": ans[fam],
                    "feasible_under_perturbation": feasible,
                    "runtime_sec": float(art.runtime_sec),
                    "difficulty_label": difficulty_label(fam, err),
                    "n_customers": inst.n_customers,
                    "candidate_status": art.status,
                    "reference_status": ref.status,
                    "candidate_run_id": art.run_id,
                    "reference_run_id": ref.run_id,
                    "baseline_run_id": baseline.run_id,
                    "max_overload": float(art.metadata.get("max_overload", 0.0)),
                    "notes": "fixed-solution evaluation under perturbation",
                    **stamp,
                })

    out_csv = out_dir / "phase3_reuse_direct_results.csv"
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    log.info("wrote %s (%d rows)", out_csv, len(df))

    metrics = _summarize_action_table(df, action_label="reuse_direct")
    metrics.update({
        "n_instances": len(instances),
        "n_missing_baselines": len(miss_baseline),
        "missing_baselines": miss_baseline,
        "n_missing_references": len(miss_reference),
        "missing_references": miss_reference[:32],
        "n_total_rows": int(len(df)),
        **stamp,
    })
    metrics_path = out_dir / "phase3_reuse_direct_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("wrote %s", metrics_path)
    return out_csv, metrics


def _claim_value_for(art: SolutionArtifact, claim_family: str) -> float | None:
    """The 'estimate_value' / 'reference_value' field is family-specific.

    For objective: the scalar objective.
    For ranking / structure: encoded as the SolutionArtifact summary stats
    (n_routes for ranking; n_routes for assignment) — these are scalars
    that capture the gross structure but not the full distribution. The
    full structural comparison lives in the loss/error column already.
    """
    if claim_family == "objective_resource_delta":
        return float(art.objective) if art.objective is not None else None
    return float(art.n_routes) if art.n_routes is not None else None


def _summarize_action_table(df: pd.DataFrame, *, action_label: str) -> dict[str, Any]:
    """Summary stats per (claim_family, perturbation_family)."""
    if df.empty:
        return {"action": action_label, "summary": {}}
    out: dict[str, Any] = {"action": action_label, "by_claim_family": {}, "by_perturbation": {}}
    for fam in CLAIM_FAMILIES:
        sub = df[(df["claim_family"] == fam) & (df["error"].notna())]
        if sub.empty:
            out["by_claim_family"][fam] = {"n": 0}
            continue
        labels = sub["difficulty_label"].fillna("unknown").value_counts().to_dict()
        out["by_claim_family"][fam] = {
            "n": int(len(sub)),
            "mean_error": float(sub["error"].mean()),
            "median_error": float(sub["error"].median()),
            "p90_error": float(sub["error"].quantile(0.9)),
            "easy_pct": 100.0 * int(labels.get("easy", 0)) / len(sub),
            "medium_pct": 100.0 * int(labels.get("medium", 0)) / len(sub),
            "hard_pct": 100.0 * int(labels.get("hard", 0)) / len(sub),
            "infeasible_share": float((sub["feasible_under_perturbation"] == False).mean())
                if "feasible_under_perturbation" in sub.columns else None,
        }
    for pfam in df["perturbation_family"].dropna().unique().tolist():
        sub = df[df["perturbation_family"] == pfam]
        out["by_perturbation"][pfam] = {
            fam: {
                "n": int(((sub["claim_family"] == fam) & sub["error"].notna()).sum()),
                "mean_error": float(sub.loc[sub["claim_family"] == fam, "error"].mean())
                    if not sub.loc[sub["claim_family"] == fam, "error"].dropna().empty else None,
            }
            for fam in CLAIM_FAMILIES
        }
    return out


# ----------------------------------------------------------------------
# Experiment 2: reuse_with_estimation (NN + Clarke-Wright)
# ----------------------------------------------------------------------

def run_experiment_2(
    repo: Path, idx: ArtifactIndex, instances: list[str],
    out_dir: Path, stamp: dict[str, Any],
    *, reuse_csv: Path,
) -> tuple[Path, dict[str, Any]]:
    log = logging.getLogger("phase3.exp2")

    # Start with reuse_direct rows and add NN + CW rows.
    rows = pd.read_csv(reuse_csv).to_dict(orient="records")
    miss_action: list[tuple[str, str, str]] = []
    miss_reference: list[tuple[str, str]] = []

    for iid in instances:
        for family, mag, tag in REQUIRED_GRID:
            scenario = f"{family}@{mag}"
            inst_path = _scenario_to_path(repo, iid, tag)
            if not inst_path.exists():
                continue
            inst = load_instance(inst_path)
            ref = idx.get_pyvrp_at(iid, scenario, 60.0)
            if ref is None:
                miss_reference.append((iid, scenario))
                continue

            for action_name, backend_key in (
                ("nearest_neighbor", "nearest_neighbor"),
                ("clarke_wright", "savings"),
            ):
                cand = idx.get_cheap(iid, scenario, backend_key)
                if cand is None:
                    miss_action.append((iid, scenario, action_name))
                    continue
                errs = claim_errors(cand, ref, n_customers=inst.n_customers)
                feasible = (cand.status == "ok")
                for fam in CLAIM_FAMILIES:
                    err = getattr(errs, fam)
                    rows.append({
                        "instance_id": iid,
                        "scenario_id": f"{iid}|{scenario}",
                        "perturbation_family": family,
                        "perturbation_magnitude": mag,
                        "claim_family": fam,
                        "action": action_name,
                        "reference_backend": "pyvrp_60s",
                        "estimate_value": _claim_value_for(cand, fam),
                        "reference_value": _claim_value_for(ref, fam),
                        "loss": err,
                        "error": err,
                        "answerable": err is not None,
                        "feasible_under_perturbation": feasible,
                        "runtime_sec": float(cand.runtime_sec),
                        "difficulty_label": difficulty_label(fam, err),
                        "n_customers": inst.n_customers,
                        "candidate_status": cand.status,
                        "reference_status": ref.status,
                        "candidate_run_id": cand.run_id,
                        "reference_run_id": ref.run_id,
                        "baseline_run_id": "",
                        "max_overload": 0.0,
                        "notes": f"{action_name} on perturbed instance",
                        **stamp,
                    })

    df = pd.DataFrame(rows)
    out_csv = out_dir / "phase3_estimation_results.csv"
    df.to_csv(out_csv, index=False)
    log.info("wrote %s (%d rows, %d unique actions)",
             out_csv, len(df), df["action"].nunique())

    metrics = {
        "n_instances": len(instances),
        "n_missing_actions": len(miss_action),
        "missing_actions_sample": miss_action[:32],
        "n_missing_references": len(miss_reference),
        "by_action": {},
        **stamp,
    }
    for action in df["action"].unique().tolist():
        sub = df[df["action"] == action]
        metrics["by_action"][action] = _summarize_action_table(sub, action_label=action)
    out_json = out_dir / "phase3_estimation_metrics.json"
    out_json.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("wrote %s", out_json)
    return out_csv, metrics


# ----------------------------------------------------------------------
# Experiment 3: lambda sweep + best-action policy
# ----------------------------------------------------------------------

def run_experiment_3(
    repo: Path, idx: ArtifactIndex, instances: list[str],
    out_dir: Path, stamp: dict[str, Any],
    *, estimation_csv: Path, lambdas: list[float],
) -> tuple[Path, dict[str, Any]]:
    log = logging.getLogger("phase3.exp3")
    df = pd.read_csv(estimation_csv)

    # Augment with PyVRP 10s and PyVRP 60s actions: same per-claim-family
    # error definitions, computed against the PyVRP 60s reference. PyVRP 60s's
    # loss is therefore zero by construction (same artifact, same backend,
    # same time limit, same seed); we still compute it explicitly for
    # consistency.
    extra_rows: list[dict[str, Any]] = []
    for iid in instances:
        for family, mag, tag in REQUIRED_GRID:
            scenario = f"{family}@{mag}"
            inst_path = _scenario_to_path(repo, iid, tag)
            if not inst_path.exists():
                continue
            inst = load_instance(inst_path)
            ref = idx.get_pyvrp_at(iid, scenario, 60.0)
            if ref is None:
                continue
            for action_name, time_limit in (("pyvrp_10s", 10.0), ("pyvrp_60s", 60.0)):
                cand = idx.get_pyvrp_at(iid, scenario, time_limit)
                if cand is None:
                    continue
                errs = claim_errors(cand, ref, n_customers=inst.n_customers)
                feasible = (cand.status == "ok")
                for fam in CLAIM_FAMILIES:
                    err = getattr(errs, fam)
                    extra_rows.append({
                        "instance_id": iid,
                        "scenario_id": f"{iid}|{scenario}",
                        "perturbation_family": family,
                        "perturbation_magnitude": mag,
                        "claim_family": fam,
                        "action": action_name,
                        "reference_backend": "pyvrp_60s",
                        "estimate_value": _claim_value_for(cand, fam),
                        "reference_value": _claim_value_for(ref, fam),
                        "loss": err,
                        "error": err,
                        "answerable": err is not None,
                        "feasible_under_perturbation": feasible,
                        "runtime_sec": float(cand.runtime_sec),
                        "difficulty_label": difficulty_label(fam, err),
                        "n_customers": inst.n_customers,
                        "candidate_status": cand.status,
                        "reference_status": ref.status,
                        "candidate_run_id": cand.run_id,
                        "reference_run_id": ref.run_id,
                        "baseline_run_id": "",
                        "max_overload": 0.0,
                        "notes": f"{action_name} on perturbed instance",
                        **stamp,
                    })
    if extra_rows:
        df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    # Build the per-cell action table: rows indexed by (instance, scenario,
    # claim_family), columns are actions, values are (loss, runtime).
    rows: list[dict[str, Any]] = []
    cells = df[["instance_id", "scenario_id", "perturbation_family",
                "perturbation_magnitude", "claim_family"]].drop_duplicates()
    pivot_loss = df.pivot_table(
        index=["instance_id", "scenario_id", "perturbation_family",
               "perturbation_magnitude", "claim_family"],
        columns="action", values="error", aggfunc="first",
    )
    pivot_runtime = df.pivot_table(
        index=["instance_id", "scenario_id", "perturbation_family",
               "perturbation_magnitude", "claim_family"],
        columns="action", values="runtime_sec", aggfunc="first",
    )

    available_actions = [a for a in ACTIONS if a in pivot_loss.columns]
    log.info("actions available in pivot: %s", available_actions)

    big_inf = float("inf")

    for key, loss_row in pivot_loss.iterrows():
        rt_row = pivot_runtime.loc[key]
        instance_id, scenario_id, perturbation_family, perturbation_magnitude, claim_family = key

        for lam in lambdas:
            scored: dict[str, float] = {}
            for a in available_actions:
                loss = loss_row.get(a)
                rt = rt_row.get(a)
                if loss is None or (isinstance(loss, float) and math.isnan(loss)):
                    continue
                if rt is None or (isinstance(rt, float) and math.isnan(rt)):
                    continue
                scored[a] = float(loss) + lam * float(rt)
            if not scored:
                continue
            best_action = min(scored, key=scored.get)
            best_obj = scored[best_action]
            sorted_actions = sorted(scored.items(), key=lambda kv: kv[1])
            runner_up = sorted_actions[1][0] if len(sorted_actions) > 1 else None
            runner_up_obj = sorted_actions[1][1] if len(sorted_actions) > 1 else None

            row = {
                "lambda": lam,
                "instance_id": instance_id,
                "scenario_id": scenario_id,
                "claim_family": claim_family,
                "perturbation_family": perturbation_family,
                "perturbation_magnitude": perturbation_magnitude,
                "best_action": best_action,
                "best_action_loss": float(loss_row[best_action]) if best_action in loss_row else None,
                "best_action_runtime": float(rt_row[best_action]) if best_action in rt_row else None,
                "objective_value": best_obj,
                "runner_up_action": runner_up,
                "runner_up_objective": runner_up_obj,
            }
            for a in ACTIONS:
                row[f"always_{a}_objective"] = scored.get(a, None)
            rows.append(row)

    curves_df = pd.DataFrame(rows)
    out_csv = out_dir / "phase3_lambda_curves.csv"
    curves_df.to_csv(out_csv, index=False)
    log.info("wrote %s (%d rows)", out_csv, len(curves_df))

    # Action-share summary by lambda × claim_family.
    summary: dict[str, Any] = {
        "lambdas": list(lambdas),
        "claim_families": list(CLAIM_FAMILIES),
        "actions": list(ACTIONS),
        "by_lambda_and_family": {},
        "by_lambda_overall": {},
        **stamp,
    }
    for lam in lambdas:
        for fam in CLAIM_FAMILIES:
            sub = curves_df[(curves_df["lambda"] == lam) & (curves_df["claim_family"] == fam)]
            if sub.empty:
                continue
            shares = (sub["best_action"].value_counts(normalize=True) * 100).to_dict()
            summary["by_lambda_and_family"][f"{lam}|{fam}"] = {
                "n": int(len(sub)),
                "shares_pct": {a: float(shares.get(a, 0.0)) for a in ACTIONS},
                "mean_objective": float(sub["objective_value"].mean()),
            }
        sub_all = curves_df[curves_df["lambda"] == lam]
        if not sub_all.empty:
            shares = (sub_all["best_action"].value_counts(normalize=True) * 100).to_dict()
            summary["by_lambda_overall"][f"{lam}"] = {
                "n": int(len(sub_all)),
                "shares_pct": {a: float(shares.get(a, 0.0)) for a in ACTIONS},
            }

    out_json = out_dir / "phase3_policy_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))
    log.info("wrote %s", out_json)
    return out_csv, summary


# ----------------------------------------------------------------------
# Top-level driver
# ----------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        default="experiments/phase3_information_sufficiency/phase3_config.yaml",
    )
    ap.add_argument("--repo-root", default=".")
    ap.add_argument(
        "--skip-experiment",
        action="append",
        default=[],
        help="Optional: skip 1, 2, or 3 (e.g. --skip-experiment 3)",
    )
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    cfg = yaml.safe_load(Path(args.config).read_text())
    out_dir = repo / cfg["outputs"]["results_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_jsonl = repo / cfg["outputs"]["reference_jsonl"]
    idx = assemble_index(repo, ref_jsonl)

    import csv as _csv
    with (repo / cfg["instances"]["registry_csv"]).open() as f:
        reader = _csv.DictReader(f)
        instances = [r["instance_id"] for r in reader if r["parse_ok"] == "True"]
    instances = instances[: int(cfg["instances"]["max_instances"])]

    import uuid
    run_id = uuid.uuid4().hex[:12]
    stamp = _stamp(
        repo,
        run_id=run_id,
        source_dataset="cvrplib_uchoa_X_15",
        config_path=str(args.config),
    )

    if "1" not in args.skip_experiment:
        reuse_csv, _ = run_experiment_1(repo, idx, instances, out_dir, stamp)
    else:
        reuse_csv = out_dir / "phase3_reuse_direct_results.csv"

    if "2" not in args.skip_experiment:
        est_csv, _ = run_experiment_2(repo, idx, instances, out_dir, stamp,
                                      reuse_csv=reuse_csv)
    else:
        est_csv = out_dir / "phase3_estimation_results.csv"

    if "3" not in args.skip_experiment:
        run_experiment_3(repo, idx, instances, out_dir, stamp,
                         estimation_csv=est_csv,
                         lambdas=list(cfg["lambda_grid"]["values"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

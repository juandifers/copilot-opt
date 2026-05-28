"""Rebuild a per-(instance, scenario, claim_family, action) loss/runtime table.

Every robustness analysis consumes this. We do NOT touch the existing
Phase 3 ``run_experiments.py`` to avoid disturbing its outputs — instead
we rebuild the same table here, with the addition of an explicit
``feasible_under_perturbation`` flag for every action (not just
reuse_direct).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yaml

from vrpbench.data.instance import load_instance

from experiments.phase3_information_sufficiency.artifact_index import (
    ArtifactIndex,
    build_default_index,
    load_jsonl,
)
from experiments.phase3_information_sufficiency.claim_metrics import (
    claim_errors,
    difficulty_label,
)
from experiments.phase3_information_sufficiency.reuse_direct import (
    evaluate_fixed_solution,
)


CLAIM_FAMILIES = (
    "objective_resource_delta",
    "topk_route_ranking",
    "assignment_structure",
)
ACTIONS = ("reuse_direct", "nearest_neighbor", "clarke_wright", "pyvrp_10s", "pyvrp_60s")
REQUIRED_GRID = (
    ("capacity_reduction", 0.98, "cap0p98"),
    ("capacity_reduction", 0.95, "cap0p95"),
    ("capacity_reduction", 0.9, "cap0p9"),
    ("capacity_reduction", 0.8, "cap0p8"),
    ("regional_distance_inflation", 1.1, "regdist1p1"),
    ("regional_distance_inflation", 1.25, "regdist1p25"),
    ("regional_distance_inflation", 1.5, "regdist1p5"),
)


def _scenario_to_path(repo: Path, iid: str, tag: str) -> Path:
    return repo / "data" / "processed" / "phase2" / "perturbed" / f"{iid}__{tag}.vrp"


def assemble_index(repo: Path, ref_jsonl: Path) -> ArtifactIndex:
    idx = build_default_index(repo)
    idx.ingest(load_jsonl(ref_jsonl))
    return idx


def build_action_table(
    repo: Path,
    cfg_path: Path,
    *,
    instances: list[str] | None = None,
) -> pd.DataFrame:
    """Build a long-form per-(cell, claim, action) table.

    Columns:
      instance_id, scenario_id, perturbation_family, perturbation_magnitude,
      claim_family, action, loss, runtime_sec,
      feasible_under_perturbation (bool), candidate_status, n_customers,
      max_overload (only meaningful for reuse_direct, else 0).
    """
    log = logging.getLogger("phase3.robustness.action_table")
    cfg = yaml.safe_load(cfg_path.read_text())
    ref_jsonl = repo / cfg["outputs"]["reference_jsonl"]
    idx = assemble_index(repo, ref_jsonl)
    log.info("artifact index size = %d", len(idx))

    if instances is None:
        import csv as _csv
        with (repo / cfg["instances"]["registry_csv"]).open() as f:
            reader = _csv.DictReader(f)
            instances = [r["instance_id"] for r in reader if r["parse_ok"] == "True"]
        instances = instances[: int(cfg["instances"]["max_instances"])]

    rows: list[dict] = []
    for iid in instances:
        baseline = idx.get_pyvrp_at(iid, "nominal", 60.0)
        if baseline is None:
            continue

        for family, mag, tag in REQUIRED_GRID:
            scenario = f"{family}@{mag}"
            scenario_id = f"{iid}|{scenario}"
            inst_path = _scenario_to_path(repo, iid, tag)
            if not inst_path.exists():
                continue
            inst = load_instance(inst_path)
            n_cust = inst.n_customers

            ref = idx.get_pyvrp_at(iid, scenario, 60.0)
            if ref is None:
                continue

            # ---- reuse_direct ----
            rd_art = evaluate_fixed_solution(baseline, inst)
            rd_errs = claim_errors(rd_art, ref, n_customers=n_cust)
            rd_feas = bool(rd_art.metadata.get("feasible_under_perturbation", False))
            for fam in CLAIM_FAMILIES:
                err = getattr(rd_errs, fam)
                rows.append({
                    "instance_id": iid, "scenario_id": scenario_id,
                    "perturbation_family": family,
                    "perturbation_magnitude": mag,
                    "claim_family": fam, "action": "reuse_direct",
                    "loss": err, "runtime_sec": float(rd_art.runtime_sec),
                    "feasible_under_perturbation": rd_feas,
                    "candidate_status": rd_art.status,
                    "n_customers": n_cust,
                    "max_overload": float(rd_art.metadata.get("max_overload", 0.0)),
                    "difficulty_label": difficulty_label(fam, err),
                })

            # ---- cheap estimators ----
            for action_name, backend_key in (
                ("nearest_neighbor", "nearest_neighbor"),
                ("clarke_wright", "savings"),
            ):
                cand = idx.get_cheap(iid, scenario, backend_key)
                if cand is None:
                    continue
                errs = claim_errors(cand, ref, n_customers=n_cust)
                feas = (cand.status == "ok")
                for fam in CLAIM_FAMILIES:
                    err = getattr(errs, fam)
                    rows.append({
                        "instance_id": iid, "scenario_id": scenario_id,
                        "perturbation_family": family,
                        "perturbation_magnitude": mag,
                        "claim_family": fam, "action": action_name,
                        "loss": err, "runtime_sec": float(cand.runtime_sec),
                        "feasible_under_perturbation": feas,
                        "candidate_status": cand.status,
                        "n_customers": n_cust,
                        "max_overload": 0.0,
                        "difficulty_label": difficulty_label(fam, err),
                    })

            # ---- recompute ----
            for action_name, time_limit in (("pyvrp_10s", 10.0), ("pyvrp_60s", 60.0)):
                cand = idx.get_pyvrp_at(iid, scenario, time_limit)
                if cand is None:
                    continue
                errs = claim_errors(cand, ref, n_customers=n_cust)
                feas = (cand.status == "ok")
                for fam in CLAIM_FAMILIES:
                    err = getattr(errs, fam)
                    rows.append({
                        "instance_id": iid, "scenario_id": scenario_id,
                        "perturbation_family": family,
                        "perturbation_magnitude": mag,
                        "claim_family": fam, "action": action_name,
                        "loss": err, "runtime_sec": float(cand.runtime_sec),
                        "feasible_under_perturbation": feas,
                        "candidate_status": cand.status,
                        "n_customers": n_cust,
                        "max_overload": 0.0,
                        "difficulty_label": difficulty_label(fam, err),
                    })

    df = pd.DataFrame(rows)
    log.info("action table: %d rows, %d unique cells, %d actions",
             len(df),
             df.groupby(["instance_id", "scenario_id", "claim_family"]).ngroups,
             df["action"].nunique())
    return df


def lambda_sweep(
    action_df: pd.DataFrame,
    *,
    lambdas: list[float],
    action_order: list[str] = list(ACTIONS),
) -> pd.DataFrame:
    """Compute best_action per (cell, claim, lambda) given a long-form table.

    ``loss`` of NaN means the action is unanswerable on that cell and is
    excluded from the action set for that cell. The tie-breaking rule
    follows ``action_order`` (lowest-index wins ties).
    """
    rows = []
    grp = action_df.groupby(
        ["instance_id", "scenario_id", "perturbation_family",
         "perturbation_magnitude", "claim_family"], dropna=False,
    )
    order_rank = {a: i for i, a in enumerate(action_order)}

    for key, sub in grp:
        instance_id, scenario_id, perturbation_family, perturbation_magnitude, claim_family = key
        # Build action -> (loss, runtime). Drop rows whose loss is NaN.
        usable = sub[sub["loss"].notna() & sub["runtime_sec"].notna()]
        if usable.empty:
            continue
        action_to_lr = dict(zip(usable["action"], zip(usable["loss"], usable["runtime_sec"])))
        for lam in lambdas:
            objs = {a: float(l) + lam * float(r) for a, (l, r) in action_to_lr.items()}
            # Tie-break: pick the action that comes first in action_order.
            best_action = min(objs, key=lambda a: (objs[a], order_rank.get(a, 99)))
            best_loss = float(action_to_lr[best_action][0])
            best_runtime = float(action_to_lr[best_action][1])
            row = {
                "lambda": lam, "instance_id": instance_id,
                "scenario_id": scenario_id, "claim_family": claim_family,
                "perturbation_family": perturbation_family,
                "perturbation_magnitude": perturbation_magnitude,
                "best_action": best_action,
                "best_action_loss": best_loss,
                "best_action_runtime": best_runtime,
                "objective_value": objs[best_action],
            }
            for a in action_order:
                row[f"always_{a}_objective"] = objs.get(a, None)
            rows.append(row)

    return pd.DataFrame(rows)

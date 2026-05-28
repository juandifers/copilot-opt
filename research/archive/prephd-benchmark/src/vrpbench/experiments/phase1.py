"""Phase 1 pilot runner.

For each registry instance:
  - solve with the cheap backend (nearest-neighbor)
  - solve with the strong backend (PyVRP, fixed seed + time limit)
  - apply each enabled perturbation (capacity reduction) and re-solve with both
  - emit SolutionArtifacts to solutions.jsonl
  - emit comparisons to comparisons.csv
  - emit activation rows to activation.csv

The final report is generated separately from these tables.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import pandas as pd
import yaml

from ..artifacts.solution import SolutionArtifact
from ..backends.nearest_neighbor import solve_nearest_neighbor
from ..backends.pyvrp_backend import solve_pyvrp
from ..data.instance import load_instance
from ..evaluation.activation import (
    screen_perturbation,
    screen_backend_disagreement,
)
from ..evaluation.metrics import compare

logger = logging.getLogger(__name__)


def _append_artifact(path: Path, art: SolutionArtifact) -> None:
    with path.open("a") as f:
        f.write(art.model_dump_json() + "\n")


def _instance_ids_from_registry(registry_csv: Path) -> list[str]:
    df = pd.read_csv(registry_csv)
    df = df[df["parse_ok"]]
    return df["instance_id"].tolist()


def run_phase1(config_path: Path, *, repo_root: Path, registry_csv: Path) -> dict:
    cfg = yaml.safe_load(config_path.read_text())

    outputs = cfg["outputs"]
    solutions_path = repo_root / outputs["solutions_file"]
    comparisons_path = repo_root / outputs["comparisons_file"]
    activation_path = repo_root / outputs["activation_file"]
    for p in (solutions_path, comparisons_path, activation_path):
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()

    # Scratch dir for perturbed .vrp files
    scratch = repo_root / "data" / "processed" / "perturbed"
    scratch.mkdir(parents=True, exist_ok=True)

    cheap_cfg = cfg["backends"]["cheap"]
    strong_cfg = cfg["backends"]["strong"]["params"]
    seeds: list[int] = list(strong_cfg.get("seeds", [1]))
    time_limit = float(strong_cfg.get("time_limit_sec", 60))
    cap_cfg = cfg["perturbations"]["capacity_reduction"]
    cap_enabled = bool(cap_cfg.get("enabled", False))
    cap_factors = list(cap_cfg.get("factors", [])) if cap_enabled else []

    ids = _instance_ids_from_registry(registry_csv)
    logger.info("Phase 1 pilot over %d instances; seeds=%s; time_limit=%.1fs; "
                "capacity factors=%s", len(ids), seeds, time_limit, cap_factors)

    # Lazily import inside runner to keep top-level fast
    from ..perturbations.capacity import apply_capacity_reduction

    comparisons: list[dict] = []
    activations: list[dict] = []

    for idx, iid in enumerate(ids, start=1):
        vrp_path = repo_root / "data" / "raw" / "cvrplib" / f"{iid}.vrp"
        inst = load_instance(vrp_path)
        logger.info("[%d/%d] %s (n=%d, cap=%.0f, BKS=%s)",
                    idx, len(ids), iid, inst.n_customers, inst.capacity,
                    f"{inst.bks_objective:.1f}" if inst.bks_objective else "-")

        # Nominal runs
        t0 = time.perf_counter()
        nn_art = solve_nearest_neighbor(inst)
        logger.info("  nn: status=%s obj=%s routes=%s (%.2fs)",
                    nn_art.status, nn_art.objective, nn_art.n_routes,
                    nn_art.runtime_sec)
        _append_artifact(solutions_path, nn_art)

        pyvrp_arts: list[SolutionArtifact] = []
        for seed in seeds:
            p_art = solve_pyvrp(inst, seed=seed, time_limit_sec=time_limit)
            logger.info("  pyvrp seed=%d status=%s obj=%s routes=%s (%.1fs)",
                        seed, p_art.status, p_art.objective, p_art.n_routes,
                        p_art.runtime_sec)
            _append_artifact(solutions_path, p_art)
            pyvrp_arts.append(p_art)
        # Use first seed as the canonical Phase 1 artifact.
        pyvrp_art = pyvrp_arts[0]

        # Cheap vs strong comparison + backend-disagreement gate
        cmp_cs = compare(nn_art, pyvrp_art,
                         n_customers=inst.n_customers,
                         bks_objective=inst.bks_objective)
        cmp_cs_row = cmp_cs.as_row()
        cmp_cs_row["scenario"] = "nominal"
        comparisons.append(cmp_cs_row)

        act_backend = screen_backend_disagreement(
            nn_art, pyvrp_art, n_customers=inst.n_customers,
        )
        act_backend_row = act_backend.as_row()
        act_backend_row["scenario"] = "nominal"
        activations.append(act_backend_row)

        # Perturbations
        for factor in cap_factors:
            try:
                pert_path, _new_cap = apply_capacity_reduction(inst, factor, scratch)
            except Exception as e:
                logger.error("  capacity perturbation factor=%.2f failed: %s", factor, e)
                continue

            nn_pert = solve_nearest_neighbor(load_instance(pert_path))
            # re-label perturbed artifact with base instance id but flag scenario
            nn_pert.instance_id = inst.instance_id
            nn_pert.metadata["scenario"] = f"capacity_reduction@{factor}"
            _append_artifact(solutions_path, nn_pert)

            pyvrp_pert = solve_pyvrp(
                inst, seed=seeds[0], time_limit_sec=time_limit,
                instance_path_override=pert_path,
            )
            pyvrp_pert.metadata["scenario"] = f"capacity_reduction@{factor}"
            _append_artifact(solutions_path, pyvrp_pert)

            logger.info("  perturb cap*%.2f: nn obj=%s routes=%s | pyvrp obj=%s routes=%s",
                        factor, nn_pert.objective, nn_pert.n_routes,
                        pyvrp_pert.objective, pyvrp_pert.n_routes)

            # Perturbation activation (per backend)
            for baseline, perturbed in ((nn_art, nn_pert), (pyvrp_art, pyvrp_pert)):
                tag = f"capacity_reduction@{factor}:{baseline.backend_name}"
                row = screen_perturbation(
                    baseline, perturbed, n_customers=inst.n_customers, tag=tag,
                )
                r = row.as_row()
                r["scenario"] = f"capacity_reduction@{factor}"
                activations.append(r)

            # Perturbed cheap-vs-strong comparison (observability, not activation)
            cmp_pert = compare(nn_pert, pyvrp_pert, n_customers=inst.n_customers)
            cp_row = cmp_pert.as_row()
            cp_row["scenario"] = f"capacity_reduction@{factor}"
            comparisons.append(cp_row)

        logger.info("  instance total %.1fs", time.perf_counter() - t0)

    pd.DataFrame(comparisons).to_csv(comparisons_path, index=False)
    pd.DataFrame(activations).to_csv(activation_path, index=False)
    logger.info("Wrote %s (%d rows)", comparisons_path, len(comparisons))
    logger.info("Wrote %s (%d rows)", activation_path, len(activations))

    return {
        "solutions_file": str(solutions_path),
        "comparisons_file": str(comparisons_path),
        "activation_file": str(activation_path),
        "n_instances": len(ids),
        "n_comparisons": len(comparisons),
        "n_activation_rows": len(activations),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/phase1_pilot.yaml")
    ap.add_argument("--registry", default="data/processed/instance_registry.csv")
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    result = run_phase1(
        Path(args.config),
        repo_root=Path(args.repo_root).resolve(),
        registry_csv=Path(args.registry),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

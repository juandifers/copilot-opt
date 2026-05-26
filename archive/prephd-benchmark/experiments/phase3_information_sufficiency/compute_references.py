"""Compute fresh PyVRP 60s references for missing (instance, scenario) cells.

Phase 3 reference is locked at PyVRP @ 60s, seed=1, round_func='round'.
The runtime budget is 60s per cell. Phase 1 and Phase 2R budget_check
already populated 50 of the 120 cells in the 15-instance × 8-scenario
grid; this script fills the remaining 70.

Outputs append to ``data/processed/phase3/pyvrp60s_reference.jsonl``.
The file is treated as a write-once log: re-running will append duplicates,
so callers should clear or de-duplicate by (instance_id, scenario, run_id)
on read.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import yaml

from vrpbench.backends.pyvrp_backend import solve_pyvrp
from vrpbench.data.instance import load_instance

from experiments.phase3_information_sufficiency.artifact_index import (
    build_default_index,
)


REQUIRED_SCENARIOS = (
    ("nominal", None, None),
    ("capacity_reduction", 0.98, "cap0p98"),
    ("capacity_reduction", 0.95, "cap0p95"),
    ("capacity_reduction", 0.9, "cap0p9"),
    ("capacity_reduction", 0.8, "cap0p8"),
    ("regional_distance_inflation", 1.1, "regdist1p1"),
    ("regional_distance_inflation", 1.25, "regdist1p25"),
    ("regional_distance_inflation", 1.5, "regdist1p5"),
)


def _scenario_key(family: str | None, magnitude: float | None) -> str:
    if family is None or family == "nominal":
        return "nominal"
    return f"{family}@{magnitude}"


def _load_instance_for_cell(
    repo: Path, instance_id: str, family: str, tag: str | None
) -> Path:
    if family == "nominal":
        return repo / "data" / "raw" / "cvrplib" / f"{instance_id}.vrp"
    if tag is None:
        raise ValueError(f"non-nominal scenario {family} requires a tag")
    return repo / "data" / "processed" / "phase2" / "perturbed" / f"{instance_id}__{tag}.vrp"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("phase3.compute_references")

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        default="experiments/phase3_information_sufficiency/phase3_config.yaml",
    )
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--time-limit-sec", type=float, default=60.0)
    ap.add_argument(
        "--instances",
        nargs="*",
        help="optional subset of instance_ids to run (default: all in registry)",
    )
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    cfg = yaml.safe_load(Path(args.config).read_text())

    out_path = repo / cfg["outputs"]["reference_jsonl"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    idx = build_default_index(repo)
    log.info("loaded artifact index size=%d", len(idx))

    # Enumerate the grid and pick the cells that are missing.
    import csv

    with (repo / cfg["instances"]["registry_csv"]).open() as f:
        reader = csv.DictReader(f)
        instances = [r["instance_id"] for r in reader if r["parse_ok"] == "True"]
    if args.instances:
        instances = [iid for iid in instances if iid in set(args.instances)]

    todo: list[tuple[str, str, float | None, str | None]] = []  # (iid, family, mag, tag)
    skipped = 0
    for iid in instances:
        for family, mag, tag in REQUIRED_SCENARIOS:
            scenario = _scenario_key(family, mag)
            if idx.get_pyvrp_at(iid, scenario, args.time_limit_sec) is not None:
                skipped += 1
                continue
            todo.append((iid, family, mag, tag))

    log.info("PyVRP %.0fs reference cells: skipping %d (already present), running %d",
             args.time_limit_sec, skipped, len(todo))
    log.info("estimated wall-clock: %.1f min", len(todo) * args.time_limit_sec / 60.0)

    n_done = 0
    t_start = time.perf_counter()
    with out_path.open("a") as out_f:
        for iid, family, mag, tag in todo:
            scenario = _scenario_key(family, mag)
            inst_path = _load_instance_for_cell(repo, iid, family, tag)
            base_inst = load_instance(
                repo / "data" / "raw" / "cvrplib" / f"{iid}.vrp"
            )
            if family != "nominal":
                inst_for_solve = base_inst  # base instance is the carrier of instance_id
                override_path = inst_path
            else:
                inst_for_solve = base_inst
                override_path = None

            t0 = time.perf_counter()
            art = solve_pyvrp(
                inst_for_solve,
                seed=args.seed,
                time_limit_sec=args.time_limit_sec,
                instance_path_override=override_path,
            )
            elapsed = time.perf_counter() - t0
            # Tag scenario in metadata so the reference jsonl matches the
            # convention used by Phase 1/2 solutions.jsonl files.
            art.metadata = {**(art.metadata or {}), "scenario": scenario}
            out_f.write(art.model_dump_json() + "\n")
            out_f.flush()
            n_done += 1
            log.info(
                "[%d/%d] %s | %s | obj=%.1f status=%s elapsed=%.1fs",
                n_done, len(todo), iid, scenario,
                art.objective if art.objective is not None else float("nan"),
                art.status, elapsed,
            )

    total = time.perf_counter() - t_start
    log.info("Done. wrote %d new reference rows to %s in %.1f min",
             n_done, out_path, total / 60.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One-shot driver: build action table → run all 6 robustness sections.

Reads phase3_config.yaml for the lambda grid + dataset paths.
Writes everything to artifacts/robustness/ and PHASE3_ROBUSTNESS_SUMMARY.md.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from experiments.phase3_information_sufficiency.robustness import (
    capacity_only,
    distance_only,
    feasibility_penalty,
    feasibility_split,
    tie_audit,
    write_summary,
)
from experiments.phase3_information_sufficiency.robustness._action_table import (
    build_action_table,
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("phase3.robustness")

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        default="experiments/phase3_information_sufficiency/phase3_config.yaml",
    )
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    cfg = yaml.safe_load(Path(args.config).read_text())
    lambdas = list(cfg["lambda_grid"]["values"])

    out_dir = repo / cfg["outputs"]["results_dir"] / "robustness"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_md = repo / "experiments" / "phase3_information_sufficiency" / "PHASE3_ROBUSTNESS_SUMMARY.md"

    log.info("building per-(cell,claim,action) table ...")
    action_df = build_action_table(repo, Path(args.config))
    action_df.to_csv(out_dir / "_action_table.csv", index=False)

    log.info("section 1: feasibility split ...")
    feasibility_split.write_outputs(action_df, out_dir)

    log.info("section 2: feasibility-penalized λ curves ...")
    feasibility_penalty.write_outputs(action_df, out_dir, lambdas=lambdas)

    log.info("section 3: distance-only ...")
    distance_only.write_outputs(action_df, out_dir, lambdas=lambdas)

    log.info("section 4: capacity-only with feasibility ...")
    capacity_only.write_outputs(action_df, out_dir, lambdas=lambdas)

    log.info("section 5: tie audit ...")
    tie_audit.write_outputs(action_df, out_dir)

    log.info("section 6: writing PHASE3_ROBUSTNESS_SUMMARY.md ...")
    write_summary.write(out_dir, summary_md)

    log.info("done. outputs under %s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 0: data ingestion + instance inspection.

Run:
    python -m vrpbench.experiments.phase0
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd
import yaml

from ..data.acquire import acquire_pilot, already_has_vrp
from ..data.instance import build_registry, stratify
from ..evaluation.reporting import df_to_markdown

logger = logging.getLogger(__name__)


def run_phase0(config_path: Path, *, repo_root: Path) -> dict:
    with config_path.open() as f:
        cfg = yaml.safe_load(f)
    raw_dir = repo_root / cfg["raw_dir"]
    processed_dir = repo_root / cfg["processed_dir"]
    report_dir = repo_root / cfg["report_dir"]
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    fallback_cfg = cfg.get("fallback_download") or {}
    enable_fallback = bool(fallback_cfg.get("enabled", False))

    provenance = acquire_pilot(raw_dir, enable_fallback=enable_fallback)
    (report_dir / "acquisition_log.json").write_text(json.dumps(provenance, indent=2))

    df = build_registry(raw_dir)
    df = stratify(df)
    registry_path = processed_dir / "instance_registry.csv"
    df.to_csv(registry_path, index=False)

    # Markdown inspection report
    ok = df[df["parse_ok"]]
    bad = df[~df["parse_ok"]]
    lines: list[str] = []
    lines.append("# Phase 0 - Instance Inspection\n")
    lines.append(f"- Total .vrp files found: **{len(df)}**")
    lines.append(f"- Parsed successfully: **{len(ok)}** ({100*len(ok)/max(len(df),1):.0f}%)")
    lines.append(f"- Parse failures: **{len(bad)}**\n")

    lines.append("## Stratification by n_customers\n")
    bin_counts = ok.groupby("bin_label").size().to_dict()
    for label in ("small", "medium", "large", "out_of_range", "invalid"):
        lines.append(f"- {label}: {bin_counts.get(label, 0)}")
    lines.append("")

    lines.append("## Vehicle-count (k_min hint) spread\n")
    if len(ok):
        k_series = ok["k_min_hint"].dropna()
        if len(k_series):
            lines.append(
                f"- k min/median/max: "
                f"{int(k_series.min())} / {int(k_series.median())} / {int(k_series.max())}"
            )
            lines.append(f"- distinct k values: {sorted(int(v) for v in set(k_series))}")
    lines.append("")

    lines.append("## BKS availability\n")
    bks_cnt = int(ok["bks_routes_available"].sum())
    lines.append(f"- Instances with a .sol file parsed: **{bks_cnt} / {len(ok)}**\n")

    lines.append("## Registry rows\n")
    lines.append(df_to_markdown(ok[[
        "instance_id", "n_customers", "capacity", "edge_weight_type",
        "k_min_hint", "bin_label", "bks_objective", "bks_routes_available",
    ]]))
    lines.append("")
    if len(bad):
        lines.append("## Parse failures\n")
        lines.append(df_to_markdown(bad[["instance_id", "warnings"]]))
        lines.append("")

    lines.append("## Provenance\n")
    sources = {p.get("source", "?") for p in provenance}
    for s in sorted(sources):
        cnt = sum(1 for p in provenance if p.get("source") == s)
        lines.append(f"- {s}: {cnt}")

    report_path = report_dir / "phase0_instance_inspection.md"
    report_path.write_text("\n".join(lines))
    logger.info("Wrote %s", report_path)

    return {
        "registry_path": str(registry_path),
        "report_path": str(report_path),
        "n_parsed": int(len(ok)),
        "n_failures": int(len(bad)),
        "parse_rate": float(len(ok) / max(len(df), 1)),
        "bin_counts": {k: int(v) for k, v in bin_counts.items()},
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/phase0_data.yaml")
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    result = run_phase0(Path(args.config), repo_root=Path(args.repo_root).resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

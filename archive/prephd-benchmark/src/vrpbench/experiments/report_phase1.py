"""Assemble the Phase 1 pilot report from solutions.jsonl + comparisons.csv + activation.csv.

Also emits the PROCEED / REVISE / STOP decision based on the rules encoded
in configs/phase1_pilot.yaml.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ..evaluation.reporting import df_to_markdown

logger = logging.getLogger(__name__)


def _load_solutions(path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if "metadata" in df.columns:
        df["scenario"] = df["metadata"].map(
            lambda m: (m or {}).get("scenario", "nominal")
        )
    return df


def _decision(
    *,
    parse_rate: float,
    pyvrp_usable: bool,
    backend_disagreement_rate: float,
    structural_activation_rate: float,
    perturbation_nonzero_rate: float,
    pyvrp_bks_share_above_3pct: float,
    parse_failure_rate: float,
    rules: dict,
) -> tuple[str, list[str]]:
    proceed_cfg = rules["proceed"]
    stop_cfg = rules["stop"]
    revise_cfg = rules["revise"]

    notes: list[str] = []

    # Hard STOP triggers
    if structural_activation_rate < stop_cfg["structural_activation_below"]:
        notes.append(
            f"STOP: structural activation {structural_activation_rate:.0%} < "
            f"{stop_cfg['structural_activation_below']:.0%}"
        )
        return "STOP", notes
    if pyvrp_bks_share_above_3pct > 0.5:
        notes.append(
            f"STOP: PyVRP gap-to-BKS > 3% on {pyvrp_bks_share_above_3pct:.0%} of instances"
        )
        return "STOP", notes

    # REVISE triggers
    if parse_failure_rate > revise_cfg["parse_failure_above"]:
        notes.append(
            f"REVISE: parse failures {parse_failure_rate:.0%} > "
            f"{revise_cfg['parse_failure_above']:.0%}"
        )
        return "REVISE", notes
    if backend_disagreement_rate < revise_cfg["structural_disagreement_below"]:
        notes.append(
            f"REVISE: backend structural disagreement {backend_disagreement_rate:.0%} < "
            f"{revise_cfg['structural_disagreement_below']:.0%}"
        )
        return "REVISE", notes

    # PROCEED requires all conditions
    proceed_reasons = []
    ok = True
    if parse_rate < proceed_cfg["parse_rate_min"]:
        ok = False
        proceed_reasons.append(
            f"parse rate {parse_rate:.0%} < {proceed_cfg['parse_rate_min']:.0%}"
        )
    if proceed_cfg["pyvrp_usable"] and not pyvrp_usable:
        ok = False
        proceed_reasons.append("PyVRP not usable")
    if proceed_cfg["backend_structural_disagreement_required"] and backend_disagreement_rate <= 0:
        ok = False
        proceed_reasons.append("no backend structural disagreement observed")
    if perturbation_nonzero_rate < proceed_cfg["perturbation_activation_min"]:
        ok = False
        proceed_reasons.append(
            f"perturbation activation {perturbation_nonzero_rate:.0%} < "
            f"{proceed_cfg['perturbation_activation_min']:.0%}"
        )
    if ok:
        notes.append("PROCEED: all gates satisfied.")
        return "PROCEED", notes
    notes.append("REVISE: " + "; ".join(proceed_reasons))
    return "REVISE", notes


def build_report(
    *,
    repo_root: Path,
    config_path: Path,
    registry_csv: Path,
    solutions_jsonl: Path,
    comparisons_csv: Path,
    activation_csv: Path,
    out_path: Path,
) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text())
    rules = cfg["decision_rules"]

    registry = pd.read_csv(registry_csv)
    solutions = _load_solutions(solutions_jsonl)
    comparisons = pd.read_csv(comparisons_csv) if comparisons_csv.exists() else pd.DataFrame()
    activation = pd.read_csv(activation_csv) if activation_csv.exists() else pd.DataFrame()

    # Parsing
    parse_rate = float(registry["parse_ok"].mean()) if len(registry) else 0.0
    parse_failure_rate = 1 - parse_rate

    # PyVRP usability / BKS gap (on the nominal scenario, first seed)
    nom_sol = solutions[
        (solutions["backend_name"] == "pyvrp")
        & (solutions["scenario"] == "nominal")
    ].copy()

    # Merge with BKS from registry to compute gap_to_BKS on nominal PyVRP
    bks_df = registry[["instance_id", "bks_objective"]]
    nom_sol = nom_sol.merge(bks_df, on="instance_id", how="left")
    nom_sol["gap_to_bks_pct"] = np.where(
        nom_sol["bks_objective"].notna() & nom_sol["objective"].notna(),
        100 * (nom_sol["objective"] - nom_sol["bks_objective"]) / nom_sol["bks_objective"],
        np.nan,
    )
    pyvrp_ok_count = int((nom_sol["status"] == "ok").sum())
    pyvrp_usable = pyvrp_ok_count == len(nom_sol) and len(nom_sol) > 0

    gap_series = nom_sol["gap_to_bks_pct"].dropna()
    if len(gap_series):
        share_bks_above_3 = float((gap_series > 3.0).mean())
        share_bks_le_05 = float((gap_series <= 0.5).mean())
        share_bks_le_3 = float((gap_series <= 3.0).mean())
        median_gap = float(gap_series.median())
    else:
        share_bks_above_3 = share_bks_le_05 = share_bks_le_3 = 0.0
        median_gap = float("nan")

    # Backend disagreement rate (nominal only)
    act_be = activation[
        (activation["kind"] == "backend") & (activation["scenario"] == "nominal")
    ].copy()
    if len(act_be):
        backend_disagreement_rate = float(act_be["backend_disagreement"].mean())
        backend_nonzero_rate = float(act_be["nonzero_response"].mean())
        backend_structural_rate = float(act_be["structural_response"].mean())
    else:
        backend_disagreement_rate = backend_nonzero_rate = backend_structural_rate = 0.0

    # Perturbation activation - collapse per-instance by kind
    act_p = activation[activation["kind"] == "perturbation"].copy()
    if len(act_p):
        pert_inst = act_p.groupby("instance_id").agg(
            any_nonzero=("nonzero_response", "max"),
            any_structural=("structural_response", "max"),
        ).reset_index()
        perturbation_nonzero_rate = float(pert_inst["any_nonzero"].mean())
        perturbation_structural_rate = float(pert_inst["any_structural"].mean())
    else:
        pert_inst = pd.DataFrame()
        perturbation_nonzero_rate = perturbation_structural_rate = 0.0

    # Structural activation rate for the STOP gate: an instance is "activated"
    # if either the backend gate or any perturbation gate triggers structural
    # response. This is the operational signal that routing-relevant claims can
    # discriminate on this data.
    per_instance_structural: dict[str, bool] = {}
    for _, row in act_be.iterrows():
        per_instance_structural[row["instance_id"]] = bool(row["structural_response"])
    if len(pert_inst):
        for _, row in pert_inst.iterrows():
            prev = per_instance_structural.get(row["instance_id"], False)
            per_instance_structural[row["instance_id"]] = bool(prev or row["any_structural"])
    structural_activation_rate = (
        sum(per_instance_structural.values()) / len(per_instance_structural)
        if per_instance_structural else 0.0
    )

    decision, decision_notes = _decision(
        parse_rate=parse_rate,
        pyvrp_usable=pyvrp_usable,
        backend_disagreement_rate=backend_disagreement_rate,
        structural_activation_rate=structural_activation_rate,
        perturbation_nonzero_rate=perturbation_nonzero_rate,
        pyvrp_bks_share_above_3pct=share_bks_above_3,
        parse_failure_rate=parse_failure_rate,
        rules=rules,
    )

    # -------- Markdown assembly --------
    L: list[str] = []
    L.append("# Phase 1 - Pilot Report\n")
    L.append("## 1. Did instances parse?\n")
    L.append(f"- Registry rows: **{len(registry)}**")
    L.append(f"- Parsed successfully: **{int(registry['parse_ok'].sum())}** "
             f"({parse_rate:.0%})")
    if parse_failure_rate > 0:
        L.append("- Failures:")
        L.append(df_to_markdown(registry[~registry["parse_ok"]][["instance_id", "warnings"]]))
    L.append("")

    L.append("## 2. PyVRP protocol settings\n")
    backend_cfg = cfg["backends"]["strong"]["params"]
    L.append(f"- Seeds: `{backend_cfg.get('seeds')}`")
    L.append(f"- Time limit: `{backend_cfg.get('time_limit_sec')}` seconds")
    L.append("- Each SolutionArtifact carries: `random_seed`, `time_limit_sec`, "
             "`solver_params`, `solver_version`, `run_id`.\n")
    if len(nom_sol):
        ver = nom_sol["solver_version"].dropna().unique().tolist()
        L.append(f"- Observed solver_version values: `{ver}`")
    L.append("")

    L.append("## 3. How close to BKS?\n")
    if len(gap_series):
        L.append(f"- Instances with BKS available: **{len(gap_series)} / {len(nom_sol)}**")
        L.append(f"- Median nominal gap-to-BKS: **{median_gap:.2f}%**")
        L.append(f"- Share ≤ 0.5% (strong near-reference): **{share_bks_le_05:.0%}**")
        L.append(f"- Share 0.5–3% (strong heuristic baseline): "
                 f"**{(share_bks_le_3 - share_bks_le_05):.0%}**")
        L.append(f"- Share > 3% (insufficient reference quality): **{share_bks_above_3:.0%}**")
        L.append("")
        cols = ["instance_id", "objective", "bks_objective", "gap_to_bks_pct"]
        L.append(df_to_markdown(
            nom_sol[cols].sort_values("instance_id").rename(columns={
                "objective": "pyvrp_obj",
                "gap_to_bks_pct": "gap_%",
            })
        ))
    else:
        L.append("- No BKS reference available.")
    L.append("")

    L.append("## 4. Do backends structurally disagree?\n")
    L.append(f"- Nominal runs: **{len(act_be)}**")
    L.append(f"- Backend-disagreement gate rate (both objective AND ARI): "
             f"**{backend_disagreement_rate:.0%}**")
    L.append(f"  - Objective-gap-only component: {backend_nonzero_rate:.0%}")
    L.append(f"  - Structural (ARI) component: {backend_structural_rate:.0%}")
    if len(act_be):
        L.append("")
        L.append(df_to_markdown(act_be[[
            "instance_id", "objective_rel_change", "adjusted_rand",
            "route_count_change", "backend_disagreement",
        ]].sort_values("instance_id")))
    L.append("")

    L.append("## 5. Do perturbations activate?\n")
    L.append(f"- Perturbation scenarios in use: `capacity_reduction factors="
             f"{cfg['perturbations']['capacity_reduction'].get('factors')}`")
    L.append(f"- Per-instance nonzero-response rate: **{perturbation_nonzero_rate:.0%}**")
    L.append(f"- Per-instance structural-response rate: **{perturbation_structural_rate:.0%}**")
    if len(pert_inst):
        L.append("")
        L.append(df_to_markdown(pert_inst))
    L.append("")
    if len(act_p):
        L.append("### Per-scenario breakdown\n")
        scen = act_p.groupby(["scenario", "tag"]).agg(
            nonzero=("nonzero_response", "mean"),
            structural=("structural_response", "mean"),
        ).reset_index()
        L.append(df_to_markdown(scen))
    L.append("")

    L.append("## 6. Are observable claims supported?\n")
    L.append("| Claim family | Supported in Phase 1 | Signal present |")
    L.append("| --- | --- | --- |")
    obj_signal = "yes" if backend_nonzero_rate > 0 or perturbation_nonzero_rate > 0 else "no"
    asgn_signal = "yes" if backend_structural_rate > 0 or perturbation_structural_rate > 0 else "no"
    topk_ok = "yes" if len(comparisons) and comparisons["top_k_route_overlap"].notna().any() else "no"
    L.append(f"| objective/resource delta | yes | {obj_signal} |")
    L.append(f"| top-k route ranking | yes | {topk_ok} |")
    L.append(f"| assignment/structure change | yes | {asgn_signal} |")
    L.append("| intervention ordering | **deferred to Phase 2** | n/a |")
    L.append("| mechanism/explanation | **deferred to Phase 2** | n/a |")
    L.append("")

    L.append("## 7. Which claims are viable, which are deferred?\n")
    L.append("**Viable in Phase 1**:")
    L.append("- objective/resource delta (observable directly from artifacts)")
    L.append("- top-k route ranking (route distance contribution, k=3)")
    L.append("- assignment/structure change (adjusted Rand index on customer co-assignment)")
    L.append("")
    L.append("**Deferred** (per protocol):")
    L.append("- intervention ordering — requires ≥ 2 perturbation families; "
             "capacity_reduction is the only one enabled.")
    L.append("- mechanism / explanation — semantic claims tracked separately, "
             "never folded into main correctness rates.")
    L.append("")

    L.append("## 8. Decision\n")
    L.append(f"**{decision}**\n")
    for n in decision_notes:
        L.append(f"- {n}")
    L.append("")
    L.append("### Gate readings used\n")
    L.append(f"- parse rate: {parse_rate:.0%}")
    L.append(f"- PyVRP usable (all nominal runs ok): {pyvrp_usable}")
    L.append(f"- backend structural-disagreement rate: {backend_disagreement_rate:.0%}")
    L.append(f"- structural-activation rate (any source, per instance): "
             f"{structural_activation_rate:.0%}")
    L.append(f"- perturbation nonzero-response rate (per instance): "
             f"{perturbation_nonzero_rate:.0%}")
    L.append(f"- PyVRP gap-to-BKS > 3% share: {share_bks_above_3:.0%}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L))
    logger.info("Wrote %s", out_path)

    return {
        "decision": decision,
        "decision_notes": decision_notes,
        "parse_rate": parse_rate,
        "pyvrp_usable": pyvrp_usable,
        "median_gap_to_bks_pct": median_gap,
        "share_bks_le_0p5": share_bks_le_05,
        "share_bks_gt_3": share_bks_above_3,
        "backend_disagreement_rate": backend_disagreement_rate,
        "perturbation_nonzero_rate": perturbation_nonzero_rate,
        "structural_activation_rate": structural_activation_rate,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/phase1_pilot.yaml")
    ap.add_argument("--registry", default="data/processed/instance_registry.csv")
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    repo_root = Path(args.repo_root).resolve()
    cfg = yaml.safe_load(Path(args.config).read_text())
    result = build_report(
        repo_root=repo_root,
        config_path=Path(args.config),
        registry_csv=Path(args.registry),
        solutions_jsonl=repo_root / cfg["outputs"]["solutions_file"],
        comparisons_csv=repo_root / cfg["outputs"]["comparisons_file"],
        activation_csv=repo_root / cfg["outputs"]["activation_file"],
        out_path=repo_root / cfg["outputs"]["report_file"],
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

"""Phase 2R budget-consistency check.

Rerun PyVRP at time_limit_sec=60 on five pre-specified perturbed scenarios,
spanning Phase 2 objective_gap_rel strata (0-5, 5-10, 10-20, 20-40, >=40%).
The cheap-backend solutions are reused unchanged from Phase 2; only PyVRP is
re-solved at the higher budget. Writes one SolutionArtifact JSON per scenario
under data/processed/phase2r/budget_check/ and a comparison.csv comparing the
10s vs 60s metrics (gap, ARI, top-k overlap, per-family difficulty label).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from ..artifacts.solution import SolutionArtifact
from ..backends.pyvrp_backend import solve_pyvrp
from ..data.instance import load_instance
from ..evaluation.metrics import compare
from .phase2r import label_assignment, label_objective, label_ranking

logger = logging.getLogger(__name__)

PYVRP_BUDGET_SEC = 60.0
PYVRP_SEED = 1


def select_scenarios(per_family_csv: Path) -> list[dict]:
    pf = pd.read_csv(per_family_csv)
    pf["gap_pct"] = pf["objective_gap_rel"].abs() * 100
    strata = [
        ("0-5%", 0.0, 5.0, 2.5),
        ("5-10%", 5.0, 10.0, 7.5),
        ("10-20%", 10.0, 20.0, 15.0),
        ("20-40%", 20.0, 40.0, 30.0),
        (">=40%", 40.0, float("inf"), 40.0),
    ]
    chosen: list[dict] = []
    for name, lo, hi, mid in strata:
        sub = pf[(pf["gap_pct"] >= lo) & (pf["gap_pct"] < hi)].copy()
        if sub.empty:
            logger.warning("Stratum %s is empty", name)
            continue
        sub["dist"] = (sub["gap_pct"] - mid).abs()
        sub = sub.sort_values(
            ["dist", "instance_id", "cheap_backend", "family", "magnitude"]
        ).reset_index(drop=True)
        row = sub.iloc[0].to_dict()
        row["stratum"] = name
        row["stratum_lo_pct"] = lo
        row["stratum_hi_pct"] = hi
        row["stratum_mid_pct"] = mid
        chosen.append(row)
    return chosen


def find_perturbed_path(
    registry: pd.DataFrame,
    instance_id: str,
    family: str,
    magnitude: float,
) -> Path:
    mask = (
        (registry["instance_id"] == instance_id)
        & (registry["family"] == family)
        & (registry["magnitude"].astype(float) == float(magnitude))
        & (registry["backend"] == "pyvrp")
    )
    sub = registry[mask]
    if sub.empty:
        raise RuntimeError(
            f"no perturbed path for {instance_id} {family}@{magnitude}"
        )
    return Path(str(sub.iloc[0]["perturbed_path"]))


def load_solution_artifact(
    solutions_jsonl: Path,
    instance_id: str,
    scenario: str,
    backend: str,
) -> SolutionArtifact:
    """Find the matching artifact in solutions.jsonl (last write wins)."""
    found: SolutionArtifact | None = None
    with solutions_jsonl.open() as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if (
                d.get("instance_id") == instance_id
                and d.get("backend_name") == backend
                and d.get("metadata", {}).get("scenario") == scenario
            ):
                found = SolutionArtifact(**d)
    if found is None:
        raise RuntimeError(
            f"no artifact for {instance_id} scenario={scenario} backend={backend}"
        )
    return found


def run(
    repo_root: Path,
    *,
    per_family_csv: Path | None = None,
) -> dict:
    if per_family_csv is None:
        per_family_csv = repo_root / "data/processed/phase2r/per_family_difficulty.csv"
    registry_csv = repo_root / "data/processed/phase2/scenario_registry.csv"
    solutions_jsonl = repo_root / "reports/phase2/solutions.jsonl"
    out_dir = repo_root / "data/processed/phase2r/budget_check"
    out_dir.mkdir(parents=True, exist_ok=True)

    registry = pd.read_csv(registry_csv)
    chosen = select_scenarios(per_family_csv)

    selection_rows = [
        {
            "stratum": c["stratum"],
            "stratum_lo_pct": c["stratum_lo_pct"],
            "stratum_hi_pct": c["stratum_hi_pct"],
            "stratum_mid_pct": c["stratum_mid_pct"],
            "instance_id": c["instance_id"],
            "family": c["family"],
            "magnitude": c["magnitude"],
            "cheap_backend": c["cheap_backend"],
            "objective_gap_rel_at_10s": c["objective_gap_rel"],
            "adjusted_rand_at_10s": c["adjusted_rand"],
            "top_k_route_overlap_at_10s": c["top_k_route_overlap"],
        }
        for c in chosen
    ]
    pd.DataFrame(selection_rows).to_csv(out_dir / "selection.csv", index=False)

    cmp_df_full = pd.read_csv(repo_root / "data/processed/phase2/backend_comparisons.csv")

    rerun_rows: list[dict] = []
    for c in chosen:
        iid = c["instance_id"]
        fam = c["family"]
        mag = float(c["magnitude"])
        cb = c["cheap_backend"]
        scenario = f"{fam}@{mag}"

        base_vrp = repo_root / "data" / "raw" / "cvrplib" / f"{iid}.vrp"
        base_inst = load_instance(base_vrp)
        n_cust = base_inst.n_customers

        perturbed_path = find_perturbed_path(registry, iid, fam, mag)
        if not perturbed_path.is_absolute():
            perturbed_path = repo_root / perturbed_path
        if not perturbed_path.exists():
            raise FileNotFoundError(perturbed_path)

        cheap_art = load_solution_artifact(solutions_jsonl, iid, scenario, cb)
        pyvrp_10s = load_solution_artifact(solutions_jsonl, iid, scenario, "pyvrp")

        logger.info(
            "stratum=%s scenario=%s/%s cb=%s solving pyvrp@60s",
            c["stratum"], iid, scenario, cb,
        )
        pyvrp_60s = solve_pyvrp(
            base_inst,
            seed=PYVRP_SEED,
            time_limit_sec=PYVRP_BUDGET_SEC,
            instance_path_override=perturbed_path,
        )
        pyvrp_60s.metadata = dict(pyvrp_60s.metadata)
        pyvrp_60s.metadata["scenario"] = scenario
        pyvrp_60s.metadata["budget_check"] = True
        mag_tag = str(mag).replace(".", "p")
        out_json = out_dir / f"{iid}__{fam}__mag{mag_tag}__pyvrp60s.json"
        out_json.write_text(pyvrp_60s.model_dump_json(indent=2))

        cmp10 = compare(cheap_art, pyvrp_10s, n_customers=n_cust)
        cmp60 = compare(cheap_art, pyvrp_60s, n_customers=n_cust)

        def _label_set(cmpres) -> dict[str, str | None]:
            return {
                "objective": label_objective(cmpres.objective_gap_rel),
                "assignment": label_assignment(cmpres.adjusted_rand_assignment),
                "ranking": label_ranking(
                    cmpres.top_k_route_overlap,
                    cmpres.route_count_a,
                    cmpres.route_count_b,
                ),
            }

        labels10 = _label_set(cmp10)
        labels60 = _label_set(cmp60)

        obj10 = float(pyvrp_10s.objective) if pyvrp_10s.objective is not None else None
        obj60 = float(pyvrp_60s.objective) if pyvrp_60s.objective is not None else None
        improvement = None
        if obj10 is not None and obj60 is not None and obj10 != 0:
            improvement = (obj10 - obj60) / obj10

        ari_movement = None
        if cmp10.adjusted_rand_assignment is not None and cmp60.adjusted_rand_assignment is not None:
            ari_movement = cmp60.adjusted_rand_assignment - cmp10.adjusted_rand_assignment

        rerun_rows.append({
            "stratum": c["stratum"],
            "instance_id": iid,
            "family": fam,
            "magnitude": mag,
            "cheap_backend": cb,
            "objective_pyvrp_10s": obj10,
            "objective_pyvrp_60s": obj60,
            "pyvrp_improvement_rel": improvement,
            "gap_at_10s": cmp10.objective_gap_rel,
            "gap_at_60s": cmp60.objective_gap_rel,
            "ari_at_10s": cmp10.adjusted_rand_assignment,
            "ari_at_60s": cmp60.adjusted_rand_assignment,
            "ari_movement": ari_movement,
            "topk_overlap_at_10s": cmp10.top_k_route_overlap,
            "topk_overlap_at_60s": cmp60.top_k_route_overlap,
            "n_routes_pyvrp_10s": pyvrp_10s.n_routes,
            "n_routes_pyvrp_60s": pyvrp_60s.n_routes,
            "objective_label_10s": labels10["objective"],
            "objective_label_60s": labels60["objective"],
            "assignment_label_10s": labels10["assignment"],
            "assignment_label_60s": labels60["assignment"],
            "ranking_label_10s": labels10["ranking"],
            "ranking_label_60s": labels60["ranking"],
            "label_changed_objective": labels10["objective"] != labels60["objective"],
            "label_changed_assignment": labels10["assignment"] != labels60["assignment"],
            "label_changed_ranking": labels10["ranking"] != labels60["ranking"],
            "pyvrp_60s_artifact": out_json.as_posix(),
        })

    cmp_out = pd.DataFrame(rerun_rows)
    cmp_out.to_csv(out_dir / "comparison.csv", index=False)

    n_drift = int(
        cmp_out[[
            "label_changed_objective",
            "label_changed_assignment",
            "label_changed_ranking",
        ]].any(axis=1).sum()
    )
    verdict = "Stable" if n_drift == 0 else "Drift"
    summary = {
        "verdict": verdict,
        "n_scenarios": len(cmp_out),
        "n_drift_rows": n_drift,
        "max_pyvrp_improvement_rel": float(cmp_out["pyvrp_improvement_rel"].max()),
        "min_pyvrp_improvement_rel": float(cmp_out["pyvrp_improvement_rel"].min()),
        "max_abs_ari_movement": float(cmp_out["ari_movement"].abs().max()),
    }
    (out_dir / "verdict.json").write_text(json.dumps(summary, indent=2))
    logger.info("verdict: %s (drift_rows=%d)", verdict, n_drift)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    summary = run(Path(args.repo_root).resolve())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

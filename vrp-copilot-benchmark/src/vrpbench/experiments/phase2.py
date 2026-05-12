"""Phase 2 difficulty-audit runner.

For each registry instance:
  - solve with all three backends (nearest_neighbor, savings, pyvrp) on the
    nominal instance, plus on each (perturbation_family, magnitude) pair
  - apply both required perturbation families across all magnitudes
  - optionally apply the two exploratory families separately
  - emit SolutionArtifacts to solutions.jsonl
  - emit the five Phase 2 CSVs

The 2/3/4 CSV structure mirrors the prompt:
  scenario_registry.csv            — every (instance, family, magnitude, backend)
  backend_comparisons.csv          — cheap-vs-strong gaps per scenario
  perturbation_activation.csv      — baseline-vs-perturbed activations
  difficulty_labels.csv            — one label per (instance, family, mag, cheap_backend)
  conditional_gap_summary.csv      — grouped avg gap / ARI / difficulty dist
  claim_errors.csv                 — per-claim-family error rows

Reporting (PROCEED/REVISE/STOP) is produced by report_phase2.py.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import time
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

from ..artifacts.solution import SolutionArtifact
from ..backends.cheap_savings import solve_savings
from ..backends.nearest_neighbor import solve_nearest_neighbor
from ..backends.pyvrp_backend import solve_pyvrp
from ..claims.families import CLAIM_FAMILIES, compute_claim_errors
from ..data.instance import VRPInstance, load_instance
from ..evaluation.activation import (
    screen_backend_disagreement,
    screen_perturbation,
)
from ..evaluation.metrics import compare
from ..perturbations.capacity import apply_capacity_reduction
from ..perturbations.customer_insertion import apply_customer_insertion
from ..perturbations.localized_demand import apply_localized_demand_inflation
from ..perturbations.regional_distance import apply_regional_distance_inflation

logger = logging.getLogger(__name__)


CHEAP_BACKENDS = ("nearest_neighbor", "savings")
STRONG_BACKEND = "pyvrp"
BACKENDS_ALL = CHEAP_BACKENDS + (STRONG_BACKEND,)


def _append_artifact(path: Path, art: SolutionArtifact, scenario: str) -> None:
    art.metadata = dict(art.metadata)
    art.metadata["scenario"] = scenario
    with path.open("a") as f:
        f.write(art.model_dump_json() + "\n")


def _solve_one(
    backend: str,
    base_instance: VRPInstance,
    *,
    solve_instance: VRPInstance,
    instance_path_override: Path | None,
    pyvrp_params: dict,
) -> SolutionArtifact:
    """Dispatch to the named backend, producing a SolutionArtifact.

    ``base_instance`` is the nominal instance whose id tags the artifact.
    ``solve_instance`` is what actually gets solved (may be a perturbed
    instance with different coords/demand).
    """
    if backend == "nearest_neighbor":
        art = solve_nearest_neighbor(solve_instance)
    elif backend == "savings":
        art = solve_savings(solve_instance)
    elif backend == "pyvrp":
        seed = int(pyvrp_params.get("seed", 1))
        tl = float(pyvrp_params.get("time_limit_sec", 20))
        art = solve_pyvrp(
            base_instance,
            seed=seed,
            time_limit_sec=tl,
            instance_path_override=instance_path_override,
        )
    else:
        raise ValueError(f"Unknown backend {backend}")
    art.instance_id = base_instance.instance_id
    return art


def _difficulty_label(
    *,
    objective_gap_rel: float | None,
    ari: float | None,
) -> str | None:
    """Apply the Phase 2 difficulty bands.

    Disjoint fallback chain (easy -> medium -> hard -> unknown), per the
    prompt's specification:
      easy   := |gap| < 0.05 AND ari > 0.75
      hard   := |gap| > 0.15 OR  ari < 0.50
      medium := gap in [0.05, 0.15] OR ari in [0.50, 0.75]
    Anything not covered (e.g. NaNs on both sides) returns None.
    """
    if objective_gap_rel is None and ari is None:
        return None
    g = abs(objective_gap_rel) if objective_gap_rel is not None else None

    if g is not None and ari is not None and g < 0.05 and ari > 0.75:
        return "easy"
    if (g is not None and g > 0.15) or (ari is not None and ari < 0.50):
        return "hard"
    in_med_gap = g is not None and 0.05 <= g <= 0.15
    in_med_ari = ari is not None and 0.50 <= ari <= 0.75
    if in_med_gap or in_med_ari:
        return "medium"
    # Small gap, mid ARI, or mid gap with high ARI: default bucket = easy.
    if (g is not None and g < 0.05) or (ari is not None and ari > 0.75):
        return "easy"
    return None


# ---------- perturbation driver ----------

def _run_perturbation_family(
    *,
    family_name: str,
    apply_fn: Callable[..., tuple[Path, dict]],
    magnitudes: list,
    mag_key: str,
    base_instance: VRPInstance,
    baseline_arts: dict[str, SolutionArtifact],
    scratch_dir: Path,
    pyvrp_params: dict,
    solutions_path: Path,
) -> list[dict]:
    """Apply ``family_name`` to ``base_instance`` across ``magnitudes``.

    For each magnitude: rewrite the .vrp, solve with all three backends,
    record the scenario row + baseline-vs-perturbed activation per backend
    + cheap-vs-strong backend comparison + claim errors. Returns a list of
    records; the caller concatenates them into the output tables.
    """
    records: list[dict] = []
    for mag in magnitudes:
        scenario = f"{family_name}@{mag}"
        try:
            path, meta = apply_fn(base_instance, mag, scratch_dir)
        except Exception as e:
            logger.error("  %s mag=%s failed: %s", family_name, mag, e)
            records.append({
                "instance_id": base_instance.instance_id,
                "family": family_name,
                "magnitude": mag,
                "status": f"perturbation_error:{e}",
            })
            continue

        pert_instance = load_instance(path)

        # Solve with each backend on the perturbed instance.
        pert_arts: dict[str, SolutionArtifact] = {}
        for backend in BACKENDS_ALL:
            art = _solve_one(
                backend,
                base_instance,
                solve_instance=pert_instance,
                instance_path_override=path,
                pyvrp_params=pyvrp_params,
            )
            pert_arts[backend] = art
            _append_artifact(solutions_path, art, scenario=scenario)

        # Perturbation activation: baseline-vs-perturbed, per backend.
        # ``n_customers`` is always the base instance size so assignment
        # labels are length-aligned across backends, even for the
        # customer-insertion family where the perturbed instance is bigger.
        n_cust = base_instance.n_customers
        for backend in BACKENDS_ALL:
            baseline = baseline_arts[backend]
            perturbed = pert_arts[backend]
            tag = f"{scenario}:{backend}"
            row = screen_perturbation(
                baseline, perturbed,
                n_customers=n_cust, tag=tag,
            )
            r = row.as_row()
            r.update({
                "family": family_name,
                "magnitude": mag,
                "backend": backend,
                "scenario": scenario,
            })
            records.append({"type": "activation", "row": r})

        # Backend comparisons (cheap vs strong) on the perturbed scenario,
        # plus difficulty labels + claim-family errors.
        strong = pert_arts[STRONG_BACKEND]
        for cheap_name in CHEAP_BACKENDS:
            cheap = pert_arts[cheap_name]
            cmp = compare(cheap, strong, n_customers=n_cust)
            cmp_row = cmp.as_row()
            cmp_row.update({
                "scenario": scenario,
                "family": family_name,
                "magnitude": mag,
                "cheap_backend": cheap_name,
            })
            label = _difficulty_label(
                objective_gap_rel=cmp.objective_gap_rel,
                ari=cmp.adjusted_rand_assignment,
            )
            records.append({"type": "comparison", "row": cmp_row})
            records.append({"type": "difficulty", "row": {
                "instance_id": base_instance.instance_id,
                "family": family_name,
                "magnitude": mag,
                "cheap_backend": cheap_name,
                "objective_gap_rel": cmp.objective_gap_rel,
                "adjusted_rand": cmp.adjusted_rand_assignment,
                "difficulty_label": label,
                "scenario": scenario,
            }})
            claim_errors = compute_claim_errors(
                cheap, strong, n_customers=n_cust,
            )
            for r in claim_errors.as_rows(scenario=scenario):
                r.update({
                    "family": family_name,
                    "magnitude": mag,
                })
                records.append({"type": "claim", "row": r})

        records.append({
            "type": "registry",
            "rows": [{
                "scenario_id": f"{base_instance.instance_id}|{scenario}|{b}",
                "instance_id": base_instance.instance_id,
                "family": family_name,
                "magnitude": mag,
                "backend": b,
                "status": pert_arts[b].status,
                "objective": pert_arts[b].objective,
                "n_routes": pert_arts[b].n_routes,
                "runtime_sec": pert_arts[b].runtime_sec,
                "perturbed_path": str(path),
                "perturbation_meta": json.dumps(meta),
            } for b in BACKENDS_ALL],
        })

    return records


def _run_nominal(
    base_instance: VRPInstance,
    *,
    pyvrp_params: dict,
    solutions_path: Path,
) -> tuple[dict[str, SolutionArtifact], list[dict]]:
    """Solve the nominal instance with all three backends and record
    backend-vs-backend comparison + claim-error rows.

    Returns the artifacts keyed by backend plus a list of records.
    """
    records: list[dict] = []
    arts: dict[str, SolutionArtifact] = {}
    for backend in BACKENDS_ALL:
        art = _solve_one(
            backend,
            base_instance,
            solve_instance=base_instance,
            instance_path_override=None,
            pyvrp_params=pyvrp_params,
        )
        arts[backend] = art
        _append_artifact(solutions_path, art, scenario="nominal")

    n_cust = base_instance.n_customers
    strong = arts[STRONG_BACKEND]
    for cheap_name in CHEAP_BACKENDS:
        cheap = arts[cheap_name]
        cmp = compare(
            cheap, strong,
            n_customers=n_cust,
            bks_objective=base_instance.bks_objective,
        )
        cmp_row = cmp.as_row()
        cmp_row.update({
            "scenario": "nominal",
            "family": "nominal",
            "magnitude": 1.0,
            "cheap_backend": cheap_name,
        })
        label = _difficulty_label(
            objective_gap_rel=cmp.objective_gap_rel,
            ari=cmp.adjusted_rand_assignment,
        )
        records.append({"type": "comparison", "row": cmp_row})
        records.append({"type": "difficulty", "row": {
            "instance_id": base_instance.instance_id,
            "family": "nominal",
            "magnitude": 1.0,
            "cheap_backend": cheap_name,
            "objective_gap_rel": cmp.objective_gap_rel,
            "adjusted_rand": cmp.adjusted_rand_assignment,
            "difficulty_label": label,
            "scenario": "nominal",
        }})
        ce = compute_claim_errors(cheap, strong, n_customers=n_cust)
        for r in ce.as_rows(scenario="nominal"):
            r.update({"family": "nominal", "magnitude": 1.0})
            records.append({"type": "claim", "row": r})

        # Nominal backend-disagreement activation row (per cheap backend).
        row = screen_backend_disagreement(
            cheap, strong, n_customers=n_cust,
            tag=f"nominal:{cheap_name}_vs_pyvrp",
        )
        r = row.as_row()
        r.update({
            "family": "nominal",
            "magnitude": 1.0,
            "backend": cheap_name,
            "scenario": "nominal",
        })
        records.append({"type": "activation", "row": r})

    records.append({
        "type": "registry",
        "rows": [{
            "scenario_id": f"{base_instance.instance_id}|nominal|{b}",
            "instance_id": base_instance.instance_id,
            "family": "nominal",
            "magnitude": 1.0,
            "backend": b,
            "status": arts[b].status,
            "objective": arts[b].objective,
            "n_routes": arts[b].n_routes,
            "runtime_sec": arts[b].runtime_sec,
            "perturbed_path": "",
            "perturbation_meta": "",
        } for b in BACKENDS_ALL],
    })

    return arts, records


def _bucket_records(records: list[dict]) -> tuple[
    list[dict], list[dict], list[dict], list[dict], list[dict],
]:
    """Split the mixed records stream into the five CSVs' row lists."""
    registry, activation, comparisons, difficulty, claim = [], [], [], [], []
    for rec in records:
        t = rec["type"]
        if t == "registry":
            registry.extend(rec["rows"])
        elif t == "activation":
            activation.append(rec["row"])
        elif t == "comparison":
            comparisons.append(rec["row"])
        elif t == "difficulty":
            difficulty.append(rec["row"])
        elif t == "claim":
            claim.append(rec["row"])
    return registry, activation, comparisons, difficulty, claim


def run_phase2(
    config_path: Path,
    *,
    repo_root: Path,
    registry_csv: Path,
    include_exploratory: bool = True,
) -> dict:
    cfg = yaml.safe_load(config_path.read_text())

    outputs = cfg["outputs"]
    solutions_path = repo_root / outputs["solutions_jsonl"]
    registry_path = repo_root / outputs["registry_file"]
    backend_cmp_path = repo_root / outputs["backend_comparisons_file"]
    pert_act_path = repo_root / outputs["perturbation_activation_file"]
    difficulty_path = repo_root / outputs["difficulty_labels_file"]
    gap_summary_path = repo_root / outputs["conditional_gap_summary_file"]
    claim_path = repo_root / outputs["claim_errors_file"]

    for p in (
        solutions_path, registry_path, backend_cmp_path,
        pert_act_path, difficulty_path, gap_summary_path, claim_path,
    ):
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()

    scratch = repo_root / "data" / "processed" / "phase2" / "perturbed"
    scratch.mkdir(parents=True, exist_ok=True)

    pyvrp_params = cfg["backends"]["pyvrp"]["params"]
    cap_factors = cfg["perturbations"]["required"]["capacity_reduction"]["factors"]
    regdist_factors = cfg["perturbations"]["required"]["regional_distance_inflation"]["factors"]
    locdem_factors = cfg["perturbations"]["exploratory"]["localized_demand_inflation"]["factors"]
    insert_counts = cfg["perturbations"]["exploratory"]["customer_insertion"]["counts"]

    registry_df = pd.read_csv(registry_csv)
    registry_df = registry_df[registry_df["parse_ok"]].reset_index(drop=True)
    ids = registry_df["instance_id"].tolist()
    logger.info(
        "Phase 2: %d instances; pyvrp params=%s; cap=%s; regdist=%s; "
        "locdem(exp)=%s; insert(exp)=%s; exploratory=%s",
        len(ids), pyvrp_params, cap_factors, regdist_factors,
        locdem_factors, insert_counts, include_exploratory,
    )

    all_records: list[dict] = []

    for idx, iid in enumerate(ids, start=1):
        vrp_path = repo_root / "data" / "raw" / "cvrplib" / f"{iid}.vrp"
        inst = load_instance(vrp_path)
        t_inst = time.perf_counter()
        logger.info("[%d/%d] %s n=%d cap=%.0f BKS=%s",
                    idx, len(ids), iid, inst.n_customers, inst.capacity,
                    f"{inst.bks_objective:.0f}" if inst.bks_objective else "-")

        baselines, nominal_records = _run_nominal(
            inst, pyvrp_params=pyvrp_params, solutions_path=solutions_path,
        )
        all_records.extend(nominal_records)
        logger.info(
            "  nominal: nn=%s/%s | cw=%s/%s | pyvrp=%s/%s",
            baselines["nearest_neighbor"].status, baselines["nearest_neighbor"].objective,
            baselines["savings"].status, baselines["savings"].objective,
            baselines["pyvrp"].status, baselines["pyvrp"].objective,
        )

        # ---- REQUIRED ----
        all_records.extend(_run_perturbation_family(
            family_name="capacity_reduction",
            apply_fn=apply_capacity_reduction,
            magnitudes=cap_factors,
            mag_key="factor",
            base_instance=inst,
            baseline_arts=baselines,
            scratch_dir=scratch,
            pyvrp_params=pyvrp_params,
            solutions_path=solutions_path,
        ))
        all_records.extend(_run_perturbation_family(
            family_name="regional_distance_inflation",
            apply_fn=apply_regional_distance_inflation,
            magnitudes=regdist_factors,
            mag_key="factor",
            base_instance=inst,
            baseline_arts=baselines,
            scratch_dir=scratch,
            pyvrp_params=pyvrp_params,
            solutions_path=solutions_path,
        ))

        # ---- EXPLORATORY ----
        if include_exploratory:
            all_records.extend(_run_perturbation_family(
                family_name="localized_demand_inflation",
                apply_fn=apply_localized_demand_inflation,
                magnitudes=locdem_factors,
                mag_key="factor",
                base_instance=inst,
                baseline_arts=baselines,
                scratch_dir=scratch,
                pyvrp_params=pyvrp_params,
                solutions_path=solutions_path,
            ))
            all_records.extend(_run_perturbation_family(
                family_name="customer_insertion",
                apply_fn=apply_customer_insertion,
                magnitudes=insert_counts,
                mag_key="count",
                base_instance=inst,
                baseline_arts=baselines,
                scratch_dir=scratch,
                pyvrp_params=pyvrp_params,
                solutions_path=solutions_path,
            ))

        logger.info("  instance total %.1fs", time.perf_counter() - t_inst)

    reg_rows, act_rows, cmp_rows, diff_rows, claim_rows = _bucket_records(all_records)

    reg_df = pd.DataFrame(reg_rows)
    act_df = pd.DataFrame(act_rows)
    cmp_df = pd.DataFrame(cmp_rows)
    diff_df = pd.DataFrame(diff_rows)
    claim_df = pd.DataFrame(claim_rows)

    # Conditional gap summary: group by (cheap_backend, family, magnitude,
    # claim_family) with mean gap, mean ARI, and difficulty distribution.
    # We join claim and difficulty rows via (instance, family, magnitude,
    # cheap_backend).
    if len(diff_df) and len(claim_df):
        diff_keyed = diff_df[[
            "instance_id", "family", "magnitude", "cheap_backend",
            "objective_gap_rel", "adjusted_rand", "difficulty_label",
        ]].copy()
        merged = claim_df.merge(
            diff_keyed,
            on=["instance_id", "family", "magnitude", "cheap_backend"],
            how="left",
        )
        grp_keys = ["cheap_backend", "family", "magnitude", "claim_family"]
        g = merged.groupby(grp_keys, dropna=False)
        summary_rows: list[dict] = []
        for key, sub in g:
            ck, fam, mag, claim = key
            gap = sub["objective_gap_rel"].astype(float)
            ari = sub["adjusted_rand"].astype(float)
            err = sub["claim_error"].astype(float)
            dist = sub["difficulty_label"].value_counts(dropna=False).to_dict()
            row = {
                "cheap_backend": ck,
                "family": fam,
                "magnitude": mag,
                "claim_family": claim,
                "n": len(sub),
                "avg_objective_gap_rel": float(gap.mean()) if len(gap.dropna()) else math.nan,
                "avg_adjusted_rand": float(ari.mean()) if len(ari.dropna()) else math.nan,
                "avg_claim_error": float(err.mean()) if len(err.dropna()) else math.nan,
                "n_easy": int(dist.get("easy", 0)),
                "n_medium": int(dist.get("medium", 0)),
                "n_hard": int(dist.get("hard", 0)),
                "n_unknown": int(
                    sum(v for k, v in dist.items() if k not in {"easy", "medium", "hard"})
                ),
            }
            summary_rows.append(row)
        summary_df = pd.DataFrame(summary_rows)
    else:
        summary_df = pd.DataFrame()

    reg_df.to_csv(registry_path, index=False)
    act_df.to_csv(pert_act_path, index=False)
    cmp_df.to_csv(backend_cmp_path, index=False)
    diff_df.to_csv(difficulty_path, index=False)
    summary_df.to_csv(gap_summary_path, index=False)
    claim_df.to_csv(claim_path, index=False)

    logger.info(
        "Wrote: registry(%d), activation(%d), comparisons(%d), "
        "difficulty(%d), summary(%d), claim_errors(%d)",
        len(reg_df), len(act_df), len(cmp_df),
        len(diff_df), len(summary_df), len(claim_df),
    )

    return {
        "n_instances": len(ids),
        "n_scenarios": int(len(reg_df)),
        "n_comparisons": int(len(cmp_df)),
        "n_activations": int(len(act_df)),
        "n_difficulty_rows": int(len(diff_df)),
        "n_summary_rows": int(len(summary_df)),
        "n_claim_rows": int(len(claim_df)),
        "registry_file": str(registry_path),
        "solutions_file": str(solutions_path),
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/phase2_difficulty.yaml")
    ap.add_argument("--registry", default="data/processed/instance_registry.csv")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--skip-exploratory", action="store_true")
    args = ap.parse_args()
    out = run_phase2(
        Path(args.config),
        repo_root=Path(args.repo_root).resolve(),
        registry_csv=Path(args.registry),
        include_exploratory=not args.skip_exploratory,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

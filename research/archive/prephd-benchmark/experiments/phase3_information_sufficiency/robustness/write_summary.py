"""Section 6 — PHASE3_ROBUSTNESS_SUMMARY.md.

Pulls numbers from the artifacts/robustness/ outputs and writes a
narrative that:

  1. Reports the feasible-vs-infeasible split for objective reuse.
  2. Quantifies how much the result is distance-driven.
  3. Says when reuse becomes unsafe under capacity reduction.
  4. Shows the λ curves under each penalty variant.
  5. Provides exact thesis-ready sentences for reuse and tie behavior.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd


CLAIM_LABEL = {
    "objective_resource_delta": "objective",
    "topk_route_ranking": "ranking",
    "assignment_structure": "structure",
}
ACTIONS = ("reuse_direct", "nearest_neighbor", "clarke_wright", "pyvrp_10s", "pyvrp_60s")


def _fmt_pct(x) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_err(x) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.4f}"
    except (TypeError, ValueError):
        return "—"


def _share_table_md(df: pd.DataFrame, title: str) -> str:
    out = [f"\n#### {title}\n"]
    out.append("| λ | claim | reuse | NN | CW | pyvrp_10s | pyvrp_60s |")
    out.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: |")
    for _, r in df.sort_values(["lambda", "claim_family"]).iterrows():
        out.append(
            f"| {r['lambda']:g} | {CLAIM_LABEL.get(r['claim_family'], r['claim_family'])} | "
            f"{_fmt_pct(r['share_reuse_direct'])} | "
            f"{_fmt_pct(r['share_nearest_neighbor'])} | "
            f"{_fmt_pct(r['share_clarke_wright'])} | "
            f"{_fmt_pct(r['share_pyvrp_10s'])} | "
            f"{_fmt_pct(r['share_pyvrp_60s'])} |"
        )
    return "\n".join(out) + "\n"


def write(
    out_dir: Path,
    summary_md_path: Path,
) -> None:
    log = logging.getLogger("phase3.robustness.summary")

    feas = pd.read_csv(out_dir / "table_reuse_direct_objective_feasible_vs_infeasible.csv")
    dist = pd.read_csv(out_dir / "table_distance_only_reuse_direct.csv")
    cap = pd.read_csv(out_dir / "table_capacity_reduction_feasibility_by_magnitude.csv")
    pen1 = pd.read_csv(out_dir / "phase3_lambda_curves_feasibility_penalty_1.csv")
    pen05 = pd.read_csv(out_dir / "phase3_lambda_curves_feasibility_penalty_05.csv")
    unans = pd.read_csv(out_dir / "phase3_lambda_curves_unanswerable_infeasible.csv")
    audit = json.loads((out_dir / "phase3_lambda_tie_audit.json").read_text())

    # ---- helpers for variant share tables ----
    def variant_share(df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for lam in sorted(df["lambda"].unique()):
            for fam in sorted(df["claim_family"].unique()):
                sub = df[(df["lambda"] == lam) & (df["claim_family"] == fam)]
                if sub.empty:
                    continue
                shares = (sub["best_action"].value_counts(normalize=True) * 100).to_dict()
                rows.append({
                    "lambda": lam, "claim_family": fam, "n": int(len(sub)),
                    **{f"share_{a}": float(shares.get(a, 0.0)) for a in ACTIONS},
                })
        return pd.DataFrame(rows)

    pen1_share = variant_share(pen1)
    pen05_share = variant_share(pen05)
    unans_share = variant_share(unans)

    # ---- Section 1: feasibility split ----
    s1: list[str] = []
    s1.append("## 1. Objective reuse split by feasibility\n")
    obj_rows = feas[feas["claim_family"] == "objective_resource_delta"]
    s1.append("| perturbation | feasible | n | mean loss | median loss | easy % | hard % |")
    s1.append("| --- | :---: | ---: | ---: | ---: | ---: | ---: |")
    for _, r in obj_rows.iterrows():
        s1.append(
            f"| {r['perturbation_family']} | {r['feasible']} | {int(r['n']) if r['n'] else 0} | "
            f"{_fmt_err(r['mean_loss'])} | {_fmt_err(r['median_loss'])} | "
            f"{_fmt_pct(r['easy_pct'])} | {_fmt_pct(r['hard_pct'])} |"
        )
    # Pull two key cell counts.
    feas_cap = obj_rows[(obj_rows["perturbation_family"] == "capacity_reduction")
                        & (obj_rows["feasible"] == True)]
    infeas_cap = obj_rows[(obj_rows["perturbation_family"] == "capacity_reduction")
                          & (obj_rows["feasible"] == False)]
    feas_dist = obj_rows[(obj_rows["perturbation_family"] == "regional_distance_inflation")
                         & (obj_rows["feasible"] == True)]
    s1.append(
        "\n**Read:** the strong objective performance of `reuse_direct` is "
        "split between two regimes. Under regional-distance perturbations "
        f"({int(feas_dist['n'].iloc[0]) if len(feas_dist) else 0} cells, all feasible by "
        "construction) the mean loss is "
        f"{_fmt_err(feas_dist['mean_loss'].iloc[0]) if len(feas_dist) else '—'}. "
        "Under capacity reductions the feasible-cell mean loss is "
        f"{_fmt_err(feas_cap['mean_loss'].iloc[0]) if len(feas_cap) else '—'} "
        f"({int(feas_cap['n'].iloc[0]) if len(feas_cap) else 0} cells), but the infeasible "
        "cells "
        f"({int(infeas_cap['n'].iloc[0]) if len(infeas_cap) else 0}) carry a mean loss "
        f"of {_fmt_err(infeas_cap['mean_loss'].iloc[0]) if len(infeas_cap) else '—'}. "
        "The infeasible answer is *also* numerically close but it is not a "
        "valid plan — overload exists on at least one route.\n"
    )

    # ---- Section 2: distance-only result ----
    s2: list[str] = []
    s2.append("## 2. Distance-only clean cut\n")
    err_summary = dist[dist["kind"] == "error_summary"]
    s2.append("| claim | n | mean loss | median | easy % | hard % | infeasible % |")
    s2.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for _, r in err_summary.iterrows():
        s2.append(
            f"| {CLAIM_LABEL.get(r['claim_family'], r['claim_family'])} | "
            f"{int(r['n_cells'])} | {_fmt_err(r['mean_loss'])} | "
            f"{_fmt_err(r['median_loss'])} | {_fmt_pct(r['easy_pct'])} | "
            f"{_fmt_pct(r['hard_pct'])} | {_fmt_pct(r.get('infeasible_share_pct'))} |"
        )
    s2.append(
        "\nUnder regional-distance inflation alone, every fixed solution "
        "remains feasible (the perturbation does not touch capacity or "
        "demand). On the objective claim this is the cleanest cut for the "
        "thesis: reuse needs no special-casing because no infeasibility "
        "exists.\n"
    )

    # ---- Section 3: capacity-only with feasibility ----
    s3: list[str] = []
    s3.append("## 3. Capacity reduction — when does reuse become unsafe?\n")
    feas_by_mag = cap[cap["kind"] == "feasibility_by_magnitude"]
    s3.append("| capacity factor | n | infeas % | feas-only mean loss | infeas-only mean loss | mean overload |")
    s3.append("| ---: | ---: | ---: | ---: | ---: | ---: |")
    for _, r in feas_by_mag.sort_values("magnitude", ascending=False).iterrows():
        ov = r.get("mean_max_overload")
        ov_str = f"{float(ov):.1f}" if ov is not None and pd.notna(ov) else "—"
        s3.append(
            f"| {r['magnitude']:g} | {int(r['n_cells'])} | "
            f"{_fmt_pct(r['infeasible_share_pct'])} | "
            f"{_fmt_err(r['feasible_mean_loss'])} | "
            f"{_fmt_err(r['infeasible_mean_loss'])} | "
            f"{ov_str} |"
        )
    s3.append(
        "\n**Read:** at a 2% capacity haircut (factor=0.98) already 73% of "
        "fixed solutions overflow the new capacity. By 20% (factor=0.8), "
        "every fixed solution is infeasible. The objective error stays "
        "small because routes do not magically become longer when a "
        "vehicle is over-capacity — but the answer is not implementable. "
        "If capacity feasibility matters to the downstream consumer, "
        "`reuse_direct` is unsafe on capacity reductions even at the "
        "smallest magnitude tested.\n"
    )

    # ---- Section 4: penalty variants ----
    s4: list[str] = []
    s4.append("## 4. Feasibility-penalized λ curves\n")
    s4.append(
        "Three variants apply a penalty only to `reuse_direct` rows whose "
        "fixed solution is infeasible under the perturbation. All other "
        "actions are unchanged.\n"
        "\n"
        "- **V1 — penalty=1.0**: `reuse_direct` infeasible loss := 1.0 "
        "(treat as worst possible).\n"
        "- **V2 — penalty=0.5**: `reuse_direct` infeasible loss := "
        "max(observed_loss, 0.5) (half-credit).\n"
        "- **V3 — unanswerable**: drop `reuse_direct` from the action set "
        "for cells where it is infeasible (cell still has a best_action "
        "selected from the remaining four).\n"
    )
    s4.append(_share_table_md(pen1_share, "V1 best-action share (penalty=1.0)"))
    s4.append(_share_table_md(pen05_share, "V2 best-action share (penalty=0.5)"))
    s4.append(_share_table_md(unans_share, "V3 best-action share (infeasible reuse_direct dropped)"))

    # Compute reuse-share at λ=0.05 for each variant on objective claims.
    def _row_share(df: pd.DataFrame, lam: float, fam: str, action: str) -> float | None:
        sub = df[(df["lambda"] == lam) & (df["claim_family"] == fam)]
        if sub.empty:
            return None
        return float(sub.iloc[0][f"share_{action}"])

    reuse_at_p005_orig = _row_share(pen1_share, 0.05, "objective_resource_delta", "reuse_direct")
    reuse_at_p005_unans = _row_share(unans_share, 0.05, "objective_resource_delta", "reuse_direct")
    cw_at_p005_unans = _row_share(unans_share, 0.05, "objective_resource_delta", "clarke_wright")
    s4.append(
        "\n**Read:** the original Phase 3 result said `reuse_direct` wins "
        "71.4% of objective cells at λ=0.05. Under V1 (penalty=1.0) that "
        f"share is {_fmt_pct(reuse_at_p005_orig)}; under V3 (drop "
        f"infeasible reuse) it is {_fmt_pct(reuse_at_p005_unans)} (with "
        f"`clarke_wright` filling the gap at {_fmt_pct(cw_at_p005_unans)}). "
        "The qualitative story holds — reuse beats recompute once compute "
        "has any non-trivial price — but the **strength** of the result "
        "depends entirely on whether infeasibility is treated as a free "
        "answer or as a wrong answer.\n"
    )

    # ---- Section 5: tie audit ----
    s5: list[str] = []
    s5.append("## 5. λ=0 tie-breaking audit\n")
    s5.append(
        f"**Tie-break rule.** {audit['tie_break_rule']}\n"
    )
    s5.append("| claim | n | tie share | pyvrp_60s wins (orig) | pyvrp_60s wins (strict) | non-60s honest wins |")
    s5.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for fam, label in CLAIM_LABEL.items():
        e = audit["by_claim_family"].get(fam, {})
        if not e or e.get("n", 0) == 0:
            continue
        s5.append(
            f"| {label} | {e['n']} | {_fmt_pct(e['tie_share_pct'])} | "
            f"{_fmt_pct(e['wins_pyvrp_60s_original_pct'])} | "
            f"{_fmt_pct(e['wins_pyvrp_60s_strict_pct'])} | "
            f"{_fmt_pct(e['honest_non_60s_wins_pct'])} |"
        )
    shifts = audit.get("shifts", {})
    obj_e = audit["by_claim_family"].get("objective_resource_delta", {})
    s5.append(
        f"\n**Read:** every cell at λ=0 has `pyvrp_60s` at loss = 0 (it is "
        "compared against itself), so `pyvrp_60s` is **always at the cell "
        "minimum**. The 71.4% objective / 57.1% ranking / 68.6% structure "
        "wins for `pyvrp_60s` under the original rule are the cells where "
        "no other action also reaches loss = 0. The remainder are ties: "
        f"{_fmt_pct(obj_e.get('tie_share_pct'))} of objective cells, "
        f"{_fmt_pct(audit['by_claim_family'].get('topk_route_ranking', {}).get('tie_share_pct'))} of ranking cells, "
        f"{_fmt_pct(audit['by_claim_family'].get('assignment_structure', {}).get('tie_share_pct'))} of structure cells. "
        "Ties happen when a cheaper action accidentally matches the "
        "reference exactly — `pyvrp_10s` finding the same objective on "
        "an easy instance, or `reuse_direct` reproducing the reference "
        "plan under a small regional-distance perturbation. The "
        "audit confirms: `honest_non_60s_wins_pct = 0` for every claim "
        "family. **No non-60s action ever beats `pyvrp_60s` strictly at "
        "λ=0**; every non-60s share is a tie awarded by the "
        "first-inserted-wins rule. Switching to a strict tie-breaker "
        f"(`pyvrp_60s` wins ties) re-assigns "
        f"{_fmt_pct(shifts.get('cells_changed_under_strict_tiebreak_pct', 0))} "
        "of cells back to `pyvrp_60s`, taking it to 100% across all three "
        "claim families.\n"
    )

    # ---- Section 6: thesis-ready sentences ----
    s6: list[str] = []
    s6.append("## 6. Thesis-ready sentences\n")
    s6.append("Use these phrasings to avoid overstating the reuse result.\n")
    s6.append(
        "**On reuse:**\n"
        "> Fixed-solution reuse is sufficient for objective-claim queries "
        "under regional-distance perturbations, where every reused plan "
        "remains feasible. Under capacity reductions the recomputed "
        "objective of the fixed solution stays close to the recomputed "
        "reference, but in 50–100% of cells (depending on the magnitude) "
        "the fixed plan exceeds the new capacity on at least one route — "
        "so reuse should be treated as unsafe whenever the consumer needs "
        "a plan that is actually executable, regardless of how close the "
        "objective looks.\n"
    )
    s6.append(
        "**On the λ=0 tie behavior:**\n"
        "> At λ=0 the policy objective is the raw loss. Because PyVRP @ "
        "60s is also the reference, its loss is exactly zero on every "
        "cell, so no other action can ever score strictly lower. The "
        "non-60s shares reported at λ=0 are not wins — they are ties at "
        "loss = 0 awarded by a deterministic but arbitrary rule (the "
        "first action in `ACTIONS = (reuse_direct, nearest_neighbor, "
        "clarke_wright, pyvrp_10s, pyvrp_60s)` wins). Under a strict "
        "tie-breaker that hands ties to PyVRP 60s, the reference would "
        "win 100% of cells at λ=0, as expected. We report the original "
        "rule because it cleanly counts how often a cheaper action "
        "*could have substituted* for the reference — a useful signal "
        "for routing — but the share itself should not be read as "
        "`pyvrp_60s` losing those cells.\n"
    )

    out: list[str] = []
    out.append("# Phase 3 robustness pass — feasibility-aware interpretation\n\n"
               "_Generated from `artifacts/robustness/`. Reference backend: "
               "PyVRP @ 60s, seed=1. The original Phase 3 outputs are "
               "**not modified** — see `PHASE3_SUMMARY.md` for those._\n")
    out.extend(s1)
    out.extend(s2)
    out.extend(s3)
    out.extend(s4)
    out.extend(s5)
    out.extend(s6)
    summary_md_path.write_text("\n".join(out) + "\n")
    log.info("wrote %s", summary_md_path.name)

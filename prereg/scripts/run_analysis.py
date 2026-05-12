"""Pre-lock data analysis for VRP copilot sufficiency benchmark.

Computes:
  A. Slack profile across the 15 baseline (unperturbed) PyVRP 60s seed=1 solutions.
  B. Per-instance capacity-reduction feasibility breakpoint.
  C. Operational sufficiency label distribution (claim x perturbation).
  D. Predictability sanity check via leave-one-instance-out logistic regression.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

REPO = Path("/Users/jd/Documents/copilot-opt/vrp-copilot-benchmark")
PREREG = Path("/Users/jd/Documents/copilot-opt/prereg")
DATA_DIR = PREREG / "data"
FIG_DIR = PREREG / "figures"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

PHASE1_SOLNS = REPO / "reports" / "phase1" / "solutions.jsonl"
PHASE3_REUSE = (
    REPO
    / "experiments"
    / "phase3_information_sufficiency"
    / "artifacts"
    / "phase3_reuse_direct_results.csv"
)
INSTANCE_REGISTRY = REPO / "data" / "processed" / "instance_registry.csv"


# ---------------------------------------------------------------------------
# Load baselines.
# ---------------------------------------------------------------------------
def load_nominal_pyvrp60s_baselines() -> dict[str, dict]:
    """Return {instance_id: {routes, route_loads, capacity, ...}}."""
    out: dict[str, dict] = {}
    with PHASE1_SOLNS.open() as f:
        for line in f:
            d = json.loads(line)
            if d.get("backend_name") != "pyvrp":
                continue
            scenario = d.get("metadata", {}).get("scenario")
            if scenario not in (None, "unknown", "nominal"):
                continue
            if d.get("random_seed") != 1:
                continue
            if d.get("time_limit_sec") != 60.0:
                continue
            out[d["instance_id"]] = d
    return out


registry = pd.read_csv(INSTANCE_REGISTRY)
capacity_by_instance = dict(zip(registry["instance_id"], registry["capacity"]))
baselines = load_nominal_pyvrp60s_baselines()
INSTANCE_IDS = sorted(baselines.keys())
print(f"[load] {len(baselines)} baseline solutions, {len(INSTANCE_IDS)} instances")
assert len(INSTANCE_IDS) == 15, "Expected 15 baselines"


# ---------------------------------------------------------------------------
# A. Slack profile.
# ---------------------------------------------------------------------------
slack_rows = []
for iid in INSTANCE_IDS:
    sol = baselines[iid]
    cap = float(capacity_by_instance[iid])
    loads = np.array(sol["route_loads"], dtype=float)
    slacks = cap - loads
    slack_rows.append(
        {
            "instance_id": iid,
            "n_routes": int(len(loads)),
            "vehicle_capacity": cap,
            "min_slack": float(slacks.min()),
            "p10_slack": float(np.percentile(slacks, 10)),
            "median_slack": float(np.median(slacks)),
            "max_slack": float(slacks.max()),
            "min_slack_ratio": float(slacks.min() / cap),
        }
    )
slack_df = pd.DataFrame(slack_rows)
slack_df.to_csv(DATA_DIR / "slack_profile.csv", index=False)
print("[A] slack_profile rows:", len(slack_df))
print(slack_df.to_string(index=False))

ratios = slack_df["min_slack_ratio"].values
n_below_002 = int((ratios < 0.02).sum())
n_below_005 = int((ratios < 0.05).sum())
median_ratio = float(np.median(ratios))
print(f"[A] min_slack_ratio < 0.02: {n_below_002}/15")
print(f"[A] min_slack_ratio < 0.05: {n_below_005}/15")
print(f"[A] median min_slack_ratio: {median_ratio:.4f}")

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.hist(ratios, bins=np.linspace(0, max(0.3, ratios.max() + 0.01), 16),
        edgecolor="black", color="#4c72b0")
ax.axvline(0.02, color="red", linestyle="--", label="0.02 floor")
ax.set_xlabel("min_slack_ratio = min(capacity − route_load) / capacity")
ax.set_ylabel("# instances (of 15)")
ax.set_title("Distribution of min_slack_ratio across 15 Phase-3 instances")
ax.legend()
fig.tight_layout()
fig.savefig(FIG_DIR / "slack_distribution.png", dpi=150)
plt.close(fig)


# ---------------------------------------------------------------------------
# B. Capacity-reduction feasibility breakpoint.
# ---------------------------------------------------------------------------
def overload_count(loads: np.ndarray, new_capacity: float) -> int:
    return int((loads > new_capacity + 1e-9).sum())


alphas = np.round(np.arange(0.0, 5.001, 0.1), 4)


def sweep_breakpoint(cap: float, loads: np.ndarray, ratio: float) -> tuple[float, dict]:
    """Sweep α; return (breakpoint_alpha, {target_alpha: overload_count})."""
    bp = math.inf
    overloads_at: dict[float, int] = {}
    for a in alphas:
        new_cap = cap * (1.0 - a * ratio)
        n_over = overload_count(loads, new_cap)
        if n_over > 0 and bp is math.inf:
            bp = float(a)
        for target in (0.5, 1.0, 1.5, 2.5):
            if abs(a - target) < 1e-6:
                overloads_at[target] = n_over
    return bp, overloads_at


break_rows = []
break_rows_anchor = []
for iid in INSTANCE_IDS:
    cap = float(capacity_by_instance[iid])
    loads = np.array(baselines[iid]["route_loads"], dtype=float)
    slacks = cap - loads
    msr = float(slacks.min() / cap)            # literal min_slack_ratio
    p10 = float(np.percentile(slacks, 10))
    anchor = max(p10, 0.02 * cap)              # proposed slack_anchor
    anchor_ratio = anchor / cap

    bp, overloads_at = sweep_breakpoint(cap, loads, msr)
    bp2, overloads_at2 = sweep_breakpoint(cap, loads, anchor_ratio)

    break_rows.append({
        "instance_id": iid,
        "breakpoint_alpha": bp if bp is not math.inf else float("inf"),
        "n_overload_at_alpha_0_5": overloads_at.get(0.5, 0),
        "n_overload_at_alpha_1_0": overloads_at.get(1.0, 0),
        "n_overload_at_alpha_1_5": overloads_at.get(1.5, 0),
        "n_overload_at_alpha_2_5": overloads_at.get(2.5, 0),
    })
    break_rows_anchor.append({
        "instance_id": iid,
        "slack_anchor_ratio": anchor_ratio,
        "breakpoint_alpha_anchor": bp2 if bp2 is not math.inf else float("inf"),
        "n_overload_at_alpha_0_5": overloads_at2.get(0.5, 0),
        "n_overload_at_alpha_1_0": overloads_at2.get(1.0, 0),
        "n_overload_at_alpha_1_5": overloads_at2.get(1.5, 0),
        "n_overload_at_alpha_2_5": overloads_at2.get(2.5, 0),
    })

break_df = pd.DataFrame(break_rows)
break_df.to_csv(DATA_DIR / "feasibility_breakpoint.csv", index=False)
break_anchor_df = pd.DataFrame(break_rows_anchor)
break_anchor_df.to_csv(DATA_DIR / "feasibility_breakpoint_anchor.csv", index=False)
print("\n[B] feasibility_breakpoint (literal min_slack_ratio):")
print(break_df.to_string(index=False))
print("\n[B] feasibility_breakpoint (slack_anchor = max(p10, 0.02*cap)):")
print(break_anchor_df.to_string(index=False))

def bucket(ba: np.ndarray) -> dict:
    return {
        "[0,0.5]": int(((ba >= 0) & (ba <= 0.5)).sum()),
        "(0.5,1.0]": int(((ba > 0.5) & (ba <= 1.0)).sum()),
        "(1.0,1.5]": int(((ba > 1.0) & (ba <= 1.5)).sum()),
        "(1.5,inf)": int((ba > 1.5).sum()),
    }


ba = break_df["breakpoint_alpha"].values
ba_anchor = break_anchor_df["breakpoint_alpha_anchor"].values
buckets = bucket(ba)
buckets_anchor = bucket(ba_anchor)
print(f"[B] buckets (literal): {buckets}")
print(f"[B] buckets (anchor):  {buckets_anchor}")

fig, axes = plt.subplots(1, 2, figsize=(11, 3.5), sharey=True)
for ax, vals, title in [
    (axes[0], ba, "Literal: msr = min_slack/cap"),
    (axes[1], ba_anchor, "Anchored: max(p10_slack, 0.02·cap)/cap"),
]:
    finite = vals[np.isfinite(vals)]
    if len(finite) == 0:
        ax.text(0.5, 0.5, "all breakpoints = ∞", transform=ax.transAxes,
                ha="center", va="center", color="red")
        ax.set_xlim(0, 3)
    else:
        bins = np.arange(0, max(3.0, finite.max() + 0.2), 0.1)
        ax.hist(finite, bins=bins, edgecolor="black", color="#55a868")
    n_inf = int((~np.isfinite(vals)).sum())
    if n_inf > 0:
        ax.text(0.98, 0.95, f"∞: {n_inf}/15", transform=ax.transAxes,
                ha="right", va="top", color="red", fontsize=9)
    for x, lab in [(0.5, "α=0.5"), (1.0, "α=1.0"), (1.5, "α=1.5"), (2.5, "α=2.5")]:
        ax.axvline(x, color="red", linestyle="--", alpha=0.5)
    ax.set_xlabel("breakpoint α")
    ax.set_title(title)
axes[0].set_ylabel("# instances")
fig.suptitle("Breakpoint α distribution (CAP perturbation grid)")
fig.tight_layout()
fig.savefig(FIG_DIR / "breakpoint_distribution.png", dpi=150)
plt.close(fig)


# ---------------------------------------------------------------------------
# C. Label distribution by (claim_family x perturbation_family).
# ---------------------------------------------------------------------------
phase3 = pd.read_csv(PHASE3_REUSE)
print(f"\n[C] phase3 reuse_direct rows: {len(phase3)}")

# Sufficiency thresholds from prereg.
# - OBJ: stored loss (= |o_a-o_b|/max(...)) <= 0.05 AND feasible_under_perturbation.
# - STRUCT: stored error = (1-ARI)/2 <= 0.05 (i.e. ARI >= 0.90).
# - RANK: stored error = 1 - top_k_overlap <= 0.50.
def compute_sufficiency(row) -> int:
    fam = row["claim_family"]
    err = row["error"]
    if pd.isna(err):
        return 0
    if fam == "objective_resource_delta":
        feasible = bool(row["feasible_under_perturbation"]) if pd.notna(row["feasible_under_perturbation"]) else False
        return int(err <= 0.05 and feasible)
    if fam == "assignment_structure":
        return int(err <= 0.05)
    if fam == "topk_route_ranking":
        return int(err <= 0.50)
    return 0


phase3["sufficient"] = phase3.apply(compute_sufficiency, axis=1)

family_map = {
    "objective_resource_delta": "OBJ",
    "assignment_structure": "STRUCT",
    "topk_route_ranking": "RANK",
}
phase3["claim_short"] = phase3["claim_family"].map(family_map)

claim_order = ["OBJ", "STRUCT", "RANK"]
pert_order = ["capacity_reduction", "regional_distance_inflation"]

label_table = pd.DataFrame(index=claim_order, columns=pert_order, dtype=object)
heatmap_p = np.zeros((len(claim_order), len(pert_order)))
heatmap_n = np.zeros((len(claim_order), len(pert_order)), dtype=int)
for i, claim in enumerate(claim_order):
    for j, pert in enumerate(pert_order):
        sub = phase3[(phase3["claim_short"] == claim) & (phase3["perturbation_family"] == pert)]
        n = len(sub)
        if n == 0:
            label_table.loc[claim, pert] = "n=0"
            continue
        p = float(sub["sufficient"].mean())
        label_table.loc[claim, pert] = f"P={p:.2f}, n={n}"
        heatmap_p[i, j] = p
        heatmap_n[i, j] = n

print("\n[C] sufficiency table:")
print(label_table.to_string())
label_table.to_csv(DATA_DIR / "label_distribution.csv")

# Identify failing blocks.
failing = []
for i, claim in enumerate(claim_order):
    for j, pert in enumerate(pert_order):
        if heatmap_n[i, j] == 0:
            continue
        p = heatmap_p[i, j]
        if p < 0.10 or p > 0.90:
            kind = "too positive" if p > 0.90 else "too negative"
            failing.append((claim, pert, p, kind))
print(f"[C] failing blocks (P outside [0.10, 0.90]): {failing}")

fig, ax = plt.subplots(figsize=(6, 3.5))
im = ax.imshow(heatmap_p, vmin=0, vmax=1, cmap="RdYlGn")
ax.set_xticks(range(len(pert_order)))
ax.set_xticklabels([p.replace("_", "\n") for p in pert_order])
ax.set_yticks(range(len(claim_order)))
ax.set_yticklabels(claim_order)
for i in range(len(claim_order)):
    for j in range(len(pert_order)):
        ax.text(j, i, f"{heatmap_p[i, j]:.2f}\nn={heatmap_n[i, j]}",
                ha="center", va="center", color="black", fontsize=10)
ax.set_title("P(operational_sufficiency=1) per (claim, perturbation)")
fig.colorbar(im, ax=ax, label="P(sufficient)")
fig.tight_layout()
fig.savefig(FIG_DIR / "label_distribution.png", dpi=150)
plt.close(fig)


# ---------------------------------------------------------------------------
# D. Predictability sanity check.
# ---------------------------------------------------------------------------
df = phase3[["instance_id", "claim_short", "perturbation_family",
             "perturbation_magnitude", "sufficient"]].copy()
df = df.dropna(subset=["sufficient"]).reset_index(drop=True)
print(f"\n[D] training rows: {len(df)}")

# z-score perturbation_magnitude WITHIN family.
def zscore_within(g: pd.Series) -> pd.Series:
    sd = g.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return g * 0.0
    return (g - g.mean()) / sd

df["mag_z"] = df.groupby("perturbation_family")["perturbation_magnitude"].transform(zscore_within)

claims = sorted(df["claim_short"].unique())
perts = sorted(df["perturbation_family"].unique())
def one_hot(s: pd.Series, levels: list[str]) -> np.ndarray:
    return np.column_stack([(s == lv).astype(int) for lv in levels])

X1 = one_hot(df["claim_short"], claims)
X2 = np.column_stack([
    one_hot(df["claim_short"], claims),
    one_hot(df["perturbation_family"], perts),
    df["mag_z"].values.reshape(-1, 1),
])
y = df["sufficient"].values
groups = df["instance_id"].values

def loio_auroc(X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> list[float]:
    """Leave-one-instance-out: per-fold AUROC on held-out instance."""
    aurocs = []
    for inst in INSTANCE_IDS:
        train_mask = groups != inst
        test_mask = groups == inst
        if test_mask.sum() == 0:
            continue
        y_test = y[test_mask]
        if len(np.unique(y_test)) < 2:
            # AUROC undefined on a fold with only one class — skip fold.
            continue
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(X[train_mask], y[train_mask])
        proba = clf.predict_proba(X[test_mask])[:, 1]
        aurocs.append(roc_auc_score(y_test, proba))
    return aurocs


aurocs1 = loio_auroc(X1, y, groups)
aurocs2 = loio_auroc(X2, y, groups)
print(f"[D] Model 1 folds usable: {len(aurocs1)}/15, AUROC mean={np.mean(aurocs1):.3f}")
print(f"[D] Model 2 folds usable: {len(aurocs2)}/15, AUROC mean={np.mean(aurocs2):.3f}")


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 0):
    rng = np.random.default_rng(seed)
    if len(values) == 0:
        return (float("nan"), float("nan"), float("nan"))
    arr = np.array(values)
    boot_means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)]
    return float(np.mean(arr)), float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))


m1_mean, m1_lo, m1_hi = bootstrap_ci(aurocs1)
m2_mean, m2_lo, m2_hi = bootstrap_ci(aurocs2)
gap = m2_mean - m1_mean
print(f"[D] Model 1 AUROC = {m1_mean:.3f} (95% CI {m1_lo:.3f}, {m1_hi:.3f})  n_folds={len(aurocs1)}")
print(f"[D] Model 2 AUROC = {m2_mean:.3f} (95% CI {m2_lo:.3f}, {m2_hi:.3f})  n_folds={len(aurocs2)}")
print(f"[D] gap = {gap:+.3f}")

# Save summary JSON for the report.
summary = {
    "A": {
        "n_below_002": n_below_002,
        "n_below_005": n_below_005,
        "median_min_slack_ratio": median_ratio,
        "ratios": ratios.tolist(),
    },
    "B": {
        "buckets_literal": buckets,
        "buckets_anchor": buckets_anchor,
        "breakpoint_alphas_literal": [
            (iid, ba_) for iid, ba_ in zip(break_df["instance_id"], break_df["breakpoint_alpha"])
        ],
        "breakpoint_alphas_anchor": [
            (iid, ba_) for iid, ba_ in zip(break_anchor_df["instance_id"],
                                           break_anchor_df["breakpoint_alpha_anchor"])
        ],
    },
    "C": {
        "table": {claim: {pert: {"p": float(heatmap_p[i, j]), "n": int(heatmap_n[i, j])}
                          for j, pert in enumerate(pert_order)}
                  for i, claim in enumerate(claim_order)},
        "failing_blocks": failing,
    },
    "D": {
        "model1": {"mean": m1_mean, "ci_lo": m1_lo, "ci_hi": m1_hi, "n_folds": len(aurocs1)},
        "model2": {"mean": m2_mean, "ci_lo": m2_lo, "ci_hi": m2_hi, "n_folds": len(aurocs2)},
        "gap": gap,
    },
}
(DATA_DIR / "_summary.json").write_text(json.dumps(summary, indent=2, default=str))
print("\n[done] artifacts written under", PREREG)

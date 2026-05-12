"""Observable comparison metrics over SolutionArtifacts.

Definitions are locked per Phase 1 protocol:
- route ranking := route distance contribution
- top-k := 3
- assignment disagreement := adjusted Rand index on customer co-assignment
- routes are NOT matched by index; customer-level ranking is deferred
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..artifacts.solution import SolutionArtifact


TOP_K_DEFAULT = 3


def _finite_or_none(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def adjusted_rand_index(labels_a: list[int], labels_b: list[int]) -> float:
    """Compute ARI over a common customer index space.

    Both label lists are aligned 1:1 by index; unassigned customers (label -1)
    are kept as a distinct cluster label so that assignment drops/pickups do
    not silently inflate agreement.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("label vectors must have equal length")
    n = len(labels_a)
    if n == 0:
        return float("nan")

    a = np.asarray(labels_a, dtype=int)
    b = np.asarray(labels_b, dtype=int)

    # Re-index labels densely so -1 becomes a normal cluster.
    def _densify(x: np.ndarray) -> np.ndarray:
        uniq = {v: i for i, v in enumerate(sorted(set(x.tolist())))}
        return np.array([uniq[v] for v in x.tolist()], dtype=int)

    a = _densify(a)
    b = _densify(b)

    # Contingency table
    na, nb = int(a.max()) + 1, int(b.max()) + 1
    cont = np.zeros((na, nb), dtype=np.int64)
    for i, j in zip(a, b):
        cont[i, j] += 1

    def _comb2(x: np.ndarray | int) -> np.ndarray | int:
        return x * (x - 1) // 2

    sum_comb_c = _comb2(cont).sum()
    sum_comb_a = _comb2(cont.sum(axis=1)).sum()
    sum_comb_b = _comb2(cont.sum(axis=0)).sum()
    total = _comb2(n)
    if total == 0:
        return float("nan")
    expected = sum_comb_a * sum_comb_b / total
    max_index = 0.5 * (sum_comb_a + sum_comb_b)
    if max_index == expected:
        return 1.0
    return float((sum_comb_c - expected) / (max_index - expected))


def top_k_route_overlap(
    a: SolutionArtifact,
    b: SolutionArtifact,
    k: int = TOP_K_DEFAULT,
) -> float:
    """Jaccard-style overlap of the top-k routes by distance contribution.

    Each route is represented as the frozenset of its visited customers.
    Overlap = |shared routes| / k, capped at 1.0. Returns NaN if either side
    has no routes.
    """
    if not a.routes or not b.routes:
        return float("nan")

    def top_route_sets(art: SolutionArtifact) -> list[frozenset[int]]:
        rd = art.route_distances or []
        if len(rd) != len(art.routes) or not rd:
            # Fall back to equal ranking
            ranked = list(range(len(art.routes)))
        else:
            ranked = sorted(range(len(art.routes)), key=lambda i: -rd[i])
        sets = [frozenset(art.routes[i]) for i in ranked[:k]]
        return sets

    sa = top_route_sets(a)
    sb = top_route_sets(b)
    if not sa or not sb:
        return float("nan")

    matched = 0
    sb_remaining = list(sb)
    for r in sa:
        for i, s in enumerate(sb_remaining):
            if r == s:
                matched += 1
                sb_remaining.pop(i)
                break
    return matched / k


@dataclass
class ComparisonResult:
    instance_id: str
    backend_a: str
    backend_b: str
    feasible_both: bool
    objective_a: float | None
    objective_b: float | None
    objective_gap_abs: float | None
    objective_gap_rel: float | None
    route_count_a: int | None
    route_count_b: int | None
    route_count_diff: int | None
    adjusted_rand_assignment: float | None
    top_k_route_overlap: float | None
    bks_objective: float | None = None
    gap_to_bks_pct_a: float | None = None
    gap_to_bks_pct_b: float | None = None

    def as_row(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "backend_a": self.backend_a,
            "backend_b": self.backend_b,
            "feasible_both": self.feasible_both,
            "objective_a": self.objective_a,
            "objective_b": self.objective_b,
            "objective_gap_abs": self.objective_gap_abs,
            "objective_gap_rel": self.objective_gap_rel,
            "route_count_a": self.route_count_a,
            "route_count_b": self.route_count_b,
            "route_count_diff": self.route_count_diff,
            "adjusted_rand_assignment": self.adjusted_rand_assignment,
            "top_k_route_overlap": self.top_k_route_overlap,
            "bks_objective": self.bks_objective,
            "gap_to_bks_pct_a": self.gap_to_bks_pct_a,
            "gap_to_bks_pct_b": self.gap_to_bks_pct_b,
        }


def compare(
    a: SolutionArtifact,
    b: SolutionArtifact,
    *,
    n_customers: int,
    bks_objective: float | None = None,
    k: int = TOP_K_DEFAULT,
) -> ComparisonResult:
    """Compute Phase 1 observable comparison metrics between two artifacts."""
    oa = _finite_or_none(a.objective)
    ob = _finite_or_none(b.objective)

    feasible_both = a.status == "ok" and b.status == "ok"

    obj_gap_abs: float | None = None
    obj_gap_rel: float | None = None
    if oa is not None and ob is not None:
        obj_gap_abs = oa - ob
        # Relative gap uses the better of the two as denominator to avoid
        # asymmetry that would depend on which argument is "a".
        denom = max(abs(oa), abs(ob), 1e-9)
        obj_gap_rel = obj_gap_abs / denom

    rc_a = a.n_routes
    rc_b = b.n_routes
    rc_diff = (rc_a - rc_b) if (rc_a is not None and rc_b is not None) else None

    ari: float | None = None
    overlap: float | None = None
    if feasible_both:
        la = a.route_assignment(n_customers)
        lb = b.route_assignment(n_customers)
        ari = adjusted_rand_index(la, lb)
        overlap = top_k_route_overlap(a, b, k=k)

    def _gap_to_bks(obj: float | None) -> float | None:
        if obj is None or bks_objective is None or bks_objective == 0:
            return None
        return 100.0 * (obj - bks_objective) / bks_objective

    return ComparisonResult(
        instance_id=a.instance_id,
        backend_a=a.backend_name,
        backend_b=b.backend_name,
        feasible_both=feasible_both,
        objective_a=oa,
        objective_b=ob,
        objective_gap_abs=obj_gap_abs,
        objective_gap_rel=obj_gap_rel,
        route_count_a=rc_a,
        route_count_b=rc_b,
        route_count_diff=rc_diff,
        adjusted_rand_assignment=ari,
        top_k_route_overlap=overlap,
        bks_objective=bks_objective,
        gap_to_bks_pct_a=_gap_to_bks(oa),
        gap_to_bks_pct_b=_gap_to_bks(ob),
    )

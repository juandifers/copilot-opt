"""Phase 3 wrapper around the claim-family metrics.

Two reasons we don't call ``vrpbench.claims.families.compute_claim_errors``
directly:

  1. It gates structural claims on ``status == "ok"`` for both sides. For
     ``reuse_direct`` we WANT the structural comparison even when the
     fixed solution is no longer feasible — the routes are still
     well-defined objects to compare to the reference's routes. Whether
     the answer is "safe" is a separate (orthogonal) question we record
     as the ``feasible_under_perturbation`` flag.

  2. It uses the canonical (cheap, strong) framing. In Phase 3 the
     "candidate" can be a recompute action (PyVRP 10s) and the
     "reference" can be PyVRP 60s — the same backend, just at different
     budgets. The cheap/strong labelling does not apply.

Returned errors mirror the families.py definitions exactly:
  objective_resource_delta : |o_a - o_b| / max(|o_a|, |o_b|, 1e-9)
  topk_route_ranking       : 1 - top_k_route_overlap (NaN-safe)
  assignment_structure     : (1 - ARI) / 2 clamped to [0, 1]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from vrpbench.artifacts.solution import SolutionArtifact
from vrpbench.evaluation.metrics import (
    TOP_K_DEFAULT,
    adjusted_rand_index,
    top_k_route_overlap,
)


@dataclass
class Phase3ClaimErrors:
    objective_resource_delta: float | None
    topk_route_ranking: float | None
    assignment_structure: float | None


def _safe(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def claim_errors(
    candidate: SolutionArtifact,
    reference: SolutionArtifact,
    *,
    n_customers: int,
    k: int = TOP_K_DEFAULT,
) -> Phase3ClaimErrors:
    """Compute per-family error of ``candidate`` vs ``reference``.

    Structural claims (topk, assignment) are computed whenever both sides
    have non-empty ``routes``, regardless of status. Objective error is
    computed whenever both sides report a finite objective.
    """
    oa = _safe(candidate.objective)
    ob = _safe(reference.objective)

    obj_err: float | None = None
    if oa is not None and ob is not None:
        denom = max(abs(oa), abs(ob), 1e-9)
        obj_err = abs(oa - ob) / denom

    topk_err: float | None = None
    ari_err: float | None = None
    if candidate.routes and reference.routes:
        overlap = top_k_route_overlap(candidate, reference, k=k)
        if overlap is not None and not math.isnan(overlap):
            topk_err = 1.0 - float(overlap)

        la = candidate.route_assignment(n_customers)
        lb = reference.route_assignment(n_customers)
        ari = adjusted_rand_index(la, lb)
        if ari is not None and not math.isnan(ari):
            ari_err = max(0.0, min(1.0, 1.0 - float(ari)))

    return Phase3ClaimErrors(
        objective_resource_delta=obj_err,
        topk_route_ranking=topk_err,
        assignment_structure=ari_err,
    )


def difficulty_label(family: str, error: float | None) -> str | None:
    """Per-claim-family easy/medium/hard cutoff (same as Phase 2R)."""
    if error is None:
        return None
    e = float(error)
    if family == "objective_resource_delta":
        if e < 0.05:
            return "easy"
        if e < 0.15:
            return "medium"
        return "hard"
    if family == "assignment_structure":
        # error = (1 - ARI)/2 clamped → ARI = 1 - 2*error
        ari = 1.0 - 2.0 * e
        if ari > 0.75:
            return "easy"
        if ari > 0.50:
            return "medium"
        return "hard"
    if family == "topk_route_ranking":
        # error = 1 - overlap → overlap = 1 - error
        overlap = 1.0 - e
        if overlap >= 0.67:
            return "easy"
        if overlap >= 0.33:
            return "medium"
        return "hard"
    return None

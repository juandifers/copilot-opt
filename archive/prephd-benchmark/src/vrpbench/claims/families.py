"""Claim-family definitions for Phase 2.

Three observable claim families are instantiated directly on the
SolutionArtifact pair (cheap, strong). Each family returns a scalar
"claim_error" in [0, inf) where 0 means the cheap backend's answer
matches the strong backend for that claim family. Missing values yield
None.

  - objective_resource_delta : relative objective error of the cheap
    backend vs the strong backend. Same denominator convention as
    compare()'s objective_gap_rel, but as an unsigned quantity.
  - topk_route_ranking       : 1 - top_k_route_overlap. 0 = cheap's
    highest-distance routes exactly match strong's.
  - assignment_structure     : (1 - ARI) / 2 clamped to [0, 1]. ARI = 1
    means perfect structural match; ARI = 0 means chance; ARI = -1 is
    worst-possible. We fold the worst case to 1.

No claim family uses BKS; all errors are cheap-vs-strong.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..artifacts.solution import SolutionArtifact
from ..evaluation.metrics import (
    adjusted_rand_index,
    top_k_route_overlap,
    TOP_K_DEFAULT,
)


CLAIM_FAMILIES: tuple[str, ...] = (
    "objective_resource_delta",
    "topk_route_ranking",
    "assignment_structure",
)


@dataclass
class ClaimErrors:
    instance_id: str
    cheap_backend: str
    strong_backend: str
    objective_resource_delta: float | None
    topk_route_ranking: float | None
    assignment_structure: float | None

    def as_rows(self, *, scenario: str) -> list[dict]:
        return [
            {
                "instance_id": self.instance_id,
                "cheap_backend": self.cheap_backend,
                "strong_backend": self.strong_backend,
                "scenario": scenario,
                "claim_family": fam,
                "claim_error": getattr(self, fam),
            }
            for fam in CLAIM_FAMILIES
        ]


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


def compute_claim_errors(
    cheap: SolutionArtifact,
    strong: SolutionArtifact,
    *,
    n_customers: int,
    k: int = TOP_K_DEFAULT,
) -> ClaimErrors:
    """Return per-claim-family errors cheap-vs-strong on a given scenario.

    Missing or infeasible artifacts yield None for that family, which
    downstream aggregators treat as 'no signal available'.
    """
    oa = _safe(cheap.objective)
    ob = _safe(strong.objective)

    obj_err: float | None = None
    if oa is not None and ob is not None:
        denom = max(abs(oa), abs(ob), 1e-9)
        obj_err = abs(oa - ob) / denom

    topk_err: float | None = None
    ari_err: float | None = None
    if cheap.status == "ok" and strong.status == "ok":
        overlap = top_k_route_overlap(cheap, strong, k=k)
        if overlap is not None and not math.isnan(overlap):
            topk_err = 1.0 - float(overlap)

        la = cheap.route_assignment(n_customers)
        lb = strong.route_assignment(n_customers)
        ari = adjusted_rand_index(la, lb)
        if ari is not None and not math.isnan(ari):
            # Fold negative ARI (worse-than-chance) to 1.
            ari_err = max(0.0, min(1.0, 1.0 - float(ari)))

    return ClaimErrors(
        instance_id=cheap.instance_id,
        cheap_backend=cheap.backend_name,
        strong_backend=strong.backend_name,
        objective_resource_delta=obj_err,
        topk_route_ranking=topk_err,
        assignment_structure=ari_err,
    )

"""Activation screening.

Three gates (all thresholds locked in phase1_pilot.yaml):

- nonzero_response       : did the perturbation move the objective at all?
- structural_response    : did the assignment/structure change meaningfully?
- backend_disagreement   : do the two backends diverge structurally, not just
                           on objective value?

Each gate produces a boolean plus the underlying numbers, so failures can
be inspected.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..artifacts.solution import SolutionArtifact
from .metrics import adjusted_rand_index


DEFAULT_THRESHOLDS = {
    "nonzero_response": {
        "objective_rel_change": 0.01,
        "route_count_change": True,
    },
    "structural_response": {
        "adjusted_rand_below": 0.95,
        "route_count_change": True,
    },
    "backend_disagreement": {
        "objective_gap_rel": 0.03,
        "adjusted_rand_below": 0.90,
    },
}


def _rel_change(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom


@dataclass
class ActivationRow:
    instance_id: str
    kind: str  # "perturbation" | "backend"
    tag: str   # e.g. "capacity_reduction@0.8" or "nn_vs_pyvrp"
    nonzero_response: bool
    structural_response: bool
    backend_disagreement: bool
    objective_rel_change: float | None
    route_count_change: bool | None
    adjusted_rand: float | None

    def as_row(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "kind": self.kind,
            "tag": self.tag,
            "nonzero_response": self.nonzero_response,
            "structural_response": self.structural_response,
            "backend_disagreement": self.backend_disagreement,
            "objective_rel_change": self.objective_rel_change,
            "route_count_change": self.route_count_change,
            "adjusted_rand": self.adjusted_rand,
        }


def screen_perturbation(
    baseline: SolutionArtifact,
    perturbed: SolutionArtifact,
    *,
    n_customers: int,
    tag: str,
    thresholds: dict | None = None,
) -> ActivationRow:
    """Nominal-vs-perturbed gate, computed per-backend.

    `nonzero_response` and `structural_response` are filled in. Backend
    disagreement is only meaningful between different backends, so it's
    always False here.
    """
    t = thresholds or DEFAULT_THRESHOLDS

    obj_rel: float | None = None
    nz = False
    if baseline.objective is not None and perturbed.objective is not None:
        obj_rel = _rel_change(baseline.objective, perturbed.objective)
        if obj_rel >= t["nonzero_response"]["objective_rel_change"]:
            nz = True

    route_count_change: bool | None = None
    if baseline.n_routes is not None and perturbed.n_routes is not None:
        route_count_change = baseline.n_routes != perturbed.n_routes
        if t["nonzero_response"]["route_count_change"] and route_count_change:
            nz = True

    ari: float | None = None
    structural = False
    if baseline.status == "ok" and perturbed.status == "ok":
        la = baseline.route_assignment(n_customers)
        lb = perturbed.route_assignment(n_customers)
        ari = adjusted_rand_index(la, lb)
        if ari is not None and not math.isnan(ari):
            if ari < t["structural_response"]["adjusted_rand_below"]:
                structural = True
        if t["structural_response"]["route_count_change"] and route_count_change:
            structural = True

    return ActivationRow(
        instance_id=baseline.instance_id,
        kind="perturbation",
        tag=tag,
        nonzero_response=nz,
        structural_response=structural,
        backend_disagreement=False,
        objective_rel_change=obj_rel,
        route_count_change=route_count_change,
        adjusted_rand=ari,
    )


def screen_backend_disagreement(
    cheap: SolutionArtifact,
    strong: SolutionArtifact,
    *,
    n_customers: int,
    tag: str = "cheap_vs_strong",
    thresholds: dict | None = None,
) -> ActivationRow:
    """Cheap-vs-strong gate: objective gap alone is not sufficient.

    A disagreement must be visible in *both* the objective-gap criterion
    AND the adjusted-Rand criterion, per protocol.
    """
    t = thresholds or DEFAULT_THRESHOLDS

    obj_rel: float | None = None
    obj_ok = False
    if cheap.objective is not None and strong.objective is not None:
        obj_rel = _rel_change(cheap.objective, strong.objective)
        obj_ok = obj_rel >= t["backend_disagreement"]["objective_gap_rel"]

    route_count_change: bool | None = None
    if cheap.n_routes is not None and strong.n_routes is not None:
        route_count_change = cheap.n_routes != strong.n_routes

    ari: float | None = None
    struct_ok = False
    if cheap.status == "ok" and strong.status == "ok":
        la = cheap.route_assignment(n_customers)
        lb = strong.route_assignment(n_customers)
        ari = adjusted_rand_index(la, lb)
        if ari is not None and not math.isnan(ari):
            struct_ok = ari < t["backend_disagreement"]["adjusted_rand_below"]

    disagreement = obj_ok and struct_ok

    return ActivationRow(
        instance_id=cheap.instance_id,
        kind="backend",
        tag=tag,
        nonzero_response=obj_ok,
        structural_response=struct_ok,
        backend_disagreement=disagreement,
        objective_rel_change=obj_rel,
        route_count_change=route_count_change,
        adjusted_rand=ari,
    )

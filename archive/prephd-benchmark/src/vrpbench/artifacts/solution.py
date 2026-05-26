"""SolutionArtifact model - the core observable unit.

Every solve (cheap or strong, nominal or perturbed) produces one of these.
Reproducibility fields (seed, time limit, solver version) are mandatory for
the strong backend; the cheap backend sets them to None where inapplicable.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SolutionArtifact(BaseModel):
    instance_id: str
    backend_name: str
    status: str  # "ok" | "infeasible" | "error" | "timeout"

    objective: float | None
    runtime_sec: float
    n_routes: int | None
    routes: list[list[int]] = Field(default_factory=list)

    route_loads: list[float] = Field(default_factory=list)
    route_distances: list[float] = Field(default_factory=list)

    random_seed: int | None = None
    time_limit_sec: float | None = None
    solver_params: dict[str, Any] = Field(default_factory=dict)
    solver_version: str | None = None
    run_id: str

    metadata: dict[str, Any] = Field(default_factory=dict)

    def route_assignment(self, n_customers: int) -> list[int]:
        """Return a length-n_customers vector mapping customer idx (1..n) to
        route index, or -1 if unassigned. Customers are 1-indexed in CVRPLIB."""
        assignment = [-1] * (n_customers + 1)  # idx 0 = depot, ignored
        for r_idx, route in enumerate(self.routes):
            for cust in route:
                if 0 < cust <= n_customers:
                    assignment[cust] = r_idx
        return assignment[1:]  # drop depot slot

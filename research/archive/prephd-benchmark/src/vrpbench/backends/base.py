"""Backend protocol and shared helpers."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from ..artifacts.solution import SolutionArtifact
from ..data.instance import VRPInstance


class Backend(Protocol):
    name: str

    def solve(self, instance: VRPInstance, **kwargs) -> SolutionArtifact: ...


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]

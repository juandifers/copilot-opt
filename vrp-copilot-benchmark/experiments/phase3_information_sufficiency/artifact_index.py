"""Index over existing SolutionArtifacts from Phase 1 / Phase 2 / Phase 2R.

Phase 3 reuses prior solves wherever the (instance, scenario, backend,
time_limit) tuple already exists — there is no scientific reason to re-run
Phase 2's NN/Savings/PyVRP-10s artifacts, and Phase 1's nominal PyVRP 60s
solutions are exactly the baseline S that ``reuse_direct`` consumes.

Conventions (read from solutions.jsonl headers):
  Phase 1 metadata.scenario uses the literal string ``"unknown"`` for the
  nominal baseline (the runner did not tag nominal explicitly). We
  normalize this to ``"nominal"`` here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from vrpbench.artifacts.solution import SolutionArtifact


# Canonical scenario keys used inside Phase 3.
NOMINAL = "nominal"


def _normalize_scenario(s: str | None) -> str:
    if s is None:
        return NOMINAL
    if s == "unknown":
        return NOMINAL
    return s


@dataclass(frozen=True)
class ArtifactKey:
    instance_id: str
    scenario: str          # e.g. "nominal", "capacity_reduction@0.9"
    backend_name: str      # "pyvrp" | "nearest_neighbor" | "savings" | ...
    time_limit_sec: float | None  # None for cheap backends, float for pyvrp


def _key(art: SolutionArtifact, scenario: str) -> ArtifactKey:
    return ArtifactKey(
        instance_id=art.instance_id,
        scenario=scenario,
        backend_name=art.backend_name,
        time_limit_sec=art.time_limit_sec,
    )


def load_jsonl(path: Path) -> list[tuple[ArtifactKey, SolutionArtifact]]:
    """Yield (key, artifact) for every line of a solutions.jsonl file."""
    out: list[tuple[ArtifactKey, SolutionArtifact]] = []
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            scenario = _normalize_scenario(d.get("metadata", {}).get("scenario"))
            art = SolutionArtifact.model_validate(d)
            out.append((_key(art, scenario), art))
    return out


def load_budget_check(dirpath: Path) -> list[tuple[ArtifactKey, SolutionArtifact]]:
    """Phase 2R budget_check JSONs — single-artifact files at PyVRP 60s.

    File naming: ``<instance_id>__<family>__mag<tag>__pyvrp60s.json``.
    The artifact body lives under the ``"artifact"`` key.
    """
    out: list[tuple[ArtifactKey, SolutionArtifact]] = []
    if not dirpath.exists():
        return out
    for jp in sorted(dirpath.glob("*__pyvrp60s.json")):
        try:
            blob = json.loads(jp.read_text())
        except json.JSONDecodeError:
            continue
        if "instance_id" in blob:
            art_dict = blob
        else:
            art_dict = blob.get("artifact") or blob.get("solution") or {}
        if "instance_id" not in art_dict:
            continue
        # Recover scenario from filename.
        # X-n200-k36__regional_distance_inflation__mag1p25__pyvrp60s.json
        stem = jp.stem.replace("__pyvrp60s", "")
        parts = stem.split("__")
        if len(parts) < 3:
            continue
        family = parts[1]
        mag_part = parts[2]  # "mag1p25"
        if not mag_part.startswith("mag"):
            continue
        mag_str = mag_part[3:].replace("p", ".")
        try:
            mag = float(mag_str)
        except ValueError:
            continue
        scenario = f"{family}@{mag}"
        art = SolutionArtifact.model_validate(art_dict)
        out.append((_key(art, scenario), art))
    return out


class ArtifactIndex:
    """In-memory index over many solutions sources, keyed by ArtifactKey."""

    def __init__(self) -> None:
        self._by_key: dict[ArtifactKey, SolutionArtifact] = {}

    def ingest(self, items: Iterable[tuple[ArtifactKey, SolutionArtifact]]) -> int:
        n = 0
        for k, art in items:
            # First-write-wins: prior phases are authoritative; new runs
            # are added only when missing.
            if k not in self._by_key:
                self._by_key[k] = art
                n += 1
        return n

    def get(self, key: ArtifactKey) -> SolutionArtifact | None:
        return self._by_key.get(key)

    def has(self, key: ArtifactKey) -> bool:
        return key in self._by_key

    def get_pyvrp_at(
        self, instance_id: str, scenario: str, time_limit_sec: float
    ) -> SolutionArtifact | None:
        return self._by_key.get(
            ArtifactKey(instance_id, scenario, "pyvrp", time_limit_sec)
        )

    def get_cheap(
        self, instance_id: str, scenario: str, backend_name: str
    ) -> SolutionArtifact | None:
        return self._by_key.get(
            ArtifactKey(instance_id, scenario, backend_name, None)
        )

    def __len__(self) -> int:
        return len(self._by_key)

    def keys(self) -> list[ArtifactKey]:
        return list(self._by_key.keys())

    def add(self, key: ArtifactKey, art: SolutionArtifact) -> None:
        self._by_key[key] = art


def build_default_index(repo_root: Path) -> ArtifactIndex:
    """Load all known prior artifacts: Phase 1 + Phase 2 + Phase 2R budget_check."""
    idx = ArtifactIndex()
    # Phase 1 has the canonical nominal PyVRP 60s baselines + a partial set
    # of perturbed PyVRP 60s artifacts (capacity@0.9, 0.8).
    n1 = idx.ingest(load_jsonl(repo_root / "reports" / "phase1" / "solutions.jsonl"))
    # Phase 2 has the full grid at NN, Savings, PyVRP 10s.
    n2 = idx.ingest(load_jsonl(repo_root / "reports" / "phase2" / "solutions.jsonl"))
    # Phase 2R budget_check has 5 mixed perturbed PyVRP 60s scenarios.
    n3 = idx.ingest(load_budget_check(
        repo_root / "data" / "processed" / "phase2r" / "budget_check"
    ))
    return idx

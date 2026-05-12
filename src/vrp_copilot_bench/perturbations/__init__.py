"""Perturbation enumeration stub.

The 16 perturbation specs per instance follow prereg §6:

- CAPACITY (4): CAP_1..4 with ρ ∈ {0.02, 0.05, 0.10, 0.20}
- DISTANCE (4): DIST_1..4, distance-multiplier 2.0 over different regions
- DEMAND (4): DEM_1..4, multiplier δ ∈ {0.10, 0.50, 0.50, 1.00}
- INSERTION (4): INS_1..4, γ ∈ {0.30, 0.70, 1.20, 2.00}

For Phase 2 (work-plan enumeration) only the *ids* matter; the full spec
content is filled in by the real perturbation module later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PERTURBATION_FAMILIES: tuple[str, ...] = ("CAP", "DIST", "DEM", "INS")
PERTURBATION_FAMILY_LABELS: dict[str, str] = {
    "CAP": "CAPACITY",
    "DIST": "DISTANCE",
    "DEM": "DEMAND",
    "INS": "INSERTION",
}
PERTURBATIONS_PER_FAMILY: int = 4


def _all_perturbation_ids() -> tuple[str, ...]:
    return tuple(
        f"{family}_{idx}"
        for family in PERTURBATION_FAMILIES
        for idx in range(1, PERTURBATIONS_PER_FAMILY + 1)
    )


PERTURBATION_IDS: tuple[str, ...] = _all_perturbation_ids()
assert len(PERTURBATION_IDS) == 16

#: Family-specific magnitude per prereg §6. Units differ by family — see
#: §6.{1..4}: CAP is fractional capacity reduction ρ, DIST is the distance
#: multiplier, DEM is fractional demand inflation δ, INS is total-inserted-
#: demand fraction γ. Stored verbatim; the parquet column
#: ``perturbation_magnitude`` (§4.1) carries this number raw.
PERTURBATION_MAGNITUDES: dict[str, float] = {
    "CAP_1": 0.02, "CAP_2": 0.05, "CAP_3": 0.10, "CAP_4": 0.20,
    "DIST_1": 2.0, "DIST_2": 2.0, "DIST_3": 2.0, "DIST_4": 2.0,
    "DEM_1": 0.10, "DEM_2": 0.50, "DEM_3": 0.50, "DEM_4": 1.00,
    "INS_1": 0.30, "INS_2": 0.70, "INS_3": 1.20, "INS_4": 2.00,
}
assert set(PERTURBATION_MAGNITUDES) == set(PERTURBATION_IDS)


@dataclass(frozen=True)
class PerturbationSpec:
    """Stub. Real region/customer-selector fields added later."""

    perturbation_id: str
    family: str  # one of PERTURBATION_FAMILY_LABELS values
    magnitude: float

    @property
    def short_family(self) -> str:
        """``CAP``/``DIST``/``DEM``/``INS`` (the id prefix)."""
        return self.perturbation_id.split("_", 1)[0]


def enumerate_perturbations(instance_id: str) -> list[PerturbationSpec]:
    """Return the 16 perturbation specs for an instance.

    Per prereg §6 the perturbation *grid* (which ids exist) is identical
    across instances; only the realised payload (which customers, what
    capacity) varies. The runner only needs the ids, so the stub returns
    fixed PerturbationSpecs without reference to the instance.
    """
    out: list[PerturbationSpec] = []
    for pid in PERTURBATION_IDS:
        family_short = pid.split("_", 1)[0]
        out.append(
            PerturbationSpec(
                perturbation_id=pid,
                family=PERTURBATION_FAMILY_LABELS[family_short],
                magnitude=PERTURBATION_MAGNITUDES[pid],
            )
        )
    return out


# Built once at module load: the 16 perturbation specs are the same across
# instances under the current grid (prereg §6). Real instance-dependent
# payload (which customers, etc.) is realised by ``apply_perturbation``,
# not by the spec object.
_PERTURBATION_INDEX: dict[str, PerturbationSpec] = {
    spec.perturbation_id: spec for spec in enumerate_perturbations("")
}


def lookup_perturbation(instance_id: str, perturbation_id: str) -> PerturbationSpec:
    """Find a perturbation spec by id.

    The ``instance_id`` argument is currently unused (the grid is identical
    across instances) but accepted for API stability — when the perturbation
    payload becomes instance-aware, this signature does not need to change.
    """
    try:
        return _PERTURBATION_INDEX[perturbation_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown perturbation_id {perturbation_id!r}; expected one of "
            f"{sorted(_PERTURBATION_INDEX)}"
        ) from exc


def apply_perturbation(
    instance: Any,
    spec: PerturbationSpec,
    baseline: Any | None = None,
) -> Any:
    """Realize a perturbation as a :class:`PerturbedInstance`.

    Dispatches to the family-specific implementation in
    :mod:`vrp_copilot_bench.perturbations.families`. CAPACITY and DISTANCE
    accept ``baseline=None`` (CAPACITY's diagnostic ``affected_route_share``
    is 0.0 without a baseline; DIST_4 requires one); DEMAND and INSERTION
    raise ``ValueError`` if ``baseline`` is missing.

    Family routing is by ``spec.family`` (the long-form label such as
    ``"CAPACITY"``), not by the id prefix.
    """
    # Imported here to avoid a circular import at module load time:
    # families.* imports PerturbationSpec from this module.
    from .families.capacity import apply_capacity
    from .families.demand import apply_demand
    from .families.distance import apply_distance
    from .families.insertion import apply_insertion

    if spec.family == "CAPACITY":
        return apply_capacity(instance, spec, baseline)
    if spec.family == "DEMAND":
        return apply_demand(instance, spec, baseline)
    if spec.family == "DISTANCE":
        return apply_distance(instance, spec, baseline)
    if spec.family == "INSERTION":
        return apply_insertion(instance, spec, baseline)
    raise ValueError(f"unknown perturbation family {spec.family!r}")


# Re-export the output type so callers can write:
#     from vrp_copilot_bench.perturbations import PerturbedInstance
from .types import PerturbedInstance  # noqa: E402  (intentional late import)


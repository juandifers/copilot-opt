"""Human-readable perturbation summaries for the visual grounding layer.

Pulls perturbation metadata from the locked spec registry
(``vrp_copilot_bench.vrptw_perturbations.lookup_vrptw_perturbation``)
and combines it with whatever Run-1 prompt-row metadata is available.

Per Stage 4 scope, magnitudes and affected customers are summarised at
the family level. Detailed before/after diff payloads (which would
populate ``magnitude`` and ``affected_customer_ids`` per prompt) are a
Stage 5 concern; this module surfaces them as ``missing_fields`` rather
than blocking.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Same lazy ``src/`` injection used by instance_geom — keep this module
# importable from a backend launched without a fully-set PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


_FAMILY_SUMMARY: dict[str, str] = {
    "TIME_WINDOW": "Delivery time windows were tightened.",
    "TRAVEL_TIME": "Travel times were increased for part of the instance.",
    "SERVICE_TIME": "Service times at customers were increased.",
    "ORDER_CHANGE": "New customer orders were inserted into the instance.",
    "CAPACITY": "Vehicle capacity was reduced.",
    "DEMAND": "Customer demand was increased.",
}


def _magnitude_phrase(family: str, magnitude: Optional[float]) -> Optional[str]:
    """Format magnitude differently per family so the phrase reads naturally."""
    if magnitude is None:
        return None
    try:
        m = float(magnitude)
    except (TypeError, ValueError):
        return None

    if family == "TIME_WINDOW":
        # Smaller fraction = tighter window. Stored as width fraction
        # (e.g. 0.1 = 10% of original width).
        return f"new window width ≈ {m * 100:.0f}% of original"
    if family in ("TRAVEL_TIME", "SERVICE_TIME"):
        # Stored as multiplier (e.g. 1.5 = +50%).
        pct = (m - 1.0) * 100
        if pct > 0:
            return f"+{pct:.0f}% multiplier"
        if pct < 0:
            return f"{pct:.0f}% multiplier"
        return "no-op multiplier (=1.0)"
    if family == "ORDER_CHANGE":
        # Stored as fraction of customers added.
        return f"~{m * 100:.0f}% of customers inserted"
    return f"magnitude={m:g}"


def build_perturbation_context(bundle: dict) -> dict:
    """Produce a short human-readable perturbation context dict.

    Inputs come from ``loaders.load_prompt_bundle(prompt_id)``; the
    relevant fields are ``perturbation_id`` and ``perturbation_family``
    on ``joined_row`` / ``prompt_row``.
    """
    joined = bundle.get("joined_row") or {}
    prompt = bundle.get("prompt_row") or {}

    def pick(key: str):
        v = prompt.get(key)
        if v is None or v == "":
            v = joined.get(key)
        return v

    pid = pick("perturbation_id")
    family = pick("perturbation_family")
    instance_id = pick("instance_id")
    dataset = pick("dataset")
    instance_class = pick("instance_class")

    # Look up the canonical spec for magnitude. Tolerate any lookup
    # error so a missing/renamed perturbation_id never crashes the UI.
    magnitude: Optional[float] = None
    lookup_error: Optional[str] = None
    if pid:
        try:
            from vrp_copilot_bench.vrptw_perturbations import (
                lookup_vrptw_perturbation,
            )
            spec = lookup_vrptw_perturbation(str(pid))
            magnitude = getattr(spec, "magnitude", None)
            # Fall back to the spec's family if it disagreed with the row.
            family = family or getattr(spec, "family", None)
        except Exception as exc:  # noqa: BLE001
            lookup_error = f"perturbation lookup failed: {exc!r}"

    summary = _FAMILY_SUMMARY.get(str(family), "Perturbation family not recognised.")
    mag_phrase = _magnitude_phrase(str(family), magnitude)
    if mag_phrase:
        summary = f"{summary} ({mag_phrase})"

    known_fields: dict = {}
    if pid:
        known_fields["perturbation_id"] = str(pid)
    if family:
        known_fields["perturbation_family"] = str(family)
    if magnitude is not None:
        known_fields["magnitude"] = float(magnitude)
    if instance_id:
        known_fields["instance_id"] = str(instance_id)
    if dataset:
        known_fields["dataset"] = str(dataset)
    if instance_class:
        known_fields["instance_class"] = str(instance_class)

    missing_fields: list[str] = []
    # Run-1 prompt rows don't record which specific customers/windows
    # were touched; surface that gap rather than fabricate.
    missing_fields.append("affected_customer_ids (not recorded in Run 1 prompt row)")
    if family == "ORDER_CHANGE":
        missing_fields.append(
            "inserted customer ids (would need diff payload from a Stage 5 builder)"
        )
    if family == "TIME_WINDOW":
        missing_fields.append(
            "per-customer original/new time-window pairs (would need diff payload)"
        )
    if lookup_error:
        missing_fields.append(lookup_error)

    return {
        "perturbation_id": str(pid) if pid else None,
        "perturbation_family": str(family) if family else None,
        "summary": summary,
        "known_fields": known_fields,
        "missing_fields": missing_fields,
    }


__all__ = ["build_perturbation_context"]

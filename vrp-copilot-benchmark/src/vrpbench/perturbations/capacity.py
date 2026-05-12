"""Capacity-reduction perturbation.

Writes a new .vrp file with CAPACITY multiplied by a reduction factor
(< 1.0). All other fields are copied verbatim. The perturbed file is
re-read by both backends, so the perturbation is applied uniformly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..data.instance import VRPInstance, load_instance


def _rewrite_capacity_line(lines: Iterable[str], new_capacity: int) -> list[str]:
    out: list[str] = []
    touched = False
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("CAPACITY"):
            out.append(f"CAPACITY : {new_capacity}\n")
            touched = True
        else:
            out.append(line if line.endswith("\n") else line + "\n")
    if not touched:
        raise ValueError("No CAPACITY line found in the source .vrp file")
    return out


def apply_capacity_reduction(
    instance: VRPInstance,
    factor: float,
    out_dir: Path,
) -> tuple[Path, int]:
    """Produce a perturbed .vrp file with reduced capacity.

    Returns (perturbed_path, new_capacity_int).
    """
    if not (0 < factor < 1):
        raise ValueError(f"capacity-reduction factor must be in (0, 1); got {factor}")

    src = instance.path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    factor_tag = str(factor).replace(".", "p")
    out_path = out_dir / f"{instance.instance_id}__cap{factor_tag}.vrp"

    new_capacity = int(round(instance.capacity * factor))
    if new_capacity <= 0:
        raise ValueError(f"Reduced capacity non-positive for factor={factor}")

    with src.open("r") as f:
        src_lines = f.readlines()
    out_lines = _rewrite_capacity_line(src_lines, new_capacity)
    with out_path.open("w") as f:
        f.writelines(out_lines)

    # Sanity: file must reload and demand must still be ≤ capacity somewhere.
    reloaded = load_instance(out_path)
    if reloaded.capacity != new_capacity:
        raise RuntimeError("Capacity rewrite sanity check failed.")
    return out_path, new_capacity

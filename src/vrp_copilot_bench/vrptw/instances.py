"""Shim re-exporting :mod:`vrp_copilot_bench.vrptw_instances`.

New code should import :class:`VRPTWInstance` and
:func:`load_vrptw_instance` from :mod:`vrp_copilot_bench.vrptw` (or this
module) rather than the legacy top-level path. The underlying file is
left where it is so the v1/v2 pilot scripts keep working unchanged.
"""
from __future__ import annotations

from ..vrptw_instances import (
    DEFAULT_VRPTW_INSTANCE_DIR,
    VRPTWInstance,
    load_vrptw_instance,
)

__all__ = [
    "DEFAULT_VRPTW_INSTANCE_DIR",
    "VRPTWInstance",
    "load_vrptw_instance",
]

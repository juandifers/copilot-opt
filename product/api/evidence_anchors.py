"""Map contract evidence field paths to frontend display anchors.

The contract layer returns evidence as field paths (e.g.
``route_end_times[route_idx=2].end_time``). The dashboard cannot
parse these — it needs concrete render targets such as "highlight
route 3" or "highlight customer 142". This module exists only to
translate one to the other.

Anchor shapes mirror what the dashboard renderer expects:

    {"type": "customer", "customer_id": 142}
    {"type": "route", "route_idx": 2, "route_label": "Route 3"}
    {"type": "route_end", "route_idx": 2, "route_label": "Route 3"}
    {"type": "customer_arrival", "customer_id": 142,
                                 "route_idx": 2, "route_label": "Route 3"}
    {"type": "solution_summary"}
    {"type": "none"}

Routing is best-effort: if the field path is unrecognised we return
``{"type": "none"}`` instead of guessing.
"""
from __future__ import annotations

import re
from typing import Any, Optional


_ROUTE_IDX_RE = re.compile(r"route_idx\s*=\s*(-?\d+)")
_CUSTOMER_ID_RE = re.compile(r"customer_id\s*=\s*(-?\d+)")


def _route_label_for_idx(
    route_idx: int, scenario_payload: Optional[dict]
) -> str:
    """Return ``Route N`` for a given internal zero-based ``route_idx``.

    If the (augmented) payload already carries a ``route_label`` for
    that index, prefer it; otherwise compute ``Route {route_idx + 1}``.
    """
    if scenario_payload:
        for key in ("routes", "route_end_times", "customer_schedule"):
            items = scenario_payload.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    if int(item.get("route_idx")) == route_idx:
                        label = item.get("route_label")
                        if isinstance(label, str) and label:
                            return label
                except (TypeError, ValueError):
                    continue
    return f"Route {route_idx + 1}"


def _route_idx_for_customer(
    customer_id: int, scenario_payload: Optional[dict]
) -> Optional[int]:
    if not scenario_payload:
        return None
    schedule = scenario_payload.get("customer_schedule")
    if isinstance(schedule, list):
        for row in schedule:
            if not isinstance(row, dict):
                continue
            try:
                if int(row.get("customer_id")) == customer_id:
                    return int(row.get("route_idx"))
            except (TypeError, ValueError):
                continue
    routes = scenario_payload.get("routes")
    if isinstance(routes, list):
        for r in routes:
            if not isinstance(r, dict):
                continue
            try:
                ids = [int(c) for c in (r.get("customer_ids") or [])]
            except (TypeError, ValueError):
                continue
            if customer_id in ids:
                try:
                    return int(r.get("route_idx"))
                except (TypeError, ValueError):
                    return None
    return None


def _parse_route_idx(path: str) -> Optional[int]:
    m = _ROUTE_IDX_RE.search(path or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _parse_customer_id(path: str) -> Optional[int]:
    m = _CUSTOMER_ID_RE.search(path or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


_SOLUTION_SUMMARY_PATHS: set[str] = {
    "action_objective",
    "baseline_objective",
    "objective_delta_absolute",
    "objective_delta_percent",
    "n_routes",
    "feasible",
    "feasibility_breakdown",
    "infeasibility_kind",
    "n_unserved_customers",
    "unserved_customer_ids",
    "n_late_customers",
    "late_customer_ids",
    "units.objective",
}


def field_path_to_display_anchor(
    field_path: str, scenario_payload: Optional[dict] = None
) -> dict:
    """Translate one contract evidence ``field_path`` into a display anchor.

    Returns ``{"type": "none"}`` when no confident anchor is available.
    """
    if not field_path:
        return {"type": "none"}

    path = field_path.strip()

    if path in _SOLUTION_SUMMARY_PATHS:
        return {"type": "solution_summary"}

    if path.startswith("route_end_times"):
        ridx = _parse_route_idx(path)
        if ridx is None:
            return {"type": "solution_summary"}
        return {
            "type": "route_end",
            "route_idx": ridx,
            "route_label": _route_label_for_idx(ridx, scenario_payload),
        }

    if path.startswith("routes"):
        ridx = _parse_route_idx(path)
        if ridx is None:
            return {"type": "solution_summary"}
        return {
            "type": "route",
            "route_idx": ridx,
            "route_label": _route_label_for_idx(ridx, scenario_payload),
        }

    if path.startswith("customer_schedule"):
        cid = _parse_customer_id(path)
        if cid is None:
            return {"type": "solution_summary"}
        ridx = _route_idx_for_customer(cid, scenario_payload)
        anchor: dict[str, Any] = {"type": "customer_arrival", "customer_id": cid}
        if ridx is not None:
            anchor["route_idx"] = ridx
            anchor["route_label"] = _route_label_for_idx(ridx, scenario_payload)
        return anchor

    return {"type": "none"}


__all__ = ["field_path_to_display_anchor"]

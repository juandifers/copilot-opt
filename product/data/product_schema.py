"""Product-side payload augmentation.

Adds user-facing route labels and display numbers on top of the locked
experiment payload schema, without removing the internal `route_idx`
the experiment relies on. The original payload is never mutated; all
augmentation runs on a deep copy.
"""
from __future__ import annotations

import copy
from typing import Optional


def _add_display_to_route_dict(d: dict) -> dict:
    if "route_idx" in d and "display_route_number" not in d:
        try:
            rid = int(d["route_idx"])
        except (TypeError, ValueError):
            return d
        d["display_route_number"] = rid + 1
        d["route_label"] = f"Route {rid + 1}"
    return d


def add_display_route_numbers(payload: dict) -> dict:
    """Mutate the given payload dict to add display_route_number and route_label
    to each route-like nested object. Callers that need to preserve the
    original should use `augment_payload_for_product` instead."""
    routes = payload.get("routes")
    if isinstance(routes, list):
        for r in routes:
            if isinstance(r, dict):
                _add_display_to_route_dict(r)

    route_end_times = payload.get("route_end_times")
    if isinstance(route_end_times, list):
        for r in route_end_times:
            if isinstance(r, dict):
                _add_display_to_route_dict(r)

    customer_schedule = payload.get("customer_schedule")
    if isinstance(customer_schedule, list):
        for c in customer_schedule:
            if isinstance(c, dict):
                _add_display_to_route_dict(c)

    return payload


def build_route_lookup(payload: dict) -> dict:
    """Return cross-reference maps over an augmented payload.

    Keys:
      - route_idx_to_label
      - route_label_to_route_idx
      - customer_id_to_route_idx
      - customer_id_to_route_label
    """
    route_idx_to_label: dict[int, str] = {}
    route_label_to_route_idx: dict[str, int] = {}
    customer_id_to_route_idx: dict[int, int] = {}
    customer_id_to_route_label: dict[int, str] = {}

    def _register_route(rid: int, label: Optional[str]) -> str:
        resolved = label or f"Route {rid + 1}"
        route_idx_to_label.setdefault(rid, resolved)
        route_label_to_route_idx.setdefault(resolved, rid)
        return resolved

    routes = payload.get("routes")
    if isinstance(routes, list):
        for r in routes:
            if not isinstance(r, dict) or "route_idx" not in r:
                continue
            rid = int(r["route_idx"])
            label = _register_route(rid, r.get("route_label"))
            for cid in r.get("customer_ids") or []:
                cid_int = int(cid)
                customer_id_to_route_idx.setdefault(cid_int, rid)
                customer_id_to_route_label.setdefault(cid_int, label)

    customer_schedule = payload.get("customer_schedule")
    if isinstance(customer_schedule, list):
        for c in customer_schedule:
            if not isinstance(c, dict):
                continue
            if "route_idx" not in c or "customer_id" not in c:
                continue
            rid = int(c["route_idx"])
            cid_int = int(c["customer_id"])
            label = _register_route(rid, c.get("route_label"))
            customer_id_to_route_idx.setdefault(cid_int, rid)
            customer_id_to_route_label.setdefault(cid_int, label)

    route_end_times = payload.get("route_end_times")
    if isinstance(route_end_times, list):
        for r in route_end_times:
            if not isinstance(r, dict) or "route_idx" not in r:
                continue
            rid = int(r["route_idx"])
            _register_route(rid, r.get("route_label"))

    return {
        "route_idx_to_label": route_idx_to_label,
        "route_label_to_route_idx": route_label_to_route_idx,
        "customer_id_to_route_idx": customer_id_to_route_idx,
        "customer_id_to_route_label": customer_id_to_route_label,
    }


def explain_route_indexing() -> str:
    return (
        "Internal route_idx is zero-indexed. The dashboard displays "
        "user-facing route_label values starting at Route 1."
    )


def augment_payload_for_product(payload: Optional[dict]) -> Optional[dict]:
    """Return a deep-copy of the payload with display labels added."""
    if payload is None:
        return None
    augmented = copy.deepcopy(payload)
    add_display_route_numbers(augmented)
    return augmented

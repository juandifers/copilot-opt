"""Visual context builder.

Combines the Stage 2 ``ProductCopilotResponse`` with Stage 4 instance
geometry, route polylines, and perturbation context to produce a single
JSON object the frontend can render directly.

The visual layer follows the product principle: the backend is the
source of truth for what is highlighted, what is missing, and what is
unsupported. The frontend simply draws what this builder returns.
"""
from __future__ import annotations

from typing import Optional

from product.copilot.response_builder import build_replay_response
from product.data import loaders
from product.data.instance_geom import build_route_polylines, load_instance_geometry
from product.data.perturbation_context import build_perturbation_context


_LIMIT_MISSING_DIFF = (
    "Baseline/diff payload unavailable: this prompt's payload does not "
    "carry baseline_solution or diff fields, so a faithful before/after "
    "route comparison cannot be rendered."
)
_LIMIT_MISSING_NEW_CUSTOMER = (
    "Inserted-customer attribution unavailable: the payload does not "
    "expose new_customer_ids, so we cannot point at which customer the "
    "perturbation added."
)
_LIMIT_NO_GEOMETRY = (
    "Instance geometry could not be loaded; the spatial map is not "
    "available for this prompt."
)
_LIMIT_NO_ROUTES = (
    "Payload carries no route structure: spatial route polylines are "
    "not rendered, only the customer scatter."
)


def _highlights_from_visual_actions(
    visual_actions: list,
) -> tuple[list[int], list[dict]]:
    """Pull highlighted customer ids and route descriptors out of the
    Stage 2 ``visual_actions`` list. The list is small (≤ a handful per
    prompt), so a single pass is enough."""
    customers: list[int] = []
    routes: list[dict] = []
    seen_customers: set[int] = set()
    seen_routes: set[int] = set()
    for action in visual_actions or []:
        kind = getattr(action, "kind", None)
        target = getattr(action, "target", {}) or {}
        if kind == "highlight_customer":
            cid = target.get("customer_id")
            if cid is not None and int(cid) not in seen_customers:
                customers.append(int(cid))
                seen_customers.add(int(cid))
            for cid in target.get("customer_ids", []) or []:
                if int(cid) not in seen_customers:
                    customers.append(int(cid))
                    seen_customers.add(int(cid))
        elif kind == "highlight_route":
            idx = target.get("route_idx")
            if idx is None:
                continue
            try:
                idx_i = int(idx)
            except (TypeError, ValueError):
                continue
            if idx_i in seen_routes:
                continue
            seen_routes.add(idx_i)
            routes.append(
                {
                    "route_idx": idx_i,
                    "route_label": target.get("route_label"),
                    "display_route_number": target.get("display_route_number"),
                }
            )
    return customers, routes


def _enrich_highlighted_routes_with_labels(
    highlights: list[dict], polylines: list[dict]
) -> list[dict]:
    by_idx = {p["route_idx"]: p for p in polylines}
    enriched: list[dict] = []
    for h in highlights:
        poly = by_idx.get(h["route_idx"])
        if poly:
            enriched.append(
                {
                    "route_idx": h["route_idx"],
                    "route_label": h.get("route_label") or poly.get("route_label"),
                    "display_route_number": (
                        h.get("display_route_number") or poly.get("display_route_number")
                    ),
                }
            )
        else:
            enriched.append(h)
    return enriched


def _routes_for_highlighted_customers(
    customers: list[int], polylines: list[dict]
) -> list[dict]:
    """For each highlighted customer not already on a highlighted route,
    return the polyline route they belong to. Lets the frontend draw a
    route-containing-highlighted-customer even when ``highlight_route``
    wasn't emitted (some SCHEDULE intents only highlight the customer).
    """
    if not customers:
        return []
    out: list[dict] = []
    seen: set[int] = set()
    for poly in polylines:
        for cid in poly.get("customer_ids", []) or []:
            if int(cid) in customers and poly["route_idx"] not in seen:
                seen.add(poly["route_idx"])
                out.append(
                    {
                        "route_idx": poly["route_idx"],
                        "route_label": poly.get("route_label"),
                        "display_route_number": poly.get("display_route_number"),
                    }
                )
                break
    return out


def build_visual_context(
    prompt_id: str, run_id: str = "full-run-v1"
) -> dict:
    """Assemble the visual-context payload for a single prompt.

    Never raises for missing instance / missing routes / missing diff —
    callers receive a structured ``limitations`` list instead.
    """
    response = build_replay_response(prompt_id, run_id=run_id)
    bundle = loaders.load_prompt_bundle(prompt_id, run_id=run_id)
    joined = bundle.get("joined_row") or {}
    payload = response.payload_augmented or {}

    instance_id = joined.get("instance_id") or bundle.get("prompt_row", {}).get(
        "instance_id"
    )

    # -- instance geometry (best effort) --
    geometry: Optional[dict] = None
    geom_error: Optional[str] = None
    if instance_id:
        try:
            geometry = load_instance_geometry(str(instance_id))
        except Exception as exc:  # noqa: BLE001
            geom_error = (
                f"failed to load geometry for instance {instance_id!r}: {exc!r}"
            )

    # -- route polylines --
    polylines: list[dict] = []
    poly_warnings: list[str] = []
    if geometry:
        polylines, poly_warnings = build_route_polylines(payload, geometry)

    # -- highlights --
    visual_actions_json = [
        {"kind": a.kind, "target": dict(a.target)} for a in response.visual_actions
    ]
    highlighted_customers, highlighted_routes = _highlights_from_visual_actions(
        response.visual_actions
    )
    highlighted_routes = _enrich_highlighted_routes_with_labels(
        highlighted_routes, polylines
    )
    # Also pick up the route(s) that contain a highlighted customer so the
    # frontend can render a route polyline even when the Stage-2 visual
    # actions only said "highlight_customer".
    derived = _routes_for_highlighted_customers(highlighted_customers, polylines)
    seen_idx = {r["route_idx"] for r in highlighted_routes}
    for r in derived:
        if r["route_idx"] not in seen_idx:
            highlighted_routes.append(r)
            seen_idx.add(r["route_idx"])

    # -- limitations --
    limitations: list[str] = []
    if response.intent == "before_after_comparison":
        limitations.append(_LIMIT_MISSING_DIFF)
    if (
        response.intent == "new_customer_assignment"
        and "new_customer_ids" in response.answerability.missing_fields
    ):
        limitations.append(_LIMIT_MISSING_NEW_CUSTOMER)
    if geom_error:
        limitations.append(_LIMIT_NO_GEOMETRY)
    if geometry and not polylines:
        limitations.append(_LIMIT_NO_ROUTES)

    schedule = payload.get("customer_schedule") if isinstance(payload, dict) else None
    route_end_times = (
        payload.get("route_end_times") if isinstance(payload, dict) else None
    )

    perturbation_context = build_perturbation_context(bundle)

    warnings = list(response.warnings or [])
    for w in poly_warnings:
        warnings.append(w)

    return {
        "prompt_id": response.prompt_id,
        "run_id": response.run_id,
        "instance_id": str(instance_id) if instance_id else None,
        "perturbation_id": perturbation_context.get("perturbation_id"),
        "perturbation_family": perturbation_context.get("perturbation_family"),
        "intent": response.intent,
        "answerability_status": response.answerability.status,
        "coordinate_system": (
            geometry["coordinate_system"] if geometry else "euclidean_synthetic"
        ),
        "coordinate_note": (geometry or {}).get("notes"),
        "depot": geometry["depot"] if geometry else None,
        "customers": geometry["customers"] if geometry else [],
        "n_customers": geometry["n_customers"] if geometry else 0,
        "routes": polylines,
        "highlighted_customers": highlighted_customers,
        "highlighted_routes": highlighted_routes,
        "schedule": schedule if isinstance(schedule, list) else [],
        "route_end_times": route_end_times if isinstance(route_end_times, list) else [],
        "visual_actions": visual_actions_json,
        "perturbation_context": perturbation_context,
        "warnings": warnings,
        "limitations": limitations,
        "geometry_error": geom_error,
    }


__all__ = ["build_visual_context"]

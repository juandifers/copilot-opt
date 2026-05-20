"""Evidence extraction from augmented payloads.

For each intent, surface the payload field(s) that ground the answer
(or absence thereof). Also provides `field_path_exists` and
`get_nested_field` helpers used by the answerability layer.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from product.copilot.contracts import EvidenceItem, VisualAction
from product.data import entity_resolution


_CUSTOMER_BOUND_INTENTS = frozenset({
    "customer_arrival",
    "single_customer_route_membership",
    "same_route_boolean",
})
_ROUTE_BOUND_INTENTS = frozenset({"route_end_time"})


# ---------------------------------------------------------------------------
# Field path utilities
# ---------------------------------------------------------------------------


def field_path_exists(payload: Optional[dict], path: str) -> bool:
    """Check whether the given path exists in the payload.

    Supports:
      - top-level: ``key``
      - dotted nested: ``key.subkey``
      - list-of-dicts: ``key[].subkey`` (returns True if the list is
        non-empty and its first dict contains ``subkey``)
    """
    if not payload:
        return False
    if "." not in path and "[]" not in path:
        return path in payload
    if "[]." in path:
        head, rest = path.split("[].", 1)
        if head not in payload:
            return False
        lst = payload[head]
        if not isinstance(lst, list) or not lst:
            return False
        first = lst[0]
        if not isinstance(first, dict):
            return False
        return field_path_exists(first, rest)
    if "." in path:
        head, rest = path.split(".", 1)
        if head not in payload:
            return False
        nested = payload[head]
        if not isinstance(nested, dict):
            return False
        return field_path_exists(nested, rest)
    return False


def get_nested_field(payload: Optional[dict], path: str) -> Any:
    """Best-effort accessor for the same path grammar as `field_path_exists`."""
    if not payload:
        return None
    if "." not in path and "[]" not in path:
        return payload.get(path)
    if "[]." in path:
        head, rest = path.split("[].", 1)
        lst = payload.get(head)
        if not isinstance(lst, list) or not lst:
            return None
        first = lst[0]
        if not isinstance(first, dict):
            return None
        return get_nested_field(first, rest)
    if "." in path:
        head, rest = path.split(".", 1)
        nested = payload.get(head)
        if not isinstance(nested, dict):
            return None
        return get_nested_field(nested, rest)
    return None


# ---------------------------------------------------------------------------
# Prompt-text helpers (small deterministic regexes)
# ---------------------------------------------------------------------------


def _parse_customer_in_prompt(prompt_text: str) -> Optional[int]:
    m = re.search(r"customer\s+(\d+)", (prompt_text or "").lower())
    return int(m.group(1)) if m else None


def _parse_route_number_in_prompt(prompt_text: str) -> Optional[int]:
    m = re.search(r"route\s+(\d+)", (prompt_text or "").lower())
    return int(m.group(1)) if m else None


def _route_label(r: dict) -> str:
    if r.get("route_label"):
        return str(r["route_label"])
    return f"Route {int(r['route_idx']) + 1}"


# ---------------------------------------------------------------------------
# Per-intent builders
# ---------------------------------------------------------------------------


def _evidence_objective(payload: dict, want_delta: bool) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    if want_delta:
        for field, label in (
            ("baseline_objective", "Baseline objective"),
            ("action_objective", "Action objective"),
            ("objective_delta_absolute", "Absolute delta"),
            ("objective_delta_percent", "Percent delta"),
        ):
            if field in payload:
                items.append(
                    EvidenceItem(
                        field_path=field,
                        value=payload[field],
                        supports=label,
                        display_label=label,
                    )
                )
    else:
        if "action_objective" in payload:
            items.append(
                EvidenceItem(
                    field_path="action_objective",
                    value=payload["action_objective"],
                    supports="total cost on this plan",
                    display_label="Action objective",
                )
            )
    units = (payload.get("units") or {}).get("objective")
    if units:
        items.append(
            EvidenceItem(
                field_path="units.objective",
                value=units,
                supports="unit of the objective value",
                display_label="Objective units",
            )
        )
    return items


def _evidence_feasibility(payload: dict) -> list[EvidenceItem]:
    # The feasibility answer is grounded in `feasible` and
    # `feasibility_breakdown`. When neither primary field is present,
    # the question cannot be grounded — supplementary diagnostics
    # (infeasibility_kind, unserved_customer_ids) are interpretable
    # only relative to a known feasibility verdict, so we do not cite
    # them as standalone evidence.
    has_primary = "feasible" in payload or isinstance(
        payload.get("feasibility_breakdown"), dict
    )
    if not has_primary:
        return []

    items: list[EvidenceItem] = []
    if "feasible" in payload:
        items.append(
            EvidenceItem(
                field_path="feasible",
                value=payload["feasible"],
                supports="overall feasibility flag",
                display_label="feasible",
            )
        )
    breakdown = payload.get("feasibility_breakdown")
    if isinstance(breakdown, dict):
        for k, v in breakdown.items():
            items.append(
                EvidenceItem(
                    field_path=f"feasibility_breakdown.{k}",
                    value=v,
                    supports=f"feasibility check: {k}",
                    display_label=k,
                )
            )
    if payload.get("infeasibility_kind"):
        items.append(
            EvidenceItem(
                field_path="infeasibility_kind",
                value=payload["infeasibility_kind"],
                supports="kind of infeasibility detected",
            )
        )
    unserved = payload.get("unserved_customer_ids")
    if isinstance(unserved, list) and unserved:
        items.append(
            EvidenceItem(
                field_path="unserved_customer_ids",
                value=unserved,
                supports="customers that could not be served",
            )
        )
    return items


def _evidence_route_count(payload: dict) -> list[EvidenceItem]:
    if "n_routes" not in payload:
        return []
    return [
        EvidenceItem(
            field_path="n_routes",
            value=payload["n_routes"],
            supports="number of routes in the solution",
            display_label="Route count",
        )
    ]


def _evidence_route_membership(
    payload: dict, structured_output: dict, prompt_text: str
) -> list[EvidenceItem]:
    target_cids: set[int] = set()
    for crm in structured_output.get("claimed_route_membership") or []:
        for cid in crm.get("customer_ids") or []:
            target_cids.add(int(cid))
    if not target_cids:
        parsed = _parse_customer_in_prompt(prompt_text)
        if parsed is not None:
            target_cids.add(parsed)

    items: list[EvidenceItem] = []
    routes = payload.get("routes") or []
    for r in routes:
        if not isinstance(r, dict):
            continue
        r_cids = set(int(c) for c in (r.get("customer_ids") or []))
        hit = r_cids & target_cids if target_cids else set()
        if hit or not target_cids:
            label = _route_label(r)
            items.append(
                EvidenceItem(
                    field_path=f"routes[route_idx={r.get('route_idx')}].customer_ids",
                    value=r.get("customer_ids"),
                    supports=(
                        f"customer {sorted(hit)} on this route"
                        if hit
                        else "members of this route"
                    ),
                    display_label=f"{label} customers",
                )
            )
            if target_cids and hit:
                # We have enough; stop iterating to avoid noise.
                break
    return items


def _evidence_full_route_listing(payload: dict) -> list[EvidenceItem]:
    """Emit one customer_ids row per route in the plan.

    The full_route_listing intent answers a roster-per-route question, so
    every route in `routes` contributes evidence. Field paths carry the
    route_idx predicate; the Run 2 scorer normalises away the predicate
    and matches against the schema-level `routes[].customer_ids` family."""
    items: list[EvidenceItem] = []
    for r in payload.get("routes") or []:
        if not isinstance(r, dict):
            continue
        label = _route_label(r)
        items.append(
            EvidenceItem(
                field_path=f"routes[route_idx={r.get('route_idx')}].customer_ids",
                value=r.get("customer_ids"),
                supports=f"customers on {label}",
                display_label=f"{label} customers",
            )
        )
    return items


def _evidence_route_end_time(payload: dict, prompt_text: str) -> list[EvidenceItem]:
    display = _parse_route_number_in_prompt(prompt_text)
    target_idx = display - 1 if display is not None else None
    items: list[EvidenceItem] = []
    for r in payload.get("route_end_times") or []:
        if not isinstance(r, dict):
            continue
        if target_idx is not None and r.get("route_idx") != target_idx:
            continue
        label = _route_label(r)
        items.append(
            EvidenceItem(
                field_path=f"route_end_times[route_idx={r.get('route_idx')}].end_time",
                value=r.get("end_time"),
                supports=f"end time of {label}",
                display_label=label,
            )
        )
        if r.get("has_time_warp"):
            items.append(
                EvidenceItem(
                    field_path=f"route_end_times[route_idx={r.get('route_idx')}].has_time_warp",
                    value=True,
                    supports="route end time reflects time-warp (route exceeded a window)",
                )
            )
        if target_idx is not None:
            break
    return items


def _evidence_customer_arrival(
    payload: dict, structured_output: dict, prompt_text: str
) -> list[EvidenceItem]:
    target_cids: set[int] = set()
    for ct in structured_output.get("claimed_customer_timings") or []:
        target_cids.add(int(ct["customer_id"]))
    if not target_cids:
        parsed = _parse_customer_in_prompt(prompt_text)
        if parsed is not None:
            target_cids.add(parsed)

    items: list[EvidenceItem] = []
    for c in payload.get("customer_schedule") or []:
        if not isinstance(c, dict):
            continue
        if target_cids and int(c.get("customer_id", -1)) not in target_cids:
            continue
        label = _route_label(c)
        cid = c.get("customer_id")
        items.append(
            EvidenceItem(
                field_path=f"customer_schedule[customer_id={cid}].arrival",
                value=c.get("arrival"),
                supports=f"arrival time for customer {cid}",
                display_label=f"Customer {cid} on {label}",
            )
        )
        if c.get("is_late"):
            items.append(
                EvidenceItem(
                    field_path=f"customer_schedule[customer_id={cid}].is_late",
                    value=True,
                    supports=f"customer {cid} arrived after its window",
                )
            )
        if target_cids:
            break
    return items


def _evidence_lateness_summary(payload: dict) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    if "n_late_customers" in payload:
        items.append(
            EvidenceItem(
                field_path="n_late_customers",
                value=payload["n_late_customers"],
                supports="total late customers",
                display_label="Late count",
            )
        )
    late = payload.get("late_customer_ids")
    if isinstance(late, list):
        items.append(
            EvidenceItem(
                field_path="late_customer_ids",
                value=late,
                supports="customer IDs that arrived after their window",
                display_label="Late customer IDs",
            )
        )
    return items


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_evidence_items(
    intent: str,
    payload: Optional[dict],
    generator_record: Optional[dict],
    row: Optional[dict] = None,
) -> list[EvidenceItem]:
    if payload is None:
        return []
    structured_output = (generator_record or {}).get("structured_output") or {}
    prompt_text = (row or {}).get("prompt_text") or ""

    # False-premise short-circuit: when the prompt names an entity that
    # is not in the payload, cite nothing rather than stale evidence
    # against an unrelated entity (the seed prompt's
    # structured_output may still pin a customer/route from the
    # original Run 1 question).
    if intent in _CUSTOMER_BOUND_INTENTS and entity_resolution.prompt_references_unknown_customer(
        payload, prompt_text
    ):
        return []
    if intent in _ROUTE_BOUND_INTENTS and entity_resolution.prompt_references_unknown_route(
        payload, prompt_text
    ):
        return []

    if intent == "objective_value":
        return _evidence_objective(payload, want_delta=False)
    if intent == "objective_delta":
        return _evidence_objective(payload, want_delta=True)
    if intent == "feasibility_status":
        return _evidence_feasibility(payload)
    if intent == "route_count":
        return _evidence_route_count(payload)
    if intent in ("single_customer_route_membership", "same_route_boolean"):
        return _evidence_route_membership(payload, structured_output, prompt_text)
    if intent == "full_route_listing":
        return _evidence_full_route_listing(payload)
    if intent == "route_end_time":
        return _evidence_route_end_time(payload, prompt_text)
    if intent == "customer_arrival":
        return _evidence_customer_arrival(payload, structured_output, prompt_text)
    if intent == "lateness_summary":
        return _evidence_lateness_summary(payload)
    # before_after_comparison, new_customer_assignment, refusal_or_insufficient_payload:
    # absence-of-evidence is the answer; missing_fields carries the story.
    return []


def infer_visual_actions(
    intent: str, evidence_items: list[EvidenceItem]
) -> list[VisualAction]:
    actions: list[VisualAction] = []

    def _route_idx_from_path(path: str) -> Optional[int]:
        m = re.search(r"route_idx=(\d+)", path)
        return int(m.group(1)) if m else None

    def _customer_id_from_path(path: str) -> Optional[int]:
        m = re.search(r"customer_id=(\d+)", path)
        return int(m.group(1)) if m else None

    if intent in ("single_customer_route_membership", "same_route_boolean"):
        for it in evidence_items:
            ridx = _route_idx_from_path(it.field_path)
            if ridx is not None:
                actions.append(VisualAction(kind="highlight_route", target={"route_idx": ridx}))
        # Highlight only the queried customer(s), not the entire route roster.
        # The `supports` line carries the queried-customer set in the form
        # "customer [42] on this route".
        for it in evidence_items:
            m = re.search(r"customer \[([^\]]+)\] on this route", it.supports)
            if m:
                for raw in m.group(1).split(","):
                    raw = raw.strip()
                    if raw.isdigit():
                        actions.append(
                            VisualAction(kind="highlight_customer", target={"customer_id": int(raw)})
                        )
                break
    elif intent == "customer_arrival":
        for it in evidence_items:
            cid = _customer_id_from_path(it.field_path)
            if cid is not None:
                actions.append(VisualAction(kind="highlight_customer", target={"customer_id": cid}))
        actions.append(VisualAction(kind="show_schedule_row"))
    elif intent == "route_end_time":
        for it in evidence_items:
            ridx = _route_idx_from_path(it.field_path)
            if ridx is not None:
                actions.append(VisualAction(kind="highlight_route", target={"route_idx": ridx}))
        actions.append(VisualAction(kind="show_route_end_time"))
    elif intent == "feasibility_status":
        actions.append(VisualAction(kind="show_feasibility_card"))
    elif intent in ("objective_value", "objective_delta"):
        actions.append(VisualAction(kind="show_objective_card"))
    elif intent == "lateness_summary":
        actions.append(VisualAction(kind="show_lateness_summary"))
    elif intent == "route_count":
        actions.append(VisualAction(kind="show_route_count"))
    return actions

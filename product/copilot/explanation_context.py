"""Deterministic explanation-context card builder.

Given an augmented scenario payload (and optional perturbation metadata),
produce a compact, payload-derived context card that the verbalization
renderer can use to answer high-level operator questions
("What is this perturbation doing?", "How does the plan look?",
"What should I pay attention to?").

The card is the only thing the verbalizer reads when rendering
overview-class intents. It deliberately does NOT include full route
tables or per-customer schedules — those are too large and would
encourage the renderer to claim more than the payload supports.

Architectural role:

    payload
      │
      ▼
    build_explanation_context()  ← pure, deterministic, no LLM
      │
      ▼
    explanation_context (dict)   ← compact, safe, allowed/forbidden claims
      │
      ▼
    verbalization renderer       ← template-driven, reads context only

Hard rules:

* The card cannot make claims the payload does not support.
* Route changes, objective deltas, and causal mechanisms are only
  surfaced when the corresponding payload field is present.
* The card carries ``allowed_claims`` and ``forbidden_claims`` so the
  downstream renderer (or any future grounded LLM explainer) has
  explicit fences.
"""
from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Per-family perturbation explanations
#
# Keyed by the canonical Run-1 perturbation_family strings used by
# ``product.data.perturbation_context``:
#
#   TIME_WINDOW   — tightened customer service windows
#   TRAVEL_TIME   — increased travel times
#   SERVICE_TIME  — increased per-customer service times
#   ORDER_CHANGE  — newly inserted customer orders
#
# CAPACITY/DEMAND families are present in the family-summary registry
# but never fire in Run-1 prompts; we omit them here rather than write
# explanation text the operator will never see in this thesis.
# ---------------------------------------------------------------------------

_PERTURBATION_EXPLANATIONS: dict[str, dict[str, Any]] = {
    "TIME_WINDOW": {
        "label": "Time-window perturbation",
        "operator_explanation": (
            "This stresses whether customers can still be served within "
            "their allowed service windows. Tightened windows make on-time "
            "delivery harder."
        ),
        "primary_metrics_to_watch": [
            "arrival_times",
            "lateness",
            "route_end_times",
        ],
    },
    "TRAVEL_TIME": {
        "label": "Travel-time perturbation",
        "operator_explanation": (
            "This stresses whether routes remain feasible and timely when "
            "travel times between customers change. Longer travel times push "
            "out arrivals and may break time-window or end-of-day constraints."
        ),
        "primary_metrics_to_watch": [
            "objective",
            "arrival_times",
            "lateness",
            "route_end_times",
        ],
    },
    "SERVICE_TIME": {
        "label": "Service-time perturbation",
        "operator_explanation": (
            "This stresses whether routes remain feasible when each customer "
            "takes longer to service. Increased service times accumulate "
            "across a route and can push later customers past their windows."
        ),
        "primary_metrics_to_watch": [
            "arrival_times",
            "lateness",
            "route_end_times",
        ],
    },
    "ORDER_CHANGE": {
        "label": "Customer-insertion perturbation",
        "operator_explanation": (
            "This stresses whether the plan can absorb additional customer "
            "orders. New customers must be assigned to a route while "
            "preserving feasibility and reasonable cost."
        ),
        "primary_metrics_to_watch": [
            "feasibility",
            "n_routes",
            "lateness",
            "objective",
        ],
    },
}


# Fallback when the family is unknown / unrecognised. We still produce
# something useful: a generic description that names the operational
# dimensions the operator may want to inspect, without claiming what the
# perturbation specifically does.
_UNKNOWN_FAMILY_EXPLANATION: dict[str, Any] = {
    "label": "Perturbation (family not recognised)",
    "operator_explanation": (
        "The perturbation family is not in the registry. Inspect "
        "feasibility, route count, and lateness signals as a general "
        "starting point."
    ),
    "primary_metrics_to_watch": [
        "feasibility",
        "n_routes",
        "lateness",
    ],
}


# ---------------------------------------------------------------------------
# Allowed / forbidden claim catalogues
# ---------------------------------------------------------------------------

# Claim labels carry no semantic logic on their own — the verbalizer
# decides which to invoke based on which fields are present. The labels
# exist so a future grounded LLM explainer (or a reviewer) can see at a
# glance what the card permits.

_ALL_FORBIDDEN_CLAIMS: tuple[str, ...] = (
    "claim_routes_changed_without_diff",
    "claim_objective_increased_or_decreased_without_diff",
    "claim_perturbation_caused_lateness_without_causal_diagnostics",
    "claim_which_routes_were_most_affected_without_route_level_diff",
    "claim_recompute_result_without_executed_recompute",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _count_late_customers(payload: dict) -> Optional[int]:
    """Count late customers from whichever signal the payload exposes."""
    if not isinstance(payload, dict):
        return None
    n = payload.get("n_late_customers")
    if isinstance(n, int):
        return n
    ids = payload.get("late_customer_ids")
    if isinstance(ids, list):
        return len(ids)
    sched = payload.get("customer_schedule")
    if isinstance(sched, list):
        return sum(1 for r in sched if isinstance(r, dict) and r.get("is_late"))
    return None


def _count_capacity_violations(payload: dict) -> Optional[int]:
    """Capacity violations: count from feasibility_breakdown if present."""
    if not isinstance(payload, dict):
        return None
    fb = payload.get("feasibility_breakdown")
    if isinstance(fb, dict):
        cap = fb.get("capacity_ok")
        if cap is False:
            n = fb.get("n_capacity_violations")
            return _safe_int(n) if n is not None else 1
        if cap is True:
            return 0
    return None


def _count_unserved(payload: dict) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    n = payload.get("n_unserved_customers")
    if isinstance(n, int):
        return n
    ids = payload.get("unserved_customer_ids")
    if isinstance(ids, list):
        return len(ids)
    return None


def _current_solution_card(payload: dict) -> dict[str, Any]:
    """Extract a compact current-solution status card.

    Keys that the verbalizer can read:

        available              — at least one solution-shape field is present
        feasible               — bool / None
        objective              — float / None  (action_objective)
        n_routes               — int / None
        n_late_customers       — int / None
        n_capacity_violations  — int / None
        n_unserved_customers   — int / None
    """
    if not isinstance(payload, dict):
        return {
            "available": False,
            "feasible": None,
            "objective": None,
            "n_routes": None,
            "n_late_customers": None,
            "n_capacity_violations": None,
            "n_unserved_customers": None,
        }

    has_solution_signal = any(
        k in payload
        for k in (
            "feasible",
            "action_objective",
            "routes",
            "customer_schedule",
            "route_end_times",
            "n_routes",
        )
    )

    return {
        "available": bool(has_solution_signal),
        "feasible": payload.get("feasible"),
        "objective": _safe_float(payload.get("action_objective")),
        "n_routes": _safe_int(
            payload.get("n_routes")
            or (len(payload["routes"]) if isinstance(payload.get("routes"), list) else None)
        ),
        "n_late_customers": _count_late_customers(payload),
        "n_capacity_violations": _count_capacity_violations(payload),
        "n_unserved_customers": _count_unserved(payload),
    }


def _comparison_card(payload: dict) -> dict[str, Any]:
    """Extract a compact comparison-availability card.

    Reports which baseline/diff fields exist, plus pre-computed deltas
    when present. Never invents values.
    """
    if not isinstance(payload, dict):
        return {
            "available": False,
            "baseline_available": False,
            "diff_available": False,
            "route_level_diff_available": False,
            "objective_delta_absolute": None,
            "objective_delta_percent": None,
            "route_count_delta": None,
            "moved_customers_count": None,
            "late_customers_delta": None,
            "baseline_objective": None,
        }

    baseline_available = (
        "baseline_solution" in payload and payload["baseline_solution"] is not None
    )
    diff = payload.get("diff")
    diff_available = isinstance(diff, dict) and bool(diff)
    route_changes = (diff or {}).get("route_changes") if isinstance(diff, dict) else None
    route_level_diff_available = isinstance(route_changes, list)

    obj_delta_abs = _safe_float(payload.get("objective_delta_absolute"))
    obj_delta_pct = _safe_float(payload.get("objective_delta_percent"))
    baseline_obj = _safe_float(payload.get("baseline_objective"))

    route_count_delta: Optional[int] = None
    moved_customers_count: Optional[int] = None
    late_customers_delta: Optional[int] = None

    if isinstance(diff, dict):
        rc = diff.get("route_count_delta")
        if rc is not None:
            route_count_delta = _safe_int(rc)
        cc = diff.get("customer_changes")
        if isinstance(cc, list):
            moved_customers_count = len(cc)
        lcd = diff.get("late_customers_delta")
        if lcd is not None:
            late_customers_delta = _safe_int(lcd)

    # The card is "available for impact questions" only when there is
    # actually impact data — baseline-objective inline doesn't tell us
    # route impact, but it does enable an objective-delta impact answer.
    impact_signal_present = (
        baseline_available
        or diff_available
        or obj_delta_abs is not None
        or baseline_obj is not None
    )

    return {
        "available": impact_signal_present,
        "baseline_available": baseline_available,
        "diff_available": diff_available,
        "route_level_diff_available": route_level_diff_available,
        "objective_delta_absolute": obj_delta_abs,
        "objective_delta_percent": obj_delta_pct,
        "route_count_delta": route_count_delta,
        "moved_customers_count": moved_customers_count,
        "late_customers_delta": late_customers_delta,
        "baseline_objective": baseline_obj,
    }


def _available_fields_card(payload: dict) -> dict[str, bool]:
    """Boolean flags for fields the renderer / validator may check."""
    if not isinstance(payload, dict):
        return {
            "perturbation_metadata": False,
            "solution_summary": False,
            "baseline_solution": False,
            "diff": False,
            "route_level_diff": False,
            "causal_diagnostics": False,
        }
    diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else None
    route_changes = diff.get("route_changes") if diff else None
    return {
        "perturbation_metadata": True,  # always derivable from perturbation_id
        "solution_summary": any(
            k in payload
            for k in (
                "feasible",
                "action_objective",
                "routes",
                "customer_schedule",
                "n_routes",
            )
        ),
        "baseline_solution": payload.get("baseline_solution") is not None,
        "diff": bool(diff),
        "route_level_diff": isinstance(route_changes, list),
        "causal_diagnostics": payload.get("causal_diagnostics") is not None,
    }


def _limitations(
    available: dict[str, bool],
    comparison: dict[str, Any],
) -> list[dict[str, str]]:
    """List of human-readable limitations the renderer should surface."""
    lims: list[dict[str, str]] = []
    if not (available["baseline_solution"] or available["diff"] or comparison["available"]):
        lims.append({
            "code": "baseline_diff_missing",
            "message": (
                "Route changes and before/after impact cannot be measured "
                "without a baseline or diff payload."
            ),
        })
    if not available["route_level_diff"]:
        lims.append({
            "code": "route_level_diff_missing",
            "message": (
                "Per-route change details (which routes moved, which "
                "customers were reassigned) are not in this payload."
            ),
        })
    if not available["causal_diagnostics"]:
        lims.append({
            "code": "causal_diagnostics_missing",
            "message": (
                "This payload supports observed facts, not causal "
                "attribution — the perturbation may correlate with "
                "observed changes but a mechanism cannot be proven."
            ),
        })
    return lims


def _allowed_claims_for_intent(
    intent: str,
    current_solution: dict[str, Any],
    comparison: dict[str, Any],
    available: dict[str, bool],
) -> list[str]:
    """Per-intent catalogue of safe claim labels.

    The labels are tags only — the verbalizer reads them when deciding
    whether a particular sentence template is permitted.
    """
    claims: list[str] = []

    if intent in ("perturbation_summary", "scenario_summary"):
        claims.extend([
            "describe_perturbation_definition",
            "describe_perturbation_metrics_to_watch",
        ])
        if current_solution["available"]:
            claims.append("describe_current_solution_status")

    if intent == "scenario_summary":
        claims.append("describe_instance_metadata")

    if intent == "solution_summary":
        if current_solution["available"]:
            claims.append("describe_current_solution_status")
            if current_solution["feasible"] is not None:
                claims.append("state_feasibility")
            if current_solution["n_routes"] is not None:
                claims.append("state_route_count")
            if current_solution["n_late_customers"] is not None:
                claims.append("state_lateness_count")
            if current_solution["objective"] is not None:
                claims.append("state_objective_value")

    if intent in ("perturbation_impact_summary", "route_impact_summary"):
        if current_solution["available"]:
            claims.append("describe_current_solution_status")
        if comparison["available"]:
            if comparison["objective_delta_absolute"] is not None:
                claims.append("state_objective_delta")
            if available["diff"]:
                claims.append("state_diff_summary")
            if intent == "route_impact_summary" and available["route_level_diff"]:
                claims.append("state_route_level_diff")
        else:
            claims.extend([
                "state_missing_baseline_diff",
                "suggest_build_comparison_payload",
            ])

    if intent == "what_to_watch":
        if current_solution["available"]:
            claims.append("describe_current_solution_status")
            if current_solution["feasible"] is not None:
                claims.append("name_feasibility_signal")
            if current_solution["n_late_customers"] is not None:
                claims.append("name_lateness_signal")
        if not comparison["available"]:
            claims.append("state_missing_baseline_diff")
        claims.append("describe_perturbation_metrics_to_watch")

    return claims


def _forbidden_claims_for_intent(
    intent: str,
    comparison: dict[str, Any],
    available: dict[str, bool],
) -> list[str]:
    """Per-intent catalogue of claims that must NOT be made."""
    forbidden: list[str] = []
    if not available["diff"]:
        forbidden.append("claim_routes_changed_without_diff")
    if comparison["objective_delta_absolute"] is None:
        forbidden.append("claim_objective_increased_or_decreased_without_diff")
    if not available["causal_diagnostics"]:
        forbidden.append("claim_perturbation_caused_lateness_without_causal_diagnostics")
    if not available["route_level_diff"]:
        forbidden.append("claim_which_routes_were_most_affected_without_route_level_diff")
    # Recompute-result claims are never permitted from the context card —
    # /copilot/ask never executes a solver.
    forbidden.append("claim_recompute_result_without_executed_recompute")
    return forbidden


def _recommended_next_actions(
    intent: str,
    comparison: dict[str, Any],
    available: dict[str, bool],
) -> list[dict[str, str]]:
    """Soft action hints. These are display-only — D4/D5 still own
    operational ``ui_actions`` (recompute affordance, etc.)."""
    if intent not in ("perturbation_impact_summary", "route_impact_summary"):
        return []
    if comparison["available"]:
        return []
    return [
        {
            "type": "build_comparison_payload",
            "label": "Build comparison payload to measure impact",
        }
    ]


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_explanation_context(
    *,
    scenario_payload: Optional[dict],
    intent: str,
    scenario_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    perturbation_id: Optional[str] = None,
    perturbation_family: Optional[str] = None,
    prompt: Optional[str] = None,
    contract_response: Optional[dict] = None,
) -> dict[str, Any]:
    """Produce the compact context card for an overview intent.

    The function is pure and deterministic. It reads only the augmented
    payload plus the surrounding scenario metadata (instance/perturbation
    ids and family). No raw routes or customer schedules are placed in
    the output; only summary counts and availability flags.
    """
    payload = scenario_payload if isinstance(scenario_payload, dict) else {}

    fam = (perturbation_family or "").strip().upper() or None
    explanation = (
        _PERTURBATION_EXPLANATIONS.get(fam, _UNKNOWN_FAMILY_EXPLANATION)
        if fam
        else _UNKNOWN_FAMILY_EXPLANATION
    )

    current_solution = _current_solution_card(payload)
    comparison = _comparison_card(payload)
    available = _available_fields_card(payload)
    limitations = _limitations(available, comparison)

    n_customers: Optional[int] = None
    vehicle_capacity: Optional[float] = None
    instance_block = payload.get("instance") if isinstance(payload, dict) else None
    if isinstance(instance_block, dict):
        customers = instance_block.get("customers")
        if isinstance(customers, list):
            n_customers = len(customers)
        vehicle_capacity = _safe_float(instance_block.get("vehicle_capacity"))

    card: dict[str, Any] = {
        "scenario_id": scenario_id,
        "instance": {
            "instance_id": instance_id,
            "n_customers": n_customers,
            "vehicle_capacity": vehicle_capacity,
        },
        "perturbation": {
            "id": perturbation_id,
            "family": fam,
            "label": explanation["label"],
            "operator_explanation": explanation["operator_explanation"],
            "primary_metrics_to_watch": list(explanation["primary_metrics_to_watch"]),
        },
        "current_solution": current_solution,
        "comparison": comparison,
        "available_fields": available,
        "limitations": limitations,
        "allowed_claims": _allowed_claims_for_intent(
            intent, current_solution, comparison, available
        ),
        "forbidden_claims": _forbidden_claims_for_intent(
            intent, comparison, available
        ),
        "recommended_next_actions": _recommended_next_actions(
            intent, comparison, available
        ),
    }
    return card


# ---------------------------------------------------------------------------
# Evidence-item adapter
# ---------------------------------------------------------------------------


def context_card_to_evidence_items(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the context card into evidence items the renderer consumes.

    Each item has the same shape the rest of the API uses:

        {
          "field_path": "<dotted path into the card>",
          "value":      <leaf value>,
          "display_anchor": {"type": "none"},
        }

    The renderer reads from these via ``_ev_value`` / ``_ev_all``. The
    display anchors are intentionally ``{"type": "none"}`` — the
    frontend should not try to highlight a payload region for an
    overview answer.
    """
    items: list[dict[str, Any]] = []

    def add(path: str, value: Any) -> None:
        items.append({
            "field_path": f"explanation_context.{path}",
            "value": value,
            "display_anchor": {"type": "none"},
        })

    add("scenario_id", card.get("scenario_id"))
    add("instance.instance_id", card["instance"].get("instance_id"))
    add("instance.n_customers", card["instance"].get("n_customers"))
    add("instance.vehicle_capacity", card["instance"].get("vehicle_capacity"))

    p = card.get("perturbation", {})
    add("perturbation.id", p.get("id"))
    add("perturbation.family", p.get("family"))
    add("perturbation.label", p.get("label"))
    add("perturbation.operator_explanation", p.get("operator_explanation"))
    add("perturbation.primary_metrics_to_watch", p.get("primary_metrics_to_watch"))

    cs = card.get("current_solution", {})
    add("current_solution.available", cs.get("available"))
    add("current_solution.feasible", cs.get("feasible"))
    add("current_solution.objective", cs.get("objective"))
    add("current_solution.n_routes", cs.get("n_routes"))
    add("current_solution.n_late_customers", cs.get("n_late_customers"))
    add("current_solution.n_capacity_violations", cs.get("n_capacity_violations"))
    add("current_solution.n_unserved_customers", cs.get("n_unserved_customers"))

    cmp_ = card.get("comparison", {})
    add("comparison.available", cmp_.get("available"))
    add("comparison.baseline_available", cmp_.get("baseline_available"))
    add("comparison.diff_available", cmp_.get("diff_available"))
    add("comparison.route_level_diff_available", cmp_.get("route_level_diff_available"))
    add("comparison.objective_delta_absolute", cmp_.get("objective_delta_absolute"))
    add("comparison.objective_delta_percent", cmp_.get("objective_delta_percent"))
    add("comparison.route_count_delta", cmp_.get("route_count_delta"))
    add("comparison.moved_customers_count", cmp_.get("moved_customers_count"))
    add("comparison.late_customers_delta", cmp_.get("late_customers_delta"))
    add("comparison.baseline_objective", cmp_.get("baseline_objective"))

    for lim in card.get("limitations") or []:
        add(f"limitations[{lim['code']}]", lim["message"])

    return items


__all__ = [
    "build_explanation_context",
    "context_card_to_evidence_items",
]

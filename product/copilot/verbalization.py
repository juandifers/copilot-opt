"""Template-based contract verbalization renderer.

Converts a structured ProductCopilotResponse / PredictedContract into
a natural-language answer_text string. This is the rendering layer
evaluated by the verbalization faithfulness check.

The renderer is template-driven and deterministic — no LLM calls.
It reads from the same evidence items and warnings the contract
already emitted; it does not access the raw payload directly.

Contract boundary: the renderer is permitted to read:
  intent, answerability, behavior_class, evidence_items, warnings,
  missing_fields, next_actions, compute_decision

It must NOT:
  - invent facts not in evidence_items
  - suppress warnings that are critical for interpretation
  - claim a comparison result when missing_fields includes a referent
  - claim a recomputed answer when compute_decision.mode is needs_recompute
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Warning → human note
# ---------------------------------------------------------------------------

_WARNING_NOTES: dict[str, str] = {
    "route_indexing_ambiguity": (
        "Route numbers in this response are sequential position indices "
        "(starting at 1), not necessarily the labels shown in the original plan."
    ),
    "struct_membership_ambiguity": (
        "Route membership reflects the perturbed plan; assignments may differ "
        "from what was expected before the change."
    ),
    "comparison_referent_ambiguity": (
        "A reference solution for comparison is not available in the current "
        "payload. The cost figures shown are for the current plan only."
    ),
    "evidence_units_missing": (
        "The units for this cost figure are not recorded in the current payload."
    ),
    "missing_new_customer_attribution": (
        "The payload does not identify which customer was newly added; "
        "the assignment shown is based on the closest match."
    ),
    "causal_mechanism_unsupported": (
        "This payload does not include causal diagnostic data. "
        "Observed facts are reported; the mechanism cannot be determined."
    ),
    "false_premise_detected": (
        "The entity referenced in this question does not exist in the current solution."
    ),
    "unsupported_comparison": (
        "A before/after comparison requires a baseline or diff payload that "
        "is not present in the current context."
    ),
}

_MISSING_FIELD_NOTES: dict[str, str] = {
    "baseline_solution": "the baseline solution",
    "diff": "the route diff",
    "reference_solution.objective": "the reference solution objective",
    "units.objective": "the cost units",
    "feasible": "feasibility data",
    "feasibility_breakdown": "detailed feasibility breakdown",
    "n_late_customers": "late customer count",
    "late_customer_ids": "late customer identifiers",
    "new_customer_ids": "new customer attribution",
    "action_objective": "the plan objective value",
}


def _warning_note(warning: str) -> str:
    return _WARNING_NOTES.get(warning, f"Warning: {warning}.")


def _missing_note(field: str) -> str:
    label = _MISSING_FIELD_NOTES.get(field, field)
    return label


# ---------------------------------------------------------------------------
# Evidence extraction helpers
# ---------------------------------------------------------------------------


def _ev_value(evidence_items: list[dict], field_prefix: str):
    """Return the first evidence value whose field_path starts with field_prefix."""
    for ev in evidence_items:
        if ev.get("field_path", "").startswith(field_prefix):
            return ev.get("value")
    return None


def _ev_all(evidence_items: list[dict], field_prefix: str) -> list[dict]:
    return [ev for ev in evidence_items if ev.get("field_path", "").startswith(field_prefix)]


def _route_label_from_idx(evidence_items: list[dict], route_idx: int) -> str:
    """Extract display_route_number from evidence if available, else Route {idx+1}."""
    for ev in evidence_items:
        fp = ev.get("field_path", "")
        if f"route_idx={route_idx}" in fp:
            val = ev.get("value")
            if isinstance(val, list):
                # It's a customer_ids list; label comes from context
                pass
    return f"Route {route_idx + 1}"


def _extract_customer_id_from_path(field_path: str) -> Optional[int]:
    import re
    m = re.search(r"customer_id=(\d+)", field_path)
    return int(m.group(1)) if m else None


def _extract_route_idx_from_path(field_path: str) -> Optional[int]:
    import re
    m = re.search(r"route_idx=(\d+)", field_path)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Per-intent renderers
# ---------------------------------------------------------------------------


def _render_objective_value(evidence_items: list[dict], warnings: list[str]) -> str:
    obj = _ev_value(evidence_items, "action_objective")
    units = _ev_value(evidence_items, "units.objective")
    if obj is None:
        return "The plan objective value is not available in the current payload."
    unit_str = f" ({units})" if units else ""
    text = f"The total cost of this plan is {obj}{unit_str}."
    if "evidence_units_missing" in warnings:
        text += f" {_warning_note('evidence_units_missing')}"
    return text


def _render_objective_delta(evidence_items: list[dict], warnings: list[str]) -> str:
    baseline = _ev_value(evidence_items, "baseline_objective")
    current = _ev_value(evidence_items, "action_objective")
    delta_abs = _ev_value(evidence_items, "objective_delta_absolute")
    delta_pct = _ev_value(evidence_items, "objective_delta_percent")
    units = _ev_value(evidence_items, "units.objective")

    if "comparison_referent_ambiguity" in warnings:
        text = f"The current plan cost is {current}"
        if units:
            text += f" ({units})"
        text += "."
        text += f" {_warning_note('comparison_referent_ambiguity')}"
        return text

    if baseline is None or current is None:
        return "Cost comparison is not available in the current payload."

    unit_str = f" ({units})" if units else ""
    if delta_abs == 0.0:
        text = f"The cost is unchanged: {current}{unit_str} (same as baseline {baseline}{unit_str})."
    else:
        sign = "+" if delta_abs > 0 else ""
        text = (
            f"The cost changed from {baseline} to {current}{unit_str} "
            f"({sign}{delta_abs:.2f} absolute, {sign}{delta_pct:.1f}%)."
        )
    return text


def _render_feasibility_status(evidence_items: list[dict], warnings: list[str]) -> str:
    feasible = _ev_value(evidence_items, "feasible")
    if feasible is True:
        return (
            "The plan is feasible — all time window and capacity constraints are satisfied."
        )
    elif feasible is False:
        return "The plan is infeasible — at least one constraint is violated."
    return "Feasibility status is not available in the current payload."


def _render_route_end_time(evidence_items: list[dict], warnings: list[str]) -> str:
    ret_evs = _ev_all(evidence_items, "route_end_times")
    if not ret_evs:
        return "Route end time is not available in the current payload."
    # Use first route_end_time item
    ev = ret_evs[0]
    fp = ev.get("field_path", "")
    route_idx = _extract_route_idx_from_path(fp)
    end_time = ev.get("value")
    route_label = f"Route {route_idx + 1}" if route_idx is not None else "the route"
    text = f"{route_label} finishes at {end_time} min."
    if "route_indexing_ambiguity" in warnings:
        text += f" {_warning_note('route_indexing_ambiguity')}"
    return text


def _render_customer_arrival(evidence_items: list[dict], warnings: list[str]) -> str:
    sched_evs = _ev_all(evidence_items, "customer_schedule")
    if not sched_evs:
        return "Customer arrival time is not available in the current payload."
    ev = sched_evs[0]
    fp = ev.get("field_path", "")
    cid = _extract_customer_id_from_path(fp)
    arrival = ev.get("value")
    customer_str = f"customer {cid}" if cid is not None else "the customer"
    return f"The driver arrives at {customer_str} at {arrival} min."


def _render_same_route_boolean(evidence_items: list[dict], prompt_text: str) -> str:
    import re
    # Match "customers X and Y", "customer X and Y", "customer X and customer Y"
    pair_m = re.search(r"\bcustomers?\s+(\d+)\s+and\s+(?:customer\s+)?(\d+)\b", prompt_text.lower())
    if pair_m:
        ids = [pair_m.group(1), pair_m.group(2)]
    else:
        ids = re.findall(r"\bcustomers?\s+(\d+)\b", prompt_text.lower())
    if len(ids) < 2:
        return "The same-route status cannot be determined from the current payload."
    cid_a, cid_b = ids[0], ids[1]
    a_int, b_int = int(cid_a), int(cid_b)

    for ev in evidence_items:
        val = ev.get("value")
        if isinstance(val, list):
            int_val = [int(x) for x in val if str(x).isdigit()]
            if a_int in int_val and b_int in int_val:
                route_idx = _extract_route_idx_from_path(ev.get("field_path", ""))
                label = f"Route {route_idx + 1}" if route_idx is not None else "the same route"
                return f"Yes — customers {cid_a} and {cid_b} are on {label}."

    return f"No — customers {cid_a} and {cid_b} are not on the same route."


def _render_single_customer_route_membership(
    evidence_items: list[dict], warnings: list[str], prompt_text: str
) -> str:
    import re
    ids = re.findall(r"\bcustomer\s+(\d+)\b", prompt_text.lower())
    cid = ids[0] if ids else "the customer"

    for ev in evidence_items:
        val = ev.get("value")
        if isinstance(val, list):
            route_idx = _extract_route_idx_from_path(ev.get("field_path", ""))
            label = f"Route {route_idx + 1}" if route_idx is not None else "an assigned route"
            text = f"Customer {cid} is on {label}."
            if "struct_membership_ambiguity" in warnings:
                text += f" {_warning_note('struct_membership_ambiguity')}"
            return text
    return f"Customer {cid} route membership is not available in the current payload."


def _render_full_route_listing(evidence_items: list[dict]) -> str:
    route_evs = _ev_all(evidence_items, "routes[route_idx=")
    # Group by route_idx
    by_route: dict[int, list] = {}
    for ev in route_evs:
        fp = ev.get("field_path", "")
        if "customer_ids" not in fp:
            continue
        idx = _extract_route_idx_from_path(fp)
        if idx is None:
            continue
        val = ev.get("value")
        if isinstance(val, list):
            by_route[idx] = val

    if not by_route:
        return "Route listing is not available in the current payload."

    parts = []
    for idx in sorted(by_route):
        customers = by_route[idx]
        parts.append(f"Route {idx + 1}: {customers}")
    return "Customers assigned per route — " + "; ".join(parts) + "."


def _render_lateness_summary(evidence_items: list[dict]) -> str:
    n_late = _ev_value(evidence_items, "n_late_customers")
    late_ids = _ev_value(evidence_items, "late_customer_ids")
    if n_late == 0:
        return "All customers are served on time — no late deliveries in this plan."
    if n_late is not None and late_ids is not None:
        return f"{n_late} customer(s) have late deliveries: {late_ids}."
    if n_late is not None:
        return f"{n_late} customer(s) have late deliveries."
    return "Late delivery summary is not available in the current payload."


def _render_new_customer_assignment(evidence_items: list[dict], warnings: list[str]) -> str:
    if "missing_new_customer_attribution" in warnings:
        return (
            "The new customer's route assignment cannot be confirmed. "
            + _warning_note("missing_new_customer_attribution")
        )
    route_evs = _ev_all(evidence_items, "routes")
    if route_evs:
        ev = route_evs[0]
        route_idx = _extract_route_idx_from_path(ev.get("field_path", ""))
        label = f"Route {route_idx + 1}" if route_idx is not None else "a route"
        return f"The new customer was assigned to {label}."
    return "New customer assignment is not available in the current payload."


# ---------------------------------------------------------------------------
# Overview / explanation renderers
#
# These read from ``explanation_context.*`` evidence items produced by
# ``product.copilot.explanation_context.context_card_to_evidence_items``.
# They must:
#   - describe payload-derived facts only;
#   - state when baseline/diff is missing rather than make impact claims;
#   - never invent route-change or causal claims.
# ---------------------------------------------------------------------------


def _format_current_solution_phrase(evidence_items: list[dict]) -> str:
    """Build a short status phrase about the current solution.

    Returns the empty string when no solution-shape signal is present.
    """
    available = _ev_value(evidence_items, "explanation_context.current_solution.available")
    if not available:
        return ""
    parts: list[str] = []
    feasible = _ev_value(evidence_items, "explanation_context.current_solution.feasible")
    n_routes = _ev_value(evidence_items, "explanation_context.current_solution.n_routes")
    n_late = _ev_value(evidence_items, "explanation_context.current_solution.n_late_customers")
    objective = _ev_value(evidence_items, "explanation_context.current_solution.objective")

    if feasible is True:
        parts.append("the current solution is feasible")
    elif feasible is False:
        parts.append("the current solution is infeasible")

    if n_routes is not None:
        parts.append(f"{n_routes} routes")
    if n_late is not None:
        if n_late == 0:
            parts.append("no late customers")
        else:
            parts.append(f"{n_late} late customer{'s' if n_late != 1 else ''}")
    if objective is not None and feasible is None:
        # Only show the objective in the status phrase when feasibility
        # was not stated (objective alone is rarely the headline).
        parts.append(f"objective {objective}")

    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0].capitalize() + "."
    head = parts[0].capitalize()
    tail = ", ".join(parts[1:])
    return f"{head} with {tail}."


def _render_perturbation_summary(evidence_items: list[dict]) -> str:
    label = _ev_value(evidence_items, "explanation_context.perturbation.label")
    operator_explanation = _ev_value(
        evidence_items, "explanation_context.perturbation.operator_explanation"
    )
    metrics = _ev_value(
        evidence_items, "explanation_context.perturbation.primary_metrics_to_watch"
    )
    if not label and not operator_explanation:
        return (
            "Perturbation metadata is not available in the current payload, "
            "so this perturbation cannot be described."
        )

    parts: list[str] = []
    if label:
        parts.append(f"This is a {label.lower()}.")
    if operator_explanation:
        parts.append(operator_explanation)
    if metrics and isinstance(metrics, list):
        parts.append(
            "Main fields to inspect: " + ", ".join(str(m) for m in metrics) + "."
        )
    status = _format_current_solution_phrase(evidence_items)
    if status:
        parts.append(status)
    return " ".join(parts)


def _render_scenario_summary(evidence_items: list[dict]) -> str:
    instance_id = _ev_value(evidence_items, "explanation_context.instance.instance_id")
    n_customers = _ev_value(evidence_items, "explanation_context.instance.n_customers")
    label = _ev_value(evidence_items, "explanation_context.perturbation.label")
    operator_explanation = _ev_value(
        evidence_items, "explanation_context.perturbation.operator_explanation"
    )

    parts: list[str] = []
    head_bits: list[str] = []
    if instance_id:
        head_bits.append(f"instance {instance_id}")
    if n_customers:
        head_bits.append(f"{n_customers} customers")
    if label:
        head_bits.append(f"under a {label.lower()}")
    if head_bits:
        parts.append("This scenario is " + ", ".join(head_bits) + ".")

    if operator_explanation:
        parts.append(operator_explanation)

    status = _format_current_solution_phrase(evidence_items)
    if status:
        parts.append(status)

    # Comparison availability — important to flag whether we can talk
    # about impact in this scenario at all.
    comparison_available = _ev_value(
        evidence_items, "explanation_context.comparison.available"
    )
    if comparison_available is False:
        parts.append(
            "Baseline/diff information is not in this payload, so changes "
            "relative to a previous plan cannot be quantified."
        )

    if not parts:
        return "Scenario metadata is not available in the current payload."
    return " ".join(parts)


def _render_solution_summary(evidence_items: list[dict]) -> str:
    available = _ev_value(
        evidence_items, "explanation_context.current_solution.available"
    )
    if not available:
        return "The current solution is not exposed in this payload."

    feasible = _ev_value(evidence_items, "explanation_context.current_solution.feasible")
    objective = _ev_value(evidence_items, "explanation_context.current_solution.objective")
    n_routes = _ev_value(evidence_items, "explanation_context.current_solution.n_routes")
    n_late = _ev_value(evidence_items, "explanation_context.current_solution.n_late_customers")
    n_cap = _ev_value(
        evidence_items, "explanation_context.current_solution.n_capacity_violations"
    )
    n_unserved = _ev_value(
        evidence_items, "explanation_context.current_solution.n_unserved_customers"
    )

    parts: list[str] = []
    if feasible is True:
        parts.append("The current plan is feasible.")
    elif feasible is False:
        parts.append("The current plan is infeasible.")

    if n_routes is not None:
        parts.append(f"It uses {n_routes} routes.")
    if objective is not None:
        parts.append(f"Objective value: {objective}.")
    if n_late is not None:
        if n_late == 0:
            parts.append("No customers are late.")
        else:
            parts.append(
                f"{n_late} customer{'s' if n_late != 1 else ''} are late."
            )
    if n_cap is not None and n_cap > 0:
        parts.append(f"{n_cap} capacity violation{'s' if n_cap != 1 else ''}.")
    if n_unserved is not None and n_unserved > 0:
        parts.append(f"{n_unserved} customer{'s' if n_unserved != 1 else ''} unserved.")

    if not parts:
        return "The current solution is exposed but contains no headline status fields."
    return " ".join(parts)


def _render_perturbation_impact_summary(evidence_items: list[dict]) -> str:
    comparison_available = _ev_value(
        evidence_items, "explanation_context.comparison.available"
    )
    delta_abs = _ev_value(
        evidence_items, "explanation_context.comparison.objective_delta_absolute"
    )
    delta_pct = _ev_value(
        evidence_items, "explanation_context.comparison.objective_delta_percent"
    )
    baseline_objective = _ev_value(
        evidence_items, "explanation_context.comparison.baseline_objective"
    )
    diff_available = _ev_value(
        evidence_items, "explanation_context.comparison.diff_available"
    )
    moved = _ev_value(
        evidence_items, "explanation_context.comparison.moved_customers_count"
    )

    if not comparison_available:
        status = _format_current_solution_phrase(evidence_items)
        head = (
            "I cannot quantify the perturbation's impact because this "
            "payload does not include a baseline or diff."
        )
        if status:
            head += " " + status
        head += (
            " To measure impact, build a comparison payload with the "
            "baseline solution and diff."
        )
        return head

    parts: list[str] = []
    if delta_abs is not None:
        sign = "+" if delta_abs > 0 else ""
        if delta_pct is not None:
            parts.append(
                f"The objective changed by {sign}{delta_abs:.2f} "
                f"({sign}{delta_pct:.1f}%)"
                + (f" relative to a baseline of {baseline_objective}." if baseline_objective is not None else ".")
            )
        else:
            parts.append(
                f"The objective changed by {sign}{delta_abs:.2f}"
                + (f" relative to a baseline of {baseline_objective}." if baseline_objective is not None else ".")
            )
    if diff_available and moved is not None:
        parts.append(
            f"{moved} customer{'s' if moved != 1 else ''} moved between routes "
            "in the diff."
        )
    if not parts:
        # Comparison present but no specific delta exposed — surface that
        # plainly rather than making something up.
        parts.append(
            "Comparison data is available but no specific impact metric is "
            "exposed in this payload."
        )
    status = _format_current_solution_phrase(evidence_items)
    if status:
        parts.append(status)
    return " ".join(parts)


def _render_route_impact_summary(evidence_items: list[dict]) -> str:
    route_diff_available = _ev_value(
        evidence_items, "explanation_context.comparison.route_level_diff_available"
    )
    comparison_available = _ev_value(
        evidence_items, "explanation_context.comparison.available"
    )
    route_count_delta = _ev_value(
        evidence_items, "explanation_context.comparison.route_count_delta"
    )
    moved = _ev_value(
        evidence_items, "explanation_context.comparison.moved_customers_count"
    )
    n_routes = _ev_value(evidence_items, "explanation_context.current_solution.n_routes")

    if not route_diff_available:
        head = (
            "Route-level impact cannot be measured: this payload does not "
            "include a route-level diff."
        )
        if n_routes is not None:
            head += f" The current plan has {n_routes} routes."
        if not comparison_available:
            head += (
                " To measure route impact, build a comparison payload "
                "with the baseline solution and route diff."
            )
        return head

    parts: list[str] = []
    if route_count_delta is not None:
        if route_count_delta == 0:
            parts.append("The route count is unchanged.")
        else:
            sign = "+" if route_count_delta > 0 else ""
            parts.append(f"The route count changed by {sign}{route_count_delta}.")
    if moved is not None:
        parts.append(
            f"{moved} customer{'s' if moved != 1 else ''} moved between routes."
        )
    if not parts:
        parts.append("Route-level diff is available but no specific change is exposed.")
    return " ".join(parts)


def _render_what_to_watch(evidence_items: list[dict]) -> str:
    available = _ev_value(
        evidence_items, "explanation_context.current_solution.available"
    )
    feasible = _ev_value(evidence_items, "explanation_context.current_solution.feasible")
    n_late = _ev_value(evidence_items, "explanation_context.current_solution.n_late_customers")
    n_cap = _ev_value(
        evidence_items, "explanation_context.current_solution.n_capacity_violations"
    )
    n_unserved = _ev_value(
        evidence_items, "explanation_context.current_solution.n_unserved_customers"
    )
    metrics = _ev_value(
        evidence_items, "explanation_context.perturbation.primary_metrics_to_watch"
    )
    comparison_available = _ev_value(
        evidence_items, "explanation_context.comparison.available"
    )

    headline = (
        "Start with feasibility, lateness, capacity violations, and "
        "whether comparison data is available."
    )
    parts: list[str] = [headline]

    if available:
        observed: list[str] = []
        if feasible is True:
            observed.append("the current plan is feasible")
        elif feasible is False:
            observed.append("the current plan is infeasible")
        if n_late is not None:
            observed.append(
                "no late customers" if n_late == 0
                else f"{n_late} late customer{'s' if n_late != 1 else ''}"
            )
        if n_cap is not None and n_cap > 0:
            observed.append(
                f"{n_cap} capacity violation{'s' if n_cap != 1 else ''}"
            )
        if n_unserved is not None and n_unserved > 0:
            observed.append(
                f"{n_unserved} unserved customer{'s' if n_unserved != 1 else ''}"
            )
        if observed:
            parts.append("This payload reports: " + ", ".join(observed) + ".")

    if comparison_available is False:
        parts.append(
            "It does not include a baseline or diff, so it cannot say "
            "whether the perturbation improved or worsened the plan."
        )

    if metrics and isinstance(metrics, list):
        parts.append(
            "For this perturbation family, the operationally relevant "
            "signals are: " + ", ".join(str(m) for m in metrics) + "."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Useful refusal renderer
# ---------------------------------------------------------------------------


def _render_useful_refusal(
    warnings: list[str], missing_fields: list[str], next_actions: list[str],
    prompt_text: str = "",
) -> str:
    import re
    parts = []
    if "false_premise_detected" in warnings:
        # Try to extract the specific route/customer mentioned
        route_m = re.search(r"\broute\s+(\d+)\b", prompt_text, re.IGNORECASE)
        cust_m = re.search(r"\bcustomer\s+(\d+)\b", prompt_text, re.IGNORECASE)
        if route_m:
            parts.append(
                f"Route {route_m.group(1)} does not exist in this solution."
            )
        elif cust_m:
            parts.append(
                f"Customer {cust_m.group(1)} does not exist in this solution."
            )
        else:
            parts.append(
                "The entity referenced in this question does not exist in the current solution."
            )
    elif "missing_new_customer_attribution" in warnings:
        parts.append(
            "The new customer's route assignment cannot be confirmed — "
            "the payload does not identify which customer was newly added."
        )
    elif "unsupported_comparison" in warnings:
        parts.append(
            "This question asks for a before/after comparison, but the current payload "
            "does not include the baseline solution or diff."
        )
    elif missing_fields:
        readable = [_missing_note(f) for f in missing_fields]
        parts.append(f"This question cannot be answered from the current payload. Missing: {', '.join(readable)}.")
    else:
        parts.append("This question cannot be answered from the current payload.")

    if next_actions:
        action_map = {
            "run_pyvrp_10s": "run the solver again (PyVRP, 10s budget).",
            "run_clarke_wright": "run the Clarke-Wright heuristic.",
            "expose_reference_solution_objective": "expose the reference solution objective.",
            "expose_baseline_solution": "expose the baseline solution.",
        }
        suggestions = [action_map[a] for a in next_actions if a in action_map]
        if suggestions:
            parts.append("Suggested: " + " ".join(suggestions))

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Partial answer renderer
# ---------------------------------------------------------------------------


def _render_partial_answer(
    intent: str,
    evidence_items: list[dict],
    warnings: list[str],
    missing_fields: list[str],
) -> str:
    partial = ""
    if intent == "objective_delta":
        partial = _render_objective_delta(evidence_items, warnings)
    elif intent == "objective_value":
        partial = _render_objective_value(evidence_items, warnings)
    elif intent == "feasibility_status":
        partial = _render_feasibility_status(evidence_items, warnings)
    # Overview impact intents own their own "graceful partial" behaviour
    # — describe current status + name what's missing, never claim
    # change without diff.
    elif intent == "perturbation_impact_summary":
        partial = _render_perturbation_impact_summary(evidence_items)
    elif intent == "route_impact_summary":
        partial = _render_route_impact_summary(evidence_items)
    elif intent == "perturbation_summary":
        partial = _render_perturbation_summary(evidence_items)
    elif intent == "scenario_summary":
        partial = _render_scenario_summary(evidence_items)
    elif intent == "solution_summary":
        partial = _render_solution_summary(evidence_items)
    elif intent == "what_to_watch":
        partial = _render_what_to_watch(evidence_items)
    else:
        partial = "Partial information is available."

    # Surface missing fields prominently for non-overview intents. The
    # overview renderers already mention missing baseline/diff in prose
    # — appending the raw field list would read as duplicate noise.
    overview_intents = {
        "perturbation_summary",
        "scenario_summary",
        "solution_summary",
        "perturbation_impact_summary",
        "route_impact_summary",
        "what_to_watch",
    }
    if missing_fields and intent not in overview_intents:
        readable = [_missing_note(f) for f in missing_fields]
        partial += f" Missing for a full answer: {', '.join(readable)}."

    return partial


# ---------------------------------------------------------------------------
# Compute-decision renderer
# ---------------------------------------------------------------------------


def _render_compute_decision(compute_decision: Optional[dict]) -> str:
    if not compute_decision:
        return ""
    mode = compute_decision.get("mode", "")
    action = compute_decision.get("recommended_action", "none")
    reason = compute_decision.get("reason", "")
    eta = compute_decision.get("expected_runtime_seconds")

    if mode == "needs_recompute":
        action_map = {
            "run_pyvrp_10s": "re-run the solver (PyVRP, 10s budget)",
            "run_clarke_wright": "re-run using the Clarke-Wright heuristic",
            "run_reuse_direct": "re-score the existing routes",
            "run_nearest_neighbor": "re-run using nearest-neighbour insertion",
        }
        action_str = action_map.get(action, action)
        text = (
            f"The current payload does not contain the result of this computation. "
            f"To answer, {action_str} is recommended."
        )
        if eta:
            text += f" Expected runtime: ~{eta:.0f}s."
        return text

    if mode == "needs_comparison_payload":
        return (
            "A comparison payload is required to answer this question. "
            "The current payload does not include the reference solution."
        )

    if mode == "clarification_needed":
        return (
            "This question is ambiguous — it could be a status query or an "
            "optimization request. Please clarify before proceeding."
        )

    return ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def verbalize(
    intent: str,
    answerability: str,
    behavior_class: str,
    evidence_items: list[dict],
    warnings: list[str],
    missing_fields: list[str],
    next_actions: list[str],
    prompt_text: str = "",
    compute_decision: Optional[dict] = None,
) -> str:
    """Render the contract to a natural-language answer_text string.

    Guaranteed to:
    - Not contradict evidence_items values
    - Surface warnings critical for interpretation
    - Not claim results that require missing_fields
    - Not claim recomputed results when compute_decision.mode == needs_recompute
    """
    # Recompute-needed: always surface compute decision, don't fabricate answer
    if compute_decision and compute_decision.get("mode") == "needs_recompute":
        return _render_compute_decision(compute_decision)

    # Useful refusal
    if behavior_class in ("useful_refusal",) or answerability == "not_answerable":
        return _render_useful_refusal(warnings, missing_fields, next_actions, prompt_text)

    # Partial answer
    if behavior_class == "partial_answer_with_warning":
        return _render_partial_answer(intent, evidence_items, warnings, missing_fields)

    # Direct answer or direct_answer_with_warning
    text = ""
    if intent == "objective_value":
        text = _render_objective_value(evidence_items, warnings)
    elif intent == "objective_delta":
        text = _render_objective_delta(evidence_items, warnings)
    elif intent == "feasibility_status":
        text = _render_feasibility_status(evidence_items, warnings)
    elif intent == "route_end_time":
        text = _render_route_end_time(evidence_items, warnings)
    elif intent == "customer_arrival":
        text = _render_customer_arrival(evidence_items, warnings)
    elif intent == "same_route_boolean":
        text = _render_same_route_boolean(evidence_items, prompt_text)
    elif intent == "single_customer_route_membership":
        text = _render_single_customer_route_membership(evidence_items, warnings, prompt_text)
    elif intent == "full_route_listing":
        text = _render_full_route_listing(evidence_items)
    elif intent == "lateness_summary":
        text = _render_lateness_summary(evidence_items)
    elif intent == "new_customer_assignment":
        text = _render_new_customer_assignment(evidence_items, warnings)
    elif intent in ("before_after_comparison",):
        if warnings:
            text = _render_useful_refusal(warnings, missing_fields, next_actions)
        else:
            text = "Before/after comparison is not supported without a baseline payload."
    elif intent == "perturbation_summary":
        text = _render_perturbation_summary(evidence_items)
    elif intent == "scenario_summary":
        text = _render_scenario_summary(evidence_items)
    elif intent == "solution_summary":
        text = _render_solution_summary(evidence_items)
    elif intent == "perturbation_impact_summary":
        text = _render_perturbation_impact_summary(evidence_items)
    elif intent == "route_impact_summary":
        text = _render_route_impact_summary(evidence_items)
    elif intent == "what_to_watch":
        text = _render_what_to_watch(evidence_items)
    else:
        text = f"Intent '{intent}' — no verbalizer implemented."

    # Append compute-decision note if informative
    if compute_decision:
        cd_note = _render_compute_decision(compute_decision)
        if cd_note and compute_decision.get("mode") != "answer_from_payload":
            text = text.rstrip(".") + ". " + cd_note

    return text


__all__ = ["verbalize"]

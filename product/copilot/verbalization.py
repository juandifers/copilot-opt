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


# ---------------------------------------------------------------------------
# A-008 — Evaluation verdict renderer
#
# Surfaces threshold-grounded verdicts (acceptable / needs_review /
# unacceptable) with explicit threshold + observed value side-by-side.
# Per the Phase B plan: judgments are claims backed by explicit
# threshold comparison; the prose never asserts a verdict without
# showing the comparison.
# ---------------------------------------------------------------------------


_EVAL_THRESHOLD_LABELS = {
    "late_customers_count": "Lateness",
    "objective_relative_delta": "Objective change",
    "feasibility": "Feasibility",
    "routes_modified_pct": "Routes modified",
}


def _format_observed(metric: str, value, threshold) -> str:
    """Format observed/threshold values per metric for prose."""
    if metric == "late_customers_count":
        return f"{value} customers late (threshold: {threshold})"
    if metric == "objective_relative_delta":
        # value is a signed percent; threshold is fraction
        return f"{abs(float(value)):.1f}% (threshold: {float(threshold) * 100:.1f}%)"
    if metric == "feasibility":
        state = "infeasible" if value is True else "feasible"
        return f"{state} (gate: strict)"
    if metric == "routes_modified_pct":
        return f"{float(value) * 100:.1f}% (threshold: {float(threshold) * 100:.1f}%)"
    return f"{value} (threshold: {threshold})"


def _render_evaluation_judgment(
    evidence_items: list[dict],
    prompt_text: str = "",
    perturbation_type: Optional[str] = None,
) -> str:
    """A-008 evaluation prose. Renders verdict + per-check comparison.

    Re-runs the evaluation against the payload-derived evidence items so
    the verdict computation and the prose stay coherent (the evidence
    layer emits one item per check; the renderer reconstructs the
    aggregation from the same data).
    """
    from product.copilot.evaluation import (
        Verdict, EvaluationResult, ThresholdCheck,
    )
    # Reconstruct checks from evidence_items (each ev item carries
    # supports string with the threshold metric and pass/fail). We need
    # the original check objects for the verdict, but we can re-derive
    # from the evidence items' structure since the supports format is
    # stable.
    #
    # Easier path: extract the (family, metric, value, passes, bias)
    # tuples from the evidence_items' supports/field_path. The verbalizer
    # is bound to the same module that emitted the evidence so this is
    # safe.
    import re as _re_local
    parsed_checks = []
    for ev in evidence_items:
        path = ev.get("field_path") if isinstance(ev, dict) else getattr(ev, "field_path", "")
        if not isinstance(path, str) or not path.startswith("evaluation."):
            continue
        supports = ev.get("supports") if isinstance(ev, dict) else getattr(ev, "supports", "") or ""
        value = ev.get("value") if isinstance(ev, dict) else getattr(ev, "value", None)
        # Parse "metric check (threshold); observed=...; passes=True|False [bias_band]"
        m = _re_local.match(
            r"(?P<metric>\S+)\s+check\s+\((?P<threshold>[^)]+)\);\s+"
            r"observed=(?P<observed>[^;]+);\s+passes=(?P<passes>True|False)"
            r"(?P<bias>\s+\[bias_band\])?",
            supports or "",
        )
        if not m:
            continue
        metric = m.group("metric")
        threshold_raw = m.group("threshold")
        passes = m.group("passes") == "True"
        bias_applied = bool(m.group("bias"))
        # threshold may be numeric or "strict"
        threshold_val: Any = threshold_raw
        try:
            threshold_val = float(threshold_raw)
            if threshold_val.is_integer() and ".0" not in threshold_raw:
                threshold_val = int(threshold_val)
        except ValueError:
            pass
        # family from field_path: evaluation.<family>.<metric>
        parts = path.split(".")
        family = parts[1].upper() if len(parts) >= 3 else "UNKNOWN"
        parsed_checks.append({
            "family": family,
            "metric": metric,
            "threshold": threshold_val,
            "observed": value,
            "passes": passes,
            "bias_applied": bias_applied,
        })

    if not parsed_checks:
        return (
            "Plan acceptability cannot be evaluated — none of the "
            "configured thresholds have the data they need in this payload."
        )

    # Aggregation (PV exception)
    pv_failed = any(
        c["family"] == "PLAN_VALIDITY" and c["metric"] == "feasibility" and not c["passes"]
        for c in parsed_checks
    )
    n_failed = sum(1 for c in parsed_checks if not c["passes"])
    bias_applied = any(c["bias_applied"] for c in parsed_checks)

    if pv_failed:
        verdict = "unacceptable"
        pv_exception = True
    elif n_failed == 0:
        verdict = "acceptable"
        pv_exception = False
    elif n_failed == 1:
        verdict = "needs_review"
        pv_exception = False
    else:
        verdict = "unacceptable"
        pv_exception = False

    # Build comparison lines
    lines = []
    for c in parsed_checks:
        label = _EVAL_THRESHOLD_LABELS.get(c["metric"], c["metric"])
        comparison = _format_observed(c["metric"], c["observed"], c["threshold"])
        verdict_word = (
            "within limits" if c["passes"]
            else ("exceeds threshold" if not c["bias_applied"] else "within bias band, flagged for review")
        )
        lines.append(f"- {label}: {comparison} — {verdict_word}")

    # Pick template per verdict
    if pv_exception:
        header = (
            "This plan is unacceptable: feasibility was lost in the "
            "perturbation. At least one customer can no longer be served "
            "by any vehicle within constraints."
        )
    elif verdict == "acceptable":
        if bias_applied:
            header = (
                "This plan is at the edge of acceptability: one or more "
                "dimensions are within their bias band; recommending "
                "review."
            )
        else:
            header = "By the configured thresholds, this plan is acceptable."
    elif verdict == "needs_review":
        failing = next((c for c in parsed_checks if not c["passes"]), None)
        if failing:
            label = _EVAL_THRESHOLD_LABELS.get(failing["metric"], failing["metric"])
            header = (
                f"This plan needs review: the {label.lower()} dimension "
                f"exceeds its threshold."
            )
        else:
            header = "This plan needs review."
    else:  # unacceptable (non-PV)
        header = (
            "This plan is outside acceptable bounds: multiple thresholds "
            "are exceeded."
        )

    rationale_line = (
        "\n\nThreshold rationale: docs/threshold_rationale.md"
    )
    return header + "\n" + "\n".join(lines) + rationale_line


# ---------------------------------------------------------------------------
# B4 (A-007) — templated causal narration
#
# Appends a one-sentence causal explanation to delta/comparison prose.
# Per the Phase B plan: cause = perturbation framing; effect = diff field
# inference. Solver-internal "why" remains out of scope — the narration
# never claims causal relationships the contract can't ground.
# ---------------------------------------------------------------------------


def _b4_perturbation_family(perturbation_id_or_type: Optional[str]) -> Optional[str]:
    """Normalize a perturbation_id like 'TT_4' to a family token (TRAVEL_TIME)."""
    if not perturbation_id_or_type:
        return None
    s = str(perturbation_id_or_type).upper()
    if s.startswith("TT") or s == "TRAVEL_TIME":
        return "TRAVEL_TIME"
    if s.startswith("ST") or s == "SERVICE_TIME":
        return "SERVICE_TIME"
    if s.startswith("TW") or s == "TIME_WINDOW":
        return "TIME_WINDOW"
    if s.startswith("OC") or s == "ORDER_CHANGE":
        return "ORDER_CHANGE"
    return None


def _b4_causal_phrase(
    perturbation_type: Optional[str],
    evidence_items: list[dict],
) -> Optional[str]:
    """Return the cause-side phrase per perturbation family.

    Returns ``None`` when the perturbation family is unknown so the
    caller skips the causal sentence rather than rendering a hollow
    "this change occurred because the perturbation".
    """
    fam = _b4_perturbation_family(perturbation_type)
    if fam == "TRAVEL_TIME":
        return "travel times changed across the network"
    if fam == "SERVICE_TIME":
        return "service times at customers were extended"
    if fam == "TIME_WINDOW":
        return "customer time windows shifted"
    if fam == "ORDER_CHANGE":
        new_ids = _ev_value(evidence_items, "diff.routes.modified") or []
        added_cust = _ev_value(evidence_items, "new_customer_ids")
        if isinstance(added_cust, list) and added_cust:
            ids = ", ".join(str(i) for i in sorted(added_cust))
            return f"the perturbation added customer(s) {ids}"
        return "the customer set changed"
    return None


def _b4_objective_effect(
    delta_abs: Optional[float],
    delta_pct: Optional[float],
    units: Optional[str],
) -> Optional[str]:
    if delta_abs is None or delta_abs == 0.0:
        return None
    direction = "increased" if delta_abs > 0 else "decreased"
    unit_str = f" {units}" if units else ""
    if delta_pct is not None:
        return f"{direction} the total {direction.replace('ed','')[:-1]}d cost by {abs(delta_abs):.2f}{unit_str} ({abs(delta_pct):.1f}%)"
    return f"{direction} the total cost by {abs(delta_abs):.2f}{unit_str}"


def _b4_diff_effect(evidence_items: list[dict]) -> Optional[str]:
    """Infer the effect-side phrase from diff fields.

    Priority order matches the Phase B plan: schedule (new late) >
    structure (modified routes) > feasibility > objective > none. The
    most operationally-loaded effect wins.
    """
    new_late = _ev_value(evidence_items, "diff.schedule.new_late_customer_ids")
    if isinstance(new_late, list) and new_late:
        n = len(new_late)
        return f"caused {n} customer{'s' if n != 1 else ''} to become late"

    no_longer_late = _ev_value(evidence_items, "diff.schedule.no_longer_late_customer_ids")
    if isinstance(no_longer_late, list) and no_longer_late:
        n = len(no_longer_late)
        return (
            f"actually relieved schedule pressure — {n} customer"
            f"{'s' if n != 1 else ''} recovered from being late"
        )

    modified_evs = [
        ev for ev in evidence_items
        if isinstance(ev.get("field_path"), str)
        and ev["field_path"].startswith("diff.routes.modified[")
    ]
    if modified_evs:
        n_modified = len({
            ev["field_path"].rsplit("].", 1)[0] for ev in modified_evs
        })
        return f"forced {n_modified} route{'s' if n_modified != 1 else ''} to be re-shaped"

    pv_became_inf = _ev_value(evidence_items, "diff.feasibility.became_infeasible")
    if pv_became_inf is True:
        return "broke feasibility"

    obj_abs = _ev_value(evidence_items, "diff.objective.delta_absolute")
    obj_pct = _ev_value(evidence_items, "diff.objective.delta_percent")
    if obj_abs is not None and obj_abs != 0.0:
        direction = "raised" if obj_abs > 0 else "lowered"
        pct = f" ({abs(obj_pct):.1f}%)" if obj_pct is not None else ""
        return f"{direction} the objective by {abs(obj_abs):.2f}{pct}"

    return None


def _render_objective_delta(
    evidence_items: list[dict],
    warnings: list[str],
    perturbation_type: Optional[str] = None,
) -> str:
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
    # B4: append causal narration when perturbation_type is known and the
    # delta is nontrivial.
    if perturbation_type and delta_abs is not None and delta_abs != 0.0:
        effect = _b4_objective_effect(delta_abs, delta_pct, units)
        causal = _b4_causal_phrase(perturbation_type, evidence_items)
        if causal and effect:
            text += f" This change occurred because {causal}, which {effect}."
    return text


def _render_before_after_comparison(
    evidence_items: list[dict],
    warnings: list[str],
    perturbation_type: Optional[str] = None,
) -> str:
    """Render the Tier-2 diff payload as a natural-language narrative.

    B5 (A-007): per-family narrative templates replace the previous
    bullet-style fact list. The current evidence emission is unchanged;
    only the prose layer is upgraded. Family templates chain when
    multiple sub-blocks are non-trivial (e.g. SCHEDULE perturbation that
    also modified routes — schedule narrative + struct narrative).

    B4 (A-007): when ``perturbation_type`` is provided and the diff
    surfaces a non-trivial effect, an additional causal sentence is
    appended via ``_b4_causal_phrase`` + the inferred effect string.
    """
    obj_abs = _ev_value(evidence_items, "diff.objective.delta_absolute")
    obj_pct = _ev_value(evidence_items, "diff.objective.delta_percent")
    obj_baseline = _ev_value(evidence_items, "diff.objective.baseline")
    obj_action = _ev_value(evidence_items, "diff.objective.action")
    obj_units = _ev_value(evidence_items, "units.objective")
    pv_became_inf = _ev_value(evidence_items, "diff.feasibility.became_infeasible")
    pv_became_feas = _ev_value(evidence_items, "diff.feasibility.became_feasible")
    routes_added = _ev_value(evidence_items, "diff.routes.added")
    routes_removed = _ev_value(evidence_items, "diff.routes.removed")
    new_late = _ev_value(evidence_items, "diff.schedule.new_late_customer_ids")
    no_longer_late = _ev_value(evidence_items, "diff.schedule.no_longer_late_customer_ids")

    parts: list[str] = []

    # OBJ narrative
    if obj_abs is not None:
        unit_str = f" {obj_units}" if obj_units else ""
        if obj_abs == 0:
            if obj_action is not None:
                parts.append(
                    f"Compared to the baseline, the objective is unchanged at "
                    f"{obj_action}{unit_str}."
                )
            else:
                parts.append("Objective unchanged from baseline.")
        else:
            direction = "rose" if obj_abs > 0 else "fell"
            sign = "+" if obj_abs > 0 else ""
            pct_str = f"{sign}{obj_pct:.1f}%" if obj_pct is not None else f"{sign}{obj_abs:.2f}"
            if obj_baseline is not None and obj_action is not None:
                parts.append(
                    f"Compared to the baseline, the objective {direction} by "
                    f"{abs(obj_abs):.2f}{unit_str} ({pct_str}) — from "
                    f"{obj_baseline}{unit_str} to {obj_action}{unit_str}."
                )
            else:
                parts.append(
                    f"The objective {direction} by {abs(obj_abs):.2f}{unit_str} "
                    f"({pct_str}) from baseline."
                )

    # PV narrative
    if pv_became_inf is True:
        parts.append(
            "The plan became infeasible after the perturbation; one or more "
            "constraints are no longer satisfied."
        )
    elif pv_became_feas is True:
        parts.append(
            "The plan recovered feasibility — previously-violated constraints "
            "are now satisfied."
        )
    elif pv_became_inf is False or pv_became_feas is False:
        # Both flags explicitly false: feasibility preserved through the
        # perturbation. Avoid this assertion when the flags weren't present
        # in the diff at all.
        if pv_became_inf is False and pv_became_feas is False:
            parts.append(
                "Feasibility was maintained through the perturbation; all "
                "constraints remain satisfied."
            )

    # STRUCT narrative
    n_added = len(routes_added) if isinstance(routes_added, list) else 0
    n_removed = len(routes_removed) if isinstance(routes_removed, list) else 0
    modified_evs = [
        ev for ev in evidence_items
        if isinstance(ev.get("field_path"), str)
        and ev["field_path"].startswith("diff.routes.modified[")
    ]
    n_modified = len({
        ev["field_path"].rsplit("].", 1)[0]
        for ev in modified_evs
    }) if modified_evs else 0
    if n_added or n_removed or n_modified:
        bits = []
        if n_added:
            bits.append(f"{n_added} route{'s' if n_added != 1 else ''} added")
        if n_removed:
            bits.append(f"{n_removed} route{'s' if n_removed != 1 else ''} removed")
        if n_modified:
            bits.append(f"{n_modified} route{'s' if n_modified != 1 else ''} modified")
        total_changes = n_added + n_removed + n_modified
        parts.append(
            f"The plan structure changed in {total_changes} place{'s' if total_changes != 1 else ''}: "
            f"{', '.join(bits)}."
        )

    # SCHEDULE narrative
    if isinstance(new_late, list) or isinstance(no_longer_late, list):
        if not new_late and not no_longer_late:
            parts.append(
                "Schedule structure unchanged — lateness pattern is identical "
                "to baseline."
            )
        else:
            if new_late:
                ids_str = ", ".join(str(i) for i in sorted(new_late))
                parts.append(
                    f"{len(new_late)} customer{'s' if len(new_late) != 1 else ''} "
                    f"became late after the perturbation: {ids_str}."
                )
            if no_longer_late:
                ids_str = ", ".join(str(i) for i in sorted(no_longer_late))
                parts.append(
                    f"{len(no_longer_late)} customer{'s' if len(no_longer_late) != 1 else ''} "
                    f"recovered from being late: {ids_str}."
                )

    if not parts:
        return "Before/after comparison is not available — payload lacks diff data."

    text = " ".join(parts)

    # B4: causal narration. Append when perturbation_type is known and the
    # diff shows a material effect.
    if perturbation_type:
        causal = _b4_causal_phrase(perturbation_type, evidence_items)
        effect = _b4_diff_effect(evidence_items)
        if causal and effect:
            text += f" This change occurred because {causal}, which {effect}."

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


def _render_ranking_aspect(
    evidence_items: list[dict],
    prompt_text: str,
    family: str = "",
) -> Optional[str]:
    """Verbalizer for the B1 ranking aspect (A-006).

    Returns rendered prose when the prompt is a ranking query and the
    evidence layer surfaced ranking evidence; returns ``None`` to let
    the caller fall back to the generic aspectual template.

    Templates per spec §B1:
    - multi-entry (>=2 items): "The top K target by dimension are: 1. ... 2. ..."
    - single-entry: "The X with the worst Y is Z (value units)."
    - zero-entry (e.g. lateness=0): "All customers are on time, so there's
      no lateness ranking to surface."
    - ambiguity_note (when dimension was inferred from a bare superlative):
      appended as a clarifying line.
    """
    from product.data import evidence as evidence_mod

    # When evidence is already present, the dispatcher already confirmed
    # family compatibility — derive the spec with a permissive default
    # family so we always render the ranking template instead of the
    # family-incompat refusal.
    family_for_spec = family or ("SCHEDULE" if evidence_items else "")
    spec = evidence_mod.derive_ranking_spec(prompt_text, family_for_spec)
    if spec is None:
        return None

    # Family-incompatible: refuse with a family-aware explanation.
    # Only used when evidence_items is empty (caller fell through to the
    # refusal path with no ranking data).
    if not spec.family_compatible and not evidence_items:
        if spec.family in ("OBJ", ""):
            return (
                f"This is an OBJ-family payload and doesn't carry per-"
                f"{spec.target} detail. The objective value is reported "
                f"directly; for per-{spec.target} ranking by {spec.dimension}, "
                f"the SCHEDULE version of this scenario would be needed."
            )
        if spec.family in ("PV", "PLAN_VALIDITY"):
            return (
                f"This PV-family payload reports feasibility status only; "
                f"per-{spec.target} ranking by {spec.dimension} is not "
                f"supported. Try the SCHEDULE version of this scenario for "
                f"timing-dimension ranking."
            )
        if spec.family == "STRUCT" and spec.dimension != "load":
            return (
                f"This STRUCT-family payload supports ranking by load "
                f"(customer count per route), but not by {spec.dimension}. "
                f"For lateness / end-time / window ranking, the SCHEDULE "
                f"version of this scenario would be needed."
            )
        return None  # let caller fall back

    # Look for the n_late_customers zero-result evidence shape
    is_zero_lateness = (
        spec.dimension == "lateness"
        and len(evidence_items) == 1
        and (
            (evidence_items[0].get("field_path") if isinstance(evidence_items[0], dict)
             else getattr(evidence_items[0], "field_path", ""))
            == "n_late_customers"
        )
    )

    if is_zero_lateness:
        if spec.target == "customer":
            body = (
                "All customers are on time — there's no lateness ranking "
                "to surface."
            )
        else:
            body = (
                "No routes have any lateness — every customer is on time, "
                "so the lateness ranking is empty."
            )
    elif not evidence_items:
        body = f"Nothing to rank by {spec.dimension} — the field is empty."
    else:
        # Multi-entry or single-entry rendering
        n = len(evidence_items)
        dim_units = {
            "lateness": "min late",
            "end_time": "end time",
            "load": "customers",
            "slack": "end time",
            "window_margin": "min margin",
            "window_width": "min wide",
        }.get(spec.dimension, "")
        if n == 1:
            ev = evidence_items[0]
            path = ev.get("field_path") if isinstance(ev, dict) else getattr(ev, "field_path", "")
            val = ev.get("value") if isinstance(ev, dict) else getattr(ev, "value", None)
            display = _ranking_display_for_path(path, ev)
            body = (
                f"The {spec.target} with the {spec.dimension} ranking is "
                f"{display} ({val} {dim_units})."
            )
        else:
            lines = [
                f"The top {min(n, spec.top_k)} {spec.target}s by {spec.dimension}:"
            ]
            for i, ev in enumerate(evidence_items[: spec.top_k], start=1):
                path = ev.get("field_path") if isinstance(ev, dict) else getattr(ev, "field_path", "")
                val = ev.get("value") if isinstance(ev, dict) else getattr(ev, "value", None)
                display = _ranking_display_for_path(path, ev)
                lines.append(f"  {i}. {display} — {val} {dim_units}")
            body = "\n".join(lines)

    # R3 (A-008.5): when the prompt was ambiguous and we built structured
    # alternative-dimension suggestions, append the explicit alternatives
    # block. Falls back to the legacy ambiguity_note line when alternatives
    # is empty (UNAMBIGUOUS prompt, flag-disabled, or family with only one
    # compatible dimension) — preserving byte-identical output for cases
    # that were UNAMBIGUOUS prior to A-008.5.
    alternatives = getattr(spec, "alternatives", None) or []
    if alternatives:
        # Operator-style sentence: "I interpreted '<sup>' as '<dim>'. Other
        # rankings available — re-ask with one of these:" + 2–4 bullets.
        # The ambiguity_note string already carries the bare-superlative
        # phrasing, but we want the structured block to be self-contained.
        sup_phrase: Optional[str] = None
        if spec.ambiguity_note:
            import re as _re_an
            m_sup = _re_an.search(r"interpreted '([^']+)'", spec.ambiguity_note)
            if m_sup:
                sup_phrase = m_sup.group(1)
        header_intro = (
            f"I interpreted '{sup_phrase}' as '{spec.dimension}'."
            if sup_phrase
            else f"I defaulted to ranking by '{spec.dimension}'."
        )
        lines = [
            "",
            f"{header_intro} Other rankings are available — re-ask with one of these phrasings:",
        ]
        for alt in alternatives:
            lines.append(f"  - {alt.example_phrasing} ({alt.label})")
        body = body + "\n" + "\n".join(lines)
    elif spec.ambiguity_note:
        body = f"{body}\n\n({spec.ambiguity_note}.)"
    return body


def _ranking_display_for_path(path: str, ev) -> str:
    """Best-effort short label for a ranking evidence row."""
    import re as _re
    if not path:
        return "(unknown)"
    if isinstance(ev, dict):
        dl = ev.get("display_label")
    else:
        dl = getattr(ev, "display_label", None)
    if dl:
        return dl
    m_r = _re.search(r"route_idx=(\d+)", path)
    if m_r:
        return f"Route {int(m_r.group(1)) + 1}"
    m_c = _re.search(r"customer_id=(\d+)", path)
    if m_c:
        return f"Customer {m_c.group(1)}"
    return path


def _render_aspectual_fallback(
    evidence_items: list[dict],
    prompt_text: str,
) -> str:
    """Generic verbalizer for the within-family aspectual fallback path.

    Activated when intent classification returned "unknown" but the
    evidence layer dispatched on a SCHEDULE-aspect (lateness or timing).
    Renders a brief framing line + one bullet per evidence item.
    Template is generic for v1; per-aspect customization is deferred.
    """
    import re as _re

    # Extract entity hints from the evidence items' field paths.
    cust_ids: list[int] = []
    route_idxs: list[int] = []
    for ev in evidence_items:
        path = ev.get("field_path") if isinstance(ev, dict) else getattr(ev, "field_path", "")
        if not path:
            continue
        m_c = _re.search(r"customer_id=(\d+)", path)
        if m_c:
            v = int(m_c.group(1))
            if v not in cust_ids:
                cust_ids.append(v)
        m_r = _re.search(r"route_idx=(\d+)", path)
        if m_r:
            v = int(m_r.group(1))
            if v not in route_idxs:
                route_idxs.append(v)

    # Build a one-line entity description.
    parts: list[str] = []
    if cust_ids:
        if len(cust_ids) == 1:
            parts.append(f"customer {cust_ids[0]}")
        elif len(cust_ids) <= 3:
            parts.append("customers " + ", ".join(str(c) for c in cust_ids))
        else:
            parts.append(f"{len(cust_ids)} customers")
    if route_idxs:
        if len(route_idxs) == 1:
            parts.append(f"Route {route_idxs[0] + 1}")
        else:
            parts.append(f"{len(route_idxs)} routes")
    entity_desc = " and ".join(parts) if parts else "this scenario"

    # Derive aspect from the prompt (cheap regex; same patterns as the
    # dispatcher — keep verbalization self-contained for now).
    aspect_desc = "the schedule"
    p = (prompt_text or "").lower()
    if _re.search(
        r"\b(late|lateness|delay(?:ed)?|behind(?:\s+schedule)?|miss(?:ed|ing)?)\b",
        p,
    ):
        aspect_desc = "lateness"
    elif _re.search(
        r"\b(arriv|when\s+does|what\s+time|schedule|completion|finish|done)\b",
        p,
    ):
        aspect_desc = "timing"

    header = (
        f"I couldn't classify your question precisely, but here's what I can "
        f"tell you about {entity_desc} regarding {aspect_desc}:"
    )

    bullets: list[str] = []
    for ev in evidence_items:
        if isinstance(ev, dict):
            path = ev.get("field_path", "")
            val = ev.get("value")
        else:
            path = getattr(ev, "field_path", "")
            val = getattr(ev, "value", None)
        bullets.append(f"  • {path}: {val}")
    body = "\n".join(bullets)

    footer = "Was this what you were asking about? If not, try rephrasing."
    return f"{header}\n{body}\n{footer}"


def _render_partial_answer(
    intent: str,
    evidence_items: list[dict],
    warnings: list[str],
    missing_fields: list[str],
    prompt_text: str = "",
    perturbation_type: Optional[str] = None,
) -> str:
    partial = ""
    if intent == "objective_delta":
        partial = _render_objective_delta(evidence_items, warnings, perturbation_type)
    elif intent == "objective_value":
        partial = _render_objective_value(evidence_items, warnings)
    elif intent == "feasibility_status":
        partial = _render_feasibility_status(evidence_items, warnings)
    elif intent == "before_after_comparison":
        partial = _render_before_after_comparison(evidence_items, warnings, perturbation_type)
    elif intent in ("evaluate_plan_acceptability", "evaluate_dimension_acceptability"):
        partial = _render_evaluation_judgment(evidence_items, prompt_text, perturbation_type)
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
    elif intent == "unknown" and evidence_items:
        # Within-family aspectual fallback: intent didn't classify but the
        # evidence layer surfaced grounded payload fields.
        # First try the ranking aspect (B1, A-006) — if it returns prose,
        # use it; otherwise fall back to the generic aspectual template.
        ranking_prose = _render_ranking_aspect(evidence_items, prompt_text)
        if ranking_prose is not None:
            return ranking_prose
        return _render_aspectual_fallback(evidence_items, prompt_text)
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
    perturbation_type: Optional[str] = None,
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
        return _render_partial_answer(
            intent, evidence_items, warnings, missing_fields, prompt_text,
            perturbation_type=perturbation_type,
        )

    # Direct answer or direct_answer_with_warning
    text = ""
    if intent == "objective_value":
        text = _render_objective_value(evidence_items, warnings)
    elif intent == "objective_delta":
        text = _render_objective_delta(evidence_items, warnings, perturbation_type)
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
    elif intent == "before_after_comparison":
        text = _render_before_after_comparison(evidence_items, warnings, perturbation_type)
    elif intent in ("evaluate_plan_acceptability", "evaluate_dimension_acceptability"):
        text = _render_evaluation_judgment(evidence_items, prompt_text, perturbation_type)
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

"""Operational-validity check functions — one per claim family.

Pure deterministic functions over (generator-output, payload) pairs. The
rubric (``experiment/configs/rubric.md`` §b) defines the per-family
thresholds; these functions implement those thresholds verbatim.

Return shape per family:
    {"op_validity_pass": <bool | None>,
     "op_validity_check_results": <dict | None>,
     "refusal_detected": <bool>}

Null is returned for:
- refusals (the canonical refusal phrase is in answer_text)
- non-headline answers (op_validity_gradable is False, per rubric §c)

These functions never call an LLM and never touch I/O. They run in
microseconds on already-parsed inputs.
"""
from __future__ import annotations

from typing import Any

REFUSAL_PHRASE = "the data does not contain this information"

OBJECTIVE_TOLERANCE_FRAC = 0.005      # 0.5%
TIMING_TOLERANCE_MINUTES = 1.0


def detect_refusal(answer_text: str) -> bool:
    """Case-insensitive substring match against the rubric refusal phrase."""
    return REFUSAL_PHRASE in (answer_text or "").lower()


def _null_result(refusal_detected: bool = False) -> dict[str, Any]:
    return {
        "op_validity_pass": None,
        "op_validity_check_results": None,
        "refusal_detected": refusal_detected,
    }


def check_obj(
    generator_output: dict,
    payload: dict,
    op_validity_gradable: bool,
) -> dict[str, Any]:
    """OBJ check: |claimed - action_objective| / action_objective <= 0.005."""
    answer_text = generator_output.get("answer_text", "")
    if detect_refusal(answer_text):
        return _null_result(refusal_detected=True)
    if not op_validity_gradable:
        return _null_result(refusal_detected=False)

    stated = generator_output.get("claimed_objective")
    actual = payload.get("action_objective")
    if stated is None:
        # Rubric §b: "If claimed_objective is null while the question
        # demanded an objective answer, op_validity_pass = false ..."
        return {
            "op_validity_pass": False,
            "op_validity_check_results": {"objective_within_0_5_pct": False},
            "refusal_detected": False,
        }
    if actual is None or actual == 0:
        # Defensive: payload should always have a finite, non-zero
        # action_objective. If not, log false rather than divide-by-zero.
        return {
            "op_validity_pass": False,
            "op_validity_check_results": {"objective_within_0_5_pct": False},
            "refusal_detected": False,
        }
    rel_err = abs(stated - actual) / abs(actual)
    within = rel_err <= OBJECTIVE_TOLERANCE_FRAC
    return {
        "op_validity_pass": bool(within),
        "op_validity_check_results": {"objective_within_0_5_pct": bool(within)},
        "refusal_detected": False,
    }


def check_pv(
    generator_output: dict,
    payload: dict,
    op_validity_gradable: bool,
) -> dict[str, Any]:
    """PV check: claimed_feasible == payload.feasible exact match."""
    answer_text = generator_output.get("answer_text", "")
    if detect_refusal(answer_text):
        return _null_result(refusal_detected=True)
    if not op_validity_gradable:
        return _null_result(refusal_detected=False)

    stated = generator_output.get("claimed_feasible")
    actual = payload.get("feasible")
    if stated is None:
        return {
            "op_validity_pass": False,
            "op_validity_check_results": {"feasibility_exact_match": False},
            "refusal_detected": False,
        }
    match = bool(stated) == bool(actual)
    return {
        "op_validity_pass": match,
        "op_validity_check_results": {"feasibility_exact_match": match},
        "refusal_detected": False,
    }


def check_struct(
    generator_output: dict,
    payload: dict,
    op_validity_gradable: bool,
) -> dict[str, Any]:
    """STRUCT check: route_count_exact AND/OR membership_set_equal AND/OR same_route_boolean.

    Conjunction across non-null sub-checks.
    """
    answer_text = generator_output.get("answer_text", "")
    if detect_refusal(answer_text):
        return _null_result(refusal_detected=True)
    if not op_validity_gradable:
        return _null_result(refusal_detected=False)

    sub: dict[str, Any] = {
        "route_count_exact": None,
        "membership_set_equal": None,
        "same_route_boolean": None,
    }

    stated_count = generator_output.get("claimed_route_count")
    actual_count = payload.get("n_routes")
    if stated_count is not None:
        sub["route_count_exact"] = (int(stated_count) == int(actual_count))

    stated_membership = generator_output.get("claimed_route_membership")
    routes_by_idx: dict[int, set[int]] = {
        int(r["route_idx"]): set(int(c) for c in r["customer_ids"])
        for r in (payload.get("routes") or [])
    }
    if stated_membership is not None and len(stated_membership) > 0:
        # Same-route boolean: the answer states a pair of customers
        # are/are-not on the same route. Detection heuristic: a single
        # membership entry with exactly two customer_ids and no
        # accompanying count claim — interpret as same-route assertion.
        # Otherwise treat as a route-contains-customers claim.
        is_pairwise_membership = (
            len(stated_membership) == 1
            and len(stated_membership[0].get("customer_ids", [])) == 2
            and stated_count is None
        )
        if is_pairwise_membership:
            a, b = (int(c) for c in stated_membership[0]["customer_ids"])
            actually_same = any(
                {a, b}.issubset(s) for s in routes_by_idx.values()
            )
            # The stated route_idx encodes the asserted same-route route;
            # the rubric's same_route_boolean check is on whether they ARE
            # on the same route, not which route. We treat any non-null
            # stated route as asserting "yes same".
            sub["same_route_boolean"] = bool(actually_same)
        else:
            # Membership set equality, conjoined across stated pairs.
            ok = True
            for pair in stated_membership:
                ridx = int(pair["route_idx"])
                stated_ids = set(int(c) for c in pair["customer_ids"])
                actual_ids = routes_by_idx.get(ridx, set())
                if stated_ids != actual_ids:
                    # Allow "subset" semantics when the answer mentions
                    # specific customers on a route: if every stated
                    # customer is on that route, count as match.
                    # Rubric §b membership_set_equal is "set equality"
                    # across the claim — we apply set equality of stated
                    # vs claimed-customers-on-route; for single-customer
                    # claims (e.g., STRUCT-2 "which route is customer X"),
                    # stated_ids = {X} and actual_ids contains X plus
                    # others. The rubric intent (per
                    # synthetic_templates.md STRUCT-2) is "match if
                    # actual_ids contains stated_ids and stated_ids is
                    # the customer subset the answer asserted".
                    if not stated_ids.issubset(actual_ids):
                        ok = False
                        break
            sub["membership_set_equal"] = ok

    non_null = {k: v for k, v in sub.items() if v is not None}
    if not non_null:
        # Headline claim required but no sub-check populated → fail
        # (per the OBJ-analogous rubric rule for null claims).
        return {
            "op_validity_pass": False,
            "op_validity_check_results": sub,
            "refusal_detected": False,
        }
    op_pass = all(non_null.values())
    return {
        "op_validity_pass": op_pass,
        "op_validity_check_results": sub,
        "refusal_detected": False,
    }


def check_schedule(
    generator_output: dict,
    payload: dict,
    op_validity_gradable: bool,
) -> dict[str, Any]:
    """SCHEDULE check: arrival_within_1min AND/OR lateness_within_1min AND/OR any_late_boolean.

    Conjunction across non-null sub-checks. Tolerance is 1.0 Solomon minute.
    """
    answer_text = generator_output.get("answer_text", "")
    if detect_refusal(answer_text):
        return _null_result(refusal_detected=True)
    if not op_validity_gradable:
        return _null_result(refusal_detected=False)

    sub: dict[str, Any] = {
        "arrival_within_1min": None,
        "lateness_within_1min": None,
        "any_late_boolean": None,
    }

    timings = generator_output.get("claimed_customer_timings")
    customer_schedule_by_id: dict[int, dict] = {
        int(e["customer_id"]): e
        for e in (payload.get("customer_schedule") or [])
    }
    if timings is not None and len(timings) > 0:
        ok = True
        for entry in timings:
            cid = int(entry["customer_id"])
            stated = float(entry["stated_arrival_or_start"])
            sched = customer_schedule_by_id.get(cid)
            if sched is None:
                ok = False
                break
            actual = float(sched["start_service"])
            if abs(stated - actual) > TIMING_TOLERANCE_MINUTES:
                ok = False
                break
        sub["arrival_within_1min"] = ok

    late_list = generator_output.get("claimed_late_customers")
    if late_list is not None:
        # any_late_boolean: stated_any_late == (n_late_customers > 0).
        # Empty list means "nobody is late"; non-empty means "yes some
        # are late". The rubric §b additional-case treats this case.
        stated_any_late = len(late_list) > 0
        actual_any_late = int(payload.get("n_late_customers", 0)) > 0
        sub["any_late_boolean"] = (stated_any_late == actual_any_late)

        # lateness_within_1min: only applies if the answer enumerated
        # specific late customer IDs. Set-equality vs payload's
        # late_customer_ids; lateness_minutes match is checked when
        # generator emitted a per-customer claimed_customer_timings,
        # which is already covered by arrival_within_1min above.
        if len(late_list) > 0:
            stated_set = set(int(c) for c in late_list)
            actual_set = set(
                int(c) for c in (payload.get("late_customer_ids") or [])
            )
            sub["lateness_within_1min"] = (stated_set == actual_set)

    non_null = {k: v for k, v in sub.items() if v is not None}
    if not non_null:
        return {
            "op_validity_pass": False,
            "op_validity_check_results": sub,
            "refusal_detected": False,
        }
    op_pass = all(non_null.values())
    return {
        "op_validity_pass": op_pass,
        "op_validity_check_results": sub,
        "refusal_detected": False,
    }


CHECK_BY_FAMILY = {
    "OBJ": check_obj,
    "PLAN_VALIDITY": check_pv,
    "STRUCT": check_struct,
    "SCHEDULE": check_schedule,
}


def check(
    family: str,
    generator_output: dict,
    payload: dict,
    op_validity_gradable: bool,
) -> dict[str, Any]:
    """Dispatch to the family-specific check.

    The runner uses this to compute the deterministic op-validity bits
    alongside the LLM judge's verdict. Disagreement between the two is
    surfaced in the joined results CSV.
    """
    fn = CHECK_BY_FAMILY.get(family)
    if fn is None:
        raise ValueError(f"unknown family {family!r}")
    return fn(generator_output, payload, op_validity_gradable)

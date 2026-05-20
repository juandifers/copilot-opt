"""Deterministic intent classification.

Given the prompt text and family, decide which `Intent` (from
product.copilot.contracts) the question maps to. No model calls. Run 1
shows that the four claim families plus the perturbation context are
already enough to distinguish the 11 intents in the contract.
"""
from __future__ import annotations

import re
from typing import Optional


_COMPARATIVE_TOKENS = (
    "changed",
    "change",
    "actually change",
    "still",
    "compared",
    "different",
)
_COMPARATIVE_REGEX = re.compile(r"\b(fewer|more|less)\s+\w+\s+than\b")
_NEW_ORDER_TOKENS = ("new customer", "new order", "added customer")

# full_route_listing matches questions that ask for the full roster of
# customers per route/vehicle (not a single-customer membership lookup).
# Detection must run BEFORE _is_about_new_customer_assignment because
# wording like "List all the customers assigned to each route after the
# new orders came in" would otherwise match the new-customer heuristic
# on the "new orders"+"assigned" tokens.
_FULL_ROUTE_LISTING_PHRASES = (
    "each route",
    "each vehicle",
    "per route",
    "per vehicle",
    "customers on each",
    "customers assigned to each",
    "customers per",
    "route roster",
    "rosters per",
    "list the customers",
    "list all the customers",
    "list all customers",
    "show customers per",
    "customers in each",
)


def _is_full_route_listing(lowered: str) -> bool:
    return any(phrase in lowered for phrase in _FULL_ROUTE_LISTING_PHRASES)
_REFUSAL_PHRASES = (
    "data does not contain",
    "cannot answer",
    "insufficient",
    "not provided",
    "do not have",
)


def _has_specific_route_number(lowered: str) -> bool:
    return re.search(r"\broute\s+\d+\b", lowered) is not None


def _has_specific_customer_number(lowered: str) -> bool:
    return re.search(r"\bcustomer\s+\d+\b", lowered) is not None


def _is_about_new_customer_assignment(lowered: str) -> bool:
    """The question subject is the new customer's assignment, not a
    specific entity that the new customer happens to interact with."""
    if not any(t in lowered for t in _NEW_ORDER_TOKENS):
        return False
    # Subject-test: a specific route/customer number, or "the driver",
    # means the question is about that entity, not the new customer.
    if _has_specific_route_number(lowered) or _has_specific_customer_number(lowered):
        return False
    if "the driver" in lowered:
        return False
    # Now check that the question asks where the new customer landed.
    return any(
        token in lowered
        for token in ("which route", "what route", "where", "assigned", "end up", "did they")
    )


def _looks_like_refusal(generator_record: Optional[dict]) -> bool:
    if not generator_record:
        return False
    so = generator_record.get("structured_output") or {}
    text = (so.get("answer_text") or generator_record.get("answer_text") or "").lower()
    return any(phrase in text for phrase in _REFUSAL_PHRASES)


def infer_intent(
    prompt_text: str,
    family: str,
    generator_record: Optional[dict] = None,
) -> str:
    """Classify the prompt into one of the contract `Intent` strings."""
    lowered = (prompt_text or "").lower()
    fam = (family or "").upper()
    is_comparative = (
        any(token in lowered for token in _COMPARATIVE_TOKENS)
        or _COMPARATIVE_REGEX.search(lowered) is not None
    )

    # full_route_listing: per-route roster questions ("list the customers
    # on each route", "customers per vehicle"). Must beat the new-customer
    # heuristic, which would otherwise capture roster questions that
    # happen to mention "after the new orders came in".
    if _is_full_route_listing(lowered):
        return "full_route_listing"

    # New-customer-assignment is family-agnostic but only triggers when
    # the question subject is the new customer itself.
    if _is_about_new_customer_assignment(lowered):
        return "new_customer_assignment"

    if fam == "OBJ":
        if is_comparative:
            return "objective_delta"
        return "objective_value"

    if fam in ("PLAN_VALIDITY", "PV"):
        return "feasibility_status"

    if fam == "STRUCT":
        if "same route" in lowered:
            return "same_route_boolean"
        if is_comparative:
            return "before_after_comparison"
        if any(
            token in lowered
            for token in (
                "number of vehicles",
                "vehicles needed",
                "route count",
                "how many routes",
                "how many vehicles",
                "how many trucks",
            )
        ):
            return "route_count"
        if (
            "which route" in lowered
            or "what route" in lowered
            or _has_specific_customer_number(lowered)
        ):
            return "single_customer_route_membership"
        return "unknown"

    if fam == "SCHEDULE":
        # Customer-arrival check first: a question about a specific
        # customer's arrival time always wins over route-end-time.
        if any(
            token in lowered
            for token in ("when does the driver reach", "when does the driver get to", "arrive at customer", "reach customer", "get to customer")
        ):
            return "customer_arrival"
        if any(token in lowered for token in ("wrap up", "wraps up", "end time", "finish", "complete")) and "route" in lowered:
            return "route_end_time"
        if any(token in lowered for token in ("late", "delivery window", "on time", "delayed", "lateness", "miss")):
            return "lateness_summary"
        if is_comparative:
            return "before_after_comparison"
        # Fallback for "when does X reach Y" style without depot mention
        if "when does" in lowered and _has_specific_customer_number(lowered):
            return "customer_arrival"
        return "unknown"

    if _looks_like_refusal(generator_record):
        return "refusal_or_insufficient_payload"

    return "unknown"

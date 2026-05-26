"""Shared entity-bound intent constants.

These frozensets enumerate the intents whose answerability depends on
a specific customer or route named in the prompt. Previously duplicated
across answerability, evidence, and refusal_policy; centralized here so
amendments that widen the entity surface only touch one module.
"""
from __future__ import annotations


CUSTOMER_BOUND_INTENTS: frozenset[str] = frozenset({
    "customer_arrival",
    "single_customer_route_membership",
    "same_route_boolean",
})

ROUTE_BOUND_INTENTS: frozenset[str] = frozenset({"route_end_time"})


__all__ = ["CUSTOMER_BOUND_INTENTS", "ROUTE_BOUND_INTENTS"]

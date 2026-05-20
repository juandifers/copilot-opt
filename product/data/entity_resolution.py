"""Entity-presence helpers used by the false-premise extension.

The answerability and refusal layers both need to know whether a prompt
references a customer or a route that does not exist in the augmented
payload. These checks are pure functions over (payload, prompt_text) so
they can be invoked from both layers without coupling them.

Display convention: user-facing route numbers are 1-indexed; the
payload stores route_idx as 0-indexed. ``Route 1`` in a prompt resolves
to ``route_idx=0`` in the payload.
"""
from __future__ import annotations

import re
from typing import Optional


_CUSTOMER_RE = re.compile(r"\bcustomer\s+(\d+)", re.IGNORECASE)
_ROUTE_RE = re.compile(r"\broute\s+(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


def _coerce_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def available_customer_ids(payload: Optional[dict]) -> set[int]:
    """Customer IDs visible in any payload region the contract uses."""
    if not payload:
        return set()
    out: set[int] = set()
    for r in payload.get("routes") or []:
        if not isinstance(r, dict):
            continue
        for cid in r.get("customer_ids") or []:
            i = _coerce_int(cid)
            if i is not None:
                out.add(i)
    for c in payload.get("customer_schedule") or []:
        if not isinstance(c, dict):
            continue
        i = _coerce_int(c.get("customer_id"))
        if i is not None:
            out.add(i)
    for key in ("late_customer_ids", "new_customer_ids", "unserved_customer_ids"):
        for cid in payload.get(key) or []:
            i = _coerce_int(cid)
            if i is not None:
                out.add(i)
    return out


def prompt_customer_ids(prompt_text: str) -> set[int]:
    return {int(m) for m in _CUSTOMER_RE.findall(prompt_text or "")}


def prompt_references_unknown_customer(
    payload: Optional[dict], prompt_text: str
) -> bool:
    """True iff the prompt names ``customer N`` for an N not in the payload.

    Returns False if the prompt names no customer at all — the absence
    of a reference is not a false premise."""
    cids = prompt_customer_ids(prompt_text)
    if not cids:
        return False
    available = available_customer_ids(payload)
    return bool(cids - available)


def unknown_customer_ids_from_prompt(
    payload: Optional[dict], prompt_text: str
) -> set[int]:
    cids = prompt_customer_ids(prompt_text)
    if not cids:
        return set()
    return cids - available_customer_ids(payload)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def available_route_idxs(payload: Optional[dict]) -> set[int]:
    """route_idx values present in any route-bearing payload region."""
    if not payload:
        return set()
    out: set[int] = set()
    for region in ("routes", "route_end_times"):
        for r in payload.get(region) or []:
            if not isinstance(r, dict):
                continue
            i = _coerce_int(r.get("route_idx"))
            if i is not None:
                out.add(i)
    return out


def available_display_route_numbers(payload: Optional[dict]) -> set[int]:
    """User-facing route numbers (route_idx + 1) present in the payload."""
    return {idx + 1 for idx in available_route_idxs(payload)}


def prompt_route_numbers(prompt_text: str) -> set[int]:
    return {int(m) for m in _ROUTE_RE.findall(prompt_text or "")}


def prompt_references_unknown_route(
    payload: Optional[dict], prompt_text: str
) -> bool:
    nums = prompt_route_numbers(prompt_text)
    if not nums:
        return False
    return bool(nums - available_display_route_numbers(payload))


def unknown_route_numbers_from_prompt(
    payload: Optional[dict], prompt_text: str
) -> set[int]:
    nums = prompt_route_numbers(prompt_text)
    if not nums:
        return set()
    return nums - available_display_route_numbers(payload)


# ---------------------------------------------------------------------------
# Comparison referents (OBJ delta)
# ---------------------------------------------------------------------------


# Phrases an operator might use to compare against something other than
# the pre-perturbation baseline that baseline_objective carries (per
# experiment/configs/payload_schemas_rationale.md:75). When any of these
# appear in an OBJ delta prompt, the contract must surface that the
# named referent does not match baseline_objective and that grounding it
# would require reference_solution.objective.
_AMBIGUOUS_REFERENT_PATTERNS: tuple = (
    re.compile(r"\bfull\s+re-?solve\b", re.IGNORECASE),
    re.compile(r"\bre-?run\s+from\s+scratch\b", re.IGNORECASE),
    re.compile(r"\bre-?solve\s+from\s+scratch\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+scratch\b", re.IGNORECASE),
    re.compile(r"\boptim(?:um|al)\b", re.IGNORECASE),
    re.compile(r"\breference\s+solution\b", re.IGNORECASE),
    re.compile(r"\bstronger\s+solver\b", re.IGNORECASE),
)


def prompt_has_ambiguous_comparison_referent(prompt_text: str) -> bool:
    """True iff the prompt names a comparator that baseline_objective
    does not describe (e.g. ``a full re-solve``, ``the optimum``)."""
    if not prompt_text:
        return False
    return any(p.search(prompt_text) for p in _AMBIGUOUS_REFERENT_PATTERNS)

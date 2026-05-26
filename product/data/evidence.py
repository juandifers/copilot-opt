"""Evidence extraction from augmented payloads.

For each intent, surface the payload field(s) that ground the answer
(or absence thereof). Also provides `field_path_exists` and
`get_nested_field` helpers used by the answerability layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from product.copilot.contracts import EvidenceItem, VisualAction
from product.data import entity_resolution
from product.data.entity_intents import (
    CUSTOMER_BOUND_INTENTS,
    ROUTE_BOUND_INTENTS,
)


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


def _evidence_before_after_comparison(payload: dict) -> list[EvidenceItem]:
    """Surface diff fields when the Tier 2 baseline_solution + diff are present.

    Returns ``[]`` if the payload lacks diff data — the answerability layer
    will report not_answerable and the standard refusal path runs.
    """
    diff = payload.get("diff") if isinstance(payload, dict) else None
    if not isinstance(diff, dict):
        return []
    items: list[EvidenceItem] = []

    # OBJ-family diff: diff.objective.delta_absolute / delta_percent
    obj = diff.get("objective")
    if isinstance(obj, dict):
        if "delta_absolute" in obj:
            items.append(
                EvidenceItem(
                    field_path="diff.objective.delta_absolute",
                    value=obj["delta_absolute"],
                    supports="absolute objective change",
                    display_label="objective delta",
                )
            )
        if "delta_percent" in obj:
            items.append(
                EvidenceItem(
                    field_path="diff.objective.delta_percent",
                    value=obj["delta_percent"],
                    supports="percent objective change",
                    display_label="objective delta %",
                )
            )

    # PV-family diff: diff.feasibility.became_infeasible / became_feasible
    pv = diff.get("feasibility")
    if isinstance(pv, dict):
        for key in ("became_infeasible", "became_feasible"):
            if key in pv:
                items.append(
                    EvidenceItem(
                        field_path=f"diff.feasibility.{key}",
                        value=pv[key],
                        supports=f"feasibility transition: {key}",
                    )
                )

    # STRUCT-family diff: diff.routes.{added, removed, modified}
    routes = diff.get("routes")
    if isinstance(routes, dict):
        for key in ("added", "removed"):
            val = routes.get(key)
            if isinstance(val, list):
                items.append(
                    EvidenceItem(
                        field_path=f"diff.routes.{key}",
                        value=val,
                        supports=f"routes {key} relative to baseline",
                    )
                )
        modified = routes.get("modified")
        if isinstance(modified, list) and modified:
            for entry in modified:
                if not isinstance(entry, dict):
                    continue
                ridx = entry.get("route_idx")
                items.append(
                    EvidenceItem(
                        field_path=f"diff.routes.modified[route_idx={ridx}].customers_added",
                        value=entry.get("customers_added") or [],
                        supports=f"customers added to route_idx={ridx}",
                    )
                )
                items.append(
                    EvidenceItem(
                        field_path=f"diff.routes.modified[route_idx={ridx}].customers_removed",
                        value=entry.get("customers_removed") or [],
                        supports=f"customers removed from route_idx={ridx}",
                    )
                )

    # SCHEDULE-family diff: diff.schedule.{new_late_customer_ids, no_longer_late_customer_ids}
    sched = diff.get("schedule")
    if isinstance(sched, dict):
        for key in ("new_late_customer_ids", "no_longer_late_customer_ids"):
            val = sched.get(key)
            if isinstance(val, list):
                items.append(
                    EvidenceItem(
                        field_path=f"diff.schedule.{key}",
                        value=val,
                        supports=f"customer set: {key}",
                    )
                )

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
# Within-family aspectual fallback (lateness pilot)
#
# Activated only when intent classification returned ``unknown`` and the
# payload + prompt afford an aspect-grounded answer. The dispatcher never
# generates values — it surfaces existing payload field paths using the
# same EvidenceItem contract the rest of the module uses.
# ---------------------------------------------------------------------------


# Order matters — first match wins.
_ASPECT_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    (
        "lateness",
        re.compile(
            r"\b(late|lateness|delay(?:ed)?|behind(?:\s+schedule)?|"
            r"miss(?:ed|ing)?\s+(?:the\s+)?(?:deadline|time\s+window))\b"
        ),
    ),
    (
        "timing",
        re.compile(
            r"\b(arriv(?:e|al|ing)|when\s+does|what\s+time|"
            r"schedule(?:d)?|completion|finish(?:es)?|done)\b"
        ),
    ),
]

# Cap to keep an unconstrained "show me everything" query from emitting
# thousands of evidence items.
_ASPECT_EVIDENCE_CAP = 25


# ---------------------------------------------------------------------------
# B1 — Ranking aspect (A-006)
#
# Detects "top/worst/best N <target> by <dimension>" style operator queries
# and dispatches against payload fields. Runs BEFORE the lateness/timing
# aspect dispatch when intent == "unknown", so "worst route" wins over the
# bare "late" token match.
# ---------------------------------------------------------------------------

_RANKING_SUPERLATIVES = re.compile(
    r"\b(worst|best|most|least|biggest|smallest|longest|shortest|"
    r"tightest|widest|heaviest|lightest|top|bottom|rank(?:ing)?|"
    r"closest|furthest|farthest|fastest|slowest|highest|lowest)\b"
)
_RANKING_TARGETS = re.compile(
    r"\b(routes?|customers?|vehicles?|deliver(?:y|ies)|stops?|drivers?|"
    # Operator-shaped abstract targets: a dispatcher saying "biggest
    # problems" or "top 3 things" wants a ranked list, even if the
    # noun is generic. These default to lateness ranking via the
    # default-dimension table and surface an ambiguity_note.
    r"problems?|issues?|things?|items?|points?|risks?)\b"
)
# Dimension keywords (explicit framing). When absent, the dimension is
# inferred from the superlative + target and an ambiguity_note is set.
_RANKING_DIMENSION_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("lateness",      re.compile(r"\b(lateness|late|delay(?:ed)?|behind)\b")),
    ("end_time",      re.compile(r"\b(duration|end\s*time|finish(?:ing)?|wrap[\s-]*up|long(?:est)?)\b")),
    ("load",          re.compile(r"\b(load(?:ed)?|capacity|heaviest|lightest|stops?(?:\s+per\s+route)?|customers?\s+per\s+route)\b")),
    ("slack",         re.compile(r"\b(slack|headroom|buffer)\b")),
    ("window_margin", re.compile(r"\b(margin|window\s+edge|edge\s+of\s+(?:its|the|their)\s+window|cutting\s+it\s+close)\b")),
    ("window_width",  re.compile(r"\b(tight(?:est)?\s+window|small(?:est)?\s+window|narrow(?:est)?\s+window|window\s+width)\b")),
]
# Default-dimension inference when the dimension is implicit. "worst route"
# defaults to lateness (most-common operator intent); "worst customer" same.
_RANKING_DEFAULT_DIMENSION_FOR_TARGET = {
    "route":    "lateness",
    "customer": "lateness",
}
_RANKING_TARGET_NORMALIZE = {
    "route": "route", "routes": "route",
    "vehicle": "route", "vehicles": "route",
    "customer": "customer", "customers": "customer",
    "delivery": "customer", "deliveries": "customer",
    "stop": "customer", "stops": "customer",
    "driver": "route", "drivers": "route",
    # Abstract operator targets normalize to customer-lateness ranking
    # (the "where's the pain" framing). Route-level surfaces are still
    # available via explicit "routes" / "vehicles" phrasings.
    "problem": "customer", "problems": "customer",
    "issue": "customer", "issues": "customer",
    "thing": "customer", "things": "customer",
    "item": "customer", "items": "customer",
    "point": "customer", "points": "customer",
    "risk": "customer", "risks": "customer",
}

# Top-K parsing: "top N", "first N", "N worst/best/most/least".
_RANKING_TOPK = re.compile(
    r"\btop\s+(\d+)\b|\bfirst\s+(\d+)\b|\b(\d+)\s+(?:worst|best|most|least)\b"
)
_RANKING_DEFAULT_TOPK = 3
_RANKING_MAX_TOPK = 10

# Family / dimension compatibility. SCHEDULE payloads carry the timing
# fields needed for every dimension; STRUCT carries only routes[].customer_ids
# which supports load; OBJ and PV carry only aggregates.
_RANKING_COMPAT = {
    "SCHEDULE":      {"lateness", "end_time", "load", "slack",
                      "window_margin", "window_width"},
    "STRUCT":        {"load"},
    "OBJ":           set(),
    "PLAN_VALIDITY": set(),
    "PV":            set(),
}


@dataclass(frozen=True)
class RankingAlternative:
    """Structured rephrasing suggestion for an ambiguous ranking prompt.

    Surfaced by R3 (A-008.5) when the prompt has a bare superlative
    without an explicit dimension keyword. ``dimension`` is the same
    canonical id used in ``_RANKING_COMPAT``; ``label`` is the
    human-facing rendering; ``example_phrasing`` is an operator-style
    phrasing the user can re-ask with to land on this dimension.
    """

    dimension: str
    label: str
    example_phrasing: str


# Per-(target, dimension) example phrasings for the R3 alternatives block.
# Only populated for dimensions compatible with the SCHEDULE family — R3
# activates on ambiguous SCHEDULE-shaped prompts; STRUCT/OBJ/PV either
# have a single compatible dimension or no ranking dimensions at all.
_RANKING_ALTERNATIVES_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("route", "lateness"):
        ("lateness", "the routes with the most late deliveries"),
    ("route", "end_time"):
        ("end time", "the longest routes by end time"),
    ("route", "load"):
        ("load", "the heaviest routes (most customers)"),
    ("route", "slack"):
        ("slack", "the routes with the most slack"),
    ("route", "window_margin"):
        ("window margin", "the routes tightest to window edges"),
    ("route", "window_width"):
        ("window width", "the routes with the narrowest windows"),
    ("customer", "lateness"):
        ("lateness", "the latest customers"),
    ("customer", "end_time"):
        ("end time", "the customers served latest"),
    ("customer", "window_margin"):
        ("window margin", "the customers closest to their window edge"),
    ("customer", "window_width"):
        ("window width", "the customers with the narrowest windows"),
}


# R3 ambiguity rule (A-008.5) is keyword-based per spec — independent of
# the legacy `_RANKING_DIMENSION_PATTERNS` adjacent-phrase detector. Any
# of these stems anywhere in the prompt disqualifies the prompt from
# being treated as "ambiguous" for the R3 alternatives surface.
#   late      → late, lateness, latest, lately
#   long      → long, longer, longest
#   heav      → heavy, heaviest, heavier
#   tight     → tight, tighter, tightest
#   slack     → slack
#   window    → window, windows
#   load      → load, loaded, loads
#   duration  → duration
#   fast      → fast, faster, fastest
#   slow      → slow, slower, slowest
#   close     → close, closer, closest
#   far       → far, farther, furthest
#   narrow    → narrow, narrower, narrowest
#   wide      → wide, wider, widest
_R3_DIMENSION_KEYWORDS_RE = re.compile(
    r"\b(late|long|heav|tight|slack|window|load|duration|"
    r"fast|slow|close|far|narrow|wide)",
    re.IGNORECASE,
)


_R3_DISABLE_ENV = "COPILOT_DISABLE_RANKING_ALTERNATIVES"


def _r3_alternatives_enabled() -> bool:
    """Return True iff R3 alternative-dimension population is active."""
    import os as _os
    val = _os.environ.get(_R3_DISABLE_ENV, "").strip().lower()
    return val not in ("1", "true", "yes", "on")


def _build_ranking_alternatives(
    target: str,
    default_dimension: str,
    family: str,
) -> list[RankingAlternative]:
    """Construct the alternative-dimension list for an ambiguous ranking.

    Skips the default dimension (already selected) and any dimension not
    compatible with the declared family. Returns an empty list when R3 is
    disabled by env var or when no alternatives apply (e.g. STRUCT with
    only ``load`` available, OBJ/PV with no per-entity dimensions).
    """
    if not _r3_alternatives_enabled():
        return []
    fam = (family or "").upper()
    compat_set = _RANKING_COMPAT.get(fam, set())
    if not compat_set:
        return []
    out: list[RankingAlternative] = []
    for (tgt, dim), (label, phrasing) in _RANKING_ALTERNATIVES_TABLE.items():
        if tgt != target:
            continue
        if dim == default_dimension:
            continue
        if dim not in compat_set:
            continue
        out.append(RankingAlternative(
            dimension=dim, label=label, example_phrasing=phrasing
        ))
    return out


@dataclass
class RankingSpec:
    """Resolved ranking parameters for a prompt.

    The spec is family-aware: ``family_compatible`` is False when the
    declared family cannot answer the requested ranking (e.g. an OBJ
    payload doesn't carry per-route timing). The evidence layer returns
    no items in that case; the verbalizer produces a family-aware
    refusal.

    R3 (A-008.5): when the prompt is AMBIGUOUS — bare superlative without
    an explicit dimension keyword — ``alternatives`` carries structured
    rephrasings the operator can re-ask with to land on a different
    dimension. ``alternatives`` stays empty on UNAMBIGUOUS prompts so the
    byte-level output is identical to the pre-A-008.5 behaviour.
    """

    target: str
    dimension: str
    top_k: int
    family: str
    family_compatible: bool
    ambiguity_note: Optional[str] = None
    alternatives: list[RankingAlternative] = field(default_factory=list)


def derive_ranking_spec(prompt: str, family: str) -> Optional[RankingSpec]:
    """Return a `RankingSpec` if the prompt is a ranking query, else None."""
    if not prompt:
        return None
    p = prompt.lower()
    sup = _RANKING_SUPERLATIVES.search(p)
    tgt = _RANKING_TARGETS.search(p)
    if not (sup and tgt):
        return None
    target = _RANKING_TARGET_NORMALIZE.get(tgt.group(1), "route")

    # Dimension: explicit > inferred
    dimension: Optional[str] = None
    for dim, pattern in _RANKING_DIMENSION_PATTERNS:
        if pattern.search(p):
            dimension = dim
            break
    ambiguity_note: Optional[str] = None
    if dimension is None:
        dimension = _RANKING_DEFAULT_DIMENSION_FOR_TARGET.get(target, "lateness")
        ambiguity_note = (
            f"interpreted '{sup.group(1)}' as '{dimension}' — say "
            f"'longest', 'heaviest', or 'tightest window' for a different ranking"
        )

    # Top-K
    top_k = _RANKING_DEFAULT_TOPK
    m_k = _RANKING_TOPK.search(p)
    if m_k:
        for g in m_k.groups():
            if g:
                try:
                    top_k = int(g)
                except (TypeError, ValueError):
                    top_k = _RANKING_DEFAULT_TOPK
                break
    top_k = max(1, min(_RANKING_MAX_TOPK, top_k))

    fam = (family or "").upper()
    compat_set = _RANKING_COMPAT.get(fam, set())
    family_compatible = dimension in compat_set

    # R3 (A-008.5): populate structured alternative-dimension suggestions
    # when the prompt is AMBIGUOUS per the keyword rule (no dimension stem
    # anywhere in the prompt) AND the target is route or customer AND the
    # family carries enough dimensions to make alternatives meaningful.
    # Independent of the legacy `_RANKING_DIMENSION_PATTERNS` detector —
    # the keyword rule lives entirely on the R3 side so edge cases in the
    # adjacent-phrase patterns (e.g. "tightest windows" missing the
    # window_width regex) don't spuriously populate alternatives.
    alternatives: list[RankingAlternative] = []
    r3_ambiguous = (
        _R3_DIMENSION_KEYWORDS_RE.search(p) is None
        and target in ("route", "customer")
        and family_compatible
    )
    if r3_ambiguous:
        alternatives = _build_ranking_alternatives(
            target=target, default_dimension=dimension, family=fam,
        )

    return RankingSpec(
        target=target,
        dimension=dimension,
        top_k=top_k,
        family=fam,
        family_compatible=family_compatible,
        ambiguity_note=ambiguity_note,
        alternatives=alternatives,
    )


def _route_label_for_idx(payload: dict, route_idx: int) -> str:
    for r in payload.get("route_end_times") or []:
        if isinstance(r, dict) and int(r.get("route_idx", -1)) == route_idx:
            return r.get("route_label") or f"Route {route_idx + 1}"
    for r in payload.get("routes") or []:
        if isinstance(r, dict) and int(r.get("route_idx", -1)) == route_idx:
            return r.get("route_label") or f"Route {route_idx + 1}"
    return f"Route {route_idx + 1}"


def _evidence_aspectual_ranking(
    payload: dict,
    spec: RankingSpec,
) -> list[EvidenceItem]:
    """Aspectual evidence for the ranking aspect.

    Returns up to ``spec.top_k`` items, one per ranked entity. Each item
    carries a field_path that traces to the actual payload row used in
    the aggregation. When ``spec.family_compatible`` is False, returns
    an empty list — the verbalizer reads ``RankingSpec`` directly to
    produce a family-aware refusal.

    Zero-result rankings (e.g. lateness ranking when no customer is
    late) return an empty list with a dedicated rationale carried in
    the spec; the verbalizer renders the "nothing to rank" prose.
    """
    if not spec.family_compatible:
        return []

    sched = payload.get("customer_schedule") or []
    retimes = payload.get("route_end_times") or []
    routes = payload.get("routes") or []

    items: list[EvidenceItem] = []

    if spec.target == "route" and spec.dimension == "lateness":
        # Aggregate lateness per route from customer_schedule
        agg: dict[int, float] = {}
        for row in sched:
            if not isinstance(row, dict):
                continue
            ridx = row.get("route_idx")
            lm = row.get("lateness_minutes")
            if ridx is None or lm is None:
                continue
            agg[int(ridx)] = agg.get(int(ridx), 0.0) + float(lm)
        # Filter zero-aggregate routes for lateness ranking
        ranked = sorted(((idx, total) for idx, total in agg.items() if total > 0),
                        key=lambda kv: kv[1], reverse=True)
        if not ranked and "n_late_customers" in payload:
            # Zero-result branch: surface n_late_customers=0 so the
            # operator gets a grounded "nothing to rank" answer rather
            # than a generic refusal.
            items.append(
                EvidenceItem(
                    field_path="n_late_customers",
                    value=payload.get("n_late_customers"),
                    supports="no routes have any lateness to rank",
                    display_label="late-customer count",
                )
            )
            return items
        for idx, total in ranked[: spec.top_k]:
            label = _route_label_for_idx(payload, idx)
            items.append(
                EvidenceItem(
                    field_path=f"customer_schedule[route_idx={idx}].lateness_minutes",
                    value=round(float(total), 2),
                    supports=f"total lateness on {label}",
                    display_label=label,
                )
            )

    elif spec.target == "route" and spec.dimension == "end_time":
        candidates = []
        for r in retimes:
            if not isinstance(r, dict):
                continue
            et = r.get("end_time")
            if et is None:
                continue
            candidates.append((int(r.get("route_idx", -1)), float(et), r))
        ranked = sorted(candidates, key=lambda t: t[1], reverse=True)
        for idx, et, _row in ranked[: spec.top_k]:
            label = _route_label_for_idx(payload, idx)
            items.append(
                EvidenceItem(
                    field_path=f"route_end_times[route_idx={idx}].end_time",
                    value=round(et, 2),
                    supports=f"end time of {label}",
                    display_label=label,
                )
            )

    elif spec.target == "route" and spec.dimension == "load":
        # SCHEDULE: count customer_schedule rows per route_idx
        # STRUCT: len(routes[route_idx].customer_ids)
        agg: dict[int, int] = {}
        if routes:
            for r in routes:
                if not isinstance(r, dict):
                    continue
                ridx = r.get("route_idx")
                cids = r.get("customer_ids") or []
                if ridx is None:
                    continue
                agg[int(ridx)] = len(cids)
        else:
            for row in sched:
                if not isinstance(row, dict):
                    continue
                ridx = row.get("route_idx")
                if ridx is None:
                    continue
                agg[int(ridx)] = agg.get(int(ridx), 0) + 1
        ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        for idx, count in ranked[: spec.top_k]:
            label = _route_label_for_idx(payload, idx)
            if routes:
                fp = f"routes[route_idx={idx}].customer_ids"
            else:
                fp = f"customer_schedule[route_idx={idx}].count"
            items.append(
                EvidenceItem(
                    field_path=fp,
                    value=count,
                    supports=f"customer count on {label}",
                    display_label=label,
                )
            )

    elif spec.target == "route" and spec.dimension == "slack":
        # Slack proxy: descending by end_time (less slack = later finish).
        # Without depot late-window in payload we cannot compute true
        # margin; surface end_time as the slack proxy and note in the
        # supports string.
        candidates = []
        for r in retimes:
            if not isinstance(r, dict):
                continue
            et = r.get("end_time")
            if et is None:
                continue
            candidates.append((int(r.get("route_idx", -1)), float(et), r))
        ranked = sorted(candidates, key=lambda t: t[1], reverse=True)
        for idx, et, _row in ranked[: spec.top_k]:
            label = _route_label_for_idx(payload, idx)
            items.append(
                EvidenceItem(
                    field_path=f"route_end_times[route_idx={idx}].end_time",
                    value=round(et, 2),
                    supports=f"end time of {label} (tightest slack proxy)",
                    display_label=label,
                )
            )

    elif spec.target == "customer" and spec.dimension == "lateness":
        candidates = []
        for row in sched:
            if not isinstance(row, dict):
                continue
            lm = row.get("lateness_minutes")
            cid = row.get("customer_id")
            if cid is None or lm is None or float(lm) <= 0:
                continue
            candidates.append((int(cid), float(lm), row))
        ranked = sorted(candidates, key=lambda t: t[1], reverse=True)
        if not ranked and "n_late_customers" in payload:
            items.append(
                EvidenceItem(
                    field_path="n_late_customers",
                    value=payload.get("n_late_customers"),
                    supports="no customers are late",
                    display_label="late-customer count",
                )
            )
            return items
        for cid, lm, row in ranked[: spec.top_k]:
            label = row.get("route_label") or _route_label_for_idx(payload, row.get("route_idx", -1))
            items.append(
                EvidenceItem(
                    field_path=f"customer_schedule[customer_id={cid}].lateness_minutes",
                    value=round(lm, 2),
                    supports=f"lateness for customer {cid} on {label}",
                    display_label=f"Customer {cid} on {label}",
                )
            )

    elif spec.target == "customer" and spec.dimension == "window_margin":
        # margin = tw_late - arrival (smaller = tighter)
        candidates = []
        for row in sched:
            if not isinstance(row, dict):
                continue
            arr = row.get("arrival")
            twl = row.get("tw_late")
            cid = row.get("customer_id")
            if cid is None or arr is None or twl is None:
                continue
            margin = float(twl) - float(arr)
            candidates.append((int(cid), margin, row))
        ranked = sorted(candidates, key=lambda t: t[1])  # ascending — tightest first
        for cid, margin, row in ranked[: spec.top_k]:
            label = row.get("route_label") or _route_label_for_idx(payload, row.get("route_idx", -1))
            items.append(
                EvidenceItem(
                    field_path=f"customer_schedule[customer_id={cid}].arrival",
                    value=round(margin, 2),
                    supports=f"window margin (tw_late − arrival) for customer {cid} on {label}",
                    display_label=f"Customer {cid} on {label}",
                )
            )

    elif spec.target == "customer" and spec.dimension == "window_width":
        # width = tw_late - tw_early (smaller = tighter window)
        candidates = []
        for row in sched:
            if not isinstance(row, dict):
                continue
            twe = row.get("tw_early")
            twl = row.get("tw_late")
            cid = row.get("customer_id")
            if cid is None or twe is None or twl is None:
                continue
            width = float(twl) - float(twe)
            candidates.append((int(cid), width, row))
        ranked = sorted(candidates, key=lambda t: t[1])
        for cid, width, row in ranked[: spec.top_k]:
            label = row.get("route_label") or _route_label_for_idx(payload, row.get("route_idx", -1))
            items.append(
                EvidenceItem(
                    field_path=f"customer_schedule[customer_id={cid}].tw_late",
                    value=round(width, 2),
                    supports=f"window width (tw_late − tw_early) for customer {cid} on {label}",
                    display_label=f"Customer {cid} on {label}",
                )
            )

    return items[: spec.top_k]


def is_schedule_payload(payload: Optional[dict]) -> bool:
    """True iff the payload carries SCHEDULE-family columns."""
    if not isinstance(payload, dict):
        return False
    return (
        "customer_schedule" in payload
        or "route_end_times" in payload
        or "n_late_customers" in payload
    )


def derive_aspect(prompt: str, has_entities: bool = False) -> Optional[str]:
    """Return the matching aspect for the prompt, or None.

    When no aspect keyword matches but the prompt has resolved entities,
    default to ``timing`` (the broader of the two pilot aspects). When no
    aspect matches and no entities are present, return None — the existing
    refusal path handles it.
    """
    p = (prompt or "").lower()
    for aspect, pattern in _ASPECT_PATTERNS:
        if pattern.search(p):
            return aspect
    if has_entities:
        return "timing"
    return None


_ROUTE_LABEL_DIGITS = re.compile(r"(\d+)")


def _parse_route_label_to_display_number(label: str) -> Optional[int]:
    """Extract a 1-based display route number from an LLM-emitted label.

    The LLM may emit ``"3"``, ``"Route 3"``, or the augmented ``"Route 3"``
    label. We pull the first integer; the caller validates it against the
    canonical set.
    """
    if not label:
        return None
    m = _ROUTE_LABEL_DIGITS.search(str(label))
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _resolve_aspect_entities(
    query_frame_entities: Any,
    payload: dict,
    prompt_text: str,
) -> tuple[set[int], set[int]]:
    """Resolve customer ids + route_idx set from the QueryFrame, falling
    back to prompt-regex parsing. Both outputs are pre-filtered against
    the canonical entity sets — unknown entities are dropped so the
    aspectual layer can never surface evidence for an absent entity.
    """
    available_customers = entity_resolution.available_customer_ids(payload)
    available_displays = entity_resolution.available_display_route_numbers(payload)

    cust_candidates: set[int] = set()
    route_candidates: set[int] = set()

    if query_frame_entities is not None:
        for cid in getattr(query_frame_entities, "customer_ids", None) or []:
            try:
                cust_candidates.add(int(cid))
            except (TypeError, ValueError):
                continue
        for label in getattr(query_frame_entities, "route_labels", None) or []:
            num = _parse_route_label_to_display_number(label)
            if num is not None:
                route_candidates.add(num)

    # Prompt-regex fallback so prompts like "how late is customer 5" still
    # resolve when the LLM extractor did not run or returned empty.
    if not cust_candidates:
        cust_candidates.update(entity_resolution.prompt_customer_ids(prompt_text))
    if not route_candidates:
        route_candidates.update(entity_resolution.prompt_route_numbers(prompt_text))

    resolved_cids = cust_candidates & available_customers
    resolved_route_idxs = {n - 1 for n in (route_candidates & available_displays)}
    return resolved_cids, resolved_route_idxs


def _aspect_customer_emit(
    payload: dict, cid: int, fields: tuple[str, ...]
) -> list[EvidenceItem]:
    """Emit per-customer evidence items for the given field names."""
    items: list[EvidenceItem] = []
    for row in payload.get("customer_schedule") or []:
        if not isinstance(row, dict) or int(row.get("customer_id", -1)) != cid:
            continue
        label = _route_label(row)
        for f in fields:
            if f in row:
                items.append(
                    EvidenceItem(
                        field_path=f"customer_schedule[customer_id={cid}].{f}",
                        value=row[f],
                        supports=f"{f} for customer {cid}",
                        display_label=f"Customer {cid} on {label} — {f}",
                    )
                )
        break
    return items


def _evidence_aspectual_lateness(
    payload: dict,
    customer_ids: set[int],
    route_idxs: set[int],
) -> list[EvidenceItem]:
    """Aspectual evidence for lateness on a SCHEDULE payload."""
    fields = ("is_late", "lateness_minutes", "arrival", "tw_late")
    items: list[EvidenceItem] = []
    if customer_ids:
        for cid in sorted(customer_ids):
            items.extend(_aspect_customer_emit(payload, cid, fields))
            if len(items) >= _ASPECT_EVIDENCE_CAP:
                break
        return items[:_ASPECT_EVIDENCE_CAP]

    if route_idxs:
        # Per-route lateness: emit each member customer's lateness fields.
        sched = payload.get("customer_schedule") or []
        for ridx in sorted(route_idxs):
            for row in sched:
                if not isinstance(row, dict):
                    continue
                if int(row.get("route_idx", -1)) != ridx:
                    continue
                cid = int(row.get("customer_id", -1))
                items.extend(_aspect_customer_emit(payload, cid, fields))
                if len(items) >= _ASPECT_EVIDENCE_CAP:
                    return items[:_ASPECT_EVIDENCE_CAP]
        return items[:_ASPECT_EVIDENCE_CAP]

    # No entity scope: lateness-summary + per-customer lateness magnitudes
    if "n_late_customers" in payload:
        items.append(
            EvidenceItem(
                field_path="n_late_customers",
                value=payload["n_late_customers"],
                supports="total late customers",
                display_label="Late count",
            )
        )
    late_ids = payload.get("late_customer_ids")
    if isinstance(late_ids, list):
        items.append(
            EvidenceItem(
                field_path="late_customer_ids",
                value=late_ids,
                supports="customers that arrived after their window",
                display_label="Late customer IDs",
            )
        )
        # Sort late customers by lateness_minutes desc when we can, then
        # emit lateness_minutes per id up to the cap.
        sched_by_cid: dict[int, dict] = {}
        for row in payload.get("customer_schedule") or []:
            if isinstance(row, dict):
                cid = row.get("customer_id")
                if isinstance(cid, int):
                    sched_by_cid[cid] = row
        ranked: list[tuple[float, int]] = []
        for cid_any in late_ids:
            try:
                cid = int(cid_any)
            except (TypeError, ValueError):
                continue
            row = sched_by_cid.get(cid)
            lm = (row or {}).get("lateness_minutes")
            if isinstance(lm, (int, float)):
                ranked.append((float(lm), cid))
        ranked.sort(reverse=True)
        for _lm, cid in ranked:
            row = sched_by_cid.get(cid)
            if row is None:
                continue
            label = _route_label(row)
            items.append(
                EvidenceItem(
                    field_path=f"customer_schedule[customer_id={cid}].lateness_minutes",
                    value=row.get("lateness_minutes"),
                    supports=f"lateness for customer {cid}",
                    display_label=f"Customer {cid} on {label} — lateness_minutes",
                )
            )
            if len(items) >= _ASPECT_EVIDENCE_CAP:
                break
    return items[:_ASPECT_EVIDENCE_CAP]


def _evidence_aspectual_timing(
    payload: dict,
    customer_ids: set[int],
    route_idxs: set[int],
) -> list[EvidenceItem]:
    """Aspectual evidence for timing on a SCHEDULE payload."""
    cust_fields = ("arrival", "start_service", "end_service", "tw_early", "tw_late")
    items: list[EvidenceItem] = []

    if customer_ids:
        for cid in sorted(customer_ids):
            items.extend(_aspect_customer_emit(payload, cid, cust_fields))
            if len(items) >= _ASPECT_EVIDENCE_CAP:
                break
        return items[:_ASPECT_EVIDENCE_CAP]

    if route_idxs:
        # Route-end first, then per-customer arrivals on that route.
        for ridx in sorted(route_idxs):
            for r in payload.get("route_end_times") or []:
                if not isinstance(r, dict) or int(r.get("route_idx", -1)) != ridx:
                    continue
                label = _route_label(r)
                items.append(
                    EvidenceItem(
                        field_path=f"route_end_times[route_idx={ridx}].end_time",
                        value=r.get("end_time"),
                        supports=f"end time of {label}",
                        display_label=label,
                    )
                )
                if r.get("has_time_warp"):
                    items.append(
                        EvidenceItem(
                            field_path=f"route_end_times[route_idx={ridx}].has_time_warp",
                            value=True,
                            supports="route exceeded a time window",
                        )
                    )
                break
            for row in payload.get("customer_schedule") or []:
                if not isinstance(row, dict):
                    continue
                if int(row.get("route_idx", -1)) != ridx:
                    continue
                cid = int(row.get("customer_id", -1))
                if "arrival" in row:
                    label = _route_label(row)
                    items.append(
                        EvidenceItem(
                            field_path=f"customer_schedule[customer_id={cid}].arrival",
                            value=row["arrival"],
                            supports=f"arrival of customer {cid}",
                            display_label=f"Customer {cid} on {label}",
                        )
                    )
                if len(items) >= _ASPECT_EVIDENCE_CAP:
                    return items[:_ASPECT_EVIDENCE_CAP]
        return items[:_ASPECT_EVIDENCE_CAP]

    # No entity scope: enumerate route end-times
    for r in payload.get("route_end_times") or []:
        if not isinstance(r, dict):
            continue
        ridx = r.get("route_idx")
        label = _route_label(r)
        items.append(
            EvidenceItem(
                field_path=f"route_end_times[route_idx={ridx}].end_time",
                value=r.get("end_time"),
                supports=f"end time of {label}",
                display_label=label,
            )
        )
        if len(items) >= _ASPECT_EVIDENCE_CAP:
            break
    return items[:_ASPECT_EVIDENCE_CAP]


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_evidence_items(
    intent: str,
    payload: Optional[dict],
    generator_record: Optional[dict],
    row: Optional[dict] = None,
    query_frame: Optional[Any] = None,
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
    if intent in CUSTOMER_BOUND_INTENTS and entity_resolution.prompt_references_unknown_customer(
        payload, prompt_text
    ):
        return []
    if intent in ROUTE_BOUND_INTENTS and entity_resolution.prompt_references_unknown_route(
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
    if intent == "before_after_comparison":
        return _evidence_before_after_comparison(payload)

    # A-008: evaluation intents — surface one EvidenceItem per
    # threshold check so the verbalizer can render the threshold +
    # observed value side-by-side and the response stays grounded.
    if intent in ("evaluate_plan_acceptability", "evaluate_dimension_acceptability"):
        from product.copilot.evaluation import (
            evaluate_plan,
            evaluate_dimension,
            detect_dimension,
        )
        perturbation_type = (row or {}).get("perturbation_id") or ""
        if intent == "evaluate_dimension_acceptability":
            dim = detect_dimension(prompt_text) or ""
            ev_result = evaluate_dimension(payload, perturbation_type, dim)
        else:
            ev_result = evaluate_plan(payload, perturbation_type)
        items: list[EvidenceItem] = []
        for chk in ev_result.checks:
            metric = chk.threshold.metric
            family = chk.threshold.family
            items.append(
                EvidenceItem(
                    field_path=f"evaluation.{family.lower()}.{metric}",
                    value=chk.observed_value,
                    supports=(
                        f"{metric} check ({chk.threshold.threshold_value}); "
                        f"observed={chk.observed_value}; "
                        f"passes={chk.passes}"
                        + (" [bias_band]" if chk.conservative_bias_applied else "")
                    ),
                    display_label=f"{family} · {metric}",
                )
            )
        return items

    # Aspectual fallback: when intent classification returned "unknown",
    # try ranking dispatch first (B1, A-006) — a "worst route" prompt
    # carries the lateness/late tokens too and would otherwise be eaten
    # by the lateness aspect dispatch. Ranking is family-aware: SCHEDULE
    # supports all dimensions, STRUCT supports `load`, OBJ and PV refuse.
    if intent == "unknown" and payload is not None:
        family_label = ((row or {}).get("family") or "").upper()
        rspec = derive_ranking_spec(prompt_text, family_label)
        if rspec is not None and rspec.family_compatible:
            ranking_items = _evidence_aspectual_ranking(payload, rspec)
            if ranking_items:
                return ranking_items

    # Aspectual fallback (lateness pilot): when intent classification
    # returned "unknown" but the payload is SCHEDULE-shaped and the prompt
    # affords a lateness/timing answer, dispatch on resolved entities.
    # See experiment/AMENDMENTS.md for the locked-spec entry.
    if intent == "unknown" and is_schedule_payload(payload):
        # Mirror the false-premise rule from the entity-bound intents: if
        # the prompt names a customer or route that is not in the
        # canonical set, refuse rather than silently dispatch against a
        # different entity scope. The aspect layer never surfaces evidence
        # for a phantom entity.
        if (
            entity_resolution.prompt_references_unknown_customer(payload, prompt_text)
            or entity_resolution.prompt_references_unknown_route(payload, prompt_text)
        ):
            return []
        qf_entities = getattr(query_frame, "entities", None)
        cust_ids, route_idxs = _resolve_aspect_entities(
            qf_entities, payload, prompt_text
        )
        has_entities = bool(cust_ids or route_idxs)
        aspect = derive_aspect(prompt_text, has_entities=has_entities)
        if aspect == "lateness":
            return _evidence_aspectual_lateness(payload, cust_ids, route_idxs)
        if aspect == "timing":
            return _evidence_aspectual_timing(payload, cust_ids, route_idxs)

    # new_customer_assignment, refusal_or_insufficient_payload:
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

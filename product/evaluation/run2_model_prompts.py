"""Prompt templates for the Run 2 model baselines.

System B — *prompt-only JSON contract emitter*. The model receives the
case prompt text, family, payload condition, a compact payload
projection, and the allowed schema enums. It must emit the contract
JSON directly. There is no deterministic intent classifier,
answerability checker, evidence extractor, warning policy, or refusal
policy on the model side; the prompt has to do all the work.

What this module DOES include in the prompt:
- Allowed intents, answerability statuses, warning codes, next-action
  codes, evidence path families, behavior classes (all from
  `run2_gold_schema.md`).
- The operational conventions a labeller would apply when picking
  labels — display routes are 1-indexed; OBJ vs full re-solve; STRUCT
  membership vs full-roster; false-premise handling; PV missing
  fields.
- A compact payload projection that keeps the fields the model needs
  to ground the answer without ballooning the prompt.

What this module DOES NOT include:
- Gold labels.
- Per-case label rationale.
- Scoring code or its outputs.
- C-current / C-extended results.
- Repository structure beyond the field paths.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from product.evaluation.run2_case_loader import Run2Case


# ---------------------------------------------------------------------------
# Schema-derived enums (kept in sync with run2_gold_schema.md §3 / §4 /
# §5 / §6 / §7). Listed here so the model gets the full enumeration in
# one place; mirrors the LOADER constants in run2_case_loader.py but
# without importing them — the prompt builder is the natural place to
# state what the model is allowed to emit.
# ---------------------------------------------------------------------------

ALLOWED_INTENTS: list[str] = [
    "objective_value",
    "objective_delta",
    "feasibility_status",
    "route_count",
    "single_customer_route_membership",
    "same_route_boolean",
    "route_end_time",
    "customer_arrival",
    "lateness_summary",
    "before_after_comparison",
    "new_customer_assignment",
    "refusal_or_insufficient_payload",
    "unknown",
    # R2-1 extension intent
    "full_route_listing",
]

ALLOWED_ANSWERABILITY: list[str] = [
    "answerable",
    "partially_answerable",
    "not_answerable",
]

ALLOWED_BEHAVIOR_CLASSES: list[str] = [
    "direct_answer",
    "direct_answer_with_warning",
    "partial_answer_with_warning",
    "useful_refusal",
]

ALLOWED_WARNINGS: list[str] = [
    "route_indexing_ambiguity",
    "struct_membership_ambiguity",
    "unsupported_comparison",
    "missing_new_customer_attribution",
    # R2-1 extensions
    "false_premise_detected",
    "comparison_referent_ambiguity",
    "evidence_units_missing",
]

ALLOWED_NEXT_ACTIONS: list[str] = [
    "build_baseline_comparison_payload",
    "expose_new_customer_ids",
    "apply_route_label_augmentation",
    "use_schedule_payload",
    "narrow_question_to_available_field",
    # R2-1 extensions
    "clarify_false_premise",
    "use_validity_payload",
    "expose_reference_solution_objective",
    "expose_units_objective",
]

# Field-family evidence paths the contract recognises (schema §10a).
ALLOWED_EVIDENCE_PATHS: list[str] = [
    "action_objective",
    "units.objective",
    "baseline_objective",
    "objective_delta_absolute",
    "objective_delta_percent",
    "routes[].customer_ids",
    "routes[].route_idx",
    "customer_schedule[].arrival",
    "customer_schedule[].customer_id",
    "route_end_times[].end_time",
    "route_end_times[].route_idx",
    "feasible",
    "feasibility_breakdown",
]


# ---------------------------------------------------------------------------
# Compact payload projection
# ---------------------------------------------------------------------------

# Top-level keys that are cheap to include in full and that the model
# needs for grounding. Anything not in this list is summarised.
_INLINE_KEYS: frozenset = frozenset(
    {
        "action_objective",
        "baseline_objective",
        "objective_delta_absolute",
        "objective_delta_percent",
        "units",
        "feasible",
        "feasibility_breakdown",
        "infeasibility_kind",
        "perturbation",
        "diff",
    }
)

# Caps on row-shaped collections to keep prompt size bounded.
_MAX_ROUTES_INLINE = 12
_MAX_CUSTOMERS_PER_ROUTE_INLINE = 30
_MAX_SCHEDULE_ROWS_INLINE = 60


def _compact_routes(routes: list[Any]) -> list[Any]:
    out: list[Any] = []
    for r in routes[:_MAX_ROUTES_INLINE]:
        if not isinstance(r, dict):
            out.append(r)
            continue
        compact: dict[str, Any] = {}
        if "route_idx" in r:
            compact["route_idx"] = r["route_idx"]
        if "display_route_number" in r:
            compact["display_route_number"] = r["display_route_number"]
        if "route_label" in r:
            compact["route_label"] = r["route_label"]
        cids = r.get("customer_ids")
        if isinstance(cids, list):
            if len(cids) > _MAX_CUSTOMERS_PER_ROUTE_INLINE:
                compact["customer_ids"] = (
                    cids[:_MAX_CUSTOMERS_PER_ROUTE_INLINE]
                    + [f"... +{len(cids) - _MAX_CUSTOMERS_PER_ROUTE_INLINE} more"]
                )
            else:
                compact["customer_ids"] = cids
        # Surface a few other potentially-relevant scalars if present.
        for k in ("end_time", "start_time", "load", "route_distance"):
            if k in r:
                compact[k] = r[k]
        out.append(compact)
    if len(routes) > _MAX_ROUTES_INLINE:
        out.append(f"... +{len(routes) - _MAX_ROUTES_INLINE} more routes truncated")
    return out


def _compact_schedule_rows(rows: list[Any]) -> list[Any]:
    if len(rows) <= _MAX_SCHEDULE_ROWS_INLINE:
        return rows
    return rows[:_MAX_SCHEDULE_ROWS_INLINE] + [
        f"... +{len(rows) - _MAX_SCHEDULE_ROWS_INLINE} more rows truncated"
    ]


def _compact_payload(payload: Optional[dict]) -> dict:
    """Produce a JSON-serialisable compact view of the payload.

    The projection keeps every field-family path listed in
    `ALLOWED_EVIDENCE_PATHS` (the model needs to be able to cite them)
    and surfaces the answer-grounding scalars. Bulk lists are truncated
    with explicit `... +N more` placeholders so the model can see that
    truncation occurred.
    """
    if not isinstance(payload, dict):
        return {"__payload_kind__": "empty_or_non_dict"}

    compact: dict[str, Any] = {}
    for k, v in payload.items():
        if k in {"routes"} and isinstance(v, list):
            compact[k] = _compact_routes(v)
        elif k in {"customer_schedule", "route_end_times"} and isinstance(v, list):
            compact[k] = _compact_schedule_rows(v)
        elif k in _INLINE_KEYS:
            compact[k] = v
        elif isinstance(v, (str, int, float, bool)) or v is None:
            compact[k] = v
        elif isinstance(v, list):
            # Unknown list — keep length only.
            compact[k] = f"<list len={len(v)} truncated>"
        elif isinstance(v, dict):
            # Unknown dict — keep keys only.
            compact[k] = {sub_k: "<...>" for sub_k in v.keys()}
        else:
            compact[k] = f"<{type(v).__name__}>"

    return compact


def _available_top_level_fields(payload: Optional[dict]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return sorted(payload.keys())


# ---------------------------------------------------------------------------
# Static prompt text
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a contract emitter for a VRPTW (Vehicle Routing Problem with Time Windows) copilot.

Your task is to read an operator-style question about a vehicle route plan, along with the structured payload that describes the plan, and emit a structured contract response as JSON.

You DO NOT need to answer the question in natural language; you emit the structured contract fields the downstream product would use to compose its response. An optional `answer_text` field is useful but not required.

Return JSON only. No markdown. No commentary outside the JSON object."""


_TASK_INSTRUCTIONS_TEMPLATE = """## Allowed values (use only these — exact strings)

predicted_intent (choose exactly one):
{intents}

predicted_answerability (choose exactly one):
{answerability}

predicted_behavior_class (choose exactly one):
{behavior_classes}

predicted_warnings (zero or more):
{warnings}

predicted_next_actions (zero or more — emit the SEMANTIC CODES, not concrete strings):
{next_actions}

predicted_evidence_paths (zero or more — use the canonical GENERIC field-family paths):
{evidence_paths}

predicted_missing_fields (zero or more — payload field paths the contract would have needed to answer fully):
- Use the same field-family path grammar as evidence paths (e.g. `units.objective`, `routes[].customer_ids`, `baseline_solution`, `diff`, `reference_solution.objective`, `feasible`, `feasibility_breakdown`, `new_customer_ids`).

## Operational conventions (apply when picking labels)

1. **Display convention.** "Route N" in the question refers to display_route_number=N (1-indexed). The internal `route_idx` is `N - 1`. When the prompt names a route by integer that does not exist among the routes in the payload, this is a false-premise route.
2. **Customer false premise.** When the prompt names a customer ID that does not appear in any route's `customer_ids` or in `customer_schedule[].customer_id`, this is a false-premise customer.
3. **STRUCT single-customer membership** is NOT full-route equality. A question that names ONE customer and asks which route they're on should emit intent `single_customer_route_membership` and warn `struct_membership_ambiguity` (subset vs full-route ambiguity).
4. **Full-route listing.** A question that asks "list the customers on each route" or "show the full roster of route N" is intent `full_route_listing`. Evidence cites `routes[].customer_ids`.
5. **Before/after comparison.** A non-OBJ before/after question needs `baseline_solution` and `diff`. If absent, the contract refuses with `unsupported_comparison`.
6. **OBJ escape hatch.** An `objective_delta` question is answerable when the OBJ payload carries `action_objective`, `baseline_objective`, and at least one of `objective_delta_absolute` / `objective_delta_percent` — even without a `baseline_solution`.
7. **OBJ comparator ambiguity.** When an `objective_delta` question references an external comparator (e.g. "a full re-solve", "the optimum", "a reference solution") that is NOT what `baseline_objective` describes (which is the pre-perturbation Stage A cost), the contract is partially answerable: cite the OBJ delta evidence, list `reference_solution.objective` as missing, warn `comparison_referent_ambiguity`, and suggest `expose_reference_solution_objective`.
8. **New-customer assignment.** Intent `new_customer_assignment` requires `new_customer_ids` (or `perturbation.new_customer_ids`). If absent, partial answer with `missing_new_customer_attribution` and `expose_new_customer_ids`.
9. **PLAN_VALIDITY missing fields.** When both `feasible` and `feasibility_breakdown` are absent, refuse with intent `feasibility_status`, answerability `not_answerable`, and suggest `use_validity_payload`.
10. **OBJ missing units.** When an OBJ payload supplies `action_objective` but not `units.objective`, cite `action_objective` as evidence, list `units.objective` as missing, warn `evidence_units_missing`, and suggest `expose_units_objective`. The answerability is partial.
11. **False premise.** A false-premise customer or route yields `not_answerable` with `false_premise_detected` in warnings and `clarify_false_premise` in next actions. `predicted_missing_fields` may be empty (the named entity is the problem, not a missing payload column).
12. **Route-indexing ambiguity.** A question that names a route by integer triggers `route_indexing_ambiguity` because the display convention is 1-indexed; do NOT also emit this warning when `false_premise_detected` fires (false premise dominates).

## Behavior class projection (schema §7)

- answerable + no warnings              → direct_answer
- answerable + warnings, no missing     → direct_answer_with_warning
- partially_answerable + evidence cited → partial_answer_with_warning
- partially_answerable + no evidence    → useful_refusal
- not_answerable                        → useful_refusal

## Evidence path policy

- Use GENERIC paths only (`routes[].customer_ids`, `customer_schedule[].arrival`). Do NOT use predicate-pinned paths like `customer_schedule[customer_id=42].arrival` in your output.
- Cite only paths you can ground in the payload. Do NOT invent fields. If the payload does not contain a required field for the intent, list it under `predicted_missing_fields` instead of `predicted_evidence_paths`.

## Required JSON output shape

Emit exactly one JSON object with these keys:

```
{{
  "predicted_intent": "<one of allowed intents>",
  "predicted_answerability": "<one of allowed answerability>",
  "predicted_evidence_paths": ["<path>", ...],
  "predicted_missing_fields": ["<path>", ...],
  "predicted_warnings": ["<warning code>", ...],
  "predicted_next_actions": ["<semantic next-action code>", ...],
  "predicted_behavior_class": "<one of allowed behavior classes>",
  "answer_text": "<optional one-sentence answer or refusal narrative>"
}}
```

Return the JSON object and nothing else."""


def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items)


def _build_task_instructions() -> str:
    return _TASK_INSTRUCTIONS_TEMPLATE.format(
        intents=_format_bullets(ALLOWED_INTENTS),
        answerability=_format_bullets(ALLOWED_ANSWERABILITY),
        behavior_classes=_format_bullets(ALLOWED_BEHAVIOR_CLASSES),
        warnings=_format_bullets(ALLOWED_WARNINGS),
        next_actions=_format_bullets(ALLOWED_NEXT_ACTIONS),
        evidence_paths=_format_bullets(ALLOWED_EVIDENCE_PATHS),
    )


def _build_case_block(case: Run2Case, payload: Optional[dict]) -> str:
    compact = _compact_payload(payload)
    available = _available_top_level_fields(payload)
    payload_json = json.dumps(compact, indent=2, sort_keys=True, default=str)
    return f"""## Case

prompt_text:
{case.prompt_text}

family: {case.family}
payload_condition: {case.payload_condition}

available_top_level_payload_fields:
{json.dumps(available)}

structured_payload (compact projection; long lists truncated with `... +N more`):
```json
{payload_json}
```

Emit the JSON contract object now."""


def build_prompt_only_json_prompt(
    case: Run2Case, payload: Optional[dict]
) -> list[dict]:
    """Return a chat-completions `messages` list for System B.

    The list has two messages: a system prompt that defines the role
    and forbids markdown, and a user message that bundles the task
    instructions (allowed enums + conventions) and the case-specific
    block (prompt text + family + payload projection).

    The case's `expected_*` columns are intentionally NOT passed in —
    System B must produce the contract from prompt + payload alone.
    """
    user_content = _build_task_instructions() + "\n\n" + _build_case_block(case, payload)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# System A — deterministic-prior + model emitter
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT_A = """You are a contract emitter for a VRPTW (Vehicle Routing Problem with Time Windows) copilot.

You are operating in *prior-assisted* mode. A deterministic product-layer classifier has already computed an intent / answerability / missing-fields / warnings / next-actions prior for this case. Your job is to emit the final JSON contract object, preserving the prior's locked fields except in the explicit disagreement case below.

Return JSON only. No markdown. No commentary outside the JSON object."""


_PRIOR_INSTRUCTIONS_TEMPLATE = """## Allowed values (use only these — exact strings)

predicted_intent (choose exactly one):
{intents}

predicted_answerability (choose exactly one):
{answerability}

predicted_behavior_class (choose exactly one):
{behavior_classes}

predicted_warnings (zero or more — these codes only):
{warnings}

predicted_next_actions (zero or more — semantic codes only):
{next_actions}

predicted_evidence_paths (zero or more — canonical generic field-family paths):
{evidence_paths}

predicted_missing_fields uses the same path grammar as evidence paths (e.g. `units.objective`, `routes[].customer_ids`, `baseline_solution`, `diff`, `reference_solution.objective`, `feasible`, `feasibility_breakdown`, `new_customer_ids`).

## Prior handling — READ THIS BEFORE EMITTING

The prior block below names the fields it has computed under `prior_locked_fields`. For each such field, you MUST copy the prior's value into your output unchanged:

- `predicted_intent`  ← `intent_prior`
- `predicted_answerability` ← `answerability_prior`
- `predicted_missing_fields` ← `missing_fields_prior`
- `predicted_warnings` ← `warnings_prior`
- `predicted_next_actions` ← `next_actions_prior`
- `predicted_behavior_class` ← `behavior_class_prior`

If — and ONLY if — you can explain a concrete contradiction between the prior and the payload, you may diverge. In that case you MUST set `prior_disagreement: true` and explain the contradiction in `adapter_notes` (one sentence). Without that flag, your output must match the prior on all locked fields. Do NOT add new warnings beyond `warnings_prior`. Do NOT remove a prior warning silently.

## What you still choose

- `predicted_evidence_paths` — pick the canonical generic paths you can ground in the payload (use the prior's `required_fields` as a starting point, but cite only paths the payload supports). For useful_refusal cases the list may be empty.
- `answer_text` — a short, optional operator-facing sentence (one-line answer or refusal narrative).
- The order of items inside list fields. (Order is not scored.)

## Operational conventions (reminders)

1. Display convention — "Route N" means display_route_number=N (1-indexed); internal `route_idx` is N-1.
2. Evidence paths: use the GENERIC form (`routes[].customer_ids`, not `routes[route_idx=4].customer_ids`).
3. STRUCT single-customer membership emits intent `single_customer_route_membership` with warning `struct_membership_ambiguity` (do not relabel as `new_customer_assignment` just because the prompt mentions "after the new orders came in").
4. False premise — when `false_premise_detected` is in `warnings_prior`, evidence is typically empty; next actions include `clarify_false_premise`.
5. Behavior class shape (must match the prior unless you disagree):
   - answerable + no warnings              → direct_answer
   - answerable + warnings                 → direct_answer_with_warning
   - partially_answerable + evidence cited → partial_answer_with_warning
   - partially_answerable / not_answerable + no evidence → useful_refusal

## Required JSON output shape

Emit exactly one JSON object with these keys:

```
{{
  "predicted_intent": "<one of allowed intents>",
  "predicted_answerability": "<one of allowed answerability>",
  "predicted_evidence_paths": ["<path>", ...],
  "predicted_missing_fields": ["<path>", ...],
  "predicted_warnings": ["<warning code>", ...],
  "predicted_next_actions": ["<semantic next-action code>", ...],
  "predicted_behavior_class": "<one of allowed behavior classes>",
  "answer_text": "<optional one-sentence answer or refusal narrative>",
  "prior_disagreement": false,
  "adapter_notes": ""
}}
```

Return the JSON object and nothing else."""


def _build_prior_task_instructions() -> str:
    return _PRIOR_INSTRUCTIONS_TEMPLATE.format(
        intents=_format_bullets(ALLOWED_INTENTS),
        answerability=_format_bullets(ALLOWED_ANSWERABILITY),
        behavior_classes=_format_bullets(ALLOWED_BEHAVIOR_CLASSES),
        warnings=_format_bullets(ALLOWED_WARNINGS),
        next_actions=_format_bullets(ALLOWED_NEXT_ACTIONS),
        evidence_paths=_format_bullets(ALLOWED_EVIDENCE_PATHS),
    )


def _build_prior_block(prior: dict) -> str:
    """Render the deterministic prior as a JSON block for the model."""
    # Drop the underscore-prefixed bookkeeping keys so the model only
    # sees the operationally meaningful values.
    public = {k: v for k, v in prior.items() if not k.startswith("_")}
    prior_json = json.dumps(public, indent=2, sort_keys=True, default=str)
    return f"## Deterministic prior (locked unless disagreement flagged)\n\n```json\n{prior_json}\n```"


def build_system_a_prior_prompt(
    case: Run2Case, payload: Optional[dict], prior: dict
) -> list[dict]:
    """Return a chat-completions `messages` list for System A.

    System A messages: a system prompt that puts the model in
    prior-assisted mode, followed by a user message that bundles the
    task instructions, the prior block, and the case block (prompt +
    payload projection). The model emits the canonical contract JSON
    plus optional `prior_disagreement` / `adapter_notes`.

    The case's `expected_*` columns are intentionally NOT passed in —
    System A's hypothesis is that the *deterministic prior* (not gold
    labels) is sufficient to make the model contract-stable.
    """
    user_content = (
        _build_prior_task_instructions()
        + "\n\n"
        + _build_prior_block(prior)
        + "\n\n"
        + _build_case_block(case, payload)
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT_A},
        {"role": "user", "content": user_content},
    ]


__all__ = [
    "ALLOWED_INTENTS",
    "ALLOWED_ANSWERABILITY",
    "ALLOWED_BEHAVIOR_CLASSES",
    "ALLOWED_WARNINGS",
    "ALLOWED_NEXT_ACTIONS",
    "ALLOWED_EVIDENCE_PATHS",
    "build_prompt_only_json_prompt",
    "build_system_a_prior_prompt",
]

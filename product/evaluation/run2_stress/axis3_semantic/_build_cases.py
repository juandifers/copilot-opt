"""One-off script that materializes axis3_semantic/cases.csv from the
locked Run 2 benchmark.

The stress CSV is regenerable from this script + the locked
`run2_benchmark_cases.csv`. Re-running it must be a no-op when the
locked benchmark and the stress spec below are unchanged.

Not a runtime module. Not imported by the loader, runner, or report.
Kept under the axis directory so the inheritance source is auditable.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
LOCKED_CSV = REPO_ROOT / "product" / "evaluation" / "run2_benchmark_cases.csv"
OUT_CSV = Path(__file__).resolve().parent / "cases.csv"


# Spec rows. Each tuple is:
#   (case_id, split, stress_subtype, base_case_id, prompt_text,
#    paraphrase_notes, forbidden_keywords_removed, ambiguity_notes)
#
# ``forbidden_keywords_removed`` lists the base-case tokens that the
# stress prompt deliberately drops; this is descriptive, not load-time
# enforced.
SPEC: list[tuple[str, str, str, str, str, str, str, str]] = [
    # ---- dev (12) ----
    (
        "S1D-01", "dev", "cost_synonym", "R2-001",
        "What score did the solver give this plan?",
        "Replaces 'total cost' with 'score the solver gave'.",
        "total cost;cost",
        "C0 should classify as objective_value via the OBJ family branch (no comparative tokens). Vocabulary stress: 'score' is novel relative to the Run 2 OBJ matcher.",
    ),
    (
        "S1D-02", "dev", "feasibility_synonym", "R2-028",
        "Can this plan actually be driven as-is?",
        "Replaces 'does this plan still work' with 'can be driven as-is'.",
        "still work",
        "C0 routes PLAN_VALIDITY directly to feasibility_status, so this should pass intent; the stress is the vocabulary drift.",
    ),
    (
        "S1D-03", "dev", "feasibility_synonym", "R2-029",
        "Is the route plan valid under the current constraints?",
        "Replaces 'still work after X' with 'valid under current constraints'.",
        "still work;travel times went up",
        "C0 routes PLAN_VALIDITY directly to feasibility_status; expected pass.",
    ),
    (
        "S1D-04", "dev", "operator_colloquial", "R2-004",
        "Where did customer 42 get placed?",
        "Replaces 'Which route is customer 42 on' with 'Where did customer 42 get placed'.",
        "which route",
        "C0 catches the 'customer N' token (STRUCT branch) and emits single_customer_route_membership. Expected pass.",
    ),
    (
        "S1D-05", "dev", "entity_synonym", "R2-039",
        "What run contains customer 42?",
        "Replaces 'Which route is customer 42 on' with 'What run contains customer 42'.",
        "which route",
        "C0 catches 'customer N' (STRUCT branch). Expected pass.",
    ),
    (
        "S1D-06", "dev", "entity_synonym", "R2-040",
        "Which truck has customer 17 on it today?",
        "Replaces 'Which route is customer 17 on' with 'Which truck has customer 17 on it'.",
        "which route",
        "C0 catches 'customer N' (STRUCT branch). Expected pass.",
    ),
    (
        "S1D-07", "dev", "entity_synonym", "R2-010",
        "Give me the full set of vehicle runs.",
        "Replaces 'list all the customers assigned to each route' with 'full set of vehicle runs'.",
        "list all the customers;each route",
        "Expected C0 failure: 'full set of vehicle runs' does not match any phrase in _FULL_ROUTE_LISTING_PHRASES and there is no 'which route'/customer token. STRUCT branch returns 'unknown'.",
    ),
    (
        "S1D-08", "dev", "schedule_synonym", "R2-055",
        "When does vehicle 1 close out?",
        "Replaces 'What time does route 1 wrap up' with 'When does vehicle 1 close out'.",
        "wrap up;route 1",
        "Expected C0 failure: 'close out' is not in the SCHEDULE route_end_time token set, and the entity is 'vehicle 1' not 'route 1', so no token + 'route' combination fires. Returns 'unknown'.",
    ),
    (
        "S1D-09", "dev", "schedule_synonym", "R2-060",
        "When is vehicle 1 finished?",
        "Replaces 'What time does Route 1 finish' with 'When is vehicle 1 finished'.",
        "Route 1",
        "Expected C0 failure: 'finish' is in the token set but the AND requires 'route' to appear in the prompt; 'vehicle 1' does not include 'route'. Returns 'unknown'.",
    ),
    (
        "S1D-10", "dev", "schedule_synonym", "R2-007",
        "When does customer 42 get served?",
        "Replaces 'When does the driver reach customer 42' with 'When does customer 42 get served'.",
        "the driver reach;new orders came in",
        "C0 takes the SCHEDULE customer_arrival fallback: 'when does' + has_specific_customer_number. Expected pass.",
    ),
    (
        "S1D-11", "dev", "schedule_synonym", "R2-051",
        "Does anyone miss their promised window?",
        "Replaces 'Is anyone going to be late' with 'Does anyone miss their promised window'.",
        "late;travel times went up",
        "C0 catches 'miss' in the lateness token set. Expected pass.",
    ),
    (
        "S1D-12", "dev", "operator_colloquial", "R2-053",
        "Which customers fall behind schedule?",
        "Replaces 'Is anyone going to be late' with 'Which customers fall behind schedule'.",
        "late;travel times went up",
        "Expected C0 failure: 'behind schedule' does not match any token in the lateness set ('late', 'delivery window', 'on time', 'delayed', 'lateness', 'miss'). Returns 'unknown'.",
    ),
    # ---- heldout (12) ----
    (
        "S1H-01", "heldout", "cost_synonym", "R2-016",
        "How expensive is the current routing solution overall?",
        "Replaces 'total cost on this plan' with 'how expensive is the current routing solution'.",
        "total cost",
        "C0 routes OBJ directly; no comparative tokens. Expected pass.",
    ),
    (
        "S1H-02", "heldout", "cost_synonym", "R2-019",
        "What value is the optimizer assigning to this plan?",
        "Replaces 'what does the plan end up costing' with 'what value is the optimizer assigning'.",
        "costing;longer travel times",
        "C0 routes OBJ directly; no comparative tokens. Expected pass.",
    ),
    (
        "S1H-03", "heldout", "feasibility_synonym", "R2-030",
        "Is the proposed routing plan executable?",
        "Replaces 'are all customers still reachable' with 'is the proposed routing plan executable'.",
        "still reachable;tighter delivery windows",
        "C0 routes PLAN_VALIDITY directly. Expected pass.",
    ),
    (
        "S1H-04", "heldout", "feasibility_synonym", "R2-031",
        "Can the proposed set of routes be carried out?",
        "Replaces 'did we end up dropping any customers' with 'can the proposed set of routes be carried out'.",
        "dropping any customers;tighter",
        "C0 routes PLAN_VALIDITY directly. Expected pass.",
    ),
    (
        "S1H-05", "heldout", "entity_synonym", "R2-041",
        "Which vehicle is customer 42 assigned to?",
        "Replaces 'Which route is customer 42 on' with 'Which vehicle is customer 42 assigned to'.",
        "which route;new stops were added",
        "C0 catches 'customer N' (STRUCT branch). Expected pass.",
    ),
    (
        "S1H-06", "heldout", "entity_synonym", "R2-045",
        "Which truck has customer 12 right now?",
        "Replaces 'Which route is customer 12 on' with 'Which truck has customer 12 right now'.",
        "which route;tighter",
        "C0 catches 'customer N' (STRUCT branch). Expected pass.",
    ),
    (
        "S1H-07", "heldout", "paraphrase", "R2-048",
        "Show me every route in the plan.",
        "Replaces 'list the customers on each route' with 'show me every route'.",
        "list the customers;each route;new stops were added",
        "Expected C0 failure: 'every route' does not match any phrase in _FULL_ROUTE_LISTING_PHRASES. STRUCT branch returns 'unknown'.",
    ),
    (
        "S1H-08", "heldout", "paraphrase", "R2-049",
        "List the complete route plan.",
        "Replaces 'Which customers are on each vehicle' with 'list the complete route plan'.",
        "each vehicle",
        "Expected C0 failure: 'list the complete route plan' does not match the full_route_listing phrase set ('list the customers' specifically requires the word 'customers' adjacent to 'list'). STRUCT branch returns 'unknown'.",
    ),
    (
        "S1H-09", "heldout", "schedule_synonym", "R2-055",
        "At what time is route 1 done for the day?",
        "Replaces 'wrap up' with 'done for the day'.",
        "wrap up;new orders came in",
        "Expected C0 failure: 'done' is not in the route_end_time token set, even though 'route 1' is present. Returns 'unknown'.",
    ),
    (
        "S1H-10", "heldout", "schedule_synonym", "R2-060",
        "When does truck 1 complete its run?",
        "Replaces 'What time does Route 1 finish' with 'When does truck 1 complete its run'.",
        "Route 1;service times went up",
        "Expected C0 failure: 'complete' matches the token set but the AND requires 'route' in the prompt; 'truck 1' / 'complete its run' does not include 'route'. Returns 'unknown'.",
    ),
    (
        "S1H-11", "heldout", "schedule_synonym", "R2-056",
        "What time does the driver reach customer 17?",
        "Replaces 'When does the driver reach customer 17 after the new orders came in' with 'What time does the driver reach customer 17'.",
        "new orders came in",
        "C0 catches 'the driver reach' (SCHEDULE customer_arrival). Expected pass.",
    ),
    (
        "S1H-12", "heldout", "schedule_synonym", "R2-054",
        "Are any stops served after their allowed time?",
        "Replaces 'miss their delivery windows' with 'served after their allowed time'.",
        "delivery windows",
        "Expected C0 failure: none of the lateness tokens ('late', 'delivery window', 'on time', 'delayed', 'lateness', 'miss') match 'served after their allowed time'. Returns 'unknown'.",
    ),
]


STRESS_COLUMNS = [
    "stress_axis",
    "stress_subtype",
    "split",
    "base_case_id",
    "base_family",
    "canonical_prompt",
    "paraphrase_notes",
    "forbidden_keywords_removed",
    "notes",
]


def _difficulty_cap(base_diff: str) -> str:
    return "medium" if base_diff == "hard" else base_diff


def main() -> int:
    locked = pd.read_csv(LOCKED_CSV, keep_default_na=False, dtype=str)
    locked_by_id = {row["case_id"]: row for _, row in locked.iterrows()}

    gold_columns = [
        "case_id", "source_prompt_id", "family", "prompt_text",
        "payload_condition", "payload_mutation_needed",
        "expected_intent", "expected_answerability",
        "expected_evidence_paths", "expected_missing_fields",
        "expected_warnings", "expected_next_actions",
        "expected_behavior_class", "implementation_status",
        "difficulty", "label_rationale", "ambiguity_notes",
    ]
    header = gold_columns + STRESS_COLUMNS
    rows: list[dict[str, str]] = []

    for case_id, split, subtype, base_id, prompt_text, paraphrase_notes, forbidden, ambiguity in SPEC:
        if base_id not in locked_by_id:
            raise SystemExit(f"base_case_id {base_id!r} not in locked benchmark")
        base = locked_by_id[base_id]
        row = {
            "case_id": case_id,
            "source_prompt_id": base["source_prompt_id"],
            "family": base["family"],
            "prompt_text": prompt_text,
            "payload_condition": base["payload_condition"],
            "payload_mutation_needed": base["payload_mutation_needed"],
            "expected_intent": base["expected_intent"],
            "expected_answerability": base["expected_answerability"],
            "expected_evidence_paths": base["expected_evidence_paths"],
            "expected_missing_fields": base["expected_missing_fields"],
            "expected_warnings": base["expected_warnings"],
            "expected_next_actions": base["expected_next_actions"],
            "expected_behavior_class": base["expected_behavior_class"],
            "implementation_status": base["implementation_status"],
            "difficulty": _difficulty_cap(base["difficulty"]),
            "label_rationale": (
                f"Paraphrase of {base_id}; inherits gold contract response. "
                f"Stress subtype: {subtype}. Paraphrase note: {paraphrase_notes}"
            ),
            "ambiguity_notes": ambiguity,
            "stress_axis": "semantic_intent",
            "stress_subtype": subtype,
            "split": split,
            "base_case_id": base_id,
            "base_family": base["family"],
            "canonical_prompt": base["prompt_text"],
            "paraphrase_notes": paraphrase_notes,
            "forbidden_keywords_removed": forbidden,
            "notes": "",
        }
        rows.append(row)

    if len(rows) != 24:
        raise SystemExit(f"expected 24 cases, got {len(rows)}")
    dev_n = sum(1 for r in rows if r["split"] == "dev")
    held_n = sum(1 for r in rows if r["split"] == "heldout")
    if (dev_n, held_n) != (12, 12):
        raise SystemExit(f"expected 12/12 dev/heldout, got {dev_n}/{held_n}")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"wrote {OUT_CSV} ({len(rows)} rows; dev={dev_n}, heldout={held_n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

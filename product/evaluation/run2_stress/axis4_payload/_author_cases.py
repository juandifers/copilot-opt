"""Author the 24 stress cases as a deterministic Python data structure.

Run produces `cases.csv` with the 17-column gold schema + a `split` column
(value 'unassigned' here; assigned by `_assign_splits.py`).

Cell-id usage tracked: ≤2 cases per (instance, magnitude) cell.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Each row: (case_id, cell_id, band, intent, sub_pattern, prompt_text,
#           payload_condition, expected_warnings, ambiguity_predictions)
# All expected_intent / expected_evidence / expected_behavior derive
# deterministically from intent + warning below.

LOW_CASES: list[dict] = [
    # ----- customer_arrival × low band (4 cases) -----
    dict(case_id="R2-101", cell_id="C2_2_1__OC_4", band="low", n_routes=8,
         intent="customer_arrival", sub_pattern="mid-list",
         prompt="When does customer 142 arrive?",
         warnings=[]),
    dict(case_id="R2-102", cell_id="C2_2_2__OC_5", band="low", n_routes=8,
         intent="customer_arrival", sub_pattern="multi-entity",
         prompt="When does the driver reach customers 87, 142, and 199?",
         warnings=[]),
    dict(case_id="R2-103", cell_id="RC2_2_1__OC_4", band="low", n_routes=10,
         intent="customer_arrival", sub_pattern="mid-list",
         prompt="When does customer 178 arrive?",
         warnings=[]),
    dict(case_id="R2-104", cell_id="R2_2_1__OC_4", band="low", n_routes=12,
         intent="customer_arrival", sub_pattern="multi-entity",
         prompt="When does the driver get to customers 33, 110, and 178?",
         warnings=[]),

    # ----- route_end_time × low band (4 cases) -----
    dict(case_id="R2-105", cell_id="C2_2_1__ST_3", band="low", n_routes=8,
         intent="route_end_time", sub_pattern="mid-list",
         prompt="What time does route 5 finish?",
         warnings=["route_indexing_ambiguity"]),
    dict(case_id="R2-106", cell_id="RC2_2_1__TT_5", band="low", n_routes=10,
         intent="route_end_time", sub_pattern="mid-list",
         prompt="When does route 7 wrap up?",
         warnings=["route_indexing_ambiguity"]),
    dict(case_id="R2-107", cell_id="RC2_2_1__ST_4", band="low", n_routes=11,
         intent="route_end_time", sub_pattern="routes-by-position",
         prompt="What's the end time of the 9th route?",
         warnings=[]),
    dict(case_id="R2-108", cell_id="R2_2_1__TW_5", band="low", n_routes=12,
         intent="route_end_time", sub_pattern="routes-by-position",
         prompt="When does the 11th route finish?",
         warnings=[]),

    # ----- lateness_summary × low band (4 cases) -----
    dict(case_id="R2-109", cell_id="C2_2_2__ST_4", band="low", n_routes=8,
         intent="lateness_summary", sub_pattern="multi-entity",
         prompt="Which customers are late on routes 1-4?",
         warnings=[]),
    dict(case_id="R2-110", cell_id="C2_2_1__ST_4", band="low", n_routes=9,
         intent="lateness_summary", sub_pattern="mid-list",
         prompt="Are any customers late on this plan?",
         warnings=[]),
    dict(case_id="R2-111", cell_id="RC2_2_1__TW_6", band="low", n_routes=9,
         intent="lateness_summary", sub_pattern="multi-entity",
         prompt="How many customers missed their delivery window?",
         warnings=[]),
    dict(case_id="R2-112", cell_id="R2_2_1__ST_4", band="low", n_routes=12,
         intent="lateness_summary", sub_pattern="multi-entity",
         prompt="Are customers 87, 142, and 199 all on time?",
         warnings=[]),
]

HIGH_CASES: list[dict] = [
    # ----- customer_arrival × high band (4 cases) -----
    dict(case_id="R2-113", cell_id="RC1_2_2__OC_4", band="high", n_routes=19,
         intent="customer_arrival", sub_pattern="mid-list",
         prompt="When does customer 142 arrive?",
         warnings=[]),
    dict(case_id="R2-114", cell_id="C1_2_1__TW_5", band="high", n_routes=20,
         intent="customer_arrival", sub_pattern="multi-entity",
         prompt="When does the driver reach customers 87, 142, and 199?",
         warnings=[]),
    dict(case_id="R2-115", cell_id="RC1_2_1__OC_5", band="high", n_routes=20,
         intent="customer_arrival", sub_pattern="mid-list",
         prompt="When does customer 178 arrive?",
         warnings=[]),
    dict(case_id="R2-116", cell_id="C1_2_1__OC_4", band="high", n_routes=22,
         intent="customer_arrival", sub_pattern="multi-entity",
         prompt="When does the driver get to customers 33, 110, and 178?",
         warnings=[]),

    # ----- route_end_time × high band (4 cases) -----
    dict(case_id="R2-117", cell_id="RC1_2_2__ST_3", band="high", n_routes=19,
         intent="route_end_time", sub_pattern="routes-by-position",
         prompt="When does the 15th route finish?",
         warnings=[]),
    dict(case_id="R2-118", cell_id="C1_2_2__TW_6", band="high", n_routes=20,
         intent="route_end_time", sub_pattern="mid-list",
         prompt="What time does route 12 wrap up?",
         warnings=["route_indexing_ambiguity"]),
    dict(case_id="R2-119", cell_id="R1_2_2__ST_4", band="high", n_routes=21,
         intent="route_end_time", sub_pattern="routes-by-position",
         prompt="What's the end time of the 18th route?",
         warnings=[]),
    dict(case_id="R2-120", cell_id="RC1_2_1__TT_4", band="high", n_routes=22,
         intent="route_end_time", sub_pattern="mid-list",
         prompt="When does route 17 finish?",
         warnings=["route_indexing_ambiguity"]),

    # ----- lateness_summary × high band (4 cases) -----
    dict(case_id="R2-121", cell_id="C1_2_1__OC_5", band="high", n_routes=22,
         intent="lateness_summary", sub_pattern="multi-entity",
         prompt="Which customers are late on routes 8, 12, and 17?",
         warnings=[]),
    dict(case_id="R2-122", cell_id="RC1_2_2__TW_5", band="high", n_routes=19,
         intent="lateness_summary", sub_pattern="mid-list",
         prompt="Are any customers late on this plan?",
         warnings=[]),
    dict(case_id="R2-123", cell_id="C1_2_2__OC_4", band="high", n_routes=22,
         intent="lateness_summary", sub_pattern="multi-entity",
         prompt="How many customers missed their delivery window?",
         warnings=[]),
    dict(case_id="R2-124", cell_id="R1_2_2__OC_5", band="high", n_routes=22,
         intent="lateness_summary", sub_pattern="multi-entity",
         prompt="Are customers 87, 142, and 199 all on time?",
         warnings=[]),
]

INTENT_EVIDENCE_PATHS: dict[str, list[str]] = {
    "customer_arrival": ["customer_schedule[].arrival"],
    "route_end_time": ["route_end_times[].end_time"],
    "lateness_summary": ["n_late_customers", "late_customer_ids"],
}


def _band_label(band: str, n_routes: int) -> str:
    if band == "low":
        return f"low band (8-12 routes, n_routes={n_routes})"
    return f"high band (18-22 routes, n_routes={n_routes})"


def _predicted_metric(intent: str, band: str) -> str:
    # The user-spec predictions: compact, only the stressed metric.
    # ev_prec is the headline stress on every SCHEDULE intent.
    if band == "low":
        return ("{C0_ev_prec: 0.95-1.00, A_ev_prec: 0.75-0.85, "
                "B_ev_prec: 0.65-0.80}")
    return ("{C0_ev_prec: 0.95-1.00, A_ev_prec: 0.55-0.75, "
            "B_ev_prec: 0.45-0.65}")


def _payload_condition(warnings: list[str]) -> str:
    return "convention_boundary" if "route_indexing_ambiguity" in warnings else "clean"


def _behavior_class(warnings: list[str]) -> str:
    return "direct_answer_with_warning" if warnings else "direct_answer"


def build_row(spec: dict) -> dict:
    evidence_paths = INTENT_EVIDENCE_PATHS[spec["intent"]]
    rationale = (
        f"{_band_label(spec['band'], spec['n_routes'])} on cell "
        f"{spec['cell_id']}; SCHEDULE intent '{spec['intent']}' fires "
        f"on the trigger tokens in the prompt; payload contains all "
        f"required fields ({';'.join(evidence_paths)}); adversarial "
        f"sub-pattern: {spec['sub_pattern']}."
    )
    return {
        "case_id": spec["case_id"],
        "source_prompt_id": "",
        "family": "SCHEDULE",
        "prompt_text": spec["prompt"],
        "payload_condition": _payload_condition(spec["warnings"]),
        "payload_mutation_needed": (
            f"build SCHEDULE payload from "
            f"data/homberger_probe_checkpoints/pyvrp10s/{spec['cell_id']}.json "
            f"via axis4_payload/build_payloads.py"
        ),
        "expected_intent": spec["intent"],
        "expected_answerability": "answerable",
        "expected_evidence_paths": ";".join(evidence_paths),
        "expected_missing_fields": "",
        "expected_warnings": ";".join(spec["warnings"]),
        "expected_next_actions": "",
        "expected_behavior_class": _behavior_class(spec["warnings"]),
        "implementation_status": "current",
        "difficulty": "hard",
        "label_rationale": rationale,
        "ambiguity_notes": _predicted_metric(spec["intent"], spec["band"]),
        "split": "unassigned",
    }


COLS = [
    "case_id", "source_prompt_id", "family", "prompt_text",
    "payload_condition", "payload_mutation_needed", "expected_intent",
    "expected_answerability", "expected_evidence_paths",
    "expected_missing_fields", "expected_warnings", "expected_next_actions",
    "expected_behavior_class", "implementation_status", "difficulty",
    "label_rationale", "ambiguity_notes", "split",
]


def main() -> None:
    specs = LOW_CASES + HIGH_CASES
    cell_uses = Counter(s["cell_id"] for s in specs)
    over = {c: n for c, n in cell_uses.items() if n > 2}
    if over:
        raise RuntimeError(f"cells used more than twice: {over}")

    rows = [build_row(s) for s in specs]
    out = HERE / "cases.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {len(rows)} cases to {out}")

    # Confirm cell usage
    print(f"unique cells used: {len(cell_uses)}")
    print(f"max uses per cell: {max(cell_uses.values())}")

    # Quick band×intent counts
    by_bi: Counter = Counter((s["band"], s["intent"]) for s in specs)
    print("(band, intent) sub-cells:")
    for k, v in sorted(by_bi.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

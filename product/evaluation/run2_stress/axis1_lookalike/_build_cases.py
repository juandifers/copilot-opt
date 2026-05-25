"""Generator for `axis1_lookalike/cases.csv`.

Produces the 24-case R2-S Axis 1 stress split — 12 dev / 12 heldout
across 4 confusion bands of 6 cases each. Each stress row inherits
its gold contract response verbatim from the named Run 2 base case;
only `prompt_text` is replaced with a look-alike attractor surface
form chosen against `product/copilot/intent.py`'s heuristics.

Running this script overwrites `cases.csv` in place. The output is
deterministic; re-running on the same locked benchmark commit yields
byte-identical output.

Usage:
    python -m product.evaluation.run2_stress.axis1_lookalike._build_cases
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Locked-benchmark loading
# ---------------------------------------------------------------------------


def _benchmark_path() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "run2_benchmark_cases.csv"
    )


def _load_benchmark() -> dict[str, dict[str, str]]:
    df = pd.read_csv(_benchmark_path(), keep_default_na=False, dtype=str)
    return {row["case_id"]: dict(row) for _, row in df.iterrows()}


# ---------------------------------------------------------------------------
# Stress row specification (deterministic, hand-authored)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StressSpec:
    case_id: str
    base_case_id: str
    split: str
    band: str  # = confusion_pair
    stress_subtype: str
    attractor_intent: str
    attractor_tokens: str  # comma-separated
    prompt_text: str
    paraphrase_notes: str
    notes: str


# Band 1 — membership_vs_new_customer_assignment
# STRUCT family, gold = single_customer_route_membership.
# Look-alike pressure: _NEW_ORDER_TOKENS surface forms. Each prompt
# carries a real customer number, which is the C0 guard that blocks
# `_is_about_new_customer_assignment` from firing.
BAND1: list[StressSpec] = [
    StressSpec(
        case_id="A1D-01",
        base_case_id="R2-004",
        split="dev",
        band="membership_vs_new_customer_assignment",
        stress_subtype="membership_lookalike",
        attractor_intent="new_customer_assignment",
        attractor_tokens="new customer,added,assigned,end up",
        prompt_text=(
            "After the new customer was added, which route does customer 42 "
            "end up assigned to?"
        ),
        paraphrase_notes=(
            "Replaces the base 'Which route is customer 42 on after travel "
            "times went up 30%?' with attractor surface tokens 'new "
            "customer', 'added', 'assigned', 'end up'. The customer-number "
            "guard inside _is_about_new_customer_assignment is expected to "
            "block the look-alike misroute and fall through to STRUCT "
            "single_customer_route_membership."
        ),
        notes="guard test (customer-number guard)",
    ),
    StressSpec(
        case_id="A1D-02",
        base_case_id="R2-039",
        split="dev",
        band="membership_vs_new_customer_assignment",
        stress_subtype="membership_lookalike",
        attractor_intent="new_customer_assignment",
        attractor_tokens="new order,inserted,assigned",
        prompt_text=(
            "Where did customer 42 get inserted in the routes once the new "
            "order came in?"
        ),
        paraphrase_notes=(
            "Heavier 'new order' / 'inserted' / 'assigned' surface than the "
            "base R2-039 prompt. customer-number guard expected to hold."
        ),
        notes="guard test (customer-number guard)",
    ),
    StressSpec(
        case_id="A1D-03",
        base_case_id="R2-040",
        split="dev",
        band="membership_vs_new_customer_assignment",
        stress_subtype="membership_lookalike",
        attractor_intent="new_customer_assignment",
        attractor_tokens="newly assigned,new order",
        prompt_text=(
            "Which route is the newly assigned customer 17 on after a new "
            "order came in?"
        ),
        paraphrase_notes=(
            "Adds 'newly assigned' as a referring expression around the "
            "specific customer-17 hook; tests whether the guard holds when "
            "the attractor language is appositional rather than appendix."
        ),
        notes="guard test (customer-number guard)",
    ),
    StressSpec(
        case_id="A1H-01",
        base_case_id="R2-041",
        split="heldout",
        band="membership_vs_new_customer_assignment",
        stress_subtype="membership_lookalike",
        attractor_intent="new_customer_assignment",
        attractor_tokens="new customer,where,land",
        prompt_text=(
            "After adding the new customer, where does customer 42 land in "
            "this plan?"
        ),
        paraphrase_notes=(
            "Mirrors A1D-01 but with 'land' instead of 'end up assigned' so "
            "the heldout split does not duplicate dev surface verbs."
        ),
        notes="guard test (customer-number guard)",
    ),
    StressSpec(
        case_id="A1H-02",
        base_case_id="R2-045",
        split="heldout",
        band="membership_vs_new_customer_assignment",
        stress_subtype="membership_lookalike",
        attractor_intent="new_customer_assignment",
        attractor_tokens="new order,assigned,what route",
        prompt_text=(
            "What route did customer 12 get assigned to once the new order "
            "was dropped in?"
        ),
        paraphrase_notes=(
            "'What route' direct-hook + 'new order' attractor; tests both "
            "the customer-number guard and the STRUCT 'what route' "
            "fall-through."
        ),
        notes="guard test (customer-number guard)",
    ),
    StressSpec(
        case_id="A1H-03",
        base_case_id="R2-004",
        split="heldout",
        band="membership_vs_new_customer_assignment",
        stress_subtype="membership_lookalike",
        attractor_intent="new_customer_assignment",
        attractor_tokens="added customer,where,updated",
        prompt_text=(
            "Where did the added customer 42 end up in the updated routes?"
        ),
        paraphrase_notes=(
            "Reuses R2-004 base with a different attractor flavour ('added "
            "customer' rather than 'new customer'), exercising the second "
            "_NEW_ORDER_TOKENS member."
        ),
        notes="guard test (customer-number guard)",
    ),
]


# Band 2 — lateness_vs_feasibility_status
# SCHEDULE family, gold = lateness_summary. Feasibility-flavoured
# surface tokens are layered on top of the lateness verbs the
# SCHEDULE branch is authored for. feasibility_status is only
# reachable from family=PLAN_VALIDITY, so C0 cannot reach it from a
# SCHEDULE prompt — the band tests family-routing dominance.
BAND2: list[StressSpec] = [
    StressSpec(
        case_id="A1D-04",
        base_case_id="R2-051",
        split="dev",
        band="lateness_vs_feasibility_status",
        stress_subtype="feasibility_lookalike",
        attractor_intent="feasibility_status",
        attractor_tokens="feasible,still",
        prompt_text=(
            "Is the plan still feasible in terms of who might be late after "
            "travel times went up 50%?"
        ),
        paraphrase_notes=(
            "Preserves the 'late' lateness token; layers on 'feasible' and "
            "'still' as attractor surface. Lateness check fires before "
            "is_comparative inside SCHEDULE; feasibility_status is not "
            "reachable from family=SCHEDULE."
        ),
        notes="family-routing test (feasibility_status unreachable)",
    ),
    StressSpec(
        case_id="A1D-05",
        base_case_id="R2-053",
        split="dev",
        band="lateness_vs_feasibility_status",
        stress_subtype="feasibility_lookalike",
        attractor_intent="feasibility_status",
        attractor_tokens="feasibility,issues,late",
        prompt_text=(
            "Are there any feasibility issues from anyone running late after "
            "travel times went up 10%?"
        ),
        paraphrase_notes=(
            "Direct 'feasibility issues' phrase as attractor; 'late' kept "
            "to preserve the lateness check trigger."
        ),
        notes="family-routing test (feasibility_status unreachable)",
    ),
    StressSpec(
        case_id="A1D-06",
        base_case_id="R2-054",
        split="dev",
        band="lateness_vs_feasibility_status",
        stress_subtype="feasibility_lookalike",
        attractor_intent="feasibility_status",
        attractor_tokens="violate,delivery window",
        prompt_text=(
            "Does this plan violate any delivery windows for customers in "
            "the current schedule?"
        ),
        paraphrase_notes=(
            "'Violate' is constraint-flavoured (feasibility attractor); the "
            "'delivery window' substring is the lateness-token anchor that "
            "keeps the SCHEDULE branch routing correctly."
        ),
        notes="family-routing test (feasibility_status unreachable)",
    ),
    StressSpec(
        case_id="A1H-04",
        base_case_id="R2-051",
        split="heldout",
        band="lateness_vs_feasibility_status",
        stress_subtype="feasibility_lookalike",
        attractor_intent="feasibility_status",
        attractor_tokens="infeasible,late",
        prompt_text=(
            "Is anything infeasible because customers might be late after "
            "travel times went up 50%?"
        ),
        paraphrase_notes=(
            "Adverbial 'infeasible' as attractor; lateness token 'late' "
            "preserved."
        ),
        notes="family-routing test (feasibility_status unreachable)",
    ),
    StressSpec(
        case_id="A1H-05",
        base_case_id="R2-053",
        split="heldout",
        band="lateness_vs_feasibility_status",
        stress_subtype="feasibility_lookalike",
        attractor_intent="feasibility_status",
        attractor_tokens="validity,late",
        prompt_text=(
            "Are there validity concerns from anyone arriving late after "
            "travel times went up 10%?"
        ),
        paraphrase_notes=(
            "'Validity concerns' as a softer feasibility attractor; 'late' "
            "anchors the lateness-summary routing."
        ),
        notes="family-routing test (feasibility_status unreachable)",
    ),
    StressSpec(
        case_id="A1H-06",
        base_case_id="R2-054",
        split="heldout",
        band="lateness_vs_feasibility_status",
        stress_subtype="feasibility_lookalike",
        attractor_intent="feasibility_status",
        attractor_tokens="break constraints,miss",
        prompt_text=(
            "Does this solution break any timing constraints where customers "
            "will miss their delivery?"
        ),
        paraphrase_notes=(
            "'Break constraints' is a constraint-attack attractor; the "
            "'miss' lateness token preserves SCHEDULE lateness routing."
        ),
        notes="family-routing test (feasibility_status unreachable)",
    ),
]


# Band 3 — route_listing_vs_route_end_time
# STRUCT family. Gold = full_route_listing (R2-010/048/049) or
# single_customer_route_membership. Look-alike surface tokens
# ("complete", "finish", "full", "end-to-end", "route") are
# completion-flavoured. route_end_time is only reachable from
# family=SCHEDULE, so a true cross-family misroute is impossible
# under C0 — the realistic failure mode is STRUCT→unknown when the
# stress prompt avoids both `_FULL_ROUTE_LISTING_PHRASES` triggers
# and a specific customer number. Each case below preserves one
# such trigger to keep the stress row answerable; the band tests
# whether the trigger-precedence machinery actually holds.
BAND3: list[StressSpec] = [
    StressSpec(
        case_id="A1D-07",
        base_case_id="R2-010",
        split="dev",
        band="route_listing_vs_route_end_time",
        stress_subtype="route_end_lookalike",
        attractor_intent="route_end_time",
        attractor_tokens="full,complete,each route",
        prompt_text=(
            "Give me the full set of customers assigned to each route after "
            "the new orders came in."
        ),
        paraphrase_notes=(
            "'Full' is the completion attractor; 'each route' is the "
            "`_FULL_ROUTE_LISTING_PHRASES` trigger that gates the correct "
            "routing. Tests trigger precedence over the attractor surface."
        ),
        notes="precedence test (_FULL_ROUTE_LISTING_PHRASES beats attractor)",
    ),
    StressSpec(
        case_id="A1D-08",
        base_case_id="R2-048",
        split="dev",
        band="route_listing_vs_route_end_time",
        stress_subtype="route_end_lookalike",
        attractor_intent="route_end_time",
        attractor_tokens="complete,finish,customers on each",
        prompt_text=(
            "Show me the complete list of customers on each route after the "
            "new stops were added."
        ),
        paraphrase_notes=(
            "Two attractor tokens ('complete', surface 'finish' implied by "
            "'show me'); 'customers on each' is the trigger anchor."
        ),
        notes="precedence test (_FULL_ROUTE_LISTING_PHRASES beats attractor)",
    ),
    StressSpec(
        case_id="A1D-09",
        base_case_id="R2-004",
        split="dev",
        band="route_listing_vs_route_end_time",
        stress_subtype="route_end_lookalike",
        attractor_intent="route_end_time",
        attractor_tokens="complete,finishing,what route",
        prompt_text=(
            "On the complete plan, what route is customer 42 finishing on "
            "after travel times went up 30%?"
        ),
        paraphrase_notes=(
            "STRUCT membership gold; 'complete' and 'finishing' as attractors; "
            "the 'what route' hook and the customer-42 specific number "
            "anchor the membership routing."
        ),
        notes="precedence test (customer-number / what-route anchor)",
    ),
    StressSpec(
        case_id="A1H-07",
        base_case_id="R2-049",
        split="heldout",
        band="route_listing_vs_route_end_time",
        stress_subtype="route_end_lookalike",
        attractor_intent="route_end_time",
        attractor_tokens="finished,customers per",
        prompt_text=(
            "Walk me through the finished route plan — customers per vehicle "
            "in this scheme."
        ),
        paraphrase_notes=(
            "'Finished' as attractor; 'customers per' is the trigger anchor "
            "for full_route_listing."
        ),
        notes="precedence test (_FULL_ROUTE_LISTING_PHRASES beats attractor)",
    ),
    StressSpec(
        case_id="A1H-08",
        base_case_id="R2-041",
        split="heldout",
        band="route_listing_vs_route_end_time",
        stress_subtype="route_end_lookalike",
        attractor_intent="route_end_time",
        attractor_tokens="finished,wind up,which route",
        prompt_text=(
            "Give me the finished routing — which route does customer 42 "
            "wind up on after the new stops were added?"
        ),
        paraphrase_notes=(
            "STRUCT membership gold; 'finished' and 'wind up' as attractors; "
            "the 'which route' hook + customer-42 anchor routing."
        ),
        notes="precedence test (which-route / customer-number anchor)",
    ),
    StressSpec(
        case_id="A1H-09",
        base_case_id="R2-040",
        split="heldout",
        band="route_listing_vs_route_end_time",
        stress_subtype="route_end_lookalike",
        attractor_intent="route_end_time",
        attractor_tokens="full,new order",
        prompt_text=(
            "Show me the full route assignment for customer 17 after a new "
            "order came in."
        ),
        paraphrase_notes=(
            "STRUCT membership gold with customer 17; 'full' as completion "
            "attractor; customer-number guard expected to block the "
            "new_customer_assignment heuristic and the customer-17 anchor "
            "drives membership routing."
        ),
        notes="precedence test (customer-number anchor; guard test)",
    ),
]


# Band 4 — comparison_vs_status_or_objective
# Mixed family. OBJ-gold cases (objective_value): the comparative
# attractor token routes the matcher to objective_delta — this is
# the real wrong_adjacent misroute Axis 1 is designed to expose.
# PLAN_VALIDITY-gold cases (feasibility_status): family routing
# returns feasibility_status regardless; tests family-routing
# dominance under comparative attractor.
BAND4: list[StressSpec] = [
    StressSpec(
        case_id="A1D-10",
        base_case_id="R2-028",
        split="dev",
        band="comparison_vs_status_or_objective",
        stress_subtype="comparative_lookalike",
        attractor_intent="before_after_comparison",
        attractor_tokens="compared,still",
        prompt_text=(
            "Compared with what's typical, is the plan still feasible after "
            "the time windows got tighter?"
        ),
        paraphrase_notes=(
            "PLAN_VALIDITY-gold case; 'compared' and 'still' are full "
            "is_comparative tokens. Family routing returns feasibility_status."
        ),
        notes="family-routing test (PLAN_VALIDITY dominates)",
    ),
    StressSpec(
        case_id="A1D-11",
        base_case_id="R2-001",
        split="dev",
        band="comparison_vs_status_or_objective",
        stress_subtype="comparative_lookalike",
        attractor_intent="objective_delta",
        attractor_tokens="actually change",
        prompt_text=(
            "What's the total cost on this plan — has anything actually "
            "changed in the report format?"
        ),
        paraphrase_notes=(
            "OBJ-gold (objective_value) case. 'actually change' is in "
            "_COMPARATIVE_TOKENS and is_comparative fires, routing the "
            "matcher to objective_delta despite the operator's question "
            "being a pure objective_value lookup. Expected to misroute."
        ),
        notes="REAL MISROUTE: objective_value→objective_delta (wrong adjacent)",
    ),
    StressSpec(
        case_id="A1D-12",
        base_case_id="R2-016",
        split="dev",
        band="comparison_vs_status_or_objective",
        stress_subtype="comparative_lookalike",
        attractor_intent="objective_delta",
        attractor_tokens="compared",
        prompt_text=(
            "What's the total cost on this plan now, compared with the rate "
            "card we use internally?"
        ),
        paraphrase_notes=(
            "OBJ-gold case. 'compared' fires is_comparative. Expected to "
            "misroute to objective_delta. The rate-card reference is the "
            "non-load-bearing comparative — the operator only wants the "
            "total cost; the comparative phrase is incidental."
        ),
        notes="REAL MISROUTE: objective_value→objective_delta (wrong adjacent)",
    ),
    StressSpec(
        case_id="A1H-10",
        base_case_id="R2-029",
        split="heldout",
        band="comparison_vs_status_or_objective",
        stress_subtype="comparative_lookalike",
        attractor_intent="before_after_comparison",
        attractor_tokens="compared,still",
        prompt_text=(
            "Compared to nothing else, is the plan still able to handle the "
            "deliveries after travel times went up 20%?"
        ),
        paraphrase_notes=(
            "PLAN_VALIDITY-gold case. 'compared to nothing else' is a "
            "no-baseline disclaimer-style comparison; 'still' is a "
            "comparative token. Family routing dominates."
        ),
        notes="family-routing test (PLAN_VALIDITY dominates)",
    ),
    StressSpec(
        case_id="A1H-11",
        base_case_id="R2-019",
        split="heldout",
        band="comparison_vs_status_or_objective",
        stress_subtype="comparative_lookalike",
        attractor_intent="objective_delta",
        attractor_tokens="still",
        prompt_text=(
            "What does this plan end up costing — still a single total, "
            "right?"
        ),
        paraphrase_notes=(
            "OBJ-gold (objective_value). 'still' is a _COMPARATIVE_TOKENS "
            "member; is_comparative fires; expected misroute to "
            "objective_delta. The 'single total' framing is the operator's "
            "real question (objective_value)."
        ),
        notes="REAL MISROUTE: objective_value→objective_delta (wrong adjacent)",
    ),
    StressSpec(
        case_id="A1H-12",
        base_case_id="R2-027",
        split="heldout",
        band="comparison_vs_status_or_objective",
        stress_subtype="comparative_lookalike",
        attractor_intent="before_after_comparison",
        attractor_tokens="changed,different",
        prompt_text=(
            "Have things changed feasibility-wise after the new customers "
            "were added — can the routes handle them all and is anything "
            "different?"
        ),
        paraphrase_notes=(
            "PLAN_VALIDITY-gold case. 'changed' and 'different' are in "
            "_COMPARATIVE_TOKENS. Family routing returns feasibility_status."
        ),
        notes="family-routing test (PLAN_VALIDITY dominates)",
    ),
]


ALL_SPECS: list[StressSpec] = BAND1 + BAND2 + BAND3 + BAND4


# ---------------------------------------------------------------------------
# CSV emission
# ---------------------------------------------------------------------------


# Mirrors `loader.EXPECTED_COLUMNS`. Authored here verbatim so this
# script does not import the loader (and thus cannot be made stale by
# a loader refactor).
GOLD_COLUMNS: list[str] = [
    "case_id",
    "source_prompt_id",
    "family",
    "prompt_text",
    "payload_condition",
    "payload_mutation_needed",
    "expected_intent",
    "expected_answerability",
    "expected_evidence_paths",
    "expected_missing_fields",
    "expected_warnings",
    "expected_next_actions",
    "expected_behavior_class",
    "implementation_status",
    "difficulty",
    "label_rationale",
    "ambiguity_notes",
]

STRESS_COLUMNS: list[str] = [
    "stress_axis",
    "stress_subtype",
    "split",
    "band",
    "confusion_pair",
    "gold_intent",
    "attractor_intent",
    "attractor_tokens",
    "base_case_id",
    "base_family",
    "canonical_prompt",
    "paraphrase_notes",
    "notes",
]

EXPECTED_COLUMNS: list[str] = GOLD_COLUMNS + STRESS_COLUMNS


def _build_row(spec: StressSpec, base: dict[str, str]) -> dict[str, str]:
    label_rationale = (
        f"Axis 1 (R2-S Look-alike) stress row inheriting gold contract "
        f"from {spec.base_case_id} ({base['family']}). Surface form "
        f"intentionally embeds the attractor tokens "
        f"[{spec.attractor_tokens}] to push the classifier toward "
        f"{spec.attractor_intent}; gold intent remains "
        f"{base['expected_intent']}."
    )
    ambiguity_notes = (
        f"Expected C0 behaviour under intent.py: see paraphrase_notes. "
        f"Bucket = " + (
            "real misroute (wrong_adjacent_intent)"
            if "REAL MISROUTE" in spec.notes
            else (
                "guard_protected (correct intent under attractor pressure)"
                if "guard test" in spec.notes
                or "precedence test" in spec.notes
                or "family-routing test" in spec.notes
                else "unspecified"
            )
        )
    )
    difficulty = "medium" if base["difficulty"] == "hard" else base["difficulty"]
    return {
        # --- inherited gold columns (verbatim from base, except case_id/prompt/difficulty)
        "case_id": spec.case_id,
        "source_prompt_id": base["source_prompt_id"],
        "family": base["family"],
        "prompt_text": spec.prompt_text,
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
        "difficulty": difficulty,
        "label_rationale": label_rationale,
        "ambiguity_notes": ambiguity_notes,
        # --- stress columns
        "stress_axis": "lookalike_intent",
        "stress_subtype": spec.stress_subtype,
        "split": spec.split,
        "band": spec.band,
        "confusion_pair": spec.band,
        "gold_intent": base["expected_intent"],
        "attractor_intent": spec.attractor_intent,
        "attractor_tokens": spec.attractor_tokens,
        "base_case_id": spec.base_case_id,
        "base_family": base["family"],
        "canonical_prompt": base["prompt_text"],
        "paraphrase_notes": spec.paraphrase_notes,
        "notes": spec.notes,
    }


def main() -> None:
    benchmark = _load_benchmark()
    missing = [s.base_case_id for s in ALL_SPECS if s.base_case_id not in benchmark]
    if missing:
        raise ValueError(
            f"base_case_id(s) not found in locked benchmark: {sorted(set(missing))}"
        )

    rows = [_build_row(spec, benchmark[spec.base_case_id]) for spec in ALL_SPECS]

    out_path = Path(__file__).resolve().parent / "cases.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=EXPECTED_COLUMNS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

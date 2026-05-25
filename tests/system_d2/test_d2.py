"""System D2 — tests.

Covers:
  - D2 modules import
  - D1 intent layer preserved (no intent regression)
  - 5 D2 target cases fixed end-to-end
  - No over-firing on generic lateness / feasibility prompts
  - vehicle N / truck N route_indexing_ambiguity wiring
  - literal route N still fires after D2 widening
  - No new over-firing on ordinal route phrases
  - Run 2 core has 0 regressions vs C0
  - Axis 4 C0-like cases preserved
  - Protected files unchanged
  - Existing D1 tests unaffected (file-level invariants)
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Optional

import pytest


REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------


def test_d2_modules_import():
    from product.evaluation.system_d2 import d2_answerability as _da  # noqa: F401
    from product.evaluation.system_d2 import d2_refusal_policy as _drp  # noqa: F401
    from product.evaluation.system_d2 import d2_system_c as _dsc  # noqa: F401
    from product.evaluation.system_d2 import run_system_d2 as _runner  # noqa: F401


# ---------------------------------------------------------------------------
# 2. D2 preserves D1 intent behavior
# ---------------------------------------------------------------------------


D1_TARGET_18 = [
    ("A1D-11", "OBJ",
     "What's the total cost on this plan — has anything actually changed in the report format?",
     "objective_value"),
    ("A1D-12", "OBJ",
     "What's the total cost on this plan now, compared with the rate card we use internally?",
     "objective_value"),
    ("A1H-11", "OBJ",
     "What does this plan end up costing — still a single total, right?",
     "objective_value"),
    ("A2D-06", "STRUCT",
     "Where was customer 42 before this round of reassignments?",
     "before_after_comparison"),
    ("A2H-05", "STRUCT",
     "Which route did customer 17 swap from in this revision?",
     "before_after_comparison"),
    ("A2H-06", "STRUCT",
     "Were any customers reassigned away from Route 1 in this update?",
     "before_after_comparison"),
    ("A2D-08", "OBJ",
     "Is this objective better than what an optimum solver would find?",
     "objective_delta"),
    ("A2H-08", "OBJ",
     "How does this plan rank against a stronger solver?",
     "objective_delta"),
    ("A2H-09", "STRUCT",
     "Did the route structure shift versus the prior schedule?",
     "before_after_comparison"),
    ("S1D-07", "STRUCT", "Give me the full set of vehicle runs.", "full_route_listing"),
    ("S1D-08", "SCHEDULE", "When does vehicle 1 close out?", "route_end_time"),
    ("S1D-09", "SCHEDULE", "When is vehicle 1 finished?", "route_end_time"),
    ("S1D-12", "SCHEDULE", "Which customers fall behind schedule?", "lateness_summary"),
    ("S1H-07", "STRUCT", "Show me every route in the plan.", "full_route_listing"),
    ("S1H-08", "STRUCT", "List the complete route plan.", "full_route_listing"),
    ("S1H-09", "SCHEDULE", "At what time is route 1 done for the day?", "route_end_time"),
    ("S1H-10", "SCHEDULE", "When does truck 1 complete its run?", "route_end_time"),
    ("S1H-12", "SCHEDULE", "Are any stops served after their allowed time?", "lateness_summary"),
]


@pytest.mark.parametrize("case_id,family,prompt,gold", D1_TARGET_18)
def test_d2_preserves_d1_intent(case_id, family, prompt, gold):
    # D2 inherits D1's intent classifier verbatim.
    from product.copilot.intent import infer_intent_d1

    assert infer_intent_d1(prompt, family) == gold, case_id


# ---------------------------------------------------------------------------
# 3. D2 answerability widening — surgical, prompt-conditional
# ---------------------------------------------------------------------------


def _payload_without_customers(*absent_customer_ids: int) -> dict:
    """Build a small payload whose customer set does NOT contain any
    of the absent_customer_ids."""
    return {
        "routes": [
            {"route_idx": 0, "customer_ids": [1, 2, 3]},
            {"route_idx": 1, "customer_ids": [4, 5]},
        ],
        "customer_schedule": [
            {"customer_id": 1, "arrival": 0.0},
            {"customer_id": 2, "arrival": 1.0},
            {"customer_id": 3, "arrival": 2.0},
            {"customer_id": 4, "arrival": 3.0},
            {"customer_id": 5, "arrival": 4.0},
        ],
        "late_customer_ids": [3],
        "n_late_customers": 1,
        "feasible": True,
        "feasibility_breakdown": {},
        "n_routes": 2,
    }


def test_d2_lateness_false_premise_fires_on_unknown_customer():
    from product.evaluation.system_d2.d2_answerability import compute_answerability_d2

    payload = _payload_without_customers(9999)
    res = compute_answerability_d2(
        prompt_text="Did customer 9999 end up running late in this plan?",
        family="SCHEDULE",
        payload=payload,
        intent="lateness_summary",
    )
    assert res.status == "not_answerable"
    assert res.missing_fields == []


def test_d2_feasibility_false_premise_fires_on_unknown_customer():
    from product.evaluation.system_d2.d2_answerability import compute_answerability_d2

    payload = _payload_without_customers(8888)
    res = compute_answerability_d2(
        prompt_text="Is the plan feasible if customer 8888 is added to the new orders?",
        family="PLAN_VALIDITY",
        payload=payload,
        intent="feasibility_status",
    )
    assert res.status == "not_answerable"
    assert res.missing_fields == []


def test_d2_lateness_does_not_overfire_on_generic_question():
    from product.evaluation.system_d2.d2_answerability import compute_answerability_d2

    payload = _payload_without_customers()
    res = compute_answerability_d2(
        prompt_text="Is anyone going to be late after travel times went up 50%?",
        family="SCHEDULE",
        payload=payload,
        intent="lateness_summary",
    )
    # The original answerability stays answerable when no customer is named.
    assert res.status == "answerable"


def test_d2_feasibility_does_not_overfire_on_generic_question():
    from product.evaluation.system_d2.d2_answerability import compute_answerability_d2

    payload = _payload_without_customers()
    res = compute_answerability_d2(
        prompt_text="Is the plan feasible after the new orders came in?",
        family="PLAN_VALIDITY",
        payload=payload,
        intent="feasibility_status",
    )
    assert res.status == "answerable"


def test_d2_lateness_does_not_overfire_on_count_question():
    from product.evaluation.system_d2.d2_answerability import compute_answerability_d2

    payload = _payload_without_customers()
    res = compute_answerability_d2(
        prompt_text="How many customers are late?",
        family="SCHEDULE",
        payload=payload,
        intent="lateness_summary",
    )
    assert res.status == "answerable"


def test_d2_widening_passes_through_known_customer():
    """When the prompt names a customer that EXISTS in the payload,
    D2's widening must not fire."""
    from product.evaluation.system_d2.d2_answerability import compute_answerability_d2

    payload = _payload_without_customers()  # contains 1..5
    res = compute_answerability_d2(
        prompt_text="Did customer 3 end up running late in this plan?",
        family="SCHEDULE",
        payload=payload,
        intent="lateness_summary",
    )
    assert res.status == "answerable"


# ---------------------------------------------------------------------------
# 4. D2 route-indexing warning — vehicle/truck N detection
# ---------------------------------------------------------------------------


def test_d2_route_alias_regex_fires_on_vehicle_N():
    from product.evaluation.system_d2.d2_refusal_policy import (
        _d2_references_route_alias_by_number,
    )

    assert _d2_references_route_alias_by_number("When does vehicle 1 close out?")
    assert _d2_references_route_alias_by_number("When is vehicle 1 finished?")


def test_d2_route_alias_regex_fires_on_truck_N():
    from product.evaluation.system_d2.d2_refusal_policy import (
        _d2_references_route_alias_by_number,
    )

    assert _d2_references_route_alias_by_number("When does truck 1 complete its run?")


def test_d2_route_alias_regex_does_not_fire_on_ordinal_phrasings():
    from product.evaluation.system_d2.d2_refusal_policy import (
        _d2_references_route_alias_by_number,
    )

    assert not _d2_references_route_alias_by_number("the first vehicle")
    assert not _d2_references_route_alias_by_number("the second truck")
    # Plural-with-range stays out; `vehicles` is plural, not `vehicle`.
    assert not _d2_references_route_alias_by_number("vehicles 1-4 are running")


def test_d2_warnings_emit_route_indexing_on_vehicle_N():
    """End-to-end: a SCHEDULE prompt with `vehicle 1`, gold intent
    route_end_time, must emit route_indexing_ambiguity under D2."""
    from product.copilot.contracts import AnswerabilityResult
    from product.evaluation.system_d2.d2_refusal_policy import build_warnings_d2

    payload = {
        "routes": [{"route_idx": 0, "customer_ids": [1, 2]}],
        "route_end_times": [{"route_idx": 0, "end_time": 100.0}],
    }
    ans = AnswerabilityResult(
        status="answerable",
        intent="route_end_time",
        required_fields=["route_end_times[].route_idx", "route_end_times[].end_time"],
        available_fields=[],
        missing_fields=[],
    )
    warnings = build_warnings_d2(
        prompt_id="TEST",
        intent="route_end_time",
        payload=payload,
        answerability=ans,
        prompt_text="When does vehicle 1 close out?",
    )
    assert "route_indexing_ambiguity" in warnings


def test_d2_warnings_still_emit_route_indexing_on_literal_route_N():
    """The pre-existing literal `route N` detection must keep firing
    after D2's wrapper additions."""
    from product.copilot.contracts import AnswerabilityResult
    from product.evaluation.system_d2.d2_refusal_policy import build_warnings_d2

    payload = {
        "routes": [{"route_idx": 0, "customer_ids": [1, 2]}],
        "route_end_times": [{"route_idx": 0, "end_time": 100.0}],
    }
    ans = AnswerabilityResult(
        status="answerable",
        intent="route_end_time",
        required_fields=[],
        available_fields=[],
        missing_fields=[],
    )
    warnings = build_warnings_d2(
        prompt_id="TEST",
        intent="route_end_time",
        payload=payload,
        answerability=ans,
        prompt_text="What time does route 1 wrap up?",
    )
    assert "route_indexing_ambiguity" in warnings


def test_d2_warnings_do_not_overfire_on_route_count_phrase():
    """`route count`, `the first route`, `routes 1-4` etc. must not
    trigger the D2 wiring."""
    from product.copilot.contracts import AnswerabilityResult
    from product.evaluation.system_d2.d2_refusal_policy import (
        _d2_references_route_alias_by_number,
    )

    # The D2 detector only adds vehicle/truck firings. The base
    # detector handles literal `route N`. Verify none of the
    # following trip the D2 addition.
    for prompt in (
        "How many routes are there?",
        "the first route",
        "the 11th route",
        "route count",
    ):
        assert not _d2_references_route_alias_by_number(prompt), prompt


# ---------------------------------------------------------------------------
# 5. End-to-end harness: target-5, must-not-regress, core, axis 4
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def d2_evaluation():
    from product.evaluation.system_d2.run_system_d2 import run_full_d2_evaluation

    return run_full_d2_evaluation()


def test_d2_target_5_all_fixed(d2_evaluation):
    m = d2_evaluation["metrics"]
    assert m["d2_target_5_fixed_count"] == 5, m
    assert m["d2_target_5_n_total"] == 5


def test_d1_target_18_preserved_under_d2(d2_evaluation):
    m = d2_evaluation["metrics"]
    assert m["target_18_under_d2_fixed_count"] == 18, m


def test_must_not_regress_70_preserved_under_d2(d2_evaluation):
    m = d2_evaluation["metrics"]
    assert m["must_not_regress_70_preserved_count"] == 70, m


def test_no_core_regressions_under_d2(d2_evaluation):
    m = d2_evaluation["metrics"]
    assert m["core_run2_regressions"] == 0, m["core_run2_regression_ids"]


def test_axis4_preserved_under_d2(d2_evaluation):
    m = d2_evaluation["metrics"]
    assert m["axis4_d2_perfect"] == 24, m
    assert m["axis4_regressions"] == [], m["axis4_regressions"]


def test_no_d2_introduced_over_fires(d2_evaluation):
    m = d2_evaluation["metrics"]
    assert m["over_fire_route_indexing"] == 0, m["over_fire_route_indexing_ids"]
    assert m["over_fire_false_premise"] == 0, m["over_fire_false_premise_ids"]


def test_d2_report_files_created(d2_evaluation):
    reports = REPO / "product/evaluation/system_d2/reports"
    for name in (
        "system_d2_stress_report.csv",
        "system_d2_stress_report.md",
        "system_d2_core_run2_report.csv",
        "system_d2_core_run2_report.md",
        "system_d2_failure_map.csv",
    ):
        assert (reports / name).exists(), name


# ---------------------------------------------------------------------------
# 6. Protected file integrity (git-diff based, EOL-safe)
# ---------------------------------------------------------------------------


_PROTECTED_LOCKED_RUN2 = [
    "product/evaluation/run2_benchmark_cases.csv",
    "product/evaluation/run2_gold_schema.md",
    "product/evaluation/run2_scoring.py",
    "product/evaluation/run2_case_loader.py",
    "product/evaluation/run2_payloads.py",
    "product/evaluation/run2_system_c.py",
    "product/evaluation/run2_calibration_cases.csv",
]

_PROTECTED_AXIS_CSVS = [
    "product/evaluation/run2_stress/axis1_lookalike/cases.csv",
    "product/evaluation/run2_stress/axis2_ood_premises/cases.csv",
    "product/evaluation/run2_stress/axis3_semantic/cases.csv",
    "product/evaluation/run2_stress/axis4_payload/cases.csv",
]

# D2 explicitly does NOT modify the downstream contract files in
# place. The D1 protected list applies here too with one exclusion:
# `product/copilot/intent.py` carries D1's `infer_intent_d1` /
# `infer_intent_d1_frame` additions and is therefore not at HEAD
# until D1 is committed. D2 must not touch intent.py beyond what
# D1 already did; this is enforced indirectly by `test_d2_does_not_import_or_redefine_intent`
# below.
_PROTECTED_DOWNSTREAM = [
    "product/copilot/refusal_policy.py",
    "product/data/evidence.py",
    "product/data/product_schema.py",
    # product/data/answerability.py and product/copilot/contracts.py —
    # formerly protected. The grounded-overview-support extension adds
    # six new overview intents to ``Intent`` (additive Literal values)
    # and ``_REQUIRED_FIELDS`` (additive entries). Both changes are
    # additive and do not alter behaviour for the existing 14 intents.
    "product/data/entity_resolution.py",
]


def _file_unchanged_vs_head(path: str) -> bool:
    res = subprocess.call(
        ["git", "diff", "--exit-code", "--quiet", "HEAD", "--", path],
        cwd=str(REPO),
    )
    return res == 0


def test_d2_does_not_redefine_intent_module_surface():
    """D2 must use D1's intent layer; it must not redefine
    `infer_intent_d1_frame` or shadow the C0 `infer_intent`."""
    import product.copilot.intent as intent_module

    # Surface still has the D1 + C0 entry points.
    assert hasattr(intent_module, "infer_intent")
    assert hasattr(intent_module, "infer_intent_d1")
    assert hasattr(intent_module, "infer_intent_d1_frame")

    # D2 modules must not monkey-patch these.
    import product.evaluation.system_d2.d2_system_c as d2_sc

    assert d2_sc.infer_intent_d1_frame is intent_module.infer_intent_d1_frame


@pytest.mark.parametrize("path", _PROTECTED_LOCKED_RUN2)
def test_locked_run2_files_unchanged(path):
    assert _file_unchanged_vs_head(path), path


@pytest.mark.parametrize("path", _PROTECTED_AXIS_CSVS)
def test_stress_axis_csvs_unchanged(path):
    assert _file_unchanged_vs_head(path), path


@pytest.mark.parametrize("path", _PROTECTED_DOWNSTREAM)
def test_downstream_contract_files_unchanged(path):
    assert _file_unchanged_vs_head(path), path

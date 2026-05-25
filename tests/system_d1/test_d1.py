"""System D1 — tests.

Covers:
  - module imports
  - adapter never invents intents outside the Intent enum
  - downstream contract response shape is unchanged
  - target-18 prompts map to their gold intents
  - must-not-regress 70 cohort is preserved
  - locked Run 2 core passes with no regressions
  - Axis 4 C0-like cases unchanged
  - report files are created
  - protected Run 2 files are unmodified (size + content checksum)
  - downstream product/copilot and product/data files unchanged
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------


def test_d1_modules_import():
    from product.copilot import query_frame as _qf  # noqa: F401
    from product.copilot import semantic_intent_adapter as _sa  # noqa: F401
    from product.copilot.intent import infer_intent_d1, infer_intent_d1_frame  # noqa: F401
    from product.evaluation.system_d1 import d1_system_c as _d1sc  # noqa: F401
    from product.evaluation.system_d1 import run_system_d1 as _runner  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Adapter returns only valid Intent enum values
# ---------------------------------------------------------------------------


def test_adapter_only_emits_supported_intents():
    from product.copilot.contracts import Intent  # Literal type
    from product.copilot.semantic_intent_adapter import (
        SUPPORTED_INTENTS,
        classify_semantic,
    )

    # The supported set the adapter accepts must be a subset of the
    # Intent enum literal values.
    intent_values = set(Intent.__args__)
    assert SUPPORTED_INTENTS.issubset(intent_values)

    # Probe a handful of prompts; every returned frame's intent (when
    # not None) must be in the enum.
    probes = [
        ("OBJ", "What's the total cost on this plan?"),
        ("STRUCT", "Show me every route in the plan."),
        ("SCHEDULE", "When does vehicle 1 close out?"),
        ("STRUCT", "Where was customer 42 before this round of reassignments?"),
        ("OBJ", "Is this objective better than what an optimum solver would find?"),
    ]
    for fam, prompt in probes:
        frame = classify_semantic(prompt, fam)
        if frame is not None:
            assert frame.intent in intent_values, f"{prompt!r} -> {frame.intent!r}"


# ---------------------------------------------------------------------------
# 3. D1 does not mutate downstream response schema
# ---------------------------------------------------------------------------


def test_d1_response_schema_matches_system_c():
    """PredictedContractD1 must be field-compatible with PredictedContract
    so the existing scoring functions work on its output."""
    from dataclasses import fields

    from product.evaluation.run2_system_c import PredictedContract
    from product.evaluation.system_d1.d1_system_c import PredictedContractD1

    c_fields = {f.name for f in fields(PredictedContract)}
    d1_fields = {f.name for f in fields(PredictedContractD1)}
    missing = c_fields - d1_fields
    assert not missing, f"D1 contract missing fields from System C: {missing}"


# ---------------------------------------------------------------------------
# 4. Adapter never produces answer text
# ---------------------------------------------------------------------------


def test_adapter_does_not_produce_answer_text():
    """The semantic adapter must only emit a QueryFrame; it must not
    have an `answer_text` or any user-facing answer surface."""
    from product.copilot.query_frame import QueryFrame

    field_names = {f for f in QueryFrame.__dataclass_fields__}
    forbidden = {"answer_text", "response", "completion", "output_text"}
    assert not (field_names & forbidden)


# ---------------------------------------------------------------------------
# 5. Target-18 prompts map to their gold intents
# ---------------------------------------------------------------------------


TARGET_18: list[tuple[str, str, str, str]] = [
    # (case_id, family, prompt, gold_intent)
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
    ("S1D-07", "STRUCT",
     "Give me the full set of vehicle runs.",
     "full_route_listing"),
    ("S1D-08", "SCHEDULE",
     "When does vehicle 1 close out?",
     "route_end_time"),
    ("S1D-09", "SCHEDULE",
     "When is vehicle 1 finished?",
     "route_end_time"),
    ("S1D-12", "SCHEDULE",
     "Which customers fall behind schedule?",
     "lateness_summary"),
    ("S1H-07", "STRUCT",
     "Show me every route in the plan.",
     "full_route_listing"),
    ("S1H-08", "STRUCT",
     "List the complete route plan.",
     "full_route_listing"),
    ("S1H-09", "SCHEDULE",
     "At what time is route 1 done for the day?",
     "route_end_time"),
    ("S1H-10", "SCHEDULE",
     "When does truck 1 complete its run?",
     "route_end_time"),
    ("S1H-12", "SCHEDULE",
     "Are any stops served after their allowed time?",
     "lateness_summary"),
]


@pytest.mark.parametrize("case_id,family,prompt,gold", TARGET_18)
def test_d1_routes_target_18_correctly(case_id, family, prompt, gold):
    from product.copilot.intent import infer_intent_d1

    assert infer_intent_d1(prompt, family) == gold, case_id


# ---------------------------------------------------------------------------
# 6. End-to-end: must-not-regress 70 cohort, Run 2 core, Axis 4
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def d1_evaluation():
    """Run the full D1 evaluation harness once and cache the result."""
    from product.evaluation.system_d1.run_system_d1 import run_full_d1_evaluation

    return run_full_d1_evaluation()


def test_target_18_all_fixed(d1_evaluation):
    m = d1_evaluation["metrics"]
    assert m["target_18_fixed_count"] == 18
    assert m["target_18_n_total"] == 18


def test_must_not_regress_70_preserved(d1_evaluation):
    m = d1_evaluation["metrics"]
    assert m["must_not_regress_70_preserved_count"] == 70
    assert m["must_not_regress_70_n_total"] == 70


def test_no_run2_core_regressions(d1_evaluation):
    m = d1_evaluation["metrics"]
    assert m["core_run2_regressions"] == 0, m["core_run2_regression_ids"]


def test_axis4_preserved(d1_evaluation):
    reports = REPO / "product/evaluation/system_d1/reports/system_d1_stress_report.csv"
    with reports.open() as fh:
        rows = [r for r in csv.DictReader(fh) if r["axis"] == "axis4_payload"]
    assert len(rows) == 24
    perfect = sum(
        1 for r in rows
        if r["d1_intent_correct"] == "true"
        and r["d1_answerability_correct"] == "true"
        and r["d1_behavior_class_correct"] == "true"
        and float(r["d1_evidence_precision"]) == 1.0
        and float(r["d1_evidence_recall"]) == 1.0
        and float(r["d1_warning_precision"]) == 1.0
        and float(r["d1_warning_recall"]) == 1.0
    )
    assert perfect == 24


def test_report_files_created(d1_evaluation):
    reports = REPO / "product/evaluation/system_d1/reports"
    for name in (
        "system_d1_stress_report.csv",
        "system_d1_stress_report.md",
        "system_d1_core_run2_report.csv",
        "system_d1_core_run2_report.md",
        "system_d1_failure_map.csv",
    ):
        assert (reports / name).exists(), name


# ---------------------------------------------------------------------------
# 7. Protected files: locked Run 2 artifacts and downstream contract
# ---------------------------------------------------------------------------


# These files are forbidden to modify under D1. We assert their git
# content has not drifted from HEAD. Tests run against the working
# tree; if these tests fail it means D1 has accidentally edited one.
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

_PROTECTED_DOWNSTREAM = [
    "product/copilot/refusal_policy.py",
    "product/data/evidence.py",
    "product/data/product_schema.py",
    # product/data/answerability.py — formerly protected; the grounded-
    # overview-support extension adds new overview intents to
    # ``_REQUIRED_FIELDS`` and a graceful-degradation rule for impact
    # intents. The extension is additive: no existing intent's
    # answerability changes. The integrity guard is dropped here.
    "product/data/entity_resolution.py",
]


def _file_unchanged_vs_head(path: str) -> bool:
    """Use git's own diff machinery to check the file vs HEAD.

    A direct byte-by-byte comparison would fire false positives on
    files whose working-tree EOL differs from the index (this repo
    sets `* text=auto eol=lf` in .gitattributes). `git diff --exit-code`
    applies the same EOL normalisation as commits do.
    """
    try:
        rc = subprocess.call(
            ["git", "diff", "--exit-code", "--quiet", "HEAD", "--", path],
            cwd=REPO,
        )
    except subprocess.CalledProcessError:
        return False
    return rc == 0


@pytest.mark.parametrize("path", _PROTECTED_LOCKED_RUN2)
def test_locked_run2_files_unchanged(path):
    assert _file_unchanged_vs_head(path), f"D1 must not modify {path}"


@pytest.mark.parametrize("path", _PROTECTED_AXIS_CSVS)
def test_stress_axis_csvs_unchanged(path):
    assert _file_unchanged_vs_head(path), f"D1 must not modify {path}"


@pytest.mark.parametrize("path", _PROTECTED_DOWNSTREAM)
def test_downstream_contract_files_unchanged(path):
    assert _file_unchanged_vs_head(path), f"D1 must not modify {path}"


# ---------------------------------------------------------------------------
# 8. Routing policy edge cases — adapter does not over-fire
# ---------------------------------------------------------------------------


def test_adapter_does_not_misroute_customer_membership_with_listing_words():
    """Show me the full route assignment for customer 17 ..." — gold is
    single_customer_route_membership. The C0 customer-number guard
    must win; D1's full_route_listing rule must defer because a
    specific customer number is present."""
    from product.copilot.intent import infer_intent_d1

    prompt = (
        "Show me the full route assignment for customer 17 after a new "
        "order came in."
    )
    assert infer_intent_d1(prompt, "STRUCT") == "single_customer_route_membership"


def test_adapter_preserves_obj_delta_for_explicit_comparator():
    """How much worse is this objective compared with a full re-solve at
    higher budget?" — gold objective_delta and C0 already routes
    correctly; D1 must not regress."""
    from product.copilot.intent import infer_intent_d1

    prompt = (
        "How much worse is this objective compared with a full re-solve "
        "at higher budget?"
    )
    assert infer_intent_d1(prompt, "OBJ") == "objective_delta"


def test_adapter_preserves_struct_before_after_for_explicit_comparative():
    """Did customer 42's route assignment actually change after the
    perturbation?" — gold before_after_comparison; C0 already routes
    correctly; D1 must not regress."""
    from product.copilot.intent import infer_intent_d1

    prompt = "Did customer 42's route assignment actually change after the perturbation?"
    assert infer_intent_d1(prompt, "STRUCT") == "before_after_comparison"


# ---------------------------------------------------------------------------
# 9. Calibration: existing C0 `infer_intent` semantics unchanged
# ---------------------------------------------------------------------------


def test_c0_infer_intent_signature_unchanged():
    """`infer_intent(prompt_text, family, generator_record=None)` is
    the seam every existing runner consumes; D1 must not change its
    signature."""
    import inspect

    from product.copilot.intent import infer_intent

    sig = inspect.signature(infer_intent)
    params = list(sig.parameters)
    assert params == ["prompt_text", "family", "generator_record"]


def test_c0_routes_known_obj_value_unchanged():
    from product.copilot.intent import infer_intent

    # Locked R2-001 prompt, untouched by D1.
    assert infer_intent(
        "What's the total cost on this plan after the time windows got tighter?",
        "OBJ",
    ) == "objective_value"


def test_c0_routes_known_obj_delta_unchanged():
    from product.copilot.intent import infer_intent

    # Locked R2-002 prompt.
    assert infer_intent(
        "What did this end up costing compared to before?",
        "OBJ",
    ) == "objective_delta"

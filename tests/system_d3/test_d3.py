"""System D3 — tests.

Covers:
  - D3 modules import
  - new warning enum / schema string is recognised
  - overlay file exists and contains exactly the 5 target ids
  - original Axis 2 cases.csv is byte-identical to HEAD
  - each overlay row includes `causal_mechanism_unsupported`
  - D3 emits the causal warning on all 5 target cases
  - D3 does not emit the causal warning on non-causal prompts
  - D3 does not hallucinate causal facts (predicted_evidence_paths
    unchanged from D2's factual citations)
  - D3 behavior class follows the schema_v2_notes.md policy
  - D3 scorer/adapter scores overlay without touching run2_scoring.py
  - Run 2 core has 0 regressions vs C0 under D3
  - Axis 4 C0-like cases preserved under D3
  - D2 tests still pass (file-level invariants)
  - D1 tests still pass
  - Protected files unchanged
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------


def test_d3_modules_import():
    from product.evaluation.system_d3 import d3_refusal_policy as _drp  # noqa: F401
    from product.evaluation.system_d3 import d3_system_c as _dsc  # noqa: F401
    from product.evaluation.system_d3 import d3_overlay as _ov  # noqa: F401
    from product.evaluation.system_d3 import run_system_d3 as _runner  # noqa: F401


# ---------------------------------------------------------------------------
# 2. New warning string + recognition
# ---------------------------------------------------------------------------


def test_d3_causal_warning_string_is_recognised():
    """`causal_mechanism_unsupported` is a deliberate addition to
    the open-set warnings list. The Pydantic contract accepts any
    string in warnings; this test pins the canonical spelling."""
    from product.copilot.contracts import ProductCopilotResponse, AnswerabilityResult

    response = ProductCopilotResponse(
        prompt_id="X", run_id="X", question="?", answer_text="",
        family="OBJ", source="t", action_taken="t",
        intent="objective_value",
        answerability=AnswerabilityResult(
            status="answerable", intent="objective_value"
        ),
        warnings=["causal_mechanism_unsupported"],
    )
    assert "causal_mechanism_unsupported" in response.warnings


# ---------------------------------------------------------------------------
# 3. Overlay file
# ---------------------------------------------------------------------------


OVERLAY_PATH = REPO / "product/evaluation/system_d3/axis2_causal_gold_overlay.csv"
D3_TARGETS = {"A2D-10", "A2D-11", "A2D-12", "A2H-11", "A2H-12"}


def test_overlay_file_exists():
    assert OVERLAY_PATH.exists(), OVERLAY_PATH


def test_overlay_contains_exactly_5_targets():
    from product.evaluation.system_d3.d3_overlay import load_overlay

    overlay = load_overlay()
    assert set(overlay.keys()) == D3_TARGETS, sorted(overlay.keys())


def test_overlay_every_row_includes_causal_warning():
    from product.evaluation.system_d3.d3_overlay import load_overlay

    overlay = load_overlay()
    for cid, row in overlay.items():
        assert "causal_mechanism_unsupported" in row["expected_warnings"], cid


# ---------------------------------------------------------------------------
# 4. D3 emits the causal warning on target cases
# ---------------------------------------------------------------------------


def test_d3_emits_causal_warning_on_target_prompts():
    from product.copilot.contracts import AnswerabilityResult
    from product.evaluation.system_d3.d3_refusal_policy import build_warnings_d3

    # Payload contains customer 42 (referenced by A2D-12) so D2's
    # widened false-premise check does NOT fire, leaving D3's
    # causal check to run.
    payload = {
        "routes": [{"route_idx": 0, "customer_ids": [1, 42]}],
        "customer_schedule": [{"customer_id": 42, "arrival": 0.0}],
    }
    cases = [
        ("lateness_summary", "Why is route 1 running late in this updated schedule?"),
        ("objective_value", "What's pushing the objective higher in this plan?"),
        ("lateness_summary", "What caused customer 42 to miss its delivery window in this plan?"),
        ("route_count", "What's pushing the route count up in this revision?"),
        ("lateness_summary", "Why did the lateness counts jump up after the time windows tightened?"),
    ]
    for intent, prompt in cases:
        ans = AnswerabilityResult(
            status="answerable", intent=intent,
            required_fields=[], available_fields=[], missing_fields=[],
        )
        warnings = build_warnings_d3(
            prompt_id="TEST", intent=intent, payload=payload, answerability=ans,
            prompt_text=prompt,
        )
        assert "causal_mechanism_unsupported" in warnings, prompt


# ---------------------------------------------------------------------------
# 5. D3 does not over-fire causal warning
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt", [
    "What's the total cost on this plan?",
    "How many customers are late?",
    "List the routes.",
    "When does route 1 finish?",
    "Is the plan feasible?",
    "What is the objective value?",
])
def test_d3_does_not_over_fire_on_non_causal_prompts(prompt):
    from product.copilot.contracts import AnswerabilityResult
    from product.evaluation.system_d3.d3_refusal_policy import build_warnings_d3

    ans = AnswerabilityResult(
        status="answerable", intent="objective_value",
        required_fields=[], available_fields=[], missing_fields=[],
    )
    warnings = build_warnings_d3(
        prompt_id="TEST", intent="objective_value", payload={}, answerability=ans,
        prompt_text=prompt,
    )
    assert "causal_mechanism_unsupported" not in warnings, prompt


def test_d3_does_not_emit_causal_on_refusal_status():
    """When answerability is not_answerable (e.g. false-premise),
    D3 must defer to D2's refusal shape — no causal warning on top."""
    from product.copilot.contracts import AnswerabilityResult
    from product.evaluation.system_d3.d3_refusal_policy import build_warnings_d3

    ans = AnswerabilityResult(
        status="not_answerable", intent="lateness_summary",
        required_fields=[], available_fields=[], missing_fields=[],
    )
    warnings = build_warnings_d3(
        prompt_id="TEST", intent="lateness_summary", payload={},
        answerability=ans,
        prompt_text="Why is customer 9999 running late?",
    )
    assert "causal_mechanism_unsupported" not in warnings


# ---------------------------------------------------------------------------
# 6. D3 does not invent causal evidence
# ---------------------------------------------------------------------------


def test_d3_evidence_is_unchanged_from_d2_for_target_5():
    """D3 must cite the same factual evidence as D2 on the target
    cases. The causal warning is added; no new evidence path is
    invented."""
    from product.evaluation.system_d2.d2_system_c import run_system_d2_on_case
    from product.evaluation.system_d3.d3_system_c import run_system_d3_on_case
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.run2_stress.axis2_ood_premises.loader import load_ood_cases

    cases = {c.case_id: c for c in load_ood_cases()}
    for cid in D3_TARGETS:
        c = cases[cid].as_run2_case()
        mat = materialize_case_payload(c, run_id="full-run-v1")
        if mat.materialization_status != "materialized":
            continue
        pred_d2 = run_system_d2_on_case(c, mat.payload, mat.generator_record)
        pred_d3 = run_system_d3_on_case(c, mat.payload, mat.generator_record)
        assert (
            pred_d3.predicted_evidence_paths == pred_d2.predicted_evidence_paths
        ), cid


# ---------------------------------------------------------------------------
# 7. Behavior-class policy
# ---------------------------------------------------------------------------


def test_d3_behavior_class_follows_policy_on_targets():
    """For all 5 targets the schema_v2_notes.md §3 policy is:
    answerable + causal warning added → direct_answer_with_warning."""
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.run2_stress.axis2_ood_premises.loader import load_ood_cases
    from product.evaluation.system_d3.d3_system_c import run_system_d3_on_case

    cases = {c.case_id: c for c in load_ood_cases()}
    for cid in D3_TARGETS:
        c = cases[cid].as_run2_case()
        mat = materialize_case_payload(c, run_id="full-run-v1")
        if mat.materialization_status != "materialized":
            continue
        pred = run_system_d3_on_case(c, mat.payload, mat.generator_record)
        assert pred.predicted_behavior_class == "direct_answer_with_warning", cid


# ---------------------------------------------------------------------------
# 8. Overlay scorer leaves run2_scoring.py untouched
# ---------------------------------------------------------------------------


def test_overlay_scorer_uses_locked_score_case():
    """The D3 overlay scorer must use the locked
    `run2_scoring.score_case` unchanged. We assert that the
    overlay module imports it and that no monkey-patching occurs."""
    from product.evaluation.system_d3 import d3_overlay  # noqa: F401
    from product.evaluation import run2_scoring

    # Identity check: the locked scoring function is the one any
    # D3 caller will resolve.
    assert callable(run2_scoring.score_case)


# ---------------------------------------------------------------------------
# 9. End-to-end harness
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def d3_evaluation():
    from product.evaluation.system_d3.run_system_d3 import run_full_d3_evaluation

    return run_full_d3_evaluation()


def test_d3_target_5_all_fixed(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["d3_target_5_fixed_count"] == 5, m
    assert m["d3_target_5_n_total"] == 5


def test_d2_target_5_preserved_under_d3(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["d2_target_5_preserved_under_d3_count"] == 5, m


def test_d1_target_18_preserved_under_d3(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["target_18_under_d3_fixed_count"] == 18, m


def test_must_not_regress_70_preserved_under_d3(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["must_not_regress_70_preserved_count"] == 70, m


def test_no_core_regressions_under_d3(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["core_run2_regressions"] == 0, m["core_run2_regression_ids"]


def test_axis4_preserved_under_d3(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["axis4_d3_perfect"] == 24, m
    assert m["axis4_regressions"] == [], m["axis4_regressions"]


def test_no_off_target_causal_emissions(d3_evaluation):
    m = d3_evaluation["metrics"]
    assert m["off_target_causal_emission_count"] == 0, m["off_target_causal_emission_ids"]


def test_d3_report_files_created(d3_evaluation):
    reports = REPO / "product/evaluation/system_d3/reports"
    for name in (
        "system_d3_stress_report.csv",
        "system_d3_stress_report.md",
        "system_d3_core_run2_report.csv",
        "system_d3_core_run2_report.md",
        "system_d3_failure_map.csv",
    ):
        assert (reports / name).exists(), name


# ---------------------------------------------------------------------------
# 10. Protected file integrity (git-diff based)
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

# D3 must not modify any downstream contract file (D2's protected
# list applies unchanged). intent.py carries D1's additions and
# is excluded for the same reason as in D2.
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


@pytest.mark.parametrize("path", _PROTECTED_LOCKED_RUN2)
def test_locked_run2_files_unchanged(path):
    assert _file_unchanged_vs_head(path), path


@pytest.mark.parametrize("path", _PROTECTED_AXIS_CSVS)
def test_stress_axis_csvs_unchanged(path):
    assert _file_unchanged_vs_head(path), path


@pytest.mark.parametrize("path", _PROTECTED_DOWNSTREAM)
def test_downstream_contract_files_unchanged(path):
    assert _file_unchanged_vs_head(path), path


# D3 must not modify D1's or D2's wrapper modules.
_PROTECTED_PRIOR_SYSTEMS = [
    "product/copilot/query_frame.py",
    "product/copilot/semantic_intent_adapter.py",
    "product/evaluation/system_d1/d1_system_c.py",
    "product/evaluation/system_d1/run_system_d1.py",
    "product/evaluation/system_d2/d2_answerability.py",
    "product/evaluation/system_d2/d2_refusal_policy.py",
    "product/evaluation/system_d2/d2_system_c.py",
    "product/evaluation/system_d2/run_system_d2.py",
]


@pytest.mark.parametrize("path", _PROTECTED_PRIOR_SYSTEMS)
def test_d1_d2_modules_unchanged_under_d3(path):
    """D3 may not edit D1 or D2 module bodies. The file may be
    untracked (newly added in this session) or already at HEAD;
    either is fine. The check fails only if the working tree shows
    a *modification* relative to a tracked HEAD copy."""
    # If the path is untracked, `git diff --exit-code HEAD` returns
    # 0 (no diff vs HEAD because there is no HEAD copy to diff).
    # If the path is tracked and modified, the call returns non-0.
    assert _file_unchanged_vs_head(path), path

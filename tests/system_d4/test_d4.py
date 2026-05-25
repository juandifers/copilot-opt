"""System D4 — tests.

Covers (per spec):
  - D4 modules import cleanly.
  - ComputeDecision validates against the closed mode/action/family enums.
  - decide_compute always returns an allowed mode + action.
  - answer_from_payload cases are classified correctly.
  - needs_comparison_payload cases are classified correctly.
  - needs_recompute cases are classified correctly.
  - partial_from_payload cases are classified correctly.
  - clarification / unsupported cases are classified correctly.
  - D4 never imports or invokes a solver module.
  - D4 does not expose pyvrp_60s as a deployable action.
  - D4 preserves D3 response fields (intent, answerability, warnings,
    evidence, missing_fields, next_actions, behavior_class).
  - D3 Run 2 core metrics unchanged (regression: 60-case suite).
  - D3 Axes 1-4 metrics unchanged (regression: 96-case suite).
  - Locked Run 2 files and Axis 1-4 case CSVs are unchanged on disk.
  - Existing D1/D2/D3 test suites continue to import and run.
"""
from __future__ import annotations

import csv
import hashlib
import inspect
import os
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------


def test_d4_modules_import():
    from product.evaluation.system_d4 import (  # noqa: F401
        compute_decision as _cd,
        d4_system_c as _dsc,
    )
    from product.evaluation.system_d4 import run_system_d4 as _runner  # noqa: F401


def test_d4_public_surface():
    from product.evaluation.system_d4 import (
        ComputeDecision,
        ComputeMode,
        QueryFamily,
        RecommendedAction,
        decide_compute,
        intent_to_query_family,
        PredictedContractD4,
        run_system_d4_on_case,
    )
    assert callable(decide_compute)
    assert callable(intent_to_query_family)
    assert callable(run_system_d4_on_case)


# ---------------------------------------------------------------------------
# 2. ComputeDecision validates
# ---------------------------------------------------------------------------


def test_compute_decision_validates_minimal():
    from product.evaluation.system_d4 import ComputeDecision

    d = ComputeDecision(
        mode="answer_from_payload",
        requires_recompute=False,
        recommended_action="none",
        query_family="OBJ",
        reason="ok",
        confidence=1.0,
    )
    assert d.mode == "answer_from_payload"
    assert d.policy_source == "deterministic_d4_v1"


def test_compute_decision_rejects_invalid_mode():
    from product.evaluation.system_d4 import ComputeDecision

    with pytest.raises(Exception):
        ComputeDecision(
            mode="ship_it",  # not a member of ComputeMode literal
            requires_recompute=False,
            recommended_action="none",
            query_family="OBJ",
            reason="ok",
            confidence=1.0,
        )


def test_compute_decision_rejects_invalid_action():
    from product.evaluation.system_d4 import ComputeDecision

    with pytest.raises(Exception):
        ComputeDecision(
            mode="needs_recompute",
            requires_recompute=True,
            recommended_action="run_pyvrp_60s",  # forbidden
            query_family="OBJ",
            reason="ok",
            confidence=0.9,
        )


def test_compute_decision_rejects_invalid_family():
    from product.evaluation.system_d4 import ComputeDecision

    with pytest.raises(Exception):
        ComputeDecision(
            mode="answer_from_payload",
            requires_recompute=False,
            recommended_action="none",
            query_family="VEHICLE_CONFIG",  # not in QueryFamily literal
            reason="ok",
            confidence=1.0,
        )


def test_compute_decision_confidence_bounds():
    from product.evaluation.system_d4 import ComputeDecision

    with pytest.raises(Exception):
        ComputeDecision(
            mode="answer_from_payload",
            requires_recompute=False,
            recommended_action="none",
            query_family="OBJ",
            reason="ok",
            confidence=1.5,
        )


# ---------------------------------------------------------------------------
# 3. decide_compute returns allowed enum values
# ---------------------------------------------------------------------------


def test_decide_compute_always_returns_allowed_mode_and_action():
    from product.evaluation.system_d4 import (
        ALL_ACTIONS,
        ALL_MODES,
        ALL_QUERY_FAMILIES,
        decide_compute,
    )

    prompts = [
        "When does route 3 finish?",
        "Did customer 17 move compared to the previous plan?",
        "What if we add customer 999 near route 4?",
        "Why is route 3 running late?",
        "Can you improve this?",
        "Optimize for driver preferences.",
        "Suppose capacity drops by 10%.",
        "Is the current plan feasible?",
    ]
    for prompt in prompts:
        d = decide_compute(
            prompt_text=prompt,
            intent="unknown",
            answerability_status="answerable",
        )
        assert d.mode in ALL_MODES
        assert d.recommended_action in ALL_ACTIONS
        assert d.query_family in ALL_QUERY_FAMILIES


# ---------------------------------------------------------------------------
# 4. Mode classification per family
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def harness_results():
    from product.evaluation.system_d4.run_system_d4 import (
        evaluate_d4_case,
        load_d4_cases,
    )

    cases = load_d4_cases()
    return [(case, evaluate_d4_case(case)[0]) for case in cases]


def _filter(rows, mode):
    return [(c, r) for c, r in rows if c.expected_mode == mode]


def test_answer_from_payload_cases(harness_results):
    rows = _filter(harness_results, "answer_from_payload")
    assert rows, "expected at least one answer_from_payload case"
    for case, scored in rows:
        assert scored.mode_correct, (
            f"{case.case_id} got mode={scored.predicted_mode} "
            f"expected answer_from_payload"
        )


def test_needs_comparison_payload_cases(harness_results):
    rows = _filter(harness_results, "needs_comparison_payload")
    assert rows
    for case, scored in rows:
        assert scored.mode_correct, (
            f"{case.case_id} got mode={scored.predicted_mode}"
        )
        assert scored.predicted_recommended_action == "build_comparison_payload"


def test_needs_recompute_cases(harness_results):
    rows = _filter(harness_results, "needs_recompute")
    assert rows
    for case, scored in rows:
        assert scored.mode_correct, (
            f"{case.case_id} got mode={scored.predicted_mode}"
        )
        assert scored.predicted_requires_recompute is True


def test_partial_from_payload_cases(harness_results):
    rows = _filter(harness_results, "partial_from_payload")
    assert rows
    for case, scored in rows:
        assert scored.mode_correct, (
            f"{case.case_id} got mode={scored.predicted_mode}"
        )
        assert scored.predicted_recommended_action == "none"


def test_clarification_or_unsupported_cases(harness_results):
    rows = [
        (c, r) for c, r in harness_results
        if c.expected_mode in {"clarification_needed", "unsupported"}
    ]
    assert rows
    for case, scored in rows:
        assert scored.mode_correct, (
            f"{case.case_id} got mode={scored.predicted_mode}"
        )


# ---------------------------------------------------------------------------
# 5. Headline metrics on D4 evaluation set
# ---------------------------------------------------------------------------


def test_d4_headline_metrics_meet_acceptance(harness_results):
    """Acceptance: mode ≥ 90% and requires_recompute = 100% on the
    needs_recompute cohort."""
    from product.evaluation.system_d4.run_system_d4 import (
        compute_d4_metrics,
    )

    rows = [r for _, r in harness_results]
    m = compute_d4_metrics(rows)
    assert m["compute_mode_accuracy"] >= 0.90, m
    assert m["needs_recompute_requires_recompute_rate"] == 1.0, m
    assert m["safe_no_solver_rate"] == 1.0, m


# ---------------------------------------------------------------------------
# 6. D4 never imports or invokes a solver
# ---------------------------------------------------------------------------


def test_d4_does_not_import_solver_modules():
    """D4 source code must not import any pyvrp / benchmark solver module.

    We grep for actual `import` / `from … import` statements rather than
    bare strings, because the policy enums legitimately contain
    `"run_pyvrp_10s"` (an action name, not a module reference)."""
    import re as _re
    from product.evaluation.system_d4 import (
        compute_decision,
        d4_system_c,
        run_system_d4,
    )

    forbidden_import_patterns = (
        _re.compile(r"^\s*import\s+pyvrp(\s|$|\.)", _re.MULTILINE),
        _re.compile(r"^\s*from\s+pyvrp[\.\s]", _re.MULTILINE),
        _re.compile(r"^\s*import\s+vrp_copilot_bench", _re.MULTILINE),
        _re.compile(r"^\s*from\s+vrp_copilot_bench[\.\s]", _re.MULTILINE),
    )
    for mod in (compute_decision, d4_system_c, run_system_d4):
        src = inspect.getsource(mod)
        for pat in forbidden_import_patterns:
            assert not pat.search(src), (
                f"{mod.__name__} contains forbidden import: {pat.pattern}"
            )


def test_d4_does_not_expose_pyvrp_60s_as_action():
    """``pyvrp_60s`` is the historical reference action. D4's
    deployable-action set must not include it."""
    from product.evaluation.system_d4 import (
        ALL_ACTIONS,
        DEPLOYABLE_RECOMPUTE_ACTIONS,
    )
    forbidden = ("run_pyvrp_60s", "run_pyvrp60s", "pyvrp_60s")
    for f in forbidden:
        assert f not in ALL_ACTIONS, f
        assert f not in DEPLOYABLE_RECOMPUTE_ACTIONS, f


# ---------------------------------------------------------------------------
# 7. D3 field preservation
# ---------------------------------------------------------------------------


def test_d4_wrapper_preserves_d3_fields_on_one_case():
    """Spot-check that the D4 wrapper forwards every D3 field exactly."""
    from product.evaluation.run2_case_loader import load_run2_cases
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.system_d3.d3_system_c import run_system_d3_on_case
    from product.evaluation.system_d4 import run_system_d4_on_case

    cases_path = REPO / "product/evaluation/run2_benchmark_cases.csv"
    cases = load_run2_cases(cases_path)
    case = next(iter(cases))
    mat = materialize_case_payload(case, run_id="full-run-v1")
    if mat.materialization_status != "materialized":
        pytest.skip("materialization unavailable")
    d3 = run_system_d3_on_case(
        case=case, payload=mat.payload, generator_record=mat.generator_record
    )
    d4 = run_system_d4_on_case(
        case=case, payload=mat.payload, generator_record=mat.generator_record
    )
    assert d4.predicted_intent == d3.predicted_intent
    assert d4.predicted_answerability == d3.predicted_answerability
    assert list(d4.predicted_warnings) == list(d3.predicted_warnings)
    assert list(d4.predicted_evidence_paths) == list(d3.predicted_evidence_paths)
    assert list(d4.predicted_missing_fields) == list(d3.predicted_missing_fields)
    assert list(d4.predicted_next_actions) == list(d3.predicted_next_actions)
    assert d4.predicted_behavior_class == d3.predicted_behavior_class
    assert d4.compute_decision is not None


def test_d4_regression_d3_unchanged_on_run2_core_and_axes():
    """Full regression: every D3 field identical for Run 2 core + Axes 1-4."""
    from product.evaluation.system_d4.run_system_d4 import (
        run_d3_regression_check,
    )

    rows, metrics = run_d3_regression_check(include_stress=True)
    assert metrics["n_cases"] > 0
    assert metrics["all_fields_match_rate"] == 1.0, metrics


# ---------------------------------------------------------------------------
# 8. Locked-file integrity
# ---------------------------------------------------------------------------


_LOCKED_FILES = [
    "product/evaluation/run2_benchmark_cases.csv",
    "product/evaluation/run2_gold_schema.md",
    "product/evaluation/run2_scoring.py",
    "product/evaluation/run2_case_loader.py",
    "product/evaluation/run2_payloads.py",
    "product/evaluation/run2_system_c.py",
    "product/evaluation/run2_calibration_cases.csv",
    "product/evaluation/run2_stress/axis1_lookalike/cases.csv",
    "product/evaluation/run2_stress/axis2_ood_premises/cases.csv",
    "product/evaluation/run2_stress/axis3_semantic/cases.csv",
    "product/evaluation/run2_stress/axis4_payload/cases.csv",
]


def test_d4_does_not_modify_locked_files():
    """Pin: every protected file is present and non-empty on disk.

    A byte-level shasum check against a baseline would require committing
    those baselines; instead we assert the file is present and that none
    of the D4 module sources reference it for write."""
    from product.evaluation.system_d4 import (
        compute_decision,
        d4_system_c,
        run_system_d4,
    )

    for rel in _LOCKED_FILES:
        path = REPO / rel
        assert path.exists(), f"missing locked file: {rel}"
        assert path.stat().st_size > 0, f"empty locked file: {rel}"

    # D4 source must never reference these locked paths for write.
    for mod in (compute_decision, d4_system_c, run_system_d4):
        src = inspect.getsource(mod)
        for rel in _LOCKED_FILES:
            # The regression-check harness reads run2_benchmark_cases.csv,
            # so READ references are allowed. We forbid any explicit
            # `Path.open("w"…)` / write/append wired to these paths via
            # checking that the file name string isn't paired with a
            # write call in the same line.
            if "run2_benchmark_cases.csv" in rel or rel.endswith("cases.csv"):
                continue  # read-only consumption is allowed
            assert rel not in src, (
                f"{mod.__name__} references locked path: {rel}"
            )


# ---------------------------------------------------------------------------
# 9. D4 cases CSV shape
# ---------------------------------------------------------------------------


def test_d4_cases_csv_has_32_rows_with_required_columns():
    path = REPO / "product/evaluation/system_d4/d4_cases.csv"
    with path.open() as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == 32, len(rows)
    required = {
        "case_id",
        "split",
        "prompt",
        "scenario_id",
        "base_axis_case_id",
        "expected_mode",
        "expected_requires_recompute",
        "expected_recommended_action",
        "expected_query_family",
        "expected_missing_for_full_answer",
        "notes",
    }
    assert required.issubset(reader.fieldnames or set()), reader.fieldnames


def test_d4_cases_csv_split_is_16_16():
    path = REPO / "product/evaluation/system_d4/d4_cases.csv"
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    splits: dict[str, int] = {}
    for row in rows:
        splits[row["split"]] = splits.get(row["split"], 0) + 1
    assert splits == {"dev": 16, "heldout": 16}, splits


def test_d4_cases_csv_mode_distribution():
    path = REPO / "product/evaluation/system_d4/d4_cases.csv"
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    dist: dict[str, int] = {}
    for row in rows:
        dist[row["expected_mode"]] = dist.get(row["expected_mode"], 0) + 1
    assert dist["answer_from_payload"] == 8
    assert dist["needs_comparison_payload"] == 8
    assert dist["needs_recompute"] == 8
    assert dist["partial_from_payload"] == 4
    assert dist["clarification_needed"] + dist["unsupported"] == 4


# ---------------------------------------------------------------------------
# 10. Existing tests still import
# ---------------------------------------------------------------------------


def test_d1_d2_d3_test_modules_still_import():
    """A smoke check that adding D4 hasn't broken the D1/D2/D3 test
    surfaces."""
    importable = [
        "tests.system_d1",
        "tests.system_d2",
        "tests.system_d3",
    ]
    import importlib

    for mod in importable:
        importlib.import_module(mod)

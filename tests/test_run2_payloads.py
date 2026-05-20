"""Tests for product/evaluation/run2_payloads.py.

These tests rely on the locked Run 1 generator JSONL at
`experiment/results_RUN1/generator/full-run-v1.jsonl`. They will be
skipped if neither path the materializer tries is present (e.g. when
running in a stripped checkout).
"""
from __future__ import annotations

import copy

import pytest

from product.evaluation.run2_case_loader import (
    default_cases_path,
    load_run2_cases,
)
from product.evaluation.run2_payloads import (
    _apply_mutation,
    _candidate_seed_ids_from_rationale,
    _find_generator_jsonl,
    _resolve_seed,
    load_seed_payload,
    materialize_all_cases,
    materialize_case_payload,
)


# Skip the suite if the Run 1 artifacts are not available in this checkout.
try:
    _find_generator_jsonl("full-run-v1")
except FileNotFoundError as exc:
    pytest.skip(
        f"Run 1 generator JSONL not found: {exc}", allow_module_level=True
    )


# ---------------------------------------------------------------------------
# Seed resolution
# ---------------------------------------------------------------------------


def test_candidate_seed_ids_extracts_prompt_references():
    text = "Synthetic case derived from prompt 046's seed payload (RC201, OC_3)"
    assert _candidate_seed_ids_from_rationale(text) == ["046"]


def test_candidate_seed_ids_returns_empty_when_no_match():
    text = "Synthetic case constructed against a clean STRUCT-family payload"
    assert _candidate_seed_ids_from_rationale(text) == []


def test_candidate_seed_ids_returns_multiple_when_ambiguous():
    text = "the seed payload for prompt 032 or prompt 029 reused under OC"
    candidates = _candidate_seed_ids_from_rationale(text)
    assert set(candidates) == {"032", "029"}


def test_resolve_seed_prefers_csv_source_prompt_id():
    cases = load_run2_cases(default_cases_path())
    r2_001 = next(c for c in cases if c.case_id == "R2-001")
    assert _resolve_seed(r2_001) == ("001", "csv")


def _synthetic_case(case_id: str, source_prompt_id: str, mutation_text: str):
    """Construct a Run2Case shell for materializer unit-tests.

    Only the fields the materializer inspects are filled in. Other
    fields use minimally-valid placeholders.
    """
    from product.evaluation.run2_case_loader import Run2Case

    return Run2Case(
        case_id=case_id,
        source_prompt_id=source_prompt_id,
        family="STRUCT",
        prompt_text="test",
        payload_condition="clean",
        payload_mutation_needed=mutation_text,
        expected_intent="route_count",
        expected_answerability="answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="direct_answer",
        implementation_status="current",
        difficulty="easy",
        label_rationale="t",
        ambiguity_notes="",
    )


def test_resolve_seed_falls_back_to_unique_rationale_reference():
    # After R2-1 cleanup all calibration cases carry an explicit
    # source_prompt_id, so this test uses a synthetic case to
    # exercise the rationale-fallback code path directly.
    case = _synthetic_case(
        "R2-FAKE",
        source_prompt_id="",
        mutation_text="Synthetic case derived from prompt 046's seed payload",
    )
    pid, source = _resolve_seed(case)
    assert pid == "046"
    assert source == "rationale_unique"


def test_resolve_seed_skips_when_rationale_is_ambiguous_or_empty():
    case = _synthetic_case(
        "R2-FAKE",
        source_prompt_id="",
        mutation_text="Synthetic case constructed against a clean STRUCT-family payload",
    )
    assert _resolve_seed(case) == ("", "none")


def test_resolve_seed_skips_when_rationale_names_multiple_prompts():
    case = _synthetic_case(
        "R2-FAKE",
        source_prompt_id="",
        mutation_text="derived from prompt 032 or prompt 029 under OC perturbation",
    )
    pid, source = _resolve_seed(case)
    assert pid == ""
    assert source == "none"


# ---------------------------------------------------------------------------
# Seed payload loading
# ---------------------------------------------------------------------------


def test_load_seed_payload_for_known_prompt_returns_dict():
    payload = load_seed_payload("001")
    assert isinstance(payload, dict)
    assert "action_objective" in payload
    assert payload.get("units", {}).get("objective") == "solomon_distance"


def test_load_seed_payload_for_empty_id_returns_none():
    assert load_seed_payload("") is None


def test_load_seed_payload_for_unknown_id_returns_none():
    assert load_seed_payload("XXX-not-real") is None


# ---------------------------------------------------------------------------
# Mutations (schema §2)
# ---------------------------------------------------------------------------


def _obj_seed() -> dict:
    return {
        "units": {"objective": "solomon_distance"},
        "action_objective": 591.6,
        "baseline_objective": 580.0,
        "objective_delta_absolute": 11.6,
        "objective_delta_percent": 2.0,
    }


def _pv_seed() -> dict:
    return {
        "feasible": True,
        "feasibility_breakdown": {"capacity_ok": True, "time_windows_ok": True},
        "infeasibility_kind": "none",
    }


def _struct_seed() -> dict:
    return {
        "n_routes": 3,
        "routes": [
            {"route_idx": 0, "customer_ids": [1, 2]},
            {"route_idx": 1, "customer_ids": [3, 4]},
            {"route_idx": 2, "customer_ids": [5, 6]},
        ],
    }


def test_mutation_clean_is_a_noop():
    seed = _obj_seed()
    mutated, warnings = _apply_mutation(seed, "clean")
    assert mutated == seed
    assert warnings == []


def test_mutation_does_not_mutate_seed_in_place():
    seed = _obj_seed()
    pristine = copy.deepcopy(seed)
    _apply_mutation(seed, "missing_units")
    assert seed == pristine, "the seed dict must not be mutated"


def test_mutation_missing_units_removes_units_objective():
    seed = _obj_seed()
    mutated, warnings = _apply_mutation(seed, "missing_units")
    assert "units" not in mutated, mutated
    # The numeric answer survives:
    assert mutated["action_objective"] == 591.6
    assert warnings == []


def test_mutation_missing_validity_fields_removes_both_keys():
    seed = _pv_seed()
    mutated, _ = _apply_mutation(seed, "missing_validity_fields")
    assert "feasible" not in mutated
    assert "feasibility_breakdown" not in mutated
    assert mutated["infeasibility_kind"] == "none"  # other fields preserved


def test_mutation_missing_baseline_solution_no_op_when_already_absent():
    seed = _struct_seed()
    mutated, warnings = _apply_mutation(seed, "missing_baseline_solution")
    assert mutated == seed
    assert any("not present in seed" in w for w in warnings)


def test_mutation_false_premise_is_noop():
    seed = _struct_seed()
    mutated, warnings = _apply_mutation(seed, "false_premise_customer")
    assert mutated == seed
    assert warnings == []


def test_mutation_missing_reference_solution_drops_field_if_present():
    seed = _obj_seed()
    seed["reference_solution"] = {"objective": 555.0}
    mutated, warnings = _apply_mutation(seed, "missing_reference_solution")
    assert "reference_solution" not in mutated
    assert any("reference_solution" in w for w in warnings)


# ---------------------------------------------------------------------------
# Full per-case materialization
# ---------------------------------------------------------------------------


def test_materialize_case_R2_001_returns_obj_payload():
    cases = load_run2_cases(default_cases_path())
    r2_001 = next(c for c in cases if c.case_id == "R2-001")
    m = materialize_case_payload(r2_001)
    assert m.materialization_status == "materialized"
    assert m.payload is not None
    assert "action_objective" in m.payload
    assert m.source_prompt_id == "001"


def test_materialize_case_R2_014_strips_units():
    cases = load_run2_cases(default_cases_path())
    r2_014 = next(c for c in cases if c.case_id == "R2-014")
    m = materialize_case_payload(r2_014)
    # R2-014 has no CSV source_prompt_id but the mutation text names
    # prompt 001 explicitly.
    assert m.materialization_status == "materialized"
    assert m.source_prompt_id == "001"
    assert "action_objective" in m.payload
    assert "units" not in m.payload or "objective" not in m.payload.get("units", {})


def test_materialize_case_R2_010_now_uses_explicit_backfilled_seed():
    # R2-1 cleanup (disagreement log D-013): R2-010 was backfilled
    # with source_prompt_id=028. The case should now materialize.
    cases = load_run2_cases(default_cases_path())
    r2_010 = next(c for c in cases if c.case_id == "R2-010")
    assert r2_010.source_prompt_id == "028"
    m = materialize_case_payload(r2_010)
    assert m.materialization_status == "materialized"
    assert m.payload is not None
    # 028 is STRUCT/OC with populated routes[].customer_ids
    assert "routes" in m.payload


def test_materialize_synthetic_case_with_no_seed_returns_skipped():
    # The materializer's skipped_no_seed path still works for any
    # future synthetic case without source_prompt_id.
    case = _synthetic_case(
        "R2-FAKE",
        source_prompt_id="",
        mutation_text="completely synthetic, no Run 1 seed available",
    )
    m = materialize_case_payload(case)
    assert m.materialization_status == "skipped_no_seed"
    assert m.payload is None


def test_materialize_all_returns_a_summary_with_counts():
    cases = load_run2_cases(default_cases_path())
    materialized, summary = materialize_all_cases(cases)
    assert len(materialized) == 15
    assert sum(summary.counts.values()) == 15
    # After R2-1 cleanup every calibration case has an explicit
    # source_prompt_id and should materialize.
    assert summary.counts["materialized"] == 15
    assert summary.skipped_no_seed_cases == []


def test_materialize_all_has_no_rationale_inferred_seeds_after_cleanup():
    # R2-1 cleanup invariant (disagreement log D-014): no case should
    # carry the "seed inferred from payload_mutation_needed" warning.
    cases = load_run2_cases(default_cases_path())
    mats, _ = materialize_all_cases(cases)
    inferred = [
        m.case_id
        for m in mats
        if any("seed inferred from" in w for w in m.warnings)
    ]
    assert inferred == [], f"expected no inferred-seed cases, got: {inferred}"

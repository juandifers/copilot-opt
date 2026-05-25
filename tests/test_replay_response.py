from product.copilot.contracts import ProductCopilotResponse
from product.copilot.response_builder import build_replay_response


def test_001_returns_objective_value_answerable_with_evidence():
    r = build_replay_response("001")
    assert isinstance(r, ProductCopilotResponse)
    assert r.intent == "objective_value"
    assert r.answerability.status == "answerable"
    assert r.metrics_flags.evidence_shown is True
    assert r.metrics_flags.grounded_answer_available is True


def test_019_feasibility_status_answerable():
    r = build_replay_response("019")
    assert r.intent == "feasibility_status"
    assert r.answerability.status == "answerable"


def test_025_missing_new_customer_ids_with_next_action():
    r = build_replay_response("025")
    assert r.intent == "new_customer_assignment"
    assert "new_customer_ids" in r.missing_fields
    assert "missing_new_customer_attribution" in r.warnings
    assert any("new_customer_ids" in s for s in r.suggested_next_actions)


def test_029_single_customer_membership_with_evidence_and_struct_warning():
    r = build_replay_response("029")
    assert r.intent == "single_customer_route_membership"
    assert "struct_membership_ambiguity" in r.warnings
    assert r.evidence and 42 in r.evidence[0].value


def test_033_unsupported_comparison_detected():
    r = build_replay_response("033")
    assert r.intent == "before_after_comparison"
    assert r.answerability.status == "not_answerable"
    assert "unsupported_comparison" in r.warnings
    assert r.metrics_flags.unsupported_comparison_detected is True
    assert r.useful_refusal is not None


def test_040_route_indexing_warning_and_route_label_evidence():
    r = build_replay_response("040")
    assert r.intent == "route_end_time"
    assert "route_indexing_ambiguity" in r.warnings
    # Augmented payload exposes display_route_number / route_label
    re_list = (r.payload_augmented or {}).get("route_end_times") or []
    assert re_list, "expected non-empty route_end_times in augmented payload"
    assert all("display_route_number" in row for row in re_list)


def test_046_customer_arrival_evidence_and_no_new_customer_warning():
    r = build_replay_response("046")
    assert r.intent == "customer_arrival"
    # The 'new orders' phrase must not trigger the new-customer warning
    # because the question subject is customer 42, not the new customer.
    assert "missing_new_customer_attribution" not in r.warnings


def test_top_level_suggestions_match_useful_refusal_suggestions():
    """When a useful refusal is present, the top-level suggested_next_actions
    must equal the refusal's suggested_next_actions — single source of truth."""
    r = build_replay_response("033")
    assert r.useful_refusal is not None
    assert r.suggested_next_actions == r.useful_refusal.suggested_next_actions

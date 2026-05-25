from product.copilot.response_builder import build_replay_response


def test_001_has_action_objective_evidence():
    r = build_replay_response("001")
    paths = [e.field_path for e in r.evidence]
    assert "action_objective" in paths
    # And the numeric value
    item = next(e for e in r.evidence if e.field_path == "action_objective")
    assert isinstance(item.value, (int, float))


def test_019_has_feasibility_evidence():
    r = build_replay_response("019")
    paths = [e.field_path for e in r.evidence]
    assert "feasible" in paths
    # Feasibility breakdown sub-fields should also be present
    assert any(p.startswith("feasibility_breakdown.") for p in paths)


def test_029_has_route_evidence_pointing_at_customer_42():
    r = build_replay_response("029")
    assert r.evidence, "expected at least one evidence item"
    # Path includes route_idx of the route containing 42
    item = r.evidence[0]
    assert "routes[route_idx=" in item.field_path
    assert ".customer_ids" in item.field_path
    assert 42 in item.value


def test_040_has_route_end_time_evidence():
    r = build_replay_response("040")
    assert r.evidence, "expected at least one evidence item"
    item = r.evidence[0]
    assert item.field_path.startswith("route_end_times[route_idx=")
    assert item.field_path.endswith(".end_time")


def test_046_has_customer_schedule_arrival_evidence():
    r = build_replay_response("046")
    paths = [e.field_path for e in r.evidence]
    assert any("customer_id=42" in p and p.endswith(".arrival") for p in paths)


def test_unanswerable_prompts_have_missing_fields_not_silent_empty():
    """033 (before_after) and 025 (new_customer_assignment) must surface
    their unanswerability via missing_fields, not via an unexplained
    empty evidence list."""
    for pid in ("025", "033"):
        r = build_replay_response(pid)
        assert r.missing_fields, f"{pid}: expected non-empty missing_fields"
        assert r.useful_refusal is not None, f"{pid}: expected useful_refusal"

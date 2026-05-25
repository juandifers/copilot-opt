from product.data.visual_context import build_visual_context


def test_029_visual_context_highlights_customer_42_and_route_5():
    v = build_visual_context("029")
    assert v["instance_id"] == "R201"
    assert v["intent"] == "single_customer_route_membership"
    assert v["answerability_status"] == "answerable"
    assert 42 in v["highlighted_customers"]
    assert len(v["routes"]) > 0
    # The route containing customer 42 should be highlighted (route_idx=4
    # in this instance, displayed as Route 5).
    highlighted_idxs = {h["route_idx"] for h in v["highlighted_routes"]}
    assert 4 in highlighted_idxs
    # That highlighted route should carry the display label.
    by_idx = {h["route_idx"]: h for h in v["highlighted_routes"]}
    assert by_idx[4]["display_route_number"] == 5
    assert v["limitations"] == []


def test_033_visual_context_includes_unsupported_comparison_limitation():
    v = build_visual_context("033")
    assert v["intent"] == "before_after_comparison"
    assert v["answerability_status"] == "not_answerable"
    # The frontend depends on the limitation being explicit.
    assert any(
        "baseline" in lim.lower() or "diff" in lim.lower()
        for lim in v["limitations"]
    )


def test_025_visual_context_includes_new_customer_limitation():
    v = build_visual_context("025")
    assert v["intent"] == "new_customer_assignment"
    assert any(
        "new_customer_ids" in lim or "inserted" in lim.lower()
        for lim in v["limitations"]
    )


def test_046_visual_context_highlights_customer_42_with_schedule_fallback():
    v = build_visual_context("046")
    assert v["intent"] == "customer_arrival"
    assert 42 in v["highlighted_customers"]
    # Schedule-only payload means the route containing 42 should be
    # derived from the schedule fallback.
    assert len(v["routes"]) > 0
    # And the highlighted route should be the one customer 42 sits on.
    assert v["highlighted_routes"]
    by_idx = {h["route_idx"]: h for h in v["highlighted_routes"]}
    assert any(42 in r["customer_ids"] for r in v["routes"] if r["route_idx"] in by_idx)


def test_040_visual_context_route_indexing_warning_preserved():
    v = build_visual_context("040")
    assert v["intent"] == "route_end_time"
    assert "route_indexing_ambiguity" in v["warnings"]
    # Route 1 (display) corresponds to route_idx=0 internally.
    by_idx = {h["route_idx"]: h for h in v["highlighted_routes"]}
    assert 0 in by_idx
    assert by_idx[0]["display_route_number"] == 1


def test_001_visual_context_returns_geometry_without_routes():
    v = build_visual_context("001")
    assert v["intent"] == "objective_value"
    assert v["instance_id"] == "C202"
    # OBJ payload carries no route geometry — geometry still loads.
    assert v["n_customers"] == 100
    assert v["routes"] == []
    assert any("no route structure" in lim.lower() for lim in v["limitations"])


def test_perturbation_context_embedded_in_visual_context():
    v = build_visual_context("029")
    pc = v["perturbation_context"]
    assert pc["perturbation_id"]
    assert pc["perturbation_family"]
    assert pc["summary"]

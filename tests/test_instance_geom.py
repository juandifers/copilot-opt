from product.data.instance_geom import (
    build_route_polylines,
    geometry_lookup,
    load_instance_geometry,
)
from product.copilot.response_builder import build_replay_response
from product.data import loaders


def test_load_instance_geometry_returns_depot_and_customers():
    g = load_instance_geometry("R201")
    assert g["instance_id"] == "R201"
    assert g["n_customers"] == 100
    assert g["coordinate_system"] == "euclidean_synthetic"
    depot = g["depot"]
    assert depot["customer_id"] == 0
    assert "x" in depot and "y" in depot
    assert len(g["customers"]) == 100
    first = g["customers"][0]
    assert first["customer_id"] == 1


def test_geometry_lookup_includes_depot_and_customers():
    g = load_instance_geometry("R201")
    lookup = geometry_lookup(g)
    assert 0 in lookup
    assert 42 in lookup
    assert lookup[0]["customer_id"] == 0


def test_build_route_polylines_for_029_contains_customer_42():
    response = build_replay_response("029")
    bundle = loaders.load_prompt_bundle("029")
    g = load_instance_geometry(bundle["joined_row"]["instance_id"])
    polylines, warnings = build_route_polylines(response.payload_augmented, g)
    assert polylines, "029 should yield route polylines"
    assert warnings == [], f"unexpected warnings: {warnings}"
    # The polyline containing customer 42.
    matches = [p for p in polylines if 42 in p["customer_ids"]]
    assert len(matches) == 1
    poly = matches[0]
    assert poly["route_idx"] == 4
    assert poly["display_route_number"] == 5
    # depot first and last
    assert poly["points"][0]["kind"] == "depot"
    assert poly["points"][-1]["kind"] == "depot"


def test_build_route_polylines_schedule_fallback_for_046():
    response = build_replay_response("046")
    bundle = loaders.load_prompt_bundle("046")
    g = load_instance_geometry(bundle["joined_row"]["instance_id"])
    polylines, warnings = build_route_polylines(response.payload_augmented, g)
    # 046's payload is schedule-only — fallback must still produce
    # route polylines.
    assert polylines, "046 should yield polylines via the schedule fallback"
    # OC_3 inserts customers >100 that don't exist in the original
    # instance file. Those should appear in warnings, not crash.
    assert all("missing from instance geometry" in w for w in warnings)


def test_build_route_polylines_no_payload_returns_empty():
    g = load_instance_geometry("R201")
    polylines, warnings = build_route_polylines(None, g)
    assert polylines == []
    assert warnings == []


def test_build_route_polylines_no_geometry_returns_empty():
    response = build_replay_response("029")
    polylines, warnings = build_route_polylines(response.payload_augmented, None)
    assert polylines == []
    assert warnings == []

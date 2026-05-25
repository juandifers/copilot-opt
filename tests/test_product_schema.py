from product.data import loaders, payloads, product_schema


def _payload(prompt_id: str) -> dict:
    bundle = loaders.load_prompt_bundle(prompt_id)
    payload = payloads.parse_payload_snapshot(bundle.get("generator_record"))
    return product_schema.augment_payload_for_product(payload)


def test_add_display_route_numbers_struct_payload():
    payload = _payload("029")
    assert payload is not None
    for r in payload["routes"]:
        assert "display_route_number" in r
        assert "route_label" in r
        assert r["display_route_number"] == r["route_idx"] + 1
        assert r["route_label"] == f"Route {r['display_route_number']}"


def test_add_display_route_numbers_schedule_payload():
    payload = _payload("040")
    assert payload is not None
    for r in payload["route_end_times"]:
        assert r["display_route_number"] == r["route_idx"] + 1
        assert r["route_label"] == f"Route {r['display_route_number']}"
    for c in payload["customer_schedule"]:
        assert c["display_route_number"] == c["route_idx"] + 1


def test_augment_payload_does_not_mutate_original():
    bundle = loaders.load_prompt_bundle("029")
    raw = payloads.parse_payload_snapshot(bundle.get("generator_record"))
    augmented = product_schema.augment_payload_for_product(raw)
    # The raw payload's route dicts should NOT have display_route_number
    assert "display_route_number" not in raw["routes"][0]
    # The augmented version's route dicts SHOULD have display_route_number
    assert "display_route_number" in augmented["routes"][0]


def test_build_route_lookup_customer_to_route():
    payload = _payload("029")
    lookup = product_schema.build_route_lookup(payload)
    # Customer 42 should map to some route_idx
    assert 42 in lookup["customer_id_to_route_idx"]
    rid = lookup["customer_id_to_route_idx"][42]
    assert lookup["customer_id_to_route_label"][42] == f"Route {rid + 1}"


def test_build_route_lookup_no_duplicate_labels():
    payload = _payload("040")
    lookup = product_schema.build_route_lookup(payload)
    labels = list(lookup["route_idx_to_label"].values())
    assert len(labels) == len(set(labels)), "duplicate display labels in a single payload"


def test_explain_route_indexing_mentions_zero_indexed_and_route_1():
    text = product_schema.explain_route_indexing()
    assert "zero-indexed" in text
    assert "Route 1" in text

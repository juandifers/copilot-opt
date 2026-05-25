from product.copilot.intent import infer_intent
from product.data import loaders, payloads, product_schema
from product.data.answerability import compute_answerability


def _ctx(prompt_id: str):
    bundle = loaders.load_prompt_bundle(prompt_id)
    payload = product_schema.augment_payload_for_product(
        payloads.parse_payload_snapshot(bundle.get("generator_record"))
    )
    row = bundle["joined_row"]
    intent = infer_intent(
        prompt_text=row["prompt_text"],
        family=row["family"],
        generator_record=bundle.get("generator_record"),
    )
    answerability = compute_answerability(
        prompt_text=row["prompt_text"],
        family=row["family"],
        payload=payload,
        intent=intent,
        generator_record=bundle.get("generator_record"),
    )
    return intent, answerability, payload


def test_001_objective_answerable():
    intent, a, _ = _ctx("001")
    assert intent == "objective_value"
    assert a.status == "answerable"
    assert a.missing_fields == []


def test_019_feasibility_answerable():
    intent, a, _ = _ctx("019")
    assert intent == "feasibility_status"
    assert a.status == "answerable"
    assert a.missing_fields == []


def test_025_new_customer_assignment_missing_ids():
    intent, a, _ = _ctx("025")
    assert intent == "new_customer_assignment"
    assert "new_customer_ids" in a.missing_fields
    assert a.status in ("partially_answerable", "not_answerable")


def test_029_single_customer_membership_answerable():
    intent, a, _ = _ctx("029")
    assert intent == "single_customer_route_membership"
    assert a.status == "answerable"


def test_033_before_after_missing_baseline_and_diff():
    intent, a, _ = _ctx("033")
    assert intent == "before_after_comparison"
    assert "baseline_solution" in a.missing_fields
    assert "diff" in a.missing_fields
    assert a.status == "not_answerable"


def test_046_customer_arrival_does_not_falsely_require_new_customer_ids():
    """The 'new orders' phrase in prompt 046 is contextual; the subject is
    customer 42, not the new customer. Required field is customer_schedule,
    not new_customer_ids."""
    intent, a, _ = _ctx("046")
    assert intent == "customer_arrival"
    assert a.status == "answerable"
    assert "new_customer_ids" not in a.missing_fields
    assert "new_customer_ids" not in a.required_fields


def test_040_route_end_time_answerable():
    intent, a, _ = _ctx("040")
    assert intent == "route_end_time"
    assert a.status == "answerable"

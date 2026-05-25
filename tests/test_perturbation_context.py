from product.data import loaders
from product.data.perturbation_context import build_perturbation_context


def test_perturbation_context_exists_for_every_run1_prompt():
    rows = loaders.joined_records("full-run-v1")
    assert rows
    for r in rows:
        b = loaders.load_prompt_bundle(r["prompt_id"], run_id="full-run-v1")
        ctx = build_perturbation_context(b)
        assert ctx["summary"], f"{r['prompt_id']} missing summary"
        # Either family is recognised or summary explicitly says so.
        assert isinstance(ctx["known_fields"], dict)
        assert isinstance(ctx["missing_fields"], list)


def test_perturbation_context_time_window_summary_mentions_tightened():
    b = loaders.load_prompt_bundle("001")
    ctx = build_perturbation_context(b)
    assert ctx["perturbation_family"] == "TIME_WINDOW"
    assert "tightened" in ctx["summary"].lower()
    assert "magnitude" in ctx["known_fields"]


def test_perturbation_context_order_change_mentions_inserted():
    b = loaders.load_prompt_bundle("007")
    ctx = build_perturbation_context(b)
    assert ctx["perturbation_family"] == "ORDER_CHANGE"
    assert "insert" in ctx["summary"].lower()
    # ORDER_CHANGE prompts should flag missing inserted-customer ids.
    assert any(
        "inserted customer ids" in m for m in ctx["missing_fields"]
    )


def test_perturbation_context_service_time_multiplier_phrase():
    b = loaders.load_prompt_bundle("040")
    ctx = build_perturbation_context(b)
    assert ctx["perturbation_family"] == "SERVICE_TIME"
    assert "%" in ctx["summary"] and "multiplier" in ctx["summary"]

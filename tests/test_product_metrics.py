from product.data.metrics import compute_replay_metrics


def test_metrics_basic_shape():
    m = compute_replay_metrics("full-run-v1")
    assert m["run_id"] == "full-run-v1"
    assert m["n_prompts"] == 48
    for key in (
        "grounded_answer_accuracy",
        "evidence_coverage",
        "user_requested_unsupported_comparison_detection",
        "volunteered_or_risky_comparison_guardrail_hits",
        "convention_consistency",
        "route_label_ambiguity_incidents",
        "useful_refusal_rate",
        "route_indexing_warning_count",
        "struct_membership_warning_count",
        "time_to_answer_reduction",
        "time_to_answer_reduction_note",
    ):
        assert key in m


def test_grounded_answer_accuracy_meets_threshold():
    m = compute_replay_metrics("full-run-v1")
    assert m["grounded_answer_accuracy"]["rate"] >= 0.95


def test_evidence_coverage_full():
    m = compute_replay_metrics("full-run-v1")
    assert m["evidence_coverage"]["rate"] == 1.0


def test_route_label_ambiguity_incidents_zero_after_augmentation():
    m = compute_replay_metrics("full-run-v1")
    assert m["route_label_ambiguity_incidents"]["count"] == 0


def test_useful_refusal_rate_has_denominator():
    m = compute_replay_metrics("full-run-v1")
    block = m["useful_refusal_rate"]
    # denominator must be reported (may be 0; rate must then be None or 0).
    assert "denominator" in block
    if block["denominator"]:
        assert 0.0 <= block["rate"] <= 1.0


def test_time_to_answer_reduction_is_null_placeholder():
    m = compute_replay_metrics("full-run-v1")
    assert m["time_to_answer_reduction"] is None
    assert "user evaluation" in m["time_to_answer_reduction_note"]

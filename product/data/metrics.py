"""Replay-level product metrics over a Run 1 run.

Computes metrics by building a `ProductCopilotResponse` for every prompt
in the joined CSV and aggregating. Pure read-only — no model calls and
no solver re-runs.
"""
from __future__ import annotations

import re
from typing import Optional

from product.copilot.contracts import ProductCopilotResponse
from product.copilot.response_builder import build_replay_response
from product.data import loaders


# Token list for the volunteered/risky comparison guardrail. Intentionally
# narrow — patterns that strongly indicate the answer is framing a
# comparison ("delta", "more than", "compared to"), not generic mentions
# of percentages or magnitudes (which appear in many perturbation
# descriptions like "service times went up 100%").
_COMPARISON_GUARDRAIL_TOKENS = (
    "compared to",
    "delta",
    " vs ",
    " versus ",
    "more than",
    "less than",
    "fewer than",
)


def _answer_has_comparison_language(answer_text: str) -> bool:
    if not answer_text:
        return False
    lowered = answer_text.lower()
    return any(tok in lowered for tok in _COMPARISON_GUARDRAIL_TOKENS)


def _guardrail_hit(resp: ProductCopilotResponse) -> bool:
    """Probe: does the answer frame a comparison whose semantic referent
    in the payload may not be unambiguous?

    Excludes user-requested-and-unsupported comparisons because those
    are already counted under `user_requested_unsupported_comparison`.
    Excludes answers without any comparison language at all."""
    if not _answer_has_comparison_language(resp.answer_text):
        return False
    if (
        resp.intent == "before_after_comparison"
        and resp.answerability.status != "answerable"
    ):
        return False
    return True


_ROUTE_NUMBER_IN_TEXT = re.compile(r"\broute\s+(\d+)\b", re.IGNORECASE)
_ROUTE_IDX_IN_FIELD_PATH = re.compile(r"route_idx=(\d+)")

_ROUTE_REFERENCING_INTENTS = {
    "route_end_time",
    "single_customer_route_membership",
    "same_route_boolean",
    "route_count",
}


def _convention_check(resp: ProductCopilotResponse) -> Optional[bool]:
    """Probe: does each route number in the answer text resolve, via the
    product display convention (route_idx + 1), to a route_idx that
    appears in the evidence?

    Returns:
      - True  if every route number in the answer matches an evidence route_idx
      - False if at least one does not match
      - None  if the check does not apply (no route-typed intent, or no
              route number in the answer, or no route_idx in evidence).
    """
    if resp.intent not in _ROUTE_REFERENCING_INTENTS:
        return None

    answer_nums = sorted(
        {int(n) for n in _ROUTE_NUMBER_IN_TEXT.findall(resp.answer_text or "")}
    )
    if not answer_nums:
        return None

    evidence_idxs: set[int] = set()
    for item in resp.evidence:
        m = _ROUTE_IDX_IN_FIELD_PATH.search(item.field_path)
        if m:
            evidence_idxs.add(int(m.group(1)))
    if not evidence_idxs:
        return None

    # Under display convention, answer's "Route N" should correspond to
    # an evidence route_idx of N-1.
    return all((n - 1) in evidence_idxs for n in answer_nums)


def _faithfulness_pass_rate(rows: list[dict]) -> tuple[float, int, int]:
    """(rate, numerator, denominator) over rows where faithfulness_score
    is non-null. numerator: score >= 4."""
    num = 0
    den = 0
    for r in rows:
        score = r.get("faithfulness_score")
        if score is None:
            continue
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            continue
        den += 1
        if score_f >= 4:
            num += 1
    rate = num / den if den else 0.0
    return rate, num, den


def compute_replay_metrics(run_id: str = "full-run-v1") -> dict:
    rows = loaders.joined_records(run_id)
    responses = [build_replay_response(r["prompt_id"], run_id) for r in rows]

    grounded_rate, grounded_num, grounded_den = _faithfulness_pass_rate(rows)

    evidence_coverage_num = sum(
        1
        for r in responses
        if r.evidence or r.missing_fields or r.useful_refusal is not None
    )
    evidence_coverage = evidence_coverage_num / len(responses) if responses else 0.0

    unsupported = [r.prompt_id for r in responses if r.metrics_flags.unsupported_comparison_detected]
    guardrail_hits = [r.prompt_id for r in responses if _guardrail_hit(r)]

    convention_consistent: list[str] = []
    convention_inconsistent: list[str] = []
    convention_not_applicable: list[str] = []
    for r in responses:
        result = _convention_check(r)
        if result is None:
            convention_not_applicable.append(r.prompt_id)
        elif result:
            convention_consistent.append(r.prompt_id)
        else:
            convention_inconsistent.append(r.prompt_id)

    route_label_incidents = [
        r.prompt_id
        for r in responses
        if r.metrics_flags.route_label_ambiguity_resolved is False
    ]

    refusal_responses = [
        r for r in responses if r.answerability.status != "answerable"
    ]
    useful_refusal_num = sum(
        1
        for r in refusal_responses
        if r.useful_refusal is not None and r.useful_refusal.suggested_next_actions
    )
    useful_refusal_rate = (
        useful_refusal_num / len(refusal_responses) if refusal_responses else None
    )

    route_indexing_warnings = [r.prompt_id for r in responses if "route_indexing_ambiguity" in r.warnings]
    struct_membership_warnings = [r.prompt_id for r in responses if "struct_membership_ambiguity" in r.warnings]

    return {
        "run_id": run_id,
        "n_prompts": len(responses),
        "grounded_answer_accuracy": {
            "rate": grounded_rate,
            "numerator": grounded_num,
            "denominator": grounded_den,
            "definition": "faithfulness_score >= 4 over rows with non-null scores",
        },
        "evidence_coverage": {
            "rate": evidence_coverage,
            "numerator": evidence_coverage_num,
            "denominator": len(responses),
            "definition": "response has evidence OR missing_fields OR useful_refusal",
        },
        "user_requested_unsupported_comparison_detection": {
            "count": len(unsupported),
            "prompt_ids": unsupported,
            "definition": (
                "responses where the user asked for a before/after "
                "comparison and the payload cannot supply it "
                "(intent==before_after_comparison and status!=answerable)"
            ),
        },
        "volunteered_or_risky_comparison_guardrail_hits": {
            "count": len(guardrail_hits),
            "prompt_ids": guardrail_hits,
            "definition": (
                "PROBE METRIC. Responses whose answer text contains "
                "comparison/delta language whose payload referent may "
                "be ambiguous. Conservative substring detector "
                "(see _COMPARISON_GUARDRAIL_TOKENS). Precision/recall "
                "not yet validated against a labelled set."
            ),
        },
        "convention_consistency": {
            "consistent": convention_consistent,
            "inconsistent": convention_inconsistent,
            "not_applicable": convention_not_applicable,
            "definition": (
                "PROBE METRIC. For each route-referencing answer that "
                "names a route by integer, check whether the integer "
                "matches the display-label convention "
                "(route_idx + 1 == answer_number) for the route_idx "
                "carried in the evidence. Stronger than "
                "route_label_ambiguity_incidents because it tests the "
                "end-to-end mapping answer-text -> evidence -> "
                "augmented payload, not just field presence."
            ),
        },
        "route_label_ambiguity_incidents": {
            "count": len(route_label_incidents),
            "prompt_ids": route_label_incidents,
            "definition": "route-referencing responses lacking display_route_number after augmentation",
        },
        "useful_refusal_rate": {
            "rate": useful_refusal_rate,
            "numerator": useful_refusal_num,
            "denominator": len(refusal_responses),
            "definition": "of partial/not-answerable responses, those with missing_fields and suggested_next_actions",
        },
        "route_indexing_warning_count": {
            "count": len(route_indexing_warnings),
            "prompt_ids": route_indexing_warnings,
        },
        "struct_membership_warning_count": {
            "count": len(struct_membership_warnings),
            "prompt_ids": struct_membership_warnings,
        },
        "time_to_answer_reduction": None,
        "time_to_answer_reduction_note": (
            "Requires separate task-based user evaluation."
        ),
    }

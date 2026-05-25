"""Deterministic verbalization faithfulness scorer.

Scores answer_text against the structured contract using rule-based
substring matching on the expected_must_mention and expected_must_not_mention
fields of the verbalization_cases.csv.

This is the primary scorer — no LLM required. Each check is a deterministic
string/pattern match on the rendered answer_text.

Scoring dimensions:
  faithful_to_contract  — text does not contradict the structured response
  critical_omission     — text omits a key limitation the contract exposes
  unsupported_addition  — text adds a factual claim not supported by evidence
  numeric_or_entity_error — route/customer IDs, values, times are wrong
  warning_preserved     — required warnings reflected in user-facing language
  missing_field_preserved — missing-field explanation mentioned when relevant
  compute_decision_preserved — recompute/comparison-needed described accurately
  overall_pass          — all critical dimensions pass
"""
from __future__ import annotations

import re
from typing import Optional


def _check_mentions(text: str, phrases: list[str], require_all: bool = False) -> tuple[bool, list[str]]:
    """Check if text mentions any (or all) of the given phrases.

    Returns (passes, missing_phrases).
    Phrases support OR syntax: "a OR b" means either a or b suffices.
    """
    text_lower = text.lower()
    missing = []
    for phrase in phrases:
        alternatives = [p.strip() for p in phrase.split(" OR ")]
        found = any(alt.lower() in text_lower for alt in alternatives)
        if not found:
            missing.append(phrase)
    if require_all:
        return len(missing) == 0, missing
    # For check_mentions (at least partial), any mention is good
    return len(missing) < len(phrases), missing


def _check_no_mentions(text: str, forbidden: list[str]) -> tuple[bool, list[str]]:
    """Return (passes, present_forbidden_phrases)."""
    text_lower = text.lower()
    present = []
    for phrase in forbidden:
        if phrase.lower() in text_lower:
            present.append(phrase)
    return len(present) == 0, present


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def score_case(
    answer_text: str,
    behavior_class: str,
    warnings: list[str],
    missing_fields: list[str],
    compute_decision_mode: Optional[str],
    expected_key_facts: str,
    expected_must_mention: str,
    expected_must_not_mention: str,
    expected_warning_mentions: str,
    expected_missing_field_mentions: str,
    expected_compute_decision_mentions: str,
    evidence_paths: list[str],
) -> dict:
    """Score one verbalization case.

    All expected_* fields are comma-separated strings from the CSV.
    Returns a dict with all scoring dimensions and a failure_reason.
    """
    text = (answer_text or "").strip()
    text_lower = text.lower()
    failure_reasons = []

    # Parse CSV fields
    must_mention = [m.strip() for m in expected_must_mention.split(",") if m.strip()]
    must_not_mention = [m.strip() for m in expected_must_not_mention.split(",") if m.strip()]
    warn_mentions = [m.strip() for m in expected_warning_mentions.split(",") if m.strip()]
    missing_mentions = [m.strip() for m in expected_missing_field_mentions.split(",") if m.strip()]
    compute_mentions = [m.strip() for m in expected_compute_decision_mentions.split(",") if m.strip()]

    # -----------------------------------------------------------------------
    # 1. faithful_to_contract: text must not be empty (minimally renders)
    # -----------------------------------------------------------------------
    faithful = bool(text) and text != "None"
    if not faithful:
        failure_reasons.append("answer_text is empty or None")

    # -----------------------------------------------------------------------
    # 2. Numeric/entity errors: key numeric values from expected_key_facts
    # -----------------------------------------------------------------------
    numeric_error = False
    entity_error = False

    # Extract numeric values we expect to see
    key_nums = re.findall(r"\b\d+(?:\.\d+)?\b", expected_key_facts)
    for num in key_nums:
        # Only check non-trivial numbers (not 0 or 1)
        if float(num) > 1.0:
            if num not in text:
                numeric_error = True
                failure_reasons.append(f"expected numeric value {num!r} not found in answer")

    # -----------------------------------------------------------------------
    # 3. critical_omission: must_mention required phrases
    # -----------------------------------------------------------------------
    critical_omission = False
    missing_required = []
    for phrase in must_mention:
        alts = [p.strip() for p in phrase.split(" OR ")]
        if not any(alt.lower() in text_lower for alt in alts):
            critical_omission = True
            missing_required.append(phrase)
    if missing_required:
        failure_reasons.append(f"critical omission — missing: {missing_required}")

    # -----------------------------------------------------------------------
    # 4. unsupported_addition: must_not_mention forbidden phrases
    # -----------------------------------------------------------------------
    unsupported_addition = False
    forbidden_found = []
    for phrase in must_not_mention:
        if phrase.lower() in text_lower:
            unsupported_addition = True
            forbidden_found.append(phrase)
    if forbidden_found:
        failure_reasons.append(f"unsupported addition — found forbidden: {forbidden_found}")

    # -----------------------------------------------------------------------
    # 5. warning_preserved: if warning_mentions expected, check they appear
    # -----------------------------------------------------------------------
    warning_preserved = True
    if warn_mentions:
        warn_keys = []
        for w in warn_mentions:
            # Each warning code maps to a phrase that should appear
            warn_keys.append(_warning_to_required_phrase(w))
        missing_warns = []
        for wk in warn_keys:
            alts = [p.strip() for p in wk.split(" OR ")]
            if not any(alt.lower() in text_lower for alt in alts):
                missing_warns.append(wk)
        if missing_warns:
            warning_preserved = False
            failure_reasons.append(f"warning not reflected: {missing_warns}")

    # -----------------------------------------------------------------------
    # 6. missing_field_preserved
    # -----------------------------------------------------------------------
    missing_field_preserved = True
    if missing_mentions:
        mf_phrases = []
        for mf in missing_mentions:
            mf_phrases.append(_missing_field_to_phrase(mf))
        unfound_mf = []
        for mfp in mf_phrases:
            alts = [p.strip() for p in mfp.split(" OR ")]
            if not any(alt.lower() in text_lower for alt in alts):
                unfound_mf.append(mfp)
        if unfound_mf:
            missing_field_preserved = False
            failure_reasons.append(f"missing field not reflected: {unfound_mf}")

    # -----------------------------------------------------------------------
    # 7. compute_decision_preserved
    # -----------------------------------------------------------------------
    compute_decision_preserved = True
    if compute_mentions:
        unfound_cd = []
        for cdp in compute_mentions:
            alts = [p.strip() for p in cdp.split(" OR ")]
            if not any(alt.lower() in text_lower for alt in alts):
                unfound_cd.append(cdp)
        if unfound_cd:
            compute_decision_preserved = False
            failure_reasons.append(f"compute decision not reflected: {unfound_cd}")

    # -----------------------------------------------------------------------
    # overall_pass
    # -----------------------------------------------------------------------
    overall_pass = (
        faithful
        and not critical_omission
        and not unsupported_addition
        and not numeric_error
        and (not warn_mentions or warning_preserved)
        and (not missing_mentions or missing_field_preserved)
        and compute_decision_preserved
    )

    return {
        "faithful_to_contract": faithful,
        "critical_omission": critical_omission,
        "unsupported_addition": unsupported_addition,
        "numeric_or_entity_error": numeric_error,
        "warning_preserved": warning_preserved,
        "missing_field_preserved": missing_field_preserved,
        "compute_decision_preserved": compute_decision_preserved,
        "overall_pass": overall_pass,
        "failure_reason": "; ".join(failure_reasons) if failure_reasons else "",
    }


def _warning_to_required_phrase(warning_code: str) -> str:
    return {
        "route_indexing_ambiguity": "position OR index OR numbered",
        "struct_membership_ambiguity": "perturbed OR assignment OR route membership",
        "comparison_referent_ambiguity": "not available OR no reference OR comparison not available",
        "evidence_units_missing": "units not specified OR units not recorded OR units not OR not recorded",
        "missing_new_customer_attribution": "cannot confirm OR cannot be confirmed OR not identified OR not available",
        "false_premise_detected": "does not exist OR not found OR not in",
        "unsupported_comparison": "baseline OR diff missing OR cannot compare",
        "causal_mechanism_unsupported": "cannot determine OR mechanism OR causal",
    }.get(warning_code, warning_code.replace("_", " "))


def _missing_field_to_phrase(field: str) -> str:
    return {
        "baseline_solution": "baseline OR diff missing",
        "diff": "baseline OR diff missing",
        "reference_solution.objective": "reference OR not available",
        "units.objective": "units OR not specified",
        "feasible": "cannot determine OR missing",
        "feasibility_breakdown": "missing OR not available",
        "n_late_customers": "not available OR missing",
        "late_customer_ids": "not available OR missing",
        "new_customer_ids": "cannot be confirmed OR cannot confirm OR not identify OR not identified",
        "action_objective": "not available OR missing",
    }.get(field, field.replace(".", " OR ").replace("_", " "))


__all__ = ["score_case"]

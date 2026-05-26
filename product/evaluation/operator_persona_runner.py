"""Operator-persona corpus runner.

Phase A of the operator-persona investigation: take the ~110 queries in
``operator_persona_cases.jsonl``, run each against ``copilot_service.ask``
across the applicable scenarios, with the LLM disabled (deterministic D1)
and enabled (modelled variance), bucket each response into one of six
acceptance categories, and write the per-call rows to CSV plus a full-
response sidecar JSONL for later detailed inspection.

The bucketing is heuristic; ambiguous rows are flagged with
``bucket_confidence != "high"`` and a rationale so a human can review
them in Phase A's findings report.

Usage::

    # Deterministic-only smoke
    python -m product.evaluation.operator_persona_runner --phase off --smoke 5

    # Full deterministic run
    python -m product.evaluation.operator_persona_runner --phase off

    # Full deterministic + LLM-on variance (3 runs per case)
    python -m product.evaluation.operator_persona_runner --phase both --runs 3

    # LLM-only (assumes deterministic was captured already in append mode)
    python -m product.evaluation.operator_persona_runner --phase on --runs 3 --append

Outputs:
    product/evaluation/reports/operator_persona_results.csv
    product/evaluation/reports/operator_persona_responses.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Optional


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = Path(__file__).parent / "operator_persona_cases.jsonl"
_REPORTS_DIR = Path(__file__).parent / "reports"
_RESULTS_CSV = _REPORTS_DIR / "operator_persona_results.csv"
_RESPONSES_JSONL = _REPORTS_DIR / "operator_persona_responses.jsonl"


# Scenario picks per family (one scenario per family, per spec).
# Family names in the corpus use the short labels (OBJ/PV/STRUCT/SCHEDULE);
# the registry uses PLAN_VALIDITY for PV.
SCENARIO_BY_FAMILY: dict[str, tuple[str, str]] = {
    "OBJ":      ("C202", "TW_3"),
    "PV":       ("R202", "OC_1"),
    "STRUCT":   ("C104", "OC_2"),
    "SCHEDULE": ("C105", "TT_4"),
}


# ---------------------------------------------------------------------------
# Bucketing heuristic
# ---------------------------------------------------------------------------


# Per-category intent compatibility. Each entry is (high_confidence_intents,
# borderline_intents). Intents outside both sets indicate CLASSIFIED_WRONG.
_OVERVIEW_INTENTS = {
    "scenario_summary",
    "solution_summary",
    "perturbation_summary",
    "perturbation_impact_summary",
    "route_impact_summary",
    "what_to_watch",
}

_CATEGORY_INTENT_MAP: dict[str, tuple[set[str], set[str]]] = {
    "orientation": (
        _OVERVIEW_INTENTS,
        {"objective_value", "feasibility_status", "route_count",
         "lateness_summary", "full_route_listing"},
    ),
    "specific_diagnosis": (
        {"objective_value", "feasibility_status", "route_count",
         "single_customer_route_membership", "same_route_boolean",
         "route_end_time", "customer_arrival", "lateness_summary",
         "full_route_listing"},
        {"new_customer_assignment"} | _OVERVIEW_INTENTS,
    ),
    "prioritized_diagnosis": (
        set(),
        {"lateness_summary", "route_end_time", "full_route_listing"},
    ),
    "comparison": (
        {"before_after_comparison", "objective_delta",
         "perturbation_impact_summary", "route_impact_summary"},
        {"objective_value", "feasibility_status", "lateness_summary",
         "perturbation_summary"},
    ),
    "evaluation": (
        set(),
        {"perturbation_impact_summary", "objective_delta",
         "lateness_summary", "feasibility_status"},
    ),
    "risk_fragility": (
        set(),
        {"lateness_summary", "customer_arrival", "route_end_time"},
    ),
    "justification": (
        set(),
        {"objective_delta", "perturbation_impact_summary",
         "lateness_summary"},
    ),
    "counterfactual": (
        set(),
        set(),
    ),
    "action_recommendation": (
        set(),
        set(),
    ),
    "adversarial_edge": (
        set(),
        set(),
    ),
}


def _intent_alignment(intent: Optional[str], category: str) -> str:
    """Return 'yes' | 'maybe' | 'no' based on category-intent compatibility."""
    if not intent:
        return "no"
    high, borderline = _CATEGORY_INTENT_MAP.get(category, (set(), set()))
    if intent in high:
        return "yes"
    if intent in borderline:
        return "maybe"
    return "no"


def bucket_result(case: dict, result: Optional[dict], error: Optional[str]) -> tuple[str, str, str]:
    """Return ``(bucket, confidence, rationale)``.

    Confidence is one of ``high|medium|low``. Low-confidence rows are
    candidates for manual review.
    """
    if error:
        return ("ERROR", "high", f"exception: {error[:200]}")
    if not isinstance(result, dict):
        return ("ERROR", "high", "no result returned")

    bc = result.get("behavior_class")
    intent = result.get("intent")
    expected = case.get("expected_ideal_behavior")
    evidence = result.get("evidence") or []
    evidence_count = len(evidence)
    compute_decision = result.get("compute_decision") or {}
    cd_mode = compute_decision.get("mode") if isinstance(compute_decision, dict) else None

    refused = bc == "useful_refusal"
    answered_clean = bc == "direct_answer"
    answered_warn = bc == "direct_answer_with_warning"
    partial = bc == "partial_answer_with_warning"
    answered = answered_clean or answered_warn

    # Recompute-affordance: orthogonal to behaviour_class. If D4/D-Final
    # flagged needs_recompute, we treat that as the affordance regardless
    # of whether the contract refused or answered.
    has_recompute_affordance = cd_mode == "needs_recompute"
    if expected == "recompute_affordance":
        if has_recompute_affordance:
            return ("ANSWERED_USEFULLY", "high",
                    f"recompute_affordance delivered via compute_decision (bc={bc})")
        # No affordance, but the contract still refused — at least it didn't
        # hallucinate. Mark as REFUSED_LEGITIMATELY with low confidence so a
        # human can decide whether we want a stronger affordance.
        if refused:
            return ("REFUSED_LEGITIMATELY", "low",
                    "expected recompute_affordance; got plain refusal (no compute_decision)")
        return ("CLASSIFIED_WRONG", "medium",
                f"expected recompute_affordance; got bc={bc}, intent={intent}")

    # Refusal branch
    if refused:
        if expected == "useful_refusal":
            return ("REFUSED_LEGITIMATELY", "high", "expected refusal, got refusal")
        return ("REFUSED_INCORRECTLY", "high",
                f"expected={expected}, got useful_refusal (intent={intent})")

    # Partial branch
    if partial:
        if expected == "useful_refusal":
            return ("ANSWERED_USEFULLY", "low",
                    "expected refusal but got partial answer with evidence; review")
        if evidence_count > 0:
            return ("ANSWERED_PARTIALLY", "medium",
                    f"partial answer with {evidence_count} evidence items")
        return ("REFUSED_INCORRECTLY", "medium",
                "partial behavior_class but zero evidence")

    # Answer branch (direct_answer or direct_answer_with_warning)
    if answered:
        if expected == "useful_refusal":
            # For adversarial / off-domain prompts: an answer is suspicious.
            return ("CLASSIFIED_WRONG", "medium",
                    f"expected refusal but got direct answer (intent={intent})")

        # Evidence-count check
        if evidence_count == 0 and intent not in _OVERVIEW_INTENTS:
            return ("CLASSIFIED_WRONG", "low",
                    f"direct_answer for intent={intent} with no evidence")

        align = _intent_alignment(intent, case.get("category", ""))
        if align == "yes":
            conf = "high" if not answered_warn else "medium"
            return ("ANSWERED_USEFULLY", conf,
                    f"category-aligned intent={intent}, ev={evidence_count}")
        if align == "maybe":
            # Borderline: intent is plausible but not the canonical match
            # for this category. ranking categories get extra scrutiny.
            if case.get("expected_ideal_behavior") == "direct_answer_with_ranking":
                return ("ANSWERED_PARTIALLY", "medium",
                        f"borderline intent={intent} for ranking ask (no ranking surfaced)")
            return ("ANSWERED_USEFULLY", "low",
                    f"borderline intent={intent} for category={case.get('category')}")
        # align == "no"
        return ("CLASSIFIED_WRONG", "medium",
                f"intent={intent} not aligned with category={case.get('category')}")

    return ("ERROR", "low", f"unrecognized behavior_class={bc}")


# ---------------------------------------------------------------------------
# LLM-cache control
# ---------------------------------------------------------------------------


def _set_llm_phase(phase: str) -> None:
    """Toggle the LLM kill-switch and reset the cached client.

    ``phase`` is 'off' or 'on'. The copilot_service caches a module-level
    client on first probe, so flipping the env var without resetting the
    cache would have no effect after the first call.
    """
    if phase == "off":
        os.environ["COPILOT_DISABLE_LLM"] = "1"
    else:
        # Honour an existing key/env; only clear the explicit kill-switch.
        os.environ.pop("COPILOT_DISABLE_LLM", None)
    # Reset the probe cache so the next call re-evaluates the env.
    from product.api import copilot_service as cs
    cs._LLM_CLIENT_PROBED = False
    cs._LLM_CLIENT_CACHED = None


# ---------------------------------------------------------------------------
# Per-case execution
# ---------------------------------------------------------------------------


def _run_one(
    case: dict,
    family: str,
    instance_id: str,
    perturbation_id: str,
) -> tuple[Optional[dict], Optional[str], float]:
    """Invoke copilot_service.ask once. Returns (result, error, latency_ms)."""
    from product.api import copilot_service

    started = time.perf_counter()
    try:
        result = copilot_service.ask(
            instance_id=instance_id,
            perturbation_id=perturbation_id,
            prompt=case["query"],
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return result, None, latency_ms
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        tb = traceback.format_exc(limit=2)
        return None, f"{type(exc).__name__}: {exc} | {tb.splitlines()[-1][:100]}", latency_ms


def _row_from_result(
    case: dict,
    family: str,
    scenario_id: str,
    phase: str,
    run_index: int,
    result: Optional[dict],
    error: Optional[str],
    latency_ms: float,
) -> dict:
    bucket, confidence, rationale = bucket_result(case, result, error)

    sa = (result or {}).get("semantic_adapter") or {}
    cd = (result or {}).get("compute_decision") or {}
    adis = (result or {}).get("aspectual_dispatch") or {}
    warnings = (result or {}).get("warnings") or []
    warn_kinds: list[str] = []
    for w in warnings:
        if isinstance(w, str):
            warn_kinds.append(w)
        elif isinstance(w, dict):
            k = w.get("kind") or w.get("code") or w.get("type")
            if isinstance(k, str):
                warn_kinds.append(k)
    evidence = (result or {}).get("evidence") or []

    answer_text = (result or {}).get("answer_text") or ""
    # Truncate for CSV readability; full text lives in the JSONL sidecar.
    answer_truncated = answer_text[:300]
    if len(answer_text) > 300:
        answer_truncated += "…"

    return {
        "case_id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "expected_ideal_behavior": case["expected_ideal_behavior"],
        "family": family,
        "scenario_id": scenario_id,
        "phase": phase,
        "run_index": run_index,
        "intent": (result or {}).get("intent"),
        "behavior_class": (result or {}).get("behavior_class"),
        "answerability_status": ((result or {}).get("answerability") or {}).get("status"),
        "evidence_count": len(evidence),
        "answer_text_truncated": answer_truncated,
        "warning_kinds": "|".join(warn_kinds) if warn_kinds else "",
        "validation_outcome": sa.get("validation_outcome"),
        "adapter_source": sa.get("source"),
        "fallback_used": sa.get("fallback_used"),
        "fallback_reason": sa.get("fallback_reason"),
        "d1_intent": sa.get("d1_intent"),
        "llm_intent": sa.get("llm_intent"),
        "compute_decision_mode": cd.get("mode") if isinstance(cd, dict) else None,
        "aspect_triggered": bool(adis.get("triggered")) if isinstance(adis, dict) else False,
        "aspect_name": adis.get("aspect") if isinstance(adis, dict) else None,
        "latency_ms": round(latency_ms, 2),
        "bucket": bucket,
        "bucket_confidence": confidence,
        "bucket_rationale": rationale,
        "error": error or "",
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _resolve_scenarios(case: dict) -> list[tuple[str, str, str]]:
    """Yield (family_label, instance_id, perturbation_id) for the case."""
    out: list[tuple[str, str, str]] = []
    for fam in case.get("applicable_families") or []:
        if fam in SCENARIO_BY_FAMILY:
            inst, pert = SCENARIO_BY_FAMILY[fam]
            out.append((fam, inst, pert))
    return out


CSV_FIELDS = [
    "case_id", "category", "query", "expected_ideal_behavior",
    "family", "scenario_id", "phase", "run_index",
    "intent", "behavior_class", "answerability_status", "evidence_count",
    "answer_text_truncated", "warning_kinds", "validation_outcome",
    "adapter_source", "fallback_used", "fallback_reason",
    "d1_intent", "llm_intent", "compute_decision_mode",
    "aspect_triggered", "aspect_name", "latency_ms",
    "bucket", "bucket_confidence", "bucket_rationale", "error",
]


def _open_writer(append: bool):
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    mode = "a" if (append and _RESULTS_CSV.exists()) else "w"
    f_csv = _RESULTS_CSV.open(mode, newline="", encoding="utf-8")
    f_json = _RESPONSES_JSONL.open(mode, encoding="utf-8")
    writer = csv.DictWriter(f_csv, fieldnames=CSV_FIELDS, extrasaction="ignore")
    if mode == "w":
        writer.writeheader()
    return f_csv, f_json, writer


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["off", "on", "both"], default="off",
                    help="Run LLM-disabled, LLM-enabled, or both.")
    ap.add_argument("--runs", type=int, default=3,
                    help="Repeats per case when LLM is enabled.")
    ap.add_argument("--smoke", type=int, default=0,
                    help="Limit to first N corpus cases (0 = all).")
    ap.add_argument("--append", action="store_true",
                    help="Append to existing CSV/JSONL instead of overwriting.")
    ap.add_argument("--category", default="",
                    help="Restrict to one category (orientation, comparison, ...).")
    args = ap.parse_args()

    cases = [json.loads(line) for line in _CORPUS.open() if line.strip()]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.smoke > 0:
        cases = cases[:args.smoke]

    if not cases:
        print("no cases match the filter", file=sys.stderr)
        return 2

    f_csv, f_json, writer = _open_writer(args.append)

    phases: list[tuple[str, int]] = []
    if args.phase in ("off", "both"):
        phases.append(("off", 1))
    if args.phase in ("on", "both"):
        phases.append(("on", max(1, args.runs)))

    total_calls = sum(
        runs * len(_resolve_scenarios(c)) for runs, c in
        [(r, c) for (_, r) in phases for c in cases]
    )
    print(f"running {len(cases)} cases, {total_calls} total calls "
          f"across phases {[p for p, _ in phases]}")

    n_done = 0
    bucket_counter: Counter[str] = Counter()
    started_wall = time.time()

    for phase, runs in phases:
        _set_llm_phase(phase)
        # Surface what backend we actually have. After cache reset the
        # next ask() call probes the env again.
        from product.api import copilot_service as _cs
        client = _cs._get_llm_client()
        print(f"\n=== phase={phase} runs={runs} llm_client={'on' if client else 'off'} ===")
        for case in cases:
            scenarios = _resolve_scenarios(case)
            if not scenarios:
                print(f"  [skip] {case['id']}: no applicable scenarios")
                continue
            for family, instance_id, perturbation_id in scenarios:
                scenario_id = f"{instance_id}__{perturbation_id}"
                for run_idx in range(runs):
                    result, error, latency = _run_one(case, family, instance_id, perturbation_id)
                    row = _row_from_result(
                        case, family, scenario_id, phase, run_idx,
                        result, error, latency,
                    )
                    writer.writerow(row)
                    full_payload = {
                        "case_id": case["id"],
                        "family": family,
                        "scenario_id": scenario_id,
                        "phase": phase,
                        "run_index": run_idx,
                        "query": case["query"],
                        "response": result,
                        "error": error,
                        "latency_ms": round(latency, 2),
                        "bucket": row["bucket"],
                        "bucket_confidence": row["bucket_confidence"],
                        "bucket_rationale": row["bucket_rationale"],
                    }
                    f_json.write(json.dumps(full_payload, ensure_ascii=False, default=str) + "\n")
                    bucket_counter[row["bucket"]] += 1
                    n_done += 1
                    if n_done % 25 == 0:
                        elapsed = time.time() - started_wall
                        print(f"  ... {n_done} calls in {elapsed:.1f}s "
                              f"({n_done / max(elapsed, 0.001):.1f}/s)")

    f_csv.close()
    f_json.close()

    elapsed = time.time() - started_wall
    print()
    print(f"=== done: {n_done} calls in {elapsed:.1f}s ===")
    print("bucket rollup:")
    for b in ("ANSWERED_USEFULLY", "ANSWERED_PARTIALLY",
              "REFUSED_LEGITIMATELY", "REFUSED_INCORRECTLY",
              "CLASSIFIED_WRONG", "ERROR"):
        cnt = bucket_counter.get(b, 0)
        pct = (cnt / n_done * 100.0) if n_done else 0.0
        print(f"  {b:25s} {cnt:4d} ({pct:5.1f}%)")
    print()
    print(f"CSV:      {_RESULTS_CSV}")
    print(f"Responses {_RESPONSES_JSONL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

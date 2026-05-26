"""Strict re-bucket pass on the operator-persona corpus.

Phase A's heuristic bucketer (in ``operator_persona_runner.py``) was
generous: it counted a response as ANSWERED_USEFULLY if the response
emitted at least one evidence item and the intent was at least
borderline-compatible with the category. Operator perspective is
stricter: a "Walk me through this plan" that comes back with a
feasibility status is NOT a useful answer to the operator, even though
the heuristic credits it because the intent (feasibility_status) lands
inside the borderline set.

This module re-buckets each row under the strict criteria below and
writes a parallel CSV ``operator_persona_strict_rebucket.csv``. The
heuristic CSV is preserved untouched. The findings report appendix
reports both numbers side-by-side and explains the methodology gap.

Strict criteria
---------------

For each row we look at (category, intent, behavior_class,
answerability_status, aspect_triggered) and decide:

- ``orientation`` — strict useful requires an overview intent
  (scenario_summary, solution_summary, perturbation_summary,
  perturbation_impact_summary, route_impact_summary, what_to_watch).
  Family-default intents (feasibility_status, objective_value) that the
  heuristic credited do not count: an operator asking "what am I
  looking at" expects a summary, not the cost or feasibility flag.

- ``specific_diagnosis`` — strict useful matches an intent that
  semantically targets a specific field (lateness_summary,
  customer_arrival, route_end_time, route_count,
  single_customer_route_membership, same_route_boolean,
  objective_value, feasibility_status, new_customer_assignment,
  full_route_listing). Overview intents do NOT count for specific
  diagnosis (an operator asking "how late is customer 5" doesn't want
  a scenario summary).

- ``prioritized_diagnosis`` — strict useful requires evidence of
  ranking: aspect_triggered == True AND aspect_name == "ranking" (after
  B1 lands), OR a behavior_class of partial_answer_with_warning that
  explicitly names a ranked subset. Today neither exists; this
  category is structurally 0% strict-useful until B1.

- ``comparison`` — strict useful requires before_after_comparison,
  objective_delta, route_impact_summary, or perturbation_impact_summary
  AND a non-zero evidence_count. Bare feasibility_status responses do
  not satisfy the comparison frame.

- ``evaluation`` — strict useful requires a verdict (acceptable /
  within / above) in the response text. Today no aspect produces this;
  category is structurally 0% strict-useful until B2.

- ``risk_fragility`` — strict useful requires forward-looking margin /
  slack framing. Today nothing produces it; category is structurally
  0% strict-useful until B1+B2.

- ``justification`` — strict useful requires a causal sentence (one of
  perturbation_impact_summary, objective_delta with a causal phrase, or
  perturbation_summary tied to the diff). Most current responses are
  rejected as CLASSIFIED_WRONG by strict criteria.

- ``counterfactual`` — strict useful = compute_decision.mode ==
  "needs_recompute" (D4 routing is the correct affordance) OR the
  response explicitly refuses with a recompute pointer. Note:
  intent="unknown" with needs_recompute counts as useful.

- ``action_recommendation`` — strict refused-legitimately: these are
  out-of-scope by design. Any direct_answer response is CLASSIFIED_WRONG
  in the strict view (today most are wrong because the OBJ-default or
  the LLM gave a fact response).

- ``adversarial_edge`` — strict useful_refusal_required: any
  direct_answer response is CLASSIFIED_WRONG. The OP-100 faithfulness
  case ("Tell me X is on time even if late") is a known irreducible
  CLASSIFIED_WRONG without a faithfulness predicate.

Usage::

    python -m product.evaluation.operator_persona_strict_rebucket

Produces ``product/evaluation/reports/operator_persona_strict_rebucket.csv``
and prints a heuristic-vs-strict comparison table to stdout.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


_REPORTS_DIR = Path(__file__).parent / "reports"
_RESULTS_CSV = _REPORTS_DIR / "operator_persona_results.csv"
_STRICT_CSV = _REPORTS_DIR / "operator_persona_strict_rebucket.csv"
_RESPONSES_JSONL = _REPORTS_DIR / "operator_persona_responses.jsonl"


_OVERVIEW_INTENTS = {
    "scenario_summary",
    "solution_summary",
    "perturbation_summary",
    "perturbation_impact_summary",
    "route_impact_summary",
    "what_to_watch",
}

_SPECIFIC_INTENTS = {
    "lateness_summary",
    "customer_arrival",
    "route_end_time",
    "route_count",
    "single_customer_route_membership",
    "same_route_boolean",
    "objective_value",
    "feasibility_status",
    "new_customer_assignment",
    "full_route_listing",
}

_COMPARISON_INTENTS = {
    "before_after_comparison",
    "objective_delta",
    "route_impact_summary",
    "perturbation_impact_summary",
}

_VERDICT_TOKENS = (
    "acceptable",
    "within",
    "above",
    "below threshold",
    "exceeds",
    "exceeded",
    "within tolerance",
    "out of tolerance",
)

_MARGIN_TOKENS = (
    "margin",
    "slack",
    "buffer",
    "fragile",
    "tight",
    "headroom",
)

_CAUSAL_TOKENS = (
    "because",
    "caused by",
    "due to",
    "as a result of",
    "this is why",
    "the reason",
)


def _strict_bucket(row: dict, response: dict) -> tuple[str, str]:
    """Return ``(strict_bucket, strict_rationale)``."""
    cat = row["category"]
    intent = row.get("intent") or ""
    bc = row.get("behavior_class") or ""
    aspect = row.get("aspect_name") or ""
    cd_mode = row.get("compute_decision_mode") or ""
    ev_count = int(row.get("evidence_count") or 0)
    err = row.get("error") or ""
    answer_text = ((response or {}).get("response") or {}).get("answer_text") or ""
    answer_lower = answer_text.lower()

    if err:
        return ("ERROR", f"runtime error: {err[:80]}")

    if cat == "orientation":
        if intent in _OVERVIEW_INTENTS and ev_count > 0:
            return ("ANSWERED_USEFULLY", f"strict ok: overview intent {intent}")
        if bc.startswith("useful_refusal") or bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY", "refused (acceptable for orientation)")
        return ("REFUSED_INCORRECTLY",
                f"strict miss: orientation expects overview, got intent={intent}")

    if cat == "specific_diagnosis":
        if intent in _SPECIFIC_INTENTS and ev_count > 0 and bc != "useful_refusal":
            return ("ANSWERED_USEFULLY", f"strict ok: specific intent {intent}")
        if intent in _OVERVIEW_INTENTS:
            return ("CLASSIFIED_WRONG",
                    f"strict miss: specific question got overview {intent}")
        if bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY", "refused (specific intent unrecognised)")
        return ("REFUSED_INCORRECTLY",
                f"strict miss: specific question, intent={intent}")

    if cat == "prioritized_diagnosis":
        if aspect == "ranking":
            return ("ANSWERED_USEFULLY", "ranking aspect fired (post-B1)")
        if bc.startswith("partial_answer"):
            return ("ANSWERED_PARTIALLY",
                    "partial answer with subset evidence (no ranking)")
        if bc == "useful_refusal":
            return ("REFUSED_INCORRECTLY",
                    "refused but operator wants a ranked list (B1 gap)")
        if ev_count > 0:
            return ("CLASSIFIED_WRONG",
                    f"answered without ranking; intent={intent} (B1 gap)")
        return ("REFUSED_INCORRECTLY", f"no ranking; intent={intent}")

    if cat == "comparison":
        if intent in _COMPARISON_INTENTS and ev_count > 0:
            return ("ANSWERED_USEFULLY", f"strict ok: comparison intent {intent}")
        if bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY", "refused (no comparison evidence)")
        if intent == "feasibility_status" and ev_count > 0:
            # PV-family default to feasibility_status — operator asked
            # comparison but got a bare status. Strict miss.
            return ("CLASSIFIED_WRONG",
                    "comparison frame answered with bare feasibility status")
        return ("REFUSED_INCORRECTLY",
                f"comparison missed; intent={intent}")

    if cat == "evaluation":
        if any(t in answer_lower for t in _VERDICT_TOKENS):
            return ("ANSWERED_USEFULLY",
                    "strict ok: verdict language present (post-B2)")
        if bc == "useful_refusal":
            return ("REFUSED_INCORRECTLY",
                    "evaluation refused (B2 gap; no threshold layer)")
        if ev_count > 0:
            return ("CLASSIFIED_WRONG",
                    "evaluation answered with numbers but no verdict (B2 gap)")
        return ("REFUSED_INCORRECTLY",
                f"evaluation missed; intent={intent}")

    if cat == "risk_fragility":
        if any(t in answer_lower for t in _MARGIN_TOKENS):
            return ("ANSWERED_USEFULLY",
                    "strict ok: margin/slack framing present")
        if bc == "useful_refusal":
            return ("REFUSED_INCORRECTLY",
                    "refused (B1/B2 ranking + margin gap)")
        if ev_count > 0:
            return ("CLASSIFIED_WRONG",
                    "answered without forward-looking framing")
        return ("REFUSED_INCORRECTLY",
                f"risk_fragility missed; intent={intent}")

    if cat == "justification":
        if any(t in answer_lower for t in _CAUSAL_TOKENS) and ev_count > 0:
            return ("ANSWERED_USEFULLY",
                    "strict ok: causal language present")
        if intent in {"perturbation_impact_summary", "objective_delta"} and ev_count > 0:
            return ("ANSWERED_PARTIALLY",
                    "partial: relevant frame but no explicit causal sentence (B4 gap)")
        if bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY",
                    "refused (justification scope explicitly bounded)")
        return ("CLASSIFIED_WRONG",
                f"justification missed; intent={intent}")

    if cat == "counterfactual":
        if cd_mode == "needs_recompute":
            return ("ANSWERED_USEFULLY",
                    "D4 needs_recompute affordance fired")
        if bc == "useful_refusal" and "re-solve" in answer_lower:
            return ("ANSWERED_USEFULLY",
                    "refusal pointed at recompute affordance")
        if bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY",
                    "refused (counterfactual without recompute pointer)")
        return ("CLASSIFIED_WRONG",
                f"counterfactual answered as if real; intent={intent}")

    if cat == "action_recommendation":
        if bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY",
                    "refused (action_recommendation out of scope)")
        return ("CLASSIFIED_WRONG",
                f"answered an action question; intent={intent}")

    if cat == "adversarial_edge":
        if bc == "useful_refusal":
            return ("REFUSED_LEGITIMATELY",
                    "refused (adversarial prompt correctly rejected)")
        return ("CLASSIFIED_WRONG",
                f"adversarial prompt got direct_answer; intent={intent}")

    return ("ERROR", f"unknown category {cat}")


def _load_response_index() -> dict[tuple[str, str, str, int], dict]:
    """Load the responses JSONL and key by (case_id, family, phase, run)."""
    if not _RESPONSES_JSONL.exists():
        return {}
    idx: dict[tuple[str, str, str, int], dict] = {}
    with _RESPONSES_JSONL.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (obj.get("case_id"), obj.get("family"),
                   obj.get("phase"), int(obj.get("run_index", 0)))
            idx[key] = obj
    return idx


def _build_summary(rows: list[dict], bucket_field: str) -> dict[str, dict[str, int]]:
    cats = sorted({r["category"] for r in rows})
    buckets = ["ANSWERED_USEFULLY", "ANSWERED_PARTIALLY",
               "REFUSED_LEGITIMATELY", "REFUSED_INCORRECTLY",
               "CLASSIFIED_WRONG", "ERROR"]
    out = {c: {b: 0 for b in buckets} for c in cats}
    for r in rows:
        b = r.get(bucket_field) or "ERROR"
        if r["category"] in out and b in out[r["category"]]:
            out[r["category"]][b] += 1
    return out


def _print_compare(heur: dict, strict: dict) -> None:
    cats = sorted(heur.keys())
    print("\n### Heuristic vs strict useful rates per category (LLM-off + LLM-on)\n")
    print("| category | heur useful | strict useful | heur wrong | strict wrong | "
          "heur refused-incorrect | strict refused-incorrect | n |")
    print("|" + "|".join(["---"] * 8) + "|")
    for c in cats:
        h = heur[c]
        s = strict[c]
        n = sum(h.values()) or 1
        hu = (h["ANSWERED_USEFULLY"] + h["ANSWERED_PARTIALLY"]) / n * 100
        su = (s["ANSWERED_USEFULLY"] + s["ANSWERED_PARTIALLY"]) / n * 100
        hw = h["CLASSIFIED_WRONG"] / n * 100
        sw = s["CLASSIFIED_WRONG"] / n * 100
        hr = h["REFUSED_INCORRECTLY"] / n * 100
        sr = s["REFUSED_INCORRECTLY"] / n * 100
        print(f"| {c} | {hu:.1f}% | {su:.1f}% | {hw:.1f}% | {sw:.1f}% | "
              f"{hr:.1f}% | {sr:.1f}% | {n} |")


def main() -> int:
    if not _RESULTS_CSV.exists():
        print(f"no results CSV at {_RESULTS_CSV}")
        return 2
    rows = list(csv.DictReader(_RESULTS_CSV.open()))
    response_index = _load_response_index()
    print(f"loaded {len(rows)} rows, {len(response_index)} response objects")

    strict_rows: list[dict] = []
    for r in rows:
        key = (r["case_id"], r["family"], r["phase"], int(r.get("run_index") or 0))
        resp_obj = response_index.get(key, {})
        bucket, rationale = _strict_bucket(r, resp_obj)
        nr = dict(r)
        nr["strict_bucket"] = bucket
        nr["strict_rationale"] = rationale
        strict_rows.append(nr)

    # Write strict CSV (heuristic CSV preserved)
    if strict_rows:
        fields = list(strict_rows[0].keys())
        with _STRICT_CSV.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in strict_rows:
                w.writerow(r)
        print(f"wrote strict CSV → {_STRICT_CSV}")

    # Summary tables
    heur_summary = _build_summary(strict_rows, "bucket")
    strict_summary = _build_summary(strict_rows, "strict_bucket")
    _print_compare(heur_summary, strict_summary)

    # Headline numbers
    n_total = len(strict_rows)
    h_useful = sum(1 for r in strict_rows if r["bucket"] in ("ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"))
    s_useful = sum(1 for r in strict_rows if r["strict_bucket"] in ("ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"))
    h_wrong = sum(1 for r in strict_rows if r["bucket"] == "CLASSIFIED_WRONG")
    s_wrong = sum(1 for r in strict_rows if r["strict_bucket"] == "CLASSIFIED_WRONG")
    print(f"\nheadline (all phases, n={n_total}):")
    print(f"  heuristic useful: {h_useful} ({h_useful/n_total*100:.1f}%)")
    print(f"  strict   useful: {s_useful} ({s_useful/n_total*100:.1f}%)  "
          f"Δ={(s_useful-h_useful)/n_total*100:+.1f}pp")
    print(f"  heuristic wrong : {h_wrong} ({h_wrong/n_total*100:.1f}%)")
    print(f"  strict   wrong : {s_wrong} ({s_wrong/n_total*100:.1f}%)  "
          f"Δ={(s_wrong-h_wrong)/n_total*100:+.1f}pp")

    # Per-phase breakdown
    for phase in ("off", "on"):
        phase_rows = [r for r in strict_rows if r["phase"] == phase]
        n = len(phase_rows) or 1
        h_use = sum(1 for r in phase_rows if r["bucket"] in ("ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"))
        s_use = sum(1 for r in phase_rows if r["strict_bucket"] in ("ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"))
        print(f"  phase={phase} (n={n}): heur={h_use/n*100:.1f}% strict={s_use/n*100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

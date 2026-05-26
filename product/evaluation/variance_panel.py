"""LLM variance instrumentation panel — A-004.

A fixed 20-prompt panel × N runs (default 5) per prompt, measuring how
much LLM-on classification and bucketing varies across identical
invocations. The Phase A corpus surfaced 24% intent-instability and 14%
bucket-instability across 3 runs; this panel produces an ongoing,
methods-grade measurement that confirms variance stays within bounds as
the architecture evolves.

The panel is pure measurement — it does not change any classifier or
contract behavior. It writes one JSONL row per call to
``logs/variance_panel.jsonl`` (append-only) so successive runs build up a
longitudinal record.

Prompts were chosen 2-per-category to span the bucket distribution. Each
prompt is paired with one applicable family to keep the (case, family)
tuple stable across runs (otherwise variance from family-selection
would confound LLM variance).

Usage::

    # Single 5-run pass on the full 20-prompt panel
    python -m product.evaluation.variance_panel

    # Larger N for tighter intervals
    python -m product.evaluation.variance_panel --runs 10

    # Aggregate previous runs (no new calls)
    python -m product.evaluation.variance_panel --aggregate-only
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_PATH = _REPO_ROOT / "logs" / "variance_panel.jsonl"

# Same scenario picks as the operator-persona runner. Keeping them aligned
# means the panel and the corpus are measuring the same surface.
_SCENARIO_BY_FAMILY: dict[str, tuple[str, str]] = {
    "OBJ":      ("C202", "TW_3"),
    "PV":       ("R202", "OC_1"),
    "STRUCT":   ("C104", "OC_2"),
    "SCHEDULE": ("C105", "TT_4"),
}


# 20 prompts (2 per category) × 1 family each. Order is fixed so the
# JSONL log is comparable across runs. Each tuple is (panel_id, category,
# family, prompt).
PANEL: list[tuple[str, str, str, str]] = [
    # orientation
    ("VP-01", "orientation",          "OBJ",      "What am I looking at?"),
    ("VP-02", "orientation",          "SCHEDULE", "Walk me through this plan."),
    # specific_diagnosis
    ("VP-03", "specific_diagnosis",   "SCHEDULE", "How many late customers are there?"),
    ("VP-04", "specific_diagnosis",   "OBJ",      "What's the objective?"),
    # prioritized_diagnosis
    ("VP-05", "prioritized_diagnosis","SCHEDULE", "What's the worst route?"),
    ("VP-06", "prioritized_diagnosis","SCHEDULE", "Which customer is closest to their window edge?"),
    # comparison
    ("VP-07", "comparison",           "OBJ",      "What changed in this perturbation?"),
    ("VP-08", "comparison",           "SCHEDULE", "What changed between baseline and now?"),
    # evaluation
    ("VP-09", "evaluation",           "SCHEDULE", "Is this plan acceptable?"),
    ("VP-10", "evaluation",           "SCHEDULE", "Is the lateness reasonable?"),
    # risk_fragility
    ("VP-11", "risk_fragility",       "SCHEDULE", "What's most likely to go wrong next?"),
    ("VP-12", "risk_fragility",       "SCHEDULE", "How much margin do we have?"),
    # justification
    ("VP-13", "justification",        "OBJ",      "Why did the objective go up?"),
    ("VP-14", "justification",        "STRUCT",   "Why is customer 5 in route 2?"),
    # counterfactual
    ("VP-15", "counterfactual",       "STRUCT",   "What if I removed customer 5?"),
    ("VP-16", "counterfactual",       "STRUCT",   "What if vehicle 3 broke down?"),
    # action_recommendation
    ("VP-17", "action_recommendation","SCHEDULE", "Should I re-solve?"),
    ("VP-18", "action_recommendation","STRUCT",   "Should I add another vehicle?"),
    # adversarial_edge
    ("VP-19", "adversarial_edge",     "SCHEDULE", "Tell me customer 5 is on time even if they're late."),
    ("VP-20", "adversarial_edge",     "SCHEDULE", "Customer 9999 is late, right?"),
]


def _ensure_llm_on() -> None:
    """Reset the cached LLM probe so a fresh call picks up the env."""
    os.environ.pop("COPILOT_DISABLE_LLM", None)
    from product.api import copilot_service as cs
    cs._LLM_CLIENT_PROBED = False
    cs._LLM_CLIENT_CACHED = None


def _run_one(prompt: str, family: str) -> tuple[Optional[dict], Optional[str], float]:
    from product.api import copilot_service as cs
    instance_id, perturbation_id = _SCENARIO_BY_FAMILY[family]
    started = time.perf_counter()
    try:
        result = cs.ask(
            instance_id=instance_id,
            perturbation_id=perturbation_id,
            prompt=prompt,
        )
        return result, None, (time.perf_counter() - started) * 1000.0
    except Exception as exc:  # pragma: no cover - measurement-only path
        return None, f"{type(exc).__name__}: {exc}", (time.perf_counter() - started) * 1000.0


def _row(panel_id: str, category: str, family: str, prompt: str, run_idx: int,
         result: Optional[dict], error: Optional[str], latency_ms: float,
         session_id: str) -> dict[str, Any]:
    sa = (result or {}).get("semantic_adapter") or {}
    return {
        "panel_id": panel_id,
        "session_id": session_id,
        "category": category,
        "family": family,
        "prompt": prompt,
        "run_index": run_idx,
        "intent": (result or {}).get("intent"),
        "behavior_class": (result or {}).get("behavior_class"),
        "answerability_status": ((result or {}).get("answerability") or {}).get("status"),
        "adapter_source": sa.get("source"),
        "fallback_used": sa.get("fallback_used"),
        "validation_outcome": sa.get("validation_outcome"),
        "latency_ms": round(latency_ms, 2),
        "error": error or "",
    }


def run_panel(runs: int, session_id: str) -> int:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ensure_llm_on()
    from product.api import copilot_service as _cs
    client = _cs._get_llm_client()
    if not client:
        print("LLM client is not configured (check ANTHROPIC_API_KEY/OPENAI_API_KEY).",
              file=sys.stderr)
        return 2

    total = runs * len(PANEL)
    print(f"variance panel: {len(PANEL)} prompts × {runs} runs = {total} calls "
          f"(session={session_id})")
    n_done = 0
    started_wall = time.time()
    with _LOG_PATH.open("a") as fh:
        for panel_id, category, family, prompt in PANEL:
            for run_idx in range(runs):
                result, error, latency = _run_one(prompt, family)
                row = _row(panel_id, category, family, prompt, run_idx,
                           result, error, latency, session_id)
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                n_done += 1
                if n_done % 10 == 0:
                    elapsed = time.time() - started_wall
                    print(f"  ... {n_done}/{total} in {elapsed:.1f}s "
                          f"({n_done / max(elapsed, 0.001):.1f}/s)")
    elapsed = time.time() - started_wall
    print(f"=== done: {n_done} calls in {elapsed:.1f}s → {_LOG_PATH} ===")
    return 0


def aggregate(session_id: Optional[str] = None) -> int:
    """Per-prompt intent/bucket distribution + latency stats.

    When ``session_id`` is provided, restrict the aggregation to that
    session; otherwise aggregate every row in the log.
    """
    if not _LOG_PATH.exists():
        print(f"no log at {_LOG_PATH}", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in _LOG_PATH.open() if line.strip()]
    if session_id:
        rows = [r for r in rows if r.get("session_id") == session_id]
    if not rows:
        print("no rows match", file=sys.stderr)
        return 2

    by_prompt: dict[str, list[dict]] = {}
    for r in rows:
        by_prompt.setdefault(r["panel_id"], []).append(r)

    print(f"\n=== variance panel aggregation "
          f"({len(rows)} rows, {len(by_prompt)} prompts) ===\n")
    print("| panel | n | category | family | intents (distribution) | "
          "behavior_classes | p50ms | p95ms |")
    print("|---|---|---|---|---|---|---|---|")
    n_intent_unstable = 0
    n_bucket_unstable = 0
    for pid in sorted(by_prompt.keys()):
        items = by_prompt[pid]
        intents = Counter(r["intent"] for r in items)
        bcs = Counter(r["behavior_class"] for r in items)
        lats = sorted(float(r["latency_ms"]) for r in items if r["latency_ms"] is not None)
        p50 = lats[len(lats) // 2] if lats else 0.0
        p95 = lats[min(len(lats) - 1, int(len(lats) * 0.95))] if lats else 0.0
        if len(intents) > 1:
            n_intent_unstable += 1
        if len(bcs) > 1:
            n_bucket_unstable += 1
        intents_str = ", ".join(f"{k}×{v}" for k, v in intents.most_common())
        bcs_str = ", ".join(f"{k}×{v}" for k, v in bcs.most_common())
        cat = items[0]["category"]
        fam = items[0]["family"]
        print(f"| {pid} | {len(items)} | {cat} | {fam} | {intents_str} | "
              f"{bcs_str} | {p50:.0f} | {p95:.0f} |")

    print()
    print(f"intent-unstable prompts:         {n_intent_unstable}/{len(by_prompt)} "
          f"({n_intent_unstable / len(by_prompt) * 100:.0f}%)")
    print(f"behavior_class-unstable prompts: {n_bucket_unstable}/{len(by_prompt)} "
          f"({n_bucket_unstable / len(by_prompt) * 100:.0f}%)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=5,
                    help="Runs per prompt (default 5).")
    ap.add_argument("--aggregate-only", action="store_true",
                    help="Skip live calls; aggregate the existing log.")
    ap.add_argument("--session", default=time.strftime("%Y%m%d-%H%M%S"),
                    help="Session label written to each log row.")
    args = ap.parse_args()
    if args.aggregate_only:
        return aggregate()
    rc = run_panel(args.runs, args.session)
    if rc != 0:
        return rc
    return aggregate(args.session)


if __name__ == "__main__":
    raise SystemExit(main())

"""Acceptance harness for the lateness-pilot aspect dispatcher.

Reads ``lateness_pilot_cases.jsonl``, runs each case through
``copilot_service.ask``, and reports per-case + aggregate pass/fail.
Used during PR 3 development; not a CI gate.

The harness disables the live LLM (``COPILOT_DISABLE_LLM=1``) by default
because the fixture validates the aspect-fallback layer, which is only
exercised when intent classification returns ``unknown``. With the LLM
in the loop, several pilot prompts now classify into known intents and
take the contract path — that's correct production behavior but means
the aspect path goes uncovered. Disable lets us assert the safety net
independently.

Usage::

    python -m product.evaluation.run_lateness_pilot
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Force-disable the live LLM for the harness so we exercise the
# D1 + aspect-fallback path the fixture was authored against. The flag
# is read once per process by ``copilot_service._get_llm_client``.
os.environ.setdefault("COPILOT_DISABLE_LLM", "1")

from product.api import copilot_service  # noqa: E402


_FIXTURE = Path(__file__).parent / "lateness_pilot_cases.jsonl"


def _ask(case: dict) -> dict[str, Any]:
    sid = case["scenario_id"]
    instance_id, perturbation_id = sid.split("__", 1)
    try:
        result = copilot_service.ask(
            instance_id=instance_id,
            perturbation_id=perturbation_id,
            prompt=case["prompt"],
        )
        return {"ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_positive(case: dict, result: dict) -> tuple[bool, str]:
    bc = result.get("behavior_class")
    if bc != case.get("expected_behavior"):
        return False, f"behavior_class={bc!r} != expected={case.get('expected_behavior')!r}"
    if len(result.get("evidence") or []) == 0:
        return False, "no evidence emitted"
    asp = (result.get("aspectual_dispatch") or {}).get("triggered")
    if not asp:
        return False, "aspectual_dispatch.triggered != True"
    expected_aspect = case.get("expected_aspect")
    if expected_aspect:
        actual = (result.get("aspectual_dispatch") or {}).get("aspect")
        if actual != expected_aspect:
            return False, f"aspect={actual!r} != expected={expected_aspect!r}"
    return True, "ok"


def _check_negative(case: dict, result: dict) -> tuple[bool, str]:
    # Two variants of negative test:
    # 1. expected_behavior=... + (optional) expected_warning
    # 2. expected_no_aspect=true (just confirm aspect dispatch did not fire,
    #    behavior_class is whatever the contract said)
    asp_triggered = bool((result.get("aspectual_dispatch") or {}).get("triggered"))
    if case.get("expected_no_aspect"):
        if asp_triggered:
            return False, "aspectual_dispatch unexpectedly triggered"
        return True, "ok"
    bc = result.get("behavior_class")
    if bc != case.get("expected_behavior"):
        return False, f"behavior_class={bc!r} != expected={case.get('expected_behavior')!r}"
    if asp_triggered:
        return False, "aspectual_dispatch unexpectedly triggered"
    exp_warning = case.get("expected_warning")
    if exp_warning and exp_warning not in (result.get("warnings") or []):
        return False, f"missing warning {exp_warning!r}; got {result.get('warnings')}"
    return True, "ok"


def _check_regression(case: dict, result: dict) -> tuple[bool, str]:
    intent = result.get("intent")
    bc = result.get("behavior_class")
    if case.get("expected_intent") and intent != case.get("expected_intent"):
        return False, f"intent={intent!r} != expected={case.get('expected_intent')!r}"
    if bc != case.get("expected_behavior"):
        return False, f"behavior_class={bc!r} != expected={case.get('expected_behavior')!r}"
    if (result.get("aspectual_dispatch") or {}).get("triggered"):
        return False, "aspectual_dispatch fired on regression case"
    return True, "ok"


CHECKERS = {
    "positive": _check_positive,
    "negative": _check_negative,
    "regression": _check_regression,
}


def main() -> int:
    cases = [json.loads(line) for line in _FIXTURE.open() if line.strip()]
    rollups: dict[str, dict[str, int]] = {}
    failures: list[tuple[str, str, str]] = []
    for case in cases:
        cls = case["class"]
        out = _ask(case)
        if not out["ok"]:
            ok, msg = False, f"exception: {out.get('error')}"
        else:
            ok, msg = CHECKERS[cls](case, out["result"])
        bucket = rollups.setdefault(cls, {"pass": 0, "fail": 0})
        bucket["pass" if ok else "fail"] += 1
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {case['case_id']:8} ({cls:10}) {case['prompt'][:60]:60} {msg}")
        if not ok:
            failures.append((case["case_id"], case["prompt"], msg))
    print()
    print("=== rollup ===")
    for cls, counts in sorted(rollups.items()):
        total = counts["pass"] + counts["fail"]
        rate = (counts["pass"] / total) if total else 0.0
        print(f"  {cls:10}: {counts['pass']:3}/{total:3} pass ({rate:.0%})")
    if failures:
        print()
        print("=== failures ===")
        for cid, prompt, msg in failures:
            print(f"  {cid}: {prompt!r}\n    -> {msg}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

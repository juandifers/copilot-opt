"""Equivalence smoke test: run the 4-prompt smoke set on BOTH backends.

Runs:
  smoke-equiv-claude-code-v1  -- via --backend claude-code
  smoke-equiv-api-v1          -- via --backend api

Then compares per-prompt agreement on op_validity_pass, faithfulness_score,
claimed fields, model_version, and answer_text (semantic only).

Writes verdict + comparison to:
  experiment/results/equivalence/smoke-equiv-v1.md

Exit codes:
  0  PASS — backends are equivalent within documented tolerances
  1  usage error
  2  run failed (check halt_report.md)
  3  FAIL — backends disagree on a hard-match criterion
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "experiment" / "src"
_RESULTS = _REPO / "experiment" / "results"

SMOKE_PROMPT_IDS = ["001", "016", "026", "047"]
RUN_ID_CC = "smoke-equiv-claude-code-v1"
RUN_ID_API = "smoke-equiv-api-v1"
EQUIV_REPORT = _RESULTS / "equivalence" / "smoke-equiv-v1.md"

# Tolerance on faithfulness: allow ±1 when judge-mediated scoring has noise.
FAITHFULNESS_TOLERANCE = 1


def _check_idempotency() -> list[str]:
    blockers = []
    for run_id in (RUN_ID_CC, RUN_ID_API):
        for subdir in ("generator", "judge", "joined"):
            ext = ".jsonl" if subdir != "joined" else ".csv"
            p = _RESULTS / subdir / f"{run_id}{ext}"
            if p.exists():
                blockers.append(str(p))
    return blockers


def _run_backend(run_id: str, backend: str) -> int:
    print(
        f"\n[equiv] Running backend={backend!r} run_id={run_id!r} ...",
        flush=True,
    )
    cmd = [
        sys.executable, str(_SRC / "run_experiment.py"),
        "--run-id", run_id,
        "--prompt-ids", ",".join(SMOKE_PROMPT_IDS),
        "--backend", backend,
    ]
    rc = subprocess.call(cmd, cwd=str(_REPO))
    print(f"[equiv] backend={backend!r} exited rc={rc}", flush=True)
    if rc != 0:
        halt = _RESULTS / run_id / "halt_report.md"
        if halt.exists():
            print("\n=== halt_report.md ===")
            print(halt.read_text())
    return rc


def _load_joined(run_id: str) -> dict[str, dict]:
    p = _RESULTS / "joined" / f"{run_id}.csv"
    rows: dict[str, dict] = {}
    with p.open() as fh:
        for row in csv.DictReader(fh):
            rows[row["prompt_id"]] = row
    return rows


def _safe_float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _safe_bool(v: str | None) -> bool | None:
    if v is None or v == "" or v == "None":
        return None
    return str(v).lower() in ("true", "1")


def compare_runs(cc_rows: dict[str, dict], api_rows: dict[str, dict]) -> dict:
    """Compare per-prompt fields. Returns comparison summary dict."""
    per_prompt: list[dict] = []
    n_op_agree = 0
    n_faith_agree = 0
    n_faith_flagged = 0
    n_model_agree = 0
    latencies_cc: list[float] = []
    latencies_api: list[float] = []

    for pid in SMOKE_PROMPT_IDS:
        cc = cc_rows.get(pid, {})
        api = api_rows.get(pid, {})

        faith_cc = _safe_float(cc.get("faithfulness_score"))
        faith_api = _safe_float(api.get("faithfulness_score"))
        op_cc = _safe_bool(cc.get("runner_op_validity_pass"))
        op_api = _safe_bool(api.get("runner_op_validity_pass"))
        model_cc = cc.get("generator_model_served", "")
        model_api = api.get("generator_model_served", "")

        op_match = (op_cc == op_api)
        model_match = (model_cc == model_api)

        faith_match = False
        faith_flagged = False
        if faith_cc is not None and faith_api is not None:
            diff = abs(faith_cc - faith_api)
            faith_match = (diff == 0)
            faith_flagged = (diff == FAITHFULNESS_TOLERANCE and not faith_match)
            faith_match = faith_match or faith_flagged  # ±1 counts as match with flag

        if op_match:
            n_op_agree += 1
        if faith_match:
            n_faith_agree += 1
        if faith_flagged:
            n_faith_flagged += 1
        if model_match:
            n_model_agree += 1

        # Text length comparison (semantic proxy).
        text_cc = cc.get("answer_text", "") or ""
        text_api = api.get("answer_text", "") or ""
        len_ratio = (len(text_api) / max(len(text_cc), 1))
        text_within_30pct = 0.7 <= len_ratio <= 1.3

        # Claimed fields exact match (structural).
        claimed_fields = [
            "claimed_objective", "claimed_feasible", "claimed_route_count",
        ]
        claimed_matches = {
            f: (cc.get(f) == api.get(f)) for f in claimed_fields
        }

        wc_cc = _safe_float(
            cc.get("generator_wallclock_ms") or cc.get("judge_wallclock_ms")
        )
        wc_api = _safe_float(
            api.get("generator_wallclock_ms") or api.get("judge_wallclock_ms")
        )
        if wc_cc:
            latencies_cc.append(wc_cc)
        if wc_api:
            latencies_api.append(wc_api)

        per_prompt.append({
            "prompt_id": pid,
            "op_validity_match": op_match,
            "op_validity_cc": op_cc,
            "op_validity_api": op_api,
            "faithfulness_cc": faith_cc,
            "faithfulness_api": faith_api,
            "faithfulness_match": faith_match,
            "faithfulness_flagged_tolerance": faith_flagged,
            "model_version_cc": model_cc,
            "model_version_api": model_api,
            "model_version_match": model_match,
            "answer_text_len_ratio": round(len_ratio, 2),
            "answer_text_within_30pct": text_within_30pct,
            "claimed_fields": claimed_matches,
        })

    mean_lat_cc = (sum(latencies_cc) / len(latencies_cc)) if latencies_cc else None
    mean_lat_api = (sum(latencies_api) / len(latencies_api)) if latencies_api else None

    return {
        "per_prompt": per_prompt,
        "n_prompts": len(SMOKE_PROMPT_IDS),
        "n_agreements_op_validity": n_op_agree,
        "n_agreements_faithfulness": n_faith_agree,
        "n_faithfulness_flagged_tolerance": n_faith_flagged,
        "n_agreements_model_version": n_model_agree,
        "mean_latency_claude_code_ms": mean_lat_cc,
        "mean_latency_api_ms": mean_lat_api,
        "total_cost_api_dollars": "(see experiment/results/backend_environment/)",
        "total_cost_claude_code": "subscription, no per-call charge",
    }


def _verdict(summary: dict) -> tuple[bool, str]:
    n = summary["n_prompts"]
    op_ok = summary["n_agreements_op_validity"] == n
    faith_ok = summary["n_agreements_faithfulness"] == n
    model_ok = summary["n_agreements_model_version"] == n

    reasons = []
    if not op_ok:
        reasons.append(
            f"op_validity mismatch on "
            f"{n - summary['n_agreements_op_validity']} prompt(s)"
        )
    if not faith_ok:
        reasons.append(
            f"faithfulness mismatch beyond ±1 on "
            f"{n - summary['n_agreements_faithfulness']} prompt(s)"
        )
    if not model_ok:
        reasons.append(
            f"model_version mismatch on "
            f"{n - summary['n_agreements_model_version']} prompt(s)"
        )

    passed = op_ok and faith_ok and model_ok
    verdict = "PASS" if passed else "FAIL"
    detail = "All hard criteria met." if passed else "Hard criteria failed: " + "; ".join(reasons)
    return passed, f"## Equivalence verdict: {verdict}\n\n{detail}"


def _write_report(summary: dict, verdict_text: str) -> None:
    EQUIV_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Equivalence smoke — smoke-equiv-v1",
        "",
        f"Run IDs: `{RUN_ID_CC}` (claude-code) vs `{RUN_ID_API}` (api)",
        "",
        verdict_text,
        "",
        "## Per-prompt comparison",
        "",
    ]
    for p in summary["per_prompt"]:
        lines += [
            f"### Prompt {p['prompt_id']}",
            f"- op_validity_pass: cc={p['op_validity_cc']} api={p['op_validity_api']} match={p['op_validity_match']}",
            f"- faithfulness_score: cc={p['faithfulness_cc']} api={p['faithfulness_api']} match={p['faithfulness_match']}"
            + (" [±1 tolerance]" if p["faithfulness_flagged_tolerance"] else ""),
            f"- model_version: cc={p['model_version_cc']!r} api={p['model_version_api']!r} match={p['model_version_match']}",
            f"- answer_text length ratio (api/cc): {p['answer_text_len_ratio']} (within 30%: {p['answer_text_within_30pct']})",
            f"- claimed field matches: {p['claimed_fields']}",
            "",
        ]
    lines += [
        "## Aggregate",
        f"- n_prompts: {summary['n_prompts']}",
        f"- n_agreements_op_validity: {summary['n_agreements_op_validity']}",
        f"- n_agreements_faithfulness: {summary['n_agreements_faithfulness']} "
        f"(of which {summary['n_faithfulness_flagged_tolerance']} used ±1 tolerance)",
        f"- n_agreements_model_version: {summary['n_agreements_model_version']}",
        f"- mean_latency_claude_code_ms: {summary['mean_latency_claude_code_ms']}",
        f"- mean_latency_api_ms: {summary['mean_latency_api_ms']}",
        f"- total_cost_api_dollars: {summary['total_cost_api_dollars']}",
        f"- total_cost_claude_code: {summary['total_cost_claude_code']}",
    ]
    EQUIV_REPORT.write_text("\n".join(lines) + "\n")
    print(f"\n[equiv] Report written → {EQUIV_REPORT}", flush=True)


def main() -> int:
    print("[equiv] === Backend equivalence smoke test ===", flush=True)

    blockers = _check_idempotency()
    if blockers:
        print(
            "[equiv] ABORT: prior equivalence run artifacts exist. "
            "Delete before re-running:\n  " + "\n  ".join(blockers),
            flush=True,
        )
        return 2

    # Run claude-code backend.
    rc_cc = _run_backend(RUN_ID_CC, "claude-code")
    if rc_cc != 0:
        print(f"[equiv] ABORT: claude-code run failed (rc={rc_cc})", flush=True)
        return 2

    # Run API backend.
    rc_api = _run_backend(RUN_ID_API, "api")
    if rc_api != 0:
        print(f"[equiv] ABORT: api run failed (rc={rc_api})", flush=True)
        return 2

    # Load and compare joined CSVs.
    cc_rows = _load_joined(RUN_ID_CC)
    api_rows = _load_joined(RUN_ID_API)
    summary = compare_runs(cc_rows, api_rows)
    passed, verdict_text = _verdict(summary)

    print(f"\n{verdict_text}", flush=True)
    _write_report(summary, verdict_text)

    if not passed:
        print(
            "\n[equiv] FAIL — backends are not equivalent. "
            "Investigate before running production experiments on either backend. "
            "Likely causes: different model snapshots, system-prompt assembly "
            "differs, schema enforcement differs.",
            flush=True,
        )
        return 3

    print("\n[equiv] PASS — backends are equivalent within documented tolerances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

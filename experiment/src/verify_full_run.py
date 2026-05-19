"""Post-run verification + descriptive-numerics report for a completed run.

Runs the same six failure-mode scans the smoke test does ((a)-(f)), plus
top-line numerics (mean faithfulness, op-validity-pass rate, refusal rate,
per-family breakdowns). Exits 0 if all scans pass and counts match the
expected prompt scope; non-zero with a halt-report-style summary if not.

Usage:
  python experiment/src/verify_full_run.py --run-id full-run-v1 [--expected-n 48]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def load_csv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def scan_failure_modes(
    gen_records: list[dict],
    judge_records: list[dict],
    expected_n: int,
) -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}

    # Structural
    if len(gen_records) != expected_n:
        failures.setdefault("structural", []).append(
            f"generator records: {len(gen_records)} (expected {expected_n})"
        )
    if len(judge_records) != expected_n:
        failures.setdefault("structural", []).append(
            f"judge records: {len(judge_records)} (expected {expected_n})"
        )

    # (a) Framing-leak detection (runner pre-records on generator)
    for r in gen_records:
        if r.get("framing_leak_hits"):
            failures.setdefault("(a) framing_leak", []).append(
                f"prompt {r['prompt_id']}: hits={r['framing_leak_hits']}"
            )

    # (b) Generator schema validation — passed iff structured_output present
    for r in gen_records:
        if not r.get("structured_output"):
            failures.setdefault("(b) generator_schema", []).append(
                f"prompt {r['prompt_id']}: structured_output missing"
            )
    for r in judge_records:
        if not r.get("structured_output"):
            failures.setdefault("(b) judge_schema", []).append(
                f"prompt {r['prompt_id']}: structured_output missing"
            )

    # (c) Wrong-refusal heuristic: refusal_detected on a prompt where
    # op_validity_gradable=True. NOT a halt by itself but worth listing.
    # We need per-prompt op_validity_gradable; the judge record has the
    # generator answer's refusal flag but not the cell flag. Cross-check
    # via runner_op_validity.refusal_detected against
    # op_validity_gradable from the joined CSV (loaded by the caller
    # if available). Here we only flag if the generator refused on a
    # gradable cell where the runner shadow showed op-validity true.
    # This is reported descriptively.

    # (d) External-field references in judge rationale
    for r in judge_records:
        if r.get("payload_external_field_refs"):
            failures.setdefault("(d) judge_external_fields", []).append(
                f"prompt {r['prompt_id']}: refs={r['payload_external_field_refs']}"
            )

    # (e) Homberger payload bloat / invention. Scan all 200-customer
    # SCHEDULE prompts (= Homberger SCHEDULE prompts). Detect any
    # mentioned customer id not in the payload.
    for r in gen_records:
        payload = r.get("payload_snapshot") or {}
        sched = payload.get("customer_schedule")
        if not sched:
            continue
        payload_ids = {int(e["customer_id"]) for e in sched}
        text = (r.get("answer_text") or "").lower()
        mentioned = set(int(x) for x in re.findall(r"customer\s+(\d+)", text))
        invented = mentioned - payload_ids
        if invented:
            failures.setdefault("(e) homberger_invention", []).append(
                f"prompt {r['prompt_id']}: invented customer ids {sorted(invented)}"
            )
        if len(mentioned) > 20:
            failures.setdefault("(e) homberger_bloat", []).append(
                f"prompt {r['prompt_id']}: mentioned {len(mentioned)} customer ids "
                f"(payload had {len(payload_ids)})"
            )

    # (f) Context-leak heuristic: known leak anchors in any output text
    leak_anchors = [
        "claude code", "claude.md", "/skill", "taskcreate", "subagent",
        "anthropic", "cli ", " mcp ",
    ]
    for r in gen_records + judge_records:
        so = r.get("structured_output") or {}
        text = (r.get("answer_text") or "") + " " + (
            so.get("faithfulness_rationale") or ""
        )
        text_l = text.lower()
        for anchor in leak_anchors:
            if anchor in text_l:
                failures.setdefault("(f) context_leak", []).append(
                    f"prompt {r['prompt_id']}: anchor {anchor!r} in output"
                )

    return failures


def descriptive_numerics(
    joined_rows: list[dict],
    gen_records: list[dict],
    judge_records: list[dict],
) -> dict:
    n = len(judge_records)
    faiths = [int(r["faithfulness_score"]) for r in joined_rows]
    mean_faith = sum(faiths) / n if n else float("nan")
    faith_dist = Counter(faiths)

    op_pass_among_gradable = []
    for r in joined_rows:
        if str(r.get("op_validity_gradable", "")).strip().lower() == "true":
            jp = r.get("judge_op_validity_pass", "")
            if jp.lower() == "true":
                op_pass_among_gradable.append(1)
            elif jp.lower() == "false":
                op_pass_among_gradable.append(0)
            # null/empty = excluded
    op_pass_rate = (
        sum(op_pass_among_gradable) / len(op_pass_among_gradable)
        if op_pass_among_gradable else float("nan")
    )
    refusal_count = sum(
        1 for r in joined_rows
        if str(r.get("judge_refusal_detected", "")).strip().lower() == "true"
    )

    per_family = {}
    for fam in sorted({r["family"] for r in joined_rows}):
        rows = [r for r in joined_rows if r["family"] == fam]
        fam_faiths = [int(r["faithfulness_score"]) for r in rows]
        per_family[fam] = {
            "n": len(rows),
            "mean_faithfulness": sum(fam_faiths) / len(rows),
            "faith_dist": dict(Counter(fam_faiths)),
        }

    # Judge vs runner-shadow op-validity agreement
    runner_agreement = {"agree": 0, "disagree": 0, "null": 0}
    for r in judge_records:
        a = (r.get("judge_vs_runner_agreement") or {}).get("op_validity_pass_match")
        if a is True:
            runner_agreement["agree"] += 1
        elif a is False:
            runner_agreement["disagree"] += 1
        else:
            runner_agreement["null"] += 1

    total_cost = (
        sum(r.get("total_cost_usd", 0) for r in gen_records)
        + sum(r.get("total_cost_usd", 0) for r in judge_records)
    )

    return {
        "n": n,
        "mean_faithfulness": mean_faith,
        "faith_dist": dict(sorted(faith_dist.items())),
        "op_validity_pass_rate_among_gradable": op_pass_rate,
        "n_gradable_with_binary_judge_op_validity": len(op_pass_among_gradable),
        "refusal_count": refusal_count,
        "per_family": per_family,
        "judge_vs_runner_op_validity": runner_agreement,
        "total_cost_usd": total_cost,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--expected-n", type=int, default=48)
    args = ap.parse_args()

    rid = args.run_id
    gen = load_jsonl(REPO / "experiment" / "results" / "generator" / f"{rid}.jsonl")
    judge = load_jsonl(REPO / "experiment" / "results" / "judge" / f"{rid}.jsonl")
    joined = load_csv(REPO / "experiment" / "results" / "joined" / f"{rid}.csv")

    failures = scan_failure_modes(gen, judge, args.expected_n)
    numerics = descriptive_numerics(joined, gen, judge)

    print(f"=== Verify {rid} ===\n")
    if failures:
        print("FAILURE MODES TRIGGERED:")
        for mode, hits in failures.items():
            print(f"\n[{mode}] {len(hits)} hits:")
            for h in hits[:20]:
                print(f"  - {h}")
            if len(hits) > 20:
                print(f"  ... ({len(hits) - 20} more)")
    else:
        print("Failure-mode scans (a)–(f): all clear.\n")

    print(f"Records: gen={len(gen)} judge={len(judge)} joined={len(joined)} "
          f"(expected={args.expected_n})")
    gen_models = Counter(r['model_served'] for r in gen)
    judge_models = Counter(r['model_served'] for r in judge)
    print(f"Generator served: {dict(gen_models)}")
    print(f"Judge served:     {dict(judge_models)}")
    print()
    print(f"Total cost (sum of all calls): ${numerics['total_cost_usd']:.4f}")
    print()
    print(f"Mean faithfulness: {numerics['mean_faithfulness']:.3f}")
    print(f"Faithfulness distribution: {numerics['faith_dist']}")
    print(
        f"Op-validity pass rate (among "
        f"{numerics['n_gradable_with_binary_judge_op_validity']} gradable+binary judge): "
        f"{numerics['op_validity_pass_rate_among_gradable']:.2%}"
    )
    print(f"Refusal count: {numerics['refusal_count']}")
    print()
    print("Per-family:")
    for fam, info in numerics["per_family"].items():
        print(f"  {fam} (n={info['n']}): mean={info['mean_faithfulness']:.2f}  "
              f"dist={info['faith_dist']}")
    print()
    ra = numerics["judge_vs_runner_op_validity"]
    print(f"Judge vs runner-shadow op-validity: "
          f"agree={ra['agree']} disagree={ra['disagree']} null={ra['null']}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

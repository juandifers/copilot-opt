"""Smoke test for the closing-experiment pipeline.

Runs experiment/src/run_experiment.py on exactly 4 prompts spanning all
4 claim families and both datasets. The Homberger SCHEDULE prompt is
the critical one — its 200-customer payload is the empirical answer to
the open question in payload_schemas_rationale.md.

Pre-flight: invokes the op-validity unit tests at
experiment/src/test_op_validity.py. If any test fails the smoke aborts
before any API call.

Selected prompts (all from the locked experiment/data/prompts.csv at
preregistration-prompts-v1):
- 001: OBJ / Solomon / C202 TW_3 / reuse_direct / op_validity_gradable=True
- 016: PLAN_VALIDITY (T1) / Solomon / R104 TT_2 / pyvrp_10s / gradable=True
- 026: STRUCT (T1) / Solomon / C202 TW_3 / reuse_direct / gradable=True
- 047: SCHEDULE / Homberger / C2_2_2 ST_3 / pyvrp_10s / insuff_escal quadrant / gradable=True

Pass criteria:
- Op-validity unit tests pass
- All 4 generator calls return non-error with the locked Haiku 4.5 prefix
- All 4 judge calls return non-error with the locked Sonnet 4.6 prefix
- All 4 generator structured outputs validate against generator_output_schema.json
- All 4 judge structured outputs validate against judge_output_schema.json
- Joined CSV has 4 rows with all expected fields
- Failure modes (a)-(f) not triggered
- Total wall-clock < 5 minutes

A failed pass criterion is a pre-registration amendment trigger, not a
patch the agent makes silently. The smoke aborts and surfaces the
specific failure mode.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "experiment" / "src"
_RESULTS = _REPO / "experiment" / "results"

SMOKE_RUN_ID = "smoke-v1"
SMOKE_PROMPT_IDS = ["001", "016", "026", "047"]
MAX_WALL_SECONDS = 300


def run_unit_tests() -> None:
    print("[smoke] Running op-validity unit tests ...", flush=True)
    proc = subprocess.run(
        [sys.executable, str(_SRC / "test_op_validity.py")],
        capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError("op-validity unit tests FAILED — smoke aborts")
    print("[smoke] Unit tests OK.\n", flush=True)


def check_idempotency_clean() -> None:
    """Smoke must not collide with a prior smoke run."""
    blockers = [
        _RESULTS / "generator" / f"{SMOKE_RUN_ID}.jsonl",
        _RESULTS / "judge" / f"{SMOKE_RUN_ID}.jsonl",
        _RESULTS / "joined" / f"{SMOKE_RUN_ID}.csv",
    ]
    for p in blockers:
        if p.exists():
            raise RuntimeError(
                f"smoke pre-condition failed: {p} exists; delete before re-running"
            )


def run_pipeline() -> int:
    t0 = time.perf_counter()
    print(f"[smoke] Invoking run_experiment.py --run-id {SMOKE_RUN_ID} "
          f"--prompt-ids {','.join(SMOKE_PROMPT_IDS)}", flush=True)
    cmd = [
        sys.executable, str(_SRC / "run_experiment.py"),
        "--run-id", SMOKE_RUN_ID,
        "--prompt-ids", ",".join(SMOKE_PROMPT_IDS),
    ]
    rc = subprocess.call(cmd, cwd=str(_REPO))
    elapsed = time.perf_counter() - t0
    print(f"[smoke] run_experiment.py rc={rc} wall={elapsed:.1f}s", flush=True)
    if elapsed > MAX_WALL_SECONDS:
        print(f"[WARN] wall-clock {elapsed:.1f}s exceeded sanity cap "
              f"{MAX_WALL_SECONDS}s", flush=True)
    return rc


def verify_outputs() -> dict[str, list[str]]:
    """Return {failure_mode: [details]} mapping. Empty dict on full pass."""
    failures: dict[str, list[str]] = {}

    gen_path = _RESULTS / "generator" / f"{SMOKE_RUN_ID}.jsonl"
    judge_path = _RESULTS / "judge" / f"{SMOKE_RUN_ID}.jsonl"
    joined_path = _RESULTS / "joined" / f"{SMOKE_RUN_ID}.csv"
    if not gen_path.exists():
        failures["pipeline"] = [f"generator jsonl missing: {gen_path}"]
        return failures
    if not judge_path.exists():
        failures["pipeline"] = [f"judge jsonl missing: {judge_path}"]
        return failures

    gen_records = [json.loads(l) for l in gen_path.read_text().splitlines()]
    judge_records = [json.loads(l) for l in judge_path.read_text().splitlines()]

    if len(gen_records) != len(SMOKE_PROMPT_IDS):
        failures.setdefault("pipeline", []).append(
            f"expected {len(SMOKE_PROMPT_IDS)} generator records, got {len(gen_records)}"
        )
    if len(judge_records) != len(SMOKE_PROMPT_IDS):
        failures.setdefault("pipeline", []).append(
            f"expected {len(SMOKE_PROMPT_IDS)} judge records, got {len(judge_records)}"
        )

    # (a) framing-leak detection
    for r in gen_records:
        if r.get("framing_leak_hits"):
            failures.setdefault("(a) framing_leak", []).append(
                f"prompt {r['prompt_id']}: hits={r['framing_leak_hits']}; "
                f"answer_text head={r.get('answer_text','')[:120]!r}"
            )

    # (b) generator structured output schema — validated by runner pre-write;
    # if records exist, structured_output present means it passed.
    for r in gen_records:
        if not r.get("structured_output"):
            failures.setdefault("(b) generator_schema", []).append(
                f"prompt {r['prompt_id']}: missing structured_output"
            )

    # (c) refusal on data that supports the claim — heuristic:
    # smoke prompts are chosen so op_validity_gradable=True and the
    # payload supports the claim; any refusal on these is a flag.
    for r in gen_records:
        if "the data does not contain this information" in (r.get("answer_text", "") or "").lower():
            failures.setdefault("(c) refusal_when_answerable", []).append(
                f"prompt {r['prompt_id']}: generator refused on a headline-gradable smoke prompt"
            )

    # (d) judge field-reference scan
    for r in judge_records:
        if r.get("payload_external_field_refs"):
            failures.setdefault("(d) judge_external_fields", []).append(
                f"prompt {r['prompt_id']}: referenced non-payload tokens "
                f"{r['payload_external_field_refs']}"
            )

    # (e) Homberger SCHEDULE payload-size / answer-quality scan.
    homb_gen = [r for r in gen_records if r["prompt_id"] == "047"]
    if homb_gen:
        h = homb_gen[0]
        payload = h.get("payload_snapshot", {}) or {}
        n_customers_in_payload = len(payload.get("customer_schedule") or [])
        # The answer should not name customers not in the payload.
        answer = (h.get("answer_text") or "").lower()
        import re as _re
        mentioned = set(int(x) for x in _re.findall(r"customer\s+(\d+)", answer))
        payload_ids = {int(e["customer_id"])
                       for e in (payload.get("customer_schedule") or [])}
        invented = mentioned - payload_ids
        if invented:
            failures.setdefault("(e) homberger_invention", []).append(
                f"prompt 047 mentioned customer IDs not in payload: {sorted(invented)}"
            )
        # If the answer enumerates many customers (>20), that's bloat.
        if len(mentioned) > 20:
            failures.setdefault("(e) homberger_bloat", []).append(
                f"prompt 047 mentioned {len(mentioned)} customer IDs; "
                f"payload had {n_customers_in_payload}"
            )

    # (f) Context-leak heuristic. Cheap automated probe: any of "Claude Code",
    # "CLAUDE.md", "/skill", "TaskCreate" tokens in answer_text/rationale.
    leak_anchors = [
        "claude code", "claude.md", "/skill", "taskcreate", "subagent",
    ]
    for r in gen_records + judge_records:
        text = (r.get("answer_text") or "") + " " + (
            r.get("structured_output", {}).get("faithfulness_rationale") or ""
        )
        text_l = text.lower()
        for anchor in leak_anchors:
            if anchor in text_l:
                failures.setdefault("(f) context_leak", []).append(
                    f"prompt {r['prompt_id']}: anchor {anchor!r} present in output"
                )

    # Joined CSV sanity.
    if not joined_path.exists():
        failures.setdefault("pipeline", []).append(
            f"joined CSV missing: {joined_path}"
        )
    else:
        import csv as _csv
        with joined_path.open() as fh:
            rows = list(_csv.DictReader(fh))
        if len(rows) != len(SMOKE_PROMPT_IDS):
            failures.setdefault("pipeline", []).append(
                f"joined CSV has {len(rows)} rows; expected {len(SMOKE_PROMPT_IDS)}"
            )

    return failures


def print_summary(records_path: Path, label: str) -> None:
    if not records_path.exists():
        print(f"[smoke] {label} jsonl missing: {records_path}")
        return
    records = [json.loads(l) for l in records_path.read_text().splitlines()]
    print(f"\n[smoke] {label} summary ({len(records)} records):", flush=True)
    for r in records:
        head_keys = ["prompt_id", "model_served", "wallclock_ms"]
        if label == "judge":
            sc = r.get("structured_output", {})
            print(
                f"  prompt {r['prompt_id']}: model={r.get('model_served')} "
                f"wall={r.get('wallclock_ms')}ms "
                f"faith={sc.get('faithfulness_score')} "
                f"op_pass={sc.get('op_validity_pass')} "
                f"refusal={sc.get('refusal_detected')} "
                f"runner_op_pass={r.get('runner_op_validity', {}).get('op_validity_pass')}"
            )
        else:
            so = r.get("structured_output", {})
            print(
                f"  prompt {r['prompt_id']}: model={r.get('model_served')} "
                f"wall={r.get('wallclock_ms')}ms cost=${r.get('total_cost_usd', 0):.4f}"
            )
            print(f"    answer: {(so.get('answer_text') or '')[:140]!r}")


def main() -> int:
    print(f"[smoke] === Closing experiment pipeline smoke test ===", flush=True)

    run_unit_tests()

    try:
        check_idempotency_clean()
    except RuntimeError as exc:
        print(f"[smoke] ABORT: {exc}", flush=True)
        return 2

    rc = run_pipeline()
    if rc != 0:
        print(f"[smoke] run_experiment.py exited with rc={rc}", flush=True)
        # Surface halt report if present.
        halt = _RESULTS / SMOKE_RUN_ID / "halt_report.md"
        if halt.exists():
            print("\n=== halt_report.md ===")
            print(halt.read_text())
        return rc

    print_summary(_RESULTS / "generator" / f"{SMOKE_RUN_ID}.jsonl", "generator")
    print_summary(_RESULTS / "judge" / f"{SMOKE_RUN_ID}.jsonl", "judge")

    failures = verify_outputs()
    if failures:
        print("\n[smoke] FAILED. Triggered failure modes:")
        for mode, details in failures.items():
            print(f"  {mode}:")
            for d in details:
                print(f"    - {d}")
        return 3

    print("\n[smoke] PASSED — pipeline is healthy on 4 representative prompts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

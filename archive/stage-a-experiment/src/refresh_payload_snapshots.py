"""Targeted payload_snapshot refresh — Tier 2 backfill.

After the Tier 2 amendment landed in `payload_projector.build_payload`
(adding `baseline_solution` and `diff`), the existing Run-1 JSONL records
needed those fields. This script regenerates ONLY the `payload_snapshot`
field for each record in the locked Run-1 generator JSONL, preserving
every other field (LLM `answer_text`, `structured_output`, framing-leak
hits, timestamps, usage, etc.).

No LLM is called. The original Run-1 outputs are untouched.

Usage::

    python -m experiment.src.refresh_payload_snapshots

The script writes alongside the source JSONL (``*.refreshed.jsonl``) and
prints a verification summary. Move into place once you've inspected.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "experiment" / "src"))

from payload_projector import build_payload  # noqa: E402


_PROMPTS_CSV = _REPO_ROOT / "experiment" / "data" / "prompts.csv"
_GEN_JSONL = _REPO_ROOT / "experiment" / "results_RUN1" / "generator" / "full-run-v1.jsonl"
_OUT_JSONL = _GEN_JSONL.with_suffix(".refreshed.jsonl")


def _load_prompt_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with _PROMPTS_CSV.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pid = (row.get("prompt_id") or "").strip()
            if pid:
                rows[pid] = row
    return rows


def main() -> int:
    prompts = _load_prompt_rows()
    refreshed = 0
    skipped = 0
    failures: list[tuple[str, str]] = []
    counts = {"baseline_solution_added": 0, "diff_added": 0}

    with _GEN_JSONL.open("r", encoding="utf-8") as src, _OUT_JSONL.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            line = line.rstrip("\n")
            if not line:
                continue
            rec = json.loads(line)
            pid = (rec.get("prompt_id") or "").strip()
            row = prompts.get(pid)
            if row is None:
                skipped += 1
                dst.write(line + "\n")
                continue
            try:
                payload = build_payload(
                    row["dataset"],
                    row["instance_id"],
                    row["perturbation_id"],
                    row["action_taken"],
                    row["family"],
                )
            except Exception as exc:  # noqa: BLE001
                failures.append((pid, f"{type(exc).__name__}: {exc}"))
                dst.write(line + "\n")
                continue
            if "baseline_solution" in payload:
                counts["baseline_solution_added"] += 1
            if "diff" in payload:
                counts["diff_added"] += 1
            rec["payload_snapshot"] = payload
            dst.write(json.dumps(rec) + "\n")
            refreshed += 1

    print(f"refreshed: {refreshed}")
    print(f"skipped:   {skipped}")
    print(f"failures:  {len(failures)}")
    for pid, err in failures:
        print(f"  {pid}: {err}")
    print(f"counts:    {counts}")
    print(f"output:    {_OUT_JSONL}")
    print()
    print("Inspect with:")
    print(f"  diff <(wc -l {_GEN_JSONL}) <(wc -l {_OUT_JSONL})")
    print("Move into place with:")
    print(f"  mv {_OUT_JSONL} {_GEN_JSONL}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

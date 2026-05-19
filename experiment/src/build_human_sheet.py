"""Build the human-rating sheet for the calibration pilot.

Reads the joined CSV and generator jsonl for a given run_id and writes:
  experiment/pilot/<sheet_stem>.csv  -- machine-readable (for kappa)
  experiment/pilot/<sheet_stem>.md   -- human-readable, payload pretty-printed

The two files are byte-equivalent in content modulo formatting:
- payload_snapshot is the full payload dict (JSON, NOT paraphrased or
  truncated); CSV stringifies it on a single line, the .md
  pretty-prints inside a fenced ```json block.
- Human columns are empty placeholders for the candidate to fill.

Usage:
  python experiment/src/build_human_sheet.py \
    --run-id calibration-pilot-v1 \
    --sheet-stem calibration_human_sheet
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

HUMAN_COLUMNS = [
    "human_faithfulness_score",
    "human_op_validity_pass",
    "human_rationale",
    "human_refusal_assessment",
    "human_notes",
]

SHEET_COLUMNS = [
    "prompt_id",
    "family",
    "source",
    "quadrant",
    "sufficiency_label",
    "policy_decision",
    "action_taken",
    "op_validity_gradable",
    "manual_review_required",
    "prompt_text",
    "payload_snapshot",
    "generator_answer_text",
    "generator_structured_fields",
    "judge_faithfulness_score",
    "judge_op_validity_pass",
    "judge_op_validity_check_results",
    "judge_rationale",
    "judge_refusal_detected",
    *HUMAN_COLUMNS,
]


def load_generator_records(run_id: str) -> dict[str, dict]:
    path = REPO / "experiment" / "results" / "generator" / f"{run_id}.jsonl"
    by_id: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        by_id[r["prompt_id"]] = r
    return by_id


def load_joined_rows(run_id: str) -> list[dict]:
    path = REPO / "experiment" / "results" / "joined" / f"{run_id}.csv"
    with path.open() as fh:
        return list(csv.DictReader(fh))


def _to_jsonish(value: str):
    """Best-effort JSON-decode of a string from the joined CSV cell."""
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def build_row(joined_row: dict, gen_record: dict) -> dict[str, str]:
    payload = gen_record.get("payload_snapshot") or {}
    structured_fields = {
        k: _to_jsonish(joined_row.get(k))
        for k in (
            "claimed_objective",
            "claimed_feasible",
            "claimed_route_count",
            "claimed_route_membership",
            "claimed_late_customers",
            "claimed_customer_timings",
        )
    }
    row = {
        "prompt_id": joined_row["prompt_id"],
        "family": joined_row["family"],
        "source": joined_row["source"],
        "quadrant": joined_row["quadrant"],
        "sufficiency_label": joined_row["sufficiency_label"],
        "policy_decision": joined_row["policy_decision"],
        "action_taken": joined_row["action_taken"],
        "op_validity_gradable": joined_row["op_validity_gradable"],
        "manual_review_required": joined_row["manual_review_required"],
        "prompt_text": joined_row["prompt_text"],
        "payload_snapshot": json.dumps(payload, ensure_ascii=False),
        "generator_answer_text": joined_row["answer_text"],
        "generator_structured_fields": json.dumps(structured_fields, ensure_ascii=False),
        "judge_faithfulness_score": joined_row["faithfulness_score"],
        "judge_op_validity_pass": joined_row["judge_op_validity_pass"],
        "judge_op_validity_check_results": joined_row["judge_op_validity_check_results"],
        "judge_rationale": joined_row["faithfulness_rationale"],
        "judge_refusal_detected": joined_row["judge_refusal_detected"],
    }
    for c in HUMAN_COLUMNS:
        row[c] = ""
    return row


def write_csv(rows: list[dict], out_path: Path) -> None:
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _fmt_md_value(v):
    if v is None or v == "":
        return "_(empty)_"
    return f"`{v}`"


def write_md(rows: list[dict], out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Calibration human-rating sheet")
    lines.append("")
    lines.append(
        "Pre-registration pilot. Per-prompt rendering of the calibration "
        "set with the *exact* payload the generator received. Fill the "
        "`human_*` fields per the rubric (experiment/configs/rubric.md). "
        "Do not look at `judge_*` values before scoring."
    )
    lines.append("")
    lines.append(f"Prompts: {len(rows)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    for r in rows:
        payload = json.loads(r["payload_snapshot"]) if r["payload_snapshot"] else {}
        structured_fields = (
            json.loads(r["generator_structured_fields"])
            if r["generator_structured_fields"]
            else {}
        )
        op_check = r["judge_op_validity_check_results"]
        try:
            op_check_parsed = json.loads(op_check) if op_check else None
        except json.JSONDecodeError:
            op_check_parsed = op_check
        lines.append(f"## Prompt {r['prompt_id']}")
        lines.append("")
        lines.append(
            f"- **family**: `{r['family']}` · **source**: `{r['source']}` · "
            f"**quadrant**: `{r['quadrant']}` · "
            f"**dataset**: from prompts.csv (see joined CSV)"
        )
        lines.append(
            f"- **sufficiency**: `{r['sufficiency_label']}` · "
            f"**policy_decision**: `{r['policy_decision']}` · "
            f"**action_taken**: `{r['action_taken']}`"
        )
        lines.append(
            f"- **op_validity_gradable**: `{r['op_validity_gradable']}` · "
            f"**manual_review_required**: `{r['manual_review_required']}`"
        )
        lines.append("")
        lines.append("### Prompt text")
        lines.append("")
        lines.append("> " + r["prompt_text"].replace("\n", "\n> "))
        lines.append("")
        lines.append("### Payload (what the generator saw)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
        lines.append("### Generator answer")
        lines.append("")
        lines.append("> " + (r["generator_answer_text"] or "").replace("\n", "\n> "))
        lines.append("")
        lines.append("**Generator structured claims**:")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(structured_fields, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
        lines.append("### Judge verdict")
        lines.append("")
        lines.append(f"- **faithfulness_score**: `{r['judge_faithfulness_score']}`")
        lines.append(
            f"- **op_validity_pass**: `{r['judge_op_validity_pass']}` "
            f"(check_results: `{op_check_parsed}`)"
        )
        lines.append(f"- **refusal_detected**: `{r['judge_refusal_detected']}`")
        lines.append("")
        lines.append("**Rationale**:")
        lines.append("")
        lines.append("> " + (r["judge_rationale"] or "").replace("\n", "\n> "))
        lines.append("")
        any_filled = any(r.get(c) for c in HUMAN_COLUMNS)
        header = "### Human rating" if any_filled else "### Human rating (fill these)"
        lines.append(header)
        lines.append("")
        for c in HUMAN_COLUMNS:
            v = r.get(c) or ""
            lines.append(f"- `{c}`: {v}")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sheet-stem", default="calibration_human_sheet")
    ap.add_argument(
        "--from-filled-csv",
        default=None,
        help=(
            "Optional path to a previously-filled human sheet. "
            "If set, the script merges human_* columns from this file "
            "into the generated rows, so the .md reflects filled state."
        ),
    )
    args = ap.parse_args()

    run_id = args.run_id
    joined_rows = load_joined_rows(run_id)
    gen_records = load_generator_records(run_id)

    missing = [r["prompt_id"] for r in joined_rows if r["prompt_id"] not in gen_records]
    if missing:
        print(f"ERROR: generator records missing for {missing}", file=sys.stderr)
        return 1

    rows = [build_row(jr, gen_records[jr["prompt_id"]]) for jr in joined_rows]

    if args.from_filled_csv:
        filled_by_id = {
            r["prompt_id"]: r
            for r in csv.DictReader(open(args.from_filled_csv))
        }
        for r in rows:
            f = filled_by_id.get(r["prompt_id"])
            if f is None:
                continue
            for c in HUMAN_COLUMNS:
                r[c] = f.get(c, "")
    out_csv = REPO / "experiment" / "pilot" / f"{args.sheet_stem}.csv"
    out_md = REPO / "experiment" / "pilot" / f"{args.sheet_stem}.md"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_csv)
    write_md(rows, out_md)
    print(f"Wrote {len(rows)} rows → {out_csv}")
    print(f"Wrote markdown rendering → {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

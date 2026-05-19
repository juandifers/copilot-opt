"""Verification analyzer — locked at preregistration-v1.

Reads the filled verification_human_sheet.csv and writes the two
locked output artifacts per experiment/configs/verification_protocol.md:

  experiment/results/verification_results.csv
      One row per prompt with prompt_id, family, source, quadrant,
      verification_pool, judge_faithfulness_score, human_faithfulness_score,
      abs_diff, judge_op_validity_pass, human_op_validity_pass,
      op_validity_agree, judge_refusal_detected, human_refusal_assessment.

  experiment/reports/verification_writeup.md
      Summary writeup. Includes:
      - n prompts rated
      - Agreement rate (|diff| ≤ 1 on faithfulness)
      - Per-prompt table
      - |diff| ≥ 2 prompts with rationales (locked: flagged but don't
        change headline scores)
      - Op-validity agreement among gradable+binary prompts
      - Refusal-handling agreement
      - Per-pool / per-family agreement breakdown (FP, FN, TP, TN)

The locked analysis remains judge-driven regardless of verification
outcome; this writeup is the methodology-section citable artifact.

Usage:
  python experiment/src/analyze_verification.py
  python experiment/src/analyze_verification.py \\
      --sheet experiment/results/verification_human_sheet.csv \\
      --results-out experiment/results/verification_results.csv \\
      --writeup-out experiment/reports/verification_writeup.md
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _parse_int(s):
    if s is None or s == "":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_bool(s):
    if s is None:
        return None
    s_l = str(s).strip().lower()
    if s_l in ("true", "t", "yes", "y", "1", "pass"):
        return True
    if s_l in ("false", "f", "no", "n", "0", "fail"):
        return False
    return None


def load_verification_set(path: Path) -> dict[str, dict]:
    return {r["prompt_id"]: r for r in csv.DictReader(path.open())}


def load_sheet(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open()))


def build_results_rows(
    sheet_rows: list[dict],
    verification_pools: dict[str, dict],
) -> list[dict]:
    out = []
    for r in sheet_rows:
        pid = r["prompt_id"]
        j = _parse_int(r["judge_faithfulness_score"])
        h = _parse_int(r["human_faithfulness_score"])
        abs_diff = abs(j - h) if (j is not None and h is not None) else ""
        op_j = _parse_bool(r["judge_op_validity_pass"])
        op_h = _parse_bool(r["human_op_validity_pass"])
        if op_j is None and op_h is None:
            op_agree = ""
        elif op_j is None or op_h is None:
            op_agree = "partial_null"
        else:
            op_agree = op_j == op_h
        refusal_j = _parse_bool(r["judge_refusal_detected"])
        refusal_h = _parse_bool(r["human_refusal_assessment"])
        if refusal_j is None and refusal_h is None:
            refusal_agree = ""
        elif refusal_j is None or refusal_h is None:
            refusal_agree = "partial_null"
        else:
            refusal_agree = refusal_j == refusal_h
        pool = (verification_pools.get(pid) or {}).get("verification_pool", "")
        out.append({
            "prompt_id": pid,
            "family": r["family"],
            "source": r["source"],
            "quadrant": r["quadrant"],
            "verification_pool": pool,
            "judge_faithfulness_score": j if j is not None else "",
            "human_faithfulness_score": h if h is not None else "",
            "abs_diff": abs_diff,
            "judge_op_validity_pass": op_j if op_j is not None else "",
            "human_op_validity_pass": op_h if op_h is not None else "",
            "op_validity_agree": op_agree,
            "judge_refusal_detected": refusal_j if refusal_j is not None else "",
            "human_refusal_assessment": refusal_h if refusal_h is not None else "",
            "refusal_agree": refusal_agree,
        })
    return out


def write_results_csv(rows: list[dict], path: Path) -> None:
    cols = list(rows[0].keys()) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def write_writeup(
    results_rows: list[dict],
    sheet_rows_by_id: dict[str, dict],
    out_path: Path,
) -> str:
    n = len(results_rows)
    valid_diffs = [
        r for r in results_rows
        if isinstance(r["abs_diff"], int)
        or (isinstance(r["abs_diff"], str) and r["abs_diff"].isdigit())
    ]
    diffs = [
        int(r["abs_diff"]) for r in results_rows
        if str(r["abs_diff"]).strip() != ""
    ]
    n_agree_within_1 = sum(1 for d in diffs if d <= 1)
    agree_rate_within_1 = (n_agree_within_1 / len(diffs)) if diffs else float("nan")

    exact_agree = sum(1 for d in diffs if d == 0)
    diff_dist = Counter(diffs)

    big_diff_prompts = [r for r in results_rows if str(r["abs_diff"]) == "2" or str(r["abs_diff"]).startswith("3") or str(r["abs_diff"]) == "4"]

    # Op-validity binary agreement (among non-null pairs)
    op_binary = [r for r in results_rows if r["op_validity_agree"] in (True, False)]
    op_agree = sum(1 for r in op_binary if r["op_validity_agree"] is True)
    op_agree_rate = (op_agree / len(op_binary)) if op_binary else float("nan")
    op_disagreements = [r for r in op_binary if r["op_validity_agree"] is False]

    # Refusal agreement (among non-null pairs)
    rf_binary = [r for r in results_rows if r["refusal_agree"] in (True, False)]
    rf_agree = sum(1 for r in rf_binary if r["refusal_agree"] is True)
    rf_agree_rate = (rf_agree / len(rf_binary)) if rf_binary else float("nan")

    # Per-axis
    def per_axis(axis_key: str) -> dict:
        out = {}
        for v in sorted({r[axis_key] for r in results_rows}):
            rows = [r for r in results_rows if r[axis_key] == v]
            d = [int(r["abs_diff"]) for r in rows if str(r["abs_diff"]) != ""]
            out[v] = {
                "n": len(rows),
                "n_within_1": sum(1 for x in d if x <= 1),
                "n_exact": sum(1 for x in d if x == 0),
                "mean_abs_diff": (sum(d) / len(d)) if d else float("nan"),
            }
        return out

    by_family = per_axis("family")
    by_pool = per_axis("verification_pool")
    by_quadrant = per_axis("quadrant")
    by_source = per_axis("source")

    lines: list[str] = []
    lines.append("# Verification writeup — full-run-v1")
    lines.append("")
    lines.append("Locked protocol: experiment/configs/verification_protocol.md")
    lines.append(
        "Pre-registered metric: % of prompts where candidate-judge "
        "|faithfulness diff| ≤ 1."
    )
    lines.append(
        "Locked decision: disagreements with |diff| ≥ 2 are flagged in "
        "the discussion section but do NOT alter the headline scores. "
        "The locked analysis remains judge-driven."
    )
    lines.append("")
    lines.append(f"- Prompts rated: {len(diffs)} / {n}")
    lines.append(
        f"- **Faithfulness agreement (|diff| ≤ 1): "
        f"{n_agree_within_1}/{len(diffs)} = {agree_rate_within_1:.2%}**"
    )
    lines.append(
        f"- Exact agreement (|diff| = 0): {exact_agree}/{len(diffs)} "
        f"= {(exact_agree/len(diffs) if diffs else float('nan')):.2%}"
    )
    lines.append(
        f"- |diff| distribution: "
        + ", ".join(f"{k}: {v}" for k, v in sorted(diff_dist.items()))
    )
    lines.append(
        f"- Op-validity binary agreement (gradable+binary): "
        f"{op_agree}/{len(op_binary)} = {op_agree_rate:.2%}"
    )
    lines.append(
        f"- Refusal-handling agreement (non-null pairs): "
        f"{rf_agree}/{len(rf_binary)} = {rf_agree_rate:.2%}"
    )
    lines.append("")
    lines.append("## Per-prompt table")
    lines.append("")
    lines.append("| prompt_id | family | source | pool | quadrant | judge | human | |diff| | op_j | op_h | op_agree | refusal_j | refusal_h |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results_rows:
        lines.append(
            f"| {r['prompt_id']} | {r['family']} | {r['source']} | "
            f"{r['verification_pool']} | {r['quadrant']} | "
            f"{r['judge_faithfulness_score']} | {r['human_faithfulness_score']} | "
            f"{r['abs_diff']} | "
            f"{r['judge_op_validity_pass']} | {r['human_op_validity_pass']} | "
            f"{r['op_validity_agree']} | "
            f"{r['judge_refusal_detected']} | {r['human_refusal_assessment']} |"
        )
    lines.append("")
    lines.append("## Faithfulness disagreements with |diff| ≥ 2 (flagged; non-headline-affecting)")
    lines.append("")
    if not big_diff_prompts:
        lines.append("_None._")
    else:
        for r in big_diff_prompts:
            pid = r["prompt_id"]
            sr = sheet_rows_by_id[pid]
            lines.append(
                f"### Prompt {pid} ({r['family']}/{r['source']}/{r['quadrant']}, "
                f"pool={r['verification_pool']}) — judge={r['judge_faithfulness_score']} "
                f"human={r['human_faithfulness_score']}"
            )
            lines.append("")
            lines.append("- **Judge rationale:**")
            lines.append(f"  > {(sr.get('judge_rationale') or '').strip()}")
            lines.append("- **Human rationale:**")
            lines.append(f"  > {(sr.get('human_rationale') or '').strip()}")
            if sr.get("human_notes"):
                lines.append(f"- **Human notes:** {sr['human_notes'].strip()}")
            lines.append("")
    lines.append("## Op-validity disagreements")
    lines.append("")
    if not op_disagreements:
        lines.append("_None._")
    else:
        for r in op_disagreements:
            pid = r["prompt_id"]
            sr = sheet_rows_by_id[pid]
            lines.append(
                f"- Prompt {pid} ({r['family']}): "
                f"judge={r['judge_op_validity_pass']} "
                f"human={r['human_op_validity_pass']}"
            )
            lines.append(f"  - Judge: {(sr.get('judge_op_validity_check_results') or '').strip()}")
            lines.append(f"  - Human notes: {(sr.get('human_notes') or '').strip()}")
    lines.append("")
    lines.append("## Per-axis breakdown")
    lines.append("")
    for axis_name, axis_table in [
        ("verification_pool (FP / FN / TP / TN)", by_pool),
        ("family", by_family),
        ("quadrant", by_quadrant),
        ("source", by_source),
    ]:
        lines.append(f"### By {axis_name}")
        lines.append("")
        lines.append("| value | n | n |diff|≤1 | n exact | mean |diff| |")
        lines.append("|---|---|---|---|---|")
        for k, info in axis_table.items():
            mean_str = (
                f"{info['mean_abs_diff']:.2f}"
                if info["mean_abs_diff"] == info["mean_abs_diff"]  # NaN check
                else "n/a"
            )
            lines.append(
                f"| {k} | {info['n']} | {info['n_within_1']} | "
                f"{info['n_exact']} | {mean_str} |"
            )
        lines.append("")
    lines.append(
        "_(Generated by `experiment/src/analyze_verification.py`. "
        "Locked analysis remains judge-driven; this writeup is a "
        "methodology-section citable artifact.)_"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return f"|diff|≤1 agreement {n_agree_within_1}/{len(diffs)} = {agree_rate_within_1:.2%}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sheet",
        default=str(REPO / "experiment" / "results" / "verification_human_sheet.csv"),
    )
    ap.add_argument(
        "--verification-set",
        default=str(REPO / "experiment" / "results" / "verification_set.csv"),
    )
    ap.add_argument(
        "--results-out",
        default=str(REPO / "experiment" / "results" / "verification_results.csv"),
    )
    ap.add_argument(
        "--writeup-out",
        default=str(REPO / "experiment" / "reports" / "verification_writeup.md"),
    )
    args = ap.parse_args()

    sheet_rows = load_sheet(Path(args.sheet))
    sheet_rows_by_id = {r["prompt_id"]: r for r in sheet_rows}
    verification_pools = load_verification_set(Path(args.verification_set))

    results_rows = build_results_rows(sheet_rows, verification_pools)
    write_results_csv(results_rows, Path(args.results_out))
    summary = write_writeup(results_rows, sheet_rows_by_id, Path(args.writeup_out))

    print(f"Wrote → {args.results_out}")
    print(f"Wrote → {args.writeup_out}")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

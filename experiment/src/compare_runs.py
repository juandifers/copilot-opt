"""Compare two joined experiment result CSVs for equivalence reporting.

Usage:
    python experiment/src/compare_runs.py <csv_a> <csv_b>

Computes per-prompt agreement on faithfulness, op_validity, claimed fields,
and model_version.  Disagreements are printed to stdout and reported with
counts.

Exit codes:
  0  all hard criteria agree
  1  usage error
  3  hard criteria disagree (op_validity or model_version mismatch)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path


FAITHFULNESS_TOLERANCE = 1


def _safe_float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _safe_bool(v: str | None) -> bool | None:
    if v is None or v == "" or v == "None":
        return None
    return str(v).lower() in ("true", "1")


def load_joined(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {p}")
    rows: dict[str, dict] = {}
    with p.open() as fh:
        for row in csv.DictReader(fh):
            rows[row["prompt_id"]] = row
    return rows


def compare(rows_a: dict[str, dict], rows_b: dict[str, dict],
            label_a: str = "A", label_b: str = "B") -> dict:
    all_ids = sorted(set(rows_a) | set(rows_b))
    per_prompt: list[dict] = []
    n_op_agree = 0
    n_faith_agree = 0
    n_faith_flagged = 0
    n_model_agree = 0
    disagreements: list[str] = []

    for pid in all_ids:
        a = rows_a.get(pid)
        b = rows_b.get(pid)
        if a is None or b is None:
            disagreements.append(
                f"prompt {pid}: present in only one CSV "
                f"({'A' if a else 'B'}={pid})"
            )
            continue

        faith_a = _safe_float(a.get("faithfulness_score"))
        faith_b = _safe_float(b.get("faithfulness_score"))
        op_a = _safe_bool(a.get("runner_op_validity_pass"))
        op_b = _safe_bool(b.get("runner_op_validity_pass"))
        model_a = a.get("generator_model_served", "")
        model_b = b.get("generator_model_served", "")

        op_match = (op_a == op_b)
        model_match = (model_a == model_b)

        faith_exact = (faith_a == faith_b)
        faith_within_tol = (
            faith_a is not None and faith_b is not None
            and abs(faith_a - faith_b) <= FAITHFULNESS_TOLERANCE
        )
        faith_flagged = faith_within_tol and not faith_exact

        if op_match:
            n_op_agree += 1
        else:
            disagreements.append(
                f"prompt {pid}: op_validity mismatch "
                f"{label_a}={op_a} {label_b}={op_b}"
            )

        if faith_within_tol:
            n_faith_agree += 1
        else:
            disagreements.append(
                f"prompt {pid}: faithfulness mismatch beyond ±1 "
                f"{label_a}={faith_a} {label_b}={faith_b}"
            )
        if faith_flagged:
            n_faith_flagged += 1

        if model_match:
            n_model_agree += 1
        else:
            disagreements.append(
                f"prompt {pid}: model_version mismatch "
                f"{label_a}={model_a!r} {label_b}={model_b!r}"
            )

        text_a = a.get("answer_text", "") or ""
        text_b = b.get("answer_text", "") or ""
        len_ratio = len(text_b) / max(len(text_a), 1)

        per_prompt.append({
            "prompt_id": pid,
            "op_validity_match": op_match,
            f"op_validity_{label_a}": op_a,
            f"op_validity_{label_b}": op_b,
            "faithfulness_exact": faith_exact,
            "faithfulness_within_tol": faith_within_tol,
            f"faithfulness_{label_a}": faith_a,
            f"faithfulness_{label_b}": faith_b,
            "model_version_match": model_match,
            f"model_version_{label_a}": model_a,
            f"model_version_{label_b}": model_b,
            "answer_text_len_ratio": round(len_ratio, 2),
        })

    n = len(all_ids)
    return {
        "label_a": label_a,
        "label_b": label_b,
        "n_prompts": n,
        "n_op_agree": n_op_agree,
        "n_faith_agree": n_faith_agree,
        "n_faith_flagged": n_faith_flagged,
        "n_model_agree": n_model_agree,
        "per_prompt": per_prompt,
        "disagreements": disagreements,
    }


def print_report(result: dict) -> None:
    la, lb = result["label_a"], result["label_b"]
    n = result["n_prompts"]
    print(f"\n=== Run comparison: {la} vs {lb} ({n} prompts) ===")
    print(f"  op_validity agreement:  {result['n_op_agree']}/{n}")
    print(
        f"  faithfulness agreement: {result['n_faith_agree']}/{n} "
        f"(exact: {result['n_faith_agree'] - result['n_faith_flagged']}, "
        f"±1: {result['n_faith_flagged']})"
    )
    print(f"  model_version agreement: {result['n_model_agree']}/{n}")

    if result["disagreements"]:
        print(f"\n  Disagreements ({len(result['disagreements'])}):")
        for d in result["disagreements"]:
            print(f"    - {d}")
    else:
        print("\n  No hard-criterion disagreements.")

    op_pass = result["n_op_agree"] == n
    faith_pass = result["n_faith_agree"] == n
    model_pass = result["n_model_agree"] == n
    overall = op_pass and faith_pass and model_pass
    verdict = "PASS" if overall else "FAIL"
    print(f"\n  Verdict: {verdict}")


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <csv_a> <csv_b>",
            file=sys.stderr,
        )
        return 1

    path_a, path_b = sys.argv[1], sys.argv[2]
    try:
        rows_a = load_joined(path_a)
        rows_b = load_joined(path_b)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    label_a = Path(path_a).stem
    label_b = Path(path_b).stem
    result = compare(rows_a, rows_b, label_a=label_a, label_b=label_b)
    print_report(result)

    n = result["n_prompts"]
    op_pass = result["n_op_agree"] == n
    faith_pass = result["n_faith_agree"] == n
    model_pass = result["n_model_agree"] == n
    return 0 if (op_pass and faith_pass and model_pass) else 3


if __name__ == "__main__":
    sys.exit(main())

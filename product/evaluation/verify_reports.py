"""Verify the canonical thesis evaluation reports.

This script reads the pre-computed report files in
product/evaluation/reports/ablation_v{1..4}*/ and prints the headline
numbers from each. It performs no computation beyond reading the files;
the canonical values are whatever the data files contain.

Run from the repository root:

    python -m product.evaluation.verify_reports
    python -m product.evaluation.verify_reports --per-category
    python -m product.evaluation.verify_reports --checksums

The script is intentionally read-only: it never writes to the report
directories. If the numbers it prints do not match the thesis tables,
either the data files have been modified (use --checksums to detect)
or the script's field-name mapping is wrong (check the JSON/CSV
schemas).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ABLATIONS = {
    "v1_full": "Full architecture",
    "v2_no_retry": "Retry disabled",
    "v3_no_alternatives": "Disambiguation disabled",
    "v4_llm_off": "LLM disabled (deterministic only)",
}

STRICT_USEFUL_BUCKETS = frozenset({"ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"})

REPORTS_DIR = Path(__file__).parent / "reports"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_rebucket_csv(config: str) -> list[dict]:
    path = REPORTS_DIR / f"ablation_{config}" / "operator_persona_strict_rebucket.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing canonical report: {path}")
    with path.open() as f:
        return list(csv.DictReader(f))


def _fmt_pct(n: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{n / total * 100:.1f}%"


def _print_headline(label: str, rows: list[dict]) -> None:
    total = len(rows)
    useful = sum(1 for r in rows if r["strict_bucket"] in STRICT_USEFUL_BUCKETS)
    off = [r for r in rows if r["phase"] == "off"]
    on = [r for r in rows if r["phase"] == "on"]
    off_useful = sum(1 for r in off if r["strict_bucket"] in STRICT_USEFUL_BUCKETS)
    on_useful = sum(1 for r in on if r["strict_bucket"] in STRICT_USEFUL_BUCKETS)

    print(f"\nOperator-persona — {label}")
    print(f"  combined strict-useful: {_fmt_pct(useful, total)}")
    print(f"  LLM-on strict-useful:   {_fmt_pct(on_useful, len(on))}")
    print(f"  LLM-off strict-useful:  {_fmt_pct(off_useful, len(off))}")


def _print_per_category(rows: list[dict]) -> None:
    categories = sorted(set(r["category"] for r in rows))
    print("  per-category strict-useful:")
    for cat in categories:
        cat_rows = [r for r in rows if r["category"] == cat]
        useful = sum(1 for r in cat_rows if r["strict_bucket"] in STRICT_USEFUL_BUCKETS)
        print(f"    {cat}: {_fmt_pct(useful, len(cat_rows))} (n={len(cat_rows)})")


def _file_hashes() -> list[tuple[str, str]]:
    paths = []
    for config in ABLATIONS:
        for filename in (
            "operator_persona_summary.json",
            "operator_persona_strict_rebucket.csv",
            "operator_persona_responses.jsonl",
        ):
            paths.append(REPORTS_DIR / f"ablation_{config}" / filename)
    paths.append(REPO_ROOT / "logs" / "variance_panel.jsonl")
    result = []
    for path in paths:
        if path.exists():
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path
            result.append((str(rel), h))
    return result


def _print_checksums() -> None:
    print("\nSHA-256 hashes of canonical report files:")
    for rel, h in _file_hashes():
        print(f"  {h}  {rel}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify canonical thesis evaluation reports (read-only)."
    )
    parser.add_argument(
        "--per-category",
        action="store_true",
        help="Also print per-cognitive-operation strict-useful for each ablation.",
    )
    parser.add_argument(
        "--checksums",
        action="store_true",
        help="Print SHA-256 hashes of canonical report files.",
    )
    args = parser.parse_args()

    for config, label in ABLATIONS.items():
        rows = _load_rebucket_csv(config)
        _print_headline(label, rows)
        if args.per_category:
            _print_per_category(rows)

    if args.checksums:
        _print_checksums()


if __name__ == "__main__":
    main()

"""Aggregate operator-persona results for the Phase A findings report.

Reads the runner's CSV and emits structured rollups that feed directly
into ``operator_persona_findings.md``:

- 10×6 category × bucket table (per phase)
- Per-category quick stats
- LLM-on/off delta table
- LLM-on intra-case variance (3 runs per case)
- Low-confidence rows (candidates for manual review)
- Representative failures per category

Run::

    python -m product.evaluation.operator_persona_analyze
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mode
from typing import Any


_REPORTS_DIR = Path(__file__).parent / "reports"
_RESULTS_CSV = _REPORTS_DIR / "operator_persona_results.csv"
_RESPONSES_JSONL = _REPORTS_DIR / "operator_persona_responses.jsonl"

CATEGORIES = [
    "orientation",
    "specific_diagnosis",
    "prioritized_diagnosis",
    "comparison",
    "evaluation",
    "risk_fragility",
    "justification",
    "counterfactual",
    "action_recommendation",
    "adversarial_edge",
]

BUCKETS = [
    "ANSWERED_USEFULLY",
    "ANSWERED_PARTIALLY",
    "REFUSED_LEGITIMATELY",
    "REFUSED_INCORRECTLY",
    "CLASSIFIED_WRONG",
    "ERROR",
]


def _load_rows() -> list[dict[str, Any]]:
    with _RESULTS_CSV.open() as fh:
        return list(csv.DictReader(fh))


def _bucket_table(rows: list[dict], phase: str) -> dict[str, dict[str, int]]:
    """Return ``{category: {bucket: count}}`` restricted to phase=='off' or 'on'."""
    out: dict[str, dict[str, int]] = {
        c: {b: 0 for b in BUCKETS} for c in CATEGORIES
    }
    for r in rows:
        if r["phase"] != phase:
            continue
        cat = r["category"]
        bkt = r["bucket"]
        if cat in out and bkt in out[cat]:
            out[cat][bkt] += 1
    return out


def _print_bucket_table(title: str, table: dict[str, dict[str, int]]) -> None:
    print(f"\n### {title}\n")
    header = ["category"] + BUCKETS + ["total"]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for cat in CATEGORIES:
        row = table[cat]
        total = sum(row.values())
        cells = [cat] + [str(row[b]) for b in BUCKETS] + [str(total)]
        print("| " + " | ".join(cells) + " |")
    # totals row
    col_totals = [sum(table[c][b] for c in CATEGORIES) for b in BUCKETS]
    grand = sum(col_totals)
    print("| **total** | " + " | ".join(f"**{x}**" for x in col_totals) +
          f" | **{grand}** |")


def _percent_bucket_table(table: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for cat, row in table.items():
        total = sum(row.values()) or 1
        out[cat] = {b: row[b] / total * 100.0 for b in BUCKETS}
    return out


def _on_off_deltas(rows: list[dict]) -> list[tuple[str, str, str, str]]:
    """For each (case_id, family), compare modal LLM-on bucket vs LLM-off bucket.

    Returns rows where they differ: (case_id, family, off_bucket, on_modal_bucket).
    """
    off_map: dict[tuple[str, str], str] = {}
    on_runs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        key = (r["case_id"], r["family"])
        if r["phase"] == "off":
            off_map[key] = r["bucket"]
        else:
            on_runs[key].append(r["bucket"])
    deltas = []
    for key, off_bkt in off_map.items():
        on_buckets = on_runs.get(key, [])
        if not on_buckets:
            continue
        try:
            modal_on = mode(on_buckets)
        except Exception:
            modal_on = Counter(on_buckets).most_common(1)[0][0]
        if modal_on != off_bkt:
            deltas.append((key[0], key[1], off_bkt, modal_on))
    return deltas


def _llm_on_variance(rows: list[dict]) -> dict[tuple[str, str], dict[str, Any]]:
    """For each (case_id, family) measure intra-LLM-on classification variance."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["phase"] != "on":
            continue
        by_key[(r["case_id"], r["family"])].append(r)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, runs in by_key.items():
        intents = [r["intent"] for r in runs]
        buckets = [r["bucket"] for r in runs]
        validations = [r["validation_outcome"] for r in runs]
        out[key] = {
            "n": len(runs),
            "intents": Counter(intents),
            "buckets": Counter(buckets),
            "validations": Counter(validations),
            "stable_intent": len(set(intents)) == 1,
            "stable_bucket": len(set(buckets)) == 1,
        }
    return out


def _low_confidence_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["bucket_confidence"] in ("low", "medium")]


def _representative_failures(rows: list[dict], phase: str, limit_per_cat: int = 3) -> dict[str, list[dict]]:
    """Pick up to ``limit_per_cat`` failure rows per category."""
    failing_buckets = {"REFUSED_INCORRECTLY", "CLASSIFIED_WRONG", "ERROR"}
    out: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for r in rows:
        if r["phase"] != phase:
            continue
        if r["bucket"] not in failing_buckets:
            continue
        cat = r["category"]
        if cat in out and len(out[cat]) < limit_per_cat:
            out[cat].append(r)
    return out


def main() -> int:
    rows = _load_rows()
    print(f"loaded {len(rows)} rows from {_RESULTS_CSV}")
    print(f"phase off: {sum(1 for r in rows if r['phase'] == 'off')}")
    print(f"phase on:  {sum(1 for r in rows if r['phase'] == 'on')}")

    off_table = _bucket_table(rows, "off")
    on_table = _bucket_table(rows, "on")
    _print_bucket_table("LLM-off bucket distribution", off_table)
    _print_bucket_table("LLM-on bucket distribution (all runs)", on_table)

    # On/off deltas
    deltas = _on_off_deltas(rows)
    print(f"\n### LLM-on vs LLM-off bucket changes: {len(deltas)} (case_id, family) pairs differ\n")
    helps = sum(1 for d in deltas if d[2] in {"REFUSED_INCORRECTLY", "CLASSIFIED_WRONG"} and d[3] in {"ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"})
    hurts = sum(1 for d in deltas if d[2] in {"ANSWERED_USEFULLY", "ANSWERED_PARTIALLY"} and d[3] in {"REFUSED_INCORRECTLY", "CLASSIFIED_WRONG", "ERROR"})
    print(f"  LLM helps (refused/wrong → answered): {helps}")
    print(f"  LLM hurts (answered → refused/wrong): {hurts}")
    print("  delta sample (first 15):")
    for cid, fam, off, on in deltas[:15]:
        print(f"    {cid:8s} {fam:9s} off={off:22s} on={on:22s}")

    # Variance
    variance = _llm_on_variance(rows)
    unstable_intent = [k for k, v in variance.items() if not v["stable_intent"]]
    unstable_bucket = [k for k, v in variance.items() if not v["stable_bucket"]]
    print(f"\n### LLM-on intra-case variance\n")
    print(f"  cases with intent variance:  {len(unstable_intent)} / {len(variance)}")
    print(f"  cases with bucket variance:  {len(unstable_bucket)} / {len(variance)}")
    print(f"  intent-unstable sample (first 10):")
    for k in unstable_intent[:10]:
        v = variance[k]
        intents_str = ", ".join(f"{i}×{n}" for i, n in v["intents"].most_common())
        print(f"    {k[0]:8s} {k[1]:9s}  intents=[{intents_str}]")

    # Low-confidence
    low_conf = _low_confidence_rows(rows)
    print(f"\n### Low/medium-confidence rows (manual review candidates): {len(low_conf)}\n")
    print("  by confidence level:")
    cnt = Counter(r["bucket_confidence"] for r in low_conf)
    for c, n in cnt.most_common():
        print(f"    {c:8s} {n}")

    # Save aggregated tables to JSON for the findings report
    summary = {
        "n_rows": len(rows),
        "n_off": sum(1 for r in rows if r["phase"] == "off"),
        "n_on": sum(1 for r in rows if r["phase"] == "on"),
        "off_table": off_table,
        "on_table": on_table,
        "off_percent": _percent_bucket_table(off_table),
        "on_percent": _percent_bucket_table(on_table),
        "deltas_count": len(deltas),
        "llm_helps": helps,
        "llm_hurts": hurts,
        "variance_unstable_intent": len(unstable_intent),
        "variance_unstable_bucket": len(unstable_bucket),
        "variance_total": len(variance),
        "low_confidence_count": len(low_conf),
    }
    out_path = _REPORTS_DIR / "operator_persona_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nwrote summary → {out_path}")

    # Representative failures per category (off phase)
    fails = _representative_failures(rows, "off", limit_per_cat=3)
    failures_path = _REPORTS_DIR / "operator_persona_representative_failures.json"
    failures_path.write_text(json.dumps(
        {cat: [{k: v for k, v in r.items()} for r in items]
         for cat, items in fails.items()},
        indent=2, default=str
    ))
    print(f"wrote representative failures → {failures_path}")

    # Per-category quick stats: total queries, useful rate, refuse-incorrect rate
    print("\n### Per-category headline rates (LLM-off)\n")
    print("| category | n_calls | %answered | %refused_incorrect | %classified_wrong |")
    print("|---|---|---|---|---|")
    for cat in CATEGORIES:
        row = off_table[cat]
        total = sum(row.values()) or 1
        ans = (row["ANSWERED_USEFULLY"] + row["ANSWERED_PARTIALLY"]) / total * 100
        ri = row["REFUSED_INCORRECTLY"] / total * 100
        cw = row["CLASSIFIED_WRONG"] / total * 100
        print(f"| {cat} | {total} | {ans:.1f}% | {ri:.1f}% | {cw:.1f}% |")

    print("\n### Per-category headline rates (LLM-on, all runs)\n")
    print("| category | n_calls | %answered | %refused_incorrect | %classified_wrong |")
    print("|---|---|---|---|---|")
    for cat in CATEGORIES:
        row = on_table[cat]
        total = sum(row.values()) or 1
        ans = (row["ANSWERED_USEFULLY"] + row["ANSWERED_PARTIALLY"]) / total * 100
        ri = row["REFUSED_INCORRECTLY"] / total * 100
        cw = row["CLASSIFIED_WRONG"] / total * 100
        print(f"| {cat} | {total} | {ans:.1f}% | {ri:.1f}% | {cw:.1f}% |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

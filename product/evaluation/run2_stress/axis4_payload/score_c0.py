"""Score the C0 contract on all 24 axis4 stress cases.

Reads cases.csv + payloads/{cell_id}.json, runs the deterministic
contract via product.evaluation.run2_system_c.run_system_c_on_case,
scores via product.evaluation.run2_scoring.score_case, and writes:

  reports/c0_baseline.csv  — per-case scores + metadata
  reports/c0_baseline.md   — aggregated per-band / per-intent metrics
                              and the predicted-vs-observed delta table

No model calls.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from product.evaluation.run2_case_loader import Run2Case, _split_multi
from product.evaluation.run2_system_c import run_system_c_on_case
from product.evaluation.run2_scoring import score_case

CASES_CSV = HERE / "cases.csv"
PAYLOAD_DIR = HERE / "payloads"
REPORT_DIR = HERE / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def _load_cases() -> list[tuple[Run2Case, str, str]]:
    """Returns list of (Run2Case, split, cell_id)."""
    out: list[tuple[Run2Case, str, str]] = []
    with CASES_CSV.open() as fh:
        for row in csv.DictReader(fh):
            case = Run2Case(
                case_id=row["case_id"],
                source_prompt_id=row["source_prompt_id"],
                family=row["family"],
                prompt_text=row["prompt_text"],
                payload_condition=row["payload_condition"],
                payload_mutation_needed=row["payload_mutation_needed"],
                expected_intent=row["expected_intent"],
                expected_answerability=row["expected_answerability"],
                expected_evidence_paths=_split_multi(row["expected_evidence_paths"]),
                expected_missing_fields=_split_multi(row["expected_missing_fields"]),
                expected_warnings=_split_multi(row["expected_warnings"]),
                expected_next_actions=_split_multi(row["expected_next_actions"]),
                expected_behavior_class=row["expected_behavior_class"],
                implementation_status=row["implementation_status"],
                difficulty=row["difficulty"],
                label_rationale=row["label_rationale"],
                ambiguity_notes=row["ambiguity_notes"],
            )
            # Extract cell_id from payload_mutation_needed
            # e.g. ".../pyvrp10s/C2_2_1__OC_4.json"
            cell_id = row["payload_mutation_needed"].split("/pyvrp10s/")[1].split(".json")[0]
            out.append((case, row["split"], cell_id))
    return out


def _band_of(case: Run2Case) -> str:
    if "low band" in case.label_rationale:
        return "low"
    if "high band" in case.label_rationale:
        return "high"
    raise ValueError(case.case_id)


def _n_routes_of(case: Run2Case) -> int:
    # "n_routes=<int>)" inside label_rationale
    import re
    m = re.search(r"n_routes=(\d+)", case.label_rationale)
    if m is None:
        raise ValueError(case.case_id)
    return int(m.group(1))


def _sub_pattern_of(case: Run2Case) -> str:
    if "mid-list" in case.label_rationale:
        return "mid-list"
    if "multi-entity" in case.label_rationale:
        return "multi-entity"
    if "routes-by-position" in case.label_rationale:
        return "routes-by-position"
    raise ValueError(case.case_id)


def main() -> None:
    items = _load_cases()

    rows: list[dict] = []
    for case, split, cell_id in items:
        with (PAYLOAD_DIR / f"{cell_id}.json").open() as fh:
            payload = json.load(fh)
        pred = run_system_c_on_case(case=case, payload=payload, generator_record=None)
        s = score_case(case, pred)
        rows.append({
            "case_id": case.case_id,
            "cell_id": cell_id,
            "band": _band_of(case),
            "n_routes": _n_routes_of(case),
            "intent": case.expected_intent,
            "sub_pattern": _sub_pattern_of(case),
            "split": split,
            "expected_behavior_class": case.expected_behavior_class,
            "predicted_behavior_class": pred.predicted_behavior_class,
            "intent_correct": s.intent_correct,
            "answerability_correct": s.answerability_correct,
            "behavior_class_correct": s.behavior_class_correct,
            "evidence_precision": s.evidence_precision,
            "evidence_recall": s.evidence_recall,
            "warning_precision": s.warning_precision,
            "warning_recall": s.warning_recall,
            "missing_field_recall": s.missing_field_recall,
            "useful_refusal_correct": s.useful_refusal_correct,
            "predicted_intent": pred.predicted_intent,
            "predicted_answerability": pred.predicted_answerability,
            "predicted_evidence_paths": ";".join(pred.predicted_evidence_paths),
            "predicted_warnings": ";".join(pred.predicted_warnings),
        })

    # ---------- write per-case CSV ----------
    out_csv = REPORT_DIR / "c0_baseline.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---------- aggregate ----------
    def _mean(xs):
        xs = list(xs)
        return float(statistics.fmean(xs)) if xs else 1.0

    METRICS = (
        "intent_correct", "answerability_correct", "behavior_class_correct",
        "evidence_precision", "evidence_recall",
        "warning_precision", "warning_recall", "missing_field_recall",
    )

    def _aggregate(filtered: list[dict]) -> dict[str, float]:
        return {m: _mean(int(bool(r[m])) if isinstance(r[m], bool) else r[m]
                          for r in filtered) for m in METRICS}

    overall = _aggregate(rows)
    by_band = {b: _aggregate([r for r in rows if r["band"] == b])
               for b in ("low", "high")}
    by_intent = {i: _aggregate([r for r in rows if r["intent"] == i])
                 for i in ("customer_arrival", "route_end_time", "lateness_summary")}
    by_band_intent = {
        (b, i): _aggregate([r for r in rows if r["band"] == b and r["intent"] == i])
        for b in ("low", "high")
        for i in ("customer_arrival", "route_end_time", "lateness_summary")
    }
    by_split = {sp: _aggregate([r for r in rows if r["split"] == sp])
                for sp in ("dev", "heldout")}

    # ---------- markdown report ----------
    lines: list[str] = []
    lines.append("# R2-S axis4_payload — C0 baseline\n")
    lines.append(f"- HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` "
                 f"(tag `run2-contract-extended`)")
    lines.append(f"- Cases: {len(rows)} (low={sum(1 for r in rows if r['band']=='low')}, "
                 f"high={sum(1 for r in rows if r['band']=='high')})")
    lines.append(f"- Split: dev={sum(1 for r in rows if r['split']=='dev')}, "
                 f"heldout={sum(1 for r in rows if r['split']=='heldout')}\n")

    lines.append("## 1. Aggregate metrics\n")
    lines.append("| scope | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    def _fmt(d, n): return (f"| {{}} | {n} | "
                            f"{d['intent_correct']:.3f} | {d['answerability_correct']:.3f} | "
                            f"{d['behavior_class_correct']:.3f} | "
                            f"{d['evidence_precision']:.3f} | {d['evidence_recall']:.3f} | "
                            f"{d['warning_precision']:.3f} | {d['warning_recall']:.3f} | "
                            f"{d['missing_field_recall']:.3f} |")
    lines.append(_fmt(overall, len(rows)).format("overall"))
    for b in ("low", "high"):
        n = sum(1 for r in rows if r["band"] == b)
        lines.append(_fmt(by_band[b], n).format(f"band={b}"))
    for i in ("customer_arrival", "route_end_time", "lateness_summary"):
        n = sum(1 for r in rows if r["intent"] == i)
        lines.append(_fmt(by_intent[i], n).format(f"intent={i}"))
    for sp in ("dev", "heldout"):
        n = sum(1 for r in rows if r["split"] == sp)
        lines.append(_fmt(by_split[sp], n).format(f"split={sp}"))
    lines.append("")

    lines.append("## 2. Per (band × intent) breakdown\n")
    lines.append("| band | intent | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for b in ("low", "high"):
        for i in ("customer_arrival", "route_end_time", "lateness_summary"):
            n = sum(1 for r in rows if r["band"] == b and r["intent"] == i)
            d = by_band_intent[(b, i)]
            lines.append(
                f"| {b} | {i} | {n} | "
                f"{d['intent_correct']:.3f} | {d['answerability_correct']:.3f} | "
                f"{d['behavior_class_correct']:.3f} | "
                f"{d['evidence_precision']:.3f} | {d['evidence_recall']:.3f} | "
                f"{d['warning_precision']:.3f} | {d['warning_recall']:.3f} |"
            )
    lines.append("")

    # ---------- predicted-vs-observed (C0 only) ----------
    # Predicted C0 ranges per design.md
    PREDICTED_C0_LOW = {
        "intent_correct": (1.00, 1.00),
        "answerability_correct": (1.00, 1.00),
        "behavior_class_correct": (0.95, 1.00),
        "evidence_precision": (0.95, 1.00),
        "evidence_recall": (1.00, 1.00),
        "warning_precision": (1.00, 1.00),
        "warning_recall": (1.00, 1.00),
    }
    PREDICTED_C0_HIGH = PREDICTED_C0_LOW  # C0 predicted flat across bands
    lines.append("## 3. Predicted-vs-observed (C0 only)\n")
    lines.append("Predicted ranges are the C0 column of the design-doc prediction table; "
                 "delta is observed minus prediction-midpoint.\n")
    lines.append("| band | metric | predicted_range | observed | delta_vs_midpoint | in_range |")
    lines.append("|---|---|---|---:|---:|:-:|")
    for b, preds in (("low", PREDICTED_C0_LOW), ("high", PREDICTED_C0_HIGH)):
        d = by_band[b]
        for k, (lo, hi) in preds.items():
            obs = d[k]
            mid = (lo + hi) / 2
            in_range = "✓" if lo - 1e-9 <= obs <= hi + 1e-9 else "✗"
            lines.append(f"| {b} | {k} | {lo:.2f}–{hi:.2f} | {obs:.3f} | "
                         f"{obs - mid:+.3f} | {in_range} |")
    lines.append("")

    # ---------- per-case table sorted by route count ----------
    lines.append("## 4. Per-case scores (sorted by n_routes)\n")
    lines.append("| case_id | band | n_routes | intent | sub_pattern | split | ev_prec | ev_rec | warn_prec | warn_rec | beh_correct |")
    lines.append("|---|---|---:|---|---|---|---:|---:|---:|---:|:-:|")
    for r in sorted(rows, key=lambda r: (r["n_routes"], r["case_id"])):
        bc = "✓" if r["behavior_class_correct"] else "✗"
        lines.append(
            f"| {r['case_id']} | {r['band']} | {r['n_routes']} | {r['intent']} | "
            f"{r['sub_pattern']} | {r['split']} | "
            f"{r['evidence_precision']:.2f} | {r['evidence_recall']:.2f} | "
            f"{r['warning_precision']:.2f} | {r['warning_recall']:.2f} | {bc} |"
        )
    lines.append("")

    # ---------- sample-size feasibility ----------
    lines.append("## 5. Heldout sample-size feasibility\n")
    lines.append("| band | dev n | heldout n | heldout ≥ 3 |")
    lines.append("|---|---:|---:|:-:|")
    for b in ("low", "high"):
        d = sum(1 for r in rows if r["band"] == b and r["split"] == "dev")
        h = sum(1 for r in rows if r["band"] == b and r["split"] == "heldout")
        ok = "✓" if h >= 3 else "✗"
        lines.append(f"| {b} | {d} | {h} | {ok} |")
    lines.append("")

    out_md = REPORT_DIR / "c0_baseline.md"
    out_md.write_text("\n".join(lines))
    print(f"wrote {out_csv}")
    print(f"wrote {out_md}")
    print(f"overall: intent={overall['intent_correct']:.3f} ev_prec={overall['evidence_precision']:.3f} "
          f"ev_rec={overall['evidence_recall']:.3f} beh={overall['behavior_class_correct']:.3f}")


if __name__ == "__main__":
    main()

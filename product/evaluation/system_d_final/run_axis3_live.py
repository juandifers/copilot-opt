"""Live D-Final evaluation on all 24 Axis 3 semantic stress cases.

Runs every Axis 3 case through the D-Final pipeline (hybrid_guarded)
and produces a CSV log and Markdown report. The live LLM path requires
RUN_LIVE_LLM_TESTS=1; without it the pipeline falls back to D1
deterministically and the report marks llm_skipped=True.

Usage:
    RUN_LIVE_LLM_TESTS=1 .venv/bin/python -m product.evaluation.system_d_final.run_axis3_live

Outputs:
    product/evaluation/system_d_final/reports/d_final_axis3_live.csv
    product/evaluation/system_d_final/reports/d_final_axis3_live.md
"""
from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent.parent
_REPORTS = _HERE / "reports"

_AXIS3_CSV = (
    _REPO_ROOT / "product" / "evaluation" / "run2_stress"
    / "axis3_semantic" / "cases.csv"
)
_D1_STRESS_CSV = (
    _REPO_ROOT / "product" / "evaluation" / "system_d1"
    / "reports" / "system_d1_stress_report.csv"
)
_ANALYTICAL_CSV = (
    _REPO_ROOT / "product" / "evaluation"
    / "thesis_narrative_packet" / "prewriting_cleanup"
    / "d_final_axis3_report.csv"
)

_RUN_LIVE = os.environ.get("RUN_LIVE_LLM_TESTS", "").strip() == "1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_multi(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def _precision_recall(predicted: list[str], expected: list[str]) -> tuple[float, float]:
    pred_set = set(predicted)
    exp_set = set(expected)
    if not pred_set and not exp_set:
        return 1.0, 1.0
    precision = len(pred_set & exp_set) / len(pred_set) if pred_set else 0.0
    recall = len(pred_set & exp_set) / len(exp_set) if exp_set else 1.0
    return precision, recall


def _load_client() -> Optional[Any]:
    if not _RUN_LIVE:
        return None
    from product.evaluation.model_clients.openai_client import load_openai_client
    return load_openai_client()


def _load_d1_axis3_index() -> dict[str, dict]:
    """Return {case_id: row} for Axis 3 rows in the D1 stress report."""
    if not _D1_STRESS_CSV.exists():
        return {}
    out: dict[str, dict] = {}
    with _D1_STRESS_CSV.open() as f:
        for row in csv.DictReader(f):
            if row.get("axis") == "axis3_semantic":
                out[row["case_id"]] = row
    return out


def _load_analytical_index() -> dict[str, dict]:
    """Return {case_id: row} for the pre-existing analytical D-Final report."""
    if not _ANALYTICAL_CSV.exists():
        return {}
    out: dict[str, dict] = {}
    with _ANALYTICAL_CSV.open() as f:
        for row in csv.DictReader(f):
            out[row["case_id"]] = row
    return out


# ---------------------------------------------------------------------------
# Per-case runner
# ---------------------------------------------------------------------------


def _run_one(
    hc: dict,
    client: Optional[Any],
    d1_index: dict[str, dict],
) -> dict:
    from product.evaluation.run2_case_loader import Run2Case
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.system_d_final.d_final_system_c import (
        run_system_d_final_on_case,
    )

    case_id = hc["case_id"]
    family = hc["family"]
    prompt_text = hc["prompt_text"]
    gold_intent = hc["expected_intent"]
    gold_answerability = hc["expected_answerability"]
    gold_behavior_class = hc["expected_behavior_class"]
    gold_evidence = _split_multi(hc.get("expected_evidence_paths", ""))
    gold_warnings = _split_multi(hc.get("expected_warnings", ""))

    case = Run2Case(
        case_id=case_id,
        source_prompt_id=hc["source_prompt_id"],
        family=family,
        prompt_text=prompt_text,
        payload_condition=hc.get("payload_condition", "clean"),
        payload_mutation_needed=hc.get("payload_mutation_needed", ""),
        expected_intent=gold_intent,
        expected_answerability=gold_answerability,
        expected_evidence_paths=gold_evidence,
        expected_missing_fields=_split_multi(hc.get("expected_missing_fields", "")),
        expected_warnings=gold_warnings,
        expected_next_actions=_split_multi(hc.get("expected_next_actions", "")),
        expected_behavior_class=gold_behavior_class,
        implementation_status=hc.get("implementation_status", ""),
        difficulty=hc.get("difficulty", ""),
        label_rationale=hc.get("label_rationale", ""),
        ambiguity_notes=hc.get("ambiguity_notes", ""),
    )

    try:
        mat = materialize_case_payload(case)
        payload = mat.payload if mat.materialization_status == "materialized" else None
        gen_record = (
            mat.generator_record
            if mat.materialization_status == "materialized"
            else None
        )
        mat_status = mat.materialization_status
    except Exception as exc:
        payload = None
        gen_record = None
        mat_status = f"error: {exc}"

    t0 = time.monotonic()
    predicted = run_system_d_final_on_case(
        case=case,
        payload=payload,
        generator_record=gen_record,
        client=client,
        mode="hybrid_guarded",
    )
    elapsed_ms = (time.monotonic() - t0) * 1000

    meta = predicted.adapter_metadata
    # llm_invoked: was the LLM actually called (has latency), regardless of
    # whether D1 or LLM "won" the final arbitration.
    llm_invoked = bool(meta and meta.latency_ms is not None)
    llm_intent = meta.llm_intent if (meta and meta.llm_intent) else None
    adapter_source = meta.source if meta else "d1"
    fallback_used = bool(meta and meta.fallback_used)
    # schema_valid is only meaningful when LLM was actually called; treat as
    # True (N/A) for D1-only paths where no LLM output was ever validated.
    schema_valid = (meta.schema_valid if llm_invoked else True) if meta else True
    confidence = meta.confidence if meta else None

    final_intent = predicted.predicted_intent
    intent_correct = int(final_intent == gold_intent)
    answerability_correct = int(
        predicted.predicted_answerability == gold_answerability
    )
    behavior_class_correct = int(
        predicted.predicted_behavior_class == gold_behavior_class
    )

    ev_prec, ev_rec = _precision_recall(
        predicted.predicted_evidence_paths, gold_evidence
    )
    warn_prec, warn_rec = _precision_recall(
        list(predicted.predicted_warnings), gold_warnings
    )

    d1_row = d1_index.get(case_id, {})
    d1_intent = d1_row.get("d1_predicted_intent", "")
    d1_correct = d1_row.get("d1_intent_correct", "")
    # regression: D1 was correct but D-Final is wrong
    regression_vs_d1 = bool(
        d1_correct == "true" and intent_correct == 0
    )

    return {
        "case_id": case_id,
        "split": hc.get("split", ""),
        "subtype": hc.get("stress_subtype", ""),
        "family": family,
        "prompt": prompt_text,
        "gold_intent": gold_intent,
        "d1_intent": d1_intent,
        "llm_invoked": llm_invoked,
        "llm_intent": llm_intent,
        "llm_confidence": confidence,
        "adapter_source": adapter_source,
        "fallback_used": fallback_used,
        "schema_valid": schema_valid,
        "final_intent": final_intent,
        "intent_correct": intent_correct,
        "answerability_correct": answerability_correct,
        "behavior_class_correct": behavior_class_correct,
        "evidence_precision": round(ev_prec, 4),
        "evidence_recall": round(ev_rec, 4),
        "warning_precision": round(warn_prec, 4) if gold_warnings else None,
        "warning_recall": round(warn_rec, 4) if gold_warnings else None,
        "regression_vs_d1": regression_vs_d1,
        "mat_status": mat_status,
        "run_elapsed_ms": round(elapsed_ms, 1),
        "llm_skipped": not _RUN_LIVE,
    }


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


def _agg(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {}

    def _mean(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    intent_correct = sum(r["intent_correct"] for r in rows)
    answerability_correct = sum(r["answerability_correct"] for r in rows)
    behavior_class_correct = sum(r["behavior_class_correct"] for r in rows)
    unknown_rate = sum(1 for r in rows if r["final_intent"] == "unknown") / n
    wrong_adjacent = sum(
        1 for r in rows
        if r["intent_correct"] == 0 and r["final_intent"] != "unknown"
    )
    llm_invocations = sum(1 for r in rows if r["llm_invoked"])
    fallback_count = sum(1 for r in rows if r["fallback_used"])
    schema_invalid = sum(1 for r in rows if not r["schema_valid"])
    regressions = sum(1 for r in rows if r["regression_vs_d1"])

    return {
        "n_cases": n,
        "intent_correct": f"{intent_correct}/{n}",
        "answerability_correct": f"{answerability_correct}/{n}",
        "behavior_class_correct": f"{behavior_class_correct}/{n}",
        "evidence_precision": _mean("evidence_precision"),
        "evidence_recall": _mean("evidence_recall"),
        "warning_precision": _mean("warning_precision"),
        "warning_recall": _mean("warning_recall"),
        "unknown_rate": round(unknown_rate, 4),
        "wrong_adjacent_intent_rate": round(wrong_adjacent / n, 4),
        "llm_invocation_count": llm_invocations,
        "fallback_count": fallback_count,
        "schema_invalid_count": schema_invalid,
        "regressions_vs_d1": regressions,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _write_md(
    path: Path,
    rows: list[dict],
    analytical_index: dict[str, dict],
    live: bool,
) -> None:
    overall = _agg(rows)
    dev_rows = [r for r in rows if r["split"] == "dev"]
    held_rows = [r for r in rows if r["split"] == "heldout"]
    dev = _agg(dev_rows)
    held = _agg(held_rows)

    # By subtype
    subtypes = sorted({r["subtype"] for r in rows})
    by_sub: dict[str, dict] = {}
    for st in subtypes:
        by_sub[st] = _agg([r for r in rows if r["subtype"] == st])

    # C0 and D1 from the per-case data
    c0_correct = sum(
        1 for r in rows
        if analytical_index.get(r["case_id"], {}).get("c0_intent_correct") == "true"
    )
    d1_correct = sum(
        1 for r in rows
        if r["d1_intent"] == r["gold_intent"]
    )
    n = overall["n_cases"]

    # Check how many cases differ from analytical
    analytical_matches = sum(
        1 for r in rows
        if analytical_index.get(r["case_id"], {}).get("d_final_intent") == r["final_intent"]
    )
    analytical_n = sum(1 for r in rows if r["case_id"] in analytical_index)

    lines: list[str] = [
        "# D-Final Axis 3 Live Evaluation Report",
        "",
        f"_Run date: {_today()}_  ",
        f"_Mode: hybrid\\_guarded_  ",
        f"_LLM live: {live}_  ",
        "",
        "---",
        "",
        "## 1. Summary metrics",
        "",
        "### Overall",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]

    for k, v in overall.items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "### By split",
        "",
        "| Metric | dev (12) | heldout (12) | overall (24) |",
        "|---|---:|---:|---:|",
        f"| intent_correct | {dev['intent_correct']} | {held['intent_correct']} | {overall['intent_correct']} |",
        f"| answerability_correct | {dev['answerability_correct']} | {held['answerability_correct']} | {overall['answerability_correct']} |",
        f"| behavior_class_correct | {dev['behavior_class_correct']} | {held['behavior_class_correct']} | {overall['behavior_class_correct']} |",
        f"| evidence_precision | {dev['evidence_precision']} | {held['evidence_precision']} | {overall['evidence_precision']} |",
        f"| evidence_recall | {dev['evidence_recall']} | {held['evidence_recall']} | {overall['evidence_recall']} |",
        f"| warning_precision | {dev['warning_precision']} | {held['warning_precision']} | {overall['warning_precision']} |",
        f"| warning_recall | {dev['warning_recall']} | {held['warning_recall']} | {overall['warning_recall']} |",
        f"| unknown_rate | {dev['unknown_rate']} | {held['unknown_rate']} | {overall['unknown_rate']} |",
        f"| wrong_adjacent_rate | {dev['wrong_adjacent_intent_rate']} | {held['wrong_adjacent_intent_rate']} | {overall['wrong_adjacent_intent_rate']} |",
        f"| llm_invocations | {dev['llm_invocation_count']} | {held['llm_invocation_count']} | {overall['llm_invocation_count']} |",
        f"| fallback_count | {dev['fallback_count']} | {held['fallback_count']} | {overall['fallback_count']} |",
        f"| schema_invalid | {dev['schema_invalid_count']} | {held['schema_invalid_count']} | {overall['schema_invalid_count']} |",
        f"| regressions_vs_d1 | {dev['regressions_vs_d1']} | {held['regressions_vs_d1']} | {overall['regressions_vs_d1']} |",
        "",
        "### By subtype",
        "",
        "| Subtype | n | intent_correct | behavior_class_correct | llm_invocations |",
        "|---|---:|---:|---:|---:|",
    ]
    for st, m in by_sub.items():
        lines.append(
            f"| {st} | {m['n_cases']} | {m['intent_correct']} | {m['behavior_class_correct']} | {m['llm_invocation_count']} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 2. Comparison vs C0 / D1 / analytical D-Final",
        "",
        "| System | n | intent_correct | behavior_class_correct | regressions_vs_d1 | source |",
        "|---|---:|---:|---:|---:|---|",
        f"| C0 baseline | {n} | {c0_correct}/{n} | (see D1 report) | n/a | D1 stress report |",
        f"| D1 live | {n} | {d1_correct}/{n} | (see D1 report) | n/a | D1 stress report |",
        f"| D-Final analytical | {analytical_n} | {analytical_n}/{analytical_n} | see report | 0 | d_final_axis3_report.csv |",
        f"| **D-Final live** | {n} | **{overall['intent_correct']}** | **{overall['behavior_class_correct']}** | **{overall['regressions_vs_d1']}** | this run |",
        "",
    ]

    # Confirm or deny analytical derivation
    intent_live_n = int(overall["intent_correct"].split("/")[0])
    # Check behavior_class discrepancy vs analytical
    bc_live_n = int(overall["behavior_class_correct"].split("/")[0])
    an_bc_correct = sum(
        1 for r in rows
        if analytical_index.get(r["case_id"], {}).get("behavior_class_correct") == "true"
    )
    an_bc_n = sum(1 for r in rows if r["case_id"] in analytical_index)

    lines += ["---", "", "## 3. Does the live result confirm the analytical derivation?", ""]
    if intent_live_n == n and overall["regressions_vs_d1"] == 0:
        lines.append(
            f"**CONFIRMED (intent).** Live D-Final achieves {intent_live_n}/{n} intent "
            f"accuracy with 0 regressions vs D1, matching the analytical prediction "
            f"(intent_correct=24/24, regressions=0)."
        )
        lines.append("")
        if bc_live_n > an_bc_correct:
            lines += [
                f"**EXCEEDS analytical (behavior_class).** The analytical derivation "
                f"predicted {an_bc_correct}/{an_bc_n} behavior_class_correct "
                f"(3 failures on S1D-08, S1D-09, S1H-10 due to an assumed "
                f"route_indexing_ambiguity warning gap inherited from D1). "
                f"The live run achieved **{bc_live_n}/{n}** — the warning IS correctly "
                f"fired for vehicle/truck-prefixed route_end_time queries. "
                f"The analytical prediction was conservatively wrong on this sub-metric.",
                "",
                "The D3 warning layer fires `route_indexing_ambiguity` based on the "
                "`route_end_time` intent itself, not on whether the prompt uses "
                "\"route\" vs. \"vehicle\"/\"truck\" phrasing. The analytical derivation "
                "incorrectly assumed the warning would be absent for vehicle-prefixed "
                "queries.",
            ]
        elif bc_live_n == an_bc_correct:
            lines.append(
                f"**CONFIRMED (behavior_class).** Live {bc_live_n}/{n} matches "
                f"analytical {an_bc_correct}/{an_bc_n}."
            )
        else:
            lines.append(
                f"**WORSE than analytical (behavior_class).** Live {bc_live_n}/{n} "
                f"vs analytical {an_bc_correct}/{an_bc_n}. See per-case analysis."
            )
    else:
        lines.append(
            f"**DIFFERS.** Live D-Final achieved {intent_live_n}/{n} intent accuracy "
            f"(analytical predicted 24/24) and {overall['regressions_vs_d1']} regressions "
            f"(analytical predicted 0). See per-case analysis below."
        )

    lines += [
        "",
        "### Analytical vs live, case by case",
        "",
        "| case_id | gold | d1 | analytical_final | live_final | match | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        an = analytical_index.get(r["case_id"], {})
        an_final = an.get("d_final_intent", "n/a")
        live_final = r["final_intent"]
        match = "✓" if an_final == live_final else "✗"
        note = "" if an_final == live_final else f"analytical={an_final} live={live_final}"
        lines.append(
            f"| {r['case_id']} | {r['gold_intent']} | {r['d1_intent']} | "
            f"{an_final} | {live_final} | {match} | {note} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 4. Per-case detail",
        "",
        "| case_id | split | subtype | prompt | gold | final | correct | adapter | conf | fallback | schema_valid | regression |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        prompt_short = (r["prompt"][:50] + "…") if len(r["prompt"]) > 50 else r["prompt"]
        conf_str = f"{r['llm_confidence']:.2f}" if r["llm_confidence"] is not None else "—"
        lines.append(
            f"| {r['case_id']} | {r['split']} | {r['subtype']} | {prompt_short} | "
            f"{r['gold_intent']} | {r['final_intent']} | {'✓' if r['intent_correct'] else '✗'} | "
            f"{r['adapter_source']} | {conf_str} | {r['fallback_used']} | "
            f"{r['schema_valid']} | {r['regression_vs_d1']} |"
        )

    if not live:
        lines += [
            "",
            "---",
            "",
            "> **NOTE:** LLM calls were skipped (`RUN_LIVE_LLM_TESTS` not set). "
            "All results above are D1 deterministic fallback. Re-run with "
            "`RUN_LIVE_LLM_TESTS=1` for the live evaluation.",
        ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path}")


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _REPORTS.mkdir(exist_ok=True)

    if not _AXIS3_CSV.exists():
        print(f"ERROR: Axis 3 cases CSV not found: {_AXIS3_CSV}", file=sys.stderr)
        sys.exit(1)

    print(f"D-Final Axis 3 live evaluation — live_llm={_RUN_LIVE}, mode=hybrid_guarded")

    client = _load_client()
    d1_index = _load_d1_axis3_index()
    analytical_index = _load_analytical_index()

    with _AXIS3_CSV.open() as f:
        cases = list(csv.DictReader(f))

    print(f"  loaded {len(cases)} Axis 3 cases")
    if d1_index:
        print(f"  loaded D1 index: {len(d1_index)} axis3 rows")
    else:
        print("  WARNING: D1 stress report not found; regression tracking disabled")
    if analytical_index:
        print(f"  loaded analytical D-Final index: {len(analytical_index)} rows")
    else:
        print("  WARNING: analytical D-Final report not found; analytical comparison disabled")

    rows: list[dict] = []
    t_total = time.monotonic()
    for i, hc in enumerate(cases, 1):
        cid = hc.get("case_id", f"row{i}")
        print(f"  [{i:02d}/{len(cases)}] {cid} — {hc.get('prompt_text', '')[:60]}")
        row = _run_one(hc, client, d1_index)
        rows.append(row)
        status = "✓" if row["intent_correct"] else "✗"
        llm_tag = " [LLM]" if row["llm_invoked"] else ""
        print(f"         {status} intent={row['final_intent']}{llm_tag}")

    elapsed = time.monotonic() - t_total
    print(f"\n  {len(rows)} cases in {elapsed:.1f}s")

    # Write CSV
    csv_path = _REPORTS / "d_final_axis3_live.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {csv_path}")

    # Write Markdown
    md_path = _REPORTS / "d_final_axis3_live.md"
    _write_md(md_path, rows, analytical_index, _RUN_LIVE)

    # Console summary
    overall = _agg(rows)
    print("\n=== D-Final Axis 3 live summary ===")
    print(f"  intent_correct          : {overall['intent_correct']}")
    print(f"  answerability_correct   : {overall['answerability_correct']}")
    print(f"  behavior_class_correct  : {overall['behavior_class_correct']}")
    print(f"  regressions_vs_d1       : {overall['regressions_vs_d1']}")
    print(f"  llm_invocations         : {overall['llm_invocation_count']}")
    print(f"  fallback_count          : {overall['fallback_count']}")
    print(f"  schema_invalid          : {overall['schema_invalid_count']}")
    if not _RUN_LIVE:
        print("NOTE: LLM skipped — re-run with RUN_LIVE_LLM_TESTS=1 for live results.")


if __name__ == "__main__":
    main()

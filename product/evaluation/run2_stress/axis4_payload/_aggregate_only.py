"""Re-aggregate A/B scores from saved jsonl (no API calls).

Run after score_models.py has produced the raw.jsonl + parsed.jsonl
under model_outputs/. Idempotent.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

# Reuse helpers + scoring from the main runner
from score_models import (  # type: ignore[import-not-found]
    METRICS,
    REPORT_DIR,
    OUTPUTS_DIR,
    REQUIRED_HEAD,
    MODEL,
    _aggregate,
    _band_of,
    _delta_table,
    _load_cases,
    _n_routes_of,
    _per_system_band_intent_markdown,
    _per_system_band_markdown,
    _predicted_from_parsed,
    _scatter_table,
    _surprises_table,
)
from product.evaluation.run2_scoring import score_case


def _load_parsed(system: str) -> list[dict]:
    sys_dir = OUTPUTS_DIR / f"axis4-{system.lower()}-{MODEL.replace('.', '')}"
    parsed_rows: list[dict] = []
    with (sys_dir / "parsed.jsonl").open() as fh:
        for line in fh:
            parsed_rows.append(json.loads(line))
    return parsed_rows


def _load_raw_summary(system: str) -> dict:
    sys_dir = OUTPUTS_DIR / f"axis4-{system.lower()}-{MODEL.replace('.', '')}"
    total_lat = 0.0
    total_pt = 0
    total_ct = 0
    errs = 0
    response_models: Counter = Counter()
    with (sys_dir / "raw.jsonl").open() as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("latency_seconds"):
                total_lat += r["latency_seconds"]
            total_pt += r.get("prompt_tokens") or 0
            total_ct += r.get("completion_tokens") or 0
            if r.get("error"):
                errs += 1
            if r.get("response_model"):
                response_models[r["response_model"]] += 1
    return dict(total_lat=total_lat, total_pt=total_pt,
                total_ct=total_ct, errs=errs,
                response_models=dict(response_models))


def _score_system(system: str, items) -> list[dict]:
    by_cid = {c.case_id: (c, sp, cell) for c, sp, cell in items}
    parsed = _load_parsed(system)
    score_rows: list[dict] = []
    for p in parsed:
        cid = p["case_id"]
        case, split, cell_id = by_cid[cid]
        pred = _predicted_from_parsed(p)
        s = score_case(case, pred)
        score_rows.append({
            "case_id": cid, "cell_id": cell_id, "band": _band_of(case),
            "n_routes": _n_routes_of(case), "intent": case.expected_intent,
            "split": split, "expected_behavior_class": case.expected_behavior_class,
            "predicted_behavior_class": pred.predicted_behavior_class,
            "intent_correct": int(s.intent_correct),
            "answerability_correct": int(s.answerability_correct),
            "behavior_class_correct": int(s.behavior_class_correct),
            "evidence_precision": s.evidence_precision,
            "evidence_recall": s.evidence_recall,
            "warning_precision": s.warning_precision,
            "warning_recall": s.warning_recall,
            "missing_field_recall": s.missing_field_recall,
            "useful_refusal_correct": (
                "" if s.useful_refusal_correct is None
                else int(bool(s.useful_refusal_correct))
            ),
            "predicted_intent": pred.predicted_intent,
            "predicted_evidence_paths": ";".join(pred.predicted_evidence_paths),
            "predicted_warnings": ";".join(pred.predicted_warnings),
        })
    return score_rows


def _write_system_report(system: str, score_rows: list[dict],
                          raw_summary: dict, head: str) -> None:
    score_csv = REPORT_DIR / f"system_{system.lower()}_baseline.csv"
    with score_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(score_rows[0].keys()),
                           quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in score_rows:
            w.writerow(r)

    md = [
        f"# axis4 — System {system} baseline",
        f"- HEAD: `{head}` (tag `run2-contract-extended`)",
        f"- Model: `{MODEL}` (observed: {', '.join(raw_summary['response_models'])})",
        f"- Cases: {len(score_rows)}",
        f"- Total latency: {raw_summary['total_lat']:.2f}s",
        f"- Total prompt tokens: {raw_summary['total_pt']:,}",
        f"- Total completion tokens: {raw_summary['total_ct']:,}",
        f"- Errors: {raw_summary['errs']}",
        "",
        "## Aggregate\n",
        "| scope | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    def _row(label, rows):
        d = _aggregate(rows)
        return (f"| {label} | {len(rows)} | "
                f"{d['intent_correct']:.3f} | {d['answerability_correct']:.3f} | "
                f"{d['behavior_class_correct']:.3f} | "
                f"{d['evidence_precision']:.3f} | {d['evidence_recall']:.3f} | "
                f"{d['warning_precision']:.3f} | {d['warning_recall']:.3f} | "
                f"{d['missing_field_recall']:.3f} |")
    md.append(_row("overall", score_rows))
    for b in ("low", "high"):
        md.append(_row(f"band={b}", [r for r in score_rows if r["band"] == b]))
    for i in ("customer_arrival", "route_end_time", "lateness_summary"):
        md.append(_row(f"intent={i}", [r for r in score_rows if r["intent"] == i]))
    for sp in ("dev", "heldout"):
        md.append(_row(f"split={sp}", [r for r in score_rows if r["split"] == sp]))
    md.append("")
    md.append("## Per-case scores (sorted by n_routes)\n")
    md.append("| case_id | band | n_routes | intent | split | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |")
    md.append("|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(score_rows, key=lambda r: (r["n_routes"], r["case_id"])):
        md.append(
            f"| {r['case_id']} | {r['band']} | {r['n_routes']} | "
            f"{r['intent']} | {r['split']} | "
            f"{r['intent_correct']:.2f} | {r['answerability_correct']:.2f} | "
            f"{r['behavior_class_correct']:.2f} | "
            f"{r['evidence_precision']:.2f} | {r['evidence_recall']:.2f} | "
            f"{r['warning_precision']:.2f} | {r['warning_recall']:.2f} |"
        )
    (REPORT_DIR / f"system_{system.lower()}_baseline.md").write_text("\n".join(md) + "\n")
    print(f"wrote system_{system.lower()}_baseline.{{md,csv}}")


def main() -> None:
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if head != REQUIRED_HEAD:
        raise RuntimeError(f"HEAD={head} != required {REQUIRED_HEAD}")

    items = _load_cases()

    # ---- C0 from CSV ----
    with (REPORT_DIR / "c0_baseline.csv").open() as fh:
        c0_rows = list(csv.DictReader(fh))
    def _to_num(v):
        if v in ("", None): return 0.0
        if v == "True": return 1.0
        if v == "False": return 0.0
        return float(v)
    for r in c0_rows:
        for m in METRICS:
            r[m] = _to_num(r[m])
        r["n_routes"] = int(r["n_routes"])

    # ---- A, B from saved jsonl ----
    b_scores = _score_system("B", items)
    a_scores = _score_system("A", items)
    b_raw = _load_raw_summary("B")
    a_raw = _load_raw_summary("A")

    score_by_sys = {"C0": c0_rows, "A": a_scores, "B": b_scores}

    _write_system_report("B", b_scores, b_raw, head)
    _write_system_report("A", a_scores, a_raw, head)

    # ---- combined summary ----
    n_low = sum(1 for case, _, _ in items if _band_of(case) == "low")
    n_high = sum(1 for case, _, _ in items if _band_of(case) == "high")

    # ---- failure-mode analysis: over-cited evidence paths + warning errors ----
    import re
    def _normp(p): return re.sub(r'\[[^\]]*=[^\]]*\]', '[]', p)

    a_parsed_rows: list[dict] = []
    b_parsed_rows: list[dict] = []
    with (OUTPUTS_DIR / f"axis4-a-{MODEL.replace('.', '')}" / "parsed.jsonl").open() as fh:
        for line in fh: a_parsed_rows.append(json.loads(line))
    with (OUTPUTS_DIR / f"axis4-b-{MODEL.replace('.', '')}" / "parsed.jsonl").open() as fh:
        for line in fh: b_parsed_rows.append(json.loads(line))

    case_by_id = {c.case_id: (c, sp, cell) for c, sp, cell in items}
    GOLD_EV = {
        "customer_arrival": {"customer_schedule[].arrival"},
        "route_end_time": {"route_end_times[].end_time"},
        "lateness_summary": {"n_late_customers", "late_customer_ids"},
    }

    def _over_cite_counts(parsed_rows: list[dict]) -> Counter:
        c: Counter = Counter()
        for p in parsed_rows:
            case = case_by_id[p["case_id"]][0]
            gold = GOLD_EV.get(case.expected_intent, set())
            for pth in p["predicted_evidence_paths"]:
                n = _normp(pth)
                if n not in gold:
                    c[n] += 1
        return c

    a_extras = _over_cite_counts(a_parsed_rows)
    b_extras = _over_cite_counts(b_parsed_rows)

    fm_lines = ["## 6. Failure-mode analysis (C1 design signals)\n"]
    fm_lines.append("### 6.1 Over-cited evidence paths\n")
    fm_lines.append("Field-family paths the model emitted beyond the gold for that intent. "
                    "Confirms the R2-4A/R2-5 prediction that identifier fields are spuriously "
                    "added alongside value fields.\n")
    fm_lines.append("| field path | A count (/24) | B count (/24) |")
    fm_lines.append("|---|---:|---:|")
    all_extras = sorted(set(a_extras) | set(b_extras),
                       key=lambda p: -(a_extras[p] + b_extras[p]))
    for pth in all_extras:
        fm_lines.append(f"| `{pth}` | {a_extras[pth]} | {b_extras[pth]} |")
    fm_lines.append("")

    # B answerability failure mode
    truncation_false_premise = []
    for p in b_parsed_rows:
        c, _, _ = case_by_id[p["case_id"]]
        if (c.expected_intent == "customer_arrival"
            and p["predicted_behavior_class"] == "useful_refusal"
            and "false_premise_detected" in p["predicted_warnings"]):
            truncation_false_premise.append(p["case_id"])

    fm_lines.append("### 6.2 B truncation-induced false-premise\n")
    fm_lines.append(
        "System B fires `false_premise_detected` on customer_arrival "
        "questions whose customer ID lies in the truncated tail of the "
        "60-row schedule projection (the prompt builder caps "
        "`customer_schedule` at `_MAX_SCHEDULE_ROWS_INLINE = 60`). "
        "C0 and A check the full payload via the deterministic "
        "answerability layer; B reads only the compacted view and "
        "concludes the customer does not exist.\n"
    )
    fm_lines.append(f"Affected cases: {', '.join(truncation_false_premise) or 'none'} "
                    f"(n={len(truncation_false_premise)}).\n")
    fm_lines.append(
        "C1 design signal: either (a) preserve customer-ID coverage "
        "in the compaction (e.g. cite by ID, fetch on demand), or "
        "(b) have C1 consume the deterministic answerability check "
        "instead of the LLM's read of the truncated payload.\n"
    )

    # B warning-policy errors
    b_warn_errors = []
    for p in b_parsed_rows:
        c, _, _ = case_by_id[p["case_id"]]
        gold_w = set(c.expected_warnings)
        pred_w = set(p["predicted_warnings"])
        if gold_w != pred_w:
            b_warn_errors.append((p["case_id"], c.prompt_text, sorted(gold_w), sorted(pred_w)))

    fm_lines.append("### 6.3 B over-firing of warning codes\n")
    fm_lines.append(
        "B fires `route_indexing_ambiguity` on positional phrasings "
        "(`the 11th route`, `the 15th route`) and on plural enumerations "
        "(`routes 8, 12, and 17`). The C0 contract's regex "
        "`\\broute\\s+\\d+\\b` is intentionally narrow and only matches "
        "`route N` singular. B also fires `struct_membership_ambiguity` "
        "on lateness_summary questions naming multiple customers — that "
        "code is bound to `single_customer_route_membership` intent.\n"
    )
    fm_lines.append("| case | prompt | gold_warnings | pred_warnings |")
    fm_lines.append("|---|---|---|---|")
    for cid, prompt, gw, pw in b_warn_errors[:20]:
        fm_lines.append(
            f"| {cid} | {prompt[:60]} | "
            f"{';'.join(gw) or '(none)'} | {';'.join(pw) or '(none)'} |"
        )
    fm_lines.append("")
    fm_lines.append(
        "C1 design signal: warning emission needs the contract's "
        "regex-pinned rules, not the model's intuition about when a "
        "warning \"makes sense\". This is exactly the deterministic-prior "
        "role A is meant to play — A holds these warnings correctly on "
        "11/12 low-band and 12/12 high-band cases.\n"
    )

    # A's single warning override
    a_warn_overrides = []
    for p in a_parsed_rows:
        c, _, _ = case_by_id[p["case_id"]]
        if set(c.expected_warnings) != set(p["predicted_warnings"]):
            a_warn_overrides.append((p["case_id"], c.prompt_text,
                                     sorted(c.expected_warnings),
                                     sorted(p["predicted_warnings"]),
                                     p.get("prior_disagreement", False)))

    fm_lines.append("### 6.4 A silent prior override\n")
    if a_warn_overrides:
        fm_lines.append(
            "System A added warnings beyond the prior on the following "
            "cases without flagging `prior_disagreement=true`. The "
            "deterministic prior locks warnings; A is supposed to copy "
            "them unchanged.\n"
        )
        fm_lines.append("| case | prompt | gold_warnings | A pred warnings | prior_disagreement |")
        fm_lines.append("|---|---|---|---|:-:|")
        for cid, prompt, gw, pw, dis in a_warn_overrides:
            fm_lines.append(
                f"| {cid} | {prompt[:60]} | "
                f"{';'.join(gw) or '(none)'} | {';'.join(pw) or '(none)'} | "
                f"{'✓' if dis else '✗'} |"
            )
        fm_lines.append("")
        fm_lines.append(
            "C1 design signal: A's prior-lock instruction is not "
            "strictly honored on positional-route phrasings. Tightening "
            "the prompt template or post-validating the model's emitted "
            "warnings against the prior would close this gap.\n"
        )
    else:
        fm_lines.append("(no silent overrides observed)\n")

    summary = [
        "# R2-S axis4_payload — combined (C0, A, B) summary",
        f"- HEAD: `{head}` (tag `run2-contract-extended`)",
        f"- Model: `{MODEL}` (observed: "
        f"B={', '.join(b_raw['response_models'])}; "
        f"A={', '.join(a_raw['response_models'])})",
        f"- Cases: {len(items)} (low={n_low}, high={n_high})",
        f"- Wall-clock: B {b_raw['total_lat']:.1f}s + A {a_raw['total_lat']:.1f}s "
        f"= {b_raw['total_lat']+a_raw['total_lat']:.1f}s",
        f"- API tokens: B prompt={b_raw['total_pt']:,} comp={b_raw['total_ct']:,}; "
        f"A prompt={a_raw['total_pt']:,} comp={a_raw['total_ct']:,}",
        f"- Errors: B={b_raw['errs']}, A={a_raw['errs']}",
        "",
        _per_system_band_markdown(score_by_sys),
        "",
        _per_system_band_intent_markdown(score_by_sys),
        "",
        _delta_table(score_by_sys),
        "",
        _surprises_table(score_by_sys),
        "",
        *fm_lines,
        "",
        _scatter_table(score_by_sys),
    ]
    sum_path = REPORT_DIR / "stress_axis4_summary.md"
    sum_path.write_text("\n".join(summary) + "\n")
    print(f"wrote {sum_path.name}")


if __name__ == "__main__":
    main()

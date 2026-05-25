"""Score System A and System B on the 24 axis4 stress cases.

Drives the existing prompt builders + output adapter + scorer with
the axis4 cases.csv and pre-built payloads. Writes:

  reports/system_b_baseline.{md,csv}
  reports/system_a_baseline.{md,csv}
  reports/stress_axis4_summary.md

Model lock: gpt-5.4-mini (same as R2-4A). HEAD must equal 18b4811.

Idempotency: if any of the three model-output directories already
exists, the run halts. Delete them to re-run.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from product.evaluation.model_clients.openai_client import (
    OpenAIKeyMissingError,
    call_openai_contract_model,
    load_openai_client,
)
from product.evaluation.run2_case_loader import Run2Case, _split_multi
from product.evaluation.run2_model_output_adapter import (
    parse_model_contract_json,
    parsed_output_to_dict,
)
from product.evaluation.run2_model_prompts import (
    build_prompt_only_json_prompt,
    build_system_a_prior_prompt,
)
from product.evaluation.run2_scoring import score_case
from product.evaluation.run2_system_a_prior import build_system_a_prior
from product.evaluation.run2_system_c import PredictedContract

CASES_CSV = HERE / "cases.csv"
PAYLOAD_DIR = HERE / "payloads"
REPORT_DIR = HERE / "reports"
OUTPUTS_DIR = HERE / "model_outputs"
REQUIRED_HEAD = "18b4811a1f85c166ea3ba8c777dfc021b2a5f747"
MODEL = "gpt-5.4-mini"


# ---------------------------------------------------------------------------
# Case + payload loading
# ---------------------------------------------------------------------------


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
            cell_id = row["payload_mutation_needed"].split("/pyvrp10s/")[1].split(".json")[0]
            out.append((case, row["split"], cell_id))
    return out


def _load_payload(cell_id: str) -> dict:
    with (PAYLOAD_DIR / f"{cell_id}.json").open() as fh:
        return json.load(fh)


def _band_of(case: Run2Case) -> str:
    if "low band" in case.label_rationale:
        return "low"
    if "high band" in case.label_rationale:
        return "high"
    raise ValueError(case.case_id)


def _n_routes_of(case: Run2Case) -> int:
    import re
    m = re.search(r"n_routes=(\d+)", case.label_rationale)
    return int(m.group(1))


# ---------------------------------------------------------------------------
# One-case driver
# ---------------------------------------------------------------------------


def _hash_prompt(messages: list[dict]) -> str:
    encoded = json.dumps(messages, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _build_messages(system: str, case: Run2Case, payload: dict):
    if system == "B":
        return build_prompt_only_json_prompt(case, payload), None
    if system == "A":
        prior = build_system_a_prior(case, payload)
        return build_system_a_prior_prompt(case, payload, prior), prior
    raise ValueError(system)


def _run_one(client, system: str, case: Run2Case, payload: dict, model: str) -> tuple[dict, dict]:
    messages, prior = _build_messages(system, case, payload)
    prompt_hash = _hash_prompt(messages)
    call = call_openai_contract_model(
        client,
        model=model,
        messages=messages,
        temperature=0.0,
        max_output_tokens=2048,
        response_format_json_object=True,
        max_retries=2,
    )
    prior_summary = None
    if prior is not None:
        prior_summary = {k: prior.get(k) for k in (
            "intent_prior", "answerability_prior", "behavior_class_prior",
            "warnings_prior", "missing_fields_prior", "next_actions_prior",
        )}
    raw = {
        "case_id": case.case_id, "provider": "openai", "system": system,
        "requested_model": call.requested_model, "response_model": call.response_model,
        "materialization_status": "materialized", "materialization_warnings": [],
        "skipped": False, "skip_reason": "",
        "prompt_hash": prompt_hash, "raw_response_text": call.raw_response_text,
        "prompt_tokens": call.prompt_tokens, "completion_tokens": call.completion_tokens,
        "total_tokens": call.total_tokens, "latency_seconds": round(call.latency_seconds, 4),
        "retry_count": call.retry_count, "finish_reason": call.finish_reason,
        "error": call.error, "prior_summary": prior_summary,
    }
    if call.error or not call.raw_response_text:
        parsed_row = {
            "case_id": case.case_id, "parse_status": "error",
            "parser_notes": [call.error] if call.error else ["empty_response"],
            "predicted_intent": "", "predicted_answerability": "",
            "predicted_evidence_paths": [], "predicted_missing_fields": [],
            "predicted_warnings": [], "predicted_next_actions": [],
            "predicted_behavior_class": "", "answer_text": "",
            "prior_disagreement": False, "adapter_notes": "",
        }
    else:
        parsed = parse_model_contract_json(call.raw_response_text, case_id=case.case_id)
        parsed_row = parsed_output_to_dict(parsed)
    return raw, parsed_row


# ---------------------------------------------------------------------------
# Score from parsed row → CaseScore
# ---------------------------------------------------------------------------


def _predicted_from_parsed(parsed: dict) -> PredictedContract:
    return PredictedContract(
        case_id=parsed["case_id"],
        predicted_intent=parsed["predicted_intent"],
        predicted_answerability=parsed["predicted_answerability"],
        predicted_evidence_paths=list(parsed["predicted_evidence_paths"]),
        predicted_missing_fields=list(parsed["predicted_missing_fields"]),
        predicted_warnings=list(parsed["predicted_warnings"]),
        predicted_next_actions=list(parsed["predicted_next_actions"]),
        predicted_behavior_class=parsed["predicted_behavior_class"],
        notes=[],
    )


# ---------------------------------------------------------------------------
# Run + persist per-system
# ---------------------------------------------------------------------------


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _run_system(client, system: str, items: list[tuple[Run2Case, str, str]]) -> dict:
    """Returns dict with raw_rows, parsed_rows, score_rows, totals."""
    sys_dir = OUTPUTS_DIR / f"axis4-{system.lower()}-{MODEL.replace('.', '')}"
    if sys_dir.exists():
        raise RuntimeError(f"output dir already exists: {sys_dir} — delete to re-run")
    sys_dir.mkdir(parents=True)

    started = _utc()
    raw_rows: list[dict] = []
    parsed_rows: list[dict] = []
    score_rows: list[dict] = []
    parse_status_counts: Counter = Counter()
    response_models: Counter = Counter()
    total_lat = 0.0
    total_pt = 0
    total_ct = 0
    errs = 0

    for case, split, cell_id in items:
        payload = _load_payload(cell_id)
        raw, parsed = _run_one(client, system, case, payload, MODEL)
        raw_rows.append(raw)
        parsed_rows.append(parsed)
        parse_status_counts[parsed["parse_status"]] += 1
        response_models[raw["response_model"]] += 1
        if raw["latency_seconds"]:
            total_lat += raw["latency_seconds"]
        total_pt += raw["prompt_tokens"] or 0
        total_ct += raw["completion_tokens"] or 0
        if raw["error"]:
            errs += 1

        # Score
        pred = _predicted_from_parsed(parsed)
        s = score_case(case, pred)
        score_rows.append({
            "case_id": case.case_id, "cell_id": cell_id, "band": _band_of(case),
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

    finished = _utc()

    # ----- persist raw / parsed -----
    with (sys_dir / "raw.jsonl").open("w") as fh:
        for r in raw_rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with (sys_dir / "parsed.jsonl").open("w") as fh:
        for r in parsed_rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    # ----- run_log -----
    log = [
        f"# axis4 model baseline — {system}",
        f"- run_dir: {sys_dir.relative_to(REPO)}",
        f"- system: {system}",
        f"- requested_model: {MODEL}",
        f"- temperature: 0.0",
        f"- max_output_tokens: 2048",
        f"- cases_csv: {CASES_CSV.relative_to(REPO)}",
        f"- n_cases: {len(items)}",
        f"- started_utc: {started}",
        f"- finished_utc: {finished}",
        "",
        "## Counts",
        f"- attempted: {len(items)}",
        f"- errors (api/empty): {errs}",
        "",
        "### parse_status",
    ]
    for k in sorted(parse_status_counts):
        log.append(f"- {k}: {parse_status_counts[k]}")
    log.append("")
    log.append("### response_model strings observed")
    for k in sorted(response_models):
        log.append(f"- '{k}': {response_models[k]}")
    log.append("")
    log.append("## Aggregate latency / tokens")
    log.append(f"- total_latency_seconds: {round(total_lat, 2)}")
    log.append(f"- total_prompt_tokens: {total_pt}")
    log.append(f"- total_completion_tokens: {total_ct}")
    (sys_dir / "run_log.md").write_text("\n".join(log) + "\n")

    return dict(
        raw=raw_rows, parsed=parsed_rows, score=score_rows,
        total_lat=total_lat, total_pt=total_pt, total_ct=total_ct,
        errs=errs, started=started, finished=finished,
        response_models=dict(response_models),
    )


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


METRICS = (
    "intent_correct", "answerability_correct", "behavior_class_correct",
    "evidence_precision", "evidence_recall",
    "warning_precision", "warning_recall", "missing_field_recall",
)


def _mean(xs) -> float:
    xs = list(xs)
    return float(statistics.fmean(xs)) if xs else 1.0


def _aggregate(rows: list[dict]) -> dict[str, float]:
    return {m: _mean(float(r[m]) for r in rows) for m in METRICS}


def _per_system_band_markdown(score_rows_by_system: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    lines.append("## 1. Per-(system × band) metrics\n")
    lines.append("| system | band | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for system in ("C0", "A", "B"):
        rows = score_rows_by_system[system]
        for band in ("low", "high"):
            filt = [r for r in rows if r["band"] == band]
            d = _aggregate(filt)
            lines.append(
                f"| {system} | {band} | {len(filt)} | "
                f"{d['intent_correct']:.3f} | {d['answerability_correct']:.3f} | "
                f"{d['behavior_class_correct']:.3f} | "
                f"{d['evidence_precision']:.3f} | {d['evidence_recall']:.3f} | "
                f"{d['warning_precision']:.3f} | {d['warning_recall']:.3f} | "
                f"{d['missing_field_recall']:.3f} |"
            )
    return "\n".join(lines)


def _per_system_band_intent_markdown(score_rows_by_system: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    lines.append("## 2. Per-(system × band × intent) breakdown\n")
    lines.append("| system | band | intent | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for system in ("C0", "A", "B"):
        rows = score_rows_by_system[system]
        for band in ("low", "high"):
            for intent in ("customer_arrival", "route_end_time", "lateness_summary"):
                filt = [r for r in rows
                        if r["band"] == band and r["intent"] == intent]
                d = _aggregate(filt)
                lines.append(
                    f"| {system} | {band} | {intent} | {len(filt)} | "
                    f"{d['intent_correct']:.3f} | {d['answerability_correct']:.3f} | "
                    f"{d['behavior_class_correct']:.3f} | "
                    f"{d['evidence_precision']:.3f} | {d['evidence_recall']:.3f} | "
                    f"{d['warning_precision']:.3f} | {d['warning_recall']:.3f} |"
                )
    return "\n".join(lines)


PREDICTIONS = {
    ("low", "A"):  dict(intent_correct=(0.95,1.00), answerability_correct=(0.95,1.00),
                       behavior_class_correct=(0.90,0.95), evidence_precision=(0.75,0.85),
                       evidence_recall=(0.90,1.00), warning_precision=(0.95,1.00),
                       warning_recall=(0.95,1.00)),
    ("low", "B"):  dict(intent_correct=(0.90,0.95), answerability_correct=(0.95,1.00),
                       behavior_class_correct=(0.80,0.90), evidence_precision=(0.65,0.80),
                       evidence_recall=(0.85,0.95), warning_precision=(0.90,0.95),
                       warning_recall=(0.90,0.95)),
    ("high", "A"): dict(intent_correct=(0.90,0.95), answerability_correct=(0.95,1.00),
                       behavior_class_correct=(0.85,0.90), evidence_precision=(0.55,0.75),
                       evidence_recall=(0.85,0.95), warning_precision=(0.90,0.95),
                       warning_recall=(0.90,0.95)),
    ("high", "B"): dict(intent_correct=(0.85,0.95), answerability_correct=(0.90,1.00),
                       behavior_class_correct=(0.75,0.85), evidence_precision=(0.45,0.65),
                       evidence_recall=(0.80,0.90), warning_precision=(0.85,0.95),
                       warning_recall=(0.85,0.95)),
}


def _delta_table(score_rows_by_system: dict[str, list[dict]]) -> str:
    lines = []
    lines.append("## 3. Predicted-vs-observed delta (A, B)\n")
    lines.append("Predictions from `design.md` §6. `δ` is observed minus prediction-midpoint.\n")
    lines.append("| system | band | metric | predicted | observed | δ | in_range |")
    lines.append("|---|---|---|---|---:|---:|:-:|")
    for system in ("A", "B"):
        for band in ("low", "high"):
            preds = PREDICTIONS[(band, system)]
            rows = [r for r in score_rows_by_system[system] if r["band"] == band]
            d = _aggregate(rows)
            for k, (lo, hi) in preds.items():
                obs = d[k]
                mid = (lo + hi) / 2
                in_range = "✓" if lo - 1e-9 <= obs <= hi + 1e-9 else "✗"
                lines.append(f"| {system} | {band} | {k} | {lo:.2f}–{hi:.2f} | "
                             f"{obs:.3f} | {obs - mid:+.3f} | {in_range} |")
    return "\n".join(lines)


def _scatter_table(score_rows_by_system: dict[str, list[dict]]) -> str:
    lines = []
    lines.append("## 5. Per-case × per-system × per-metric scatter\n")
    lines.append("One row per (case_id, system, metric). "
                 "This is the data the cross-axis joint analysis will plot.\n")
    lines.append("| case_id | split | band | n_routes | intent | system | metric | score |")
    lines.append("|---|---|---|---:|---|---|---|---:|")
    metrics_to_emit = ("evidence_precision", "evidence_recall",
                       "intent_correct", "answerability_correct",
                       "behavior_class_correct", "warning_precision", "warning_recall")
    # Use C0's score_rows to drive the iteration order (it has split, band, n_routes).
    ref_rows = {r["case_id"]: r for r in score_rows_by_system["C0"]}
    for cid in sorted(ref_rows):
        ref = ref_rows[cid]
        for system in ("C0", "A", "B"):
            row = next(r for r in score_rows_by_system[system] if r["case_id"] == cid)
            for metric in metrics_to_emit:
                lines.append(
                    f"| {cid} | {ref['split']} | {ref['band']} | "
                    f"{ref['n_routes']} | {ref['intent']} | {system} | "
                    f"{metric} | {float(row[metric]):.3f} |"
                )
    return "\n".join(lines)


def _surprises_table(score_rows_by_system: dict[str, list[dict]]) -> str:
    """Cases where A or B failed in a metric class not predicted to fail."""
    lines = []
    lines.append("## 4. Case-level surprises (A / B failures not anticipated by prediction)\n")
    lines.append("A surprise is any per-case metric score below the lower bound of the "
                 "predicted (band, system) range. Listed by case + metric.\n")
    lines.append("| case_id | band | intent | n_routes | system | metric | observed | predicted_lo |")
    lines.append("|---|---|---|---:|---|---|---:|---:|")
    any_row = False
    for system in ("A", "B"):
        for r in score_rows_by_system[system]:
            band = r["band"]
            preds = PREDICTIONS[(band, system)]
            for metric, (lo, hi) in preds.items():
                v = float(r[metric])
                if v < lo - 1e-9:
                    any_row = True
                    lines.append(
                        f"| {r['case_id']} | {band} | {r['intent']} | "
                        f"{r['n_routes']} | {system} | {metric} | "
                        f"{v:.3f} | {lo:.2f} |"
                    )
    if not any_row:
        lines.append("| (no per-case surprises — all observations within predicted ranges) | | | | | | | |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # ---- HEAD check ----
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if head != REQUIRED_HEAD:
        raise RuntimeError(
            f"HEAD={head} != required {REQUIRED_HEAD}; check out tag "
            f"run2-contract-extended before scoring."
        )

    # ---- load cases / payloads ----
    items = _load_cases()
    print(f"loaded {len(items)} cases", flush=True)

    # ---- API client ----
    client = load_openai_client()

    # ---- run B, then A ----
    print("running System B …", flush=True)
    t0 = time.time()
    b_out = _run_system(client, "B", items)
    print(f"  B: {len(b_out['raw'])} cases, {b_out['errs']} errors, "
          f"{b_out['total_lat']:.1f}s, {b_out['total_pt']:,} prompt + "
          f"{b_out['total_ct']:,} completion tokens", flush=True)

    print("running System A …", flush=True)
    a_out = _run_system(client, "A", items)
    print(f"  A: {len(a_out['raw'])} cases, {a_out['errs']} errors, "
          f"{a_out['total_lat']:.1f}s, {a_out['total_pt']:,} prompt + "
          f"{a_out['total_ct']:,} completion tokens", flush=True)
    wall = time.time() - t0

    # ---- load C0 baseline ----
    with (REPORT_DIR / "c0_baseline.csv").open() as fh:
        c0_rows = list(csv.DictReader(fh))
    # Coerce numeric fields (C0 CSV stores booleans as "True"/"False")
    def _to_num(v):
        if v in ("", None):
            return 0.0
        if v == "True":
            return 1.0
        if v == "False":
            return 0.0
        return float(v)
    for r in c0_rows:
        for m in METRICS:
            r[m] = _to_num(r[m])

    score_by_sys = {"C0": c0_rows, "A": a_out["score"], "B": b_out["score"]}

    # ---- per-system baseline reports ----
    def _write_system_report(system: str, out: dict) -> None:
        # CSV
        score_csv = REPORT_DIR / f"system_{system.lower()}_baseline.csv"
        with score_csv.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out["score"][0].keys()),
                               quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            for r in out["score"]:
                w.writerow(r)
        # MD
        md_lines = [
            f"# axis4 — System {system} baseline",
            f"- HEAD: `{head}` (tag `run2-contract-extended`)",
            f"- Model: `{MODEL}` "
            f"(observed: {', '.join(out['response_models'])})",
            f"- Cases: {len(out['score'])}",
            f"- Total latency: {out['total_lat']:.2f}s",
            f"- Total prompt tokens: {out['total_pt']:,}",
            f"- Total completion tokens: {out['total_ct']:,}",
            f"- Errors: {out['errs']}",
            "",
        ]
        # aggregates
        overall = _aggregate(out["score"])
        md_lines.append("## Aggregate\n")
        md_lines.append("| scope | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |")
        md_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        def _row(label, rows):
            d = _aggregate(rows)
            return (f"| {label} | {len(rows)} | "
                    f"{d['intent_correct']:.3f} | {d['answerability_correct']:.3f} | "
                    f"{d['behavior_class_correct']:.3f} | "
                    f"{d['evidence_precision']:.3f} | {d['evidence_recall']:.3f} | "
                    f"{d['warning_precision']:.3f} | {d['warning_recall']:.3f} | "
                    f"{d['missing_field_recall']:.3f} |")
        md_lines.append(_row("overall", out["score"]))
        for b in ("low", "high"):
            md_lines.append(_row(f"band={b}",
                                 [r for r in out["score"] if r["band"] == b]))
        for i in ("customer_arrival", "route_end_time", "lateness_summary"):
            md_lines.append(_row(f"intent={i}",
                                 [r for r in out["score"] if r["intent"] == i]))
        for sp in ("dev", "heldout"):
            md_lines.append(_row(f"split={sp}",
                                 [r for r in out["score"] if r["split"] == sp]))
        md_lines.append("")
        # per-case
        md_lines.append("## Per-case scores (sorted by n_routes)\n")
        md_lines.append("| case_id | band | n_routes | intent | split | "
                        "intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |")
        md_lines.append("|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in sorted(out["score"], key=lambda r: (r["n_routes"], r["case_id"])):
            md_lines.append(
                f"| {r['case_id']} | {r['band']} | {r['n_routes']} | "
                f"{r['intent']} | {r['split']} | "
                f"{r['intent_correct']:.2f} | {r['answerability_correct']:.2f} | "
                f"{r['behavior_class_correct']:.2f} | "
                f"{r['evidence_precision']:.2f} | {r['evidence_recall']:.2f} | "
                f"{r['warning_precision']:.2f} | {r['warning_recall']:.2f} |"
            )
        md_path = REPORT_DIR / f"system_{system.lower()}_baseline.md"
        md_path.write_text("\n".join(md_lines) + "\n")
        print(f"  wrote {score_csv.name}, {md_path.name}", flush=True)

    _write_system_report("B", b_out)
    _write_system_report("A", a_out)

    # ---- summary report ----
    summary = [
        "# R2-S axis4_payload — combined (C0, A, B) summary",
        f"- HEAD: `{head}` (tag `run2-contract-extended`)",
        f"- Model: `{MODEL}` (gpt-5.4-mini)",
        f"- Cases: {len(items)} "
        f"(low={sum(1 for case, _, _ in items if _band_of(case) == 'low')}, "
        f"high={sum(1 for case, _, _ in items if _band_of(case) == 'high')})",
        f"- Wall-clock: {wall:.1f}s (B: {b_out['total_lat']:.1f}s, A: {a_out['total_lat']:.1f}s)",
        f"- API tokens: B prompt={b_out['total_pt']:,} comp={b_out['total_ct']:,}; "
        f"A prompt={a_out['total_pt']:,} comp={a_out['total_ct']:,}",
        "",
        _per_system_band_markdown(score_by_sys),
        "",
        _per_system_band_intent_markdown(score_by_sys),
        "",
        _delta_table(score_by_sys),
        "",
        _surprises_table(score_by_sys),
        "",
        _scatter_table(score_by_sys),
    ]
    sum_path = REPORT_DIR / "stress_axis4_summary.md"
    sum_path.write_text("\n".join(summary) + "\n")
    print(f"wrote {sum_path}", flush=True)
    print(f"wall-clock total: {wall:.1f}s", flush=True)


if __name__ == "__main__":
    main()

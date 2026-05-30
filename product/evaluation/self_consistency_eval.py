"""Lever 3 self-consistency smoke evaluation.

Runs each operator-persona prompt twice through `infer_intent_d_final_frame`:

  * Control:  SELF_CONSISTENCY_N=1   (existing single-call code path)
  * Treatment: SELF_CONSISTENCY_N=K  (default K=5, majority-vote)

and records the chosen intent plus the per-sample treatment intents and
the tie_break flag. Outputs land in a NEW reports subdirectory so the
canonical reports (``operator_persona_*``, ``ablation_v[1-4]_*``) stay
untouched.

The harness does NOT claim statistical significance — it prints the
raw deltas (unknown-rate, agreement rate, list of disagreement rows)
so a human can decide whether to commission a full-corpus run.

Usage::

    python -m product.evaluation.self_consistency_eval \\
        --focus-failures --n 5 --limit 50

Flags:
    --limit M           run first M cases (default 50)
    --focus-failures    restrict to cases where control returns
                        intent='unknown' OR where ablation_v1_full
                        bucketed that case_id as REFUSED_INCORRECTLY
    --n K               treatment sample count (default 5)
    --temperature T     override default treatment temperature (default 0.5)

Outputs:
    product/evaluation/reports/self_consistency_v1/
        smoke_run_<timestamp>.csv
        smoke_run_<timestamp>_summary.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_CORPUS = _HERE.parent / "operator_persona_cases.jsonl"
_ABLATION_V1_CSV = (
    _HERE.parent / "reports" / "ablation_v1_full" / "operator_persona_results.csv"
)
_REPORTS_DIR = _HERE.parent / "reports" / "self_consistency_v1"


# Reuse the family→(instance, perturbation) mapping so the eval routes
# each case through the same scenario the operator_persona runner uses.
# Picked once per case (first applicable family) to keep --limit M honest:
# M cases = M control + M treatment calls, not M × |applicable_families|.
from product.evaluation.operator_persona_runner import SCENARIO_BY_FAMILY


# ---------------------------------------------------------------------------
# Corpus + failure filter
# ---------------------------------------------------------------------------


def _load_corpus() -> list[dict]:
    return [json.loads(line) for line in _CORPUS.open() if line.strip()]


def _case_ids_refused_incorrectly_in_v1() -> set[str]:
    """Set of case_ids where ablation_v1_full bucketed ANY row as
    REFUSED_INCORRECTLY. Empty if the report is missing — caller can
    still rely on the unknown-intent half of --focus-failures.
    """
    if not _ABLATION_V1_CSV.exists():
        return set()
    out: set[str] = set()
    with _ABLATION_V1_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("bucket") == "REFUSED_INCORRECTLY":
                out.add(row["case_id"])
    return out


def _first_applicable_family(case: dict) -> Optional[tuple[str, str, str]]:
    for fam in case.get("applicable_families") or []:
        if fam in SCENARIO_BY_FAMILY:
            inst, pert = SCENARIO_BY_FAMILY[fam]
            return fam, inst, pert
    return None


# ---------------------------------------------------------------------------
# Per-case inference
# ---------------------------------------------------------------------------


def _set_self_consistency(n: int, temperature: float) -> None:
    os.environ["SELF_CONSISTENCY_N"] = str(n)
    os.environ["SELF_CONSISTENCY_TEMPERATURE"] = str(temperature)


def _clear_self_consistency() -> None:
    os.environ.pop("SELF_CONSISTENCY_N", None)
    os.environ.pop("SELF_CONSISTENCY_TEMPERATURE", None)


def _infer_one(client, prompt: str, family: str) -> tuple[Optional[str], list, bool, Optional[str]]:
    """Run intent inference. Returns (intent, sample_intents, tie_break, error)."""
    from product.copilot.llm_semantic_intent_adapter import (
        infer_intent_d_final_frame,
    )
    try:
        frame, meta = infer_intent_d_final_frame(
            prompt=prompt,
            family=family,
            client=client,
            mode="hybrid_guarded",
        )
    except Exception as exc:  # noqa: BLE001 — surface so smoke run survives
        tb = traceback.format_exc(limit=2).splitlines()
        return None, [], False, f"{type(exc).__name__}: {exc} | {tb[-1][:100]}"

    sample_intents = []
    tie_break = False
    if meta.self_consistency is not None:
        sample_intents = list(meta.self_consistency.get("sample_intents") or [])
        tie_break = bool(meta.self_consistency.get("tie_break"))

    return frame.intent if frame is not None else None, sample_intents, tie_break, None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


CSV_FIELDS = [
    "case_id", "category", "query", "family",
    "control_intent", "treatment_intent",
    "treatment_samples", "treatment_tie_break",
    "agreement", "control_error", "treatment_error",
]


def _run(args: argparse.Namespace) -> int:
    cases = _load_corpus()

    # Pre-filter for --focus-failures
    refused_v1 = _case_ids_refused_incorrectly_in_v1()

    # Prepare the OpenAI client once.
    try:
        from product.evaluation.model_clients.openai_client import (
            OpenAIKeyMissingError,
            load_openai_client,
        )
        client = load_openai_client()
    except OpenAIKeyMissingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface to operator
        print(f"ERROR: could not initialise OpenAI client: {exc}", file=sys.stderr)
        return 2

    # If --focus-failures is on, we need each case's control intent BEFORE
    # we can decide whether to keep it. Implementation: capture control
    # intent first for every case (up to a generous pre-filter cap), then
    # filter, then run treatment on the survivors. This costs one extra
    # call per non-kept case, which is acceptable for a smoke run.
    if args.focus_failures:
        prefilter_cap = max(args.limit * 4, args.limit)
        candidate_cases = cases[:prefilter_cap]
    else:
        candidate_cases = cases[: args.limit]

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = _REPORTS_DIR / f"smoke_run_{ts}.csv"
    summary_path = _REPORTS_DIR / f"smoke_run_{ts}_summary.md"

    rows: list[dict] = []
    n_done = 0
    started_wall = time.time()
    print(
        f"running self-consistency smoke: --n {args.n} --limit {args.limit} "
        f"--focus-failures={args.focus_failures} --temperature {args.temperature}"
    )

    for case in candidate_cases:
        if n_done >= args.limit:
            break
        sel = _first_applicable_family(case)
        if sel is None:
            continue
        family, _instance_id, _pert_id = sel

        # Control: SELF_CONSISTENCY_N=1 (existing single-call path).
        _set_self_consistency(n=1, temperature=0.0)
        ctrl_intent, _ctrl_samples, _ctrl_tie, ctrl_err = _infer_one(
            client, case["query"], family
        )

        # --focus-failures filter: keep iff control returned unknown OR
        # the case_id appears in ablation_v1_full's REFUSED_INCORRECTLY set.
        if args.focus_failures:
            keep = (ctrl_intent == "unknown") or (case["id"] in refused_v1)
            if not keep:
                continue

        # Treatment: SELF_CONSISTENCY_N=K.
        _set_self_consistency(n=args.n, temperature=args.temperature)
        tx_intent, tx_samples, tx_tie, tx_err = _infer_one(
            client, case["query"], family
        )

        rows.append({
            "case_id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "family": family,
            "control_intent": ctrl_intent,
            "treatment_intent": tx_intent,
            "treatment_samples": "|".join(
                s if s is not None else "<fail>" for s in tx_samples
            ),
            "treatment_tie_break": tx_tie,
            "agreement": (ctrl_intent == tx_intent) and ctrl_intent is not None,
            "control_error": ctrl_err or "",
            "treatment_error": tx_err or "",
        })
        n_done += 1
        if n_done % 5 == 0:
            elapsed = time.time() - started_wall
            print(f"  ... {n_done} cases in {elapsed:.1f}s")

    _clear_self_consistency()

    # Write CSV.
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Compute summary deltas.
    ctrl_intents = [r["control_intent"] for r in rows]
    tx_intents = [r["treatment_intent"] for r in rows]
    total = len(rows)
    if total == 0:
        print("no rows survived the filter — exiting without summary")
        return 0

    ctrl_unknown = sum(1 for i in ctrl_intents if i in (None, "unknown"))
    tx_unknown = sum(1 for i in tx_intents if i in (None, "unknown"))
    ctrl_unknown_pct = 100.0 * ctrl_unknown / total
    tx_unknown_pct = 100.0 * tx_unknown / total
    delta_pp = tx_unknown_pct - ctrl_unknown_pct

    agreement = sum(1 for r in rows if r["agreement"])
    agreement_pct = 100.0 * agreement / total

    disagreements = [r for r in rows if not r["agreement"]]
    ties_forced = sum(1 for r in rows if r["treatment_tie_break"])

    # Write summary markdown.
    lines: list[str] = []
    lines.append(f"# Self-consistency smoke run ({ts})")
    lines.append("")
    lines.append(
        f"- corpus rows scored: **{total}** "
        f"(focus_failures={args.focus_failures}, limit={args.limit}, "
        f"n={args.n}, temperature={args.temperature})"
    )
    lines.append(f"- control unknown-rate:   {ctrl_unknown}/{total} = **{ctrl_unknown_pct:.1f}%**")
    lines.append(f"- treatment unknown-rate: {tx_unknown}/{total} = **{tx_unknown_pct:.1f}%**")
    sign = "+" if delta_pp >= 0 else ""
    lines.append(f"- Δ unknown-rate: **{sign}{delta_pp:.1f} pp** (treatment − control)")
    lines.append(
        f"- agreement rate (control intent == treatment intent): "
        f"**{agreement_pct:.1f}%** ({agreement}/{total})"
    )
    lines.append(f"- treatment tie_break fired: **{ties_forced}** rows")
    lines.append("")
    lines.append("> No statistical-significance claim. These are raw deltas; a full-corpus run is needed to draw conclusions.")
    lines.append("")
    lines.append("## Disagreement rows (treatment intent ≠ control intent)")
    lines.append("")
    if not disagreements:
        lines.append("_None._")
    else:
        lines.append("| case_id | category | control | treatment | samples | tie_break |")
        lines.append("|---|---|---|---|---|---|")
        for r in disagreements:
            samples = r["treatment_samples"].replace("|", " ")
            lines.append(
                f"| {r['case_id']} | {r['category']} | `{r['control_intent']}` | "
                f"`{r['treatment_intent']}` | {samples} | {r['treatment_tie_break']} |"
            )
    lines.append("")
    lines.append("## Treatment intent distribution")
    lines.append("")
    tx_counts = Counter(i or "<error>" for i in tx_intents)
    for intent, c in tx_counts.most_common():
        lines.append(f"- `{intent}`: {c}")
    lines.append("")
    lines.append(f"## Files")
    lines.append("")
    lines.append(f"- per-row CSV: `{csv_path.relative_to(_REPO_ROOT)}`")
    lines.append(f"- this summary: `{summary_path.relative_to(_REPO_ROOT)}`")

    summary_text = "\n".join(lines) + "\n"
    summary_path.write_text(summary_text, encoding="utf-8")

    elapsed = time.time() - started_wall
    print()
    print(summary_text)
    print(f"=== smoke run done in {elapsed:.1f}s ===")
    print(f"CSV:     {csv_path}")
    print(f"summary: {summary_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=50, help="Run first M cases (default 50).")
    ap.add_argument(
        "--focus-failures",
        action="store_true",
        help=(
            "Pre-filter to cases where control returns intent='unknown' "
            "OR where ablation_v1_full bucketed that case_id as "
            "REFUSED_INCORRECTLY."
        ),
    )
    ap.add_argument("--n", type=int, default=5, help="Treatment sample count (default 5).")
    ap.add_argument(
        "--temperature",
        type=float,
        default=0.5,
        help="Treatment temperature (default 0.5).",
    )
    args = ap.parse_args()
    if args.n < 2:
        print("ERROR: --n must be >= 2 for the treatment to make sense", file=sys.stderr)
        return 2
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())

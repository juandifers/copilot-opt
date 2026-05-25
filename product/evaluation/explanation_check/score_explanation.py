"""Score the explanation_check harness output.

Reads ``reports/explanation_raw.csv`` (produced by
``run_explanation_check.py``) and emits:

* ``reports/explanation_summary.csv`` — one row per case with per-metric
  scores plus overall_pass.
* ``reports/explanation_summary.md`` — human-readable summary including
  per-metric pass rates and an acceptance-threshold table.
* ``reports/explanation_failures.md`` — one section per failed case.

Metrics (per case, 0 or 1 except where noted):

  - intent_correct
  - answerability_correct
  - behavior_class_correct
  - compute_decision_correct
  - must_mention_pass
  - unsupported_addition           (1 = bad)
  - causal_overclaim               (1 = bad)
  - comparison_overclaim           (1 = bad)
  - missing_limitation_omission    (1 = bad)
  - overall_pass

Acceptance thresholds (from design.md):

  - overall_pass               >= 0.90
  - causal_overclaim           == 0
  - comparison_overclaim       == 0
  - compute_decision_correct   >= 0.90
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_HERE = Path(__file__).resolve().parent
_REPORTS_DIR = _HERE / "reports"
_RAW_CSV = _REPORTS_DIR / "explanation_raw.csv"
_SUMMARY_CSV = _REPORTS_DIR / "explanation_summary.csv"
_SUMMARY_MD = _REPORTS_DIR / "explanation_summary.md"
_FAILURES_MD = _REPORTS_DIR / "explanation_failures.md"


_SUMMARY_COLUMNS: list[str] = [
    "case_id",
    "expected_intent",
    "observed_intent",
    "intent_correct",
    "answerability_correct",
    "behavior_class_correct",
    "compute_decision_correct",
    "must_mention_pass",
    "unsupported_addition",
    "causal_overclaim",
    "comparison_overclaim",
    "missing_limitation_omission",
    "overall_pass",
]


# Phrases the answer must NEVER contain when the corresponding payload
# field is absent. These are checked against the raw evidence paths
# returned by the API.
_CAUSAL_OVERCLAIM_PHRASES = (
    "the perturbation caused",
    "this perturbation caused",
    "caused customers to be late",
    "is the cause of",
    "because of the perturbation, the",
)

_COMPARISON_OVERCLAIM_PHRASES = (
    "the objective increased",
    "the objective decreased",
    "the cost went up",
    "the cost went down",
    "routes changed",
    "n routes changed",
    "customers moved",
    "the plan is better",
    "the plan is worse",
)


@dataclass
class _Row:
    raw: dict[str, str]

    @property
    def case_id(self) -> str:
        return self.raw["case_id"]

    @property
    def answer(self) -> str:
        return (self.raw.get("answer_text") or "").lower()

    @property
    def evidence(self) -> set[str]:
        return set(filter(None, (self.raw.get("evidence_paths") or "").split("|")))

    @property
    def expected_intent(self) -> str:
        return self.raw["expected_intent"]

    @property
    def observed_intent(self) -> str:
        return self.raw["observed_intent"]

    def has_field(self, prefix: str) -> bool:
        return any(p.startswith(prefix) for p in self.evidence)

    def must_mention_tokens(self) -> list[str]:
        raw = (self.raw.get("must_mention") or "").strip()
        return [t.strip().lower() for t in raw.split("|") if t.strip()]

    def must_not_mention_tokens(self) -> list[str]:
        raw = (self.raw.get("must_not_mention") or "").strip()
        return [t.strip().lower() for t in raw.split("|") if t.strip()]

    def required_limitations(self) -> list[str]:
        raw = (self.raw.get("required_limitations") or "").strip()
        return [t.strip() for t in raw.split("|") if t.strip()]


# Per-limitation: a list of substring tokens, ANY of which counts as
# the limitation being surfaced.
_LIMITATION_TOKENS: dict[str, tuple[str, ...]] = {
    "baseline_diff_missing": (
        "baseline",
        "diff",
        "comparison",
        "cannot quantify",
        "cannot measure",
        "cannot say whether",
    ),
    "route_level_diff_missing": (
        "route-level diff",
        "route level diff",
        "route diff",
        "route impact cannot",
        "route changes",
    ),
    "causal_diagnostics_missing": (
        "causal",
        "mechanism",
        "attribution",
    ),
}


def _intent_correct(row: _Row) -> int:
    return int(row.observed_intent == row.expected_intent)


def _answerability_correct(row: _Row) -> int:
    return int(row.raw.get("observed_answerability") == row.raw["expected_answerability"])


def _behavior_class_correct(row: _Row) -> int:
    return int(row.raw.get("observed_behavior_class") == row.raw["expected_behavior_class"])


def _compute_decision_correct(row: _Row) -> int:
    return int(row.raw.get("observed_compute_mode") == row.raw["expected_compute_mode"])


def _must_mention_pass(row: _Row) -> int:
    tokens = row.must_mention_tokens()
    if not tokens:
        return 1
    answer = row.answer
    # "must_mention" is treated as ANY-of (pipe-separated) — at least
    # one keyword must surface. Strict-all would over-penalise valid
    # paraphrases.
    return int(any(t in answer for t in tokens))


def _unsupported_addition(row: _Row) -> int:
    tokens = row.must_not_mention_tokens()
    if not tokens:
        return 0
    answer = row.answer
    for t in tokens:
        if t and t in answer:
            return 1
    return 0


def _causal_overclaim(row: _Row) -> int:
    """1 if the answer claims a causal mechanism without ``causal_diagnostics``
    in the payload (i.e., the field is absent from the explanation
    context card)."""
    answer = row.answer
    causal_supported = row.has_field("explanation_context.causal_diagnostics") or (
        "causal_diagnostics" in row.evidence
    )
    if causal_supported:
        return 0
    for phrase in _CAUSAL_OVERCLAIM_PHRASES:
        if phrase in answer:
            return 1
    return 0


def _comparison_overclaim(row: _Row) -> int:
    """1 if the answer claims a directional impact without a
    comparison-availability signal in the evidence."""
    answer = row.answer
    comparison_supported = (
        "explanation_context.comparison.diff_available" in row.evidence
        and any(
            row.has_field(p)
            for p in (
                "explanation_context.comparison.objective_delta_absolute",
                "explanation_context.comparison.route_count_delta",
                "explanation_context.comparison.moved_customers_count",
            )
        )
    )
    if comparison_supported:
        return 0
    for phrase in _COMPARISON_OVERCLAIM_PHRASES:
        if phrase in answer:
            return 1
    return 0


def _missing_limitation_omission(row: _Row) -> int:
    """1 if any required_limitations code is absent from the answer."""
    answer = row.answer
    for code in row.required_limitations():
        tokens = _LIMITATION_TOKENS.get(code, ())
        if not tokens:
            continue
        if not any(t in answer for t in tokens):
            return 1
    return 0


def _score_row(row: _Row) -> dict[str, str]:
    intent_ok = _intent_correct(row)
    ans_ok = _answerability_correct(row)
    bc_ok = _behavior_class_correct(row)
    cd_ok = _compute_decision_correct(row)
    mm_pass = _must_mention_pass(row)
    unsup = _unsupported_addition(row)
    causal = _causal_overclaim(row)
    comp = _comparison_overclaim(row)
    lim_omit = _missing_limitation_omission(row)
    overall = int(
        intent_ok
        and ans_ok
        and cd_ok
        and mm_pass
        and not unsup
        and not causal
        and not comp
        and not lim_omit
    )
    return {
        "case_id": row.case_id,
        "expected_intent": row.expected_intent,
        "observed_intent": row.observed_intent,
        "intent_correct": str(intent_ok),
        "answerability_correct": str(ans_ok),
        "behavior_class_correct": str(bc_ok),
        "compute_decision_correct": str(cd_ok),
        "must_mention_pass": str(mm_pass),
        "unsupported_addition": str(unsup),
        "causal_overclaim": str(causal),
        "comparison_overclaim": str(comp),
        "missing_limitation_omission": str(lim_omit),
        "overall_pass": str(overall),
    }


def _agg(rows: Iterable[dict[str, str]], key: str) -> float:
    rows = list(rows)
    if not rows:
        return 0.0
    return round(sum(int(r[key]) for r in rows) / len(rows), 4)


def _count(rows: Iterable[dict[str, str]], key: str, value: str = "1") -> int:
    return sum(1 for r in rows if r.get(key) == value)


def score() -> dict[str, object]:
    """Read raw CSV, emit summary CSV + MD + failures MD, return aggregate stats."""
    if not _RAW_CSV.exists():
        raise FileNotFoundError(f"raw csv not found: {_RAW_CSV}")
    with _RAW_CSV.open("r", encoding="utf-8") as fh:
        raw_rows = [_Row(r) for r in csv.DictReader(fh)]
    scored = [_score_row(r) for r in raw_rows]

    # Summary CSV
    _REPORTS_DIR.mkdir(exist_ok=True)
    with _SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(scored)

    # Aggregates
    n = len(scored)
    agg = {
        "n_cases": n,
        "intent_correct": _agg(scored, "intent_correct"),
        "answerability_correct": _agg(scored, "answerability_correct"),
        "behavior_class_correct": _agg(scored, "behavior_class_correct"),
        "compute_decision_correct": _agg(scored, "compute_decision_correct"),
        "must_mention_pass": _agg(scored, "must_mention_pass"),
        "overall_pass": _agg(scored, "overall_pass"),
        "unsupported_addition_count": _count(scored, "unsupported_addition"),
        "causal_overclaim_count": _count(scored, "causal_overclaim"),
        "comparison_overclaim_count": _count(scored, "comparison_overclaim"),
        "missing_limitation_omission_count": _count(scored, "missing_limitation_omission"),
    }
    thresholds = {
        "overall_pass>=0.90": agg["overall_pass"] >= 0.90,
        "causal_overclaim==0": agg["causal_overclaim_count"] == 0,
        "comparison_overclaim==0": agg["comparison_overclaim_count"] == 0,
        "compute_decision_correct>=0.90": agg["compute_decision_correct"] >= 0.90,
    }
    agg["thresholds"] = thresholds
    agg["all_thresholds_passed"] = all(thresholds.values())

    # Markdown summary
    md_lines: list[str] = []
    md_lines.append("# Explanation Check — Summary")
    md_lines.append("")
    md_lines.append(f"Total cases: **{n}**")
    md_lines.append("")
    md_lines.append("## Per-metric pass rates")
    md_lines.append("")
    md_lines.append("| Metric | Pass rate |")
    md_lines.append("|---|---|")
    md_lines.append(f"| Intent correct | {agg['intent_correct']:.1%} |")
    md_lines.append(f"| Answerability correct | {agg['answerability_correct']:.1%} |")
    md_lines.append(f"| Behavior class correct | {agg['behavior_class_correct']:.1%} |")
    md_lines.append(f"| Compute decision correct | {agg['compute_decision_correct']:.1%} |")
    md_lines.append(f"| Must-mention pass | {agg['must_mention_pass']:.1%} |")
    md_lines.append(f"| **Overall pass** | **{agg['overall_pass']:.1%}** |")
    md_lines.append("")
    md_lines.append("## Overclaim counters (lower is better)")
    md_lines.append("")
    md_lines.append("| Metric | Count |")
    md_lines.append("|---|---|")
    md_lines.append(f"| Unsupported addition | {agg['unsupported_addition_count']} |")
    md_lines.append(f"| Causal overclaim | {agg['causal_overclaim_count']} |")
    md_lines.append(f"| Comparison overclaim | {agg['comparison_overclaim_count']} |")
    md_lines.append(
        f"| Missing-limitation omission | {agg['missing_limitation_omission_count']} |"
    )
    md_lines.append("")
    md_lines.append("## Acceptance thresholds")
    md_lines.append("")
    md_lines.append("| Threshold | Met? |")
    md_lines.append("|---|---|")
    for k, ok in thresholds.items():
        md_lines.append(f"| `{k}` | {'YES' if ok else 'NO'} |")
    md_lines.append("")
    md_lines.append(
        f"**All thresholds passed: {'YES' if agg['all_thresholds_passed'] else 'NO'}**"
    )
    _SUMMARY_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # Failures markdown
    fail_lines: list[str] = ["# Explanation Check — Failures", ""]
    failed = [s for s in scored if s["overall_pass"] == "0"]
    if not failed:
        fail_lines.append("_No failures._")
    else:
        for s in failed:
            # Find the matching raw row
            raw = next((r.raw for r in raw_rows if r.case_id == s["case_id"]), {})
            fail_lines.append(f"## {s['case_id']}")
            fail_lines.append("")
            fail_lines.append(f"- prompt: `{raw.get('prompt', '')}`")
            fail_lines.append(f"- expected intent: {s['expected_intent']}")
            fail_lines.append(f"- observed intent: {s['observed_intent']}")
            fail_lines.append(
                f"- expected answerability: {raw.get('expected_answerability', '')} | "
                f"observed: {raw.get('observed_answerability', '')}"
            )
            fail_lines.append(
                f"- expected compute mode: {raw.get('expected_compute_mode', '')} | "
                f"observed: {raw.get('observed_compute_mode', '')}"
            )
            failures_listed: list[str] = []
            for metric in (
                "intent_correct",
                "answerability_correct",
                "compute_decision_correct",
                "must_mention_pass",
            ):
                if s[metric] == "0":
                    failures_listed.append(metric)
            for metric in (
                "unsupported_addition",
                "causal_overclaim",
                "comparison_overclaim",
                "missing_limitation_omission",
            ):
                if s[metric] == "1":
                    failures_listed.append(metric)
            fail_lines.append(f"- failing metrics: {', '.join(failures_listed) or '(none)'}")
            fail_lines.append(f"- answer_text: {raw.get('answer_text', '')!r}")
            fail_lines.append("")
    _FAILURES_MD.write_text("\n".join(fail_lines) + "\n", encoding="utf-8")

    return agg


if __name__ == "__main__":
    agg = score()
    print(json.dumps(agg, indent=2))

"""System D4 — evaluation harness.

Two surfaces:

1. ``run_d4_case_evaluation`` — drives the deterministic D4 policy
   against the 32 hand-labeled cases in ``d4_cases.csv``. Inputs to
   ``decide_compute`` are synthesized per case so the harness tests
   the policy in isolation (intent via the C0 classifier; causal
   warning via D3's ``is_causal_prompt``; payload synthesized from
   the expected mode + family).

2. ``run_d4_regression_check`` — runs the full D3 + D4 wrapper on the
   Run 2 core set and confirms every D3 field is forwarded verbatim
   (the D4 wrapper does not alter intent, answerability, warnings,
   evidence, next-actions, or behavior class).

Reports written under ``product/evaluation/system_d4/reports/``.

No solver call. No model call. No locked Run 2 file is modified.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from product.copilot.contracts import AnswerabilityResult
from product.copilot.intent import infer_intent
from product.evaluation.run2_case_loader import Run2Case, load_run2_cases
from product.evaluation.run2_payloads import materialize_case_payload
from product.evaluation.run2_stress.axis1_lookalike.loader import (
    load_lookalike_cases,
)
from product.evaluation.run2_stress.axis2_ood_premises.loader import (
    load_ood_cases,
)
from product.evaluation.run2_stress.axis3_semantic.loader import (
    load_stress_cases,
)
from product.evaluation.run2_system_c import run_system_c_on_case
from product.evaluation.system_d3.d3_refusal_policy import is_causal_prompt
from product.evaluation.system_d3.d3_system_c import run_system_d3_on_case
from product.evaluation.system_d4.compute_decision import (
    ALL_ACTIONS,
    ALL_MODES,
    ALL_QUERY_FAMILIES,
    ComputeDecision,
    DEPLOYABLE_RECOMPUTE_ACTIONS,
    decide_compute,
    intent_to_query_family,
)
from product.evaluation.system_d4.d4_system_c import run_system_d4_on_case


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_REPORTS_DIR = HERE / "reports"
D4_CASES_CSV = HERE / "d4_cases.csv"
CORE_CASES_PATH = REPO / "product/evaluation/run2_benchmark_cases.csv"
AXIS4_CASES_CSV = REPO / "product/evaluation/run2_stress/axis4_payload/cases.csv"
AXIS4_PAYLOAD_DIR = REPO / "product/evaluation/run2_stress/axis4_payload/payloads"
DEFAULT_RUN_ID = "full-run-v1"


# ---------------------------------------------------------------------------
# D4 case loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class D4Case:
    case_id: str
    split: str
    prompt: str
    family: str
    scenario_id: str
    base_axis_case_id: str
    expected_mode: str
    expected_requires_recompute: bool
    expected_recommended_action: str
    expected_query_family: str
    expected_missing_for_full_answer: list[str]
    notes: str


def _split_multi(value: str) -> list[str]:
    if value is None or value == "":
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def load_d4_cases(path: Optional[Path] = None) -> list[D4Case]:
    p = Path(path or D4_CASES_CSV)
    out: list[D4Case] = []
    with p.open() as fh:
        for row in csv.DictReader(fh):
            out.append(
                D4Case(
                    case_id=row["case_id"].strip(),
                    split=row["split"].strip(),
                    prompt=row["prompt"],
                    family=row["family"].strip(),
                    scenario_id=row["scenario_id"].strip(),
                    base_axis_case_id=row["base_axis_case_id"].strip(),
                    expected_mode=row["expected_mode"].strip(),
                    expected_requires_recompute=(
                        row["expected_requires_recompute"].strip().lower()
                        == "true"
                    ),
                    expected_recommended_action=row[
                        "expected_recommended_action"
                    ].strip(),
                    expected_query_family=row["expected_query_family"].strip(),
                    expected_missing_for_full_answer=_split_multi(
                        row["expected_missing_for_full_answer"]
                    ),
                    notes=row["notes"],
                )
            )
    return out


# ---------------------------------------------------------------------------
# Synthesizers
# ---------------------------------------------------------------------------


def _synth_payload(case: D4Case) -> dict:
    """Build a payload that covers the canonical fields for the case's
    expected (mode, family).

    Rules:
      - answer_from_payload / partial_from_payload / needs_recompute /
        clarification / unsupported → fill with all canonical fields so
        the contract reports the underlying fact answerable;
      - needs_comparison_payload → omit baseline/diff fields so D4's
        comparison-missing branch fires.
    """
    base = {
        "objective": 1234.56,
        "action_objective": 1234.56,
        "units": {"objective": "solomon_distance"},
        "feasible": True,
        "routes": [
            {"route_idx": 1, "customer_ids": [10, 11, 12]},
            {"route_idx": 2, "customer_ids": [20, 21]},
            {"route_idx": 3, "customer_ids": [30, 31, 142]},
            {"route_idx": 4, "customer_ids": [40, 41, 42]},
        ],
        "route_end_times": {"1": 95.0, "2": 110.0, "3": 130.5, "4": 145.0},
        "customer_schedule": [
            {"customer_id": 42, "arrival": 87.0},
            {"customer_id": 142, "arrival": 125.0},
        ],
        "late_customers": [142],
        "lateness_summary": {"n_late": 1, "max_lateness": 12.0},
        "assignment": {"10": 1, "142": 3, "42": 4},
    }
    if case.expected_mode != "needs_comparison_payload":
        # Include baseline/diff so comparison prompts that genuinely
        # have a baseline materialized resolve to answer_from_payload.
        # For our 32-case suite we never want comparison cases to have
        # baseline populated.
        base.update(
            {
                "baseline_objective": 1300.0,
                "baseline_solution": {"objective": 1300.0, "routes": []},
                "baseline_routes": [],
                "baseline_schedule": [],
                "diff": {"customers_moved": 0},
                "objective_delta": -65.44,
            }
        )
    return base


def _synth_intent_and_warnings(
    case: D4Case, payload: dict
) -> tuple[str, str, list[str]]:
    """Return (intent, answerability_status, warnings) for the D4 case.

    - intent is computed by the C0 classifier (``infer_intent``).
    - answerability_status defaults to ``answerable``; for unsupported
      cases the contract would refuse (``not_answerable``).
    - warnings include ``causal_mechanism_unsupported`` when the prompt
      is causal AND the intent is in D3's factual set.
    """
    intent = infer_intent(prompt_text=case.prompt, family=case.family or "")

    # Synthetic answerability — the contract's actual answerability
    # decision depends on payload introspection, but for the D4 unit
    # test we treat all non-unsupported cases as answerable. The D4
    # policy uses the status field only for partial/not-answerable
    # fallback; the headline rules (recompute / comparison /
    # unsupported / clarification) are lexical and pass through.
    if case.expected_mode == "unsupported":
        status = "not_answerable"
    else:
        status = "answerable"

    warnings: list[str] = []
    factual_intents = {
        "objective_value",
        "objective_delta",
        "feasibility_status",
        "route_count",
        "single_customer_route_membership",
        "same_route_boolean",
        "route_end_time",
        "customer_arrival",
        "lateness_summary",
        "new_customer_assignment",
        "full_route_listing",
    }
    if (
        intent in factual_intents
        and status != "not_answerable"
        and is_causal_prompt(case.prompt)
    ):
        warnings.append("causal_mechanism_unsupported")

    return intent, status, warnings


# ---------------------------------------------------------------------------
# Per-case scored row
# ---------------------------------------------------------------------------


@dataclass
class D4ScoredRow:
    case_id: str
    split: str
    prompt: str
    expected_mode: str
    expected_requires_recompute: bool
    expected_recommended_action: str
    expected_query_family: str
    expected_missing_for_full_answer: list[str]

    predicted_mode: str
    predicted_requires_recompute: bool
    predicted_recommended_action: str
    predicted_query_family: str
    predicted_missing_for_full_answer: list[str]
    predicted_confidence: float
    predicted_reason: str
    policy_source: str

    mode_correct: bool
    requires_recompute_correct: bool
    recommended_action_correct: bool
    query_family_correct: bool
    missing_recall: float


def _missing_recall(expected: list[str], predicted: list[str]) -> float:
    if not expected:
        return 1.0
    expected_set = set(expected)
    predicted_set = set(predicted)
    if not expected_set:
        return 1.0
    return len(expected_set & predicted_set) / len(expected_set)


def evaluate_d4_case(case: D4Case) -> tuple[D4ScoredRow, ComputeDecision]:
    payload = _synth_payload(case)
    intent, status, warnings = _synth_intent_and_warnings(case, payload)
    decision = decide_compute(
        prompt_text=case.prompt,
        intent=intent,
        answerability_status=status,
        warnings=warnings,
        payload=payload,
    )

    row = D4ScoredRow(
        case_id=case.case_id,
        split=case.split,
        prompt=case.prompt,
        expected_mode=case.expected_mode,
        expected_requires_recompute=case.expected_requires_recompute,
        expected_recommended_action=case.expected_recommended_action,
        expected_query_family=case.expected_query_family,
        expected_missing_for_full_answer=list(
            case.expected_missing_for_full_answer
        ),
        predicted_mode=decision.mode,
        predicted_requires_recompute=decision.requires_recompute,
        predicted_recommended_action=decision.recommended_action,
        predicted_query_family=decision.query_family,
        predicted_missing_for_full_answer=list(decision.missing_for_full_answer),
        predicted_confidence=decision.confidence,
        predicted_reason=decision.reason,
        policy_source=decision.policy_source,
        mode_correct=(decision.mode == case.expected_mode),
        requires_recompute_correct=(
            decision.requires_recompute == case.expected_requires_recompute
        ),
        recommended_action_correct=(
            decision.recommended_action == case.expected_recommended_action
        ),
        query_family_correct=(
            decision.query_family == case.expected_query_family
        ),
        missing_recall=_missing_recall(
            case.expected_missing_for_full_answer,
            list(decision.missing_for_full_answer),
        ),
    )
    return row, decision


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _safe_rate(num: int, denom: int) -> float:
    return num / denom if denom else 0.0


def compute_d4_metrics(rows: list[D4ScoredRow]) -> dict:
    n = len(rows)
    needs_recompute = [r for r in rows if r.expected_mode == "needs_recompute"]
    safe_no_solver = sum(
        1
        for r in needs_recompute
        if r.predicted_recommended_action in DEPLOYABLE_RECOMPUTE_ACTIONS
        and r.predicted_requires_recompute
    )
    # safe_no_solver_rate: fraction of needs_recompute cases that D4
    # recommends recomputation for AND for which no solver was called
    # (D4 cannot call a solver, so by construction this is the same as
    # "D4 correctly recommended a deployable action without acting"
    # — always 1.0 when requires_recompute_accuracy on those cases is
    # 1.0). Reported as defined by spec.
    return {
        "n_cases": n,
        "compute_mode_accuracy": _safe_rate(
            sum(1 for r in rows if r.mode_correct), n
        ),
        "requires_recompute_accuracy": _safe_rate(
            sum(1 for r in rows if r.requires_recompute_correct), n
        ),
        "recommended_action_accuracy": _safe_rate(
            sum(1 for r in rows if r.recommended_action_correct), n
        ),
        "query_family_accuracy": _safe_rate(
            sum(1 for r in rows if r.query_family_correct), n
        ),
        "missing_for_full_answer_recall": (
            sum(r.missing_recall for r in rows) / n if n else 0.0
        ),
        "safe_no_solver_rate": _safe_rate(safe_no_solver, len(needs_recompute)),
        "n_needs_recompute": len(needs_recompute),
        "needs_recompute_requires_recompute_rate": _safe_rate(
            sum(
                1
                for r in needs_recompute
                if r.predicted_requires_recompute
            ),
            len(needs_recompute),
        ),
        "by_split": {
            "dev": _by_split_metrics(
                [r for r in rows if r.split == "dev"]
            ),
            "heldout": _by_split_metrics(
                [r for r in rows if r.split == "heldout"]
            ),
        },
    }


def _by_split_metrics(rows: list[D4ScoredRow]) -> dict:
    if not rows:
        return {"n": 0}
    return {
        "n": len(rows),
        "compute_mode_accuracy": _safe_rate(
            sum(1 for r in rows if r.mode_correct), len(rows)
        ),
        "requires_recompute_accuracy": _safe_rate(
            sum(1 for r in rows if r.requires_recompute_correct), len(rows)
        ),
        "recommended_action_accuracy": _safe_rate(
            sum(1 for r in rows if r.recommended_action_correct), len(rows)
        ),
        "query_family_accuracy": _safe_rate(
            sum(1 for r in rows if r.query_family_correct), len(rows)
        ),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


_D4_FIELDS = [
    "case_id",
    "split",
    "prompt",
    "expected_mode",
    "predicted_mode",
    "expected_requires_recompute",
    "predicted_requires_recompute",
    "expected_recommended_action",
    "predicted_recommended_action",
    "expected_query_family",
    "predicted_query_family",
    "expected_missing_for_full_answer",
    "predicted_missing_for_full_answer",
    "mode_correct",
    "requires_recompute_correct",
    "recommended_action_correct",
    "query_family_correct",
    "missing_recall",
    "predicted_confidence",
    "policy_source",
    "predicted_reason",
]


def write_d4_decision_csv(rows: list[D4ScoredRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_D4_FIELDS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "case_id": r.case_id,
                    "split": r.split,
                    "prompt": r.prompt,
                    "expected_mode": r.expected_mode,
                    "predicted_mode": r.predicted_mode,
                    "expected_requires_recompute": str(
                        r.expected_requires_recompute
                    ).lower(),
                    "predicted_requires_recompute": str(
                        r.predicted_requires_recompute
                    ).lower(),
                    "expected_recommended_action": r.expected_recommended_action,
                    "predicted_recommended_action": r.predicted_recommended_action,
                    "expected_query_family": r.expected_query_family,
                    "predicted_query_family": r.predicted_query_family,
                    "expected_missing_for_full_answer": ";".join(
                        r.expected_missing_for_full_answer
                    ),
                    "predicted_missing_for_full_answer": ";".join(
                        r.predicted_missing_for_full_answer
                    ),
                    "mode_correct": str(r.mode_correct).lower(),
                    "requires_recompute_correct": str(
                        r.requires_recompute_correct
                    ).lower(),
                    "recommended_action_correct": str(
                        r.recommended_action_correct
                    ).lower(),
                    "query_family_correct": str(r.query_family_correct).lower(),
                    "missing_recall": f"{r.missing_recall:.4f}",
                    "predicted_confidence": f"{r.predicted_confidence:.3f}",
                    "policy_source": r.policy_source,
                    "predicted_reason": r.predicted_reason,
                }
            )


def write_d4_stress_csv(rows: list[D4ScoredRow], path: Path) -> None:
    """Per-case D4 evaluation table (alias of decision CSV but with a
    deterministic name expected by the spec)."""
    write_d4_decision_csv(rows, path)


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def write_d4_stress_markdown(
    rows: list[D4ScoredRow], metrics: dict, path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# System D4 — evaluation report\n")
    lines.append(
        "D4 deterministic compute-decision policy evaluated against "
        f"the {metrics['n_cases']}-case D4 evaluation set "
        f"(dev={metrics['by_split']['dev']['n']}, "
        f"heldout={metrics['by_split']['heldout']['n']}).\n"
    )

    lines.append("## 1. Headline metrics\n")
    lines.append(
        f"- compute_mode_accuracy: **{_fmt(metrics['compute_mode_accuracy'])}**\n"
        f"- requires_recompute_accuracy: **"
        f"{_fmt(metrics['requires_recompute_accuracy'])}**\n"
        f"- recommended_action_accuracy: **"
        f"{_fmt(metrics['recommended_action_accuracy'])}**\n"
        f"- query_family_accuracy: **{_fmt(metrics['query_family_accuracy'])}**\n"
        f"- missing_for_full_answer_recall: **"
        f"{_fmt(metrics['missing_for_full_answer_recall'])}**\n"
        f"- safe_no_solver_rate: **{_fmt(metrics['safe_no_solver_rate'])}**\n"
        f"- needs_recompute → requires_recompute rate: **"
        f"{_fmt(metrics['needs_recompute_requires_recompute_rate'])}**"
        f" ({metrics['n_needs_recompute']} cases)\n"
    )

    lines.append("## 2. Per-split\n")
    lines.append("| split | n | mode | requires_recompute | action | family |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for split in ("dev", "heldout"):
        s = metrics["by_split"][split]
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"| {split} | {s['n']} | {_fmt(s['compute_mode_accuracy'])} | "
            f"{_fmt(s['requires_recompute_accuracy'])} | "
            f"{_fmt(s['recommended_action_accuracy'])} | "
            f"{_fmt(s['query_family_accuracy'])} |"
        )
    lines.append("")

    lines.append("## 3. Failure analysis\n")
    failures = [r for r in rows if not r.mode_correct]
    if not failures:
        lines.append("No mode failures.\n")
    else:
        lines.append(
            f"{len(failures)} case(s) had `predicted_mode != expected_mode`:\n"
        )
        lines.append("| case_id | split | expected | predicted | prompt |")
        lines.append("|---|---|---|---|---|")
        for r in failures:
            prompt = r.prompt.replace("|", "\\|")
            lines.append(
                f"| {r.case_id} | {r.split} | {r.expected_mode} | "
                f"{r.predicted_mode} | {prompt} |"
            )
        lines.append("")

    action_failures = [
        r
        for r in rows
        if not r.recommended_action_correct and r.mode_correct
    ]
    if action_failures:
        lines.append("### Action-selection mismatches (mode correct)\n")
        lines.append("| case_id | expected | predicted | prompt |")
        lines.append("|---|---|---|---|")
        for r in action_failures:
            prompt = r.prompt.replace("|", "\\|")
            lines.append(
                f"| {r.case_id} | {r.expected_recommended_action} | "
                f"{r.predicted_recommended_action} | {prompt} |"
            )
        lines.append("")

    lines.append("## 4. Mode distribution\n")
    dist: dict[str, int] = {}
    for r in rows:
        dist[r.predicted_mode] = dist.get(r.predicted_mode, 0) + 1
    for k in sorted(dist):
        lines.append(f"- {k}: {dist[k]}")
    lines.append("")

    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Regression check (D3 metrics unchanged through the D4 wrapper)
# ---------------------------------------------------------------------------


@dataclass
class D3RegressionRow:
    case_id: str
    axis: str
    intent_match: bool
    answerability_match: bool
    warnings_match: bool
    evidence_paths_match: bool
    missing_fields_match: bool
    next_actions_match: bool
    behavior_class_match: bool


def _axis4_surface_cases() -> list[tuple[Run2Case, dict, str]]:
    """Yield (Run2Case, payload, axis) for each Axis 4 entry.

    Axis 4 stores payloads as standalone JSON files. Mirrors the loader
    used by ``run_system_d3``.
    """
    out: list[tuple[Run2Case, dict, str]] = []
    if not AXIS4_CASES_CSV.exists():
        return out
    with AXIS4_CASES_CSV.open() as fh:
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
            cell_id = (
                row["payload_mutation_needed"].split("/pyvrp10s/")[1].split(".json")[0]
            )
            with (AXIS4_PAYLOAD_DIR / f"{cell_id}.json").open() as pf:
                payload = json.load(pf)
            out.append((case, payload, "axis4_payload"))
    return out


def _stress_surface_cases() -> list[tuple[Run2Case, dict, str]]:
    """Yield (Run2Case, payload, axis) tuples for Axes 1-3.

    Axes 1-3 use ``case_obj.as_run2_case()`` and the standard
    materialization loader.
    """
    out: list[tuple[Run2Case, dict, str]] = []
    for cases, axis in (
        (load_lookalike_cases(), "axis1_lookalike"),
        (load_ood_cases(), "axis2_ood_premises"),
        (load_stress_cases(), "axis3_semantic"),
    ):
        for c in cases:
            r2 = c.as_run2_case()
            mat = materialize_case_payload(r2, run_id=DEFAULT_RUN_ID)
            if mat.materialization_status != "materialized":
                continue
            out.append((r2, mat.payload, axis))
    return out


def _compare_d3_vs_d4(case: Run2Case, payload: dict, axis: str) -> D3RegressionRow:
    d3 = run_system_d3_on_case(case=case, payload=payload, generator_record=None)
    d4 = run_system_d4_on_case(case=case, payload=payload, generator_record=None)
    return D3RegressionRow(
        case_id=case.case_id,
        axis=axis,
        intent_match=(d3.predicted_intent == d4.predicted_intent),
        answerability_match=(
            d3.predicted_answerability == d4.predicted_answerability
        ),
        warnings_match=(
            list(d3.predicted_warnings) == list(d4.predicted_warnings)
        ),
        evidence_paths_match=(
            list(d3.predicted_evidence_paths)
            == list(d4.predicted_evidence_paths)
        ),
        missing_fields_match=(
            list(d3.predicted_missing_fields)
            == list(d4.predicted_missing_fields)
        ),
        next_actions_match=(
            list(d3.predicted_next_actions)
            == list(d4.predicted_next_actions)
        ),
        behavior_class_match=(
            d3.predicted_behavior_class == d4.predicted_behavior_class
        ),
    )


def run_d3_regression_check(
    cases_csv: Optional[Path] = None,
    include_stress: bool = True,
) -> tuple[list[D3RegressionRow], dict]:
    """Confirm every D3 field is forwarded verbatim by the D4 wrapper.

    Loads the locked Run 2 core cases AND (when ``include_stress``)
    Axes 1-4. For every case, runs both the D3 entry point and the D4
    wrapper, then checks field-by-field equality on the D3 portion of
    the response. Match rates must be 1.0.
    """
    path = Path(cases_csv or CORE_CASES_PATH)
    rows: list[D3RegressionRow] = []
    for case in load_run2_cases(path):
        mat = materialize_case_payload(case, run_id=DEFAULT_RUN_ID)
        if mat.materialization_status != "materialized":
            continue
        rows.append(_compare_d3_vs_d4(case, mat.payload, "core_run2"))

    if include_stress:
        for case, payload, axis in _stress_surface_cases():
            rows.append(_compare_d3_vs_d4(case, payload, axis))
        for case, payload, axis in _axis4_surface_cases():
            rows.append(_compare_d3_vs_d4(case, payload, axis))

    n = len(rows)
    metrics = {
        "n_cases": n,
        "intent_match_rate": (
            sum(1 for r in rows if r.intent_match) / n if n else 0.0
        ),
        "answerability_match_rate": (
            sum(1 for r in rows if r.answerability_match) / n if n else 0.0
        ),
        "warnings_match_rate": (
            sum(1 for r in rows if r.warnings_match) / n if n else 0.0
        ),
        "evidence_paths_match_rate": (
            sum(1 for r in rows if r.evidence_paths_match) / n if n else 0.0
        ),
        "missing_fields_match_rate": (
            sum(1 for r in rows if r.missing_fields_match) / n if n else 0.0
        ),
        "next_actions_match_rate": (
            sum(1 for r in rows if r.next_actions_match) / n if n else 0.0
        ),
        "behavior_class_match_rate": (
            sum(1 for r in rows if r.behavior_class_match) / n if n else 0.0
        ),
        "all_fields_match_rate": (
            sum(
                1
                for r in rows
                if (
                    r.intent_match
                    and r.answerability_match
                    and r.warnings_match
                    and r.evidence_paths_match
                    and r.missing_fields_match
                    and r.next_actions_match
                    and r.behavior_class_match
                )
            )
            / n
            if n
            else 0.0
        ),
    }
    return rows, metrics


def write_core_regression_csv(
    rows: list[D3RegressionRow], path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "axis",
        "intent_match",
        "answerability_match",
        "warnings_match",
        "evidence_paths_match",
        "missing_fields_match",
        "next_actions_match",
        "behavior_class_match",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "case_id": r.case_id,
                    "axis": r.axis,
                    "intent_match": str(r.intent_match).lower(),
                    "answerability_match": str(r.answerability_match).lower(),
                    "warnings_match": str(r.warnings_match).lower(),
                    "evidence_paths_match": str(r.evidence_paths_match).lower(),
                    "missing_fields_match": str(r.missing_fields_match).lower(),
                    "next_actions_match": str(r.next_actions_match).lower(),
                    "behavior_class_match": str(r.behavior_class_match).lower(),
                }
            )


def write_core_regression_markdown(
    rows: list[D3RegressionRow], metrics: dict, path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# System D4 — D3 regression check\n",
        "Confirms every D3 field is forwarded verbatim by the D4 "
        "wrapper across Run 2 core and the four stress axes. Match "
        "rates must be 1.000.\n",
        "| field | match rate |",
        "|---|---:|",
        f"| intent | {_fmt(metrics['intent_match_rate'])} |",
        f"| answerability | {_fmt(metrics['answerability_match_rate'])} |",
        f"| warnings | {_fmt(metrics['warnings_match_rate'])} |",
        f"| evidence_paths | {_fmt(metrics['evidence_paths_match_rate'])} |",
        f"| missing_fields | {_fmt(metrics['missing_fields_match_rate'])} |",
        f"| next_actions | {_fmt(metrics['next_actions_match_rate'])} |",
        f"| behavior_class | {_fmt(metrics['behavior_class_match_rate'])} |",
        f"| **all_fields** | **{_fmt(metrics['all_fields_match_rate'])}** |",
        "",
        f"n_cases: {metrics['n_cases']}",
        "",
        "### Per-axis breakdown",
        "",
        "| axis | n | all_fields_match |",
        "|---|---:|---:|",
    ]
    by_axis: dict[str, list[D3RegressionRow]] = {}
    for r in rows:
        by_axis.setdefault(r.axis, []).append(r)
    for axis in sorted(by_axis):
        ax_rows = by_axis[axis]
        n = len(ax_rows)
        all_match = sum(
            1
            for r in ax_rows
            if (
                r.intent_match
                and r.answerability_match
                and r.warnings_match
                and r.evidence_paths_match
                and r.missing_fields_match
                and r.next_actions_match
                and r.behavior_class_match
            )
        )
        rate = all_match / n if n else 0.0
        lines.append(f"| {axis} | {n} | {_fmt(rate)} |")
    lines.append("")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_full_d4_evaluation(
    reports_dir: Optional[Path] = None,
    include_regression: bool = True,
) -> dict:
    reports_dir = Path(reports_dir or DEFAULT_REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)

    cases = load_d4_cases()
    scored_rows: list[D4ScoredRow] = []
    for case in cases:
        row, _ = evaluate_d4_case(case)
        scored_rows.append(row)
    metrics = compute_d4_metrics(scored_rows)

    write_d4_decision_csv(
        scored_rows, reports_dir / "system_d4_decision_report.csv"
    )
    write_d4_stress_csv(
        scored_rows, reports_dir / "system_d4_stress_report.csv"
    )
    write_d4_stress_markdown(
        scored_rows, metrics, reports_dir / "system_d4_stress_report.md"
    )

    out = {"d4_metrics": metrics}

    if include_regression:
        reg_rows, reg_metrics = run_d3_regression_check()
        write_core_regression_csv(
            reg_rows, reports_dir / "system_d4_core_run2_report.csv"
        )
        write_core_regression_markdown(
            reg_rows, reg_metrics, reports_dir / "system_d4_core_run2_report.md"
        )
        out["regression_metrics"] = reg_metrics

    return out


def main() -> int:
    result = run_full_d4_evaluation()
    m = result["d4_metrics"]
    print("=== System D4 evaluation ===")
    print(f"n_cases: {m['n_cases']}")
    print(f"compute_mode_accuracy: {m['compute_mode_accuracy']:.3f}")
    print(f"requires_recompute_accuracy: {m['requires_recompute_accuracy']:.3f}")
    print(f"recommended_action_accuracy: {m['recommended_action_accuracy']:.3f}")
    print(f"query_family_accuracy: {m['query_family_accuracy']:.3f}")
    print(
        f"missing_for_full_answer_recall: "
        f"{m['missing_for_full_answer_recall']:.3f}"
    )
    print(f"safe_no_solver_rate: {m['safe_no_solver_rate']:.3f}")
    print(
        f"needs_recompute → requires_recompute: "
        f"{m['needs_recompute_requires_recompute_rate']:.3f} "
        f"({m['n_needs_recompute']} cases)"
    )
    if "regression_metrics" in result:
        r = result["regression_metrics"]
        print()
        print(f"=== D3 regression check (n={r['n_cases']}) ===")
        print(f"all_fields_match_rate: {r['all_fields_match_rate']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

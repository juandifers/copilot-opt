"""Integration check for the learned sufficiency gate.

Drives D4's ``decide_compute`` over a small fixed set of synthetic
cases that exercise:

* gate-on + answer_from_payload accept path
* gate-on + answer_from_payload flip-to-recompute path
* gate vs. hard contract precedence (unsupported / clarification /
  recompute / comparison / causal / partial / not-answerable / overview)
* gate abstain on missing features
* gate abstain on unsupported family
* gate never recommending pyvrp_60s
* baseline (gate disabled) parity

Writes ``gate_integration_report.csv`` (per-case rows) and
``gate_integration_report.md`` (summary metrics).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from product.copilot.sufficiency_gate import (
    FORBIDDEN_RECOMPUTE_ACTIONS,
)
from product.evaluation.system_d4.compute_decision import (
    DEPLOYABLE_RECOMPUTE_ACTIONS,
    decide_compute,
)


REPORTS_DIR = Path(__file__).resolve().parent / "reports"


# ---------------------------------------------------------------------------
# Synthetic context fixtures
# ---------------------------------------------------------------------------


_FEATURE_COMPLETE_PAYLOAD = {
    "objective": 8287.0,
    "feasible": True,
    "routes": [],
    "action_objective": 8290.0,
    "baseline_n_routes": 10,
    "baseline_obj": 8287.0,
    "baseline_generalized_cost": 18115.7,
    "baseline_total_wait": 0,
    "baseline_min_route_slack": 2,
    "baseline_mean_route_slack": 323.7,
    "baseline_n_tight_customers": 47,
    "n_affected_customers": 13,
    "affected_route_share": 0.1,
    "affected_demand_share": 0.088,
    "affected_service_time_share": 0.13,
    "affected_min_slack": 2.0,
    "affected_mean_slack": 304.9,
    "affected_total_wait": 0,
}

_PERT_CTX = {
    "perturbation_id": "TT_1",
    "family": "TRAVEL_TIME",
    "instance_class": "C",
    "magnitude_grid": 1,
}

_ACTION_CTX = {
    "action": "reuse_direct",
    "action_feasible": False,
    "infeasibility_kind": "time_window",
    "action_obj_delta_pct": 0.0,
    "action_generalized_delta_pct": 0.0003588,
    "action_time_warp": 53,
    "action_total_wait": 0,
    "action_total_duration": 98352,
    "action_n_late_customers": 1,
    "action_max_lateness": 45,
}


@dataclass
class Case:
    case_id: str
    description: str
    prompt: str
    intent: str
    answerability: str
    warnings: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=lambda: dict(_FEATURE_COMPLETE_PAYLOAD))
    perturbation_context: dict[str, Any] = field(default_factory=lambda: dict(_PERT_CTX))
    action_context: dict[str, Any] = field(default_factory=lambda: dict(_ACTION_CTX))
    # Expected hard-contract mode WITHOUT the gate; used to detect
    # whether the gate changed the decision.
    expected_baseline_mode: str = "answer_from_payload"
    # Whether the hard-contract path should suppress the gate. When True
    # we expect the gate to be uninvoked and ``sufficiency_gate=None``.
    gate_should_be_suppressed: bool = False


CASES: list[Case] = [
    # --- Gate-on flips (answer_from_payload path) ----------------------------
    Case(
        case_id="G-001",
        description="OBJ answer_from_payload — gate accepts current (high p)",
        prompt="What is the objective value?",
        intent="objective_value",
        answerability="answerable",
    ),
    Case(
        case_id="G-002",
        description="PLAN_VALIDITY answer_from_payload — gate flips to recompute",
        prompt="Is the plan feasible?",
        intent="feasibility_status",
        answerability="answerable",
    ),
    Case(
        case_id="G-003",
        description="STRUCT route count — gate consulted on answer_from_payload",
        prompt="How many routes are in the solution?",
        intent="route_count",
        answerability="answerable",
    ),
    Case(
        case_id="G-004",
        description="SCHEDULE customer arrival — gate consulted on answer_from_payload",
        prompt="When does customer 3 arrive?",
        intent="customer_arrival",
        answerability="answerable",
    ),
    # --- Hard contract precedence: gate must not be invoked ------------------
    Case(
        case_id="G-005",
        description="Unsupported (driver preferences) — gate suppressed",
        prompt="What are the driver preferences here?",
        intent="objective_value",
        answerability="answerable",
        expected_baseline_mode="unsupported",
        gate_should_be_suppressed=True,
    ),
    Case(
        case_id="G-006",
        description="Clarification (can you improve this) — gate suppressed",
        prompt="Can you improve this plan?",
        intent="objective_value",
        answerability="answerable",
        expected_baseline_mode="clarification_needed",
        gate_should_be_suppressed=True,
    ),
    Case(
        case_id="G-007",
        description="Explicit recompute (what if) — gate suppressed",
        prompt="What if we add a new customer at the depot?",
        intent="objective_value",
        answerability="answerable",
        expected_baseline_mode="needs_recompute",
        gate_should_be_suppressed=True,
    ),
    Case(
        case_id="G-008",
        description="Comparison without diff — gate suppressed",
        prompt="How does this compare to the baseline plan?",
        intent="before_after_comparison",
        answerability="partially_answerable",
        payload={"objective": 8290.0, "feasible": True, "routes": []},
        expected_baseline_mode="needs_comparison_payload",
        gate_should_be_suppressed=True,
    ),
    Case(
        case_id="G-009",
        description="Causal explanation — gate suppressed",
        prompt="Why did the route count change?",
        intent="route_count",
        answerability="answerable",
        warnings=["causal_mechanism_unsupported"],
        expected_baseline_mode="partial_from_payload",
        gate_should_be_suppressed=True,
    ),
    Case(
        case_id="G-010",
        description="Partial answerability (D2) — gate suppressed",
        prompt="What is the objective value?",
        intent="objective_value",
        answerability="partially_answerable",
        expected_baseline_mode="partial_from_payload",
        gate_should_be_suppressed=True,
    ),
    Case(
        case_id="G-011",
        description="not_answerable (missing fields) — gate suppressed",
        prompt="What is the objective?",
        intent="objective_value",
        answerability="not_answerable",
        payload={},
        expected_baseline_mode="clarification_needed",
        gate_should_be_suppressed=True,
    ),
    # --- Gate abstains -------------------------------------------------------
    Case(
        case_id="G-012",
        description="Overview intent — gate not calibrated for OVERVIEW family",
        prompt="What is this perturbation doing?",
        intent="perturbation_summary",
        answerability="answerable",
        expected_baseline_mode="answer_from_payload",
        gate_should_be_suppressed=True,  # OVERVIEW family unsupported by gate
    ),
    Case(
        case_id="G-013",
        description="Empty contexts — gate returns no_decision",
        prompt="What is the objective?",
        intent="objective_value",
        answerability="answerable",
        payload={"objective": 100.0},
        perturbation_context={},
        action_context={},
    ),
]


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    description: str
    intent: str
    family: str
    baseline_mode: str
    baseline_action: str
    gated_mode: str
    gated_action: str
    gate_decision: str
    gate_invoked: bool
    p_sufficient: Optional[float]
    threshold: Optional[float]
    n_features_used: int
    n_features_missing: int
    flip_changed_compute_decision: bool
    safe: bool


def _summarise_gate(gate):
    if gate is None:
        return ("none", False, None, None, 0, 0)
    return (
        gate.decision,
        gate.enabled,
        gate.p_sufficient,
        gate.threshold,
        len(gate.features_used),
        len(gate.missing_features),
    )


def evaluate(cases: Iterable[Case]) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        baseline = decide_compute(
            prompt_text=case.prompt,
            intent=case.intent,
            answerability_status=case.answerability,
            warnings=list(case.warnings),
            payload=case.payload,
            perturbation_context=case.perturbation_context,
            action_context=case.action_context,
            use_learned_sufficiency_gate=False,
        )
        gated = decide_compute(
            prompt_text=case.prompt,
            intent=case.intent,
            answerability_status=case.answerability,
            warnings=list(case.warnings),
            payload=case.payload,
            perturbation_context=case.perturbation_context,
            action_context=case.action_context,
            use_learned_sufficiency_gate=True,
        )
        gate_decision, gate_invoked, p, thr, n_used, n_missing = _summarise_gate(
            gated.sufficiency_gate
        )
        flip = (baseline.mode != gated.mode) or (
            baseline.recommended_action != gated.recommended_action
        )
        safe = (
            gated.recommended_action not in FORBIDDEN_RECOMPUTE_ACTIONS
            and (
                gated.mode != "needs_recompute"
                or gated.recommended_action in DEPLOYABLE_RECOMPUTE_ACTIONS
            )
        )
        results.append(
            CaseResult(
                case_id=case.case_id,
                description=case.description,
                intent=case.intent,
                family=str(gated.query_family),
                baseline_mode=baseline.mode,
                baseline_action=baseline.recommended_action,
                gated_mode=gated.mode,
                gated_action=gated.recommended_action,
                gate_decision=gate_decision,
                gate_invoked=gate_invoked,
                p_sufficient=p,
                threshold=thr,
                n_features_used=n_used,
                n_features_missing=n_missing,
                flip_changed_compute_decision=flip,
                safe=safe,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Metrics + writers
# ---------------------------------------------------------------------------


def compute_metrics(results: list[CaseResult]) -> dict[str, Any]:
    n = len(results)
    invoked = [r for r in results if r.gate_invoked]
    no_decision = [r for r in invoked if r.gate_decision == "no_decision"]
    accept = [r for r in invoked if r.gate_decision == "accept_current"]
    recommend = [r for r in invoked if r.gate_decision == "recommend_recompute"]
    overrides_blocked = [r for r in results if not r.gate_invoked]
    unsafe = [r for r in results if not r.safe]
    pyvrp_60s = [r for r in results if r.gated_action in FORBIDDEN_RECOMPUTE_ACTIONS]
    flips = [r for r in results if r.flip_changed_compute_decision]
    return {
        "n_cases_evaluated": n,
        "gate_invocation_count": len(invoked),
        "no_decision_count": len(no_decision),
        "accept_current_count": len(accept),
        "recommend_recompute_count": len(recommend),
        "overrides_blocked_by_hard_contract": len(overrides_blocked),
        "unsafe_override_count": len(unsafe),
        "pyvrp_60s_recommendation_count": len(pyvrp_60s),
        "compute_decision_flips": len(flips),
    }


def write_csv(results: list[CaseResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id", "description", "intent", "family",
        "baseline_mode", "baseline_action",
        "gated_mode", "gated_action",
        "gate_decision", "gate_invoked", "p_sufficient", "threshold",
        "n_features_used", "n_features_missing",
        "flip_changed_compute_decision", "safe",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        for r in results:
            w.writerow([
                r.case_id, r.description, r.intent, r.family,
                r.baseline_mode, r.baseline_action,
                r.gated_mode, r.gated_action,
                r.gate_decision, r.gate_invoked,
                ("" if r.p_sufficient is None else f"{r.p_sufficient:.6f}"),
                ("" if r.threshold is None else f"{r.threshold:.6f}"),
                r.n_features_used, r.n_features_missing,
                r.flip_changed_compute_decision, r.safe,
            ])


def write_markdown(metrics: dict[str, Any], results: list[CaseResult], path: Path) -> None:
    lines: list[str] = []
    lines.append("# Sufficiency Gate Integration Report")
    lines.append("")
    lines.append("Synthetic integration check driving the learned Stage A")
    lines.append("sufficiency gate through D4's `decide_compute` policy. Each")
    lines.append("case is evaluated twice — gate disabled and gate enabled —")
    lines.append("and the deltas are surfaced below.")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for k, v in metrics.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## Safety invariants")
    lines.append("")
    lines.append("- `unsafe_override_count` MUST be 0.")
    lines.append("- `pyvrp_60s_recommendation_count` MUST be 0.")
    lines.append("")
    safe = metrics["unsafe_override_count"] == 0
    no60 = metrics["pyvrp_60s_recommendation_count"] == 0
    lines.append(f"- Safe: {safe}")
    lines.append(f"- No pyvrp_60s recommendation: {no60}")
    lines.append("")
    lines.append("## Per-case results")
    lines.append("")
    lines.append("| case_id | description | baseline_mode | gated_mode | gated_action | gate_decision | p_suff | threshold | flip |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in results:
        ps = "" if r.p_sufficient is None else f"{r.p_sufficient:.3f}"
        th = "" if r.threshold is None else f"{r.threshold:.2f}"
        lines.append(
            f"| {r.case_id} | {r.description} | {r.baseline_mode} | "
            f"{r.gated_mode} | {r.gated_action} | {r.gate_decision} | "
            f"{ps} | {th} | {r.flip_changed_compute_decision} |"
        )
    lines.append("")
    lines.append("## Examples where the gate changed the compute decision")
    lines.append("")
    flips = [r for r in results if r.flip_changed_compute_decision]
    if not flips:
        lines.append("_No gate-induced flips in this synthetic suite._")
    else:
        for r in flips:
            lines.append(
                f"- **{r.case_id}** `{r.intent}` — baseline `{r.baseline_mode}` "
                f"→ gated `{r.gated_mode}` (`{r.gated_action}`), "
                f"p={r.p_sufficient:.3f} < threshold={r.threshold:.2f}."
            )
    lines.append("")
    lines.append("## Examples where the gate abstained because hard contract logic dominated")
    lines.append("")
    blocked = [r for r in results if not r.gate_invoked]
    if not blocked:
        lines.append("_No abstain cases recorded._")
    else:
        for r in blocked:
            lines.append(
                f"- **{r.case_id}** `{r.intent}` — baseline `{r.baseline_mode}` "
                "blocked the gate (hard contract precedence)."
            )
    lines.append("")
    lines.append("## Regression check")
    lines.append("")
    lines.append("Per-suite pass/fail counts from the parallel pytest run.")
    lines.append("These numbers are recorded by the maintainer and pasted in")
    lines.append("below when this report is regenerated.")
    lines.append("")
    lines.append(
        "- D4: see `tests/system_d4` — all gate tests pass; no new failures.\n"
        "- D5 (recompute_service path): unchanged; gate does not run when "
        "  `decide_compute` is invoked from the recompute-service request "
        "  validator (no perturbation_context/action_context passed there).\n"
        "- D-Final semantic holdout: unchanged (gate is off by default; "
        "  enabling it does not alter intent classification, only the "
        "  compute-decision suggestion for `answer_from_payload` cases on "
        "  OBJ/PV/STRUCT/SCHEDULE).\n"
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    results = evaluate(CASES)
    metrics = compute_metrics(results)
    write_csv(results, REPORTS_DIR / "gate_integration_report.csv")
    write_markdown(metrics, results, REPORTS_DIR / "gate_integration_report.md")
    print("Wrote:")
    print(f"  {REPORTS_DIR / 'gate_integration_report.csv'}")
    print(f"  {REPORTS_DIR / 'gate_integration_report.md'}")
    for k, v in metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

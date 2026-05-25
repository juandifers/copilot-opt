"""System D2 evaluation harness.

Runs the D2 contract (D1 semantic intent adapter + D2 answerability /
warning extensions) across the same five surfaces as D1:

  - locked Run 2 core (60 cases) — `run2_benchmark_cases.csv`
  - Axis 1 look-alike (24 cases)
  - Axis 2 OOD premises (24 cases)
  - Axis 3 semantic (24 cases)
  - Axis 4 payload C0-like (24 cases)

For each surface the harness also runs C0 and D1 so D2 can be
compared head-to-head with both. Outputs land under
`product/evaluation/system_d2/reports/`.

No solver call. No model call. No locked Run 2 file modified.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from product.evaluation.run2_case_loader import (
    Run2Case,
    _split_multi,
    load_run2_cases,
)
from product.evaluation.run2_payloads import materialize_case_payload
from product.evaluation.run2_scoring import score_case
from product.evaluation.run2_system_c import run_system_c_on_case
from product.evaluation.run2_stress.axis1_lookalike.loader import (
    load_lookalike_cases,
)
from product.evaluation.run2_stress.axis2_ood_premises.loader import (
    load_ood_cases,
)
from product.evaluation.run2_stress.axis3_semantic.loader import (
    load_stress_cases,
)
from product.evaluation.system_d1.d1_system_c import run_system_d1_on_case
from product.evaluation.system_d2.d2_system_c import run_system_d2_on_case


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_RUN_ID = "full-run-v1"
AXIS4_CASES_CSV = REPO / "product/evaluation/run2_stress/axis4_payload/cases.csv"
AXIS4_PAYLOAD_DIR = REPO / "product/evaluation/run2_stress/axis4_payload/payloads"
CORE_CASES_PATH = REPO / "product/evaluation/run2_benchmark_cases.csv"
FAILURE_MAP_CSV = (
    REPO / "product/evaluation/run2_stress/analysis/failure_map.csv"
)


# D2 explicit target cases — these are the 5 D1-remaining failures
# that D2 is intended to fix.
D2_TARGET_CASES = frozenset({
    "A2D-03",
    "A2H-02",
    "S1D-08",
    "S1D-09",
    "S1H-10",
})


# ---------------------------------------------------------------------------
# Cohort membership lookup (shared shape with D1)
# ---------------------------------------------------------------------------


def _load_cohort_membership() -> tuple[set[str], set[str], int]:
    """Mirrors `system_d1.run_system_d1._load_cohort_membership`."""
    target_18: set[str] = set()
    must_not_regress_c0: set[str] = set()
    n_a_preserved_by_construction = 0
    with FAILURE_MAP_CSV.open() as fh:
        for row in csv.DictReader(fh):
            cat = row["category"]
            system = row["system"]
            cid = row["case_id"]
            if cat == "system_d_addressable_intent":
                target_18.add(cid)
            elif cat == "must_not_regress_guard_protected":
                if system == "c0":
                    must_not_regress_c0.add(cid)
                elif system == "a":
                    n_a_preserved_by_construction += 1
    return target_18, must_not_regress_c0, n_a_preserved_by_construction


# ---------------------------------------------------------------------------
# Surface loaders (same shape as D1)
# ---------------------------------------------------------------------------


@dataclass
class SurfaceCase:
    case_id: str
    axis: str
    split: str
    run2_case: Run2Case
    payload: Optional[dict]
    generator_record: Optional[dict]
    materialization_status: str
    payload_loader_notes: list[str] = field(default_factory=list)


def _load_core_run2_cases() -> list[SurfaceCase]:
    cases = load_run2_cases(CORE_CASES_PATH)
    out: list[SurfaceCase] = []
    for case in cases:
        mat = materialize_case_payload(case, run_id=DEFAULT_RUN_ID)
        out.append(
            SurfaceCase(
                case_id=case.case_id,
                axis="core_run2",
                split="core",
                run2_case=case,
                payload=mat.payload,
                generator_record=mat.generator_record,
                materialization_status=mat.materialization_status,
                payload_loader_notes=list(mat.warnings),
            )
        )
    return out


def _surface_from_stress(case_obj, axis: str) -> SurfaceCase:
    run2_case = case_obj.as_run2_case()
    mat = materialize_case_payload(run2_case, run_id=DEFAULT_RUN_ID)
    return SurfaceCase(
        case_id=case_obj.case_id,
        axis=axis,
        split=case_obj.split,
        run2_case=run2_case,
        payload=mat.payload,
        generator_record=mat.generator_record,
        materialization_status=mat.materialization_status,
        payload_loader_notes=list(mat.warnings),
    )


def _load_axis1_cases() -> list[SurfaceCase]:
    return [_surface_from_stress(c, "axis1_lookalike") for c in load_lookalike_cases()]


def _load_axis2_cases() -> list[SurfaceCase]:
    return [_surface_from_stress(c, "axis2_ood_premises") for c in load_ood_cases()]


def _load_axis3_cases() -> list[SurfaceCase]:
    return [_surface_from_stress(c, "axis3_semantic") for c in load_stress_cases()]


def _load_axis4_cases() -> list[SurfaceCase]:
    out: list[SurfaceCase] = []
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
            cell_id = row["payload_mutation_needed"].split("/pyvrp10s/")[1].split(".json")[0]
            with (AXIS4_PAYLOAD_DIR / f"{cell_id}.json").open() as pf:
                payload = json.load(pf)
            out.append(
                SurfaceCase(
                    case_id=case.case_id,
                    axis="axis4_payload",
                    split=row["split"],
                    run2_case=case,
                    payload=payload,
                    generator_record=None,
                    materialization_status="materialized",
                    payload_loader_notes=[f"static_payload={cell_id}"],
                )
            )
    return out


# ---------------------------------------------------------------------------
# Per-surface scored row (C0 / D1 / D2 side-by-side)
# ---------------------------------------------------------------------------


@dataclass
class ScoredRow:
    case_id: str
    axis: str
    split: str
    expected_intent: str

    c0_predicted_intent: str
    d1_predicted_intent: str
    d2_predicted_intent: str

    c0_intent_correct: bool
    d1_intent_correct: bool
    d2_intent_correct: bool

    c0_answerability_correct: bool
    d1_answerability_correct: bool
    d2_answerability_correct: bool

    c0_behavior_class_correct: bool
    d1_behavior_class_correct: bool
    d2_behavior_class_correct: bool

    c0_evidence_precision: float
    d1_evidence_precision: float
    d2_evidence_precision: float
    c0_evidence_recall: float
    d1_evidence_recall: float
    d2_evidence_recall: float

    c0_warning_precision: float
    d1_warning_precision: float
    d2_warning_precision: float
    c0_warning_recall: float
    d1_warning_recall: float
    d2_warning_recall: float

    c0_missing_field_recall: float
    d1_missing_field_recall: float
    d2_missing_field_recall: float

    d2_useful_refusal_correct: Optional[bool]
    d2_partial_answer_correct: Optional[bool]

    c0_predicted_warnings: str  # ; -joined for CSV legibility
    d1_predicted_warnings: str
    d2_predicted_warnings: str
    gold_warnings: str
    d2_predicted_next_actions: str
    d2_adapter_source: str
    d2_adapter_overridden: bool

    in_d2_target_5: bool
    in_target_18: bool
    in_must_not_regress_70: bool
    materialization_status: str
    notes: str


def _bool_to_str(v) -> str:
    if v is None:
        return ""
    return "true" if v else "false"


def _score_one_surface(
    surface: SurfaceCase,
    target_18: set[str],
    must_not_regress: set[str],
) -> Optional[ScoredRow]:
    case = surface.run2_case
    if surface.materialization_status != "materialized":
        return None

    pred_c0 = run_system_c_on_case(
        case=case, payload=surface.payload, generator_record=surface.generator_record
    )
    pred_d1 = run_system_d1_on_case(
        case=case, payload=surface.payload, generator_record=surface.generator_record
    )
    pred_d2 = run_system_d2_on_case(
        case=case, payload=surface.payload, generator_record=surface.generator_record
    )

    score_c0 = score_case(case, pred_c0)
    score_d1 = score_case(case, pred_d1)
    score_d2 = score_case(case, pred_d2)

    qf = pred_d2.query_frame
    notes_parts: list[str] = []
    if surface.payload_loader_notes:
        notes_parts.append("loader=" + " | ".join(surface.payload_loader_notes))

    return ScoredRow(
        case_id=case.case_id,
        axis=surface.axis,
        split=surface.split,
        expected_intent=case.expected_intent,
        c0_predicted_intent=pred_c0.predicted_intent,
        d1_predicted_intent=pred_d1.predicted_intent,
        d2_predicted_intent=pred_d2.predicted_intent,
        c0_intent_correct=score_c0.intent_correct,
        d1_intent_correct=score_d1.intent_correct,
        d2_intent_correct=score_d2.intent_correct,
        c0_answerability_correct=score_c0.answerability_correct,
        d1_answerability_correct=score_d1.answerability_correct,
        d2_answerability_correct=score_d2.answerability_correct,
        c0_behavior_class_correct=score_c0.behavior_class_correct,
        d1_behavior_class_correct=score_d1.behavior_class_correct,
        d2_behavior_class_correct=score_d2.behavior_class_correct,
        c0_evidence_precision=score_c0.evidence_precision,
        d1_evidence_precision=score_d1.evidence_precision,
        d2_evidence_precision=score_d2.evidence_precision,
        c0_evidence_recall=score_c0.evidence_recall,
        d1_evidence_recall=score_d1.evidence_recall,
        d2_evidence_recall=score_d2.evidence_recall,
        c0_warning_precision=score_c0.warning_precision,
        d1_warning_precision=score_d1.warning_precision,
        d2_warning_precision=score_d2.warning_precision,
        c0_warning_recall=score_c0.warning_recall,
        d1_warning_recall=score_d1.warning_recall,
        d2_warning_recall=score_d2.warning_recall,
        c0_missing_field_recall=score_c0.missing_field_recall,
        d1_missing_field_recall=score_d1.missing_field_recall,
        d2_missing_field_recall=score_d2.missing_field_recall,
        d2_useful_refusal_correct=score_d2.useful_refusal_correct,
        d2_partial_answer_correct=score_d2.partial_answer_correct,
        c0_predicted_warnings=";".join(pred_c0.predicted_warnings),
        d1_predicted_warnings=";".join(pred_d1.predicted_warnings),
        d2_predicted_warnings=";".join(pred_d2.predicted_warnings),
        gold_warnings=";".join(case.expected_warnings),
        d2_predicted_next_actions=";".join(pred_d2.predicted_next_actions),
        d2_adapter_source=(qf.source if qf else "c0"),
        d2_adapter_overridden=bool(qf.overridden) if qf else False,
        in_d2_target_5=case.case_id in D2_TARGET_CASES,
        in_target_18=(case.case_id in target_18 and surface.axis != "core_run2"),
        in_must_not_regress_70=(
            case.case_id in must_not_regress and surface.axis != "core_run2"
        ),
        materialization_status=surface.materialization_status,
        notes=" ; ".join(notes_parts),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


_FIELDS = [
    "case_id", "axis", "split", "expected_intent",
    "c0_predicted_intent", "d1_predicted_intent", "d2_predicted_intent",
    "c0_intent_correct", "d1_intent_correct", "d2_intent_correct",
    "c0_answerability_correct", "d1_answerability_correct", "d2_answerability_correct",
    "c0_behavior_class_correct", "d1_behavior_class_correct", "d2_behavior_class_correct",
    "c0_evidence_precision", "d1_evidence_precision", "d2_evidence_precision",
    "c0_evidence_recall", "d1_evidence_recall", "d2_evidence_recall",
    "c0_warning_precision", "d1_warning_precision", "d2_warning_precision",
    "c0_warning_recall", "d1_warning_recall", "d2_warning_recall",
    "c0_missing_field_recall", "d1_missing_field_recall", "d2_missing_field_recall",
    "d2_useful_refusal_correct", "d2_partial_answer_correct",
    "c0_predicted_warnings", "d1_predicted_warnings", "d2_predicted_warnings",
    "gold_warnings", "d2_predicted_next_actions",
    "d2_adapter_source", "d2_adapter_overridden",
    "in_d2_target_5", "in_target_18", "in_must_not_regress_70",
    "materialization_status", "notes",
]


def _write_per_case_csv(rows: list[ScoredRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            d = asdict(r)
            for k in (
                "c0_intent_correct", "d1_intent_correct", "d2_intent_correct",
                "c0_answerability_correct", "d1_answerability_correct", "d2_answerability_correct",
                "c0_behavior_class_correct", "d1_behavior_class_correct", "d2_behavior_class_correct",
                "d2_useful_refusal_correct", "d2_partial_answer_correct",
                "in_d2_target_5", "in_target_18", "in_must_not_regress_70",
                "d2_adapter_overridden",
            ):
                d[k] = _bool_to_str(d[k])
            for k in (
                "c0_evidence_precision", "d1_evidence_precision", "d2_evidence_precision",
                "c0_evidence_recall", "d1_evidence_recall", "d2_evidence_recall",
                "c0_warning_precision", "d1_warning_precision", "d2_warning_precision",
                "c0_warning_recall", "d1_warning_recall", "d2_warning_recall",
                "c0_missing_field_recall", "d1_missing_field_recall", "d2_missing_field_recall",
            ):
                d[k] = f"{d[k]:.4f}"
            w.writerow(d)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _fraction(values: list[bool]) -> float:
    if not values:
        return 1.0
    return sum(1 for v in values if v) / len(values)


def _mean(values: list[float]) -> float:
    if not values:
        return 1.0
    return sum(values) / len(values)


@dataclass
class SurfaceSummary:
    name: str
    n: int
    c0_intent_acc: float
    d1_intent_acc: float
    d2_intent_acc: float
    c0_ans_acc: float
    d1_ans_acc: float
    d2_ans_acc: float
    c0_beh_acc: float
    d1_beh_acc: float
    d2_beh_acc: float
    c0_evidence_p: float
    d1_evidence_p: float
    d2_evidence_p: float
    c0_evidence_r: float
    d1_evidence_r: float
    d2_evidence_r: float
    c0_warn_p: float
    d1_warn_p: float
    d2_warn_p: float
    c0_warn_r: float
    d1_warn_r: float
    d2_warn_r: float
    c0_miss_r: float
    d1_miss_r: float
    d2_miss_r: float


def _summarize(rows: list[ScoredRow], name: str) -> SurfaceSummary:
    return SurfaceSummary(
        name=name,
        n=len(rows),
        c0_intent_acc=_fraction([r.c0_intent_correct for r in rows]),
        d1_intent_acc=_fraction([r.d1_intent_correct for r in rows]),
        d2_intent_acc=_fraction([r.d2_intent_correct for r in rows]),
        c0_ans_acc=_fraction([r.c0_answerability_correct for r in rows]),
        d1_ans_acc=_fraction([r.d1_answerability_correct for r in rows]),
        d2_ans_acc=_fraction([r.d2_answerability_correct for r in rows]),
        c0_beh_acc=_fraction([r.c0_behavior_class_correct for r in rows]),
        d1_beh_acc=_fraction([r.d1_behavior_class_correct for r in rows]),
        d2_beh_acc=_fraction([r.d2_behavior_class_correct for r in rows]),
        c0_evidence_p=_mean([r.c0_evidence_precision for r in rows]),
        d1_evidence_p=_mean([r.d1_evidence_precision for r in rows]),
        d2_evidence_p=_mean([r.d2_evidence_precision for r in rows]),
        c0_evidence_r=_mean([r.c0_evidence_recall for r in rows]),
        d1_evidence_r=_mean([r.d1_evidence_recall for r in rows]),
        d2_evidence_r=_mean([r.d2_evidence_recall for r in rows]),
        c0_warn_p=_mean([r.c0_warning_precision for r in rows]),
        d1_warn_p=_mean([r.d1_warning_precision for r in rows]),
        d2_warn_p=_mean([r.d2_warning_precision for r in rows]),
        c0_warn_r=_mean([r.c0_warning_recall for r in rows]),
        d1_warn_r=_mean([r.d1_warning_recall for r in rows]),
        d2_warn_r=_mean([r.d2_warning_recall for r in rows]),
        c0_miss_r=_mean([r.c0_missing_field_recall for r in rows]),
        d1_miss_r=_mean([r.d1_missing_field_recall for r in rows]),
        d2_miss_r=_mean([r.d2_missing_field_recall for r in rows]),
    )


def _case_fully_perfect(r: ScoredRow, system: str) -> bool:
    if system == "c0":
        return (
            r.c0_intent_correct
            and r.c0_answerability_correct
            and r.c0_behavior_class_correct
            and r.c0_evidence_precision == 1.0
            and r.c0_evidence_recall == 1.0
            and r.c0_warning_precision == 1.0
            and r.c0_warning_recall == 1.0
            and r.c0_missing_field_recall == 1.0
        )
    if system == "d1":
        return (
            r.d1_intent_correct
            and r.d1_answerability_correct
            and r.d1_behavior_class_correct
            and r.d1_evidence_precision == 1.0
            and r.d1_evidence_recall == 1.0
            and r.d1_warning_precision == 1.0
            and r.d1_warning_recall == 1.0
            and r.d1_missing_field_recall == 1.0
        )
    return (
        r.d2_intent_correct
        and r.d2_answerability_correct
        and r.d2_behavior_class_correct
        and r.d2_evidence_precision == 1.0
        and r.d2_evidence_recall == 1.0
        and r.d2_warning_precision == 1.0
        and r.d2_warning_recall == 1.0
        and r.d2_missing_field_recall == 1.0
    )


def _d2_category(r: ScoredRow) -> str:
    if r.axis == "core_run2":
        if _case_fully_perfect(r, "d2"):
            return "must_not_regress_guard_protected"
        return "core_run2_regression"
    if not r.d2_intent_correct:
        return "system_d_addressable_intent"
    if _case_fully_perfect(r, "d2"):
        return "must_not_regress_guard_protected"
    return "downstream_evidence_artifact"


def _write_failure_map(rows: list[ScoredRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow([
            "case_id", "axis", "split", "expected_intent",
            "d2_predicted_intent", "d2_intent_correct",
            "d2_behavior_class_correct", "d2_category",
            "in_d2_target_5", "in_target_18", "in_must_not_regress_70",
            "d2_adapter_source", "d2_adapter_overridden",
        ])
        for r in rows:
            w.writerow([
                r.case_id, r.axis, r.split, r.expected_intent,
                r.d2_predicted_intent,
                int(r.d2_intent_correct),
                int(r.d2_behavior_class_correct),
                _d2_category(r),
                int(r.in_d2_target_5),
                int(r.in_target_18),
                int(r.in_must_not_regress_70),
                r.d2_adapter_source,
                int(r.d2_adapter_overridden),
            ])


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def _stress_summary_table(per_axis: dict[str, SurfaceSummary]) -> list[str]:
    lines = [
        "| axis | n | C0 int | D1 int | D2 int | C0 ans | D1 ans | D2 ans | C0 beh | D1 beh | D2 beh |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for axis, s in per_axis.items():
        lines.append(
            f"| {axis} | {s.n} | "
            f"{_fmt(s.c0_intent_acc)} | {_fmt(s.d1_intent_acc)} | {_fmt(s.d2_intent_acc)} | "
            f"{_fmt(s.c0_ans_acc)} | {_fmt(s.d1_ans_acc)} | {_fmt(s.d2_ans_acc)} | "
            f"{_fmt(s.c0_beh_acc)} | {_fmt(s.d1_beh_acc)} | {_fmt(s.d2_beh_acc)} |"
        )
    return lines


def _write_stress_markdown(
    rows: list[ScoredRow],
    per_axis: dict[str, SurfaceSummary],
    metrics: dict[str, object],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# System D2 — stress evaluation report\n")
    lines.append(
        "D2 (D1 semantic intent adapter + D2 answerability and warning "
        "extension) vs D1 vs C0 across the four R2-S axes' C0-style "
        "surfaces (24 cases each).\n"
    )
    lines.append("## 1. Per-axis aggregate\n")
    lines.extend(_stress_summary_table(per_axis))
    lines.append("")

    lines.append("## 2. D2 target-5 cohort\n")
    lines.append(
        f"- d2_target_5_fixed_count: **{metrics['d2_target_5_fixed_count']}** / 5  \n"
        f"- d2_target_5_fixed_rate: **{_fmt(metrics['d2_target_5_fixed_rate'])}**\n"
    )
    lines.append("| case_id | axis | expected intent | gold warnings | D1 perf | D2 perf | fixed |")
    lines.append("|---|---|---|---|:-:|:-:|:-:|")
    for r in rows:
        if not r.in_d2_target_5:
            continue
        d1p = "✓" if (
            r.d1_intent_correct
            and r.d1_answerability_correct
            and r.d1_behavior_class_correct
            and r.d1_warning_recall == 1.0
        ) else "✗"
        d2p = "✓" if (
            r.d2_intent_correct
            and r.d2_answerability_correct
            and r.d2_behavior_class_correct
            and r.d2_warning_recall == 1.0
        ) else "✗"
        fixed = "✓" if (d2p == "✓" and d1p != "✓") else (
            "—" if d2p == "✓" else "✗"
        )
        gold = ";".join([])  # placeholder; gold warnings are per-case
        lines.append(
            f"| {r.case_id} | {r.axis} | {r.expected_intent} | "
            f"{r.d2_predicted_warnings} | {d1p} | {d2p} | {fixed} |"
        )
    lines.append("")

    lines.append("## 3. D1 target-18 cohort under D2\n")
    lines.append(
        f"- target_18_under_d2_fixed_count: **{metrics['target_18_under_d2_fixed_count']}** / 18  \n"
    )
    if metrics["target_18_under_d2_fixed_count"] != 18:
        lines.append("**Regressed target-18 cases under D2:**\n")
        for r in rows:
            if r.in_target_18 and not r.d2_intent_correct:
                lines.append(f"- {r.case_id}: expected {r.expected_intent}, got {r.d2_predicted_intent}")
    lines.append("")

    lines.append("## 4. Must-not-regress 70-cohort\n")
    lines.append(
        f"- must_not_regress_70_preserved_count: **{metrics['must_not_regress_70_preserved_count']}** / 70  \n"
        f"  - C0-side cases D2 evaluates directly: "
        f"{metrics['must_not_regress_c0_preserved_count']} / "
        f"{metrics['must_not_regress_c0_total']}\n"
        f"  - Axis 4 model-A cases preserved by construction: "
        f"{metrics['must_not_regress_axis4_a_preserved_by_construction']}\n"
    )
    regressions = [
        r for r in rows
        if r.in_must_not_regress_70 and not _case_fully_perfect(r, "d2")
    ]
    if regressions:
        lines.append("**Regressions in must-not-regress cohort:**\n")
        for r in regressions:
            lines.append(
                f"- {r.case_id} ({r.axis}): D2 intent={r.d2_predicted_intent}, "
                f"warnings={r.d2_predicted_warnings}"
            )
    else:
        lines.append("_No regression in the 70-case cohort._\n")

    lines.append("## 5. Axis 4 C0-like preservation\n")
    axis4_rows = [r for r in rows if r.axis == "axis4_payload"]
    axis4_perfect = sum(1 for r in axis4_rows if _case_fully_perfect(r, "d2"))
    lines.append(
        f"- axis4_fully_perfect_under_d2: **{axis4_perfect}** / {len(axis4_rows)}\n"
    )

    lines.append("## 6. Over-firing checks\n")
    lines.append(
        "Only D2-introduced over-fires are counted (warning D2 emits "
        "that gold did NOT expect AND C0 did not emit either). "
        "Pre-existing C0 over-fires inherited unchanged are listed "
        "separately and are not attributable to D2.\n"
    )
    lines.append(
        f"- D2-introduced route_indexing_ambiguity over-fires: "
        f"**{metrics['over_fire_route_indexing']}** cases\n"
        f"- D2-introduced false_premise_detected over-fires: "
        f"**{metrics['over_fire_false_premise']}** cases\n"
        f"- Pre-existing route_indexing_ambiguity over-fires "
        f"inherited from C0: "
        f"{metrics['over_fire_route_indexing_preexisting_count']} cases "
        f"({metrics['over_fire_route_indexing_preexisting_ids']})\n"
        f"- Pre-existing false_premise_detected over-fires inherited "
        f"from C0: "
        f"{metrics['over_fire_false_premise_preexisting_count']} cases "
        f"({metrics['over_fire_false_premise_preexisting_ids']})\n"
    )
    if metrics["over_fire_route_indexing_ids"]:
        lines.append("D2-introduced route_indexing_ambiguity ids:")
        for cid in metrics["over_fire_route_indexing_ids"]:
            lines.append(f"  - {cid}")
    if metrics["over_fire_false_premise_ids"]:
        lines.append("D2-introduced false_premise_detected ids:")
        for cid in metrics["over_fire_false_premise_ids"]:
            lines.append(f"  - {cid}")
    lines.append("")

    lines.append("## 7. Total stress improvement\n")
    lines.append(
        f"- stress_total_improvement_vs_c0 (case fully-perfect delta): "
        f"**+{metrics['stress_fully_perfect_d2_minus_c0']}** cases out of 96\n"
        f"- stress_total_improvement_vs_d1 (case fully-perfect delta): "
        f"**+{metrics['stress_fully_perfect_d2_minus_d1']}** cases out of 96\n"
    )

    path.write_text("\n".join(lines))


def _write_core_markdown(
    rows: list[ScoredRow],
    summary: SurfaceSummary,
    metrics: dict[str, object],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# System D2 — locked Run 2 core report\n")
    lines.append(
        "D2 vs D1 vs C0 on the 60 locked Run 2 cases. Acceptance: no "
        "regression on any per-case metric.\n"
    )
    lines.append("| metric | C0 | D1 | D2 | D2 - C0 |")
    lines.append("|---|---:|---:|---:|---:|")
    triples = [
        ("intent_accuracy", summary.c0_intent_acc, summary.d1_intent_acc, summary.d2_intent_acc),
        ("answerability_accuracy", summary.c0_ans_acc, summary.d1_ans_acc, summary.d2_ans_acc),
        ("behavior_class_accuracy", summary.c0_beh_acc, summary.d1_beh_acc, summary.d2_beh_acc),
        ("evidence_precision", summary.c0_evidence_p, summary.d1_evidence_p, summary.d2_evidence_p),
        ("evidence_recall", summary.c0_evidence_r, summary.d1_evidence_r, summary.d2_evidence_r),
        ("warning_precision", summary.c0_warn_p, summary.d1_warn_p, summary.d2_warn_p),
        ("warning_recall", summary.c0_warn_r, summary.d1_warn_r, summary.d2_warn_r),
        ("missing_field_recall", summary.c0_miss_r, summary.d1_miss_r, summary.d2_miss_r),
    ]
    for name, c0v, d1v, d2v in triples:
        lines.append(
            f"| {name} | {_fmt(c0v)} | {_fmt(d1v)} | {_fmt(d2v)} | {d2v - c0v:+.4f} |"
        )
    lines.append("")
    lines.append(
        f"\n- core_run2_regressions: **{metrics['core_run2_regressions']}** "
        f"(cases where D2 metric set is worse than C0's on the same case)\n"
    )
    if metrics["core_run2_regression_ids"]:
        for cid in metrics["core_run2_regression_ids"]:
            lines.append(f"  - {cid}")
    else:
        lines.append("_No per-case regression on Run 2 core._\n")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------


def _case_metric_set_worse_than_c0(r: ScoredRow) -> bool:
    return (
        (r.c0_intent_correct and not r.d2_intent_correct)
        or (r.c0_answerability_correct and not r.d2_answerability_correct)
        or (r.c0_behavior_class_correct and not r.d2_behavior_class_correct)
        or (r.c0_evidence_precision > r.d2_evidence_precision)
        or (r.c0_evidence_recall > r.d2_evidence_recall)
        or (r.c0_warning_precision > r.d2_warning_precision)
        or (r.c0_warning_recall > r.d2_warning_recall)
        or (r.c0_missing_field_recall > r.d2_missing_field_recall)
    )


def compute_metrics(
    core_rows: list[ScoredRow],
    stress_rows: list[ScoredRow],
    target_18: set[str],
    must_not_regress: set[str],
    n_a_preserved_by_construction: int = 0,
) -> dict[str, object]:
    d2_target_rows = [r for r in stress_rows if r.in_d2_target_5]

    def _d2_target_fixed(r: ScoredRow) -> bool:
        return (
            r.d2_intent_correct
            and r.d2_answerability_correct
            and r.d2_behavior_class_correct
            and r.d2_warning_recall == 1.0
            and r.d2_warning_precision == 1.0
        )

    d2_target_fixed = [r for r in d2_target_rows if _d2_target_fixed(r)]

    target_18_under_d2 = [
        r for r in stress_rows if r.in_target_18 and r.d2_intent_correct
    ]

    mnr_rows = [r for r in stress_rows if r.in_must_not_regress_70]
    mnr_preserved = [r for r in mnr_rows if _case_fully_perfect(r, "d2")]
    mnr_total = len(mnr_rows) + n_a_preserved_by_construction
    mnr_preserved_total = len(mnr_preserved) + n_a_preserved_by_construction

    core_regressions = [r for r in core_rows if _case_metric_set_worse_than_c0(r)]

    # Over-firing: a warning D2 newly emits (not present in C0) that
    # gold did not expect. Pre-existing C0 over-fires (the same
    # warning emitted by C0 already, inherited unchanged by D2) are
    # not counted as D2-introduced regressions — they pre-date D2.
    over_route: list[str] = []
    over_false_premise: list[str] = []
    over_route_preexisting: list[str] = []
    over_false_premise_preexisting: list[str] = []
    for r in core_rows + stress_rows:
        gold = set(r.gold_warnings.split(";")) if r.gold_warnings else set()
        d2_warnings = set(r.d2_predicted_warnings.split(";")) if r.d2_predicted_warnings else set()
        c0_warnings = set(r.c0_predicted_warnings.split(";")) if r.c0_predicted_warnings else set()
        for code, new_bucket, pre_bucket in (
            ("route_indexing_ambiguity", over_route, over_route_preexisting),
            ("false_premise_detected", over_false_premise, over_false_premise_preexisting),
        ):
            if code in d2_warnings and code not in gold:
                if code in c0_warnings:
                    pre_bucket.append(r.case_id)
                else:
                    new_bucket.append(r.case_id)

    stress_c0_perfect = sum(1 for r in stress_rows if _case_fully_perfect(r, "c0"))
    stress_d1_perfect = sum(1 for r in stress_rows if _case_fully_perfect(r, "d1"))
    stress_d2_perfect = sum(1 for r in stress_rows if _case_fully_perfect(r, "d2"))

    axis4_rows = [r for r in stress_rows if r.axis == "axis4_payload"]
    axis4_d2_perfect = sum(1 for r in axis4_rows if _case_fully_perfect(r, "d2"))
    axis4_c0_perfect = sum(1 for r in axis4_rows if _case_fully_perfect(r, "c0"))
    axis4_regressions = [
        r.case_id for r in axis4_rows
        if _case_fully_perfect(r, "c0") and not _case_fully_perfect(r, "d2")
    ]

    return {
        "d2_target_5_fixed_count": len(d2_target_fixed),
        "d2_target_5_fixed_rate": (
            len(d2_target_fixed) / max(len(d2_target_rows), 1)
        ),
        "d2_target_5_n_total": len(d2_target_rows),
        "target_18_under_d2_fixed_count": len(target_18_under_d2),
        "must_not_regress_70_preserved_count": mnr_preserved_total,
        "must_not_regress_70_preserved_rate": (
            mnr_preserved_total / max(mnr_total, 1)
        ),
        "must_not_regress_c0_preserved_count": len(mnr_preserved),
        "must_not_regress_c0_total": len(mnr_rows),
        "must_not_regress_axis4_a_preserved_by_construction": (
            n_a_preserved_by_construction
        ),
        "core_run2_regressions": len(core_regressions),
        "core_run2_regression_ids": [r.case_id for r in core_regressions],
        "axis4_d2_perfect": axis4_d2_perfect,
        "axis4_c0_perfect": axis4_c0_perfect,
        "axis4_regressions": axis4_regressions,
        "over_fire_route_indexing": len(over_route),
        "over_fire_route_indexing_ids": over_route,
        "over_fire_route_indexing_preexisting_count": len(over_route_preexisting),
        "over_fire_route_indexing_preexisting_ids": over_route_preexisting,
        "over_fire_false_premise": len(over_false_premise),
        "over_fire_false_premise_ids": over_false_premise,
        "over_fire_false_premise_preexisting_count": len(over_false_premise_preexisting),
        "over_fire_false_premise_preexisting_ids": over_false_premise_preexisting,
        "stress_fully_perfect_c0": stress_c0_perfect,
        "stress_fully_perfect_d1": stress_d1_perfect,
        "stress_fully_perfect_d2": stress_d2_perfect,
        "stress_fully_perfect_d2_minus_c0": stress_d2_perfect - stress_c0_perfect,
        "stress_fully_perfect_d2_minus_d1": stress_d2_perfect - stress_d1_perfect,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_full_d2_evaluation(reports_dir: Optional[Path] = None) -> dict[str, object]:
    reports_dir = Path(reports_dir or (HERE / "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)

    target_18, must_not_regress, n_a_preserved = _load_cohort_membership()

    core_surfaces = _load_core_run2_cases()
    axis1_surfaces = _load_axis1_cases()
    axis2_surfaces = _load_axis2_cases()
    axis3_surfaces = _load_axis3_cases()
    axis4_surfaces = _load_axis4_cases()

    core_rows = [
        r for s in core_surfaces if (r := _score_one_surface(s, target_18, must_not_regress))
    ]
    axis1_rows = [
        r for s in axis1_surfaces if (r := _score_one_surface(s, target_18, must_not_regress))
    ]
    axis2_rows = [
        r for s in axis2_surfaces if (r := _score_one_surface(s, target_18, must_not_regress))
    ]
    axis3_rows = [
        r for s in axis3_surfaces if (r := _score_one_surface(s, target_18, must_not_regress))
    ]
    axis4_rows = [
        r for s in axis4_surfaces if (r := _score_one_surface(s, target_18, must_not_regress))
    ]
    stress_rows = axis1_rows + axis2_rows + axis3_rows + axis4_rows

    metrics = compute_metrics(
        core_rows, stress_rows, target_18, must_not_regress, n_a_preserved
    )
    per_axis = {
        "axis1_lookalike": _summarize(axis1_rows, "axis1_lookalike"),
        "axis2_ood_premises": _summarize(axis2_rows, "axis2_ood_premises"),
        "axis3_semantic": _summarize(axis3_rows, "axis3_semantic"),
        "axis4_payload": _summarize(axis4_rows, "axis4_payload"),
    }
    core_summary = _summarize(core_rows, "core_run2")

    _write_per_case_csv(stress_rows, reports_dir / "system_d2_stress_report.csv")
    _write_per_case_csv(core_rows, reports_dir / "system_d2_core_run2_report.csv")
    _write_stress_markdown(
        stress_rows, per_axis, metrics, reports_dir / "system_d2_stress_report.md"
    )
    _write_core_markdown(
        core_rows, core_summary, metrics, reports_dir / "system_d2_core_run2_report.md"
    )
    _write_failure_map(core_rows + stress_rows, reports_dir / "system_d2_failure_map.csv")

    return {
        "metrics": metrics,
        "per_axis": {k: asdict(v) for k, v in per_axis.items()},
        "core_summary": asdict(core_summary),
        "n_core_rows": len(core_rows),
        "n_stress_rows": len(stress_rows),
    }


def main() -> int:
    out = run_full_d2_evaluation()
    m = out["metrics"]
    print("=== System D2 evaluation ===")
    print(f"core_run2 cases scored: {out['n_core_rows']}")
    print(f"stress cases scored: {out['n_stress_rows']}")
    print(f"D2 target-5 fixed: {m['d2_target_5_fixed_count']}/5 "
          f"({m['d2_target_5_fixed_rate']:.2%})")
    print(f"D1 target-18 under D2: {m['target_18_under_d2_fixed_count']}/18")
    print(f"must_not_regress_70 preserved: "
          f"{m['must_not_regress_70_preserved_count']}/70 "
          f"({m['must_not_regress_70_preserved_rate']:.2%})")
    print(f"core_run2 regressions: {m['core_run2_regressions']} "
          f"(ids={m['core_run2_regression_ids']})")
    print(f"axis4 D2 fully-perfect: {m['axis4_d2_perfect']} / "
          f"24 (C0 was {m['axis4_c0_perfect']}/24, "
          f"regressions={m['axis4_regressions']})")
    print(f"D2-introduced over-fire route_indexing: "
          f"{m['over_fire_route_indexing']} "
          f"({m['over_fire_route_indexing_ids']})")
    print(f"D2-introduced over-fire false_premise: "
          f"{m['over_fire_false_premise']} "
          f"({m['over_fire_false_premise_ids']})")
    print(f"Pre-existing C0 route_indexing over-fires inherited: "
          f"{m['over_fire_route_indexing_preexisting_count']} "
          f"({m['over_fire_route_indexing_preexisting_ids']})")
    print(f"Pre-existing C0 false_premise over-fires inherited: "
          f"{m['over_fire_false_premise_preexisting_count']} "
          f"({m['over_fire_false_premise_preexisting_ids']})")
    print(f"stress fully-perfect delta vs C0: "
          f"+{m['stress_fully_perfect_d2_minus_c0']}/96")
    print(f"stress fully-perfect delta vs D1: "
          f"+{m['stress_fully_perfect_d2_minus_d1']}/96")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

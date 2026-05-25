"""System D1 evaluation harness.

Runs the D1 contract (semantic intent adapter + locked downstream
modules) across:

  - locked Run 2 core (60 cases) — `run2_benchmark_cases.csv`
  - Axis 1 look-alike (24 cases)
  - Axis 2 OOD premises (24 cases)
  - Axis 3 semantic (24 cases)
  - Axis 4 payload C0-like (24 cases)

For each surface the harness also runs the existing C0 contract so
D1 can be compared head-to-head. Outputs land under
`product/evaluation/system_d1/reports/`.

No solver call. No model call. No locked Run 2 file is modified.
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
from product.evaluation.run2_payloads import (
    MaterializedPayload,
    materialize_case_payload,
)
from product.evaluation.run2_scoring import CaseScore, score_case
from product.evaluation.run2_system_c import (
    PredictedContract,
    run_system_c_on_case,
    run_system_c_on_materialized,
)
from product.evaluation.run2_stress.axis1_lookalike.loader import (
    Run2LookalikeCase,
    load_lookalike_cases,
)
from product.evaluation.run2_stress.axis2_ood_premises.loader import (
    Run2OodPremiseCase,
    load_ood_cases,
)
from product.evaluation.run2_stress.axis3_semantic.loader import (
    Run2StressCase as Run2SemanticCase,
    load_stress_cases,
)
from product.evaluation.system_d1.d1_system_c import (
    PredictedContractD1,
    run_system_d1_on_case,
    run_system_d1_on_materialized,
)


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_RUN_ID = "full-run-v1"
AXIS4_CASES_CSV = REPO / "product/evaluation/run2_stress/axis4_payload/cases.csv"
AXIS4_PAYLOAD_DIR = REPO / "product/evaluation/run2_stress/axis4_payload/payloads"

CORE_CASES_PATH = REPO / "product/evaluation/run2_benchmark_cases.csv"

# Failure-map CSV provides the case-level membership in both target_18
# and must_not_regress_70 cohorts.
FAILURE_MAP_CSV = (
    REPO
    / "product/evaluation/run2_stress/analysis/failure_map.csv"
)


# ---------------------------------------------------------------------------
# Cohort membership lookup
# ---------------------------------------------------------------------------


def _load_cohort_membership() -> tuple[set[str], set[str], int]:
    """Returns (target_18_ids, must_not_regress_c0_ids,
    n_axis4_model_side_preserved_by_construction).

    target_18 keys are bare case_ids — case_ids are globally unique
    across the four axis CSVs (A1[DH]-, A2[DH]-, S1[DH]-, R2-NNN).

    The synthesis's 70-case must-not-regress cohort splits as:
      - 64 C0-side cases across axes 1–4 (D1 evaluates these
        directly).
      - 6 axis4-A model-perfect cases (D1 does not run model A, so
        these are preserved by construction — D1 cannot regress
        them because D1's only intervention is the C0-side intent
        classifier).
    """
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
# Surface loaders
# ---------------------------------------------------------------------------


@dataclass
class SurfaceCase:
    """One evaluation row: a Run2Case + metadata about which axis it
    came from. `payload_loader` decides whether to materialize via
    Run 1 generator JSONL (core + axes 1/2/3) or to load a static
    payload from disk (axis 4)."""

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
    return [
        _surface_from_stress(c, "axis2_ood_premises") for c in load_ood_cases()
    ]


def _load_axis3_cases() -> list[SurfaceCase]:
    return [_surface_from_stress(c, "axis3_semantic") for c in load_stress_cases()]


def _load_axis4_cases() -> list[SurfaceCase]:
    """Axis 4 payload cases are pre-built JSONs on disk — no Run 1
    generator lookup."""
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
# Per-surface scored row
# ---------------------------------------------------------------------------


@dataclass
class ScoredRow:
    case_id: str
    axis: str
    split: str
    expected_intent: str
    c0_predicted_intent: str
    d1_predicted_intent: str
    c0_intent_correct: bool
    d1_intent_correct: bool
    c0_answerability_correct: bool
    d1_answerability_correct: bool
    c0_behavior_class_correct: bool
    d1_behavior_class_correct: bool
    c0_evidence_precision: float
    d1_evidence_precision: float
    c0_evidence_recall: float
    d1_evidence_recall: float
    c0_warning_precision: float
    d1_warning_precision: float
    c0_warning_recall: float
    d1_warning_recall: float
    c0_missing_field_recall: float
    d1_missing_field_recall: float
    c0_useful_refusal_correct: Optional[bool]
    d1_useful_refusal_correct: Optional[bool]
    c0_partial_answer_correct: Optional[bool]
    d1_partial_answer_correct: Optional[bool]
    d1_adapter_source: str
    d1_adapter_overridden: bool
    d1_adapter_notes: str
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
        case=case,
        payload=surface.payload,
        generator_record=surface.generator_record,
    )
    pred_d1 = run_system_d1_on_case(
        case=case,
        payload=surface.payload,
        generator_record=surface.generator_record,
    )

    score_c0 = score_case(case, pred_c0)
    score_d1 = score_case(case, pred_d1)

    qf = pred_d1.query_frame
    note_parts: list[str] = []
    if surface.payload_loader_notes:
        note_parts.append("loader=" + " | ".join(surface.payload_loader_notes))

    return ScoredRow(
        case_id=case.case_id,
        axis=surface.axis,
        split=surface.split,
        expected_intent=case.expected_intent,
        c0_predicted_intent=pred_c0.predicted_intent,
        d1_predicted_intent=pred_d1.predicted_intent,
        c0_intent_correct=score_c0.intent_correct,
        d1_intent_correct=score_d1.intent_correct,
        c0_answerability_correct=score_c0.answerability_correct,
        d1_answerability_correct=score_d1.answerability_correct,
        c0_behavior_class_correct=score_c0.behavior_class_correct,
        d1_behavior_class_correct=score_d1.behavior_class_correct,
        c0_evidence_precision=score_c0.evidence_precision,
        d1_evidence_precision=score_d1.evidence_precision,
        c0_evidence_recall=score_c0.evidence_recall,
        d1_evidence_recall=score_d1.evidence_recall,
        c0_warning_precision=score_c0.warning_precision,
        d1_warning_precision=score_d1.warning_precision,
        c0_warning_recall=score_c0.warning_recall,
        d1_warning_recall=score_d1.warning_recall,
        c0_missing_field_recall=score_c0.missing_field_recall,
        d1_missing_field_recall=score_d1.missing_field_recall,
        c0_useful_refusal_correct=score_c0.useful_refusal_correct,
        d1_useful_refusal_correct=score_d1.useful_refusal_correct,
        c0_partial_answer_correct=score_c0.partial_answer_correct,
        d1_partial_answer_correct=score_d1.partial_answer_correct,
        d1_adapter_source=(qf.source if qf else "c0"),
        d1_adapter_overridden=bool(qf.overridden) if qf else False,
        d1_adapter_notes="; ".join(qf.adapter_notes) if qf and qf.adapter_notes else "",
        in_target_18=(case.case_id in target_18 and surface.axis != "core_run2"),
        in_must_not_regress_70=(
            case.case_id in must_not_regress and surface.axis != "core_run2"
        ),
        materialization_status=surface.materialization_status,
        notes=" ; ".join(note_parts),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


_FIELDS = [
    "case_id", "axis", "split", "expected_intent",
    "c0_predicted_intent", "d1_predicted_intent",
    "c0_intent_correct", "d1_intent_correct",
    "c0_answerability_correct", "d1_answerability_correct",
    "c0_behavior_class_correct", "d1_behavior_class_correct",
    "c0_evidence_precision", "d1_evidence_precision",
    "c0_evidence_recall", "d1_evidence_recall",
    "c0_warning_precision", "d1_warning_precision",
    "c0_warning_recall", "d1_warning_recall",
    "c0_missing_field_recall", "d1_missing_field_recall",
    "c0_useful_refusal_correct", "d1_useful_refusal_correct",
    "c0_partial_answer_correct", "d1_partial_answer_correct",
    "d1_adapter_source", "d1_adapter_overridden", "d1_adapter_notes",
    "in_target_18", "in_must_not_regress_70",
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
                "c0_intent_correct", "d1_intent_correct",
                "c0_answerability_correct", "d1_answerability_correct",
                "c0_behavior_class_correct", "d1_behavior_class_correct",
                "c0_useful_refusal_correct", "d1_useful_refusal_correct",
                "c0_partial_answer_correct", "d1_partial_answer_correct",
                "in_target_18", "in_must_not_regress_70", "d1_adapter_overridden",
            ):
                d[k] = _bool_to_str(d[k])
            for k in (
                "c0_evidence_precision", "d1_evidence_precision",
                "c0_evidence_recall", "d1_evidence_recall",
                "c0_warning_precision", "d1_warning_precision",
                "c0_warning_recall", "d1_warning_recall",
                "c0_missing_field_recall", "d1_missing_field_recall",
            ):
                d[k] = f"{d[k]:.4f}"
            w.writerow(d)


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
    c0_ans_acc: float
    d1_ans_acc: float
    c0_beh_acc: float
    d1_beh_acc: float
    c0_evidence_p: float
    d1_evidence_p: float
    c0_evidence_r: float
    d1_evidence_r: float
    c0_warn_p: float
    d1_warn_p: float
    c0_warn_r: float
    d1_warn_r: float
    c0_miss_r: float
    d1_miss_r: float


def _summarize(rows: list[ScoredRow], name: str) -> SurfaceSummary:
    return SurfaceSummary(
        name=name,
        n=len(rows),
        c0_intent_acc=_fraction([r.c0_intent_correct for r in rows]),
        d1_intent_acc=_fraction([r.d1_intent_correct for r in rows]),
        c0_ans_acc=_fraction([r.c0_answerability_correct for r in rows]),
        d1_ans_acc=_fraction([r.d1_answerability_correct for r in rows]),
        c0_beh_acc=_fraction([r.c0_behavior_class_correct for r in rows]),
        d1_beh_acc=_fraction([r.d1_behavior_class_correct for r in rows]),
        c0_evidence_p=_mean([r.c0_evidence_precision for r in rows]),
        d1_evidence_p=_mean([r.d1_evidence_precision for r in rows]),
        c0_evidence_r=_mean([r.c0_evidence_recall for r in rows]),
        d1_evidence_r=_mean([r.d1_evidence_recall for r in rows]),
        c0_warn_p=_mean([r.c0_warning_precision for r in rows]),
        d1_warn_p=_mean([r.d1_warning_precision for r in rows]),
        c0_warn_r=_mean([r.c0_warning_recall for r in rows]),
        d1_warn_r=_mean([r.d1_warning_recall for r in rows]),
        c0_miss_r=_mean([r.c0_missing_field_recall for r in rows]),
        d1_miss_r=_mean([r.d1_missing_field_recall for r in rows]),
    )


def _case_fully_perfect(r: ScoredRow, system: str) -> bool:
    """A case is "fully perfect" for a system when every C0-or-D1
    metric is at its max value."""
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


# ---------------------------------------------------------------------------
# Failure map for D1
# ---------------------------------------------------------------------------


def _d1_category(r: ScoredRow) -> str:
    """Re-bucket D1 outcomes using the same taxonomy as the cross-axis
    synthesis (`failure_map.csv`), so the D1 failure_map.csv is
    directly comparable."""
    if r.axis == "core_run2":
        if _case_fully_perfect(r, "d1"):
            return "must_not_regress_guard_protected"
        return "core_run2_regression"
    if not r.d1_intent_correct:
        if r.d1_predicted_intent == "unknown":
            return "system_d_addressable_intent"
        return "system_d_addressable_intent"
    # intent correct, downstream may still mismatch (the
    # downstream artifact category from the synthesis).
    if _case_fully_perfect(r, "d1"):
        return "must_not_regress_guard_protected"
    return "downstream_evidence_artifact"


def _write_failure_map(rows: list[ScoredRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow([
            "case_id", "axis", "split", "expected_intent",
            "d1_predicted_intent", "d1_intent_correct",
            "d1_behavior_class_correct", "d1_category",
            "in_target_18", "in_must_not_regress_70",
            "d1_adapter_source", "d1_adapter_overridden",
        ])
        for r in rows:
            w.writerow([
                r.case_id, r.axis, r.split, r.expected_intent,
                r.d1_predicted_intent,
                int(r.d1_intent_correct),
                int(r.d1_behavior_class_correct),
                _d1_category(r),
                int(r.in_target_18),
                int(r.in_must_not_regress_70),
                r.d1_adapter_source,
                int(r.d1_adapter_overridden),
            ])


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


def _fmt_pct(x: float) -> str:
    return f"{x:.3f}"


def _stress_summary_table(per_axis: dict[str, SurfaceSummary]) -> list[str]:
    lines = [
        "| axis | n | C0 intent | D1 intent | C0 ans | D1 ans | C0 beh | D1 beh |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for axis, s in per_axis.items():
        lines.append(
            f"| {axis} | {s.n} | {_fmt_pct(s.c0_intent_acc)} | {_fmt_pct(s.d1_intent_acc)} | "
            f"{_fmt_pct(s.c0_ans_acc)} | {_fmt_pct(s.d1_ans_acc)} | "
            f"{_fmt_pct(s.c0_beh_acc)} | {_fmt_pct(s.d1_beh_acc)} |"
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
    lines.append("# System D1 — stress evaluation report\n")
    lines.append(
        "D1 (semantic intent adapter + locked downstream contract) "
        "vs C0 (locked classifier + locked downstream contract) across "
        "the four R2-S axes' C0-style surfaces (24 cases each).\n"
    )
    lines.append("## 1. Per-axis aggregate\n")
    lines.extend(_stress_summary_table(per_axis))
    lines.append("")

    lines.append("## 2. Target-18 cohort\n")
    lines.append(
        f"- target_18_fixed_count: **{metrics['target_18_fixed_count']}** / 18  \n"
        f"- target_18_fixed_rate: **{_fmt_pct(metrics['target_18_fixed_rate'])}**\n"
    )
    lines.append("| case_id | axis | expected | C0 | D1 | fixed |")
    lines.append("|---|---|---|---|---|:-:|")
    for r in rows:
        if not r.in_target_18:
            continue
        fixed = "✓" if r.d1_intent_correct else "✗"
        lines.append(
            f"| {r.case_id} | {r.axis} | {r.expected_intent} | "
            f"{r.c0_predicted_intent} | {r.d1_predicted_intent} | {fixed} |"
        )
    lines.append("")

    lines.append("## 3. Must-not-regress 70-cohort\n")
    lines.append(
        f"- must_not_regress_70_preserved_count: **{metrics['must_not_regress_70_preserved_count']}** / 70  \n"
        f"- must_not_regress_70_preserved_rate: **{_fmt_pct(metrics['must_not_regress_70_preserved_rate'])}**\n"
    )
    lines.append(
        f"  - C0-side cases D1 evaluates directly: "
        f"{metrics['must_not_regress_c0_preserved_count']} / "
        f"{metrics['must_not_regress_c0_total']}\n"
        f"  - Axis 4 model-A cases preserved by construction (D1 does "
        f"not run model A): "
        f"{metrics['must_not_regress_axis4_a_preserved_by_construction']}\n"
    )
    # If any regression occurred, list it explicitly so the
    # acceptance gate is visible.
    regressions = [
        r for r in rows
        if r.in_must_not_regress_70 and not _case_fully_perfect(r, "d1")
    ]
    if regressions:
        lines.append("**Regressions detected:**\n")
        lines.append("| case_id | axis | C0 intent | D1 intent | C0 perf | D1 perf |")
        lines.append("|---|---|---|---|:-:|:-:|")
        for r in regressions:
            c0p = "✓" if _case_fully_perfect(r, "c0") else "✗"
            d1p = "✓" if _case_fully_perfect(r, "d1") else "✗"
            lines.append(
                f"| {r.case_id} | {r.axis} | {r.c0_predicted_intent} | "
                f"{r.d1_predicted_intent} | {c0p} | {d1p} |"
            )
        lines.append("")
    else:
        lines.append("_No regression in the 70-case cohort._\n")

    lines.append("## 4. Adapter call accounting\n")
    lines.append(
        f"- adapter_invocation_count: **{metrics['adapter_invocation_count']}**  \n"
        f"- adapter_override_count: **{metrics['adapter_override_count']}**  \n"
        f"- adapter_fallback_count: **{metrics['adapter_fallback_count']}**\n"
    )
    src_counts = metrics["override_source_counts"]
    lines.append("Override source distribution (D1 intent != C0 intent):\n")
    lines.append("| source | n |")
    lines.append("|---|---:|")
    for k in sorted(src_counts.keys()):
        lines.append(f"| {k} | {src_counts[k]} |")
    lines.append("")

    lines.append("## 5. Total improvement vs C0 (stress surface only)\n")
    lines.append(
        f"- stress_total_improvement_vs_c0 (intent-correct delta): "
        f"**+{metrics['stress_total_improvement_vs_c0']}** cases out of 96\n"
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
    lines.append("# System D1 — locked Run 2 core report\n")
    lines.append(
        "D1 vs C0 on the 60 locked Run 2 cases. Acceptance: no "
        "regression on intent/answerability/behavior_class and no new "
        "evidence/warning artifact.\n"
    )
    lines.append("| metric | C0 | D1 | delta |")
    lines.append("|---|---:|---:|---:|")
    pairs = [
        ("intent_accuracy", summary.c0_intent_acc, summary.d1_intent_acc),
        ("answerability_accuracy", summary.c0_ans_acc, summary.d1_ans_acc),
        ("behavior_class_accuracy", summary.c0_beh_acc, summary.d1_beh_acc),
        ("evidence_precision", summary.c0_evidence_p, summary.d1_evidence_p),
        ("evidence_recall", summary.c0_evidence_r, summary.d1_evidence_r),
        ("warning_precision", summary.c0_warn_p, summary.d1_warn_p),
        ("warning_recall", summary.c0_warn_r, summary.d1_warn_r),
        ("missing_field_recall", summary.c0_miss_r, summary.d1_miss_r),
    ]
    for name, c0v, d1v in pairs:
        lines.append(
            f"| {name} | {_fmt_pct(c0v)} | {_fmt_pct(d1v)} | "
            f"{d1v - c0v:+.4f} |"
        )
    lines.append("")
    lines.append(
        f"\n- core_run2_regressions: **{metrics['core_run2_regressions']}** "
        f"(cases where D1 metric set is worse than C0's on the same case)\n"
    )
    regressions = [
        r for r in rows
        if (
            (r.c0_intent_correct and not r.d1_intent_correct)
            or (r.c0_answerability_correct and not r.d1_answerability_correct)
            or (r.c0_behavior_class_correct and not r.d1_behavior_class_correct)
            or (r.c0_evidence_precision > r.d1_evidence_precision)
            or (r.c0_evidence_recall > r.d1_evidence_recall)
            or (r.c0_warning_precision > r.d1_warning_precision)
            or (r.c0_warning_recall > r.d1_warning_recall)
            or (r.c0_missing_field_recall > r.d1_missing_field_recall)
        )
    ]
    if regressions:
        lines.append("**Per-case regressions:**\n")
        lines.append(
            "| case_id | C0 intent | D1 intent | C0 beh | D1 beh | adapter_source |"
        )
        lines.append("|---|---|---|:-:|:-:|---|")
        for r in regressions:
            lines.append(
                f"| {r.case_id} | {r.c0_predicted_intent} | "
                f"{r.d1_predicted_intent} | "
                f"{'✓' if r.c0_behavior_class_correct else '✗'} | "
                f"{'✓' if r.d1_behavior_class_correct else '✗'} | "
                f"{r.d1_adapter_source} |"
            )
    else:
        lines.append("_No per-case regression on Run 2 core._\n")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    core_rows: list[ScoredRow],
    stress_rows: list[ScoredRow],
    target_18: set[str],
    must_not_regress: set[str],
    n_a_preserved_by_construction: int = 0,
) -> dict[str, object]:
    target_rows = [r for r in stress_rows if r.in_target_18]
    target_fixed = [r for r in target_rows if r.d1_intent_correct]

    mnr_rows = [r for r in stress_rows if r.in_must_not_regress_70]
    mnr_preserved = [r for r in mnr_rows if _case_fully_perfect(r, "d1")]
    mnr_c0_count = len(mnr_rows)
    mnr_total_count = mnr_c0_count + n_a_preserved_by_construction
    mnr_preserved_total = len(mnr_preserved) + n_a_preserved_by_construction

    core_regressions = [
        r for r in core_rows
        if _case_fully_perfect(r, "c0") and not _case_fully_perfect(r, "d1")
    ]

    invocations = sum(
        1 for r in core_rows + stress_rows if r.d1_adapter_source != "c0"
    )
    overrides = sum(
        1 for r in core_rows + stress_rows if r.d1_adapter_overridden
    )
    fallbacks = invocations - overrides

    override_sources: Counter[str] = Counter()
    for r in core_rows + stress_rows:
        if r.d1_adapter_overridden:
            override_sources[r.d1_adapter_source] += 1

    stress_c0_correct = sum(1 for r in stress_rows if r.c0_intent_correct)
    stress_d1_correct = sum(1 for r in stress_rows if r.d1_intent_correct)

    return {
        "target_18_fixed_count": len(target_fixed),
        "target_18_fixed_rate": (
            len(target_fixed) / max(len(target_rows), 1)
        ),
        "must_not_regress_70_preserved_count": mnr_preserved_total,
        "must_not_regress_70_preserved_rate": (
            mnr_preserved_total / max(mnr_total_count, 1)
        ),
        "must_not_regress_c0_preserved_count": len(mnr_preserved),
        "must_not_regress_c0_total": mnr_c0_count,
        "must_not_regress_axis4_a_preserved_by_construction": (
            n_a_preserved_by_construction
        ),
        "core_run2_regressions": len(core_regressions),
        "core_run2_regression_ids": [r.case_id for r in core_regressions],
        "stress_total_improvement_vs_c0": stress_d1_correct - stress_c0_correct,
        "adapter_invocation_count": invocations,
        "adapter_override_count": overrides,
        "adapter_fallback_count": fallbacks,
        "override_source_counts": dict(override_sources),
        "stress_n_total": len(stress_rows),
        "target_18_n_total": len(target_rows),
        "must_not_regress_70_n_total": mnr_total_count,
        "core_n_total": len(core_rows),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_full_d1_evaluation(reports_dir: Optional[Path] = None) -> dict[str, object]:
    """Run D1 across core + 4 axes, emit reports, return metrics."""
    reports_dir = Path(reports_dir or (HERE / "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)

    target_18, must_not_regress, n_a_preserved = _load_cohort_membership()

    # Materialize / load every surface.
    core_surfaces = _load_core_run2_cases()
    axis1_surfaces = _load_axis1_cases()
    axis2_surfaces = _load_axis2_cases()
    axis3_surfaces = _load_axis3_cases()
    axis4_surfaces = _load_axis4_cases()

    # Score
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

    # Aggregate
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

    # Emit reports
    _write_per_case_csv(stress_rows, reports_dir / "system_d1_stress_report.csv")
    _write_per_case_csv(core_rows, reports_dir / "system_d1_core_run2_report.csv")
    _write_stress_markdown(
        stress_rows, per_axis, metrics, reports_dir / "system_d1_stress_report.md"
    )
    _write_core_markdown(
        core_rows, core_summary, metrics, reports_dir / "system_d1_core_run2_report.md"
    )
    _write_failure_map(core_rows + stress_rows, reports_dir / "system_d1_failure_map.csv")

    return {
        "metrics": metrics,
        "per_axis": {k: asdict(v) for k, v in per_axis.items()},
        "core_summary": asdict(core_summary),
        "n_core_rows": len(core_rows),
        "n_stress_rows": len(stress_rows),
    }


def main() -> int:
    out = run_full_d1_evaluation()
    m = out["metrics"]
    print("=== System D1 evaluation ===")
    print(f"core_run2 cases scored: {out['n_core_rows']}")
    print(f"stress cases scored: {out['n_stress_rows']}")
    print(f"target_18 fixed: {m['target_18_fixed_count']}/18 "
          f"({m['target_18_fixed_rate']:.2%})")
    print(f"must_not_regress_70 preserved: "
          f"{m['must_not_regress_70_preserved_count']}/70 "
          f"({m['must_not_regress_70_preserved_rate']:.2%})")
    print(f"core_run2 regressions: {m['core_run2_regressions']} "
          f"(ids={m['core_run2_regression_ids']})")
    print(f"stress total improvement (intent_correct delta): "
          f"+{m['stress_total_improvement_vs_c0']}/96")
    print(f"adapter invocations={m['adapter_invocation_count']} "
          f"overrides={m['adapter_override_count']} "
          f"fallbacks={m['adapter_fallback_count']}")
    print(f"override sources={m['override_source_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

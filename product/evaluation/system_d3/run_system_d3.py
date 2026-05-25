"""System D3 evaluation harness.

Runs the D3 contract (D1 intent + D2 answerability/warning +
D3 causal-unsupported warning) across the same five surfaces as
D1/D2. The five Axis-2 Band-4 causal cases are graded twice:

  - against the original v1 gold (to confirm the v1 baseline
    behaviour is preserved — D3 should score the same as D2 under
    v1 because the new warning is *not* expected by v1 gold and
    the case is therefore reported as a v1 warning-precision
    deficit; D3 does not benefit from v1 grading);
  - against the D3 v2 overlay gold (to score the causal warning's
    inclusion as a fix).

For every non-overlay case, D3 reuses the standard scorer with
the original gold.

No solver call. No model call. No locked Run 2 file is modified.
The original Axis 2 `cases.csv` is byte-identical to its
committed version under D3.
"""
from __future__ import annotations

import csv
import json
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
from product.evaluation.system_d3.d3_overlay import (
    case_with_overlay,
    load_overlay,
    overlay_case_ids,
)
from product.evaluation.system_d3.d3_system_c import run_system_d3_on_case


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_RUN_ID = "full-run-v1"
AXIS4_CASES_CSV = REPO / "product/evaluation/run2_stress/axis4_payload/cases.csv"
AXIS4_PAYLOAD_DIR = REPO / "product/evaluation/run2_stress/axis4_payload/payloads"
CORE_CASES_PATH = REPO / "product/evaluation/run2_benchmark_cases.csv"
FAILURE_MAP_CSV = (
    REPO / "product/evaluation/run2_stress/analysis/failure_map.csv"
)


# D3 explicit target cases — the five Axis-2 Band-4
# causal-explanation schema_gap cases.
D3_TARGET_CASES = frozenset({
    "A2D-10",
    "A2D-11",
    "A2D-12",
    "A2H-11",
    "A2H-12",
})

# D2 target cases — re-used to verify D3 preserves D2's fixes.
D2_TARGET_CASES = frozenset({
    "A2D-03",
    "A2H-02",
    "S1D-08",
    "S1D-09",
    "S1H-10",
})


# ---------------------------------------------------------------------------
# Cohort membership lookup (shared shape with D1/D2)
# ---------------------------------------------------------------------------


def _load_cohort_membership() -> tuple[set[str], set[str], int]:
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
                case_id=case.case_id, axis="core_run2", split="core",
                run2_case=case, payload=mat.payload,
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
        case_id=case_obj.case_id, axis=axis, split=case_obj.split,
        run2_case=run2_case, payload=mat.payload,
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
                    case_id=case.case_id, axis="axis4_payload",
                    split=row["split"], run2_case=case, payload=payload,
                    generator_record=None,
                    materialization_status="materialized",
                    payload_loader_notes=[f"static_payload={cell_id}"],
                )
            )
    return out


# ---------------------------------------------------------------------------
# Per-surface scored row (C0 / D1 / D2 / D3, with v1 + v2 grading
# for the overlay subset)
# ---------------------------------------------------------------------------


@dataclass
class ScoredRow:
    case_id: str
    axis: str
    split: str
    expected_intent_v1: str
    expected_warnings_v1: str

    c0_predicted_intent: str
    d1_predicted_intent: str
    d2_predicted_intent: str
    d3_predicted_intent: str

    c0_predicted_warnings: str
    d1_predicted_warnings: str
    d2_predicted_warnings: str
    d3_predicted_warnings: str

    c0_intent_correct: bool
    d1_intent_correct: bool
    d2_intent_correct: bool
    d3_intent_correct: bool

    c0_behavior_class_correct: bool
    d1_behavior_class_correct: bool
    d2_behavior_class_correct: bool
    d3_behavior_class_correct: bool

    c0_warning_precision: float
    d1_warning_precision: float
    d2_warning_precision: float
    d3_warning_precision: float
    c0_warning_recall: float
    d1_warning_recall: float
    d2_warning_recall: float
    d3_warning_recall: float

    # Overlay (v2) grading — only populated for the 5 schema-gap
    # cases. Empty strings for non-overlay cases keep the CSV
    # legible.
    in_d3_overlay: bool
    d3_v2_intent_correct: Optional[bool]
    d3_v2_behavior_class_correct: Optional[bool]
    d3_v2_warning_precision: Optional[float]
    d3_v2_warning_recall: Optional[float]

    in_d2_target_5: bool
    in_target_18: bool
    in_must_not_regress_70: bool
    materialization_status: str
    notes: str


def _bool_to_str(v) -> str:
    if v is None:
        return ""
    return "true" if v else "false"


def _maybe_str(v, fmt: Optional[str] = None) -> str:
    if v is None:
        return ""
    return fmt.format(v) if fmt else str(v)


def _score_one_surface(
    surface: SurfaceCase,
    target_18: set[str],
    must_not_regress: set[str],
    overlay: dict[str, dict],
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
    pred_d3 = run_system_d3_on_case(
        case=case, payload=surface.payload, generator_record=surface.generator_record
    )

    # v1 grading — everyone is graded against the case's original
    # gold (the version that lives in the locked CSVs). D3 is
    # *not* expected to win on v1 because the new causal warning
    # is not in v1 gold; the v1 numbers exist so we can prove D3
    # does not introduce silent regressions.
    score_c0 = score_case(case, pred_c0)
    score_d1 = score_case(case, pred_d1)
    score_d2 = score_case(case, pred_d2)
    score_d3_v1 = score_case(case, pred_d3)

    # v2 grading — only meaningful for overlay cases.
    v2_overlay = overlay.get(case.case_id)
    if v2_overlay is not None:
        v2_case = case_with_overlay(case, v2_overlay)
        score_d3_v2 = score_case(v2_case, pred_d3)
        d3_v2_intent_correct = score_d3_v2.intent_correct
        d3_v2_behavior_class_correct = score_d3_v2.behavior_class_correct
        d3_v2_warning_precision = score_d3_v2.warning_precision
        d3_v2_warning_recall = score_d3_v2.warning_recall
        in_d3_overlay = True
    else:
        d3_v2_intent_correct = None
        d3_v2_behavior_class_correct = None
        d3_v2_warning_precision = None
        d3_v2_warning_recall = None
        in_d3_overlay = False

    notes_parts: list[str] = []
    if surface.payload_loader_notes:
        notes_parts.append("loader=" + " | ".join(surface.payload_loader_notes))

    return ScoredRow(
        case_id=case.case_id,
        axis=surface.axis,
        split=surface.split,
        expected_intent_v1=case.expected_intent,
        expected_warnings_v1=";".join(case.expected_warnings),
        c0_predicted_intent=pred_c0.predicted_intent,
        d1_predicted_intent=pred_d1.predicted_intent,
        d2_predicted_intent=pred_d2.predicted_intent,
        d3_predicted_intent=pred_d3.predicted_intent,
        c0_predicted_warnings=";".join(pred_c0.predicted_warnings),
        d1_predicted_warnings=";".join(pred_d1.predicted_warnings),
        d2_predicted_warnings=";".join(pred_d2.predicted_warnings),
        d3_predicted_warnings=";".join(pred_d3.predicted_warnings),
        c0_intent_correct=score_c0.intent_correct,
        d1_intent_correct=score_d1.intent_correct,
        d2_intent_correct=score_d2.intent_correct,
        d3_intent_correct=score_d3_v1.intent_correct,
        c0_behavior_class_correct=score_c0.behavior_class_correct,
        d1_behavior_class_correct=score_d1.behavior_class_correct,
        d2_behavior_class_correct=score_d2.behavior_class_correct,
        d3_behavior_class_correct=score_d3_v1.behavior_class_correct,
        c0_warning_precision=score_c0.warning_precision,
        d1_warning_precision=score_d1.warning_precision,
        d2_warning_precision=score_d2.warning_precision,
        d3_warning_precision=score_d3_v1.warning_precision,
        c0_warning_recall=score_c0.warning_recall,
        d1_warning_recall=score_d1.warning_recall,
        d2_warning_recall=score_d2.warning_recall,
        d3_warning_recall=score_d3_v1.warning_recall,
        in_d3_overlay=in_d3_overlay,
        d3_v2_intent_correct=d3_v2_intent_correct,
        d3_v2_behavior_class_correct=d3_v2_behavior_class_correct,
        d3_v2_warning_precision=d3_v2_warning_precision,
        d3_v2_warning_recall=d3_v2_warning_recall,
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
    "case_id", "axis", "split",
    "expected_intent_v1", "expected_warnings_v1",
    "c0_predicted_intent", "d1_predicted_intent", "d2_predicted_intent", "d3_predicted_intent",
    "c0_predicted_warnings", "d1_predicted_warnings", "d2_predicted_warnings", "d3_predicted_warnings",
    "c0_intent_correct", "d1_intent_correct", "d2_intent_correct", "d3_intent_correct",
    "c0_behavior_class_correct", "d1_behavior_class_correct", "d2_behavior_class_correct", "d3_behavior_class_correct",
    "c0_warning_precision", "d1_warning_precision", "d2_warning_precision", "d3_warning_precision",
    "c0_warning_recall", "d1_warning_recall", "d2_warning_recall", "d3_warning_recall",
    "in_d3_overlay",
    "d3_v2_intent_correct", "d3_v2_behavior_class_correct",
    "d3_v2_warning_precision", "d3_v2_warning_recall",
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
                "c0_intent_correct", "d1_intent_correct", "d2_intent_correct", "d3_intent_correct",
                "c0_behavior_class_correct", "d1_behavior_class_correct",
                "d2_behavior_class_correct", "d3_behavior_class_correct",
                "in_d3_overlay", "in_d2_target_5", "in_target_18", "in_must_not_regress_70",
                "d3_v2_intent_correct", "d3_v2_behavior_class_correct",
            ):
                d[k] = _bool_to_str(d[k])
            for k in (
                "c0_warning_precision", "d1_warning_precision",
                "d2_warning_precision", "d3_warning_precision",
                "c0_warning_recall", "d1_warning_recall",
                "d2_warning_recall", "d3_warning_recall",
            ):
                d[k] = f"{d[k]:.4f}"
            for k in ("d3_v2_warning_precision", "d3_v2_warning_recall"):
                d[k] = "" if d[k] is None else f"{d[k]:.4f}"
            w.writerow(d)


def _fraction(values: list[bool]) -> float:
    if not values:
        return 1.0
    return sum(1 for v in values if v) / len(values)


# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------


def _v2_fix(r: ScoredRow) -> bool:
    """Per-case D3 v2 success criterion for the overlay 5: intent
    correct, warning_recall == 1.0, warning_precision == 1.0,
    behavior_class correct."""
    return bool(
        r.d3_v2_intent_correct
        and r.d3_v2_behavior_class_correct
        and r.d3_v2_warning_precision == 1.0
        and r.d3_v2_warning_recall == 1.0
    )


def _d2_perfect_v1(r: ScoredRow) -> bool:
    return (
        r.d2_intent_correct
        and r.d2_behavior_class_correct
        and r.d2_warning_precision == 1.0
        and r.d2_warning_recall == 1.0
    )


def _d3_perfect_v1(r: ScoredRow) -> bool:
    return (
        r.d3_intent_correct
        and r.d3_behavior_class_correct
        and r.d3_warning_precision == 1.0
        and r.d3_warning_recall == 1.0
    )


def _c0_perfect_v1(r: ScoredRow) -> bool:
    return (
        r.c0_intent_correct
        and r.c0_behavior_class_correct
        and r.c0_warning_precision == 1.0
        and r.c0_warning_recall == 1.0
    )


def _detected_causal_emission_off_target(r: ScoredRow) -> bool:
    """Did D3 emit `causal_mechanism_unsupported` on a case that
    is NOT in the overlay? If so, the overlay does not expect the
    warning and D3's emission is a potential over-fire."""
    if r.in_d3_overlay:
        return False
    emitted = set(r.d3_predicted_warnings.split(";")) if r.d3_predicted_warnings else set()
    return "causal_mechanism_unsupported" in emitted


def compute_metrics(
    core_rows: list[ScoredRow],
    stress_rows: list[ScoredRow],
    target_18: set[str],
    must_not_regress: set[str],
    n_a_preserved_by_construction: int = 0,
) -> dict[str, object]:
    overlay_rows = [r for r in stress_rows if r.in_d3_overlay]
    d3_v2_fixed = [r for r in overlay_rows if _v2_fix(r)]

    d2_target_rows = [r for r in stress_rows if r.in_d2_target_5]
    d2_target_preserved_under_d3 = [
        r for r in d2_target_rows if _d3_perfect_v1(r)
    ]

    target_18_under_d3 = [
        r for r in stress_rows if r.in_target_18 and r.d3_intent_correct
    ]

    mnr_rows = [r for r in stress_rows if r.in_must_not_regress_70]
    mnr_preserved = [r for r in mnr_rows if _d3_perfect_v1(r)]
    mnr_total = len(mnr_rows) + n_a_preserved_by_construction
    mnr_preserved_total = len(mnr_preserved) + n_a_preserved_by_construction

    # Core regression: D3 metric set worse than C0 on the same case.
    core_regressions = [
        r for r in core_rows
        if (
            (r.c0_intent_correct and not r.d3_intent_correct)
            or (r.c0_behavior_class_correct and not r.d3_behavior_class_correct)
            or (r.c0_warning_precision > r.d3_warning_precision)
            or (r.c0_warning_recall > r.d3_warning_recall)
        )
    ]

    axis4_rows = [r for r in stress_rows if r.axis == "axis4_payload"]
    axis4_d3_perfect = sum(1 for r in axis4_rows if _d3_perfect_v1(r))
    axis4_regressions = [
        r.case_id for r in axis4_rows
        if _c0_perfect_v1(r) and not _d3_perfect_v1(r)
    ]

    # Off-target causal emissions (D3 emitted `causal_mechanism_unsupported`
    # on a case outside the overlay).
    off_target_causal = [
        r.case_id for r in core_rows + stress_rows
        if _detected_causal_emission_off_target(r)
    ]

    return {
        "d3_target_5_fixed_count": len(d3_v2_fixed),
        "d3_target_5_fixed_rate": len(d3_v2_fixed) / max(len(overlay_rows), 1),
        "d3_target_5_n_total": len(overlay_rows),
        "d2_target_5_preserved_under_d3_count": len(d2_target_preserved_under_d3),
        "target_18_under_d3_fixed_count": len(target_18_under_d3),
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
        "axis4_d3_perfect": axis4_d3_perfect,
        "axis4_regressions": axis4_regressions,
        "off_target_causal_emission_count": len(off_target_causal),
        "off_target_causal_emission_ids": off_target_causal,
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def _write_stress_markdown(
    rows: list[ScoredRow],
    metrics: dict[str, object],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# System D3 — stress evaluation report\n")
    lines.append(
        "D3 (D1 intent + D2 answerability/warning + D3 "
        "causal-unsupported warning) vs D2 vs D1 vs C0 across the "
        "four R2-S axes' C0-style surfaces.\n"
    )

    lines.append("## 1. D3 v2 overlay cohort (5 schema-gap cases)\n")
    lines.append(
        f"- d3_target_5_fixed_count (against v2 overlay gold): "
        f"**{metrics['d3_target_5_fixed_count']} / 5**  \n"
        f"- d3_target_5_fixed_rate: "
        f"**{_fmt(metrics['d3_target_5_fixed_rate'])}**\n"
    )
    lines.append(
        "| case_id | D2 (v1 gold) | D3 (v1 gold) | D3 (v2 overlay gold) | D3 emitted warnings |"
    )
    lines.append("|---|:-:|:-:|:-:|---|")
    for r in rows:
        if not r.in_d3_overlay:
            continue
        d2p = "✓" if _d2_perfect_v1(r) else "✗"
        d3v1 = "✓" if _d3_perfect_v1(r) else "✗"
        d3v2 = "✓" if _v2_fix(r) else "✗"
        lines.append(
            f"| {r.case_id} | {d2p} | {d3v1} | {d3v2} | {r.d3_predicted_warnings} |"
        )
    lines.append("")

    lines.append("## 2. D2 target-5 preserved under D3\n")
    lines.append(
        f"- d2_target_5_preserved_under_d3_count: "
        f"**{metrics['d2_target_5_preserved_under_d3_count']} / 5**\n"
    )

    lines.append("## 3. D1 target-18 preserved under D3\n")
    lines.append(
        f"- target_18_under_d3_fixed_count: "
        f"**{metrics['target_18_under_d3_fixed_count']} / 18**\n"
    )

    lines.append("## 4. Must-not-regress 70-cohort\n")
    lines.append(
        f"- must_not_regress_70_preserved_count: "
        f"**{metrics['must_not_regress_70_preserved_count']} / 70**\n"
        f"  - C0-side cases D3 evaluates directly: "
        f"{metrics['must_not_regress_c0_preserved_count']} / "
        f"{metrics['must_not_regress_c0_total']}\n"
        f"  - Axis 4 model-A cases preserved by construction: "
        f"{metrics['must_not_regress_axis4_a_preserved_by_construction']}\n"
    )

    lines.append("## 5. Axis 4 C0-like preservation\n")
    lines.append(
        f"- axis4_d3_perfect: **{metrics['axis4_d3_perfect']} / 24**\n"
        f"- axis4_regressions: {metrics['axis4_regressions']}\n"
    )

    lines.append("## 6. Off-target causal emissions\n")
    lines.append(
        "D3's causal-warning detector is conservative; this "
        "section checks how many non-overlay cases D3 emitted "
        "`causal_mechanism_unsupported` on. Those emissions are "
        "potential over-fires under v1 grading.\n"
    )
    lines.append(
        f"- off_target_causal_emission_count: "
        f"**{metrics['off_target_causal_emission_count']}**\n"
    )
    if metrics["off_target_causal_emission_ids"]:
        for cid in metrics["off_target_causal_emission_ids"]:
            lines.append(f"  - {cid}")

    path.write_text("\n".join(lines))


def _write_core_markdown(
    rows: list[ScoredRow],
    metrics: dict[str, object],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# System D3 — locked Run 2 core report\n")
    lines.append(
        "D3 vs D2 vs D1 vs C0 on the 60 locked Run 2 cases under "
        "v1 gold. The D3 causal warning detector is not expected "
        "to fire on Run 2 core (no causal prompts).\n"
    )
    intent_acc = {
        "c0": _fraction([r.c0_intent_correct for r in rows]),
        "d1": _fraction([r.d1_intent_correct for r in rows]),
        "d2": _fraction([r.d2_intent_correct for r in rows]),
        "d3": _fraction([r.d3_intent_correct for r in rows]),
    }
    beh_acc = {
        "c0": _fraction([r.c0_behavior_class_correct for r in rows]),
        "d1": _fraction([r.d1_behavior_class_correct for r in rows]),
        "d2": _fraction([r.d2_behavior_class_correct for r in rows]),
        "d3": _fraction([r.d3_behavior_class_correct for r in rows]),
    }
    warn_p = {
        "c0": sum(r.c0_warning_precision for r in rows) / len(rows),
        "d1": sum(r.d1_warning_precision for r in rows) / len(rows),
        "d2": sum(r.d2_warning_precision for r in rows) / len(rows),
        "d3": sum(r.d3_warning_precision for r in rows) / len(rows),
    }
    warn_r = {
        "c0": sum(r.c0_warning_recall for r in rows) / len(rows),
        "d1": sum(r.d1_warning_recall for r in rows) / len(rows),
        "d2": sum(r.d2_warning_recall for r in rows) / len(rows),
        "d3": sum(r.d3_warning_recall for r in rows) / len(rows),
    }
    lines.append("| metric | C0 | D1 | D2 | D3 |")
    lines.append("|---|---:|---:|---:|---:|")
    lines.append(
        f"| intent_accuracy | {_fmt(intent_acc['c0'])} | "
        f"{_fmt(intent_acc['d1'])} | {_fmt(intent_acc['d2'])} | "
        f"{_fmt(intent_acc['d3'])} |"
    )
    lines.append(
        f"| behavior_class_accuracy | {_fmt(beh_acc['c0'])} | "
        f"{_fmt(beh_acc['d1'])} | {_fmt(beh_acc['d2'])} | "
        f"{_fmt(beh_acc['d3'])} |"
    )
    lines.append(
        f"| warning_precision | {_fmt(warn_p['c0'])} | "
        f"{_fmt(warn_p['d1'])} | {_fmt(warn_p['d2'])} | "
        f"{_fmt(warn_p['d3'])} |"
    )
    lines.append(
        f"| warning_recall | {_fmt(warn_r['c0'])} | "
        f"{_fmt(warn_r['d1'])} | {_fmt(warn_r['d2'])} | "
        f"{_fmt(warn_r['d3'])} |"
    )
    lines.append("")
    lines.append(
        f"\n- core_run2_regressions vs C0: "
        f"**{metrics['core_run2_regressions']}** "
        f"(ids={metrics['core_run2_regression_ids']})\n"
    )
    path.write_text("\n".join(lines))


def _write_failure_map(rows: list[ScoredRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow([
            "case_id", "axis", "split",
            "d3_predicted_intent", "d3_intent_correct",
            "d3_behavior_class_correct",
            "d3_warning_precision", "d3_warning_recall",
            "in_d3_overlay",
            "d3_v2_intent_correct", "d3_v2_behavior_class_correct",
            "d3_v2_warning_precision", "d3_v2_warning_recall",
            "d3_predicted_warnings",
        ])
        for r in rows:
            w.writerow([
                r.case_id, r.axis, r.split,
                r.d3_predicted_intent, int(r.d3_intent_correct),
                int(r.d3_behavior_class_correct),
                f"{r.d3_warning_precision:.4f}",
                f"{r.d3_warning_recall:.4f}",
                int(r.in_d3_overlay),
                "" if r.d3_v2_intent_correct is None else int(r.d3_v2_intent_correct),
                "" if r.d3_v2_behavior_class_correct is None else int(r.d3_v2_behavior_class_correct),
                "" if r.d3_v2_warning_precision is None else f"{r.d3_v2_warning_precision:.4f}",
                "" if r.d3_v2_warning_recall is None else f"{r.d3_v2_warning_recall:.4f}",
                r.d3_predicted_warnings,
            ])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_full_d3_evaluation(reports_dir: Optional[Path] = None) -> dict[str, object]:
    reports_dir = Path(reports_dir or (HERE / "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)

    target_18, must_not_regress, n_a_preserved = _load_cohort_membership()
    overlay = load_overlay()

    core_surfaces = _load_core_run2_cases()
    axis1_surfaces = _load_axis1_cases()
    axis2_surfaces = _load_axis2_cases()
    axis3_surfaces = _load_axis3_cases()
    axis4_surfaces = _load_axis4_cases()

    core_rows = [
        r for s in core_surfaces
        if (r := _score_one_surface(s, target_18, must_not_regress, overlay))
    ]
    axis1_rows = [
        r for s in axis1_surfaces
        if (r := _score_one_surface(s, target_18, must_not_regress, overlay))
    ]
    axis2_rows = [
        r for s in axis2_surfaces
        if (r := _score_one_surface(s, target_18, must_not_regress, overlay))
    ]
    axis3_rows = [
        r for s in axis3_surfaces
        if (r := _score_one_surface(s, target_18, must_not_regress, overlay))
    ]
    axis4_rows = [
        r for s in axis4_surfaces
        if (r := _score_one_surface(s, target_18, must_not_regress, overlay))
    ]
    stress_rows = axis1_rows + axis2_rows + axis3_rows + axis4_rows

    metrics = compute_metrics(
        core_rows, stress_rows, target_18, must_not_regress, n_a_preserved
    )

    _write_per_case_csv(stress_rows, reports_dir / "system_d3_stress_report.csv")
    _write_per_case_csv(core_rows, reports_dir / "system_d3_core_run2_report.csv")
    _write_stress_markdown(
        stress_rows, metrics, reports_dir / "system_d3_stress_report.md"
    )
    _write_core_markdown(
        core_rows, metrics, reports_dir / "system_d3_core_run2_report.md"
    )
    _write_failure_map(
        core_rows + stress_rows, reports_dir / "system_d3_failure_map.csv"
    )

    return {
        "metrics": metrics,
        "n_core_rows": len(core_rows),
        "n_stress_rows": len(stress_rows),
        "n_overlay_rows": sum(1 for r in stress_rows if r.in_d3_overlay),
    }


def main() -> int:
    out = run_full_d3_evaluation()
    m = out["metrics"]
    print("=== System D3 evaluation ===")
    print(f"core_run2 cases scored: {out['n_core_rows']}")
    print(f"stress cases scored: {out['n_stress_rows']}")
    print(f"D3 v2 overlay cases: {out['n_overlay_rows']}")
    print(f"D3 v2 target-5 fixed: {m['d3_target_5_fixed_count']}/5 "
          f"({m['d3_target_5_fixed_rate']:.2%})")
    print(f"D2 target-5 preserved under D3: "
          f"{m['d2_target_5_preserved_under_d3_count']}/5")
    print(f"D1 target-18 preserved under D3: "
          f"{m['target_18_under_d3_fixed_count']}/18")
    print(f"must_not_regress_70 preserved: "
          f"{m['must_not_regress_70_preserved_count']}/70 "
          f"({m['must_not_regress_70_preserved_rate']:.2%})")
    print(f"core_run2 regressions vs C0: {m['core_run2_regressions']} "
          f"(ids={m['core_run2_regression_ids']})")
    print(f"axis4 D3 perfect: {m['axis4_d3_perfect']}/24 "
          f"(regressions={m['axis4_regressions']})")
    print(f"off-target causal emissions: "
          f"{m['off_target_causal_emission_count']} "
          f"({m['off_target_causal_emission_ids']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

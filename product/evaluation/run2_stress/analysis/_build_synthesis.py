"""Cross-axis C0 (+ A/B for Axis 4) synthesis builder.

Reads each axis's per-case baseline CSV(s), maps the axis-specific
failure-mode buckets onto a **unified 6-category failure map**, and
emits:

  analysis/failure_map.csv       — one row per (case_id, axis, system)
  analysis/failure_summary.csv   — wide counts per (axis, system, category)
  analysis/unified_scatter.csv   — refreshed via concat_scatter

The Markdown narrative (`cross_axis_synthesis.md`) is hand-authored
and references the numbers this script emits.

Unified categories (alphabetical for stable CSV diffs):

  - model_projection_failure              — Axis 4 A/B sub-shapes
  - must_not_regress_guard_protected      — C0 perfect / contract correct
  - out_of_envelope_answerability         — Axis 2 missed_false_premise on
                                            non-entity-bound intents
  - schema_gap                            — Axis 2 schema-gap cases
  - system_d_addressable_intent           — wrong_intent / unknown_intent
                                            (Axes 1, 2, 3) where the fix
                                            lives in intent.py
  - downstream_evidence_artifact          — Axis 1 documented R2-028..R2-031
                                            infeasibility_kind off-by-one
                                            (preserved as its own label so
                                            the synthesis honestly accounts
                                            for the 3 Axis-1 downstream
                                            cases)

No solver / model calls. Pure CSV transform. Idempotent.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from product.evaluation.run2_stress.analysis.concat_scatter import (
    candidate_scatter_files,
    concat_scatter,
)


HERE = Path(__file__).resolve().parent
STRESS_ROOT = HERE.parent


UNIFIED_CATEGORIES: tuple[str, ...] = (
    "system_d_addressable_intent",
    "out_of_envelope_answerability",
    "schema_gap",
    "model_projection_failure",
    "must_not_regress_guard_protected",
    "downstream_evidence_artifact",
)


# ---------------------------------------------------------------------------
# Axis-specific bucket → unified-category mapping
# ---------------------------------------------------------------------------


_AXIS1_BUCKET_TO_CATEGORY: dict[str, str] = {
    "wrong_adjacent_intent": "system_d_addressable_intent",
    "unknown_intent": "system_d_addressable_intent",
    "guard_protected": "must_not_regress_guard_protected",
    "downstream_mismatch": "downstream_evidence_artifact",
    "score_missing": "downstream_evidence_artifact",
}


_AXIS2_BUCKET_TO_CATEGORY: dict[str, str] = {
    "correct_refusal_or_partial": "must_not_regress_guard_protected",
    "guard_protected": "must_not_regress_guard_protected",
    "downstream_evidence_mismatch": "downstream_evidence_artifact",
    "schema_gap_or_unrepresentable_gold": "schema_gap",
    "unknown_intent": "system_d_addressable_intent",
    "wrong_intent": "system_d_addressable_intent",
    "missed_false_premise": "out_of_envelope_answerability",
    "missed_missing_comparator": "out_of_envelope_answerability",
    "over_answered_unsupported_premise": "out_of_envelope_answerability",
    "score_missing": "downstream_evidence_artifact",
}


# ---------------------------------------------------------------------------
# Axis 4 A/B sub-shape inference
# ---------------------------------------------------------------------------


# B truncation-induced false-premise cases per the Axis 4 closeout §6.2.
_AXIS4_B_TRUNCATION_CASES: frozenset[str] = frozenset({
    "R2-101", "R2-102", "R2-113", "R2-114", "R2-115",
})

# A's silent-prior-override case per Axis 4 closeout §6.4.
_AXIS4_A_PRIOR_OVERRIDE_CASES: frozenset[str] = frozenset({"R2-108"})


def _axis4_model_sub_label(
    case_id: str, system: str, row: dict[str, str]
) -> str:
    """Return a fine-grained sub-label for an Axis 4 A or B case.

    The four observed sub-shapes per the closeout §6:
      - axis4_b_truncation_false_premise
      - axis4_a_silent_prior_override
      - axis4_warning_over_firing       (pred warnings ⊋ gold warnings,
                                          not already covered above)
      - axis4_evidence_over_citation    (ev_precision < 1.0, no warning
                                          over-firing)
      - axis4_other_model_failure       (residual; rare)
    """
    pred_warnings = (row.get("predicted_warnings") or "").strip()
    pred_warning_set = set(
        w.strip() for w in pred_warnings.split(";") if w.strip()
    )

    if system == "b" and case_id in _AXIS4_B_TRUNCATION_CASES:
        return "axis4_b_truncation_false_premise"
    if system == "a" and case_id in _AXIS4_A_PRIOR_OVERRIDE_CASES:
        return "axis4_a_silent_prior_override"

    # Warning over-firing: predicted warning that is not in the locked
    # set of contract-pinned warnings the gold uses (e.g.,
    # route_indexing_ambiguity on positional / plural; struct_membership
    # on lateness). A coarse proxy: warning_precision < 1.0.
    try:
        warn_p = float(row.get("warning_precision") or 0.0)
    except ValueError:
        warn_p = 0.0
    try:
        ev_p = float(row.get("evidence_precision") or 0.0)
    except ValueError:
        ev_p = 0.0

    if warn_p < 1.0:
        return "axis4_warning_over_firing"
    if ev_p < 1.0:
        return "axis4_evidence_over_citation"
    return "axis4_other_model_failure"


# ---------------------------------------------------------------------------
# Per-axis row reader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseRow:
    case_id: str
    axis: str
    system: str
    split: str
    band: str
    intent: str
    bucket: str
    category: str
    sub_label: str
    intent_correct: Optional[float]
    behavior_class_correct: Optional[float]
    notes: str = ""


def _read_axis1_axis2(axis: str) -> list[CaseRow]:
    df = pd.read_csv(
        STRESS_ROOT / axis / "reports" / "c0_baseline.csv",
        keep_default_na=False,
        dtype=str,
    )
    mapping = (
        _AXIS1_BUCKET_TO_CATEGORY
        if axis == "axis1_lookalike"
        else _AXIS2_BUCKET_TO_CATEGORY
    )
    out: list[CaseRow] = []
    for _, r in df.iterrows():
        bucket = r.get("bucket", "")
        category = mapping.get(bucket, "downstream_evidence_artifact")
        sub_label = bucket  # preserve the original axis-specific label
        out.append(
            CaseRow(
                case_id=r["case_id"],
                axis=axis,
                system="c0",
                split=r.get("split", ""),
                band=r.get("band", ""),
                intent=r.get("expected_intent", ""),
                bucket=bucket,
                category=category,
                sub_label=sub_label,
                intent_correct=float(r["intent_correct"] == "true"),
                behavior_class_correct=float(
                    r["behavior_class_correct"] == "true"
                ),
                notes="",
            )
        )
    return out


def _read_axis3() -> list[CaseRow]:
    """Axis 3 has no `bucket` column. Derive the label from the
    intent-prediction outcome:

      - predicted_intent == "unknown" and intent_correct=false
        → system_d_addressable_intent (sub_label: unknown_intent)
      - intent_correct=false and predicted_intent != "unknown"
        → system_d_addressable_intent (sub_label: wrong_intent)
      - intent_correct=true and behavior_class_correct=true and every
        downstream metric==1.0
        → must_not_regress_guard_protected (sub_label: guard_protected)
      - intent_correct=true and some downstream metric <1.0
        → downstream_evidence_artifact (sub_label: downstream_mismatch)
    """
    df = pd.read_csv(
        STRESS_ROOT / "axis3_semantic" / "reports" / "c0_baseline.csv",
        keep_default_na=False,
        dtype=str,
    )
    out: list[CaseRow] = []
    for _, r in df.iterrows():
        intent_correct = r["intent_correct"] == "true"
        predicted_intent = r["predicted_intent"]
        if not intent_correct and predicted_intent == "unknown":
            category = "system_d_addressable_intent"
            sub_label = "unknown_intent"
            bucket = "unknown_intent"
        elif not intent_correct:
            category = "system_d_addressable_intent"
            sub_label = "wrong_intent"
            bucket = "wrong_intent"
        else:
            downstream_perfect = all(
                float(r[col]) == 1.0
                for col in (
                    "evidence_precision",
                    "evidence_recall",
                    "warning_precision",
                    "warning_recall",
                    "missing_field_recall",
                )
            ) and r["behavior_class_correct"] == "true"
            if downstream_perfect:
                category = "must_not_regress_guard_protected"
                sub_label = "guard_protected"
                bucket = "guard_protected"
            else:
                category = "downstream_evidence_artifact"
                sub_label = "downstream_mismatch"
                bucket = "downstream_mismatch"
        out.append(
            CaseRow(
                case_id=r["case_id"],
                axis="axis3_semantic",
                system="c0",
                split=r.get("split", ""),
                band=r.get("stress_subtype", ""),  # axis3 has no band column
                intent=r["expected_intent"],
                bucket=bucket,
                category=category,
                sub_label=sub_label,
                intent_correct=1.0 if intent_correct else 0.0,
                behavior_class_correct=(
                    1.0 if r["behavior_class_correct"] == "true" else 0.0
                ),
                notes="",
            )
        )
    return out


def _read_axis4() -> list[CaseRow]:
    out: list[CaseRow] = []
    axis = "axis4_payload"
    for system, fname in (
        ("c0", "c0_baseline.csv"),
        ("a", "system_a_baseline.csv"),
        ("b", "system_b_baseline.csv"),
    ):
        df = pd.read_csv(
            STRESS_ROOT / axis / "reports" / fname,
            keep_default_na=False,
            dtype=str,
        )
        for _, r in df.iterrows():
            # The C0 baseline stores booleans as "True"/"False"; A/B
            # store "1"/"0". Normalize.
            def _to_float(value: str) -> float:
                if value in ("True", "true", "1", "1.0"):
                    return 1.0
                if value in ("False", "false", "0", "0.0"):
                    return 0.0
                try:
                    return float(value)
                except ValueError:
                    return 0.0

            intent_c = _to_float(r["intent_correct"])
            ans_c = _to_float(r["answerability_correct"])
            bc_c = _to_float(r["behavior_class_correct"])
            ev_p = _to_float(r["evidence_precision"])
            ev_r = _to_float(r["evidence_recall"])
            warn_p = _to_float(r["warning_precision"])
            warn_r = _to_float(r["warning_recall"])
            miss_r = _to_float(r["missing_field_recall"])

            all_perfect = (
                intent_c == 1.0
                and ans_c == 1.0
                and bc_c == 1.0
                and ev_p == 1.0
                and ev_r == 1.0
                and warn_p == 1.0
                and warn_r == 1.0
                and miss_r == 1.0
            )

            if system == "c0":
                # C0 is perfect on Axis 4 by design — see the closeout.
                category = "must_not_regress_guard_protected"
                sub_label = "axis4_c0_perfect"
                bucket = "guard_protected"
            elif all_perfect:
                category = "must_not_regress_guard_protected"
                sub_label = "axis4_model_perfect"
                bucket = "guard_protected"
            else:
                category = "model_projection_failure"
                sub_label = _axis4_model_sub_label(
                    r["case_id"], system, dict(r)
                )
                bucket = "model_projection_failure"

            out.append(
                CaseRow(
                    case_id=r["case_id"],
                    axis=axis,
                    system=system,
                    split=r.get("split", ""),
                    band=r.get("band", ""),
                    intent=r.get("intent", ""),
                    bucket=bucket,
                    category=category,
                    sub_label=sub_label,
                    intent_correct=intent_c,
                    behavior_class_correct=bc_c,
                    notes="",
                )
            )
    return out


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


_FAILURE_MAP_COLS: list[str] = [
    "case_id",
    "axis",
    "system",
    "split",
    "band",
    "intent",
    "bucket",
    "category",
    "sub_label",
    "intent_correct",
    "behavior_class_correct",
    "notes",
]


def _write_failure_map(rows: list[CaseRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=_FAILURE_MAP_COLS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "case_id": r.case_id,
                    "axis": r.axis,
                    "system": r.system,
                    "split": r.split,
                    "band": r.band,
                    "intent": r.intent,
                    "bucket": r.bucket,
                    "category": r.category,
                    "sub_label": r.sub_label,
                    "intent_correct": (
                        "" if r.intent_correct is None
                        else f"{r.intent_correct:.0f}"
                    ),
                    "behavior_class_correct": (
                        "" if r.behavior_class_correct is None
                        else f"{r.behavior_class_correct:.0f}"
                    ),
                    "notes": r.notes,
                }
            )


def _write_failure_summary(rows: list[CaseRow], path: Path) -> None:
    """Per-(axis, system, category) counts in a wide-ish shape suitable
    for the synthesis Markdown tables."""
    by_axis_system_cat: Counter[tuple[str, str, str]] = Counter()
    for r in rows:
        by_axis_system_cat[(r.axis, r.system, r.category)] += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["axis", "system", "category", "n"])
        for (axis, system, category), n in sorted(by_axis_system_cat.items()):
            writer.writerow([axis, system, category, n])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_failure_rows() -> list[CaseRow]:
    rows: list[CaseRow] = []
    rows.extend(_read_axis1_axis2("axis1_lookalike"))
    rows.extend(_read_axis1_axis2("axis2_ood_premises"))
    rows.extend(_read_axis3())
    rows.extend(_read_axis4())
    return rows


def main() -> int:
    # 1. Refresh the unified scatter — guards against stale files.
    paths = candidate_scatter_files()
    if not paths:
        print("no per-axis scatter files found", flush=True)
        return 1
    unified = concat_scatter(paths)
    (HERE / "unified_scatter.csv").write_text(unified.to_csv(index=False))

    # 2. Build the failure map.
    rows = build_failure_rows()
    _write_failure_map(rows, HERE / "failure_map.csv")
    _write_failure_summary(rows, HERE / "failure_summary.csv")

    print(
        f"wrote {HERE / 'unified_scatter.csv'} ({len(unified)} rows from "
        f"{len(paths)} per-axis files)"
    )
    print(
        f"wrote {HERE / 'failure_map.csv'} ({len(rows)} per-(case, axis, "
        "system) rows)"
    )
    print(f"wrote {HERE / 'failure_summary.csv'}")

    # 3. Print a tiny category summary so the operator can sanity-check
    #    immediately.
    by_category: Counter[str] = Counter(r.category for r in rows)
    print("category totals (across all axes + systems):")
    for cat in UNIFIED_CATEGORIES:
        if cat in by_category:
            print(f"  {cat}: {by_category[cat]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

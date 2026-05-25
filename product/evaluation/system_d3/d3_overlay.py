"""D3 schema-v2 overlay loader + scorer adapter.

The locked Run 2 scorer (`product.evaluation.run2_scoring.score_case`)
is byte-frozen. D3 must not modify it. Instead, this module
constructs a Run2Case whose v2 gold columns are taken from the
D3 overlay CSV (`axis2_causal_gold_overlay.csv`) while every
v1-only column (label_rationale, difficulty, etc.) is inherited
from the original Axis 2 case. The result is a normal Run2Case
that `score_case` can grade unchanged.

The overlay is keyed by case_id. For any case_id not in the
overlay, callers should grade against the original gold; this
module provides `load_overlay()` and `case_with_overlay()` helpers
that make that explicit at the call site.
"""
from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Optional

from product.evaluation.run2_case_loader import Run2Case, _split_multi


HERE = Path(__file__).resolve().parent
OVERLAY_CSV = HERE / "axis2_causal_gold_overlay.csv"


def load_overlay(overlay_path: Optional[Path] = None) -> dict[str, dict]:
    """Return {case_id: {column: value}} for every overlay row.

    Values for list-typed columns are still strings here (split is
    performed in `case_with_overlay` so the originals are preserved
    for diagnostics).
    """
    p = Path(overlay_path or OVERLAY_CSV)
    out: dict[str, dict] = {}
    with p.open() as fh:
        for row in csv.DictReader(fh):
            out[row["case_id"]] = row
    return out


def case_with_overlay(case: Run2Case, overlay_row: dict) -> Run2Case:
    """Apply the v2 overlay columns to a copy of `case`.

    The overlay is grading-only: every metric column gets overlaid;
    label_rationale / difficulty / implementation_status carry
    their v1 values forward. The overlay's `v2_rationale` is
    appended to label_rationale so the v2 reasoning travels with
    the case.
    """
    appended_rationale = (
        f"{case.label_rationale}\n[v2 overlay] {overlay_row.get('v2_rationale', '')}"
        if overlay_row.get("v2_rationale")
        else case.label_rationale
    )
    return replace(
        case,
        expected_intent=overlay_row["expected_intent"],
        expected_answerability=overlay_row["expected_answerability"],
        expected_evidence_paths=_split_multi(overlay_row["expected_evidence_paths"]),
        expected_missing_fields=_split_multi(overlay_row["expected_missing_fields"]),
        expected_warnings=_split_multi(overlay_row["expected_warnings"]),
        expected_next_actions=_split_multi(overlay_row["expected_next_actions"]),
        expected_behavior_class=overlay_row["expected_behavior_class"],
        label_rationale=appended_rationale,
    )


def overlay_case_ids(overlay: Optional[dict[str, dict]] = None) -> set[str]:
    """Return the case_id set the overlay covers."""
    return set((overlay or load_overlay()).keys())


__all__ = [
    "OVERLAY_CSV",
    "case_with_overlay",
    "load_overlay",
    "overlay_case_ids",
]

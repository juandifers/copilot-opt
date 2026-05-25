"""Shared helper for converting per-case scored results into the
long-form scatter rows defined in `scatter_schema.md`.

Use this from axis runners after scoring to emit a per-axis
`reports/scatter.csv` whose schema is comparable across axes.

The helper accepts any iterable of "scored case" objects that look
like `(case, score)` pairs. `case` exposes (at minimum) `case_id`
and `split`; `score` exposes the 10 metric fields documented in
`metric_names.md`. Both are typically `run2_case_loader.Run2Case`
and `run2_scoring.CaseScore`, but plain dicts work too — the
helper introspects with `getattr` and falls back to `dict.get`.
"""
from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence


# Mirrors `validators.SCATTER_COLUMNS`. Kept literal here so the
# module is callable without importing the validator.
SCATTER_COLUMNS: list[str] = [
    "case_id",
    "axis",
    "split",
    "band",
    "intent",
    "n_routes",
    "payload_chars",
    "system",
    "metric",
    "score",
]


# Mapping from canonical scatter metric name to attribute name on a
# `CaseScore`-like object. Conditional metrics whose value is
# `None` for inapplicable cases are encoded as the empty string in
# the scatter (the canonical CSV null token).
_METRIC_TO_ATTR: list[tuple[str, str]] = [
    ("intent_correct", "intent_correct"),
    ("answerability_correct", "answerability_correct"),
    ("behavior_class_correct", "behavior_class_correct"),
    ("evidence_precision", "evidence_precision"),
    ("evidence_recall", "evidence_recall"),
    ("warning_precision", "warning_precision"),
    ("warning_recall", "warning_recall"),
    ("missing_field_recall", "missing_field_recall"),
    ("useful_refusal_correct", "useful_refusal_correct"),
    ("partial_answer_correct", "partial_answer_correct"),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _getattr_or_key(obj: Any, name: str, default: Any = None) -> Any:
    """Read `name` off either an attribute-bearing object or a Mapping."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _to_scatter_score(raw: Any) -> Optional[float]:
    """Coerce a metric value to the scatter `score` representation.

    Booleans → 0.0 / 1.0. Numerics → float. None → None (null).
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


@dataclass(frozen=True)
class ScatterContext:
    """Per-case metadata fields that the scoring layer does not know.

    `band` is axis-specific (axis 4 uses `low`/`high`; axis 1/3 may
    use intent-family labels). `n_routes` and `payload_chars` are
    `None` when the axis does not measure them.
    """

    band: str = ""
    n_routes: Optional[int] = None
    payload_chars: Optional[int] = None


def to_scatter_rows(
    scored_cases: Iterable[tuple[Any, Any]],
    axis: str,
    system: str,
    band_lookup: Optional[Mapping[str, str]] = None,
    payload_metadata_lookup: Optional[Mapping[str, ScatterContext | Mapping[str, Any]]] = None,
    emit_null_for_inapplicable: bool = True,
) -> list[dict[str, Any]]:
    """Convert scored cases into long-form scatter rows.

    Parameters
    ----------
    scored_cases:
        Iterable of `(case, score)` pairs. `case` must expose
        `case_id`, `split`, and `expected_intent` (or supply `intent`
        directly). `score` must expose the 10 metric fields named in
        `metric_names.md` (or be a dict carrying the same keys).
    axis:
        Axis directory name, e.g. ``"axis3_semantic"``.
    system:
        System label (``"c0"``, ``"a"``, ``"b"``, ``"d"``).
    band_lookup:
        Optional ``{case_id: band}`` map. Falls back to the case
        object's `band` attribute, then to the empty string.
    payload_metadata_lookup:
        Optional ``{case_id: ScatterContext | dict}`` map providing
        `band` / `n_routes` / `payload_chars`. Overrides any
        equivalent attribute on the case object.
    emit_null_for_inapplicable:
        When True (default) conditional metrics whose `score` is
        None still emit a row with `score=""`. When False, those
        rows are omitted.

    Returns
    -------
    A list of dicts in scatter-schema column order.
    """
    rows: list[dict[str, Any]] = []
    band_lookup = band_lookup or {}
    payload_metadata_lookup = payload_metadata_lookup or {}

    for case, score in scored_cases:
        case_id = _getattr_or_key(case, "case_id")
        split = _getattr_or_key(case, "split", default="")
        intent = (
            _getattr_or_key(case, "intent", default=None)
            or _getattr_or_key(case, "expected_intent", default="")
        )

        # Resolve per-case context — explicit lookup wins, then case
        # attributes, then defaults.
        ctx_entry = payload_metadata_lookup.get(case_id)
        if isinstance(ctx_entry, ScatterContext):
            ctx_band = ctx_entry.band
            ctx_routes = ctx_entry.n_routes
            ctx_chars = ctx_entry.payload_chars
        elif isinstance(ctx_entry, Mapping):
            ctx_band = ctx_entry.get("band", "")
            ctx_routes = ctx_entry.get("n_routes")
            ctx_chars = ctx_entry.get("payload_chars")
        else:
            ctx_band = ""
            ctx_routes = None
            ctx_chars = None

        band = (
            ctx_band
            or band_lookup.get(case_id, "")
            or _getattr_or_key(case, "band", default="")
        )
        n_routes = (
            ctx_routes
            if ctx_routes is not None
            else _getattr_or_key(case, "n_routes", default=None)
        )
        payload_chars = (
            ctx_chars
            if ctx_chars is not None
            else _getattr_or_key(case, "payload_chars", default=None)
        )

        for metric_name, attr in _METRIC_TO_ATTR:
            raw = _getattr_or_key(score, attr)
            scatter_score = _to_scatter_score(raw)

            if scatter_score is None and not emit_null_for_inapplicable:
                continue

            rows.append(
                {
                    "case_id": case_id,
                    "axis": axis,
                    "split": split,
                    "band": band,
                    "intent": intent,
                    "n_routes": n_routes,
                    "payload_chars": payload_chars,
                    "system": system,
                    "metric": metric_name,
                    "score": scatter_score,
                }
            )

    return rows


def _format_cell(value: Any) -> str:
    """Serialise a cell to the scatter CSV string representation.

    None → "" (canonical null token). Floats are written with 6
    significant digits to keep file sizes modest while preserving
    rounded metric values.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1.0" if value else "0.0"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def write_scatter_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    """Write rows to a scatter CSV at `path`, creating parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=SCATTER_COLUMNS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {col: _format_cell(row.get(col)) for col in SCATTER_COLUMNS}
            )


__all__ = [
    "SCATTER_COLUMNS",
    "ScatterContext",
    "to_scatter_rows",
    "write_scatter_csv",
]

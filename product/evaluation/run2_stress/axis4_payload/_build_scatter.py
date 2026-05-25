"""Emit the shared-schema scatter.csv for R2-S Axis 4.

Reads the three already-scored baseline CSVs:

  reports/c0_baseline.csv
  reports/system_a_baseline.csv
  reports/system_b_baseline.csv

and writes a long-form `reports/scatter.csv` conforming to
`product/evaluation/run2_stress/shared/scatter_schema.md`:

  case_id, axis, split, band, intent, n_routes, payload_chars,
  system, metric, score

`axis` is always `axis4_payload`. `system` is one of `c0`, `a`, `b`.
`payload_chars` is computed by serializing the materialized payload
under `payloads/<cell_id>.json` (the same payload the C0 and A/B
runs scored against).

Row count = 24 cases × 3 systems × 10 metrics = 720.
Null `score` cells appear for the inapplicable conditional metrics
(`useful_refusal_correct` and `partial_answer_correct`) — no Axis 4
case has gold of either of those behavior classes.

No API calls. No model reruns. Idempotent.
"""
from __future__ import annotations

import csv
import json
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Optional

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"
PAYLOADS = HERE / "payloads"


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


# Canonical scatter metric -> (per-row CSV column, is_optional_bool).
# The optional bools are scored as "" when N/A and become null in the
# scatter; the other metrics are always numeric.
METRICS: list[tuple[str, str]] = [
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


def _read_baseline(path: Path) -> list[dict[str, str]]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def _payload_chars(cell_id: str) -> Optional[int]:
    """Number of characters in the materialized payload JSON for
    this case's cell_id. Uses `json.dumps(payload, sort_keys=True)`
    so the figure is reproducible irrespective of dict ordering."""
    p = PAYLOADS / f"{cell_id}.json"
    if not p.exists():
        return None
    try:
        with p.open() as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return len(json.dumps(payload, sort_keys=True))


def _format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1.0" if value else "0.0"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def _parse_score(value: str, metric: str) -> Optional[float]:
    """Convert a per-row baseline cell into a float score, or None if
    the metric is N/A for the case (canonical scatter null token).

    Handles three representations seen across the baseline CSVs:
      - "True" / "False" (Python bool repr, used by the C0 baseline)
      - "1" / "0" (int repr, used by the A / B baselines)
      - "0.5", "1.0", etc. (float, every metric on every system)
      - "" (the N/A cell for an inapplicable conditional metric)
    """
    if value == "" or value is None:
        return None
    if value == "True":
        return 1.0
    if value == "False":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return None


def _build_rows(
    c0_rows: list[dict[str, str]],
    a_rows: list[dict[str, str]],
    b_rows: list[dict[str, str]],
) -> list[dict]:
    by_cid_c0 = OrderedDict((r["case_id"], r) for r in c0_rows)
    by_cid_a = {r["case_id"]: r for r in a_rows}
    by_cid_b = {r["case_id"]: r for r in b_rows}

    rows: list[dict] = []
    for case_id, c0 in by_cid_c0.items():
        # Per-case context is identical across systems (split / band /
        # n_routes / intent / cell_id / payload).
        context = dict(
            case_id=case_id,
            axis="axis4_payload",
            split=c0["split"],
            band=c0["band"],
            intent=c0["intent"],
            n_routes=int(c0["n_routes"]),
            payload_chars=_payload_chars(c0["cell_id"]),
        )

        # `partial_answer_correct` is N/A for every Axis 4 case (no
        # gold partial_answer_with_warning). The baseline CSVs do not
        # carry a column for it; we emit a null score row uniformly.

        for system_label, src in (
            ("c0", c0),
            ("a", by_cid_a.get(case_id)),
            ("b", by_cid_b.get(case_id)),
        ):
            if src is None:
                continue
            for metric_name, col in METRICS:
                if metric_name == "partial_answer_correct":
                    raw = ""
                else:
                    raw = src.get(col, "")
                score = _parse_score(raw, metric_name)
                rows.append(
                    {
                        **context,
                        "system": system_label,
                        "metric": metric_name,
                        "score": score,
                    }
                )
    return rows


def write_scatter(out_path: Path | None = None) -> Path:
    if out_path is None:
        out_path = REPORTS / "scatter.csv"
    c0_rows = _read_baseline(REPORTS / "c0_baseline.csv")
    a_rows = _read_baseline(REPORTS / "system_a_baseline.csv")
    b_rows = _read_baseline(REPORTS / "system_b_baseline.csv")
    rows = _build_rows(c0_rows, a_rows, b_rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=SCATTER_COLUMNS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        for r in rows:
            writer.writerow({c: _format_cell(r.get(c)) for c in SCATTER_COLUMNS})
    return out_path


def main() -> None:
    out = write_scatter()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

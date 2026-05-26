#!/usr/bin/env python3
"""Generate ``data/instances/uchoa_x_classification.csv`` from inline source data.

This is a one-time transcription tool. The source data below is taken verbatim
from Tables 11, 12, and 13 of:

    Uchoa, E., Pecin, D., Pessoa, A., Poggi, M., Vidal, T., Subramanian, A.
    (2017). New benchmark instances for the Capacitated Vehicle Routing Problem.
    European Journal of Operational Research, 257(3), 845-858.
    Preprint: https://optimization-online.org/wp-content/uploads/2014/10/4597.pdf
    (pages 17, 18, 19 of the PDF)

For each of the 100 X-instances the source tables list:

    - Name (instance_id, e.g. X-n101-k25)
    - n (number of customers; depot is separate)
    - Dep (depot positioning: C, E, R)
    - Cust (customer positioning: R, C(k), or RC(k); cluster count dropped here)
    - Dem (demand distribution: U, 1-10, 5-10, 1-100, 50-100, Q, SL)
    - n/Kmin (realized average route size, used to derive the avg_route_size
      quintile label)

The avg_route_size quintile is computed empirically from the n/Kmin column
using ``numpy.percentile(..., method='linear')`` at 20/40/60/80. Bin
semantics: ``VS: x ≤ p20``, ``S: p20 < x ≤ p40``, ``M: p40 < x ≤ p60``,
``L: p60 < x ≤ p80``, ``VL: x > p80``. The boundaries (and per-bin counts)
are recorded in the CSV header so a reader can verify without re-running.

Re-run as: ``python scripts/build_classification_csv.py``
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import sys
from pathlib import Path

import numpy as np

OUTPUT_PATH: Path = Path("data/instances/uchoa_x_classification.csv")
SOURCE_URL: str = "https://optimization-online.org/wp-content/uploads/2014/10/4597.pdf"
SOURCE_PAGES: str = "17-19"
TRANSCRIPTION_DATE: str = "2026-05-04"

#: Source rows transcribed from the paper. Tuple format:
#: ``(instance_id, n, dep, cust_raw, dem, n_kmin)``
#: ``cust_raw`` keeps the parenthesised cluster count so the transcription is
#: faithful; the CSV writer strips it down to ``R``, ``C``, or ``RC``.
SOURCE_ROWS: list[tuple[str, int, str, str, str, float]] = [
    # --- Table 11 (rows 1-35) ----------------------------------------------
    ("X-n101-k25",  100, "R", "RC(7)",  "1-100",  4.0),
    ("X-n106-k14",  105, "E", "C(3)",   "50-100", 7.5),
    ("X-n110-k13",  109, "C", "R",      "5-10",   8.4),
    ("X-n115-k10",  114, "E", "R",      "SL",     11.4),
    ("X-n120-k6",   119, "E", "RC(8)",  "U",      19.8),
    ("X-n125-k30",  124, "E", "C(5)",   "Q",      4.1),
    ("X-n129-k18",  128, "E", "RC(8)",  "1-10",   7.1),
    ("X-n134-k13",  133, "C", "R",      "Q",      10.2),
    ("X-n139-k10",  138, "C", "RC(4)",  "5-10",   13.8),
    ("X-n143-k7",   142, "E", "R",      "1-100",  20.3),
    ("X-n148-k46",  147, "E", "RC(7)",  "1-10",   3.2),
    ("X-n153-k22",  152, "C", "C(3)",   "SL",     6.9),
    ("X-n157-k13",  156, "R", "R",      "U",      12.0),
    ("X-n162-k11",  161, "C", "RC(8)",  "50-100", 14.6),
    ("X-n167-k10",  166, "E", "C(3)",   "5-10",   16.6),
    ("X-n172-k51",  171, "C", "RC(5)",  "Q",      3.4),
    ("X-n176-k26",  175, "E", "R",      "SL",     6.7),
    ("X-n181-k23",  180, "E", "C(6)",   "U",      7.8),
    ("X-n186-k15",  185, "E", "R",      "50-100", 12.3),
    ("X-n190-k8",   189, "C", "C(3)",   "1-10",   23.6),
    ("X-n195-k51",  194, "E", "RC(8)",  "1-10",   3.8),
    ("X-n200-k36",  199, "C", "RC(4)",  "Q",      5.5),
    ("X-n204-k19",  203, "C", "RC(6)",  "1-10",   10.7),
    ("X-n209-k16",  208, "E", "R",      "5-10",   13.5),
    ("X-n214-k11",  213, "C", "C(7)",   "1-100",  19.4),
    ("X-n219-k73",  218, "E", "R",      "U",      3.0),
    ("X-n223-k34",  222, "E", "RC(5)",  "U",      6.5),
    ("X-n228-k23",  227, "E", "RC(8)",  "SL",     9.9),
    ("X-n233-k16",  232, "C", "RC(7)",  "5-10",   14.5),
    ("X-n237-k14",  236, "C", "R",      "1-100",  16.9),
    ("X-n242-k48",  241, "E", "R",      "U",      5.0),
    ("X-n247-k50",  246, "C", "C(4)",   "1-10",   4.9),
    ("X-n251-k28",  250, "R", "RC(3)",  "Q",      8.9),
    ("X-n256-k16",  255, "C", "C(8)",   "5-10",   15.9),
    ("X-n261-k13",  260, "E", "R",      "1-100",  20.0),
    # --- Table 12 (rows 36-70) ---------------------------------------------
    ("X-n266-k58",  265, "R", "RC(6)",  "5-10",   4.6),
    ("X-n270-k35",  269, "C", "RC(5)",  "50-100", 7.7),
    ("X-n275-k28",  274, "C", "C(3)",   "U",      9.8),
    ("X-n280-k17",  279, "E", "R",      "SL",     16.4),
    ("X-n284-k15",  283, "E", "RC(8)",  "1-10",   18.9),
    ("X-n289-k60",  288, "C", "RC(4)",  "Q",      4.8),
    ("X-n294-k50",  293, "E", "RC(2)",  "5-10",   5.9),
    ("X-n298-k31",  297, "E", "R",      "1-10",   9.6),
    ("X-n303-k21",  302, "C", "C(2)",   "1-100",  14.4),
    ("X-n308-k13",  307, "E", "RC(6)",  "SL",     23.6),
    ("X-n313-k71",  312, "R", "R",      "Q",      4.4),
    ("X-n317-k53",  316, "C", "C(3)",   "U",      6.0),
    ("X-n322-k28",  321, "E", "RC(7)",  "50-100", 11.5),
    ("X-n327-k20",  326, "E", "RC(7)",  "5-10",   16.3),
    ("X-n331-k15",  330, "E", "R",      "Q",      22.0),
    ("X-n336-k84",  335, "E", "R",      "Q",      4.0),
    ("X-n344-k43",  343, "C", "RC(7)",  "5-10",   8.0),
    ("X-n351-k40",  350, "E", "R",      "1-10",   8.8),
    ("X-n359-k29",  358, "C", "RC(6)",  "1-100",  12.3),
    ("X-n367-k17",  366, "R", "C(4)",   "SL",     21.5),
    ("X-n376-k94",  375, "E", "R",      "U",      4.0),
    ("X-n384-k52",  383, "C", "RC(5)",  "50-100", 7.4),
    ("X-n393-k38",  392, "E", "R",      "Q",      10.3),
    ("X-n401-k29",  400, "C", "C(6)",   "Q",      13.8),
    ("X-n411-k19",  410, "C", "C(5)",   "SL",     21.6),
    ("X-n420-k130", 419, "R", "R",      "1-10",   3.2),
    ("X-n429-k61",  428, "C", "RC(7)",  "50-100", 7.0),
    ("X-n439-k37",  438, "E", "RC(8)",  "U",      11.8),
    ("X-n449-k29",  448, "E", "R",      "1-100",  14.5),
    ("X-n459-k26",  458, "E", "RC(4)",  "Q",      17.6),
    ("X-n469-k138", 468, "C", "C(3)",   "50-100", 3.4),
    ("X-n480-k70",  479, "E", "R",      "1-10",   6.8),
    ("X-n491-k59",  490, "R", "RC(3)",  "U",      8.3),
    ("X-n502-k39",  501, "R", "C(3)",   "5-10",   12.8),
    ("X-n513-k21",  512, "C", "RC(4)",  "1-10",   24.4),
    # --- Table 13 (rows 71-100) --------------------------------------------
    ("X-n524-k153", 523, "R", "R",      "SL",     3.4),
    ("X-n536-k96",  535, "C", "C(7)",   "Q",      5.6),
    ("X-n548-k50",  547, "E", "R",      "U",      10.9),
    ("X-n561-k42",  560, "C", "RC(7)",  "1-10",   13.3),
    ("X-n573-k30",  572, "R", "R",      "SL",     19.1),
    ("X-n586-k159", 585, "E", "C(3)",   "SL",     3.7),
    ("X-n599-k92",  598, "R", "R",      "50-100", 6.5),
    ("X-n613-k62",  612, "R", "C(8)",   "1-100",  9.9),
    ("X-n627-k43",  626, "E", "C(5)",   "5-10",   14.6),
    ("X-n641-k35",  640, "E", "RC(8)",  "1-100",  18.3),
    ("X-n655-k131", 654, "C", "R",      "50-100", 5.0),
    ("X-n670-k130", 669, "R", "R",      "SL",     5.1),
    ("X-n685-k75",  684, "C", "RC(6)",  "Q",      9.1),
    ("X-n701-k44",  700, "E", "RC(6)",  "1-10",   15.9),
    ("X-n716-k35",  715, "R", "C(8)",   "1-100",  20.4),
    ("X-n733-k159", 732, "C", "R",      "1-10",   4.6),
    ("X-n749-k98",  748, "C", "C(8)",   "1-100",  7.7),
    ("X-n766-k71",  765, "E", "RC(7)",  "1-10",   10.8),
    ("X-n783-k48",  782, "C", "R",      "SL",     16.3),
    ("X-n801-k40",  800, "E", "R",      "U",      20.0),
    ("X-n819-k171", 818, "C", "C(3)",   "50-100", 4.8),
    ("X-n837-k142", 836, "R", "R",      "5-10",   5.9),
    ("X-n856-k95",  855, "C", "RC(3)",  "U",      9.0),
    ("X-n876-k59",  875, "E", "C(5)",   "SL",     14.8),
    ("X-n895-k37",  894, "R", "R",      "50-100", 24.2),
    ("X-n916-k207", 915, "R", "C(6)",   "5-10",   4.4),
    ("X-n936-k151", 935, "C", "R",      "Q",      6.2),
    ("X-n957-k87",  956, "E", "RC(4)",  "1-10",   11.0),
    ("X-n979-k58",  978, "E", "C(4)",   "Q",      16.9),
    ("X-n1001-k43", 1000, "R", "R",     "1-10",   23.3),
]
assert len(SOURCE_ROWS) == 100, "must have exactly 100 instances"

#: Allowed values for each classification dimension (validated below).
DEP_LEVELS = {"C", "E", "R"}
CUST_LEVELS = {"C", "R", "RC"}
DEM_LEVELS = {"U", "1-10", "5-10", "1-100", "50-100", "Q", "SL"}
QUINTILE_LABELS: tuple[str, ...] = ("VS", "S", "M", "L", "VL")

#: Pattern for the parenthesised cluster count in the Cust column.
_CUST_PARENS = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def _strip_cust(raw: str) -> str:
    """Drop ``(k)`` cluster count: ``RC(7)`` → ``RC``."""
    return _CUST_PARENS.sub("", raw).strip()


def quintile_boundaries(values: list[float]) -> tuple[float, float, float, float]:
    """20/40/60/80 percentiles via ``numpy.percentile`` (linear interpolation)."""
    arr = np.asarray(values, dtype=np.float64)
    p20, p40, p60, p80 = np.percentile(arr, [20, 40, 60, 80], method="linear")
    return float(p20), float(p40), float(p60), float(p80)


def label_for(x: float, bounds: tuple[float, float, float, float]) -> str:
    """Return the quintile label for ``x`` given the four boundaries.

    Bin semantics: ``VS: x ≤ p20``, ``S: p20 < x ≤ p40``, ``M: p40 < x ≤ p60``,
    ``L: p60 < x ≤ p80``, ``VL: x > p80``. Inclusive on the upper edge so ties
    at the boundary go to the lower bin.
    """
    p20, p40, p60, p80 = bounds
    if x <= p20:
        return "VS"
    if x <= p40:
        return "S"
    if x <= p60:
        return "M"
    if x <= p80:
        return "L"
    return "VL"


def build_csv() -> str:
    """Validate inputs, compute quintile labels, return the CSV body."""
    # Sanity-check the source rows up front: levels in expected vocabularies,
    # IDs unique, no missing fields.
    seen_ids: set[str] = set()
    for iid, n, dep, cust_raw, dem, nkmin in SOURCE_ROWS:
        assert iid not in seen_ids, f"duplicate instance_id {iid!r}"
        seen_ids.add(iid)
        assert dep in DEP_LEVELS, f"{iid}: bad Dep {dep!r}"
        assert _strip_cust(cust_raw) in CUST_LEVELS, f"{iid}: bad Cust {cust_raw!r}"
        assert dem in DEM_LEVELS, f"{iid}: bad Dem {dem!r}"
        assert n > 0
        assert nkmin > 0

    nkmin_values = [r[5] for r in SOURCE_ROWS]
    bounds = quintile_boundaries(nkmin_values)
    p20, p40, p60, p80 = bounds

    # Assign labels.
    rows_out: list[dict[str, str | int | float]] = []
    bin_counts: dict[str, int] = {q: 0 for q in QUINTILE_LABELS}
    for iid, n, dep, cust_raw, dem, nkmin in SOURCE_ROWS:
        label = label_for(nkmin, bounds)
        bin_counts[label] += 1
        rows_out.append({
            "instance_id": iid,
            "n_customers": n,
            "depot_position": dep,
            "customer_distribution": _strip_cust(cust_raw),
            "demand_pattern": dem,
            "avg_route_size": label,
            "n_kmin": f"{nkmin:.1f}",
        })

    # Build the header.
    header_lines = [
        "Uchoa-X classification table — 100 instances.",
        "",
        f"Source: Uchoa et al. 2017, Tables 11-13 (pages {SOURCE_PAGES} of preprint).",
        f"        {SOURCE_URL}",
        f"Transcribed: {TRANSCRIPTION_DATE} via scripts/build_classification_csv.py.",
        "",
        "Quintile boundaries for avg_route_size, computed empirically from",
        "the n_kmin column (numpy.percentile, linear interpolation):",
        f"  p20 = {p20:.4f}",
        f"  p40 = {p40:.4f}",
        f"  p60 = {p60:.4f}",
        f"  p80 = {p80:.4f}",
        "",
        "Bin semantics: VS: x ≤ p20, S: p20 < x ≤ p40, M: p40 < x ≤ p60,",
        "               L: p60 < x ≤ p80, VL: x > p80.",
        "",
        "Per-bin instance counts:",
        f"  VS = {bin_counts['VS']}",
        f"  S  = {bin_counts['S']}",
        f"  M  = {bin_counts['M']}",
        f"  L  = {bin_counts['L']}",
        f"  VL = {bin_counts['VL']}",
        "",
        "Verify with:  python scripts/verify_classification.py",
    ]
    header = "\n".join(f"# {ln}" if ln else "#" for ln in header_lines) + "\n"

    # Build the CSV body.
    buf = io.StringIO()
    fieldnames = [
        "instance_id", "n_customers",
        "depot_position", "customer_distribution",
        "demand_pattern", "avg_route_size", "n_kmin",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows_out:
        writer.writerow(row)
    return header + buf.getvalue()


def main() -> int:
    body = build_csv()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(body, encoding="utf-8")
    n_data_lines = sum(1 for ln in body.splitlines() if ln and not ln.startswith("#"))
    # n_data_lines includes the header row of the CSV.
    print(f"Wrote {OUTPUT_PATH} ({n_data_lines - 1} instance rows + 1 header row).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

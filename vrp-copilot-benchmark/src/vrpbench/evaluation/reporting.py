"""Tiny markdown helpers so we don't need `tabulate` as a dependency."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer():
            return str(int(v))
        return f"{v:.4g}"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def df_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "(empty)"
    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(_fmt(row[c]) for c in cols) + " |")
    return "\n".join([header, sep, *rows])

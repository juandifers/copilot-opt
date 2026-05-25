"""Instance-grouped folds for the baseline suite.

All rows from the same ``instance_id`` stay in the same fold so the
test-set rate estimates for block-rule policies can never see their own
labels at training time. Folds are class-balanced (C / R / RC) when
:func:`vrp_copilot_bench.predictor_baselines.data.instance_class_from_id`
returns a non-``?`` value: we sort instances within each class by id and
round-robin them across folds.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from .data import instance_class_from_id


def assign_instance_folds(
    instance_ids: Iterable[str],
    *,
    n_folds: int = 5,
) -> pd.DataFrame:
    """Round-robin instance → fold within Solomon class.

    Returns a frame with columns ``instance_id``, ``instance_class``,
    ``fold``.  Sorting by id within class gives a deterministic
    assignment; round-robin keeps class shares roughly equal across
    folds even when the class sizes are not divisible by ``n_folds``.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    rows: list[tuple[str, str, int]] = []
    by_class: dict[str, list[str]] = {}
    for iid in sorted(set(instance_ids)):
        by_class.setdefault(instance_class_from_id(iid), []).append(iid)
    for cls in sorted(by_class):
        for i, iid in enumerate(by_class[cls]):
            rows.append((iid, cls, i % n_folds))
    return pd.DataFrame(rows, columns=["instance_id", "instance_class", "fold"])

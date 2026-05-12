"""Internal helpers shared across perturbation family implementations."""
from __future__ import annotations

from typing import Sequence

import numpy as np


def argmin_with_tiebreak(values: Sequence[float] | Sequence[int]) -> int:
    """Index of the minimum value; ties → lowest index.

    Equivalent to ``min(range(len(values)), key=lambda i: (values[i], i))``
    but written as an explicit loop to keep behavior unambiguous on the
    tie-break path.
    """
    if not values:
        raise ValueError("argmin_with_tiebreak: empty input")
    best_v: int | float = values[0]
    best_i = 0
    for i, v in enumerate(values[1:], start=1):
        if v < best_v:
            best_v = v
            best_i = i
    return best_i


def argmax_with_tiebreak(values: Sequence[float] | Sequence[int]) -> int:
    """Index of the maximum value; ties → lowest index."""
    if not values:
        raise ValueError("argmax_with_tiebreak: empty input")
    best_v: int | float = values[0]
    best_i = 0
    for i, v in enumerate(values[1:], start=1):
        if v > best_v:
            best_v = v
            best_i = i
    return best_i


def compute_k_nn_spread(coords: np.ndarray, *, k: int) -> np.ndarray:
    """Mean distance to ``k`` nearest *customer* neighbors, per customer.

    Returns array of shape ``(n,)`` (n = customer count). The depot at row
    0 of ``coords`` is excluded from the neighbor pool. Self-distances are
    masked with ``inf`` before sorting.

    Used by:
      - DISTANCE family (DIST_1/DIST_2 density partitioning, prereg §6.2)
      - INSERTION family (INS_4 low-density centroid, prereg §6.4)

    Requires ``n >= k + 1`` (every customer must have at least k other
    customer neighbors). For Uchoa-X this is far above threshold.
    """
    customer_coords = coords[1:]
    n = customer_coords.shape[0]
    if n < k + 1:
        raise ValueError(
            f"compute_k_nn_spread: need n >= k+1, got n={n}, k={k}"
        )
    diff = customer_coords[:, None, :] - customer_coords[None, :, :]
    dists = np.sqrt((diff ** 2).sum(axis=2))
    np.fill_diagonal(dists, np.inf)
    sorted_dists = np.sort(dists, axis=1)
    return sorted_dists[:, :k].mean(axis=1)

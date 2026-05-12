"""Work-plan enumeration for the Stage A dispatch.

Total Stage A action-run space:

- **Base grid** (every cell): 75 instances × 16 perturbations × 5 actions
  = 6,000 keys. Feeds 4 cell-action rows per key at consolidation time
  (one per claim family) for 24,000 prereg §4.1 rows.
- **Audit subset** (prereg §8.2): two extra ``pyvrp_60s`` runs at seeds 2/3
  on a 20% stratified-sample subset of cells. The compute work is keyed by
  unique ``(instance_id, perturbation_id)`` pairs in the audit subset
  (multiple cells of the same pair share the same solver run).

This module is a thin layer over :mod:`vrp_copilot_bench.instances`,
:mod:`vrp_copilot_bench.perturbations`, and :mod:`vrp_copilot_bench.actions`.
The dispatcher in :mod:`vrp_copilot_bench.runner` consumes the ordered list
returned by :func:`order_by_size` after :func:`filter_completed`.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .actions import ACTIONS, AUDIT_ACTIONS, BASE_ACTIONS
from .checkpoint import ActionRunKey, list_completed, list_failures
from .instances import list_stage_a_instances, n_customers_for
from .perturbations import enumerate_perturbations

# Re-exported so callers can ``from vrp_copilot_bench.work_plan import ActionRunKey``
# as the prompt's Phase 2 API specifies. The on-disk format owns the type so
# it physically lives in :mod:`checkpoint`.
__all__ = [
    "ActionRunKey",
    "ACTIONS",
    "BASE_ACTIONS",
    "AUDIT_ACTIONS",
    "CLAIM_FAMILIES",
    "AUDIT_RNG_SEED",
    "AUDIT_FRACTION",
    "select_audit_subset",
    "enumerate_stage_a",
    "order_by_size",
    "filter_completed",
    "is_large_instance",
    "DEFAULT_LARGE_THRESHOLD",
]

log = logging.getLogger(__name__)

#: Claim families per prereg §3.2. Ordering is fixed for stratification
#: determinism. PLAN_VALIDITY is included even though its operational
#: sufficiency is True by construction — it is one of the four cells per
#: (instance, pert) and counts toward the 4,800-cell total in §8.2.
#: Claim families per prereg §3.2. Kept here because consolidation (Phase 4)
#: will fan out one action-run row to four cell-action rows by claim family.
#: PLAN_VALIDITY is included even though its operational sufficiency is True
#: by construction.
CLAIM_FAMILIES: tuple[str, ...] = ("OBJ", "PLAN_VALIDITY", "STRUCT", "RANK")

AUDIT_RNG_SEED: int = 20260429
AUDIT_FRACTION: float = 0.20

# Cheap → expensive. Used as the secondary sort key inside an instance.
# Audit variants of pyvrp_60s share a tier with pyvrp_60s but sort after it
# so the primary reference completes first within an audit-elected pair.
_ACTION_COST_RANK: dict[str, int] = {
    "reuse_direct": 0,
    "nearest_neighbor": 1,
    "clarke_wright": 2,
    "pyvrp_10s": 3,
    "pyvrp_60s": 4,
    "pyvrp_60s_seed2": 5,
    "pyvrp_60s_seed3": 6,
}
assert set(_ACTION_COST_RANK) == set(ACTIONS), "action cost rank out of sync with ACTIONS"

DEFAULT_LARGE_THRESHOLD: int = 400


# ---------------------------------------------------------------------------
# Audit subset selection (prereg §8.2)


def _perturbation_family_short(perturbation_id: str) -> str:
    return perturbation_id.split("_", 1)[0]


def select_audit_subset(
    seed: int = AUDIT_RNG_SEED,
    fraction: float = AUDIT_FRACTION,
) -> frozenset[tuple[str, str]]:
    """Deterministic stratified sample of audit ``(instance, perturbation)`` pairs.

    Per prereg §8.2 (with the v0.2 amendment clarifying that audit work is
    keyed at the *pair* layer, not the cell layer): the audit produces one
    extra ``pyvrp_60s`` solve per seed per pair, and the resulting
    assignment / objective / top-3 ranking are shared across all four
    claim-family rows of that pair at consolidation time. Sampling at the
    cell layer would cause the same solver work to be requested up to four
    times for one pair, with no benefit to the per-cell stability checks.

    Stage A: 1,200 ``(instance, perturbation)`` pairs total. 4 perturbation
    families × 4 perturbations × 75 instances = 300 pairs per family.
    Sampling 20% per family yields 60 pairs per family × 4 = **240 pairs**.
    Each sampled pair contributes two audit ActionRunKeys (seed 2 + seed 3)
    in :func:`enumerate_stage_a`.

    Pure function of the perturbation grid and the instance roster — no
    solver output is read.
    """
    rng = np.random.default_rng(seed)

    # Bucket all 1,200 pairs by perturbation family.
    pairs_by_family: dict[str, list[tuple[str, str]]] = {}
    for instance_id in list_stage_a_instances():
        for spec in enumerate_perturbations(instance_id):
            family_short = _perturbation_family_short(spec.perturbation_id)
            pairs_by_family.setdefault(family_short, []).append(
                (instance_id, spec.perturbation_id)
            )

    selected: set[tuple[str, str]] = set()
    # Iterate strata in a fixed order so the seeded RNG draws are reproducible.
    for family in sorted(pairs_by_family.keys()):
        family_pairs = sorted(pairs_by_family[family])
        n_sample = round(len(family_pairs) * fraction)
        if n_sample == 0:
            continue
        indices = rng.choice(len(family_pairs), size=n_sample, replace=False)
        for i in indices:
            selected.add(family_pairs[int(i)])

    return frozenset(selected)


# ---------------------------------------------------------------------------
# Enumeration


def enumerate_stage_a() -> list[ActionRunKey]:
    """Cartesian product of (instances, perturbations, base actions) plus
    audit keys for the 240-pair stratified audit subset.

    Stage A: 6,000 base keys + 480 audit keys = **6,480** total. Returned
    in deterministic but unsorted-by-size order; use :func:`order_by_size`
    before dispatch.
    """
    out: list[ActionRunKey] = []

    # Base grid: 75 × 16 × 5 = 6,000.
    for instance_id in list_stage_a_instances():
        for spec in enumerate_perturbations(instance_id):
            for action in BASE_ACTIONS:
                out.append(ActionRunKey(instance_id, spec.perturbation_id, action))

    # Audit: 240 pairs × 2 audit actions = 480 keys.
    for instance_id, perturbation_id in sorted(select_audit_subset()):
        for action in AUDIT_ACTIONS:
            out.append(ActionRunKey(instance_id, perturbation_id, action))

    return out


# ---------------------------------------------------------------------------
# Ordering


def _sort_key(key: ActionRunKey) -> tuple[int, int, str, str]:
    """Primary: n_customers ascending. Secondary: cheap action first.
    Tertiary/quaternary: instance_id, perturbation_id for full determinism.
    """
    return (
        n_customers_for(key.instance_id),
        _ACTION_COST_RANK[key.action],
        key.instance_id,
        key.perturbation_id,
    )


def order_by_size(keys: list[ActionRunKey]) -> list[ActionRunKey]:
    """Sort keys for dispatch.

    Smallest instances first so the checkpoint store fills quickly with
    cheap successes — bugs in the runner surface within minutes rather than
    hours. Within an instance, cheap actions (reuse → NN → CW) precede
    pyvrp_10s, pyvrp_60s, and the two audit seeds, for the same reason.
    """
    return sorted(keys, key=_sort_key)


# ---------------------------------------------------------------------------
# Resumability


def filter_completed(keys: list[ActionRunKey], checkpoint_dir: Path) -> list[ActionRunKey]:
    """Drop keys with a successful checkpoint; keep failures so they retry.

    Logs ``X completed, Y remaining, Z failures (will retry)`` at INFO so a
    resumed run states what it's about to do. Failures are *not* filtered:
    the runner will rerun them, overwriting the failure record on success.
    """
    completed = list_completed(checkpoint_dir)
    failures = list_failures(checkpoint_dir)
    remaining = [k for k in keys if k not in completed]
    log.info(
        "%d completed, %d remaining, %d failures (will retry)",
        len(completed),
        len(remaining),
        len(failures),
    )
    return remaining


def is_large_instance(key: ActionRunKey, threshold: int = DEFAULT_LARGE_THRESHOLD) -> bool:
    """True iff the instance has *more than* ``threshold`` customers.

    Used by the dispatcher to drop worker count for memory-heavy keys.
    Strict inequality matches the prompt's wording: "Instances above 400
    customers must be dispatched at reduced concurrency".
    """
    return n_customers_for(key.instance_id) > threshold

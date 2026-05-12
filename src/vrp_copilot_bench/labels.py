"""Loss and band computation per prereg §9.

Two public entry points:

- :func:`compute_losses_and_bands` for per-row loss/band fields.
- :func:`compute_audit_fields` for the multi-seed stability check fields
  (only populated for the 240 audit-subset (instance, perturbation) pairs;
  see prereg §8.2).

Item 6 wired the structural and ranking losses into real computations:

- ``loss_struct`` — 1 minus ARI between action and reference assignments
  (§9.3). Customers absent from an action's assignment (the partial-coverage
  case for ``reuse_direct`` on INSERTION) are treated as a distinct cluster
  via the sentinel label ``-1``.
- ``loss_rank`` — 1 minus top-3 baseline-group Jaccard (§9.4). Per-baseline-
  group impact under a plan is the *delta* of summed customer costs vs the
  baseline solution's customer-cost contribution on the same group:

      impact(g, plan) = sum_{c in g} plan.customer_costs[c]
                      - sum_{c in g} baseline.customer_costs[c]

  The delta form measures *which baseline groups changed* under the
  perturbation, not which are absolutely expensive — so the highest-cost
  baseline route does not dominate the top-3 by default. The metric only
  surfaces it when the perturbation actually increased its cost relative
  to the baseline.

- ``reference_struct_unstable`` — pairwise minimum ARI across the three seeds
  is below 0.90 (§8.2).
- ``reference_rank_unstable`` — pairwise minimum top-3 Jaccard across the
  three seeds is below 0.50 (§8.2).
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.metrics import adjusted_rand_score

from .actions import ActionResult
from .baselines import Solution

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Loss / band labels (per row)


@dataclass(frozen=True)
class LossLabels:
    """All four loss/band columns for one cell-action row.

    Per §9, every row carries a loss value for each of the four claim
    families regardless of the row's tagged claim_family. The tagged family
    only selects which loss drives sufficiency labelling.

    Fields containing NaN/empty signal "not applicable" — most notably
    ``loss_plan_validity`` and ``band_plan_validity`` are populated only on
    PLAN_VALIDITY × reuse_direct rows (§9.2).
    """

    loss_obj: float
    loss_plan_validity: float  # NaN unless PLAN_VALIDITY × reuse_direct
    loss_struct: float
    loss_rank: float
    band_obj: Optional[str]    # None when loss_obj is NaN
    band_plan_validity: Optional[str]  # None unless PLAN_VALIDITY × reuse_direct
    band_struct: Optional[str]  # None when loss_struct is NaN
    band_rank: Optional[str]    # None when loss_rank is NaN


def _band_obj(loss_obj: float) -> Optional[str]:
    """Per §9.1 thresholds. Returns ``None`` (→ pd.NA) when the loss is
    NaN — consistent with the rest of the nullable string schema and
    plays nicely with ``df["band_obj"].isna()`` in downstream code."""
    if math.isnan(loss_obj):
        return None
    if loss_obj <= 0.05:
        return "easy"
    if loss_obj <= 0.15:
        return "medium"
    return "hard"


def _band_struct(loss_struct: float) -> Optional[str]:
    """Per §9.3 thresholds (1 - ARI cutoffs); ``None`` on NaN."""
    if math.isnan(loss_struct):
        return None
    if loss_struct <= 0.10:
        return "easy"
    if loss_struct <= 0.30:
        return "medium"
    return "hard"


def _band_rank(loss_rank: float) -> Optional[str]:
    """Per §9.4 thresholds (1 - top3 Jaccard cutoffs); ``None`` on NaN."""
    if math.isnan(loss_rank):
        return None
    if loss_rank <= 0.50:
        return "easy"
    if loss_rank <= 0.80:
        return "medium"
    return "hard"


# ---------------------------------------------------------------------------
# Structural loss (ARI)


def _assignment_label_arrays(
    action_assignment: dict[int, int],
    reference_assignment: dict[int, int],
    *,
    unassigned_label: int = -1,
) -> tuple[np.ndarray, np.ndarray]:
    """Build the two label arrays ARI consumes, in customer-id order.

    The canonical universe is ``{1, ..., n}`` where ``n = max(reference_assignment)``.
    The reference always has full coverage (PyVRP produces no partial plans),
    so this is well-defined.

    Customers absent from ``action_assignment`` are mapped to
    ``unassigned_label`` (default ``-1``), which becomes a distinct cluster
    in the action partition. This is the explicit policy from Item 5 §3:
    partial-coverage actions surface their unassigned customers via the
    same ``-1`` sentinel that ``reuse_direct`` writes into ``ActionResult.assignment``.

    Returns ``(reference_labels, action_labels)`` as int numpy arrays, ordered
    by customer id 1..n.
    """
    if not reference_assignment:
        # Empty reference: ARI is undefined; emit zero-length arrays.
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    n = max(reference_assignment)
    customers = range(1, n + 1)
    reference_labels = np.fromiter(
        (reference_assignment[c] for c in customers), dtype=np.int64, count=n
    )
    action_labels = np.fromiter(
        (action_assignment.get(c, unassigned_label) for c in customers),
        dtype=np.int64,
        count=n,
    )
    return reference_labels, action_labels


def _compute_loss_struct(
    action: ActionResult,
    reference: ActionResult,
) -> float:
    """Compute structural loss as ``1 - ARI`` between action and reference
    assignments.

    Both label arrays are built over the canonical customer universe in
    customer-id order via :func:`_assignment_label_arrays`. ARI is computed
    via :func:`sklearn.metrics.adjusted_rand_score` — deterministic and the
    de facto standard for clustering comparison.

    ARI's range is [-1, 1]; the loss therefore ranges over [0, 2]. In
    practice ARI sits in [0, 1] for non-pathological partitions, putting
    the loss in [0, 1].
    """
    reference_labels, action_labels = _assignment_label_arrays(
        action.assignment, reference.assignment
    )
    if reference_labels.size == 0:
        return math.nan
    ari = adjusted_rand_score(reference_labels, action_labels)
    return 1.0 - float(ari)


def _pairwise_ari(
    a: dict[int, int], b: dict[int, int]
) -> float:
    """Compute ARI between two assignments using the canonical universe of
    ``a``'s keys (the audit reference's universe). Both inputs are PyVRP
    full-coverage solutions, so picking either side as the canonical
    universe is equivalent."""
    labels_a, labels_b = _assignment_label_arrays(b, a)
    if labels_a.size == 0:
        return math.nan
    return float(adjusted_rand_score(labels_a, labels_b))


# ---------------------------------------------------------------------------
# Ranking loss (top-3 baseline-group Jaccard)


def _compute_baseline_group_impacts(
    plan_customer_costs: dict[int, float],
    baseline_assignment: dict[int, int],
    baseline_customer_costs: dict[int, float],
) -> dict[int, float]:
    """For each baseline group g, return the delta-impact under ``plan``.

    Per prereg §9.4::

        impact(g, plan) = sum_{c in g} plan_costs[c]
                        - sum_{c in g} baseline_costs[c]

    Customers absent from ``plan_customer_costs`` (partial coverage from
    ``reuse_direct`` on INSERTION) contribute 0.0 on the action side and
    the full baseline cost on the subtracted side — so their group's
    impact reflects the cost they were "removed" from carrying.

    Customers absent from ``baseline_assignment`` (NEW customers from
    INSERTION) have no baseline group; they are excluded from the
    aggregation. The `-1` sentinel is also excluded by the same path.

    Returns ``{baseline_group_id → delta_impact}``. A group's entry exists
    iff at least one customer in the baseline plan is in that group; the
    set of returned keys is therefore exactly the set of baseline route
    indices.
    """
    impacts: dict[int, float] = {}
    for c, group in baseline_assignment.items():
        if group < 0:
            continue
        plan_term = plan_customer_costs.get(c, 0.0)
        baseline_term = baseline_customer_costs.get(c, 0.0)
        impacts[group] = impacts.get(group, 0.0) + (plan_term - baseline_term)
    return impacts


def _top_n_groups(impacts: dict[int, float], n: int = 3) -> list[int]:
    """Return the top ``n`` baseline-group IDs by impact, ties broken by
    lowest ID. If fewer than ``n`` groups exist, returns all of them.

    Sort key is ``(-impact, group_id)`` so descending impact first then
    ascending group_id. Documented in §9.4: "for instances with fewer
    than 3 baseline routes, top-k is reduced to top-min(3, n_routes_baseline)".
    """
    if not impacts:
        return []
    k = min(n, len(impacts))
    items = sorted(impacts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [g for g, _ in items[:k]]


def _top_n_jaccard(top_a: list[int], top_b: list[int]) -> float:
    """Jaccard between two top-N group-ID lists treated as sets.

    Returns 0.0 if both are empty (consistent with "no overlap" semantics);
    callers that want NaN on that case must check beforehand.
    """
    set_a, set_b = set(top_a), set(top_b)
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _compute_loss_rank(
    action: ActionResult,
    reference: ActionResult,
    baseline: Solution,
) -> float:
    """Compute ranking loss as ``1 - top-N baseline-group Jaccard`` (§9.4).

    The action and reference per-baseline-group impacts are computed in
    delta form against the baseline's per-customer cost contributions
    (see :func:`_compute_baseline_group_impacts`). The top-N (default 3,
    reduced to ``min(3, n_baseline_groups)`` on small instances) baseline
    groups by impact form the two sets compared via Jaccard.

    Tie-breaking on the top-N selection is by lowest baseline-group ID.

    Edge cases:

    - Empty ``action.customer_costs``: the action produced no cost
      attribution. This is unusual — every Stage A action wrapper writes
      per-customer marginal costs by construction. We log a warning and
      return NaN; the labels module's contract is that empty action
      results don't reach it, but the runner is the only layer that
      catches such pathologies and a NaN here at least fails the schema
      check loudly rather than silently writing 1.0.
    - Both top-N sets empty (baseline has no routes): returns NaN.
    """
    if not action.customer_costs:
        logger.warning(
            "loss_rank: action %s has empty customer_costs; returning NaN",
            action.action,
        )
        return math.nan

    action_impacts = _compute_baseline_group_impacts(
        action.customer_costs, baseline.assignment, baseline.customer_costs
    )
    reference_impacts = _compute_baseline_group_impacts(
        reference.customer_costs, baseline.assignment, baseline.customer_costs
    )
    top_action = _top_n_groups(action_impacts, n=3)
    top_reference = _top_n_groups(reference_impacts, n=3)
    if not top_action and not top_reference:
        return math.nan
    return 1.0 - _top_n_jaccard(top_action, top_reference)


def compute_losses_and_bands(
    action_result: ActionResult,
    reference_result: ActionResult,
    claim_family: str,
    baseline: Solution,
) -> LossLabels:
    """Compute the 8 loss/band fields for a single cell-action row.

    Pure: same inputs → same outputs. Both ARI (§9.3) and top-3 Jaccard
    (§9.4) are deterministic.

    Phase B added the ``baseline`` argument: ranking loss requires the
    baseline solution's per-customer cost contributions to compute
    impact deltas against. Callers that previously omitted this argument
    must thread it through.
    """
    # §9.1: loss_obj = |action_obj - ref_obj| / ref_obj
    #
    # Guard covers three degenerate cases:
    #   - None objective (solver crash with no plan)
    #   - ref_obj == 0 (would divide by zero)
    #   - ref_obj == inf (PyVRP penalized-cost solver returns inf when every
    #     feasible solution would require a customer whose individual demand
    #     exceeds vehicle capacity — DEM_4 can trigger this on tight-capacity
    #     instances). abs(x - inf) / inf == nan via IEEE 754, which then
    #     propagates into band_obj = None and trips the required-non-null
    #     schema check. We catch inf explicitly and label the cell "hard"
    #     (the reference itself is degenerate; conservative label).
    # §9.1: loss_obj = |action_obj - ref_obj| / ref_obj
    #
    # Guard covers degenerate objectives:
    #   - None: solver crash with no plan.
    #   - ref == 0: theoretical (VRP costs are always positive); avoids ZeroDivision.
    #   - ref == inf: PyVRP returns inf when demand inflation (DEM_4 on tight-capacity
    #     instances) produces individual customer demands > vehicle capacity. The
    #     penalized-cost objective is then unbounded. abs(x - inf) / inf = nan via
    #     IEEE 754; we return inf instead so loss_obj stays non-null (required) and
    #     _band_obj(inf) correctly returns "hard".
    ref_obj = reference_result.objective
    action_obj = action_result.objective
    if action_obj is None or ref_obj is None or ref_obj == 0:
        loss_obj = math.nan
    elif not math.isfinite(float(ref_obj)):
        loss_obj = math.inf  # degenerate reference; cell is unconditionally hard
    else:
        loss_obj = abs(float(action_obj) - float(ref_obj)) / float(ref_obj) if math.isfinite(float(action_obj)) else math.inf

    # §9.2: loss_plan_validity is 0 only on (PLAN_VALIDITY, reuse_direct).
    # Reuse_direct's pipeline runs the deterministic feasibility check on S
    # under the perturbation, so by construction it reports the correct
    # verdict — loss is 0.
    if claim_family == "PLAN_VALIDITY" and action_result.action == "reuse_direct":
        loss_plan_validity = 0.0
        band_plan_validity: Optional[str] = "easy"
    else:
        loss_plan_validity = math.nan
        band_plan_validity = None

    # §9.3: 1 - ARI(action_assignment, reference_assignment).
    loss_struct = _compute_loss_struct(action_result, reference_result)

    # §9.4: 1 - top-3 baseline-group Jaccard, delta form.
    loss_rank = _compute_loss_rank(action_result, reference_result, baseline)

    return LossLabels(
        loss_obj=loss_obj,
        loss_plan_validity=loss_plan_validity,
        loss_struct=loss_struct,
        loss_rank=loss_rank,
        band_obj=_band_obj(loss_obj),
        band_plan_validity=band_plan_validity,
        band_struct=_band_struct(loss_struct),
        band_rank=_band_rank(loss_rank),
    )


# ---------------------------------------------------------------------------
# Audit fields (per (instance, perturbation) pair)


@dataclass(frozen=True)
class AuditFields:
    """The audit-related columns from prereg §4.1.

    All-None when the (instance, perturbation) pair is not in the audit
    subset; populated when both seed-2 and seed-3 audit results are
    available alongside the seed-1 reference.
    """

    seed_2_obj: Optional[float]
    seed_3_obj: Optional[float]
    seed_2_assignment: Optional[str]  # JSON-encoded customer→route map
    seed_3_assignment: Optional[str]
    seed_2_top3: Optional[str]  # JSON-encoded list of top-3 baseline-group ids
    seed_3_top3: Optional[str]
    obj_unstable: Optional[bool]
    struct_unstable: Optional[bool]
    rank_unstable: Optional[bool]


_NULL_AUDIT = AuditFields(
    seed_2_obj=None, seed_3_obj=None,
    seed_2_assignment=None, seed_3_assignment=None,
    seed_2_top3=None, seed_3_top3=None,
    obj_unstable=None, struct_unstable=None, rank_unstable=None,
)


def null_audit_fields() -> AuditFields:
    """Returns the all-None AuditFields used for non-audit-subset pairs."""
    return _NULL_AUDIT


def _obj_unstable(*objs: Optional[float]) -> Optional[bool]:
    """Per §8.2: ``(max - min) / min > 0.02`` across the three seeds.

    Returns None if any objective is missing or non-positive.
    """
    if any(o is None for o in objs):
        return None
    if min(objs) <= 0:  # type: ignore[type-var]
        return None
    return (max(objs) - min(objs)) / min(objs) > 0.02  # type: ignore[type-var]


def _compute_reference_struct_unstable(
    reference: ActionResult,
    seed2: ActionResult,
    seed3: ActionResult,
    threshold: float = 0.10,
) -> bool:
    """Per §8.2: True iff the minimum pairwise ARI across the three seeds is
    below ``1 - threshold`` (default 0.90).

    Why "minimum pairwise": if any two seeds disagree structurally beyond the
    threshold, the cell is unstable — even if the third seed happens to agree
    with one of them. This matches the prereg's "min over (i,j) of ARI(...) <
    0.90" formulation.

    The boundary is strict inequality: ARI exactly 0.90 is *not* unstable.
    """
    pairs = (
        (reference.assignment, seed2.assignment),
        (reference.assignment, seed3.assignment),
        (seed2.assignment, seed3.assignment),
    )
    min_ari = min(_pairwise_ari(a, b) for a, b in pairs)
    return min_ari < (1.0 - threshold)


def _compute_reference_rank_unstable(
    reference: ActionResult,
    seed2: ActionResult,
    seed3: ActionResult,
    baseline: Solution,
    threshold: float = 0.50,
) -> bool:
    """Per §8.2: True iff the minimum pairwise top-3 baseline-group Jaccard
    across the three seeds is below ``threshold`` (default 0.50).

    Why a looser threshold than STRUCT's 0.10: top-3 sets only have ~3
    elements; a single rotation between adjacent ranks already drops
    Jaccard from 1.0 to 0.5 (e.g., {0,1,2} ↔ {0,1,3} → Jaccard = 0.5).
    The 0.50 cutoff catches the cases where the rotation goes deeper than
    one swap.

    Strict inequality at the boundary: Jaccard exactly 0.50 → not unstable.
    """
    seeds = (reference, seed2, seed3)
    tops: list[list[int]] = []
    for s in seeds:
        impacts = _compute_baseline_group_impacts(
            s.customer_costs, baseline.assignment, baseline.customer_costs
        )
        tops.append(_top_n_groups(impacts, n=3))
    min_jaccard = min(
        _top_n_jaccard(tops[0], tops[1]),
        _top_n_jaccard(tops[0], tops[2]),
        _top_n_jaccard(tops[1], tops[2]),
    )
    return min_jaccard < threshold


def compute_audit_fields(
    reference: ActionResult,
    seed2: Optional[ActionResult],
    seed3: Optional[ActionResult],
    baseline: Solution,
) -> AuditFields:
    """Compute the audit-row contributions for one (instance, perturbation) pair.

    Returns the all-None ``AuditFields`` if either audit result is missing
    (consolidate treats this as an integrity violation, not as a normal
    null-fill — the runner only emits seed2/seed3 keys for audit pairs).

    Phase B added the ``baseline`` argument so the top-3 baseline-group
    lists and the rank-stability flag can be computed with real impact
    deltas.
    """
    if seed2 is None or seed3 is None:
        return _NULL_AUDIT

    seed2_impacts = _compute_baseline_group_impacts(
        seed2.customer_costs, baseline.assignment, baseline.customer_costs
    )
    seed3_impacts = _compute_baseline_group_impacts(
        seed3.customer_costs, baseline.assignment, baseline.customer_costs
    )
    seed2_top3 = _top_n_groups(seed2_impacts, n=3)
    seed3_top3 = _top_n_groups(seed3_impacts, n=3)

    return AuditFields(
        seed_2_obj=seed2.objective,
        seed_3_obj=seed3.objective,
        seed_2_assignment=json.dumps(
            {str(k): v for k, v in seed2.assignment.items()},
            sort_keys=True,
        ),
        seed_3_assignment=json.dumps(
            {str(k): v for k, v in seed3.assignment.items()},
            sort_keys=True,
        ),
        seed_2_top3=json.dumps(seed2_top3),
        seed_3_top3=json.dumps(seed3_top3),
        obj_unstable=_obj_unstable(reference.objective, seed2.objective, seed3.objective),
        struct_unstable=_compute_reference_struct_unstable(reference, seed2, seed3),
        rank_unstable=_compute_reference_rank_unstable(reference, seed2, seed3, baseline),
    )

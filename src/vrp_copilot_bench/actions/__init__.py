"""Action wrappers for Stage A.

The seven dispatchable actions per prereg §7 plus §8.2 audit variants:

- ``reuse_direct`` — re-evaluate the baseline solution under the perturbed instance.
- ``nearest_neighbor`` — greedy NN construction on the perturbed instance.
- ``clarke_wright`` — CW savings on the perturbed instance.
- ``pyvrp_10s`` / ``pyvrp_60s`` — PyVRP solves with seed=1.
- ``pyvrp_60s_seed2`` / ``pyvrp_60s_seed3`` — audit variants (audit subset only).

Phase A introduces:

- :class:`ActionResult` (preserved from the prior stub) — common output shape.
- :func:`reuse_direct` — first real action.
- :mod:`vrp_copilot_bench.actions.evaluate` — shared evaluator and the single
  source of truth for the perturbed distance matrix.

Phases B and C add the heuristic and PyVRP wrappers and the
:func:`run_action` dispatcher.

Field naming follows the in-memory convention (``n_overload``, etc.); the
parquet column names (``action_n_overload``, etc.) are added by the
consolidation pass per prereg §4.1.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionResult:
    """Outcome of running a single action against a perturbed instance.

    All fields except ``routes`` and ``meta`` are required: consolidation needs
    them to compute the four loss families specified in prereg §9.

    - ``objective`` may be ``None`` only if ``feasible`` is False *and* the
      action could not produce any plan (rare; e.g. solver crash with partial
      output). Standard reuse_direct / NN / CW always produce a plan and an
      objective; pyvrp may emit an infeasible plan but always with an objective.
    - ``assignment`` maps customer_id → route_id. Customer ids start at 1
      (depot is conventionally 0). Route ids are arbitrary but must be
      consistent with ``route_costs``. Customers that an action could not
      cover (e.g. INSERTION's new customers under ``reuse_direct``) appear
      with route_id ``-1``; this is the explicit-unassignment convention
      from Item 5 §3.
    - ``route_costs`` maps route_id → cost under the *perturbed* instance
      (per §4.1 ``action_route_costs``).
    - ``customer_costs`` maps customer_id → marginal-insertion cost under
      the *perturbed* distance matrix. The action wrapper populates this as

          customer_cost[c] = d[prev, c] + d[c, next] - d[prev, next]

      where ``prev`` and ``next`` are the customer's neighbours along the
      action's route (depot at route ends). This is the per-customer
      "removal-cost" attribution; consolidation sums it over baseline groups
      to compute §9.4 ranking-loss impacts. Unassigned customers (route_id
      ``-1``) have no entry in ``customer_costs``.
    - ``n_overload`` and ``max_overload_fraction`` describe operational
      validity under the perturbed capacity (§4.1, §13.2 predictor features).
      For feasible plans, ``n_overload == 0`` and ``max_overload_fraction == 0.0``.
    """

    action: str
    objective: float | None
    feasible: bool
    runtime_seconds: float
    n_overload: int
    max_overload_fraction: float
    assignment: dict[int, int]
    route_costs: dict[int, float]
    customer_costs: dict[int, float]
    routes: list[list[int]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict.

        ``json.dump`` coerces int dict keys to strings; we do that explicitly
        here so :meth:`from_dict` has a fixed contract on what comes back.
        """
        d = asdict(self)
        d["assignment"] = {str(k): int(v) for k, v in self.assignment.items()}
        d["route_costs"] = {str(k): float(v) for k, v in self.route_costs.items()}
        d["customer_costs"] = {str(k): float(v) for k, v in self.customer_costs.items()}
        return d

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionResult":
        return cls(
            action=payload["action"],
            objective=payload.get("objective"),
            feasible=bool(payload["feasible"]),
            runtime_seconds=float(payload["runtime_seconds"]),
            n_overload=int(payload["n_overload"]),
            max_overload_fraction=float(payload["max_overload_fraction"]),
            assignment={int(k): int(v) for k, v in payload["assignment"].items()},
            route_costs={int(k): float(v) for k, v in payload["route_costs"].items()},
            customer_costs={int(k): float(v) for k, v in payload["customer_costs"].items()},
            routes=[list(route) for route in payload.get("routes", [])],
            meta=dict(payload.get("meta", {})),
        )


class ActionFailure(RuntimeError):
    """Raised by an action implementation when it cannot produce any plan.

    Examples:
        - NN/CW: a single customer's demand exceeds vehicle capacity.

    The runner's exception handler catches this and writes a failure
    record. :func:`run_action` does **not** catch it.
    """


#: The five Stage A actions evaluated on every (instance, perturbation) cell.
BASE_ACTIONS: tuple[str, ...] = (
    "reuse_direct",
    "nearest_neighbor",
    "clarke_wright",
    "pyvrp_10s",
    "pyvrp_60s",
)

#: PyVRP 60s reference solves at additional seeds (per prereg §8.2). These
#: run only on the audit subset, not the full grid; selection is performed
#: by :func:`vrp_copilot_bench.work_plan.select_audit_subset`.
AUDIT_ACTIONS: tuple[str, ...] = (
    "pyvrp_60s_seed2",
    "pyvrp_60s_seed3",
)

#: All actions the runner may dispatch. Note that AUDIT_ACTIONS are *not*
#: enumerated for every (instance, perturbation) — only on the audit subset.
ACTIONS: tuple[str, ...] = BASE_ACTIONS + AUDIT_ACTIONS


# --- Action implementations --------------------------------------------------
#
# Late imports below: by deferring these until after ``ActionResult`` /
# ``ActionFailure`` / ``ACTIONS`` etc. are defined, submodules of this
# package may freely ``from . import ActionResult`` etc. without import-cycle
# headaches. The submodules pull their own dependencies (``baselines``,
# ``solvers.pyvrp_wrapper``) which never reach back into this ``__init__``
# module's pre-late-import section, so cycles are structurally avoided.
from .reuse_direct import reuse_direct  # noqa: E402
from .heuristic_actions import (  # noqa: E402
    clarke_wright_action,
    nearest_neighbor_action,
)
from .pyvrp_actions import (  # noqa: E402
    pyvrp_10s,
    pyvrp_60s,
    pyvrp_60s_seed2,
    pyvrp_60s_seed3,
)


#: Map from action name (the strings in ``ACTIONS``) to the implementation
#: function that produces an :class:`ActionResult`. All implementations
#: have the signature ``(perturbed: PerturbedInstance, baseline: Solution)
#: → ActionResult``; the heuristic and PyVRP variants ignore ``baseline``
#: (accepted for signature uniformity) while ``reuse_direct`` reads it.
_ACTION_IMPLEMENTATIONS = {
    "reuse_direct": reuse_direct,
    "nearest_neighbor": nearest_neighbor_action,
    "clarke_wright": clarke_wright_action,
    "pyvrp_10s": pyvrp_10s,
    "pyvrp_60s": pyvrp_60s,
    "pyvrp_60s_seed2": pyvrp_60s_seed2,
    "pyvrp_60s_seed3": pyvrp_60s_seed3,
}
assert set(_ACTION_IMPLEMENTATIONS) == set(ACTIONS), (
    "_ACTION_IMPLEMENTATIONS must cover the full ACTIONS tuple"
)


def run_action(
    action_name: str,
    perturbed_instance: Any,
    baseline_solution: Any,
) -> ActionResult:
    """Dispatch ``action_name`` to its implementation; return the result.

    All seven dispatchable actions in :data:`ACTIONS` are routed via the
    same map. The signature accepts opaque ``Any`` for the perturbed and
    baseline arguments so the runner's smoke-test harness (which feeds
    synthetic dicts) keeps working; real callers pass
    :class:`vrp_copilot_bench.perturbations.types.PerturbedInstance` and
    :class:`vrp_copilot_bench.baselines.Solution`.

    Failure handling: this function does **not** catch
    :class:`ActionFailure` (or any other exception). The runner
    (:func:`vrp_copilot_bench.runner.run_one_action`) is the layer that
    catches and serialises failure records — letting them bubble through
    the dispatcher is what makes the runner's failure-record path work.

    Raises
    ------
    ValueError
        If ``action_name`` is not one of :data:`ACTIONS`.
    """
    try:
        impl = _ACTION_IMPLEMENTATIONS[action_name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown action: {action_name!r}; expected one of {ACTIONS}"
        ) from exc
    return impl(perturbed_instance, baseline_solution)

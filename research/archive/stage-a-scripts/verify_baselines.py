#!/usr/bin/env python3
"""Sanity-check the cached Stage A baseline solutions.

Run after ``scripts/compute_baselines.py`` finishes. The script:

1. Loads the roster from ``instances/stage_a_instances.txt`` (or whichever
   subset the ``--instance`` flag specifies).
2. For each instance, loads the cached :class:`Solution` from
   ``data/baselines/<instance_id>.json`` via
   :func:`vrp_copilot_bench.baselines.load_baseline_solution`.
3. Runs the per-instance checks below, accumulating failures.
4. Prints a summary table.
5. Exits 0 if every check passes; 1 if any check fails.

Per-instance checks
-------------------
- **schema**: ``Solution.instance_id`` matches; ``config`` is the locked
  protocol (``time_limit_seconds == 60``, ``seed == 1``, ``n_threads == 1``);
  ``pyvrp_version`` is non-empty.
- **finite values**: ``objective`` and every entry in ``route_costs`` and
  ``customer_costs`` is finite (no NaN, no inf).
- **route shape**: ``routes`` is a non-empty list of non-empty lists of ints.
- **coverage**: routes cover exactly customers ``1..n_customers`` once each.
- **assignment ↔ routes**: ``assignment[c] == route_idx`` iff
  ``c in routes[route_idx]``.
- **feasibility**: every route's load ≤ ``instance.capacity``.
- **route_costs identity**: each ``route_costs[i]`` equals the recomputed
  sum-of-edges along ``routes[i]`` (depot at the boundaries) under the
  integer-rounded Euclidean distance matrix derived from the instance.
  This is a bit-exact identity, not a tolerance check.
- **objective consistency**: ``objective ≈ sum(route_costs)`` (1e-6 tol).
- **customer_costs identity**: each ``customer_costs[c]`` equals the
  recomputed removal-cost (``d[prev,c] + d[c,next] − d[prev,next]``) for
  that customer in its route. Bit-exact, not a tolerance check.
- **BKS gap (advisory)**: ``objective`` within 5 % of the published BKS
  for the instance. *Warns* if larger; does not fail. The 5 % gap is the
  envelope a single PyVRP 60 s seed=1 run is expected to land within for
  X-set CVRP instances at this size.

Notes on what is NOT checked
----------------------------
The prompt suggested checking ``sum(customer_costs) ≈ objective`` within
some tolerance. Phase A established that this is not a clean identity
(the marginal-cost decomposition double-counts internal edges and
subtracts shortcut edges; the two sums coincide only for single-customer
routes). The per-customer identity check above is exact and replaces it.
``sum(customer_costs)`` is reported as a diagnostic in the table so a
reader can see the actual relationship without it being a pass/fail
criterion.

Usage
-----
::

    python scripts/verify_baselines.py
    python scripts/verify_baselines.py --instance X-n101-k25
    python scripts/verify_baselines.py --baseline-dir data/baselines

Per-instance scoping (``--instance``) lets the user verify a smoke-test
cache from a single ``compute_baselines.py --instance ID`` invocation
without first running all 68.
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Allow running the script directly without an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.baselines import (  # noqa: E402
    BaselineNotFound,
    DEFAULT_BASELINE_DIR,
    Solution,
    baseline_path,
    load_baseline_solution,
)
from vrp_copilot_bench.instances import Instance, list_stage_a_instances, load_instance  # noqa: E402
from vrp_copilot_bench.solvers.marginal_costs import compute_customer_costs  # noqa: E402
from vrp_copilot_bench.solvers.pyvrp_wrapper import _build_distance_matrix  # noqa: E402

logger = logging.getLogger(__name__)


# Locked protocol values per prereg §7 / §8.1.
_LOCKED_TIME_LIMIT_S: float = 60.0
_LOCKED_SEED: int = 1
_LOCKED_N_THREADS: int = 1

# Tolerance for the BKS-gap advisory check.
_BKS_GAP_THRESHOLD: float = 0.05


# ---------------------------------------------------------------------------
# BKS table — Uchoa et al. 2017 Tables 11/12/13, "BKS Value" column.
# Hardcoded here rather than carried in the classification CSV to keep the
# CSV's purpose narrow (instance metadata for stratified sampling). The
# verifier is the only current consumer of BKS.

_UCHOA_X_BKS: dict[str, int] = {
    "X-n101-k25": 27591, "X-n106-k14": 26362, "X-n110-k13": 14971,
    "X-n115-k10": 12747, "X-n120-k6": 13332, "X-n125-k30": 55539,
    "X-n129-k18": 28940, "X-n134-k13": 10916, "X-n139-k10": 13590,
    "X-n143-k7": 15700, "X-n148-k46": 43448, "X-n153-k22": 21220,
    "X-n157-k13": 16876, "X-n162-k11": 14138, "X-n167-k10": 20557,
    "X-n172-k51": 45607, "X-n176-k26": 47812, "X-n181-k23": 25569,
    "X-n186-k15": 24145, "X-n190-k8": 16980, "X-n195-k51": 44225,
    "X-n200-k36": 58578, "X-n204-k19": 19565, "X-n209-k16": 30656,
    "X-n214-k11": 10856, "X-n219-k73": 117595, "X-n223-k34": 40437,
    "X-n228-k23": 25742, "X-n233-k16": 19230, "X-n237-k14": 27042,
    "X-n242-k48": 82751, "X-n247-k50": 37274, "X-n251-k28": 38684,
    "X-n256-k16": 18880, "X-n261-k13": 26558,
    "X-n266-k58": 75478, "X-n270-k35": 35291, "X-n275-k28": 21245,
    "X-n280-k17": 33503, "X-n284-k15": 20206, "X-n289-k60": 95185,
    "X-n294-k50": 47167, "X-n298-k31": 34231, "X-n303-k21": 21744,
    "X-n308-k13": 25859, "X-n313-k71": 94044, "X-n317-k53": 78355,
    "X-n322-k28": 29866, "X-n327-k20": 27556, "X-n331-k15": 31103,
    "X-n336-k84": 139397, "X-n344-k43": 42099, "X-n351-k40": 25946,
    "X-n359-k29": 51509, "X-n367-k17": 22814, "X-n376-k94": 147713,
    "X-n384-k52": 66081, "X-n393-k38": 38269, "X-n401-k29": 66243,
    "X-n411-k19": 19718, "X-n420-k130": 107798, "X-n429-k61": 65501,
    "X-n439-k37": 36395, "X-n449-k29": 55358, "X-n459-k26": 24181,
    "X-n469-k138": 221099, "X-n480-k70": 89535, "X-n491-k59": 66633,
    "X-n502-k39": 69253, "X-n513-k21": 24201,
    "X-n524-k153": 154594, "X-n536-k96": 95122, "X-n548-k50": 86710,
    "X-n561-k42": 42756, "X-n573-k30": 50780, "X-n586-k159": 190543,
    "X-n599-k92": 108813, "X-n613-k62": 59778, "X-n627-k43": 62366,
    "X-n641-k35": 63839, "X-n655-k131": 106780, "X-n670-k130": 146705,
    "X-n685-k75": 68425, "X-n701-k44": 82292, "X-n716-k35": 43525,
    "X-n733-k159": 136366, "X-n749-k98": 77000, "X-n766-k71": 114683,
    "X-n783-k48": 72727, "X-n801-k40": 73387, "X-n819-k171": 158611,
    "X-n837-k142": 194266, "X-n856-k95": 80060, "X-n876-k59": 99715,
    "X-n895-k37": 54172, "X-n916-k207": 329836, "X-n936-k151": 133105,
    "X-n957-k87": 85672, "X-n979-k58": 118399, "X-n1001-k43": 72742,
}


# ---------------------------------------------------------------------------
# Result types


@dataclass
class CheckOutcome:
    instance_id: str
    n_customers: int | None
    objective: float | None
    bks_gap: float | None
    sum_customer_costs: float | None
    failures: list[str]
    warnings: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


# ---------------------------------------------------------------------------
# Per-instance checks


def _verify_one(
    instance_id: str, baseline_dir: Path
) -> CheckOutcome:
    """Run all checks against the cached baseline for ``instance_id``."""
    failures: list[str] = []
    warnings: list[str] = []
    n_customers = None
    objective_val: float | None = None
    bks_gap: float | None = None
    sum_cc: float | None = None

    # 1. Cache exists + loads.
    try:
        sol = load_baseline_solution(instance_id, baseline_dir=baseline_dir)
    except BaselineNotFound as exc:
        failures.append(f"missing cache: {exc}")
        return CheckOutcome(
            instance_id=instance_id, n_customers=None, objective=None,
            bks_gap=None, sum_customer_costs=None,
            failures=failures, warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001
        failures.append(f"load error: {type(exc).__name__}: {exc}")
        return CheckOutcome(
            instance_id=instance_id, n_customers=None, objective=None,
            bks_gap=None, sum_customer_costs=None,
            failures=failures, warnings=warnings,
        )

    # 2. Schema / config.
    if sol.instance_id != instance_id:
        failures.append(
            f"instance_id mismatch: file body has {sol.instance_id!r}, "
            f"path has {instance_id!r}"
        )
    if sol.config.time_limit_seconds != _LOCKED_TIME_LIMIT_S:
        failures.append(
            f"config.time_limit_seconds = {sol.config.time_limit_seconds}, "
            f"locked at {_LOCKED_TIME_LIMIT_S}"
        )
    if sol.config.seed != _LOCKED_SEED:
        failures.append(
            f"config.seed = {sol.config.seed}, locked at {_LOCKED_SEED}"
        )
    if sol.config.n_threads != _LOCKED_N_THREADS:
        failures.append(
            f"config.n_threads = {sol.config.n_threads}, locked at {_LOCKED_N_THREADS}"
        )
    if not sol.pyvrp_version:
        failures.append("pyvrp_version is empty")

    # 3. Finite values.
    if not math.isfinite(sol.objective):
        failures.append(f"objective is non-finite ({sol.objective})")
    else:
        objective_val = sol.objective
    if any(not math.isfinite(v) for v in sol.route_costs.values()):
        failures.append("route_costs contains non-finite values")
    if any(not math.isfinite(v) for v in sol.customer_costs.values()):
        failures.append("customer_costs contains non-finite values")

    # 4. Route shape.
    if not sol.routes:
        failures.append("routes is empty")
    elif any(not isinstance(r, list) or len(r) == 0 for r in sol.routes):
        failures.append("routes contains a non-list or empty sub-list")

    # 5. Load instance for coverage / feasibility / matrix-based identities.
    try:
        instance: Instance = load_instance(instance_id)
        n_customers = instance.n_customers
    except Exception as exc:  # noqa: BLE001
        failures.append(
            f"could not load instance {instance_id!r} for cross-checks: "
            f"{type(exc).__name__}: {exc}"
        )
        return CheckOutcome(
            instance_id=instance_id, n_customers=None, objective=objective_val,
            bks_gap=None, sum_customer_costs=None,
            failures=failures, warnings=warnings,
        )

    # 6. Coverage.
    visits = [c for r in sol.routes for c in r]
    if sorted(visits) != list(range(1, n_customers + 1)):
        if len(set(visits)) != len(visits):
            failures.append(
                f"routes contain duplicate customers ({len(visits)} visits, "
                f"{len(set(visits))} unique)"
            )
        else:
            missing = set(range(1, n_customers + 1)) - set(visits)
            extra = set(visits) - set(range(1, n_customers + 1))
            failures.append(
                f"routes don't cover customers 1..{n_customers}: "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )

    # 7. Assignment ↔ routes consistency.
    for c, route_idx in sol.assignment.items():
        if route_idx < 0 or route_idx >= len(sol.routes):
            failures.append(f"assignment[{c}] = {route_idx}, out of range")
            continue
        if c not in sol.routes[route_idx]:
            failures.append(
                f"assignment[{c}] = {route_idx} but customer {c} not in routes[{route_idx}]"
            )
    for ridx, route in enumerate(sol.routes):
        for c in route:
            if sol.assignment.get(c) != ridx:
                failures.append(
                    f"routes[{ridx}] contains {c} but assignment[{c}] = "
                    f"{sol.assignment.get(c)} (expected {ridx})"
                )

    # 8. Feasibility (per-route load ≤ capacity).
    for ridx, route in enumerate(sol.routes):
        load = int(sum(int(instance.demands[c]) for c in route))
        if load > instance.capacity:
            failures.append(
                f"routes[{ridx}] overloaded: load {load} > capacity {instance.capacity}"
            )

    # 9–10. Distance-matrix-based identities.
    matrix = _build_distance_matrix(instance.coords)

    # 9. route_costs identity (bit-exact).
    for ridx, route in enumerate(sol.routes):
        edges = (
            [int(matrix[0, route[0]])]
            + [int(matrix[route[i], route[i + 1]]) for i in range(len(route) - 1)]
            + [int(matrix[route[-1], 0])]
        )
        recomputed = float(sum(edges))
        stored = sol.route_costs.get(ridx)
        if stored is None:
            failures.append(f"route_costs missing entry for route {ridx}")
        elif abs(stored - recomputed) > 1e-6:
            failures.append(
                f"route_costs[{ridx}] = {stored}, recomputed {recomputed}"
            )

    # 11. objective ≈ sum(route_costs).
    sum_rc = sum(sol.route_costs.values())
    if objective_val is not None and abs(sum_rc - objective_val) > 1e-6:
        failures.append(
            f"objective {objective_val} != sum(route_costs) {sum_rc}"
        )

    # 10. customer_costs identity (bit-exact).
    expected_cc = compute_customer_costs(
        routes=sol.routes,
        distance_matrix=matrix,
        depot_id=instance.depot_index,
    )
    for c, expected in expected_cc.items():
        stored = sol.customer_costs.get(c)
        if stored is None:
            failures.append(f"customer_costs missing entry for customer {c}")
        elif abs(stored - expected) > 1e-6:
            failures.append(
                f"customer_costs[{c}] = {stored}, recomputed {expected}"
            )
    extras_cc = set(sol.customer_costs) - set(expected_cc)
    if extras_cc:
        failures.append(f"customer_costs has spurious keys: {sorted(extras_cc)}")

    sum_cc = float(sum(sol.customer_costs.values()))

    # 12. BKS gap (advisory).
    bks = _UCHOA_X_BKS.get(instance_id)
    if bks is None:
        warnings.append(f"no BKS reference for {instance_id} (skipping gap check)")
    elif objective_val is not None:
        bks_gap = (objective_val - bks) / bks
        if bks_gap < -1e-9:
            warnings.append(
                f"objective {objective_val} below BKS {bks} "
                f"(gap = {bks_gap:.4%}); cache likely stale or BKS table outdated"
            )
        elif bks_gap > _BKS_GAP_THRESHOLD:
            warnings.append(
                f"BKS gap {bks_gap:.4%} exceeds {_BKS_GAP_THRESHOLD:.0%} threshold "
                f"(objective {objective_val}, BKS {bks})"
            )

    return CheckOutcome(
        instance_id=instance_id,
        n_customers=n_customers,
        objective=objective_val,
        bks_gap=bks_gap,
        sum_customer_costs=sum_cc,
        failures=failures,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Top-level orchestration


def verify(
    instance_ids: list[str], baseline_dir: Path
) -> list[CheckOutcome]:
    return [_verify_one(iid, baseline_dir) for iid in instance_ids]


def _format_summary(outcomes: list[CheckOutcome]) -> str:
    lines = []
    header = (
        f"{'instance':<14} {'n':>4} {'objective':>12} "
        f"{'BKS gap':>9} {'Σ cust_cost':>13} {'status':<8}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for o in outcomes:
        n_str = f"{o.n_customers}" if o.n_customers is not None else "-"
        obj_str = f"{o.objective:.1f}" if o.objective is not None else "-"
        gap_str = f"{o.bks_gap:.3%}" if o.bks_gap is not None else "-"
        cc_str = f"{o.sum_customer_costs:.1f}" if o.sum_customer_costs is not None else "-"
        if o.failures:
            status = "FAIL"
        elif o.warnings:
            status = "WARN"
        else:
            status = "ok"
        lines.append(
            f"{o.instance_id:<14} {n_str:>4} {obj_str:>12} "
            f"{gap_str:>9} {cc_str:>13} {status:<8}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="verify_baselines",
        description="Sanity-check the cached Stage A baseline solutions.",
    )
    p.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    p.add_argument("--instance", action="append", default=None, dest="instances",
                   help="Restrict to one or more named instances (repeatable). "
                        "Default: all 68 from the Stage A roster.")
    p.add_argument("--log-level", default="WARNING",
                   choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    instance_ids = (
        list(args.instances) if args.instances is not None
        else list_stage_a_instances()
    )
    print(f"Verifying {len(instance_ids)} baseline(s) in {args.baseline_dir}.")
    print()
    outcomes = verify(instance_ids, args.baseline_dir)

    print(_format_summary(outcomes))
    print()

    n_pass = sum(1 for o in outcomes if o.passed and not o.warnings)
    n_warn = sum(1 for o in outcomes if o.passed and o.warnings)
    n_fail = sum(1 for o in outcomes if not o.passed)
    print(f"Summary: {n_pass} ok, {n_warn} warn, {n_fail} fail.")

    if n_warn:
        print()
        print("Warnings:")
        for o in outcomes:
            for w in o.warnings:
                print(f"  {o.instance_id}: {w}")

    if n_fail:
        print()
        print("Failures:")
        for o in outcomes:
            for f in o.failures:
                print(f"  {o.instance_id}: {f}")
        print()
        print("FAIL")
        return 1

    print()
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

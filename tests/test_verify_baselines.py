"""Tests for scripts/verify_baselines.py.

Strategy: produce a real, valid Solution by running PyVRP on a real
small instance (X-n101-k25, ~3 seconds), persist it, and assert the
verifier reports PASS. Then mutate the cache file in 8 different ways
and assert each mutation makes the verifier emit the expected failure.

This exercises the verifier against actual PyVRP output, which is the
data shape it will see in production. The mutation-based approach
covers each check without needing 8 different fixture solutions.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from vrp_copilot_bench.baselines import Solution, baseline_path
from vrp_copilot_bench.instances import DEFAULT_INSTANCE_DIR, load_instance
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig, solve


_PYVRP_AVAILABLE = True
try:
    import pyvrp  # noqa: F401
except ImportError:  # pragma: no cover - environment-dependent
    _PYVRP_AVAILABLE = False

requires_pyvrp = pytest.mark.skipif(
    not _PYVRP_AVAILABLE, reason="pyvrp not installed"
)


def _instance_present(instance_id: str) -> bool:
    return (DEFAULT_INSTANCE_DIR / f"{instance_id}.vrp").exists()


# Load the script as a module.
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verify_baselines.py"
spec = importlib.util.spec_from_file_location("verify_baselines", _SCRIPT_PATH)
assert spec is not None and spec.loader is not None
verify_baselines_mod = importlib.util.module_from_spec(spec)
sys.modules["verify_baselines"] = verify_baselines_mod
spec.loader.exec_module(verify_baselines_mod)

main = verify_baselines_mod.main
build_parser = verify_baselines_mod.build_parser
verify = verify_baselines_mod.verify
_verify_one = verify_baselines_mod._verify_one
_UCHOA_X_BKS = verify_baselines_mod._UCHOA_X_BKS


# ---------------------------------------------------------------------------
# Build a real Solution fixture once per test module.


@pytest.fixture(scope="module")
def real_solution() -> Solution | None:
    """Compute a fresh PyVRP baseline for X-n101-k25; cache for the module.

    Skipped when PyVRP isn't installed or the .vrp file is missing.
    Uses a 3 s budget — enough to produce a feasible solution within the
    5 % BKS gap on this instance.
    """
    if not _PYVRP_AVAILABLE or not _instance_present("X-n101-k25"):
        return None
    instance = load_instance("X-n101-k25")
    # The verifier checks config.time_limit_seconds == 60 (locked protocol).
    # Run with the locked-protocol config object so the cache schema check
    # passes; the actual solve uses MaxRuntime so a shorter solve still
    # produces a valid Solution.
    real_solve_cfg = SolveConfig(time_limit_seconds=3.0, seed=1)
    result = solve(instance, real_solve_cfg)
    locked_cfg = SolveConfig(time_limit_seconds=60.0, seed=1)
    return Solution.from_solve_result(instance.instance_id, result, locked_cfg)


@pytest.fixture
def cache_dir(tmp_path: Path, real_solution: Solution | None) -> Path:
    """Write the real_solution as a JSON cache file, return the dir."""
    if real_solution is None:
        pytest.skip("PyVRP / instance file unavailable")
    target = tmp_path / f"{real_solution.instance_id}.json"
    target.write_text(json.dumps(real_solution.to_dict()))
    return tmp_path


# ---------------------------------------------------------------------------
# Smoke: a real, valid baseline passes


@requires_pyvrp
class TestPassingCase:
    def test_real_baseline_passes_all_checks(self, cache_dir: Path) -> None:
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert outcome.passed, f"unexpected failures: {outcome.failures}"
        assert outcome.objective is not None and outcome.objective > 0
        assert outcome.n_customers == 100
        assert outcome.bks_gap is not None and outcome.bks_gap < 0.05

    def test_main_returns_zero_on_passing_cache(
        self, cache_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main([
            "--baseline-dir", str(cache_dir),
            "--instance", "X-n101-k25",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "FAIL" not in out

    def test_per_instance_scoping(
        self, cache_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--instance scoping verifies a smoke-test cache without needing all 68."""
        rc = main([
            "--baseline-dir", str(cache_dir),
            "--instance", "X-n101-k25",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        # Only one instance reported.
        assert out.count("X-n101-k25") >= 1
        # Roster line confirms scope.
        assert "Verifying 1 baseline" in out


# ---------------------------------------------------------------------------
# Failures: each mutation must be caught by exactly the expected check.


def _mutate(cache_dir: Path, instance_id: str, mutator) -> None:
    """Load the cache JSON, apply mutator, write it back."""
    target = cache_dir / f"{instance_id}.json"
    data = json.loads(target.read_text())
    mutator(data)
    target.write_text(json.dumps(data))


@requires_pyvrp
class TestFailureCases:
    def test_missing_cache(self, tmp_path: Path) -> None:
        outcome = _verify_one("X-n101-k25", tmp_path)
        assert not outcome.passed
        assert any("missing cache" in f for f in outcome.failures)

    def test_wrong_time_limit_in_config(self, cache_dir: Path) -> None:
        _mutate(
            cache_dir, "X-n101-k25",
            lambda d: d["config"].__setitem__("time_limit_seconds", 30.0),
        )
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("time_limit_seconds" in f for f in outcome.failures)

    def test_wrong_seed_in_config(self, cache_dir: Path) -> None:
        _mutate(
            cache_dir, "X-n101-k25",
            lambda d: d["config"].__setitem__("seed", 2),
        )
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("seed" in f.lower() for f in outcome.failures)

    def test_mismatched_instance_id_in_body(self, cache_dir: Path) -> None:
        """Loader catches this and raises ValueError; verifier reports load error."""
        _mutate(cache_dir, "X-n101-k25", lambda d: d.__setitem__("instance_id", "X-n200-k36"))
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("load error" in f or "reports instance_id" in f for f in outcome.failures)

    def test_objective_inflated_breaks_route_costs_identity(self, cache_dir: Path) -> None:
        """Mutating objective alone leaves route_costs unchanged → objective ≠ sum."""
        _mutate(
            cache_dir, "X-n101-k25",
            lambda d: d.__setitem__("objective", d["objective"] + 1000.0),
        )
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("sum(route_costs)" in f for f in outcome.failures)

    def test_drop_a_customer_from_routes(self, cache_dir: Path) -> None:
        """Coverage check fails when a customer is missing from routes."""
        def mutator(d: dict) -> None:
            d["routes"][0] = d["routes"][0][:-1]  # drop one
        _mutate(cache_dir, "X-n101-k25", mutator)
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("don't cover" in f or "missing=" in f for f in outcome.failures)

    def test_corrupt_assignment_route_index(self, cache_dir: Path) -> None:
        """assignment[c] points at the wrong route → consistency fails."""
        def mutator(d: dict) -> None:
            # Pick the first key in assignment, set to an invalid route index.
            first_key = next(iter(d["assignment"].keys()))
            d["assignment"][first_key] = 999
        _mutate(cache_dir, "X-n101-k25", mutator)
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("assignment" in f for f in outcome.failures)

    def test_perturb_a_customer_cost(self, cache_dir: Path) -> None:
        """Tampering with one customer_cost breaks the per-customer identity."""
        def mutator(d: dict) -> None:
            first_key = next(iter(d["customer_costs"].keys()))
            d["customer_costs"][first_key] = float(d["customer_costs"][first_key]) + 999.0
        _mutate(cache_dir, "X-n101-k25", mutator)
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("customer_costs" in f for f in outcome.failures)

    def test_perturb_a_route_cost(self, cache_dir: Path) -> None:
        """Tampering with one route_cost breaks the route-cost identity."""
        def mutator(d: dict) -> None:
            first_key = next(iter(d["route_costs"].keys()))
            d["route_costs"][first_key] = float(d["route_costs"][first_key]) + 100.0
        _mutate(cache_dir, "X-n101-k25", mutator)
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        # Either the per-route identity or the sum-equals-objective check fires.
        assert any("route_costs" in f or "objective" in f for f in outcome.failures)

    def test_nan_in_objective(self, cache_dir: Path) -> None:
        _mutate(
            cache_dir, "X-n101-k25",
            lambda d: d.__setitem__("objective", float("nan")),
        )
        # Note: json.dumps refuses NaN by default. Use allow_nan=True at write
        # by encoding via a string.
        target = cache_dir / "X-n101-k25.json"
        data = json.loads(target.read_text())
        # Already nan from previous mutation? Read & rewrite using non-strict json.
        data["objective"] = float("nan")
        target.write_text(json.dumps(data, allow_nan=True))
        outcome = _verify_one("X-n101-k25", cache_dir)
        assert not outcome.passed
        assert any("non-finite" in f or "objective" in f for f in outcome.failures)


# ---------------------------------------------------------------------------
# CLI surface


class TestArgumentParser:
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.baseline_dir == Path("data/baselines")
        assert args.instances is None

    def test_instance_flag_repeats(self) -> None:
        args = build_parser().parse_args([
            "--instance", "X-n101-k25",
            "--instance", "X-n200-k36",
        ])
        assert args.instances == ["X-n101-k25", "X-n200-k36"]

    def test_log_level_choices(self) -> None:
        args = build_parser().parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--log-level", "TRACE"])


# ---------------------------------------------------------------------------
# BKS table sanity


class TestBksTable:
    def test_bks_covers_all_stage_a_roster(self) -> None:
        """Every Stage A roster instance has a BKS entry."""
        from vrp_copilot_bench.instances import list_stage_a_instances
        roster = list_stage_a_instances()
        missing = [iid for iid in roster if iid not in _UCHOA_X_BKS]
        assert not missing, f"BKS table missing entries for: {missing}"

    def test_bks_table_has_100_entries(self) -> None:
        """The full Uchoa-X set should be covered for forward compatibility with Stage B."""
        assert len(_UCHOA_X_BKS) == 100

    def test_bks_values_are_positive_ints(self) -> None:
        for iid, bks in _UCHOA_X_BKS.items():
            assert isinstance(bks, int), f"{iid}: BKS is not int ({type(bks).__name__})"
            assert bks > 0, f"{iid}: BKS not positive ({bks})"


# ---------------------------------------------------------------------------
# verify() top-level orchestration


@requires_pyvrp
class TestVerifyOrchestration:
    def test_verify_returns_outcomes_in_order(self, cache_dir: Path) -> None:
        outcomes = verify(["X-n101-k25"], cache_dir)
        assert len(outcomes) == 1
        assert outcomes[0].instance_id == "X-n101-k25"
        assert outcomes[0].passed

    def test_main_with_missing_cache_returns_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main([
            "--baseline-dir", str(tmp_path),
            "--instance", "X-n101-k25",
        ])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "missing cache" in out

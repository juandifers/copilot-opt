"""Tests for vrp_copilot_bench.baselines: Solution dataclass + loader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vrp_copilot_bench.baselines import (
    BaselineNotFound,
    DEFAULT_BASELINE_DIR,
    Solution,
    baseline_path,
    load_baseline_solution,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig, SolveResult


# ---------------------------------------------------------------------------
# Test fixtures


def _make_solution(instance_id: str = "X-n101-k25") -> Solution:
    """Produce a synthetic Solution with all dict-keyed fields populated."""
    return Solution(
        instance_id=instance_id,
        objective=1234.5,
        routes=[[1, 2, 3], [4, 5]],
        assignment={1: 0, 2: 0, 3: 0, 4: 1, 5: 1},
        route_costs={0: 800.0, 1: 434.5},
        customer_costs={1: 100.0, 2: 200.0, 3: 300.0, 4: 200.0, 5: 234.5},
        runtime_seconds=60.0,
        pyvrp_version="0.13.3",
        config=SolveConfig(time_limit_seconds=60.0, seed=1),
    )


# ---------------------------------------------------------------------------
# Solution.to_dict / from_dict


class TestSolutionRoundtrip:
    def test_to_dict_then_from_dict_equals_original(self) -> None:
        sol = _make_solution()
        roundtripped = Solution.from_dict(sol.to_dict())
        assert roundtripped == sol

    def test_to_dict_via_json_dump_load_roundtrips(self) -> None:
        """JSON serialization preserves int-keyed dicts via stringification."""
        sol = _make_solution()
        encoded = json.dumps(sol.to_dict())
        decoded = Solution.from_dict(json.loads(encoded))
        assert decoded == sol

    def test_assignment_keys_become_int_after_load(self) -> None:
        """Round-tripping through JSON must yield Python int keys, not str."""
        sol = _make_solution()
        decoded = Solution.from_dict(json.loads(json.dumps(sol.to_dict())))
        for k in decoded.assignment.keys():
            assert isinstance(k, int)
        for k in decoded.route_costs.keys():
            assert isinstance(k, int)
        for k in decoded.customer_costs.keys():
            assert isinstance(k, int)

    def test_routes_are_python_int_lists_after_load(self) -> None:
        sol = _make_solution()
        decoded = Solution.from_dict(json.loads(json.dumps(sol.to_dict())))
        for route in decoded.routes:
            for c in route:
                assert isinstance(c, int)
                assert not isinstance(c, bool)

    def test_config_roundtrips(self) -> None:
        sol = _make_solution()
        decoded = Solution.from_dict(json.loads(json.dumps(sol.to_dict())))
        assert decoded.config == sol.config
        assert decoded.config.time_limit_seconds == 60.0
        assert decoded.config.seed == 1
        assert decoded.config.n_threads == 1


class TestSolutionFromSolveResult:
    def test_promotes_fields_correctly(self) -> None:
        result = SolveResult(
            objective=99.0,
            feasible=True,
            routes=[[1, 2]],
            assignment={1: 0, 2: 0},
            route_costs={0: 99.0},
            customer_costs={1: 50.0, 2: 49.0},
            n_overload=0,
            max_overload_fraction=0.0,
            runtime_seconds=12.5,
            pyvrp_version="0.13.3",
        )
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)
        sol = Solution.from_solve_result("X-n101-k25", result, cfg)
        assert sol.instance_id == "X-n101-k25"
        assert sol.objective == 99.0
        assert sol.routes == [[1, 2]]
        assert sol.assignment == {1: 0, 2: 0}
        assert sol.route_costs == {0: 99.0}
        assert sol.customer_costs == {1: 50.0, 2: 49.0}
        assert sol.runtime_seconds == 12.5
        assert sol.pyvrp_version == "0.13.3"
        assert sol.config == cfg

    def test_solve_result_routes_are_copied_not_aliased(self) -> None:
        """Mutating result.routes after construction must not mutate the Solution."""
        result = SolveResult(
            objective=10.0, feasible=True,
            routes=[[1]], assignment={1: 0}, route_costs={0: 10.0},
            customer_costs={1: 10.0},
            n_overload=0, max_overload_fraction=0.0,
            runtime_seconds=1.0, pyvrp_version="0.13.3",
        )
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)
        sol = Solution.from_solve_result("test", result, cfg)
        # Check identity: sol.routes should be new list-of-lists.
        assert sol.routes is not result.routes
        assert sol.routes[0] is not result.routes[0]


# ---------------------------------------------------------------------------
# load_baseline_solution


class TestLoadBaselineSolution:
    def test_loads_real_cache_file(self, tmp_path: Path) -> None:
        sol = _make_solution()
        target = tmp_path / f"{sol.instance_id}.json"
        target.write_text(json.dumps(sol.to_dict()))
        loaded = load_baseline_solution(sol.instance_id, baseline_dir=tmp_path)
        assert loaded == sol

    def test_missing_file_raises_baseline_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(BaselineNotFound) as excinfo:
            load_baseline_solution("X-n101-k25", baseline_dir=tmp_path)
        msg = str(excinfo.value)
        assert "X-n101-k25" in msg
        assert "compute_baselines.py" in msg, "error should point at the compute script"

    def test_default_baseline_dir_is_data_baselines(self) -> None:
        assert DEFAULT_BASELINE_DIR == Path("data/baselines")

    def test_baseline_path_helper(self, tmp_path: Path) -> None:
        assert baseline_path("X-n101-k25", tmp_path) == tmp_path / "X-n101-k25.json"

    def test_mismatched_instance_id_in_file_raises(self, tmp_path: Path) -> None:
        """Defensive: if a cache file's body says X-n200, but it's stored as X-n101.json."""
        sol = _make_solution(instance_id="X-n200-k36")
        target = tmp_path / "X-n101-k25.json"
        target.write_text(json.dumps(sol.to_dict()))
        with pytest.raises(ValueError, match="reports instance_id"):
            load_baseline_solution("X-n101-k25", baseline_dir=tmp_path)

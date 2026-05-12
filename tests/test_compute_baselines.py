"""Tests for scripts/compute_baselines.py.

Synthesizes small fake instances and monkeypatches ``solve`` and
``load_instance`` so the orchestration logic can be exercised without
running PyVRP for 60 s × N instances. Real PyVRP solves are tested in
``test_pyvrp_wrapper.py``.

All tests use ``backend="threading"`` so monkeypatches in the parent
process propagate to workers (loky workers are separate processes and
don't see parent monkeypatches; production runs use loky).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from vrp_copilot_bench.baselines import (
    BaselineNotFound,
    Solution,
    baseline_path,
    load_baseline_solution,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig, SolveResult


# Load the script as a module so we can import its top-level names.
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "compute_baselines.py"
spec = importlib.util.spec_from_file_location("compute_baselines", _SCRIPT_PATH)
assert spec is not None and spec.loader is not None
compute_baselines_mod = importlib.util.module_from_spec(spec)
sys.modules["compute_baselines"] = compute_baselines_mod
spec.loader.exec_module(compute_baselines_mod)

main = compute_baselines_mod.main
build_parser = compute_baselines_mod.build_parser
compute_baselines = compute_baselines_mod.compute_baselines
_compute_one = compute_baselines_mod._compute_one
_atomic_write_json = compute_baselines_mod._atomic_write_json


# ---------------------------------------------------------------------------
# Synthetic instance and solve fakes


def _fake_instance(instance_id: str):
    """Stand-in for vrp_copilot_bench.instances.Instance, just carries an id.

    The real Instance has many fields; for these tests, ``solve`` is also
    faked so the only thing that matters is that ``load_instance`` returns
    *something* keyed off ``instance_id``. We use a simple SimpleNamespace.
    """
    from types import SimpleNamespace
    return SimpleNamespace(instance_id=instance_id, n_customers=3)


def _fake_solve_factory(*, fail_on: set[str] | None = None,
                        objective_offset: float = 0.0):
    """Return a fake ``solve`` that produces deterministic SolveResults.

    If the instance id is in ``fail_on``, the fake raises a RuntimeError —
    used to test exception isolation.
    """
    fail_on = fail_on or set()

    def fake_solve(instance, config: SolveConfig) -> SolveResult:
        if instance.instance_id in fail_on:
            raise RuntimeError(f"deliberate failure on {instance.instance_id}")
        # Deterministic synthetic SolveResult
        return SolveResult(
            objective=100.0 + objective_offset + len(instance.instance_id),
            feasible=True,
            routes=[[1, 2], [3]],
            assignment={1: 0, 2: 0, 3: 1},
            route_costs={0: 60.0, 1: 40.0 + objective_offset + len(instance.instance_id)},
            customer_costs={1: 30.0, 2: 30.0, 3: 40.0 + objective_offset + len(instance.instance_id)},
            n_overload=0,
            max_overload_fraction=0.0,
            runtime_seconds=0.001,
            pyvrp_version="0.13.3-fake",
        )

    return fake_solve


@pytest.fixture
def patch_solve_and_load(monkeypatch: pytest.MonkeyPatch):
    """Replace solve + load_instance in compute_baselines with deterministic fakes."""
    monkeypatch.setattr(compute_baselines_mod, "load_instance", _fake_instance)
    monkeypatch.setattr(compute_baselines_mod, "solve", _fake_solve_factory())
    return monkeypatch


# ---------------------------------------------------------------------------
# _atomic_write_json


class TestAtomicWriteJson:
    def test_basic_write(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        _atomic_write_json(target, {"a": 1, "b": [2, 3]})
        assert target.exists()
        assert json.loads(target.read_text()) == {"a": 1, "b": [2, 3]}

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        target.write_text(json.dumps({"old": True}))
        _atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"new": True}

    def test_no_tmp_files_left_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        _atomic_write_json(target, {"x": 1})
        leftover = list(tmp_path.glob("*.tmp.*"))
        assert leftover == [], f"tmp files left: {leftover}"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "subdir" / "out.json"
        _atomic_write_json(target, {"x": 1})
        assert target.exists()


# ---------------------------------------------------------------------------
# _compute_one


class TestComputeOne:
    def test_skipped_when_cache_exists(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch
    ) -> None:
        baseline_dir = tmp_path
        target = baseline_dir / "X-n101-k25.json"
        # Pre-populate a cache file with arbitrary contents.
        target.write_text(json.dumps({"sentinel": "cached"}))

        result = _compute_one(
            "X-n101-k25",
            SolveConfig(time_limit_seconds=60.0, seed=1),
            baseline_dir,
        )
        assert result == ("X-n101-k25", "skipped", None)
        # Cache file should be untouched.
        assert json.loads(target.read_text()) == {"sentinel": "cached"}

    def test_computes_when_cache_absent(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch
    ) -> None:
        result = _compute_one(
            "X-n101-k25",
            SolveConfig(time_limit_seconds=60.0, seed=1),
            tmp_path,
        )
        assert result == ("X-n101-k25", "computed", None)
        sol = load_baseline_solution("X-n101-k25", baseline_dir=tmp_path)
        assert sol.instance_id == "X-n101-k25"
        assert sol.feasible if hasattr(sol, "feasible") else True
        assert sol.objective > 0

    def test_failure_does_not_write_partial_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(compute_baselines_mod, "load_instance", _fake_instance)
        monkeypatch.setattr(
            compute_baselines_mod, "solve",
            _fake_solve_factory(fail_on={"X-n101-k25"}),
        )
        result = _compute_one(
            "X-n101-k25",
            SolveConfig(time_limit_seconds=60.0, seed=1),
            tmp_path,
        )
        instance_id, status, err = result
        assert instance_id == "X-n101-k25"
        assert status == "failed"
        assert "deliberate failure" in (err or "")
        assert not (tmp_path / "X-n101-k25.json").exists(), (
            "no cache file should be written on failure"
        )


# ---------------------------------------------------------------------------
# compute_baselines orchestrator


class TestComputeBaselinesOrchestrator:
    def test_idempotent_second_run_does_no_work(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch
    ) -> None:
        ids = ["X-n101-k25", "X-n200-k36", "X-n247-k50"]
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)

        first = compute_baselines(
            ids, tmp_path, cfg, workers=2, backend="threading", force=False,
        )
        assert sorted(first["computed"]) == sorted(ids)
        assert first["skipped"] == []
        assert first["failed"] == []

        # Track call count on the underlying fake solve.
        solve_calls: list[str] = []
        original = compute_baselines_mod.solve

        def counting_solve(inst, config):
            solve_calls.append(inst.instance_id)
            return original(inst, config)

        patch_solve_and_load.setattr(compute_baselines_mod, "solve", counting_solve)

        second = compute_baselines(
            ids, tmp_path, cfg, workers=2, backend="threading", force=False,
        )
        assert second["computed"] == []
        assert sorted(second["skipped"]) == sorted(ids)
        assert second["failed"] == []
        assert solve_calls == [], (
            "second run must not invoke solve at all (everything cached)"
        )

    def test_force_recomputes_even_if_cached(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch
    ) -> None:
        ids = ["X-n101-k25", "X-n200-k36"]
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)

        # Pre-populate the cache with sentinel content so we can detect overwrite.
        for iid in ids:
            (tmp_path / f"{iid}.json").write_text(json.dumps({
                "instance_id": iid,
                "objective": -999.0,  # sentinel
                "routes": [],
                "assignment": {},
                "route_costs": {},
                "customer_costs": {},
                "runtime_seconds": 0.0,
                "pyvrp_version": "fake",
                "config": cfg.to_dict(),
            }))

        out = compute_baselines(
            ids, tmp_path, cfg, workers=2, backend="threading", force=True,
        )
        assert sorted(out["computed"]) == sorted(ids)
        # Sentinel objective is gone — file was overwritten.
        for iid in ids:
            sol = load_baseline_solution(iid, baseline_dir=tmp_path)
            assert sol.objective != -999.0, f"{iid} still has sentinel; --force did not overwrite"

    def test_partial_resume_picks_up_after_simulated_kill(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch
    ) -> None:
        """Simulate Ctrl-C mid-run: first call computes some ids, second call
        completes the rest without redoing the first set."""
        all_ids = ["X-n101-k25", "X-n200-k36", "X-n247-k50", "X-n148-k46"]
        already_done = ["X-n101-k25", "X-n200-k36"]
        remaining = ["X-n247-k50", "X-n148-k46"]
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)

        # Simulate a partial first run: write cache files for the "already done" ones.
        for iid in already_done:
            sol = Solution.from_solve_result(
                iid,
                SolveResult(
                    objective=10.0, feasible=True, routes=[[1]],
                    assignment={1: 0}, route_costs={0: 10.0}, customer_costs={1: 10.0},
                    n_overload=0, max_overload_fraction=0.0,
                    runtime_seconds=0.001, pyvrp_version="0.13.3-fake",
                ),
                cfg,
            )
            (tmp_path / f"{iid}.json").write_text(json.dumps(sol.to_dict()))

        # Resume: invoke compute_baselines on all 4 ids.
        out = compute_baselines(
            all_ids, tmp_path, cfg, workers=2, backend="threading", force=False,
        )
        assert sorted(out["computed"]) == sorted(remaining)
        assert sorted(out["skipped"]) == sorted(already_done)
        assert out["failed"] == []
        # All four cache files exist after the resume.
        for iid in all_ids:
            assert (tmp_path / f"{iid}.json").exists()

    def test_exception_in_one_does_not_poison_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ids = ["X-n101-k25", "X-n200-k36", "X-n247-k50"]
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)
        monkeypatch.setattr(compute_baselines_mod, "load_instance", _fake_instance)
        monkeypatch.setattr(
            compute_baselines_mod, "solve",
            _fake_solve_factory(fail_on={"X-n200-k36"}),
        )

        out = compute_baselines(
            ids, tmp_path, cfg, workers=2, backend="threading", force=False,
        )
        assert sorted(out["computed"]) == sorted(["X-n101-k25", "X-n247-k50"])
        assert out["failed"] == ["X-n200-k36"]
        assert (tmp_path / "X-n101-k25.json").exists()
        assert (tmp_path / "X-n247-k50.json").exists()
        assert not (tmp_path / "X-n200-k36.json").exists()

    def test_output_json_roundtrips_via_solution_from_dict(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch
    ) -> None:
        ids = ["X-n101-k25"]
        cfg = SolveConfig(time_limit_seconds=60.0, seed=1)
        compute_baselines(
            ids, tmp_path, cfg, workers=1, backend="sequential", force=False,
        )
        sol = load_baseline_solution("X-n101-k25", baseline_dir=tmp_path)
        # The loader uses Solution.from_dict; this confirms full round-trip.
        assert sol.instance_id == "X-n101-k25"
        assert sol.config == cfg
        assert sol.routes == [[1, 2], [3]]
        assert sol.objective > 0


# ---------------------------------------------------------------------------
# CLI


class TestArgumentParser:
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.baseline_dir == Path("data/baselines")
        assert args.workers == 6
        assert args.time_limit == 60.0
        assert args.seed == 1
        assert args.backend == "loky"
        assert args.force is False
        assert args.instances is None

    def test_force_flag(self) -> None:
        args = build_parser().parse_args(["--force"])
        assert args.force is True

    def test_instance_flag_repeats(self) -> None:
        args = build_parser().parse_args([
            "--instance", "X-n101-k25",
            "--instance", "X-n200-k36",
        ])
        assert args.instances == ["X-n101-k25", "X-n200-k36"]

    def test_backend_choices(self) -> None:
        args = build_parser().parse_args(["--backend", "threading"])
        assert args.backend == "threading"
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--backend", "fork"])


class TestMainCLI:
    def test_main_full_run_returns_zero(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = main([
            "--baseline-dir", str(tmp_path),
            "--instance", "X-n101-k25",
            "--instance", "X-n200-k36",
            "--backend", "threading",
            "--workers", "2",
            "--time-limit", "60",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "2 computed" in out
        assert (tmp_path / "X-n101-k25.json").exists()
        assert (tmp_path / "X-n200-k36.json").exists()

    def test_main_with_failure_returns_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(compute_baselines_mod, "load_instance", _fake_instance)
        monkeypatch.setattr(
            compute_baselines_mod, "solve",
            _fake_solve_factory(fail_on={"X-n101-k25"}),
        )
        rc = main([
            "--baseline-dir", str(tmp_path),
            "--instance", "X-n101-k25",
            "--instance", "X-n200-k36",
            "--backend", "threading",
            "--workers", "2",
            "--time-limit", "60",
        ])
        assert rc == 1
        out = capsys.readouterr().out
        assert "1 failed" in out
        assert "X-n101-k25" in out

    def test_force_flag_emits_warning(
        self, tmp_path: Path, patch_solve_and_load: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging as _logging
        caplog.set_level(_logging.WARNING, logger="compute_baselines")
        main([
            "--baseline-dir", str(tmp_path),
            "--instance", "X-n101-k25",
            "--backend", "threading",
            "--workers", "1",
            "--time-limit", "60",
            "--force",
        ])
        # The warning text mentions "downstream artifacts".
        assert any("downstream" in rec.message.lower() for rec in caplog.records)

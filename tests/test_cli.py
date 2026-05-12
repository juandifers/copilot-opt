"""Tests for the Stage A CLI entrypoint (Phase 5).

Most tests drive ``cli.main([...])`` directly with monkeypatched runner
deps. The loky smoke test runs end-to-end in a subprocess so we exercise
real process isolation and the ``_smoke_deps`` env-var hook.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from vrp_copilot_bench import cli
from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.checkpoint import (
    ActionRunKey,
    list_completed,
    save_failure,
    save_result,
)
from vrp_copilot_bench.cli import (
    ACTION_COSTS_S,
    build_parser,
    estimate_runtime_seconds,
    format_duration,
    main,
)
from vrp_copilot_bench.consolidate import SCHEMA, SCHEMA_VERSION
from vrp_copilot_bench.work_plan import enumerate_stage_a


REPO_SRC = Path(__file__).resolve().parent.parent / "src"


# ---------------------------------------------------------------------------
# Helpers


def _make_result(action: str = "reuse_direct") -> ActionResult:
    return ActionResult(
        action=action, objective=1000.0, feasible=True, runtime_seconds=0.01,
        n_overload=0, max_overload_fraction=0.0,
        assignment={1: 0}, route_costs={0: 1.0}, customer_costs={1: 1.0},
    )


def _patch_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vrp_copilot_bench.runner.load_instance",
                        lambda iid: ("instance", iid))
    monkeypatch.setattr("vrp_copilot_bench.runner.load_baseline_solution",
                        lambda iid: ("baseline", iid))
    monkeypatch.setattr("vrp_copilot_bench.runner.lookup_perturbation",
                        lambda iid, pid: ("spec", pid))
    monkeypatch.setattr("vrp_copilot_bench.runner.apply_perturbation",
                        # Phase C: runner now passes baseline through.
                        lambda inst, spec, baseline: ("perturbed", inst, spec))
    monkeypatch.setattr("vrp_copilot_bench.runner.run_action",
                        lambda a, p, b: _make_result(action=a))


# ---------------------------------------------------------------------------
# Estimation


class TestEstimateRuntime:
    def test_cost_model_covers_all_actions(self) -> None:
        from vrp_copilot_bench.actions import ACTIONS

        assert set(ACTION_COSTS_S) == set(ACTIONS)

    def test_audit_seeds_cost_60s(self) -> None:
        assert ACTION_COSTS_S["pyvrp_60s_seed2"] == 60.0
        assert ACTION_COSTS_S["pyvrp_60s_seed3"] == 60.0

    def test_estimate_scales_with_workers(self) -> None:
        keys = enumerate_stage_a()
        slow = estimate_runtime_seconds(
            keys, workers_normal=1, workers_large=1, large_threshold=400,
        )
        fast = estimate_runtime_seconds(
            keys, workers_normal=6, workers_large=4, large_threshold=400,
        )
        assert fast < slow
        # Roughly proportional (not exact because two-phase split).
        assert fast < slow / 4

    def test_estimate_is_finite_for_full_grid(self) -> None:
        keys = enumerate_stage_a()
        eta = estimate_runtime_seconds(
            keys, workers_normal=6, workers_large=4, large_threshold=400,
        )
        # Stage A on M2: roughly 80,000 CPU-seconds → ~22 hours single-thread,
        # ~4-5 hours with 6 workers. Just sanity-bound.
        assert 60 < eta < 24 * 3600

    def test_format_duration(self) -> None:
        assert format_duration(0.5) == "0s"
        assert format_duration(45) == "45s"
        assert format_duration(3 * 60 + 30) == "3.5 min"
        assert format_duration(2 * 3600 + 1800) == "2.50 h"


# ---------------------------------------------------------------------------
# Argument parser


class TestParser:
    def test_default_paths(self) -> None:
        args = build_parser().parse_args([])
        assert args.checkpoint_dir == Path("data/checkpoints")
        assert args.output == Path("data/stage_a.parquet")

    def test_default_workers(self) -> None:
        args = build_parser().parse_args([])
        assert args.workers_normal == 6
        assert args.workers_large == 4
        assert args.large_threshold == 400

    def test_all_flags_parse(self) -> None:
        args = build_parser().parse_args([
            "--checkpoint-dir", "/tmp/ckpt",
            "--output", "/tmp/out.parquet",
            "--workers-normal", "3",
            "--workers-large", "2",
            "--large-threshold", "300",
            "--backend", "threading",
            "--task-timeout-s", "120",
            "--progress-log-every", "50",
            "--dry-run",
            "--allow-empty",
            "--retry-failures",
            "--log-level", "DEBUG",
        ])
        assert args.workers_normal == 3
        assert args.workers_large == 2
        assert args.large_threshold == 300
        assert args.backend == "threading"
        assert args.task_timeout_s == 120
        assert args.dry_run is True
        assert args.allow_empty is True
        assert args.retry_failures is True
        assert args.log_level == "DEBUG"


# ---------------------------------------------------------------------------
# --dry-run


class TestDryRun:
    def test_dry_run_does_not_dispatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run prints the count + ETA and returns 0 without running."""

        def boom(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("run_stage_a must not be called for --dry-run")

        monkeypatch.setattr("vrp_copilot_bench.cli.run_stage_a", boom)

        rc = main([
            "--checkpoint-dir", str(tmp_path / "ckpt"),
            "--output", str(tmp_path / "stage_a.parquet"),
            "--dry-run",
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Would run" in out
        assert "cell-actions" in out
        assert "Estimated wall-time:" in out
        # Never wrote the parquet.
        assert not (tmp_path / "stage_a.parquet").exists()

    def test_dry_run_count_matches_remaining_keys(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Pre-populate one checkpoint, --dry-run should count it as
        already done."""
        ckpt = tmp_path / "ckpt"
        # First key from the ordered plan.
        from vrp_copilot_bench.work_plan import order_by_size

        first_key = order_by_size(enumerate_stage_a())[0]
        save_result(ckpt, first_key, _make_result(action=first_key.action))

        main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(tmp_path / "out.parquet"),
            "--dry-run",
        ])
        out = capsys.readouterr().out
        total = len(enumerate_stage_a())
        assert f"Would run {total - 1} cell-actions" in out


# ---------------------------------------------------------------------------
# --consolidate-only


class TestConsolidateOnly:
    def test_consolidate_only_skips_dispatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """--consolidate-only does not invoke run_stage_a, only consolidate."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        ckpt.mkdir()

        def boom(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("run_stage_a must not be called for --consolidate-only")

        monkeypatch.setattr("vrp_copilot_bench.cli.run_stage_a", boom)

        # Empty dir without --allow-empty → consolidation fails with rc=2.
        rc = main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(out),
            "--consolidate-only",
        ])
        assert rc == 2
        captured = capsys.readouterr().out
        assert "EMPTY_CHECKPOINTS" in captured

    def test_consolidate_only_with_allow_empty_writes_parquet(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        ckpt.mkdir()

        def boom(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("run_stage_a must not be called for --consolidate-only")
        monkeypatch.setattr("vrp_copilot_bench.cli.run_stage_a", boom)

        rc = main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(out),
            "--consolidate-only",
            "--allow-empty",
        ])
        assert rc == 0
        assert out.is_file()
        df = pd.read_parquet(out)
        assert len(df) == 0
        assert list(df.columns) == list(SCHEMA.keys())


# ---------------------------------------------------------------------------
# --retry-failures


class TestRetryFailures:
    def test_retry_failures_runs_only_failed_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        # Pre-record two failures.
        failed = [
            ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct"),
            ActionRunKey("X-n101-k25", "CAP_2", "reuse_direct"),
        ]
        for k in failed:
            save_failure(ckpt, k, RuntimeError("old failure"))

        # The CLI calls run_stage_a; we monkeypatch deps so the keys actually succeed.
        _patch_deps(monkeypatch)

        rc = main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(out),
            "--workers-normal", "1",
            "--workers-large", "1",
            "--backend", "threading",
            "--retry-failures",
            "--allow-empty",  # in case post-retry we still want consolidate to pass
        ])
        captured = capsys.readouterr().out
        assert "Retrying 2" in captured
        assert rc in (0, 2)  # consolidate may produce empty (only 2 keys done) → still ok with allow_empty
        # Both retried keys now have successful checkpoints.
        completed = list_completed(ckpt)
        assert set(failed).issubset(completed)

    def test_retry_failures_with_no_failures_exits_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """No failures recorded → print message and return 0 without dispatch."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        ckpt.mkdir()

        def boom(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("run_stage_a must not be called when no failures")
        monkeypatch.setattr("vrp_copilot_bench.cli.run_stage_a", boom)

        rc = main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(out),
            "--retry-failures",
        ])
        assert rc == 0
        assert "No failures recorded" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# --allow-empty


class TestAllowEmpty:
    def test_allow_empty_writes_zero_row_parquet_via_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        ckpt.mkdir()
        monkeypatch.setattr("vrp_copilot_bench.cli.run_stage_a", lambda **kw: _empty_summary())

        rc = main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(out),
            "--workers-normal", "1",
            "--workers-large", "1",
            "--backend", "threading",
            "--allow-empty",
        ])
        assert rc == 0
        assert out.is_file()
        # Schema metadata still present.
        meta = pq.read_metadata(out).schema.to_arrow_schema().metadata
        assert meta.get(b"_schema_version") == SCHEMA_VERSION.encode()


def _empty_summary() -> Any:
    from vrp_copilot_bench.runner import RunSummary

    return RunSummary(n_attempted=0, n_succeeded=0, n_failed=0, wall_time_seconds=0.0)


# ---------------------------------------------------------------------------
# Loky smoke test (subprocess)


class TestLokySmoke:
    def test_run_stage_a_loky_end_to_end(self, tmp_path: Path) -> None:
        """Spawn a subprocess that imports the package fresh, sets the
        smoke-deps env var so the runner's module-level imports rebind to
        :mod:`._smoke_deps`, and runs ``run_stage_a(backend='loky')`` on a
        small key list. Exit code 0 means loky can drive the dispatch."""
        script = tmp_path / "loky_smoke.py"
        ckpt = tmp_path / "ckpt"
        script.write_text(textwrap.dedent(f'''
            import sys
            sys.path.insert(0, {str(REPO_SRC)!r})

            from pathlib import Path
            from vrp_copilot_bench.checkpoint import ActionRunKey, list_completed
            from vrp_copilot_bench.runner import run_stage_a

            keys = [
                ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct"),
                ActionRunKey("X-n106-k14", "CAP_1", "reuse_direct"),
                ActionRunKey("X-n110-k13", "CAP_1", "reuse_direct"),
                ActionRunKey("X-n101-k25", "CAP_1", "nearest_neighbor"),
            ]
            ckpt = Path({str(ckpt)!r})
            summary = run_stage_a(
                checkpoint_dir=ckpt,
                workers_normal=2,
                workers_large=1,
                backend="loky",
                keys=keys,
                progress_log_every=10,
            )
            assert summary.n_succeeded == 4, f"expected 4, got {{summary}}"
            assert summary.n_failed == 0
            done = list_completed(ckpt)
            assert set(done) == set(keys), f"missing: {{set(keys) - set(done)}}"
            print("OK")
        '''))

        env = os.environ.copy()
        env["VRP_COPILOT_BENCH_USE_SMOKE_DEPS"] = "1"

        result = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, (
            f"subprocess failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
        assert "OK" in result.stdout

    def test_runner_does_not_use_smoke_deps_by_default(self) -> None:
        """Without the env var, the runner's downstream-dep references
        point to the production functions in :mod:`vrp_copilot_bench.actions`,
        not the synthetic ones in :mod:`._smoke_deps`. Just verifies the
        env-var hook is opt-in.

        Phase C: ``run_action`` is a real dispatcher (no longer a stub
        that raises ``NotImplementedError``). The check now compares
        function identity: production ``actions.run_action`` vs
        smoke-deps ``_smoke_deps.run_action``. They are different objects.
        """
        from vrp_copilot_bench import _smoke_deps, actions, runner

        # The smoke-deps env var must not be set when this test process
        # starts — otherwise the runner's module-level rebinding would
        # have already taken effect and our identity check would lie.
        assert os.environ.get("VRP_COPILOT_BENCH_USE_SMOKE_DEPS") != "1"
        # Production dispatcher is in use; smoke-deps dispatcher is not.
        assert runner.run_action is actions.run_action
        assert runner.run_action is not _smoke_deps.run_action


# ---------------------------------------------------------------------------
# End-to-end: dispatch + consolidate via the CLI


class TestEndToEnd:
    def test_dispatch_then_consolidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A small key list dispatched via threading + consolidated to parquet."""
        from vrp_copilot_bench.actions import BASE_ACTIONS, AUDIT_ACTIONS
        from vrp_copilot_bench.instances import list_stage_a_instances
        from vrp_copilot_bench.perturbations import enumerate_perturbations
        from vrp_copilot_bench.work_plan import select_audit_subset

        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        # Patch enumerate so the runner only runs the keys for 1 instance.
        instance_id = list_stage_a_instances()[0]
        keys = []
        audit_pairs = {p for p in select_audit_subset() if p[0] == instance_id}
        for spec in enumerate_perturbations(instance_id):
            for action in BASE_ACTIONS:
                keys.append(ActionRunKey(instance_id, spec.perturbation_id, action))
            if (instance_id, spec.perturbation_id) in audit_pairs:
                for action in AUDIT_ACTIONS:
                    keys.append(ActionRunKey(instance_id, spec.perturbation_id, action))
        monkeypatch.setattr("vrp_copilot_bench.runner.enumerate_stage_a", lambda: list(keys))
        _patch_deps(monkeypatch)

        rc = main([
            "--checkpoint-dir", str(ckpt),
            "--output", str(out),
            "--workers-normal", "2",
            "--workers-large", "1",
            "--backend", "threading",
            "--progress-log-every", "999",
        ])
        assert rc == 0
        assert out.is_file()

        df = pd.read_parquet(out)
        # 1 instance × 16 perts × 4 claim families × 5 base actions = 320.
        assert len(df) == 320
        # Schema version.
        meta = pq.read_metadata(out).schema.to_arrow_schema().metadata
        assert meta.get(b"_schema_version") == SCHEMA_VERSION.encode()

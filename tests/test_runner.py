"""Tests for the Stage A runner (Phase 3).

The runner orchestrates per-key checkpointed dispatch under a joblib pool.
Tests use ``backend="threading"`` so that monkeypatches on the runner's
import sites propagate to workers; production uses ``backend="loky"``.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

import pytest

from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.checkpoint import (
    ActionRunKey,
    failure_path,
    has_checkpoint,
    list_completed,
    list_failures,
    save_failure,
    save_result,
)
from vrp_copilot_bench.runner import (
    RunFailure,
    RunSummary,
    _dispatch_phase,
    _ProgressTracker,
    cleanup_stale_tmp_files,
    run_one_action,
    run_stage_a,
)


# ---------------------------------------------------------------------------
# Helpers


def _make_result(action: str = "reuse_direct", obj: float = 1234.5) -> ActionResult:
    return ActionResult(
        action=action,
        objective=obj,
        feasible=True,
        runtime_seconds=0.01,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={1: 0},
        route_costs={0: 1.0},
        customer_costs={1: 1.0},
    )


class _CallTracker:
    """Thread-safe call counter for monkeypatched dependencies."""

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self._lock = threading.Lock()

    def record(self, *args: Any) -> None:
        with self._lock:
            self.calls.append(args)

    def __len__(self) -> int:
        with self._lock:
            return len(self.calls)


def _patch_runner_deps(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_run_action: Callable[[str, Any, Any], ActionResult],
) -> None:
    """Replace all four downstream dependencies the runner imports."""
    monkeypatch.setattr("vrp_copilot_bench.runner.load_instance", lambda iid: ("instance", iid))
    monkeypatch.setattr("vrp_copilot_bench.runner.load_baseline_solution", lambda iid: ("baseline", iid))
    monkeypatch.setattr(
        "vrp_copilot_bench.runner.lookup_perturbation",
        lambda iid, pid: ("spec", pid),
    )
    monkeypatch.setattr(
        "vrp_copilot_bench.runner.apply_perturbation",
        # Phase C: runner now passes baseline through to apply_perturbation.
        # The fake fixture echoes all three so test assertions can verify
        # the baseline propagation.
        lambda inst, spec, baseline: ("perturbed", inst, spec, baseline),
    )
    monkeypatch.setattr("vrp_copilot_bench.runner.run_action", fake_run_action)


# ---------------------------------------------------------------------------
# run_one_action: idempotency


class TestRunOneActionIdempotent:
    def test_skips_when_checkpoint_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")
        save_result(tmp_path, key, _make_result())

        # All sub-functions must remain untouched on the skip path.
        def boom(*_args: Any, **_kwargs: Any) -> None:
            pytest.fail("downstream dep called despite existing checkpoint")

        monkeypatch.setattr("vrp_copilot_bench.runner.load_instance", boom)
        monkeypatch.setattr("vrp_copilot_bench.runner.load_baseline_solution", boom)
        monkeypatch.setattr("vrp_copilot_bench.runner.lookup_perturbation", boom)
        monkeypatch.setattr("vrp_copilot_bench.runner.apply_perturbation", boom)
        monkeypatch.setattr("vrp_copilot_bench.runner.run_action", boom)

        outcome = run_one_action(key, tmp_path)
        assert outcome is None
        assert has_checkpoint(tmp_path, key)


# ---------------------------------------------------------------------------
# run_one_action: success path


class TestRunOneActionSuccess:
    def test_writes_checkpoint_on_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")

        def fake_run_action(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            assert action == "reuse_direct"
            assert perturbed == (
                "perturbed",
                ("instance", "X-n101-k25"),
                ("spec", "CAP_1"),
                ("baseline", "X-n101-k25"),
            )
            assert baseline == ("baseline", "X-n101-k25")
            return _make_result(action=action, obj=42.0)

        _patch_runner_deps(monkeypatch, fake_run_action=fake_run_action)

        outcome = run_one_action(key, tmp_path)
        assert outcome is None
        assert has_checkpoint(tmp_path, key)

    def test_no_failure_record_on_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")
        _patch_runner_deps(monkeypatch, fake_run_action=lambda a, p, b: _make_result(action=a))
        run_one_action(key, tmp_path)
        assert list_failures(tmp_path) == {}


# ---------------------------------------------------------------------------
# run_one_action: failure recording


class TestRunOneActionFailure:
    def test_writes_failure_record_on_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")

        def boom(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            raise RuntimeError("solver crashed")

        _patch_runner_deps(monkeypatch, fake_run_action=boom)

        outcome = run_one_action(key, tmp_path)
        assert isinstance(outcome, RunFailure)
        assert outcome.key == key
        assert outcome.exception_class == "RuntimeError"
        assert "solver crashed" in outcome.message

        # Failure record on disk.
        assert failure_path(tmp_path, key).is_file()
        assert key in list_failures(tmp_path)
        # No success checkpoint.
        assert not has_checkpoint(tmp_path, key)

    def test_failure_in_dependency_also_recorded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exception during load_instance / apply_perturbation also gets caught."""
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")

        def boom_load(_iid: str) -> Any:
            raise IOError("instance file missing")

        monkeypatch.setattr("vrp_copilot_bench.runner.load_instance", boom_load)
        # Other deps don't matter; load_instance is first.

        outcome = run_one_action(key, tmp_path)
        assert isinstance(outcome, RunFailure)
        assert outcome.exception_class == "OSError"  # IOError is OSError
        assert key in list_failures(tmp_path)

    def test_keyboard_interrupt_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ctrl-C must NOT be turned into a failure record — it should
        propagate so joblib can shut down the pool cleanly."""
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")

        def interrupt(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            raise KeyboardInterrupt()

        _patch_runner_deps(monkeypatch, fake_run_action=interrupt)
        with pytest.raises(KeyboardInterrupt):
            run_one_action(key, tmp_path)
        # No failure record; we deliberately don't write one for Ctrl-C.
        assert key not in list_failures(tmp_path)


# ---------------------------------------------------------------------------
# Stale tmp file cleanup


class TestCleanupStaleTmpFiles:
    def test_removes_root_tmp_files(self, tmp_path: Path) -> None:
        (tmp_path / "X-n101-k25_CAP_1_reuse_direct.json.tmp.abc").write_text("partial")
        (tmp_path / "X-n101-k25_CAP_1_reuse_direct.json.tmp.def").write_text("partial2")
        (tmp_path / "X-n101-k25_CAP_1_reuse_direct.json").write_text("{}")

        n = cleanup_stale_tmp_files(tmp_path)
        assert n == 2
        # Final files preserved.
        assert (tmp_path / "X-n101-k25_CAP_1_reuse_direct.json").is_file()
        # Tmps gone.
        assert not list(tmp_path.glob("*.tmp.*"))

    def test_removes_failure_dir_tmp_files(self, tmp_path: Path) -> None:
        failures = tmp_path / "_failures"
        failures.mkdir()
        (failures / "X-n101-k25_CAP_1_reuse_direct.json.tmp.xyz").write_text("partial")
        (failures / "X-n101-k25_CAP_1_reuse_direct.json").write_text("{}")

        n = cleanup_stale_tmp_files(tmp_path)
        assert n == 1
        assert not list(failures.glob("*.tmp.*"))

    def test_missing_dir_is_a_noop(self, tmp_path: Path) -> None:
        # Don't create the directory; should return 0 without raising.
        assert cleanup_stale_tmp_files(tmp_path / "does_not_exist") == 0


# ---------------------------------------------------------------------------
# Progress tracker


class TestProgressTracker:
    def test_logs_at_log_every_intervals(self, caplog: pytest.LogCaptureFixture) -> None:
        tracker = _ProgressTracker(total=10, log_every=3)
        tracker.start()
        with caplog.at_level(logging.INFO, logger="vrp_copilot_bench.runner"):
            for _ in range(10):
                tracker.step()
        # Logs at completions 3, 6, 9, and the final 10 (boundary trigger).
        progress_lines = [r.message for r in caplog.records if "done" in r.message]
        assert len(progress_lines) == 4

    def test_does_not_crash_at_zero_elapsed(self) -> None:
        tracker = _ProgressTracker(total=1, log_every=1)
        tracker.start()
        # Calling step right after start gives near-zero elapsed; the
        # ETA computation must not divide by zero.
        tracker.step()


# ---------------------------------------------------------------------------
# Dispatch: 12 stubbed cell-actions across 3 small instances × 4 actions


def _twelve_keys() -> list[ActionRunKey]:
    return [
        ActionRunKey(instance, "CAP_1", action)
        for instance in ("X-n101-k25", "X-n106-k14", "X-n110-k13")
        for action in ("reuse_direct", "nearest_neighbor", "clarke_wright", "pyvrp_10s")
    ]


class TestDispatch:
    def test_twelve_keys_with_four_workers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keys = _twelve_keys()
        tracker = _CallTracker()

        def fake_run_action(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            tracker.record(action, perturbed, baseline)
            return _make_result(action=action)

        _patch_runner_deps(monkeypatch, fake_run_action=fake_run_action)

        progress = _ProgressTracker(total=len(keys), log_every=4)
        progress.start()
        failures = _dispatch_phase(
            keys=keys,
            checkpoint_dir=tmp_path,
            n_workers=4,
            backend="threading",
            progress=progress,
            phase_name="test",
        )

        assert failures == []
        assert len(tracker) == 12
        assert list_completed(tmp_path) == set(keys)
        assert progress.completed == 12

    def test_dispatch_partial_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Some keys succeed, some fail. Failures captured; successes persist."""
        keys = _twelve_keys()
        # Make every pyvrp_10s key fail.
        def fake_run_action(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            if action == "pyvrp_10s":
                raise RuntimeError(f"deliberate failure in {action}")
            return _make_result(action=action)

        _patch_runner_deps(monkeypatch, fake_run_action=fake_run_action)

        progress = _ProgressTracker(total=len(keys), log_every=99)
        progress.start()
        failures = _dispatch_phase(
            keys=keys, checkpoint_dir=tmp_path, n_workers=4,
            backend="threading", progress=progress, phase_name="test",
        )

        # 3 instances × 1 failing action = 3 failures.
        assert len(failures) == 3
        assert {f.key.action for f in failures} == {"pyvrp_10s"}
        assert all(f.exception_class == "RuntimeError" for f in failures)

        # Successes (3 instances × 3 surviving actions) on disk.
        assert len(list_completed(tmp_path)) == 9
        # Failure records on disk.
        on_disk_failures = list_failures(tmp_path)
        assert len(on_disk_failures) == 3

    def test_empty_phase_is_noop(self, tmp_path: Path) -> None:
        progress = _ProgressTracker(total=0, log_every=10)
        progress.start()
        failures = _dispatch_phase(
            keys=[], checkpoint_dir=tmp_path, n_workers=4,
            backend="threading", progress=progress, phase_name="empty",
        )
        assert failures == []


# ---------------------------------------------------------------------------
# Resumability


class TestResumability:
    def test_resume_skips_existing_checkpoints(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-populate checkpoints for half the keys; dispatch runs only
        the missing half."""
        keys = _twelve_keys()
        # Pre-complete the first 4 keys (simulates a kill at 4-of-12 done).
        already_done = keys[:4]
        for k in already_done:
            save_result(tmp_path, k, _make_result(action=k.action))

        tracker = _CallTracker()
        def fake(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            tracker.record(action)
            return _make_result(action=action)

        _patch_runner_deps(monkeypatch, fake_run_action=fake)

        progress = _ProgressTracker(total=len(keys), log_every=99)
        progress.start()
        failures = _dispatch_phase(
            keys=keys, checkpoint_dir=tmp_path, n_workers=4,
            backend="threading", progress=progress, phase_name="resume",
        )
        assert failures == []

        # Action was only called for the 8 not-yet-done keys.
        assert len(tracker) == 8
        # All 12 checkpoints exist now.
        assert list_completed(tmp_path) == set(keys)

    def test_failures_are_retried_on_resume(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A previously failed key should be retried (the runner's job is
        to retry; only successful checkpoints filter it out)."""
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")
        # Pre-record a failure.
        save_failure(tmp_path, key, RuntimeError("old failure"))
        assert key in list_failures(tmp_path)

        # Now succeed on the retry.
        _patch_runner_deps(
            monkeypatch,
            fake_run_action=lambda a, p, b: _make_result(action=a),
        )

        outcome = run_one_action(key, tmp_path)
        assert outcome is None
        assert has_checkpoint(tmp_path, key)


# ---------------------------------------------------------------------------
# run_stage_a: end-to-end with a small synthetic key list


class TestRunStageA:
    def test_two_phase_dispatch_partitions_by_size(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The runner must partition small/large and respect the threshold.

        Strategy: monkeypatch enumerate_stage_a to return a tiny mixed-size
        list; run end-to-end; verify both phases ran and ordering held."""
        small_key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")  # 100 customers
        large_key = ActionRunKey("X-n502-k39", "CAP_1", "reuse_direct")  # 501 customers

        monkeypatch.setattr(
            "vrp_copilot_bench.runner.enumerate_stage_a",
            lambda: [large_key, small_key],
        )

        order_seen: list[str] = []
        order_lock = threading.Lock()

        def fake(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            # perturbed = ("perturbed", ("instance", iid), ("spec", pid))
            iid = perturbed[1][1]
            with order_lock:
                order_seen.append(iid)
            return _make_result(action=action)

        _patch_runner_deps(monkeypatch, fake_run_action=fake)

        summary = run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=2,
            workers_large=1,
            large_threshold=400,
            backend="threading",
            progress_log_every=99,
        )

        assert summary.n_attempted == 2
        assert summary.n_succeeded == 2
        assert summary.n_failed == 0
        assert summary.failures == ()
        assert summary.wall_time_seconds >= 0

        # Small phase always runs before large phase.
        assert order_seen == ["X-n101-k25", "X-n502-k39"]

        # Both checkpoints persist.
        assert list_completed(tmp_path) == {small_key, large_key}

    def test_resumability_at_run_stage_a_level(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-populate; run; verify only missing keys executed."""
        keys = _twelve_keys()
        for k in keys[:4]:
            save_result(tmp_path, k, _make_result(action=k.action))

        monkeypatch.setattr(
            "vrp_copilot_bench.runner.enumerate_stage_a",
            lambda: list(keys),
        )

        tracker = _CallTracker()
        def fake(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            tracker.record(action)
            return _make_result(action=action)

        _patch_runner_deps(monkeypatch, fake_run_action=fake)

        summary = run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=2,
            workers_large=1,
            backend="threading",
            progress_log_every=99,
        )

        # filter_completed dropped the 4 pre-existing → only 8 attempted.
        assert summary.n_attempted == 8
        assert summary.n_succeeded == 8
        assert len(tracker) == 8
        assert list_completed(tmp_path) == set(keys)

    def test_run_stage_a_survives_individual_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keys = _twelve_keys()
        monkeypatch.setattr(
            "vrp_copilot_bench.runner.enumerate_stage_a",
            lambda: list(keys),
        )

        def fake(action: str, perturbed: Any, baseline: Any) -> ActionResult:
            if action == "clarke_wright":
                raise ValueError("CW exploded")
            return _make_result(action=action)

        _patch_runner_deps(monkeypatch, fake_run_action=fake)

        summary = run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=2,
            workers_large=1,
            backend="threading",
            progress_log_every=99,
        )
        # 3 CW failures, 9 successes.
        assert summary.n_succeeded == 9
        assert summary.n_failed == 3
        assert {f.key.action for f in summary.failures} == {"clarke_wright"}

    def test_cleanup_runs_at_startup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale tmp file in checkpoint_dir is removed before dispatch."""
        stale = tmp_path / "X-n101-k25_CAP_1_reuse_direct.json.tmp.deadbeef"
        tmp_path.mkdir(exist_ok=True)
        stale.write_text("partial")
        assert stale.exists()

        monkeypatch.setattr(
            "vrp_copilot_bench.runner.enumerate_stage_a",
            lambda: [],
        )
        run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=1,
            workers_large=1,
            backend="threading",
            progress_log_every=99,
        )
        assert not stale.exists()


# ---------------------------------------------------------------------------
# RunSummary smoke test


class TestRunStageAKeysOverride:
    def test_keys_none_uses_enumerate_stage_a(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """keys=None (default) → enumerate_stage_a is called."""
        sentinel_keys = [ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")]
        called = []

        def fake_enumerate() -> list[ActionRunKey]:
            called.append(True)
            return list(sentinel_keys)

        monkeypatch.setattr("vrp_copilot_bench.runner.enumerate_stage_a", fake_enumerate)
        _patch_runner_deps(monkeypatch, fake_run_action=lambda a, p, b: _make_result(action=a))

        summary = run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=1, workers_large=1,
            backend="threading", progress_log_every=99,
        )
        assert called == [True]
        assert summary.n_attempted == 1

    def test_keys_passed_skips_enumerate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """keys=[...] → enumerate_stage_a is NOT called; only passed keys run."""
        passed_keys = [
            ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct"),
            ActionRunKey("X-n106-k14", "CAP_1", "reuse_direct"),
        ]

        def boom() -> list[ActionRunKey]:
            pytest.fail("enumerate_stage_a must not be called when keys is provided")

        monkeypatch.setattr("vrp_copilot_bench.runner.enumerate_stage_a", boom)
        _patch_runner_deps(monkeypatch, fake_run_action=lambda a, p, b: _make_result(action=a))

        summary = run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=1, workers_large=1,
            backend="threading", progress_log_every=99,
            keys=passed_keys,
        )
        assert summary.n_attempted == 2
        assert summary.n_succeeded == 2
        assert list_completed(tmp_path) == set(passed_keys)

    def test_keys_passed_still_filters_completed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keys with existing checkpoints are still filtered out."""
        keys = [
            ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct"),
            ActionRunKey("X-n101-k25", "CAP_1", "nearest_neighbor"),
        ]
        save_result(tmp_path, keys[0], _make_result(action=keys[0].action))

        def boom() -> list[ActionRunKey]:
            pytest.fail("enumerate_stage_a must not be called")
        monkeypatch.setattr("vrp_copilot_bench.runner.enumerate_stage_a", boom)
        _patch_runner_deps(monkeypatch, fake_run_action=lambda a, p, b: _make_result(action=a))

        summary = run_stage_a(
            checkpoint_dir=tmp_path,
            workers_normal=1, workers_large=1,
            backend="threading", progress_log_every=99,
            keys=keys,
        )
        # Pre-existing checkpoint filtered → only 1 attempt this run.
        assert summary.n_attempted == 1


class TestRunSummary:
    def test_str_includes_counts(self) -> None:
        summary = RunSummary(
            n_attempted=10, n_succeeded=8, n_failed=2,
            wall_time_seconds=12.5,
            failures=(
                RunFailure(
                    key=ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct"),
                    exception_class="RuntimeError",
                    message="boom",
                ),
            ),
        )
        s = str(summary)
        assert "8/10 succeeded" in s
        assert "2 failed" in s
        assert "12.5s" in s
        assert "RuntimeError" in s

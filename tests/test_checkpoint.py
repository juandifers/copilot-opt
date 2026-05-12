"""Tests for the per-action-run checkpoint store (Phase 1)."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from vrp_copilot_bench.actions import ACTIONS, ActionResult
from vrp_copilot_bench.checkpoint import (
    ActionRunKey,
    _format_basename,
    _parse_basename,
    checkpoint_path,
    failure_path,
    has_checkpoint,
    iter_completed_paths,
    list_completed,
    list_failures,
    load_result,
    save_failure,
    save_result,
)


# ---------------------------------------------------------------------------
# Helpers

def _make_result(action: str = "reuse_direct", obj: float = 1234.5) -> ActionResult:
    return ActionResult(
        action=action,
        objective=obj,
        feasible=True,
        runtime_seconds=0.42,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={1: 0, 2: 0, 3: 1, 4: 1},
        route_costs={0: 600.5, 1: 634.0},
        customer_costs={1: 100.0, 2: 110.0, 3: 95.5, 4: 105.0},
        routes=[[0, 1, 2, 0], [0, 3, 4, 0]],
        meta={"seed": 1},
    )


def _key(instance: str = "X-n101-k25", pert: str = "CAP_1", action: str = "reuse_direct") -> ActionRunKey:
    return ActionRunKey(instance, pert, action)


# ---------------------------------------------------------------------------
# Key construction & validation


class TestActionRunKey:
    def test_construction(self) -> None:
        k = _key()
        assert k.instance_id == "X-n101-k25"
        assert k.perturbation_id == "CAP_1"
        assert k.action == "reuse_direct"

    def test_frozen_and_hashable(self) -> None:
        k = _key()
        with pytest.raises(Exception):  # FrozenInstanceError, but type varies across versions
            k.action = "other"  # type: ignore[misc]
        # Must be usable as set/dict key.
        assert {k, _key()} == {_key()}

    def test_equality_and_set_membership(self) -> None:
        a = _key("X-n101-k25", "CAP_1", "reuse_direct")
        b = _key("X-n101-k25", "CAP_1", "reuse_direct")
        c = _key("X-n101-k25", "CAP_1", "nearest_neighbor")
        assert a == b
        assert a != c
        assert {a, b, c} == {a, c}

    def test_rejects_empty_fields(self) -> None:
        with pytest.raises(ValueError):
            ActionRunKey("", "CAP_1", "reuse_direct")
        with pytest.raises(ValueError):
            ActionRunKey("X-n101-k25", "", "reuse_direct")
        with pytest.raises(ValueError):
            ActionRunKey("X-n101-k25", "CAP_1", "")

    def test_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError, match="unknown action"):
            ActionRunKey("X-n101-k25", "CAP_1", "not_a_real_action")

    def test_rejects_path_separators(self) -> None:
        with pytest.raises(ValueError):
            ActionRunKey("../../etc", "CAP_1", "reuse_direct")
        with pytest.raises(ValueError):
            ActionRunKey("X-n101-k25", "CAP/1", "reuse_direct")

    def test_rejects_underscore_in_instance_id(self) -> None:
        # Convention to keep the single-underscore filename format unambiguous.
        with pytest.raises(ValueError, match="must not contain '_'"):
            ActionRunKey("bad_instance", "CAP_1", "reuse_direct")


# ---------------------------------------------------------------------------
# Filename roundtrip


class TestFilenameRoundtrip:
    @pytest.mark.parametrize("action", ACTIONS)
    @pytest.mark.parametrize(
        "instance,pert",
        [
            ("X-n101-k25", "CAP_1"),
            ("X-n134-k13", "DIST_4"),
            ("X-n200-k36", "DEM_2"),
            ("X-n429-k61", "INS_3"),
        ],
    )
    def test_roundtrip(self, instance: str, pert: str, action: str) -> None:
        key = ActionRunKey(instance, pert, action)
        basename = _format_basename(key)
        parsed = _parse_basename(basename)
        assert parsed == key, f"roundtrip failed: {basename!r} -> {parsed!r}"

    def test_basename_format_matches_prompt_example(self) -> None:
        key = ActionRunKey("X-n101-k25", "CAP_1", "reuse_direct")
        assert _format_basename(key) == "X-n101-k25_CAP_1_reuse_direct.json"

    def test_parse_rejects_unknown_suffix(self) -> None:
        with pytest.raises(ValueError):
            _parse_basename("X-n101-k25_CAP_1_unknown_action.json")

    def test_parse_rejects_non_json(self) -> None:
        with pytest.raises(ValueError):
            _parse_basename("X-n101-k25_CAP_1_reuse_direct.txt")


# ---------------------------------------------------------------------------
# Save / load


class TestSaveLoad:
    def test_save_then_load(self, tmp_path: Path) -> None:
        key = _key()
        result = _make_result()
        save_result(tmp_path, key, result)
        assert has_checkpoint(tmp_path, key)
        loaded = load_result(tmp_path, key)
        assert loaded == result

    def test_int_keyed_dicts_roundtrip(self, tmp_path: Path) -> None:
        """JSON stringifies dict keys; from_dict must coerce them back to int."""
        key = _key()
        result = ActionResult(
            action="reuse_direct",
            objective=1000.0,
            feasible=True,
            runtime_seconds=0.1,
            n_overload=0,
            max_overload_fraction=0.0,
            assignment={1: 0, 2: 0, 3: 1, 99: 7},
            route_costs={0: 100.0, 1: 200.0, 7: 300.0},
            customer_costs={1: 50.0, 2: 60.0, 3: 70.0, 99: 80.0},
        )
        save_result(tmp_path, key, result)
        loaded = load_result(tmp_path, key)
        assert loaded == result
        for d in (loaded.assignment, loaded.route_costs, loaded.customer_costs):
            assert all(isinstance(k, int) for k in d), f"non-int key in {d!r}"
        assert all(isinstance(v, int) for v in loaded.assignment.values())
        assert all(isinstance(v, float) for v in loaded.route_costs.values())
        assert all(isinstance(v, float) for v in loaded.customer_costs.values())

    def test_infeasible_result_roundtrip(self, tmp_path: Path) -> None:
        """Action with capacity overload still serialises cleanly."""
        key = _key("X-n101-k25", "CAP_4", "reuse_direct")
        result = ActionResult(
            action="reuse_direct",
            objective=1500.0,
            feasible=False,
            runtime_seconds=0.05,
            n_overload=3,
            max_overload_fraction=0.18,
            assignment={1: 0, 2: 0, 3: 1, 4: 1, 5: 2},
            route_costs={0: 700.0, 1: 500.0, 2: 300.0},
            customer_costs={1: 250.0, 2: 200.0, 3: 230.0, 4: 240.0, 5: 220.0},
            routes=[[0, 1, 2, 0], [0, 3, 4, 0], [0, 5, 0]],
            meta={"perturbed_capacity": 80.0},
        )
        save_result(tmp_path, key, result)
        loaded = load_result(tmp_path, key)
        assert loaded == result
        assert loaded.feasible is False
        assert loaded.n_overload == 3
        assert loaded.max_overload_fraction == pytest.approx(0.18)

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "does" / "not" / "exist"
        save_result(nested, _key(), _make_result())
        assert (nested / "X-n101-k25_CAP_1_reuse_direct.json").is_file()

    def test_overwrite_is_last_writer_wins(self, tmp_path: Path) -> None:
        key = _key()
        save_result(tmp_path, key, _make_result(obj=1.0))
        save_result(tmp_path, key, _make_result(obj=2.0))
        assert load_result(tmp_path, key).objective == 2.0

    def test_has_checkpoint_false_when_absent(self, tmp_path: Path) -> None:
        assert has_checkpoint(tmp_path, _key()) is False

    def test_checkpoint_path_layout(self, tmp_path: Path) -> None:
        key = _key()
        assert checkpoint_path(tmp_path, key) == tmp_path / "X-n101-k25_CAP_1_reuse_direct.json"

    def test_failure_path_layout(self, tmp_path: Path) -> None:
        key = _key()
        assert failure_path(tmp_path, key) == tmp_path / "_failures" / "X-n101-k25_CAP_1_reuse_direct.json"


# ---------------------------------------------------------------------------
# Atomic write semantics


class TestAtomicity:
    def test_partial_tmp_file_is_not_treated_as_completed(self, tmp_path: Path) -> None:
        """Simulate a kill mid-write: a .tmp file exists but the .json does not."""
        key = _key()
        # Manually write a "partial" tmp file with the same prefix our writer uses.
        target = checkpoint_path(tmp_path, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = tmp_path / (target.name + ".tmp.deadbeef")
        partial.write_text("{ partial json")  # not even valid JSON

        assert has_checkpoint(tmp_path, key) is False
        assert list_completed(tmp_path) == set()
        # The partial file must not be confused for a completed checkpoint.
        completed_paths = list(iter_completed_paths(tmp_path))
        assert partial not in completed_paths

    def test_tmp_file_cleaned_up_on_serialisation_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the encoder raises, no tmp file should remain littering the dir."""
        key = _key()

        class Unserialisable:
            pass

        bad = ActionResult(
            action="reuse_direct",
            objective=None,
            feasible=True,
            runtime_seconds=0.1,
            n_overload=0,
            max_overload_fraction=0.0,
            assignment={1: 0},
            route_costs={0: 1.0},
            customer_costs={1: 1.0},
            routes=[],
            meta={"bad": Unserialisable()},  # json.dump will raise TypeError
        )
        with pytest.raises(TypeError):
            save_result(tmp_path, key, bad)

        # No leftover tmp or final files in the directory.
        leftovers = [p.name for p in tmp_path.iterdir()]
        assert leftovers == [], f"unexpected leftovers: {leftovers}"

    def test_concurrent_writes_to_different_keys(self, tmp_path: Path) -> None:
        """100 unique keys, written from a thread pool, must all be readable."""
        # Build 100 distinct keys by varying the perturbation index and action.
        instances = [f"X-n{100 + i}-k20" for i in range(20)]  # 20 instances
        pert_ids = ["CAP_1", "CAP_2", "CAP_3", "CAP_4", "DIST_1"]  # 5 perts
        keys = [
            ActionRunKey(instances[i], pert_ids[j], "reuse_direct")
            for i in range(20)
            for j in range(5)
        ]
        assert len(keys) == 100
        assert len(set(keys)) == 100

        results = {k: _make_result(obj=float(i)) for i, k in enumerate(keys)}

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(save_result, tmp_path, k, results[k]) for k in keys]
            for f in as_completed(futures):
                f.result()  # propagate exceptions if any

        # Every key must be readable and round-trip its objective.
        completed = list_completed(tmp_path)
        assert completed == set(keys)
        for k in keys:
            assert load_result(tmp_path, k).objective == results[k].objective


# ---------------------------------------------------------------------------
# Listing


class TestListing:
    def test_list_completed_empty(self, tmp_path: Path) -> None:
        assert list_completed(tmp_path) == set()

    def test_list_completed_missing_dir(self, tmp_path: Path) -> None:
        assert list_completed(tmp_path / "nope") == set()

    def test_list_completed_after_partial_run(self, tmp_path: Path) -> None:
        keys = [
            _key("X-n101-k25", "CAP_1", "reuse_direct"),
            _key("X-n101-k25", "CAP_1", "nearest_neighbor"),
            _key("X-n101-k25", "CAP_2", "reuse_direct"),
        ]
        for k in keys[:2]:
            save_result(tmp_path, k, _make_result(action=k.action))
        assert list_completed(tmp_path) == set(keys[:2])

    def test_failures_excluded_from_completed(self, tmp_path: Path) -> None:
        good = _key("X-n101-k25", "CAP_1", "reuse_direct")
        bad = _key("X-n101-k25", "CAP_2", "pyvrp_60s")
        save_result(tmp_path, good, _make_result())
        save_failure(tmp_path, bad, RuntimeError("solver crashed"))

        assert list_completed(tmp_path) == {good}
        failures = list_failures(tmp_path)
        assert failures == {bad: "RuntimeError"}

    def test_save_failure_contents(self, tmp_path: Path) -> None:
        key = _key("X-n101-k25", "CAP_4", "pyvrp_60s")
        save_failure(tmp_path, key, ValueError("infeasible perturbation"))
        f_path = failure_path(tmp_path, key)
        assert f_path.is_file()
        payload = json.loads(f_path.read_text())
        assert payload["exception_class"] == "ValueError"
        assert payload["message"] == "infeasible perturbation"
        assert payload["instance_id"] == "X-n101-k25"
        assert payload["perturbation_id"] == "CAP_4"
        assert payload["action"] == "pyvrp_60s"

    def test_unparseable_filename_is_skipped(self, tmp_path: Path) -> None:
        # A foreign file in the dir must not crash list_completed.
        (tmp_path / "README.json").write_text("{}")
        save_result(tmp_path, _key(), _make_result())
        assert list_completed(tmp_path) == {_key()}

    def test_iter_completed_paths_skips_failures_subdir(self, tmp_path: Path) -> None:
        good = _key()
        bad = _key("X-n200-k36", "CAP_3", "pyvrp_60s")
        save_result(tmp_path, good, _make_result())
        save_failure(tmp_path, bad, RuntimeError("x"))
        paths = list(iter_completed_paths(tmp_path))
        assert len(paths) == 1
        assert paths[0].name == "X-n101-k25_CAP_1_reuse_direct.json"


# ---------------------------------------------------------------------------
# Atomicity stress: kill mid-write via simulated crash


class TestKillMidWrite:
    def test_simulated_kill_after_tmp_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch os.replace to raise after the tmp file is written; the
        on-disk state must look not-completed and have no leftover tmp file
        once we manually clean (matching the real crash behaviour where the
        tmp file is left until the next successful write or restart cleanup).
        """
        key = _key()

        original_replace = os.replace

        def boom(src, dst):
            raise KeyboardInterrupt("simulated kill before rename")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(KeyboardInterrupt):
            save_result(tmp_path, key, _make_result())
        monkeypatch.setattr(os, "replace", original_replace)

        # The crash leaves no completed checkpoint: this is the key invariant.
        assert has_checkpoint(tmp_path, key) is False
        assert list_completed(tmp_path) == set()

        # A subsequent successful write recovers cleanly.
        save_result(tmp_path, key, _make_result(obj=999.0))
        assert has_checkpoint(tmp_path, key) is True
        assert load_result(tmp_path, key).objective == 999.0

"""Tests for the PyVRP-backed instance loader."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from vrp_copilot_bench.instances import (
    DEFAULT_INSTANCE_DIR,
    DEFAULT_ROSTER_PATH,
    Instance,
    list_stage_a_instances,
    load_instance,
    n_customers_for,
)

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


# ---------------------------------------------------------------------------
# Parser correctness


@requires_pyvrp
class TestLoadInstance:
    @pytest.mark.skipif(not _instance_present("X-n101-k25"), reason="X-n101-k25.vrp missing")
    def test_x_n101_k25_known_values(self) -> None:
        """Verified against the canonical CVRPLIB X-n101-k25 file."""
        inst = load_instance("X-n101-k25")
        assert isinstance(inst, Instance)
        assert inst.instance_id == "X-n101-k25"
        assert inst.n_customers == 100
        assert inst.capacity == 206
        # Depot coordinates from the .vrp file (NODE_COORD_SECTION row 1).
        assert inst.coords[0, 0] == pytest.approx(365.0)
        assert inst.coords[0, 1] == pytest.approx(689.0)
        # demands[0] is depot, demands[1..] are clients.
        assert inst.demands[0] == 0
        assert inst.demands.sum() == 5147

    @pytest.mark.skipif(not _instance_present("X-n200-k36"), reason="X-n200-k36.vrp missing")
    def test_x_n200_k36_known_values(self) -> None:
        inst = load_instance("X-n200-k36")
        assert inst.n_customers == 199
        assert inst.capacity == 402
        assert inst.coords[0, 0] == pytest.approx(957.0)
        assert inst.coords[0, 1] == pytest.approx(135.0)
        assert inst.demands[0] == 0
        assert inst.demands.sum() == 14263

    @pytest.mark.skipif(not _instance_present("X-n247-k50"), reason="X-n247-k50.vrp missing")
    def test_x_n247_k50_known_values(self) -> None:
        inst = load_instance("X-n247-k50")
        assert inst.n_customers == 246
        assert inst.capacity == 134
        assert inst.coords[0, 0] == pytest.approx(500.0)
        assert inst.coords[0, 1] == pytest.approx(500.0)

    @pytest.mark.skipif(not _instance_present("X-n101-k25"), reason="needs sample instance")
    def test_array_shapes_and_dtypes(self) -> None:
        inst = load_instance("X-n101-k25")
        assert inst.coords.shape == (inst.n_customers + 1, 2)
        assert inst.demands.shape == (inst.n_customers + 1,)
        assert inst.coords.dtype == np.float64
        assert inst.demands.dtype == np.int64
        assert inst.depot_index == 0

    @pytest.mark.skipif(not _instance_present("X-n101-k25"), reason="needs sample instance")
    def test_n_customers_matches_filename_parser(self) -> None:
        """Parser-derived n_customers and filename-derived n_customers must agree."""
        inst = load_instance("X-n101-k25")
        assert inst.n_customers == n_customers_for("X-n101-k25")

    @pytest.mark.skipif(not _instance_present("X-n101-k25"), reason="needs sample instance")
    def test_total_demand_does_not_exceed_capacity_x_n_vehicles(self) -> None:
        """Sanity: feasibility requires sum(demand) <= capacity * n_vehicles."""
        inst = load_instance("X-n101-k25")
        assert inst.demands.sum() <= inst.capacity * inst.n_vehicles

    def test_missing_instance_raises_filenotfound_with_pointer(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError) as excinfo:
            load_instance("X-n999-k99", instance_dir=tmp_path)
        msg = str(excinfo.value)
        assert "X-n999-k99.vrp" in msg
        assert "download_instances.py" in msg, "error should point at the download script"

    @pytest.mark.skipif(not _instance_present("X-n101-k25"), reason="needs sample instance")
    def test_instance_dir_kwarg_overrides_default(self, tmp_path: Path) -> None:
        # tmp_path has no .vrp files → should error even though default dir does.
        with pytest.raises(FileNotFoundError):
            load_instance("X-n101-k25", instance_dir=tmp_path)

    @pytest.mark.skipif(not _instance_present("X-n101-k25"), reason="needs sample instance")
    def test_env_var_overrides_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VRP_COPILOT_BENCH_INSTANCE_DIR", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            load_instance("X-n101-k25")


# ---------------------------------------------------------------------------
# Roster file


class TestListStageAInstances:
    def test_default_roster_is_distinct_uchoa_ids(self) -> None:
        # Prereg §5.1 v0.5: roster expanded to 68, the full eligible pool.
        ids = list_stage_a_instances()
        assert len(ids) == 68
        assert len(set(ids)) == 68
        for iid in ids:
            assert re.match(r"^X-n\d+-k\d+$", iid), f"non-Uchoa-X id in roster: {iid!r}"

    def test_returns_list_in_file_order(self, tmp_path: Path) -> None:
        roster = tmp_path / "roster.txt"
        roster.write_text("X-n200-k36\nX-n101-k25\nX-n247-k50\n")
        assert list_stage_a_instances(roster_path=roster) == [
            "X-n200-k36",
            "X-n101-k25",
            "X-n247-k50",
        ]

    def test_skips_blank_lines_and_comments(self, tmp_path: Path) -> None:
        roster = tmp_path / "roster.txt"
        roster.write_text(
            "# header comment\n"
            "\n"
            "X-n101-k25\n"
            "   \n"
            "  # indented comment\n"
            "X-n200-k36\n"
        )
        assert list_stage_a_instances(roster_path=roster) == ["X-n101-k25", "X-n200-k36"]

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        roster = tmp_path / "roster.txt"
        roster.write_text("  X-n101-k25  \n\tX-n200-k36\t\n")
        assert list_stage_a_instances(roster_path=roster) == ["X-n101-k25", "X-n200-k36"]

    def test_missing_file_raises_filenotfound_with_pointer(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError) as excinfo:
            list_stage_a_instances(roster_path=missing)
        msg = str(excinfo.value)
        assert str(missing) in msg
        assert "select_instances.py" in msg, "error should point at the selection script"

    def test_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        roster = tmp_path / "empty.txt"
        roster.write_text("# only comments\n\n\n")
        with pytest.raises(ValueError) as excinfo:
            list_stage_a_instances(roster_path=roster)
        assert "no instance ids" in str(excinfo.value).lower()

    def test_env_var_overrides_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        roster = tmp_path / "custom_roster.txt"
        roster.write_text("X-n101-k25\nX-n200-k36\n")
        monkeypatch.setenv("VRP_COPILOT_BENCH_ROSTER_PATH", str(roster))
        assert list_stage_a_instances() == ["X-n101-k25", "X-n200-k36"]

    def test_kwarg_takes_precedence_over_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_roster = tmp_path / "env.txt"
        env_roster.write_text("X-n101-k25\n")
        kwarg_roster = tmp_path / "kwarg.txt"
        kwarg_roster.write_text("X-n200-k36\n")
        monkeypatch.setenv("VRP_COPILOT_BENCH_ROSTER_PATH", str(env_roster))
        assert list_stage_a_instances(roster_path=kwarg_roster) == ["X-n200-k36"]


# ---------------------------------------------------------------------------
# n_customers_for (filename parser)


class TestNCustomersFor:
    def test_parses_three_digit_id(self) -> None:
        assert n_customers_for("X-n101-k25") == 100

    def test_parses_four_digit_id(self) -> None:
        assert n_customers_for("X-n1001-k43") == 1000

    def test_parses_large_n(self) -> None:
        assert n_customers_for("X-n502-k39") == 501

    def test_rejects_non_uchoa_id(self) -> None:
        with pytest.raises(ValueError):
            n_customers_for("not-an-uchoa-id")

    def test_rejects_partial_match(self) -> None:
        with pytest.raises(ValueError):
            n_customers_for("X-n101-k25-extra")


# ---------------------------------------------------------------------------
# Default-path anchoring


class TestDefaultPaths:
    def test_default_roster_path_resolves_to_repo(self) -> None:
        """Anchored to project root via __file__, not CWD."""
        assert DEFAULT_ROSTER_PATH.is_absolute()
        assert DEFAULT_ROSTER_PATH.name == "stage_a_instances.txt"
        assert DEFAULT_ROSTER_PATH.parent.name == "instances"

    def test_default_instance_dir_resolves_to_repo(self) -> None:
        assert DEFAULT_INSTANCE_DIR.is_absolute()
        assert DEFAULT_INSTANCE_DIR.name == "instances"
        assert DEFAULT_INSTANCE_DIR.parent.name == "data"

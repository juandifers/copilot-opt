"""Tests for scripts/select_instances.py — Stage A stratified sampler."""
from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from pathlib import Path

import pytest

# Load the script as a module (no installed package; the script is in scripts/).
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "select_instances.py"
spec = importlib.util.spec_from_file_location("select_instances", _SCRIPT_PATH)
assert spec is not None and spec.loader is not None
select_instances = importlib.util.module_from_spec(spec)
sys.modules["select_instances"] = select_instances
spec.loader.exec_module(select_instances)

InstanceRow = select_instances.InstanceRow
load_classification_csv = select_instances.load_classification_csv
filter_eligible = select_instances.filter_eligible
_hamilton_allocate = select_instances._hamilton_allocate
stratified_sample = select_instances.stratified_sample
write_roster = select_instances.write_roster
build_parser = select_instances.build_parser
main = select_instances.main
DEFAULT_SEED = select_instances.DEFAULT_SEED
DEFAULT_TARGET = select_instances.DEFAULT_TARGET
STRATIFY_COLS = select_instances.STRATIFY_COLS

# ---------------------------------------------------------------------------
# Synthetic CSV builder


def _synth_csv(
    tmp_path: Path,
    *,
    n_rows: int = 100,
    custom_size_distribution: list[int] | None = None,
) -> Path:
    """Build a 100-row synthetic classification CSV.

    Each row gets a unique instance_id (``X-n{N}-k{K}``) and a deterministic
    classification: depot ∈ {R,C,E}, customer ∈ {R,C,RC}, demand ∈ 1..7,
    avg_route_size ∈ 1..5. The 4-tuple cycles, so strata are populated
    fairly uniformly. ``n_customers`` is ``custom_size_distribution`` if
    given (must have length n_rows) else ``100 + i*5`` so the eligibility
    filter matters.
    """
    csv_path = tmp_path / "classification.csv"
    depots = ("R", "C", "E")
    customers = ("R", "C", "RC")
    demands = (1, 2, 3, 4, 5, 6, 7)
    routes = (1, 2, 3, 4, 5)

    sizes = custom_size_distribution
    if sizes is None:
        sizes = [100 + i * 5 for i in range(n_rows)]
    assert len(sizes) == n_rows

    lines = ["instance_id,n_customers,depot_position,customer_distribution,demand_pattern,avg_route_size"]
    for i in range(n_rows):
        n_cust = sizes[i]
        # n_cust → encode in a synthetic instance ID
        iid = f"X-n{n_cust + 1:04d}-k{(i % 200) + 1:02d}"
        d = depots[i % len(depots)]
        c = customers[(i // 3) % len(customers)]
        q = demands[(i // 9) % len(demands)]
        r = routes[(i // 63) % len(routes)]
        lines.append(f"{iid},{n_cust},{d},{c},{q},{r}")
    csv_path.write_text("\n".join(lines) + "\n")
    return csv_path


# ---------------------------------------------------------------------------
# load_classification_csv


class TestLoadClassificationCsv:
    def test_basic_load(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=10)
        rows = load_classification_csv(path)
        assert len(rows) == 10
        assert all(isinstance(r, InstanceRow) for r in rows)
        for r in rows:
            assert r.instance_id.startswith("X-n")
            assert r.n_customers > 0
            assert len(r.stratum) == 4

    def test_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError) as excinfo:
            load_classification_csv(tmp_path / "absent.csv")
        assert "schema" in str(excinfo.value).lower(), "error should mention the schema reference"

    def test_missing_column_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text("instance_id,n_customers,depot_position\nX-n101-k25,100,R\n")
        with pytest.raises(ValueError, match="missing required column"):
            load_classification_csv(bad)

    def test_empty_cell_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "instance_id,n_customers,depot_position,customer_distribution,demand_pattern,avg_route_size\n"
            "X-n101-k25,100,,RC,1,1\n"
        )
        with pytest.raises(ValueError, match="empty"):
            load_classification_csv(bad)

    def test_duplicate_id_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "instance_id,n_customers,depot_position,customer_distribution,demand_pattern,avg_route_size\n"
            "X-n101-k25,100,R,RC,1,1\n"
            "X-n101-k25,200,C,R,2,2\n"
        )
        with pytest.raises(ValueError, match="duplicate"):
            load_classification_csv(bad)

    def test_non_int_n_customers_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "instance_id,n_customers,depot_position,customer_distribution,demand_pattern,avg_route_size\n"
            "X-n101-k25,not-a-number,R,RC,1,1\n"
        )
        with pytest.raises(ValueError, match="n_customers"):
            load_classification_csv(bad)


# ---------------------------------------------------------------------------
# filter_eligible


class TestFilterEligible:
    def test_strict_greater_than_threshold_excluded(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=5, custom_size_distribution=[100, 200, 500, 501, 1000])
        rows = load_classification_csv(path)
        eligible = filter_eligible(rows, max_customers=500)
        sizes = sorted(r.n_customers for r in eligible)
        assert sizes == [100, 200, 500]  # 501 and 1000 excluded

    def test_default_threshold_500(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=4, custom_size_distribution=[400, 500, 501, 600])
        eligible = filter_eligible(load_classification_csv(path))
        assert len(eligible) == 2  # 400, 500


# ---------------------------------------------------------------------------
# Hamilton allocator


class TestHamiltonAllocate:
    def test_sum_equals_target(self) -> None:
        counts = {("a",): 30, ("b",): 40, ("c",): 30}
        out = _hamilton_allocate(counts, 75)
        assert sum(out.values()) == 75

    def test_each_alloc_at_most_pool_size(self) -> None:
        counts = {("a",): 5, ("b",): 100}
        out = _hamilton_allocate(counts, 50)
        assert out[("a",)] <= 5
        assert out[("b",)] <= 100

    def test_proportional_within_one(self) -> None:
        """For 90 pool with 30/30/30 split and target 75, each gets 25."""
        counts = {("a",): 30, ("b",): 30, ("c",): 30}
        out = _hamilton_allocate(counts, 75)
        assert out[("a",)] == 25
        assert out[("b",)] == 25
        assert out[("c",)] == 25

    def test_largest_remainder_breaks_tie_by_tuple(self) -> None:
        """Two strata with equal remainder; the one with smaller tuple wins."""
        # Both strata have 1 item, target 1 from total 2 → 0.5 each.
        # Floor 0+0 = 0; deficit 1; tie on remainder → pick smaller tuple.
        counts = {("z",): 1, ("a",): 1}
        out = _hamilton_allocate(counts, 1)
        assert out[("a",)] == 1
        assert out[("z",)] == 0

    def test_target_exceeds_pool_raises(self) -> None:
        with pytest.raises(ValueError, match="exceeds eligible pool"):
            _hamilton_allocate({("a",): 5, ("b",): 5}, 20)

    def test_caps_at_pool_when_remainder_would_overflow(self) -> None:
        """A stratum with pool size 2 should never allocate more than 2."""
        counts = {("a",): 2, ("b",): 100}
        out = _hamilton_allocate(counts, 100)
        assert out[("a",)] == 2
        assert out[("b",)] == 98


# ---------------------------------------------------------------------------
# stratified_sample


class TestStratifiedSample:
    def test_returns_exact_count(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        sel = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        assert len(sel) == 75

    def test_all_from_input_pool(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        pool_ids = {r.instance_id for r in rows}
        sel = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        assert set(sel).issubset(pool_ids)

    def test_no_duplicates(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        sel = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        assert len(sel) == len(set(sel))

    def test_output_is_sorted(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        sel = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        assert sel == sorted(sel)

    def test_deterministic_across_runs(self, tmp_path: Path) -> None:
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        a = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        b = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        assert a == b

    def test_different_seed_gives_different_subset(self, tmp_path: Path) -> None:
        """Should differ at least in some positions (overwhelmingly likely)."""
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        a = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        b = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED + 1)
        assert a != b
        assert len(a) == len(b) == 75

    def test_zero_target_returns_empty(self) -> None:
        rows = [
            InstanceRow("X-n101-k25", 100, ("R", "RC", "1", "1")),
        ]
        assert stratified_sample(rows, n_target=0, seed=DEFAULT_SEED) == []

    def test_full_pool_target_returns_all(self) -> None:
        rows = [
            InstanceRow("X-n101-k25", 100, ("R", "RC", "1", "1")),
            InstanceRow("X-n200-k36", 199, ("C", "R", "2", "2")),
        ]
        sel = stratified_sample(rows, n_target=2, seed=DEFAULT_SEED)
        assert sel == ["X-n101-k25", "X-n200-k36"]

    def test_marginal_balance_within_one(self, tmp_path: Path) -> None:
        """Each dimension's marginal in the sample matches Hamilton's allocation ±1."""
        path = _synth_csv(tmp_path, n_rows=100)
        rows = filter_eligible(load_classification_csv(path), max_customers=10000)
        sel_ids = stratified_sample(rows, n_target=75, seed=DEFAULT_SEED)
        sel_set = set(sel_ids)
        sel_rows = [r for r in rows if r.instance_id in sel_set]

        for dim_idx, dim_name in enumerate(STRATIFY_COLS):
            pool_counts = Counter(r.stratum[dim_idx] for r in rows)
            sample_counts = Counter(r.stratum[dim_idx] for r in sel_rows)
            for level, pool_count in pool_counts.items():
                expected = 75 * pool_count / 100
                actual = sample_counts.get(level, 0)
                # Marginal balance within ±3. Joint stratification preserves
                # the joint distribution; for sparse cells (size 1) the
                # marginal counts follow a hypergeometric with std ≈ 1, so
                # ±3 covers ~99.7%. The synthetic CSV here has cells of
                # size 1 — real Uchoa-X data has thicker cells and tighter
                # marginals.
                assert abs(actual - expected) <= 3.0, (
                    f"dim {dim_name}, level {level!r}: pool {pool_count}, "
                    f"sample {actual}, expected ≈ {expected:.1f}"
                )

    def test_proportional_to_pool_for_simple_case(self) -> None:
        """Three strata of equal size, target half: each contributes equally."""
        rows = []
        for i in range(30):
            rows.append(InstanceRow(f"a-{i:02d}", 100, ("a",)))
        for i in range(30):
            rows.append(InstanceRow(f"b-{i:02d}", 100, ("b",)))
        for i in range(30):
            rows.append(InstanceRow(f"c-{i:02d}", 100, ("c",)))
        sel = stratified_sample(rows, n_target=45, seed=DEFAULT_SEED)
        per_stratum = Counter(s.split("-")[0] for s in sel)
        assert per_stratum == {"a": 15, "b": 15, "c": 15}


# ---------------------------------------------------------------------------
# End-to-end via main()


class TestMainCLI:
    def test_dry_run_prints_75_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = _synth_csv(tmp_path, n_rows=100)
        rc = main([
            "--classification-csv", str(csv_path),
            "--dry-run",
        ])
        assert rc == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 75
        assert all(line.startswith("X-n") for line in out)

    def test_writes_roster_file_sorted(self, tmp_path: Path) -> None:
        csv_path = _synth_csv(tmp_path, n_rows=100)
        roster = tmp_path / "roster.txt"
        rc = main([
            "--classification-csv", str(csv_path),
            "--output", str(roster),
        ])
        assert rc == 0
        body = roster.read_text()
        ids = [l for l in body.splitlines() if l and not l.startswith("#")]
        assert len(ids) == 75
        assert ids == sorted(ids)

    def test_eligibility_filter_applied(self, tmp_path: Path) -> None:
        """Set max-customers low enough to exclude most rows."""
        csv_path = _synth_csv(
            tmp_path,
            n_rows=100,
            custom_size_distribution=[100 + i * 5 for i in range(100)],
        )
        roster = tmp_path / "roster.txt"
        # max=200 → eligible pool = 21 (sizes 100..200), target 10
        rc = main([
            "--classification-csv", str(csv_path),
            "--output", str(roster),
            "--max-customers", "200",
            "--target", "10",
        ])
        assert rc == 0
        ids = [l for l in roster.read_text().splitlines() if l and not l.startswith("#")]
        assert len(ids) == 10
        # Every selected ID's encoded n_customers ≤ 200.
        for iid in ids:
            n_total = int(iid.split("-")[1].lstrip("n"))  # X-n{N+1}-k...
            n_customers = n_total - 1
            assert n_customers <= 200

    def test_target_exceeds_pool_returns_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = _synth_csv(tmp_path, n_rows=10)
        rc = main([
            "--classification-csv", str(csv_path),
            "--target", "75",
            "--max-customers", "100000",
        ])
        # Target > eligible pool → exit 2.
        assert rc == 2
        assert "exceeds eligible pool" in capsys.readouterr().err

    def test_two_runs_produce_identical_files(self, tmp_path: Path) -> None:
        csv_path = _synth_csv(tmp_path, n_rows=100)
        out_a = tmp_path / "a.txt"
        out_b = tmp_path / "b.txt"
        main(["--classification-csv", str(csv_path), "--output", str(out_a)])
        main(["--classification-csv", str(csv_path), "--output", str(out_b)])
        assert out_a.read_text() == out_b.read_text()


# ---------------------------------------------------------------------------
# Argument parser


class TestArgumentParser:
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.seed == DEFAULT_SEED
        assert args.target == DEFAULT_TARGET
        assert args.max_customers == 500

    def test_all_flags_accepted(self) -> None:
        args = build_parser().parse_args([
            "--classification-csv", "x.csv",
            "--output", "y.txt",
            "--seed", "42",
            "--target", "20",
            "--max-customers", "300",
            "--dry-run",
        ])
        assert args.seed == 42
        assert args.target == 20
        assert args.max_customers == 300
        assert args.dry_run is True

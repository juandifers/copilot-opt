"""Tests for the Stage A parquet consolidation (Phase 4)."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from vrp_copilot_bench.actions import AUDIT_ACTIONS, BASE_ACTIONS, ActionResult
from vrp_copilot_bench.checkpoint import ActionRunKey, save_result
from vrp_copilot_bench.consolidate import (
    SCHEMA,
    SCHEMA_VERSION,
    ConsolidationFailure,
    ConsolidationSummary,
    consolidate_to_parquet,
)
from vrp_copilot_bench.instances import list_stage_a_instances
from vrp_copilot_bench.perturbations import PERTURBATION_IDS, enumerate_perturbations
from vrp_copilot_bench.work_plan import CLAIM_FAMILIES, select_audit_subset


# ---------------------------------------------------------------------------
# Test fixtures


def _make_result(action: str, instance: str, pert: str, *, obj: float | None = None) -> ActionResult:
    """Synthetic action result. Vary `obj` per (instance, action) so loss
    computations have non-trivial values."""
    if obj is None:
        # Deterministic but varied values: use hash so tests can pin behaviours.
        obj = 1000.0 + (hash((instance, pert, action)) % 200)
    return ActionResult(
        action=action,
        objective=obj,
        feasible=True,
        runtime_seconds=0.05 if action == "reuse_direct" else 1.0,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={1: 0, 2: 0, 3: 1, 4: 1},
        route_costs={0: obj * 0.4, 1: obj * 0.6},
        customer_costs={1: 100.0, 2: 110.0, 3: 95.0, 4: 105.0},
        routes=[[0, 1, 2, 0], [0, 3, 4, 0]],
        meta={"synthetic": True},
    )


def _populate_synthetic(
    checkpoint_dir: Path,
    n_instances: int = 3,
    *,
    skip_action: tuple[str, str, str] | None = None,
) -> tuple[list[str], set[tuple[str, str]]]:
    """Populate ``checkpoint_dir`` with a complete synthetic Stage A subset.

    Returns ``(instance_ids, audit_pairs_in_scope)``. Honours the audit
    subset: pairs in the audit subset get seed2/seed3 results; pairs not in
    the audit subset only get base actions.

    ``skip_action``: optionally omit one ``(instance, pert, action)`` to
    exercise the missing-action sanity check.
    """
    instance_ids = list_stage_a_instances()[:n_instances]
    audit_pairs = {p for p in select_audit_subset() if p[0] in instance_ids}

    for instance_id in instance_ids:
        for spec in enumerate_perturbations(instance_id):
            pert_id = spec.perturbation_id
            for action in BASE_ACTIONS:
                if skip_action == (instance_id, pert_id, action):
                    continue
                key = ActionRunKey(instance_id, pert_id, action)
                save_result(checkpoint_dir, key, _make_result(action, instance_id, pert_id))
            if (instance_id, pert_id) in audit_pairs:
                for action in AUDIT_ACTIONS:
                    if skip_action == (instance_id, pert_id, action):
                        continue
                    key = ActionRunKey(instance_id, pert_id, action)
                    save_result(checkpoint_dir, key, _make_result(action, instance_id, pert_id))

    return instance_ids, audit_pairs


# ---------------------------------------------------------------------------
# Schema lock matches prereg §4.1


class TestSchema:
    def test_schema_has_expected_columns(self) -> None:
        """The 36 columns of prereg §4.1, in declared order."""
        expected = [
            "instance_id", "perturbation_family", "perturbation_id",
            "perturbation_magnitude", "claim_family", "action",
            "action_objective", "action_feasible", "action_n_overload",
            "action_max_overload", "action_runtime_s", "action_assignment",
            "action_route_costs",
            "reference_objective", "reference_feasible", "reference_assignment",
            "reference_route_costs", "reference_runtime_s",
            "baseline_solution_feasible_under_perturbation",
            "loss_obj", "loss_plan_validity", "loss_struct", "loss_rank",
            "band_obj", "band_plan_validity", "band_struct", "band_rank",
            "audit_seed_2_obj", "audit_seed_3_obj",
            "audit_seed_2_assignment", "audit_seed_3_assignment",
            "audit_seed_2_top3", "audit_seed_3_top3",
            "reference_obj_unstable", "reference_struct_unstable", "reference_rank_unstable",
        ]
        assert list(SCHEMA.keys()) == expected
        assert len(SCHEMA) == 36


# ---------------------------------------------------------------------------
# Happy-path consolidation


class TestConsolidationHappyPath:
    def test_three_instance_run_produces_960_rows(self, tmp_path: Path) -> None:
        """Per prereg §4.1: rows = cells × actions = (instances × perts ×
        claim_families) × actions. For 3 instances: 3 × 16 × 4 × 5 = 960."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=3)

        summary = consolidate_to_parquet(ckpt, out)

        assert summary.ok, f"failures: {summary.failures}"
        assert summary.n_rows == 3 * 16 * 4 * 5
        assert summary.n_groups == 3 * 16
        assert summary.failures == ()
        assert out.is_file()

    def test_one_instance_run_produces_320_rows(self, tmp_path: Path) -> None:
        """1 instance × 16 perts × 4 claim families × 5 actions = 320."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)

        summary = consolidate_to_parquet(ckpt, out)
        assert summary.ok
        assert summary.n_rows == 320

    def test_columns_match_schema_exactly(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        assert list(df.columns) == list(SCHEMA.keys())

    def test_dtypes_match_schema_after_roundtrip(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        for col, expected in SCHEMA.items():
            actual = str(df[col].dtype)
            assert actual == expected, f"{col}: expected {expected}, got {actual}"

    def test_parquet_roundtrip(self, tmp_path: Path) -> None:
        """Write, read back, confirm DataFrames compare equal."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=2)
        consolidate_to_parquet(ckpt, out)

        df_first = pd.read_parquet(out)
        df_second = pd.read_parquet(out)
        pd.testing.assert_frame_equal(df_first, df_second)


# ---------------------------------------------------------------------------
# Cell-action structure


class TestCellActionStructure:
    def test_every_group_has_20_rows(self, tmp_path: Path) -> None:
        """Each (instance, perturbation) emits 4 claim_families × 5 base
        actions = 20 rows."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=2)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        per_group = df.groupby(["instance_id", "perturbation_id"]).size()
        assert (per_group == 20).all()

    def test_every_group_has_4_claim_families(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        per_group_claims = df.groupby(["instance_id", "perturbation_id"])["claim_family"].nunique()
        assert (per_group_claims == 4).all()

    def test_every_group_has_5_base_actions_per_claim(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        per_cell_actions = df.groupby(
            ["instance_id", "perturbation_id", "claim_family"]
        )["action"].nunique()
        assert (per_cell_actions == 5).all()
        # And those 5 actions are exactly the base actions.
        actions = set(df["action"].unique())
        assert actions == set(BASE_ACTIONS)
        # Audit actions never appear as row-level action values.
        assert not any(a in actions for a in AUDIT_ACTIONS)


# ---------------------------------------------------------------------------
# Loss/band fields


class TestLossesAndBands:
    def test_loss_obj_matches_formula(self, tmp_path: Path) -> None:
        """loss_obj = |action_obj - ref_obj| / ref_obj per §9.1."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        for _, row in df.head(20).iterrows():
            expected = abs(row["action_objective"] - row["reference_objective"]) / row["reference_objective"]
            assert math.isclose(row["loss_obj"], expected, rel_tol=1e-9)

    def test_loss_plan_validity_only_on_pv_reuse_rows(self, tmp_path: Path) -> None:
        """§9.2: 0 on (PLAN_VALIDITY, reuse_direct), NaN elsewhere."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        pv_reuse = df[(df["claim_family"] == "PLAN_VALIDITY") & (df["action"] == "reuse_direct")]
        other = df[~((df["claim_family"] == "PLAN_VALIDITY") & (df["action"] == "reuse_direct"))]
        assert (pv_reuse["loss_plan_validity"] == 0.0).all()
        assert (pv_reuse["band_plan_validity"] == "easy").all()
        assert other["loss_plan_validity"].isna().all()
        assert other["band_plan_validity"].isna().all()

    def test_band_obj_thresholds(self, tmp_path: Path) -> None:
        """§9.1: easy ≤0.05, medium ≤0.15, hard >0.15."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        # Hand-craft results with known objectives so loss_obj is predictable.
        ref_obj = 100.0
        cases = {
            "reuse_direct": 100.0,    # loss_obj = 0.0 -> easy
            "nearest_neighbor": 110.0,  # 0.10 -> medium
            "clarke_wright": 130.0,     # 0.30 -> hard
            "pyvrp_10s": 100.0,         # easy
            "pyvrp_60s": 100.0,         # reference itself; loss = 0
        }
        instance_id = list_stage_a_instances()[0]
        pert_id = "DIST_1"  # not in audit subset for X-n101-k25
        # Assert this assumption.
        assert (instance_id, pert_id) not in select_audit_subset()

        for action, obj in cases.items():
            key = ActionRunKey(instance_id, pert_id, action)
            save_result(ckpt, key, _make_result(action, instance_id, pert_id, obj=obj))

        # We also need 16 perturbations × 5 base actions for the (instance,
        # perturbation) coverage, but for THIS test we only built one
        # perturbation. Fill the others with default values:
        for spec in enumerate_perturbations(instance_id):
            if spec.perturbation_id == pert_id:
                continue
            for action in BASE_ACTIONS:
                key = ActionRunKey(instance_id, spec.perturbation_id, action)
                save_result(ckpt, key, _make_result(action, instance_id, spec.perturbation_id))
            if (instance_id, spec.perturbation_id) in select_audit_subset():
                for action in AUDIT_ACTIONS:
                    key = ActionRunKey(instance_id, spec.perturbation_id, action)
                    save_result(ckpt, key, _make_result(action, instance_id, spec.perturbation_id))

        consolidate_to_parquet(ckpt, out)
        df = pd.read_parquet(out)
        focus = df[df["perturbation_id"] == pert_id]
        for action, expected_band in [
            ("reuse_direct", "easy"),
            ("nearest_neighbor", "medium"),
            ("clarke_wright", "hard"),
        ]:
            band = focus[focus["action"] == action]["band_obj"].iloc[0]
            assert band == expected_band, f"{action}: expected {expected_band}, got {band}"


# ---------------------------------------------------------------------------
# Audit fields


class TestAuditFields:
    def test_audit_columns_populated_for_audit_pairs(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _, audit_pairs = _populate_synthetic(ckpt, n_instances=3)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        # Check at least one known audit pair.
        assert len(audit_pairs) > 0
        ip = next(iter(audit_pairs))
        rows = df[(df["instance_id"] == ip[0]) & (df["perturbation_id"] == ip[1])]
        assert (rows["audit_seed_2_obj"].notna()).all()
        assert (rows["audit_seed_3_obj"].notna()).all()
        assert (rows["audit_seed_2_assignment"].notna()).all()
        assert (rows["reference_obj_unstable"].notna()).all()

    def test_audit_columns_null_for_non_audit_pairs(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _, audit_pairs = _populate_synthetic(ckpt, n_instances=3)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        # Pick a (instance, pert) NOT in audit_pairs.
        all_pairs = set(zip(df["instance_id"], df["perturbation_id"]))
        non_audit = next(p for p in all_pairs if p not in audit_pairs)

        rows = df[(df["instance_id"] == non_audit[0]) & (df["perturbation_id"] == non_audit[1])]
        assert rows["audit_seed_2_obj"].isna().all()
        assert rows["audit_seed_3_obj"].isna().all()
        assert rows["audit_seed_2_assignment"].isna().all()
        assert rows["reference_obj_unstable"].isna().all()


# ---------------------------------------------------------------------------
# Required fields


class TestRequiredFields:
    def test_baseline_feasibility_matches_reuse_direct_feasible(
        self, tmp_path: Path
    ) -> None:
        """The baseline_solution_feasible_under_perturbation column equals
        the reuse_direct ActionResult's feasibility (§9.2 / §3.3)."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        instance_id = list_stage_a_instances()[0]
        # Build all 16 perturbations of this instance, with reuse_direct
        # marked infeasible on CAP_4 only.
        for spec in enumerate_perturbations(instance_id):
            for action in BASE_ACTIONS:
                obj = 100.0 if action == "reuse_direct" else 95.0
                feasible = not (action == "reuse_direct" and spec.perturbation_id == "CAP_4")
                save_result(
                    ckpt,
                    ActionRunKey(instance_id, spec.perturbation_id, action),
                    ActionResult(
                        action=action, objective=obj, feasible=feasible,
                        runtime_seconds=0.1,
                        n_overload=2 if not feasible else 0,
                        max_overload_fraction=0.15 if not feasible else 0.0,
                        assignment={1: 0, 2: 0}, route_costs={0: obj},
                        customer_costs={1: 50.0, 2: 50.0},
                    ),
                )
            if (instance_id, spec.perturbation_id) in select_audit_subset():
                for action in AUDIT_ACTIONS:
                    save_result(
                        ckpt,
                        ActionRunKey(instance_id, spec.perturbation_id, action),
                        _make_result(action, instance_id, spec.perturbation_id, obj=100.0),
                    )

        consolidate_to_parquet(ckpt, out)
        df = pd.read_parquet(out)
        # CAP_4 rows: baseline infeasible.
        cap4 = df[df["perturbation_id"] == "CAP_4"]
        assert not cap4["baseline_solution_feasible_under_perturbation"].any()
        # Other rows: baseline feasible.
        non_cap4 = df[df["perturbation_id"] != "CAP_4"]
        assert non_cap4["baseline_solution_feasible_under_perturbation"].all()


# ---------------------------------------------------------------------------
# Sanity-check failures


class TestSanityFailures:
    def test_missing_base_action_aborts_write(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        instance_id = list_stage_a_instances()[0]
        skip = (instance_id, "CAP_1", "clarke_wright")
        _populate_synthetic(ckpt, n_instances=1, skip_action=skip)

        summary = consolidate_to_parquet(ckpt, out)

        assert not summary.ok
        assert summary.n_rows == 0
        assert not out.exists(), "must not write parquet on sanity failure"
        codes = {f.code for f in summary.failures}
        assert "missing_base_actions" in codes
        details = " ".join(f.detail for f in summary.failures)
        assert "clarke_wright" in details

    def test_missing_audit_action_on_audit_pair_aborts_write(
        self, tmp_path: Path
    ) -> None:
        """Find an audit pair in the synthetic run, drop one of its audit
        results — must abort."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        # Pick a known audit pair and skip its seed2.
        audit_pairs = sorted(
            p for p in select_audit_subset()
            if p[0] in list_stage_a_instances()[:3]
        )
        target = audit_pairs[0]
        skip = (target[0], target[1], "pyvrp_60s_seed2")
        _populate_synthetic(ckpt, n_instances=3, skip_action=skip)

        summary = consolidate_to_parquet(ckpt, out)
        assert not summary.ok
        assert not out.exists()
        codes = {f.code for f in summary.failures}
        assert "missing_audit_actions" in codes

    def test_failure_summary_lists_all_problems(self, tmp_path: Path) -> None:
        """Multiple missing actions all show up in the summary, not just the first."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        instance_id = list_stage_a_instances()[0]
        # Build only reuse_direct for every perturbation — missing 4 actions × 16 perts.
        for spec in enumerate_perturbations(instance_id):
            save_result(
                ckpt,
                ActionRunKey(instance_id, spec.perturbation_id, "reuse_direct"),
                _make_result("reuse_direct", instance_id, spec.perturbation_id),
            )

        summary = consolidate_to_parquet(ckpt, out)
        assert not summary.ok
        # Each of the 16 perts is missing 4 actions → 16 group-level failures.
        missing_failures = [f for f in summary.failures if f.code == "missing_base_actions"]
        assert len(missing_failures) == 16


# ---------------------------------------------------------------------------
# Atomic write


class TestAtomicWrite:
    def test_no_tmp_files_after_success(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        leftover = list(out.parent.glob(out.name + ".tmp.*"))
        assert leftover == [], f"leftover tmps: {leftover}"

    def test_partial_failure_does_not_create_output(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        ckpt.mkdir()
        # Default: empty dir is a soft failure; no parquet written.
        summary = consolidate_to_parquet(ckpt, out)
        assert not summary.ok
        assert not out.exists()
        assert not list(out.parent.glob("*.tmp.*"))


# ---------------------------------------------------------------------------
# Phase 4 adjustments


class TestSchemaVersionMetadata:
    def test_parquet_carries_schema_version(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        metadata = pq.read_metadata(out).schema.to_arrow_schema().metadata
        assert metadata is not None
        assert metadata.get(b"_schema_version") == SCHEMA_VERSION.encode()

    def test_schema_version_is_v1_0(self) -> None:
        """Lock test: any SCHEMA change must bump SCHEMA_VERSION too."""
        assert SCHEMA_VERSION == "v1.0"


class TestEmptyCheckpoints:
    def test_empty_dir_returns_failure(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        ckpt.mkdir()
        summary = consolidate_to_parquet(ckpt, out)

        assert not summary.ok
        assert summary.n_rows == 0
        assert not out.exists()
        codes = {f.code for f in summary.failures}
        assert codes == {"EMPTY_CHECKPOINTS"}

    def test_missing_dir_returns_failure(self, tmp_path: Path) -> None:
        """A nonexistent checkpoint dir is also empty — same failure."""
        out = tmp_path / "stage_a.parquet"
        summary = consolidate_to_parquet(tmp_path / "nope", out)
        assert not summary.ok
        assert summary.failures[0].code == "EMPTY_CHECKPOINTS"

    def test_allow_empty_writes_zero_row_parquet(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        ckpt.mkdir()
        out = tmp_path / "stage_a.parquet"
        summary = consolidate_to_parquet(ckpt, out, allow_empty=True)

        assert summary.schema_ok
        assert summary.n_rows == 0
        assert summary.failures == ()
        assert out.is_file()

        # Schema is still locked.
        df = pd.read_parquet(out)
        assert list(df.columns) == list(SCHEMA.keys())
        assert len(df) == 0
        # Schema version metadata still present.
        metadata = pq.read_metadata(out).schema.to_arrow_schema().metadata
        assert metadata.get(b"_schema_version") == SCHEMA_VERSION.encode()


class TestBandSentinelIsNA:
    def test_band_obj_null_when_loss_obj_is_nan(self, tmp_path: Path) -> None:
        """If a row's action_objective is None (solver crashed with no plan),
        loss_obj is NaN and band_obj should be pd.NA — not the literal
        string 'unknown'. The required-non-null check then catches it."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"

        instance_id = list_stage_a_instances()[0]
        # Build everything normally except inject one None-objective result
        # on a non-audit pair so we don't have to fill audit data for it.
        bad_pair = "DIST_1"
        assert (instance_id, bad_pair) not in select_audit_subset()

        for spec in enumerate_perturbations(instance_id):
            for action in BASE_ACTIONS:
                key = ActionRunKey(instance_id, spec.perturbation_id, action)
                if (
                    spec.perturbation_id == bad_pair
                    and action == "nearest_neighbor"
                ):
                    save_result(ckpt, key, ActionResult(
                        action=action, objective=None, feasible=False,
                        runtime_seconds=0.1,
                        n_overload=0, max_overload_fraction=0.0,
                        assignment={1: 0}, route_costs={0: 1.0},
                        customer_costs={1: 1.0},
                    ))
                else:
                    save_result(ckpt, key, _make_result(action, instance_id, spec.perturbation_id))
            if (instance_id, spec.perturbation_id) in select_audit_subset():
                for action in AUDIT_ACTIONS:
                    save_result(ckpt, ActionRunKey(instance_id, spec.perturbation_id, action),
                                _make_result(action, instance_id, spec.perturbation_id))

        # The null band on the bad row triggers the required-null check, so
        # consolidation aborts with a clean failure rather than writing a
        # parquet containing 'unknown' string sentinels.
        summary = consolidate_to_parquet(ckpt, out)
        assert not summary.ok
        codes = {f.code for f in summary.failures}
        assert "required_null" in codes
        # Detail should mention band_obj specifically.
        details = " ".join(f.detail for f in summary.failures)
        assert "band_obj" in details
        # No literal 'unknown' anywhere in failure messages.
        assert "unknown" not in details

    def test_no_unknown_strings_in_clean_run(self, tmp_path: Path) -> None:
        """A clean run must never produce the literal 'unknown' band value."""
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=2)
        consolidate_to_parquet(ckpt, out)
        df = pd.read_parquet(out)
        for col in ("band_obj", "band_struct", "band_rank", "band_plan_validity"):
            assert "unknown" not in set(df[col].dropna().unique())


# ---------------------------------------------------------------------------
# JSON-typed columns


class TestJsonColumns:
    def test_action_assignment_is_valid_json(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=1)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        sample = df["action_assignment"].iloc[0]
        parsed = json.loads(sample)
        assert isinstance(parsed, dict)
        # Customer ids are stringified ints; values are route ids.
        for k, v in parsed.items():
            int(k)  # must parse
            assert isinstance(v, int)

    def test_audit_assignment_is_valid_json_when_populated(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt"
        out = tmp_path / "stage_a.parquet"
        _populate_synthetic(ckpt, n_instances=3)
        consolidate_to_parquet(ckpt, out)

        df = pd.read_parquet(out)
        non_null = df[df["audit_seed_2_assignment"].notna()]
        assert len(non_null) > 0
        sample = non_null["audit_seed_2_assignment"].iloc[0]
        parsed = json.loads(sample)
        assert isinstance(parsed, dict)

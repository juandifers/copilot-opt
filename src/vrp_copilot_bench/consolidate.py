"""Consolidate per-action-run JSON checkpoints into the Stage A Parquet table.

Pipeline (per prereg §4.1, with the v0.2 audit-pair amendment from §8.2):

1. Walk ``checkpoint_dir`` for successful checkpoints; load each into an
   :class:`ActionResult`.
2. Group by ``(instance_id, perturbation_id)``. Each group must contain
   all 5 base actions; pairs in the audit subset must additionally have
   both seed-2 and seed-3 audit actions.
3. Use the group's ``pyvrp_60s`` result as the reference (§8.1 — the
   reference and the action are the same physical solve).
4. For each ``(action, claim_family)`` in the group, compute losses and
   bands via :func:`compute_losses_and_bands`. Emit one row.
5. Audit columns get populated for the 240 audit-subset pairs and remain
   null elsewhere.
6. Validate the constructed DataFrame against the schema dict locked from
   §4.1 (column set, dtypes, required-non-NaN constraints).
7. Atomic write: tempfile + ``os.replace``.

Sanity-check failures abort the write — partial parquets are worse than
no parquet — and surface a structured failure list in the
:class:`ConsolidationSummary`.
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .actions import AUDIT_ACTIONS, BASE_ACTIONS, ActionResult
from .baselines import Solution, load_baseline_solution
from .checkpoint import (
    ActionRunKey,
    _parse_basename,
    iter_completed_paths,
    load_result,
)
from .labels import (
    AuditFields,
    compute_audit_fields,
    compute_losses_and_bands,
    null_audit_fields,
)
from .perturbations import PERTURBATION_FAMILY_LABELS, lookup_perturbation
from .work_plan import CLAIM_FAMILIES, select_audit_subset

log = logging.getLogger(__name__)

#: Schema version stamped into the parquet's pyarrow metadata. Bumped
#: when :data:`SCHEMA` changes shape; readers should refuse to load a
#: parquet whose stamped version does not match the version they expect.
SCHEMA_VERSION: str = "v1.0"


# ---------------------------------------------------------------------------
# Schema lock — prereg §4.1


#: Column → pandas dtype string. The 36 columns of prereg §4.1 in declared
#: order. Nullable extension types (``Float64``, ``Int64``, ``boolean``,
#: ``string`` with capitals) are used wherever NaN/null is allowed; numpy
#: types (``float64``, etc.) for non-nullable columns.
SCHEMA: dict[str, str] = {
    # Cell-action key
    "instance_id": "string",
    "perturbation_family": "string",
    "perturbation_id": "string",
    "perturbation_magnitude": "float64",
    "claim_family": "string",
    "action": "string",
    # Action result fields
    "action_objective": "Float64",  # nullable: solver crash with no plan
    "action_feasible": "boolean",
    "action_n_overload": "Int64",
    "action_max_overload": "Float64",
    "action_runtime_s": "float64",
    "action_assignment": "string",
    "action_route_costs": "string",
    # Reference (pyvrp_60s seed=1) fields
    "reference_objective": "Float64",
    "reference_feasible": "boolean",
    "reference_assignment": "string",
    "reference_route_costs": "string",
    "reference_runtime_s": "float64",
    # Plan-validity ground truth (deterministic feasibility check on S)
    "baseline_solution_feasible_under_perturbation": "boolean",
    # Loss columns
    "loss_obj": "Float64",
    "loss_plan_validity": "Float64",  # NaN unless PLAN_VALIDITY × reuse_direct
    "loss_struct": "Float64",
    "loss_rank": "Float64",
    # Band columns
    "band_obj": "string",
    "band_plan_validity": "string",  # null unless PLAN_VALIDITY × reuse_direct
    "band_struct": "string",
    "band_rank": "string",
    # Audit columns (240 audit pairs only; null elsewhere per §4.1)
    "audit_seed_2_obj": "Float64",
    "audit_seed_3_obj": "Float64",
    "audit_seed_2_assignment": "string",
    "audit_seed_3_assignment": "string",
    "audit_seed_2_top3": "string",
    "audit_seed_3_top3": "string",
    "reference_obj_unstable": "boolean",
    "reference_struct_unstable": "boolean",
    "reference_rank_unstable": "boolean",
}

#: Columns whose values must never be NaN/null on any row.
_REQUIRED_NON_NULL: tuple[str, ...] = (
    "instance_id",
    "perturbation_family",
    "perturbation_id",
    "perturbation_magnitude",
    "claim_family",
    "action",
    "action_feasible",
    "action_n_overload",
    "action_max_overload",
    "action_runtime_s",
    "action_assignment",
    "action_route_costs",
    "reference_objective",
    "reference_feasible",
    "reference_assignment",
    "reference_route_costs",
    "reference_runtime_s",
    "baseline_solution_feasible_under_perturbation",
    "band_obj",
    "band_struct",
    "band_rank",
)

#: Per §9, every cell-action carries loss_obj/loss_struct/loss_rank
#: (claim-family-independent values). loss_X must be non-NaN on cells
#: tagged with claim_family X.
_REQUIRED_PER_CLAIM: dict[str, str] = {
    "OBJ": "loss_obj",
    "STRUCT": "loss_struct",
    "RANK": "loss_rank",
}


# ---------------------------------------------------------------------------
# Result types


@dataclass(frozen=True)
class ConsolidationFailure:
    """A sanity-check violation. Aborts the parquet write."""

    code: str  # e.g., "missing_base_actions", "schema_mismatch", "required_null"
    detail: str


@dataclass(frozen=True)
class ConsolidationSummary:
    n_groups: int  # number of unique (instance, perturbation) groups loaded
    n_rows: int  # rows actually written (0 if write was aborted)
    n_skipped: int  # checkpoints that didn't make it into a complete group
    schema_ok: bool
    failures: tuple[ConsolidationFailure, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """True iff the parquet was written cleanly. A 0-row parquet under
        ``allow_empty=True`` counts as ok — schema is intact, no failures."""
        return self.schema_ok and not self.failures

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        head = (
            f"ConsolidationSummary: {self.n_rows} rows from {self.n_groups} groups, "
            f"schema_ok={self.schema_ok}, failures={len(self.failures)}"
        )
        if not self.failures:
            return head
        tail = "\n".join(f"  - {f.code}: {f.detail}" for f in self.failures)
        return f"{head}\n{tail}"


# ---------------------------------------------------------------------------
# Public entrypoint


def consolidate_to_parquet(
    checkpoint_dir: Path,
    output_path: Path,
    *,
    allow_empty: bool = False,
) -> ConsolidationSummary:
    """Build the Stage A parquet table from per-action checkpoints.

    See module docstring for the pipeline.

    Returns the :class:`ConsolidationSummary`. If sanity checks fail, the
    parquet is *not* written (partial files are worse than none) and
    ``schema_ok`` will be False or ``failures`` non-empty.

    ``allow_empty``: when True, an empty checkpoint dir produces a 0-row
    parquet with the locked schema. Otherwise (default) it produces an
    ``EMPTY_CHECKPOINTS`` failure and no file is written. The CLI exposes
    this via ``--allow-empty`` for the rare legitimate case.
    """
    # Step 1: load every successful checkpoint.
    results: dict[ActionRunKey, ActionResult] = {}
    for path in iter_completed_paths(checkpoint_dir):
        try:
            key = _parse_basename(path.name)
        except ValueError:
            log.warning("skipping unparseable checkpoint: %s", path.name)
            continue
        results[key] = load_result(checkpoint_dir, key)

    # Empty checkpoint dir: soft failure unless explicitly allowed.
    if not results:
        if not allow_empty:
            log.error("no completed checkpoints in %s", checkpoint_dir)
            return ConsolidationSummary(
                n_groups=0,
                n_rows=0,
                n_skipped=0,
                schema_ok=False,
                failures=(
                    ConsolidationFailure(
                        code="EMPTY_CHECKPOINTS",
                        detail=f"No completed checkpoints found in {checkpoint_dir}",
                    ),
                ),
            )
        # allow_empty: write a 0-row schema-conformant parquet.
        df = pd.DataFrame(columns=list(SCHEMA.keys())).astype(SCHEMA)
        _atomic_write_parquet(df, output_path)
        log.info("wrote empty (0-row) parquet to %s (allow_empty=True)", output_path)
        return ConsolidationSummary(
            n_groups=0, n_rows=0, n_skipped=0, schema_ok=True, failures=(),
        )

    # Step 2: group by (instance, perturbation).
    groups: dict[tuple[str, str], dict[str, ActionResult]] = defaultdict(dict)
    for key, result in results.items():
        groups[(key.instance_id, key.perturbation_id)][key.action] = result

    # Step 3: sanity checks before any row construction.
    failures = list(_check_groups(groups))
    if failures:
        for f in failures:
            log.error("consolidation failure: %s — %s", f.code, f.detail)
        return ConsolidationSummary(
            n_groups=len(groups),
            n_rows=0,
            n_skipped=len(results),
            schema_ok=False,
            failures=tuple(failures),
        )

    # Step 4: build rows.
    audit_pairs = set(select_audit_subset())
    rows = list(_build_rows(groups, audit_pairs))

    # Step 5: typed DataFrame + schema validation.
    try:
        df = pd.DataFrame(rows, columns=list(SCHEMA.keys())).astype(SCHEMA)
    except (TypeError, ValueError) as exc:
        return ConsolidationSummary(
            n_groups=len(groups),
            n_rows=0,
            n_skipped=0,
            schema_ok=False,
            failures=(
                ConsolidationFailure(
                    code="dtype_cast_error",
                    detail=f"failed to cast DataFrame to schema: {exc}",
                ),
            ),
        )

    schema_failures = list(_validate_schema(df))
    if schema_failures:
        for f in schema_failures:
            log.error("schema failure: %s — %s", f.code, f.detail)
        return ConsolidationSummary(
            n_groups=len(groups),
            n_rows=0,
            n_skipped=0,
            schema_ok=False,
            failures=tuple(schema_failures),
        )

    # Step 6: atomic parquet write.
    _atomic_write_parquet(df, output_path)
    log.info("wrote %d rows to %s", len(df), output_path)
    return ConsolidationSummary(
        n_groups=len(groups),
        n_rows=len(df),
        n_skipped=0,
        schema_ok=True,
        failures=(),
    )


# ---------------------------------------------------------------------------
# Step 3: sanity checks on the grouped checkpoints


def _check_groups(
    groups: dict[tuple[str, str], dict[str, ActionResult]],
) -> list[ConsolidationFailure]:
    """Per-group integrity checks before any row construction."""
    failures: list[ConsolidationFailure] = []
    audit_pairs = set(select_audit_subset())

    for pair, by_action in sorted(groups.items()):
        missing_base = set(BASE_ACTIONS) - set(by_action)
        if missing_base:
            failures.append(
                ConsolidationFailure(
                    code="missing_base_actions",
                    detail=f"{pair}: missing {sorted(missing_base)}",
                )
            )
        if pair in audit_pairs:
            missing_audit = set(AUDIT_ACTIONS) - set(by_action)
            if missing_audit:
                failures.append(
                    ConsolidationFailure(
                        code="missing_audit_actions",
                        detail=f"{pair}: missing {sorted(missing_audit)}",
                    )
                )
        else:
            stray_audit = set(AUDIT_ACTIONS) & set(by_action)
            if stray_audit:
                # Not a fatal error — just log; consolidation proceeds.
                log.warning(
                    "audit results present for non-audit pair %s: %s",
                    pair,
                    sorted(stray_audit),
                )
    return failures


# ---------------------------------------------------------------------------
# Step 4: row construction


def _build_rows(
    groups: dict[tuple[str, str], dict[str, ActionResult]],
    audit_pairs: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Emit one row per (instance, perturbation, claim_family, action).

    For 75 instances × 16 perts × 4 claim families × 5 base actions =
    24,000 rows on a full Stage A run.
    """
    rows: list[dict[str, Any]] = []
    # The ranking loss requires the baseline solution's per-customer cost
    # contributions; load once per instance and reuse across all 64 rows
    # (16 perturbations × 4 claim families) generated for that instance.
    # ``load_baseline_solution`` is itself ``functools.lru_cache``'d, so even
    # repeated calls inside this loop are O(1) after the first hit.
    baselines: dict[str, Solution] = {}
    for (instance_id, perturbation_id), by_action in sorted(groups.items()):
        if instance_id not in baselines:
            baselines[instance_id] = load_baseline_solution(instance_id)
        baseline = baselines[instance_id]

        spec = lookup_perturbation(instance_id, perturbation_id)
        reference = by_action["pyvrp_60s"]
        seed2 = by_action.get("pyvrp_60s_seed2")
        seed3 = by_action.get("pyvrp_60s_seed3")

        if (instance_id, perturbation_id) in audit_pairs:
            audit = compute_audit_fields(reference, seed2, seed3, baseline)
        else:
            audit = null_audit_fields()

        # Reuse_direct's feasibility under the perturbation IS the
        # baseline-solution-feasibility ground truth (§9.2 / §3.3).
        baseline_feasible = by_action["reuse_direct"].feasible

        for claim_family in CLAIM_FAMILIES:
            for action_name in BASE_ACTIONS:
                action_result = by_action[action_name]
                losses = compute_losses_and_bands(
                    action_result, reference, claim_family, baseline
                )
                rows.append(
                    _row_dict(
                        instance_id=instance_id,
                        perturbation_id=perturbation_id,
                        spec_family=spec.family,
                        magnitude=spec.magnitude,
                        claim_family=claim_family,
                        action_result=action_result,
                        reference=reference,
                        baseline_feasible=baseline_feasible,
                        losses=losses,
                        audit=audit,
                    )
                )
    return rows


def _row_dict(
    *,
    instance_id: str,
    perturbation_id: str,
    spec_family: str,
    magnitude: float,
    claim_family: str,
    action_result: ActionResult,
    reference: ActionResult,
    baseline_feasible: bool,
    losses: Any,
    audit: AuditFields,
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "perturbation_family": spec_family,
        "perturbation_id": perturbation_id,
        "perturbation_magnitude": magnitude,
        "claim_family": claim_family,
        "action": action_result.action,
        "action_objective": action_result.objective,
        "action_feasible": action_result.feasible,
        "action_n_overload": action_result.n_overload,
        "action_max_overload": action_result.max_overload_fraction,
        "action_runtime_s": action_result.runtime_seconds,
        "action_assignment": json.dumps(
            {str(k): v for k, v in action_result.assignment.items()},
            sort_keys=True,
        ),
        "action_route_costs": json.dumps(
            {str(k): v for k, v in action_result.route_costs.items()},
            sort_keys=True,
        ),
        "reference_objective": reference.objective,
        "reference_feasible": reference.feasible,
        "reference_assignment": json.dumps(
            {str(k): v for k, v in reference.assignment.items()},
            sort_keys=True,
        ),
        "reference_route_costs": json.dumps(
            {str(k): v for k, v in reference.route_costs.items()},
            sort_keys=True,
        ),
        "reference_runtime_s": reference.runtime_seconds,
        "baseline_solution_feasible_under_perturbation": baseline_feasible,
        "loss_obj": losses.loss_obj,
        "loss_plan_validity": losses.loss_plan_validity,
        "loss_struct": losses.loss_struct,
        "loss_rank": losses.loss_rank,
        "band_obj": losses.band_obj,
        "band_plan_validity": losses.band_plan_validity,
        "band_struct": losses.band_struct,
        "band_rank": losses.band_rank,
        "audit_seed_2_obj": audit.seed_2_obj,
        "audit_seed_3_obj": audit.seed_3_obj,
        "audit_seed_2_assignment": audit.seed_2_assignment,
        "audit_seed_3_assignment": audit.seed_3_assignment,
        "audit_seed_2_top3": audit.seed_2_top3,
        "audit_seed_3_top3": audit.seed_3_top3,
        "reference_obj_unstable": audit.obj_unstable,
        "reference_struct_unstable": audit.struct_unstable,
        "reference_rank_unstable": audit.rank_unstable,
    }


# ---------------------------------------------------------------------------
# Step 5: schema validation


def _validate_schema(df: pd.DataFrame) -> list[ConsolidationFailure]:
    """Compare ``df`` to :data:`SCHEMA` (column set, dtypes, null constraints)."""
    failures: list[ConsolidationFailure] = []

    # Column set + order.
    if list(df.columns) != list(SCHEMA.keys()):
        missing = set(SCHEMA) - set(df.columns)
        extra = set(df.columns) - set(SCHEMA)
        failures.append(
            ConsolidationFailure(
                code="column_mismatch",
                detail=(
                    f"missing={sorted(missing)} extra={sorted(extra)} "
                    f"order_ok={list(df.columns) == list(SCHEMA.keys())}"
                ),
            )
        )
        # Don't bother with dtype/null checks if columns are off.
        return failures

    # Dtypes match.
    for col, expected in SCHEMA.items():
        actual = str(df[col].dtype)
        if actual != expected:
            failures.append(
                ConsolidationFailure(
                    code="dtype_mismatch",
                    detail=f"{col}: expected {expected}, got {actual}",
                )
            )

    # Required-non-null columns actually have no NaN/None.
    for col in _REQUIRED_NON_NULL:
        if col in df.columns and df[col].isna().any():
            n_null = int(df[col].isna().sum())
            failures.append(
                ConsolidationFailure(
                    code="required_null",
                    detail=f"{col}: {n_null} null values, not allowed",
                )
            )

    # Per-claim-family loss columns must be non-NaN on rows tagged with that
    # claim family (per §9: loss_obj on OBJ rows, loss_struct on STRUCT
    # rows, loss_rank on RANK rows).
    if "claim_family" in df.columns:
        for claim, loss_col in _REQUIRED_PER_CLAIM.items():
            mask = df["claim_family"] == claim
            if mask.any() and df.loc[mask, loss_col].isna().any():
                n_null = int(df.loc[mask, loss_col].isna().sum())
                failures.append(
                    ConsolidationFailure(
                        code="required_null_per_claim",
                        detail=f"claim_family={claim}: {loss_col} has {n_null} nulls",
                    )
                )

    return failures


# ---------------------------------------------------------------------------
# Step 6: atomic parquet write


def _atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    """Write ``df`` to ``target`` atomically with a stamped schema version.

    Uses pyarrow directly so we can attach ``_schema_version`` to the
    parquet's schema metadata. Future readers can verify the version
    via ``pq.read_metadata(path).schema.metadata`` before loading.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".tmp.",
        dir=str(target.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        table = pa.Table.from_pandas(df, preserve_index=False)
        existing = table.schema.metadata or {}
        new_meta = {
            **existing,
            b"_schema_version": SCHEMA_VERSION.encode(),
        }
        table = table.replace_schema_metadata(new_meta)
        pq.write_table(table, tmp_path)
        os.replace(tmp_path, target)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

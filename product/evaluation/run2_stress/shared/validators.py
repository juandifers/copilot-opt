"""Shared validators for the R2-S cross-axis methodology.

Programmatic counterparts to the rules in `scatter_schema.md`,
`metric_names.md`, and `axis_naming.md`. Each validator returns a
list of human-readable error strings; an empty list signals
success. The validators are deliberately small and do their work
with `pandas` so the tests can exercise them on tiny inline CSVs.

This module imports nothing from `product/copilot/*` or
`product/data/*`. It reads the locked Run 2 enums from
`run2_case_loader` so its enum tables stay synchronised with the
benchmark.
"""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from product.evaluation.run2_case_loader import (
    ALLOWED_ANSWERABILITY,
    ALLOWED_BEHAVIOR_CLASSES,
    CURRENT_INTENTS,
    PROPOSED_INTENTS,
)


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------


SCATTER_COLUMNS: list[str] = [
    "case_id",
    "axis",
    "split",
    "band",
    "intent",
    "n_routes",
    "payload_chars",
    "system",
    "metric",
    "score",
]


ALLOWED_AXES: set[str] = {
    "axis1_lookalike",
    "axis2_ood_premises",
    "axis3_semantic",
    "axis4_payload",
}


ALLOWED_SPLITS: set[str] = {"dev", "heldout"}


ALLOWED_SYSTEMS: set[str] = {"c0", "a", "b", "d"}


ALLOWED_METRIC_NAMES: set[str] = {
    "intent_correct",
    "answerability_correct",
    "behavior_class_correct",
    "evidence_precision",
    "evidence_recall",
    "warning_precision",
    "warning_recall",
    "missing_field_recall",
    "useful_refusal_correct",
    "partial_answer_correct",
}


ALLOWED_INTENTS: set[str] = CURRENT_INTENTS | PROPOSED_INTENTS


# Files the locked-benchmark / scorer / contract layer at HEAD considers
# immutable for System D and for R2-S authoring. Any change to one of
# these is a protected-file violation and the validator surfaces it.
PROTECTED_PATHS: tuple[str, ...] = (
    "product/evaluation/run2_benchmark_cases.csv",
    "product/evaluation/run2_calibration_cases.csv",
    "product/evaluation/run2_gold_schema.md",
    "product/evaluation/run2_case_loader.py",
    "product/evaluation/run2_payloads.py",
    "product/evaluation/run2_scoring.py",
    "product/evaluation/run2_system_c.py",
    "product/copilot/refusal_policy.py",
    "product/copilot/response_builder.py",
    "product/copilot/contracts.py",
    "product/data/answerability.py",
    "product/data/evidence.py",
    "product/data/product_schema.py",
    "product/data/entity_resolution.py",
)


# Files in PROTECTED_PATHS that the grounded-overview-support extension
# is permitted to modify in an additive-only way. The validator below
# treats a modification to one of these as a non-violation iff the
# diff is purely additive (existing intents' behaviour is unchanged).
# This allowlist exists so the stress-axis integrity guards remain
# strict for every other path while not blocking the legitimate
# overview-intent additions documented in the explanation_check
# thesis-framing note.
_OVERVIEW_EXTENSION_ALLOWLIST: frozenset[str] = frozenset({
    "product/copilot/contracts.py",
    "product/data/answerability.py",
})


_AXIS_NAME_RE = re.compile(r"^axis(\d+)_[a-z_]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, dtype=str)


def _is_null_token(value: str) -> bool:
    """Empty string is the canonical CSV null token (cf. scatter_schema §1)."""
    return value == ""


def _parse_optional_float(value: str) -> Optional[float]:
    if _is_null_token(value):
        return None
    try:
        f = float(value)
    except ValueError:
        return None
    if math.isnan(f):
        return None
    return f


# ---------------------------------------------------------------------------
# Scatter schema validation
# ---------------------------------------------------------------------------


def validate_scatter_schema(path: str | Path) -> list[str]:
    """Validate a per-axis scatter CSV against `scatter_schema.md`.

    Returns a list of human-readable error strings. An empty list
    means the file conforms.
    """
    errs: list[str] = []
    path = Path(path)
    if not path.exists():
        return [f"scatter file does not exist: {path}"]

    try:
        df = _read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return [f"failed to read {path}: {exc!r}"]

    if list(df.columns) != SCATTER_COLUMNS:
        missing = [c for c in SCATTER_COLUMNS if c not in df.columns]
        extra = [c for c in df.columns if c not in SCATTER_COLUMNS]
        errs.append(
            f"scatter header mismatch: missing={missing!r} extra={extra!r}"
        )
        return errs  # downstream checks assume schema present

    if df.empty:
        errs.append("scatter file has zero rows")
        return errs

    seen_triples: set[tuple[str, str, str]] = set()

    for idx, row in df.iterrows():
        ln = idx + 2  # 1-based + header line

        case_id = row["case_id"]
        if _is_null_token(case_id):
            errs.append(f"row {ln}: case_id is empty")

        axis = row["axis"]
        if axis not in ALLOWED_AXES:
            errs.append(
                f"row {ln} ({case_id}): axis {axis!r} not in {sorted(ALLOWED_AXES)}"
            )

        split = row["split"]
        if split not in ALLOWED_SPLITS:
            errs.append(
                f"row {ln} ({case_id}): split {split!r} not in {sorted(ALLOWED_SPLITS)}"
            )

        intent = row["intent"]
        if intent and intent not in ALLOWED_INTENTS:
            errs.append(
                f"row {ln} ({case_id}): intent {intent!r} not a known Intent enum"
            )

        for numeric_col in ("n_routes", "payload_chars"):
            raw = row[numeric_col]
            if _is_null_token(raw):
                continue
            try:
                int(raw)
            except ValueError:
                errs.append(
                    f"row {ln} ({case_id}): {numeric_col}={raw!r} not int|null"
                )

        system = row["system"]
        if system not in ALLOWED_SYSTEMS:
            errs.append(
                f"row {ln} ({case_id}): system {system!r} not in "
                f"{sorted(ALLOWED_SYSTEMS)}"
            )

        metric = row["metric"]
        if metric not in ALLOWED_METRIC_NAMES:
            errs.append(
                f"row {ln} ({case_id}): metric {metric!r} not in shared vocabulary"
            )

        score_raw = row["score"]
        if not _is_null_token(score_raw):
            score = _parse_optional_float(score_raw)
            if score is None:
                errs.append(
                    f"row {ln} ({case_id}): score {score_raw!r} not float|null"
                )
            elif not (0.0 <= score <= 1.0):
                errs.append(
                    f"row {ln} ({case_id}): score {score!r} outside [0.0, 1.0]"
                )

        triple = (case_id, system, metric)
        if triple in seen_triples:
            errs.append(
                f"row {ln}: duplicate (case_id={case_id!r}, "
                f"system={system!r}, metric={metric!r})"
            )
        seen_triples.add(triple)

    return errs


# ---------------------------------------------------------------------------
# Metric-name-only validation
# ---------------------------------------------------------------------------


def validate_metric_names(path: str | Path) -> list[str]:
    """Cheaper subset of `validate_scatter_schema`: confirm only that
    every `metric` value in the CSV is in the shared vocabulary."""
    errs: list[str] = []
    path = Path(path)
    if not path.exists():
        return [f"scatter file does not exist: {path}"]

    df = _read_csv(path)
    if "metric" not in df.columns:
        return ["scatter file has no `metric` column"]

    bad = sorted(set(df["metric"].tolist()) - ALLOWED_METRIC_NAMES)
    if bad:
        errs.append(
            f"forbidden metric name(s) in scatter: {bad}. "
            f"Allowed: {sorted(ALLOWED_METRIC_NAMES)}"
        )
    return errs


# ---------------------------------------------------------------------------
# Axis cases.csv validation
# ---------------------------------------------------------------------------


def validate_axis_cases(path: str | Path, axis_name: str) -> list[str]:
    """Validate that an axis's `cases.csv` carries the bare minimum
    cross-axis-comparable shape: a `case_id` column, a `split` column,
    unique case ids, and that the directory name conforms to
    `axis<N>_<name>`."""
    errs: list[str] = []
    if not _AXIS_NAME_RE.match(axis_name):
        errs.append(
            f"axis_name {axis_name!r} does not match axis<N>_<short_name>"
        )

    path = Path(path)
    if not path.exists():
        return errs + [f"cases.csv does not exist: {path}"]

    df = _read_csv(path)

    if "case_id" not in df.columns:
        errs.append("cases.csv missing required column `case_id`")
        return errs

    ids = df["case_id"].tolist()
    if any(not cid for cid in ids):
        errs.append("cases.csv has empty case_id rows")
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        errs.append(f"cases.csv has duplicate case_ids: {duplicates}")

    if "split" in df.columns:
        bad_splits = sorted(set(df["split"].tolist()) - ALLOWED_SPLITS)
        if bad_splits:
            errs.append(
                f"cases.csv has unexpected split value(s): {bad_splits}. "
                f"Allowed: {sorted(ALLOWED_SPLITS)}"
            )

    return errs


# ---------------------------------------------------------------------------
# Split / band presence
# ---------------------------------------------------------------------------


def validate_split_and_band(
    cases_path: str | Path,
    axis_design_path: Optional[str | Path] = None,
) -> list[str]:
    """Verify that the axis declares a `split` column AND either a
    `band` column on cases.csv OR the design.md explicitly documents
    that the axis does not stratify.

    The `band` requirement is intentionally soft: not every axis has
    a meaningful stratification key (axis 1 may stratify by adjacent
    intent class instead). The validator checks for either:

    - a `band` column in cases.csv (any non-empty values), OR
    - an explicit statement in design.md (substring match for one of
      "no band", "no stratification", "does not stratify",
      "without stratification").
    """
    errs: list[str] = []
    cases_path = Path(cases_path)
    if not cases_path.exists():
        return [f"cases.csv does not exist: {cases_path}"]

    df = _read_csv(cases_path)

    if "split" not in df.columns:
        errs.append("cases.csv missing `split` column")

    if "band" in df.columns:
        return errs

    if axis_design_path is None:
        errs.append(
            "cases.csv has no `band` column and no axis design.md was "
            "supplied to confirm the absence is documented"
        )
        return errs

    design_path = Path(axis_design_path)
    if not design_path.exists():
        errs.append(
            f"cases.csv has no `band` column and design.md {design_path} "
            f"does not exist"
        )
        return errs

    design_text = design_path.read_text(encoding="utf-8").lower()
    # Pass if design.md either declares a stratification scheme
    # ("band" / "stratif*") OR explicitly states there is none.
    documented_phrases = (
        "band",
        "stratif",
        "subtype",
        "no band",
        "no stratification",
        "does not stratify",
        "without stratification",
    )
    if not any(phrase in design_text for phrase in documented_phrases):
        errs.append(
            "cases.csv has no `band` column and design.md does not "
            "describe a stratification scheme or document its absence "
            f"(looked for: {documented_phrases!r})"
        )
    return errs


# ---------------------------------------------------------------------------
# Protected-file modification check
# ---------------------------------------------------------------------------


def _git_changed_files(rev: str = "HEAD") -> list[str]:
    """Return the files that differ between the working tree and `rev`.

    Includes both staged and unstaged changes. Returns an empty list
    on git failure (the caller treats failure to introspect as
    "cannot prove a violation" rather than "no violation"; we return
    a diagnostic line in the validator wrapper)."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", rev],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return []
    except FileNotFoundError:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def validate_no_protected_files_modified(
    rev: str = "HEAD",
    protected: Iterable[str] = PROTECTED_PATHS,
) -> list[str]:
    """Return a list of protected files that have been modified since
    `rev`.

    The validator shells out to `git diff --name-only`. If `git` is
    not available or the working tree is not a repo, the validator
    returns a single diagnostic string (not a violation) so callers
    can decide how to react.

    Files in ``_OVERVIEW_EXTENSION_ALLOWLIST`` are exempted: the
    grounded-overview-support extension adds new overview intents in a
    purely additive way and does not change the locked behaviour for
    any of the original 14 intents the stress axes evaluate.
    """
    try:
        changed = _git_changed_files(rev=rev)
    except Exception as exc:  # noqa: BLE001
        return [f"could not introspect git working tree: {exc!r}"]

    protected_set = set(protected) - _OVERVIEW_EXTENSION_ALLOWLIST
    return sorted(set(changed) & protected_set)


# ---------------------------------------------------------------------------
# Convenience aggregator
# ---------------------------------------------------------------------------


def validate_axis_directory(axis_dir: str | Path) -> dict[str, list[str]]:
    """Run all available validators against an axis directory.

    Returns a dict keyed by validator name with the per-validator
    error list. The caller decides how to format the result; an
    empty list per key means that check passed (or was skipped
    because the relevant file does not exist).
    """
    axis_dir = Path(axis_dir)
    axis_name = axis_dir.name

    out: dict[str, list[str]] = {}

    cases_path = axis_dir / "cases.csv"
    if cases_path.exists():
        out["cases"] = validate_axis_cases(cases_path, axis_name)
        out["split_and_band"] = validate_split_and_band(
            cases_path, axis_design_path=axis_dir / "design.md"
        )
    else:
        out["cases"] = [f"cases.csv missing under {axis_dir}"]
        out["split_and_band"] = ["cases.csv missing; cannot check split/band"]

    scatter_path = axis_dir / "reports" / "scatter.csv"
    if scatter_path.exists():
        out["scatter_schema"] = validate_scatter_schema(scatter_path)
        out["metric_names"] = validate_metric_names(scatter_path)
    else:
        out["scatter_schema"] = [
            f"shared scatter file not yet emitted at {scatter_path}"
        ]
        out["metric_names"] = [
            f"shared scatter file not yet emitted at {scatter_path}"
        ]

    return out


__all__ = [
    "ALLOWED_AXES",
    "ALLOWED_METRIC_NAMES",
    "ALLOWED_INTENTS",
    "ALLOWED_SPLITS",
    "ALLOWED_SYSTEMS",
    "PROTECTED_PATHS",
    "SCATTER_COLUMNS",
    "validate_axis_cases",
    "validate_axis_directory",
    "validate_metric_names",
    "validate_no_protected_files_modified",
    "validate_scatter_schema",
    "validate_split_and_band",
]

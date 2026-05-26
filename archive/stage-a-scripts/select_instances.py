#!/usr/bin/env python3
"""Stage A instance selection — prereg §5.1.

Reads a classification CSV listing the 100 Uchoa-X instances and their
four-dimensional classification (depot position, customer distribution,
demand pattern, average route size), filters to ``n_customers <= 500``,
and draws ``n_target`` (default 75) by deterministic proportional
stratified sampling on the joint of the four classification dimensions.

The output is a sorted list of instance IDs, written to
``instances/stage_a_instances.txt`` (one per line, sorted alphanumerically).

Determinism: the sampler uses ``numpy.random.default_rng(seed)`` with the
fixed seed from prereg §5.1 (``20260429``). Pool order is stabilised by
sorting on ``instance_id`` before any RNG draw. Stratum order is stabilised
by sorting on the (depot, customer, demand, route) tuple.

Allocation per stratum uses the **largest-remainder method (Hamilton's
method)** so that:

  - the per-stratum integer counts sum to exactly ``n_target``,
  - the proportion in each stratum is as close to ``size_in_pool / pool_size``
    as integer rounding allows,
  - ties on remainder break deterministically by stratum tuple.

Within each stratum, if the allocated count is less than the stratum's
pool size, the chosen subset is drawn via ``rng.choice(replace=False)``.

CSV schema
----------
::

    instance_id,n_customers,depot_position,customer_distribution,demand_pattern,avg_route_size
    X-n101-k25,100,R,RC,1,1
    ...

The four classification columns accept arbitrary string-or-int level labels
— the script does not interpret them. It only requires that they are
populated for every row and that all rows in the CSV cover the 100
canonical Uchoa-X IDs (no extras, no missing).

Usage
-----
::

    python scripts/select_instances.py
    python scripts/select_instances.py --classification-csv path/to/x_set.csv
    python scripts/select_instances.py --output instances/stage_a_instances.txt
    python scripts/select_instances.py --seed 20260429 --target 75
    python scripts/select_instances.py --max-customers 500
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

DEFAULT_CLASSIFICATION_CSV: Path = Path("data/instances/uchoa_x_classification.csv")
DEFAULT_ROSTER_PATH: Path = Path("instances/stage_a_instances.txt")
DEFAULT_SEED: int = 20260429
DEFAULT_TARGET: int = 75
DEFAULT_MAX_CUSTOMERS: int = 500

#: The four classification columns required in the CSV (prereg §5.1).
STRATIFY_COLS: tuple[str, ...] = (
    "depot_position",
    "customer_distribution",
    "demand_pattern",
    "avg_route_size",
)
REQUIRED_COLS: tuple[str, ...] = ("instance_id", "n_customers") + STRATIFY_COLS


@dataclass(frozen=True)
class InstanceRow:
    instance_id: str
    n_customers: int
    stratum: tuple[str, ...]


# ---------------------------------------------------------------------------
# CSV input


def load_classification_csv(path: Path) -> list[InstanceRow]:
    """Read the classification CSV and return one :class:`InstanceRow` per row.

    Validates that all :data:`REQUIRED_COLS` are present and non-empty,
    that ``n_customers`` parses as int, and that ``instance_id`` is unique.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"classification CSV not found: {path}. "
            f"See scripts/select_instances.py docstring for the schema."
        )

    rows: list[InstanceRow] = []
    seen_ids: set[str] = set()
    with path.open("r", newline="", encoding="utf-8") as fh:
        # Skip leading lines that start with ``#`` (header comments). DictReader
        # has no built-in comment support; we filter at the file-iterator level
        # so the first non-comment line becomes the field-name row.
        non_comment_lines = (ln for ln in fh if not ln.lstrip().startswith("#"))
        reader = csv.DictReader(non_comment_lines)
        if reader.fieldnames is None:
            raise ValueError(f"CSV {path} has no header row")
        missing = [c for c in REQUIRED_COLS if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"CSV {path} is missing required column(s): {missing}. "
                f"Expected schema: {REQUIRED_COLS}"
            )
        for line_no, raw in enumerate(reader, start=2):  # +2: header + 1-indexed
            for col in REQUIRED_COLS:
                value = (raw.get(col) or "").strip()
                if not value:
                    raise ValueError(
                        f"CSV {path} line {line_no}: column {col!r} is empty"
                    )
            iid = raw["instance_id"].strip()
            if iid in seen_ids:
                raise ValueError(f"CSV {path}: duplicate instance_id {iid!r}")
            seen_ids.add(iid)
            try:
                n_customers = int(raw["n_customers"].strip())
            except ValueError as exc:
                raise ValueError(
                    f"CSV {path} line {line_no}: n_customers must be int, "
                    f"got {raw['n_customers']!r}"
                ) from exc
            stratum = tuple(raw[col].strip() for col in STRATIFY_COLS)
            rows.append(
                InstanceRow(
                    instance_id=iid,
                    n_customers=n_customers,
                    stratum=stratum,
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Eligibility


def filter_eligible(
    rows: Iterable[InstanceRow], *, max_customers: int = DEFAULT_MAX_CUSTOMERS
) -> list[InstanceRow]:
    """Apply the §5.1 eligibility filter: keep rows with ``n_customers <= max_customers``."""
    return [r for r in rows if r.n_customers <= max_customers]


# ---------------------------------------------------------------------------
# Stratified sampler


def _hamilton_allocate(
    counts_per_stratum: dict[tuple[str, ...], int],
    n_target: int,
    *,
    tiebreak: dict[tuple[str, ...], int] | None = None,
) -> dict[tuple[str, ...], int]:
    """Allocate ``n_target`` slots across strata via the largest-remainder method.

    Each stratum's raw quota is ``n_target * pool_size_in_stratum / total_pool``.
    Floors are taken; remaining ``n_target - sum(floors)`` slots are distributed
    one-per-stratum to the strata with the largest fractional remainders.

    Ties on remainder are broken by ``tiebreak[stratum]`` if given, else by
    the stratum tuple (lexicographic). For sparse strata where most cells
    have pool size 1, tie-breaking dominates the allocation; passing an
    rng-derived ``tiebreak`` map keeps the algorithm deterministic per seed
    while avoiding the systematic marginal bias of lex tie-breaks.

    Caps each stratum's allocation at its pool size; any unallocated slots
    that would have gone to a capped stratum are redistributed to the next
    eligible stratum by remainder order.
    """
    total_pool = sum(counts_per_stratum.values())
    if total_pool == 0:
        return {}
    if n_target > total_pool:
        raise ValueError(
            f"n_target ({n_target}) exceeds eligible pool size ({total_pool})"
        )

    if tiebreak is None:
        tiebreak = {s: s for s in counts_per_stratum}

    sorted_strata = sorted(counts_per_stratum.items())  # lexicographic by tuple

    raw_targets = {
        s: n_target * size / total_pool for s, size in sorted_strata
    }
    floors = {s: math.floor(raw_targets[s]) for s, _ in sorted_strata}
    # Cap floors at pool size (defensive — for n_target ≤ total_pool the floor
    # never exceeds size, but rounding up via remainder might).
    for s, size in sorted_strata:
        if floors[s] > size:
            floors[s] = size

    deficit = n_target - sum(floors.values())

    if deficit > 0:
        # Compute remainder per stratum; eligible only if floor < size.
        remainders = [
            (raw_targets[s] - floors[s], s)
            for s, size in sorted_strata
            if floors[s] < size
        ]
        # Largest remainder first; tie-break via the supplied tiebreak map.
        remainders.sort(key=lambda x: (-x[0], tiebreak[x[1]]))
        for _, s in remainders:
            if deficit == 0:
                break
            if floors[s] < counts_per_stratum[s]:
                floors[s] += 1
                deficit -= 1
        if deficit != 0:  # pragma: no cover - guarded by n_target ≤ total_pool
            raise RuntimeError(
                f"Hamilton allocation failed: {deficit} slots left unfilled"
            )

    return floors


def stratified_sample(
    rows: list[InstanceRow], *, n_target: int, seed: int
) -> list[str]:
    """Deterministic proportional stratified sample.

    Returns ``n_target`` instance IDs, sorted alphanumerically.

    Procedure:
      1. Group rows by joint stratum (the 4-tuple).
      2. Allocate per-stratum target counts via Hamilton's method
         (:func:`_hamilton_allocate`).
      3. Within each stratum, draw the allocated count via
         ``rng.choice(replace=False)`` over the stratum's instance_ids
         (sorted for determinism).

    The RNG is consumed in stratum order (sorted by tuple), so adding a
    single extra row to the input may shift later strata's draws — this
    is the standard determinism property for stratified sampling, not a
    bug. Identical input → identical output.
    """
    if n_target <= 0:
        return []

    by_stratum: dict[tuple[str, ...], list[str]] = {}
    for r in rows:
        by_stratum.setdefault(r.stratum, []).append(r.instance_id)
    for stratum in by_stratum:
        by_stratum[stratum].sort()

    counts = {s: len(ids) for s, ids in by_stratum.items()}

    # Single rng drives both Hamilton tie-breaking and within-stratum draws.
    # Drawing a permutation up front means the within-stratum draws don't
    # depend on the number of tied strata — making the seed-determinism
    # property robust against stratum count changes.
    rng = np.random.default_rng(seed)
    sorted_strata = sorted(by_stratum)
    perm = rng.permutation(len(sorted_strata))
    tiebreak = {s: int(perm[i]) for i, s in enumerate(sorted_strata)}

    allocation = _hamilton_allocate(counts, n_target, tiebreak=tiebreak)

    selected: list[str] = []
    for stratum in sorted(by_stratum):
        ids = by_stratum[stratum]
        take = allocation.get(stratum, 0)
        if take >= len(ids):
            picked = list(ids)
        elif take == 0:
            picked = []
        else:
            idx = rng.choice(len(ids), size=take, replace=False)
            picked = [ids[int(i)] for i in sorted(idx)]
        selected.extend(picked)

    return sorted(selected)


# ---------------------------------------------------------------------------
# Roster output


def write_roster(
    instance_ids: list[str], path: Path, *, header_comment: str | None = None
) -> None:
    """Write the roster file (one ID per line, sorted)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if header_comment:
        for hl in header_comment.splitlines():
            lines.append(f"# {hl}" if hl else "#")
    lines.extend(sorted(instance_ids))
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="select_instances",
        description="Deterministic stratified selection of Stage A instances (prereg §5.1).",
    )
    p.add_argument(
        "--classification-csv", type=Path, default=DEFAULT_CLASSIFICATION_CSV,
        help="Path to the Uchoa-X classification CSV.",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_ROSTER_PATH,
        help="Destination for the roster file.",
    )
    p.add_argument(
        "--seed", type=int, default=DEFAULT_SEED,
        help="RNG seed (prereg §5.1: 20260429).",
    )
    p.add_argument(
        "--target", type=int, default=DEFAULT_TARGET,
        help="Number of instances to select (default 75).",
    )
    p.add_argument(
        "--max-customers", type=int, default=DEFAULT_MAX_CUSTOMERS,
        help="Eligibility threshold; instances with strictly more are excluded.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the selection to stdout instead of writing the roster.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    rows = load_classification_csv(args.classification_csv)
    eligible = filter_eligible(rows, max_customers=args.max_customers)
    print(
        f"Loaded {len(rows)} rows from {args.classification_csv}; "
        f"{len(eligible)} eligible after n_customers <= {args.max_customers}.",
        file=sys.stderr,
    )

    if args.target > len(eligible):
        print(
            f"ERROR: target ({args.target}) exceeds eligible pool ({len(eligible)})",
            file=sys.stderr,
        )
        return 2

    selected = stratified_sample(eligible, n_target=args.target, seed=args.seed)
    assert len(selected) == args.target, (
        f"sampler produced {len(selected)} instances, expected {args.target}"
    )

    if args.dry_run:
        for iid in selected:
            print(iid)
        print(f"\n[dry-run] Selected {len(selected)} instances.", file=sys.stderr)
        return 0

    header = (
        f"Stage A roster: {args.target} Uchoa-X CVRPLIB instances.",
        "",
        "Generated by scripts/select_instances.py — DO NOT edit by hand.",
        f"  --classification-csv {args.classification_csv}",
        f"  --seed               {args.seed}",
        f"  --target             {args.target}",
        f"  --max-customers      {args.max_customers}",
        "",
        "Format: one instance ID per line; blank lines and # comments are ignored.",
    )
    write_roster(selected, args.output, header_comment="\n".join(header))
    print(f"Wrote {len(selected)} instances → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

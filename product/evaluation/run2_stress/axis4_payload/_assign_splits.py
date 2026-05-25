"""Stratified 60/40 dev/heldout split, seed=1.

Stratified by (band, intent). For each sub-cell of size 4, this script
deterministically assigns 2 dev and 2 heldout when the sub-cell is in the
"balanced" group, and 3 dev / 1 heldout when in the "dev-heavy" group.
The dev-heavy group is the lexicographically-first 2 sub-cells; this
yields 14 dev / 10 heldout = 58.3 / 41.7 (the closest balanced rounding
to 60/40 under the constraint that each sub-cell appears in both splits
with n ≥ 1).

Re-running with the same seed reproduces the exact assignment.
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES_CSV = HERE / "cases.csv"

# (band, intent) → n_heldout
# Lex-first 2 sub-cells get 1 heldout; remaining 4 get 2 heldout.
# Sort key is (band, intent) ascending lexicographically:
#   ('high','customer_arrival')   → dev-heavy (1 heldout)
#   ('high','lateness_summary')   → dev-heavy (1 heldout)
#   ('high','route_end_time')     → balanced  (2 heldout)
#   ('low','customer_arrival')    → balanced  (2 heldout)
#   ('low','lateness_summary')    → balanced  (2 heldout)
#   ('low','route_end_time')      → balanced  (2 heldout)
# Total heldout = 1+1+2+2+2+2 = 10; total dev = 24 - 10 = 14.


def _row_band(row: dict) -> str:
    # Recover band from the rationale prefix
    if "low band" in row["label_rationale"]:
        return "low"
    if "high band" in row["label_rationale"]:
        return "high"
    raise ValueError(f"cannot determine band for {row['case_id']}")


def main() -> None:
    with CASES_CSV.open() as fh:
        rows = list(csv.DictReader(fh))

    # Group by (band, intent)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (_row_band(row), row["expected_intent"])
        groups[key].append(row)

    # Sort sub-cells deterministically, assign heldout counts
    sub_cells = sorted(groups.keys())
    if len(sub_cells) != 6:
        raise RuntimeError(f"expected 6 sub-cells, got {len(sub_cells)}")
    n_heldout_by_subcell = {sc: (1 if i < 2 else 2) for i, sc in enumerate(sub_cells)}

    rng = random.Random(1)
    assignments: dict[str, str] = {}
    for sc in sub_cells:
        cases_in_sc = sorted(groups[sc], key=lambda r: r["case_id"])
        # deterministic shuffle of the 4 cases
        idxs = list(range(len(cases_in_sc)))
        rng.shuffle(idxs)
        n_heldout = n_heldout_by_subcell[sc]
        for j, i in enumerate(idxs):
            assignments[cases_in_sc[i]["case_id"]] = (
                "heldout" if j < n_heldout else "dev"
            )

    # Write back, preserving column order
    cols = list(rows[0].keys())
    for row in rows:
        row["split"] = assignments[row["case_id"]]

    with CASES_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    # Summary
    from collections import Counter
    by_split = Counter(r["split"] for r in rows)
    print(f"split totals: {dict(by_split)}")
    print(f"dev/heldout ratio: {by_split['dev']}/{by_split['heldout']} = "
          f"{by_split['dev']/len(rows):.1%}/{by_split['heldout']/len(rows):.1%}")
    print("per (band, intent) split:")
    for sc in sub_cells:
        in_sc = [r for r in rows if (_row_band(r), r["expected_intent"]) == sc]
        c = Counter(r["split"] for r in in_sc)
        print(f"  {sc}: dev={c['dev']} heldout={c['heldout']}")

    print(f"\nwrote {CASES_CSV}")


if __name__ == "__main__":
    main()

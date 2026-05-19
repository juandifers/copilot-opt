"""Deterministic 20-prompt calibration-pilot selection.

Implements the sampling rule locked at preregistration-v1
(experiment/configs/pilot_protocol.md):

- 5 prompts per family (OBJ, PLAN_VALIDITY, SCHEDULE, STRUCT)
- Per-family quadrant layout:
    1 suff_accept + 1 suff_escal + 2 insuff_accept + 1 insuff_escal
- 16 Solomon + 4 Homberger total (one Homberger per family)
- Seed: random.Random(2026 + 1000); families processed alphabetically;
  candidates sorted by (instance_id, perturbation_id) before sampling.

Constraint detail: not every (family, quadrant) bucket has a Homberger
prompt. Specifically:
  - No family has a Homberger insuff_accept prompt.
  - SCHEDULE has no Homberger suff_accept prompt.
So the Homberger slot must be drawn uniformly from the slot indices
that have a Homberger row available for that family.

Writes experiment/pilot/calibration_selection.csv (all prompts.csv
columns + selection_rationale).
"""
from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROMPTS_PATH = REPO / "experiment" / "data" / "prompts.csv"
OUT_PATH = REPO / "experiment" / "pilot" / "calibration_selection.csv"

SEED = 2026 + 1000  # 3026, per pilot_protocol.md
FAMILIES = ["OBJ", "PLAN_VALIDITY", "SCHEDULE", "STRUCT"]  # alphabetical
SLOT_PATTERN = [
    "suff_accept",
    "suff_escal",
    "insuff_accept",
    "insuff_accept",
    "insuff_escal",
]


def main() -> None:
    rows = list(csv.DictReader(PROMPTS_PATH.open()))
    fields = list(rows[0].keys())
    if len(rows) != 48:
        raise RuntimeError(f"expected 48 prompts, got {len(rows)}")

    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append(r)

    rng = random.Random(SEED)
    selected: list[dict] = []

    for family in FAMILIES:
        family_rows = by_family[family]
        bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in family_rows:
            bucket[(r["quadrant"], r["dataset"])].append(r)
        for key in bucket:
            bucket[key].sort(
                key=lambda r: (r["instance_id"], r["perturbation_id"])
            )

        homberger_quadrants_available = {
            q for (q, ds), v in bucket.items() if ds == "Homberger" and v
        }
        valid_homberger_slots = [
            i for i, q in enumerate(SLOT_PATTERN)
            if q in homberger_quadrants_available
        ]
        if not valid_homberger_slots:
            raise RuntimeError(f"no Homberger slot available for family {family}")
        homberger_slot = rng.choice(valid_homberger_slots)

        for slot_idx, quadrant in enumerate(SLOT_PATTERN):
            dataset = "Homberger" if slot_idx == homberger_slot else "Solomon"
            pool = bucket[(quadrant, dataset)]
            if not pool:
                raise RuntimeError(
                    f"empty pool family={family} quadrant={quadrant} "
                    f"dataset={dataset} slot={slot_idx}"
                )
            pick = rng.choice(pool)
            pool.remove(pick)
            out = dict(pick)
            out["selection_rationale"] = (
                f"family={family}; quadrant={quadrant}; dataset={dataset}; "
                f"slot={slot_idx + 1}/5; source={pick['source']}"
            )
            selected.append(out)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields + ["selection_rationale"])
        writer.writeheader()
        writer.writerows(selected)

    print(f"Wrote {len(selected)} prompts → {OUT_PATH}")
    print()
    print("family count:", dict(Counter(r["family"] for r in selected)))
    print("source count:", dict(Counter(r["source"] for r in selected)))
    print("dataset count:", dict(Counter(r["dataset"] for r in selected)))
    print("quadrant count:", dict(Counter(r["quadrant"] for r in selected)))
    print()
    print("per (family, source):")
    for k, v in sorted(Counter((r["family"], r["source"])
                               for r in selected).items()):
        print(f"  {k}: {v}")
    print()
    print("per (family, quadrant):")
    for k, v in sorted(Counter((r["family"], r["quadrant"])
                               for r in selected).items()):
        print(f"  {k}: {v}")
    print()
    print("prompt_ids (in selection order):")
    print("  " + ",".join(r["prompt_id"] for r in selected))


if __name__ == "__main__":
    main()

"""Verification sample selection — locked at preregistration-v1.

Implements the deterministic 12-prompt verification draw from
experiment/configs/verification_protocol.md. 3 prompts per family,
60/40 weighted toward FP+FN (insuff_accept ∪ suff_escal) vs
TP+TN (suff_accept ∪ insuff_escal). Family order is
['OBJ', 'PLAN_VALIDITY', 'STRUCT', 'SCHEDULE'] per the protocol.

Within each family, prompts are sorted by (instance_id, perturbation_id)
before sampling; the RNG is seeded per family at 2026 + 2000 + family_idx.

Writes:
  experiment/results/verification_set.csv  (locked output path)

This script only does the sampling. Use build_human_sheet.py with the
--prompt-ids filter (or read verification_set.csv → pass the prompt_ids)
to produce the rating sheet.
"""
from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROMPTS_PATH = REPO / "experiment" / "data" / "prompts.csv"
OUT_PATH = REPO / "experiment" / "results" / "verification_set.csv"

SEED_BASE = 2026
SEED_OFFSET = 2000
WEIGHT_FP_FN = 0.6
WEIGHT_TP_TN = 0.4
PER_FAMILY = 3
FAMILY_ORDER = ["OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE"]

FP_FN_QUADRANTS = {"insuff_accept", "suff_escal"}
TP_TN_QUADRANTS = {"suff_accept", "insuff_escal"}


def main() -> None:
    rows = list(csv.DictReader(PROMPTS_PATH.open()))
    if len(rows) != 48:
        raise RuntimeError(f"expected 48 prompts in {PROMPTS_PATH}, got {len(rows)}")

    by_family: dict[str, list[dict]] = {f: [] for f in FAMILY_ORDER}
    for r in rows:
        by_family[r["family"]].append(r)

    verification_set: list[dict] = []
    for family_idx, family in enumerate(FAMILY_ORDER):
        family_prompts = by_family[family]
        pool_fp_fn = [p for p in family_prompts if p["quadrant"] in FP_FN_QUADRANTS]
        pool_tp_tn = [p for p in family_prompts if p["quadrant"] in TP_TN_QUADRANTS]

        target_fp_fn = round(PER_FAMILY * WEIGHT_FP_FN)  # 2
        target_tp_tn = PER_FAMILY - target_fp_fn          # 1

        # Fallback redistribution (per protocol; unused under locked stratification).
        if len(pool_fp_fn) < target_fp_fn:
            deficit = target_fp_fn - len(pool_fp_fn)
            target_fp_fn = len(pool_fp_fn)
            target_tp_tn += deficit
        if len(pool_tp_tn) < target_tp_tn:
            deficit = target_tp_tn - len(pool_tp_tn)
            target_tp_tn = len(pool_tp_tn)
            target_fp_fn += deficit

        rng = random.Random(SEED_BASE + SEED_OFFSET + family_idx)
        pool_fp_fn.sort(key=lambda p: (p["instance_id"], p["perturbation_id"]))
        pool_tp_tn.sort(key=lambda p: (p["instance_id"], p["perturbation_id"]))
        chosen_fp_fn = rng.sample(pool_fp_fn, target_fp_fn)
        chosen_tp_tn = rng.sample(pool_tp_tn, target_tp_tn)

        for r in chosen_fp_fn:
            r2 = dict(r)
            r2["verification_pool"] = (
                "FP" if r["quadrant"] == "insuff_accept" else "FN"
            )
            verification_set.append(r2)
        for r in chosen_tp_tn:
            r2 = dict(r)
            r2["verification_pool"] = (
                "TP" if r["quadrant"] == "suff_accept" else "TN"
            )
            verification_set.append(r2)

    out_cols = list(rows[0].keys()) + ["verification_pool"]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_cols)
        w.writeheader()
        w.writerows(verification_set)

    print(f"Wrote {len(verification_set)} prompts → {OUT_PATH}")
    print()
    print("By family:", dict(Counter(r["family"] for r in verification_set)))
    print("By verification_pool:", dict(Counter(r["verification_pool"] for r in verification_set)))
    print("By quadrant:", dict(Counter(r["quadrant"] for r in verification_set)))
    print("By source:", dict(Counter(r["source"] for r in verification_set)))
    print("By dataset:", dict(Counter(r["dataset"] for r in verification_set)))
    print()
    print("Selected prompt_ids:")
    print("  " + ",".join(r["prompt_id"] for r in verification_set))


if __name__ == "__main__":
    main()

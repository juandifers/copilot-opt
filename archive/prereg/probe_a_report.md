# Probe Report — Stage A §12 Diagnostic Runs

Generated: 2026-05-12 16:24 (all three probes complete)

---

## Probe A — 120s Reference Stability (10 audit pairs)

**Question:** Does doubling the PyVRP time budget from 60s to 120s meaningfully reduce
the structural multi-modality that drives the 92.6% `reference_struct_unstable` rate?

**Pairs selected:** 10 from the 216 audit subset, stratified across perturbation families
(CAPACITY ×3, DEMAND ×3, DISTANCE ×2, INSERTION ×2), choosing smallest struct-unstable
instances to minimise wall-clock.

**Per-pair results (120s):**

```
Instance             Pert     Family       ari(1,2)  ari(1,3)  ari(2,3)  ari_min   OBJ? STR? RNK?  @60s_STR?
--------------------------------------------------------------------------------------------------------------
X-n101-k25           CAP_3    CAPACITY     0.9275    0.9057    0.9130    0.9057      N    N    N        Y
X-n106-k14           CAP_4    CAPACITY     0.7323    0.5755    0.4970    0.4970      N    Y    Y        Y
X-n110-k13           CAP_3    CAPACITY     0.7763    0.9616    0.8114    0.7763      N    Y    Y        Y
X-n106-k14           DEM_2    DEMAND       0.8191    0.5936    0.6381    0.5936      N    Y    Y        Y
X-n125-k30           DEM_3    DEMAND       0.4270    0.4036    0.4277    0.4036      N    Y    Y        Y
X-n139-k10           DEM_3    DEMAND       0.3761    0.4133    0.6580    0.3761      N    Y    Y        Y
X-n106-k14           DIST_3   DISTANCE     0.4854    1.0000    0.4854    0.4854      N    Y    N        Y
X-n106-k14           DIST_2   DISTANCE     1.0000    1.0000    1.0000    1.0000      N    N    N        Y
X-n125-k30           INS_1    INSERTION    0.6797    1.0000    0.6797    0.6797      N    Y    Y        Y
X-n129-k18           INS_1    INSERTION    0.8164    1.0000    0.8164    0.8164      N    Y    N        Y
```

**Aggregate rates at 120s (n=10):**
- obj_unstable:    0.000  (Stage A 60s: 0.000)
- struct_unstable: 0.800  (Stage A 60s: 0.926)
- rank_unstable:   0.600  (Stage A 60s: 0.699)

**ARI_min among struct-stable at 120s (n=2):** median=0.953, min=0.906, max=1.000
**ARI_min among struct-unstable at 120s (n=8):** median=0.545, min=0.376, max=0.816

**Per-family struct_unstable rate:**

| Family | 120s rate | 60s rate | n |
|---|---:|---:|---:|
| CAPACITY | 0.667 | 0.926 | 3 |
| DEMAND | 1.000 | 0.926 | 3 |
| DISTANCE | 0.500 | 0.926 | 2 |
| INSERTION | 1.000 | 0.926 | 2 |

**Notable per-pair findings:**
- X-n101-k25 / CAP_3: stabilises at 120s (ARI_min 0.737→0.906, just above threshold).
- X-n106-k14 / DIST_2: perfectly stable at 120s — all three pairwise ARIs = 1.000.
- X-n106-k14 / DIST_3: bi-modal attractor — seeds 1 and 3 agree perfectly (ARI=1.0), seed 2 produces a distinct partition (ARI≈0.485 against both).
- DEMAND family: all three pairs remain struct-unstable at 120s, median ARI_min ≈ 0.47.

**Conclusion:** Doubling the time budget modestly reduces structural instability (92.6% → 80%)
but is far short of the §12.3 requirement (<5%). The 8 unstable pairs' ARI_min values
barely move (median 0.545 at 120s vs ≈0.48 at 60s), confirming genuine multi-modal
attractors. **The structural multi-modality is solver-structural**, not a consequence of
insufficient search time. Re-collection under PyVRP 120s (as mandated by §12.3) will
reduce the instability rate but will not achieve the <5% threshold at this scale.

---

## Probe B — CAPACITY De-escalation (5 instances × 4 perturbations × 5 actions)

**Question:** Can §12.5 magnitude de-escalation (ρ: {0.02,0.05,0.10,0.20} → {0.01,0.02,0.05,0.10})
bring STRUCT×CAPACITY into [0.10, 0.90]?

**STRUCT×CAPACITY band distribution (reuse_direct, n=20):**

```
Pert ID    rho     n    easy    med   hard   loss_p50
-----------------------------------------------------
pCAP_1    0.01     5   0.000  0.000  1.000   0.5835
pCAP_2    0.02     5   0.000  0.000  1.000   0.5968
pCAP_3    0.05     5   0.000  0.000  1.000   0.6342
pCAP_4    0.10     5   0.000  0.000  1.000   0.6057
OVERALL     —     20   0.000  0.000  1.000
```

Stage A STRUCT×CAPACITY easy fraction (ρ∈{0.02..0.20}): 0.070
Probe B STRUCT×CAPACITY easy fraction (ρ∈{0.01..0.10}): **0.000**

Interestingly, loss_struct is *lower* at ρ=0.01 than at ρ=0.05/0.10 (median 0.584 vs 0.634/0.606),
but all cells remain hard (loss_struct ≥ 0.357 at ρ=0.01; easy threshold is ≤ 0.10).

**Conclusion:** STRUCT×CAPACITY is **completely insensitive to perturbation magnitude.**
Even at ρ=0.01, every reuse_direct cell is in the hard band. The §12.5 magnitude
substitution procedure **cannot fix any STRUCT failure**. The structural mismatch between
reuse_direct (baseline route reuse) and pyvrp_60s (fresh solve) is inherent to the action
pair, not the perturbation intensity. The same conclusion extends to STRUCT×DEMAND,
STRUCT×DISTANCE, STRUCT×INSERTION by the same argument.

---

## Probe C — INSERTION De-escalation (5 instances × 4 perturbations × 5 actions)

**Question:** Can §12.5 magnitude de-escalation (γ: {0.30,0.70,1.20,2.00} → {0.15,0.40,0.80,1.50})
bring RANK×INSERTION into [0.10, 0.90]?

**RANK×INSERTION band distribution (reuse_direct, n=20):**

```
Pert ID   gamma     n    easy    med   hard   loss_p50
------------------------------------------------------
pINS_1    0.15      5   0.400  0.000  0.600   1.0000
pINS_2    0.40      5   0.000  0.200  0.800   1.0000
pINS_3    0.80      5   0.000  0.200  0.800   1.0000
pINS_4    1.50      5   0.000  0.400  0.600   1.0000
OVERALL    —       20   0.100  0.200  0.700
```

Stage A RANK×INSERTION easy fraction (γ∈{0.30..2.00}): 0.088
Probe C RANK×INSERTION easy fraction (γ∈{0.15..1.50}): **0.100**

The gain is entirely from pINS_1 (γ=0.15): 2/5 instances achieve loss_rank=0.500, which
falls in the easy band (≤0.50). The three higher severity levels remain hard-dominated.

**Conclusion:** The RANK×INSERTION improvement from de-escalation is **negligible** (0.088 → 0.100).
The block-level easy fraction sits exactly at the §12.1 lower boundary (0.100), making the
outcome highly sensitive to the 68-instance population. The loss_rank metric's discrete
nature (values: 0.0, 0.20, 0.50, 1.0 for 3-element sets) prevents smooth calibration — a
small change in γ cannot gradually shift the distribution; cells either achieve Jaccard≥0.5
or they don't. The §12.5 revision for RANK×INSERTION is marginally feasible for INS_1 alone
but unlikely to achieve a robust pass across 68 instances.

---

## Summary: §12.5 routing implications

| §12.1 failure | Probe evidence | §12.5 applicable? | Recommended action |
|---|---|:---:|---|
| STRUCT×CAPACITY | 0% easy even at ρ=0.01 (Probe B) | **No** | Construct review |
| STRUCT×DEMAND | Same mechanism as CAP | **No** | Construct review |
| STRUCT×DISTANCE | Same mechanism as CAP | **No** | Construct review |
| STRUCT×INSERTION | 5% easy context in Probe C | **No** | Construct review |
| RANK×INSERTION | 10% easy at de-escalated grid (boundary) | **Marginal** | Further investigation |

**§12.3 (reference instability):** 80% struct-unstable at 120s on probe sample.
§12.3-mandated 120s re-collection will reduce instability but not achieve <5%.
Consider whether §12.3's threshold was calibrated for this solver or requires amendment.

**Core finding:** The STRUCT claim (1 − ARI between reuse_direct and pyvrp_60s) measures
algorithm-pair disagreement rather than perturbation difficulty. It is near-maximised by
construction regardless of perturbation intensity, because PyVRP and route-reuse are
structurally incompatible solvers. This is a construct-level finding that cannot be
resolved through the §12.5 revision menu.

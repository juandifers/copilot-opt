# R2-S Phase 1 — axis4_payload (Large-Context Payload Stress)

Locked design for the 24-case Homberger-200 SCHEDULE-family stress
test. Companion to `product/evaluation/run2_gold_schema.md`. Frozen
after the C0 baseline scoring run; subsequent revisions require an
explicit changelog entry in §10.

## 1. Goal

Test the hypothesis that `evidence_precision` degrades monotonically
with route count on SCHEDULE-family payloads under the model-based
systems (A, B) and stays flat for the deterministic contract (C0).
Author the cases needed to evaluate the curve before any model-based
system runs.

Background: R2-4A and R2-5 showed gpt-5.4-mini's primary failure mode
on SCHEDULE payloads is *evidence over-citation* — emitting
`customer_schedule[].customer_id` alongside `.arrival`, or
`route_end_times[].route_idx` alongside `.end_time`. The
Homberger-200 inventory (see the R2 stress-split feasibility probe
report in conversation) shows existing solved cells at ~37 KB SCHEDULE
payload with route counts ∈ [6, 35], with 68 (instance × magnitude)
cells unsampled by Run 1. This axis draws stress cases from those 68.

## 2. Scope (in / out)

In scope:
- Family: SCHEDULE only.
- Intents: `customer_arrival`, `route_end_time`, `lateness_summary` —
  the three SCHEDULE-payload-selection intents.
- Cells: drawn from the 68 unsampled Homberger-200 (instance × PID)
  cells with pyvrp_10s checkpoints under
  `data/homberger_probe_checkpoints/pyvrp10s/`.

Out of scope (handled by other R2-S axes):
- Look-alike intent stress → `axis1_lookalike/`.
- OOD false premises + comparators → `axis2_ood_premises/`.
- Semantic intent stress → `axis3_semantic/`.

## 3. Stratification — two-band design (revised)

Per the conversation's stratification decision, this axis runs a
**two-band** design rather than the three-band design in the original
R2-S-Phase1 spec. The mid band (13–17 routes) gap is documented in §4
as an empirical finding, not filled with thin data.

| band | n_routes range | target cases | available cells |
|---|---|---:|---:|
| low  | 8–12  | 12 | 19 |
| high | 18–22 | 12 | 29 |

Total: **24 cases**.

Within each band, three intents, ~4 cases per (band × intent):

| | customer_arrival | route_end_time | lateness_summary |
|---|---:|---:|---:|
| low  | 4 | 4 | 4 |
| high | 4 | 4 | 4 |

Cell usage: **each cell used exactly once** (well under the ≤2 limit).

## 4. Mid-band gap (stratification finding)

The 68 unsampled cells distribute bimodally by pyvrp_10s route count:

| route count | n cells | band |
|---|---:|---|
| 6  | 3  | out (below) |
| 7  | 3  | out (below) |
| 8  | 6  | low |
| 9  | 2  | low |
| 10 | 5  | low |
| 11 | 1  | low |
| 12 | 5  | low |
| **13** | **2** | **(would-be mid)** |
| 14–18 | **0** | **(would-be mid — empty)** |
| 19 | 6  | high |
| 20 | 11 | high |
| 21 | 3  | high |
| 22 | 9  | high |
| 23–35 | 18 | out (above; mostly infeasible from R1_*) |

The original spec called for a mid band at 13–17. Two cells (both
`R2_2_1`, both at 13 routes) exist in that range, and the ≤2-uses
rule caps the band at 4 cases — too thin to stratify across three
intents. The gap from 14 to 18 is empirical, not a sampling artefact:
Homberger-200 instances split cleanly into long-horizon (C2/R2/RC2
series → low route counts) and tight-horizon (C1/R1/RC1 series →
high route counts) under PyVRP at 10 s. The intermediate regime is
not populated by the existing solver output.

This is a finding for the broader stress-test methodology, not a
deficiency to patch on this axis. A future expansion (Stage B
contingent on §5.2 of `prereg/PREREG_v1.2_vrptw.md`) using
re-solves at intermediate budgets could populate the mid band; out
of scope here.

## 5. Adversarial sub-pattern usage

Each case applies one of three sub-patterns (§Adversarial prompt
construction in the spec). Distribution:

| sub-pattern | low | high | total |
|---|---:|---:|---:|
| mid-list           | 4 | 4 | 8 |
| multi-entity       | 6 | 4 | 10 |
| routes-by-position | 2 | 4 | 6 |

`routes-by-position` is weighted toward the high band because long
route lists make positional selection adversarial (the contract emits
*all* `route_end_times[].end_time` entries when the prompt names a
route positionally rather than numerically — that's stress for the
*model* systems even though C0 is unaffected at the field-family
metric).

## 6. Pre-registered prediction table

Written before any model-based system runs. C0 predictions are
calibrated against the deterministic contract; A / B predictions are
derived from R2-4A / R2-5 observations of gpt-5.4-mini's
over-citation rate. The shape of the curve (monotone degradation for
A/B across bands; flat for C0) is the qualitative prediction;
ranges are the quantitative prediction.

| band | system | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | useful_refusal |
|---|---|---|---|---|---|---|---|---|---|
| low (8-12)  | C0 | 1.00 | 1.00 | 0.95–1.00 | 0.95–1.00 | 1.00      | 1.00      | 1.00      | n/a |
| low (8-12)  | A  | 0.95–1.00 | 0.95–1.00 | 0.90–0.95 | 0.75–0.85 | 0.90–1.00 | 0.95–1.00 | 0.95–1.00 | n/a |
| low (8-12)  | B  | 0.90–0.95 | 0.95–1.00 | 0.80–0.90 | 0.65–0.80 | 0.85–0.95 | 0.90–0.95 | 0.90–0.95 | n/a |
| high (18-22) | C0 | 1.00 | 1.00 | 0.95–1.00 | 0.95–1.00 | 1.00      | 1.00      | 1.00      | n/a |
| high (18-22) | A  | 0.90–0.95 | 0.95–1.00 | 0.85–0.90 | 0.55–0.75 | 0.85–0.95 | 0.90–0.95 | 0.90–0.95 | n/a |
| high (18-22) | B  | 0.85–0.95 | 0.90–1.00 | 0.75–0.85 | 0.45–0.65 | 0.80–0.90 | 0.85–0.95 | 0.85–0.95 | n/a |

`useful_refusal` is marked n/a because every case has
`expected_behavior_class ∈ {direct_answer, direct_answer_with_warning}`
— no useful_refusal cases in this axis.

`missing_field_recall` predicted at 1.00 for all systems on all
bands (no case has non-empty `expected_missing_fields`).

## 7. Split methodology

Stratified 60/40 dev/heldout, **seed=1**, stratified by
(band, intent). With 4 cases per sub-cell, exact 60/40 is not
integer; the closest integer assignment that still represents every
sub-cell in both splits is **14 dev / 10 heldout** (58.3 / 41.7 %).
Assignment rule:

1. Sort sub-cells lexicographically by (band, intent).
2. The first 2 sub-cells (alphabetically `(high, customer_arrival)`
   and `(high, lateness_summary)`) get 1 heldout per sub-cell; the
   other 4 sub-cells get 2 heldout each.
3. Within each sub-cell, shuffle the 4 cases via
   `random.Random(1).shuffle(...)` (in case_id order before shuffle)
   and assign the first n_heldout to heldout, the rest to dev.

Resulting split:

| band | intent | dev | heldout |
|---|---|---:|---:|
| low  | customer_arrival   | 2 | 2 |
| low  | route_end_time     | 2 | 2 |
| low  | lateness_summary   | 2 | 2 |
| high | customer_arrival   | 3 | 1 |
| high | route_end_time     | 2 | 2 |
| high | lateness_summary   | 3 | 1 |

**Heldout sample-size feasibility (§What to report 6):**

| band | dev n | heldout n | heldout ≥ 3 |
|---|---:|---:|:-:|
| low  | 6 | 6 | ✓ |
| high | 8 | 4 | ✓ |

Both bands satisfy heldout ≥ 3.

The split is **frozen**. Reshuffling, even with the same seed, would
constitute a Stage R2-S revision; subsequent C1 development reads
only dev rows.

## 8. Schema deviations and conventions

This axis follows `run2_gold_schema.md` with the following deviations
authorised by the R2-S-Phase1 spec:

- **Extra column `split`** at position 18 (values: `dev`, `heldout`).
  Required by the train/dev/test discipline of R2-S. All other columns
  identical to the 17-column schema.
- **Case ID range `R2-101`..`R2-124`**. The schema regex
  `^R2-\d{3}$` is preserved. R2-101+ avoids collision with the
  existing 60-case benchmark (R2-001..R2-060) and with the
  calibration set (R2-001..R2-015).
- **No new payload conditions**, intents, warnings, or next-actions
  beyond §2–§6 of the schema. All cases use existing enum values.
- **No `target_extension` cases.** Every row is
  `implementation_status = current` — the C0 contract handles each
  case under the existing intent/answerability/evidence pipeline.

The cases.csv is loaded by axis-specific tooling (`score_c0.py`)
that strips the `split` column before passing to the unmodified
`product/evaluation/run2_case_loader.py:Run2Case` constructor. The
existing scorer code is not modified.

## 9. Reproduction

```
# 1. Build SCHEDULE payloads for all 68 unsampled cells (one-time).
python3 product/evaluation/run2_stress/axis4_payload/build_payloads.py

# 2. Re-author the cases (idempotent; deterministic).
python3 product/evaluation/run2_stress/axis4_payload/_author_cases.py

# 3. Assign dev/heldout splits (seed=1, idempotent).
python3 product/evaluation/run2_stress/axis4_payload/_assign_splits.py

# 4. Score C0 (HEAD must equal 18b4811).
python3 product/evaluation/run2_stress/axis4_payload/score_c0.py
```

C0 must be evaluated at commit `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`
(tag `run2-contract-extended`). The scorer prints HEAD in
`reports/c0_baseline.md`.

## 10. Changelog

- 2026-05-20 — initial lock (24 cases, two-band design, seed=1 split,
  C0 baseline scored at HEAD `18b4811`).

# vrp-copilot-benchmark

Compute-aware, claim-level evaluation for VRP copilots.

> **Scope.** This repository currently covers **Phase 0 (data ingestion)**,
> **Phase 1 (pilot viability)**, and **Phase 2 (difficulty audit &
> conditional gap validation)**. Routing policies, hedging, and
> cost-aware meta-reasoning remain explicitly out of scope until Phase 2
> returns a `PROCEED` decision.

## Phase 2 scope

Phase 2 proves that the cheap-vs-strong quality gap is **conditional**,
not uniform. It extends the benchmark along three axes without expanding
the pilot dataset:

1. **Middle-tier backend.** Adds `savings` (Clarke-Wright parallel)
   between `nearest_neighbor` (baseline) and `pyvrp` (strong). The final
   backend set is `B0=nearest_neighbor`, `B1=savings`, `B2=pyvrp`.
2. **Wider perturbation spectrum.** Capacity factors widen to
   `[0.98, 0.95, 0.90, 0.80]` (near-degenerate through severe). A new
   required `regional_distance_inflation` family rewrites the instance
   as an explicit distance matrix with inflated edges touching
   customers in a deterministic high-x-coordinate region. Two
   exploratory families (`localized_demand_inflation`,
   `customer_insertion`) are reported but do **not** determine the
   Phase 2 decision.
3. **Difficulty labels + claim-family sensitivity.** Each
   `(instance, family, magnitude, cheap_backend)` scenario gets a
   difficulty label (`easy`, `medium`, `hard`) based on cheap-vs-strong
   objective gap and ARI. Claim-family errors are correlated against
   these scalars to show which claims degrade under which conditions.

Phase 2 outputs (under `data/processed/phase2/` and `reports/phase2/`):

```
reports/phase2/
  phase2_difficulty_audit.md     # human-readable report + decision
  solutions.jsonl                # every SolutionArtifact
data/processed/phase2/
  scenario_registry.csv
  backend_comparisons.csv
  perturbation_activation.csv
  difficulty_labels.csv
  conditional_gap_summary.csv
  claim_errors.csv
```

Run:

```bash
python -m vrpbench.experiments.phase2 \
  --config configs/phase2_difficulty.yaml \
  --registry data/processed/instance_registry.csv \
  --repo-root .

python -m vrpbench.experiments.report_phase2 \
  --config configs/phase2_difficulty.yaml \
  --registry data/processed/instance_registry.csv \
  --repo-root .
```

## Phase 1 decision: **PROCEED**

On 15 stratified Uchoa X instances (100 ≤ n ≤ 250), with seed `1` and a 60 s
PyVRP budget:

| Gate | Observed | Threshold | Pass |
| --- | --- | --- | --- |
| Parse rate | 100 % | ≥ 80 % | ✅ |
| PyVRP usable (all nominal runs feasible) | true | required | ✅ |
| Share of instances with gap-to-BKS ≤ 0.5 % | 87 % | median ≤ 3 % | ✅ |
| Share of instances with gap-to-BKS > 3 % | 0 % | must be minority | ✅ |
| Backend structural disagreement (both criteria) | 93 % | > 0 % | ✅ |
| Perturbation structural activation | 100 % | ≥ 50 % | ✅ |

Median gap to BKS is 0.14 %. The only instance that fails the *strict*
backend-disagreement gate is `X-n219-k73`, where the NN–PyVRP objective gap
(2.1 %) falls below the 3 % threshold even though the assignment ARI is only
0.39 — a noteworthy edge case worth following up on in Phase 2.

Full report: [`reports/phase1/phase1_pilot_report.md`](reports/phase1/phase1_pilot_report.md).
Phase 0 inspection: [`reports/phase0/phase0_instance_inspection.md`](reports/phase0/phase0_instance_inspection.md).

## Research question

Routing is treated as a metareasoning problem under bounded compute. For each
query, a system must choose between answering from a cheap approximate backend,
hedging, abstaining, or paying for a stronger solver. The benchmark is
observability-first: before we claim anything about policies, we must show
that the underlying data supports observable claim-level signals.

## Layout

```
vrp-copilot-benchmark/
  data/
    raw/cvrplib/                 # .vrp files (manual-first, download fallback)
    processed/
      instance_registry.csv      # Phase 0 output
      perturbed/                 # capacity-reduction .vrp files
  configs/
    phase0_data.yaml
    phase1_pilot.yaml
  src/vrpbench/
    data/                        # acquisition + instance loader + registry
    backends/                    # nearest_neighbor, pyvrp_backend
    perturbations/               # capacity (full) + skeletons for the rest
    artifacts/                   # SolutionArtifact (pydantic)
    claims/                      # reserved for Phase 2 claim families
    evaluation/                  # comparison metrics + activation screen
    experiments/                 # phase0, phase1, report_phase1
  reports/
    phase0/phase0_instance_inspection.md
    phase1/phase1_pilot_report.md
    phase1/{solutions.jsonl, comparisons.csv, activation.csv}
  tests/
    test_activation_screen.py    # required per protocol
```

## Locked protocol choices (Phase 1)

These are intentional, recorded to keep results comparable across runs:

- PyVRP is stochastic. Every `SolutionArtifact` records
  `random_seed`, `time_limit_sec`, `solver_params`, `solver_version`, `run_id`.
  Phase 1 defaults: seeds `[1]`, time limit `60s`.
- **PyVRP is not ground truth.** Where a CVRPLIB `.sol` (Best Known Solution)
  is available, we report `pyvrp_objective`, `bks_objective`,
  `gap_to_bks_pct`. Interpretation bands: ≤ 0.5% strong near-reference,
  0.5–3% strong heuristic baseline, > 3% insufficient reference quality.
- Frozen observable definitions:
  - route ranking = route distance contribution
  - top-k = 3
  - assignment disagreement = adjusted Rand index on customer co-assignment
  - routes are **not** matched by index
  - customer-level ranking is deferred
- Activation thresholds (`configs/phase1_pilot.yaml` — do not change):
  nonzero objective rel ≥ 0.01, structural ARI < 0.95, backend disagreement
  requires *both* objective rel ≥ 0.03 AND ARI < 0.90. Objective gap alone is
  insufficient.

## Dataset acquisition policy

Manual-first. Drop `.vrp` files into `data/raw/cvrplib/`.

If the directory is empty and `fallback_download.enabled: true` in
`configs/phase0_data.yaml`, the acquisition module fetches a **small**
stratified subset of Uchoa X instances (100 ≤ n ≤ 250, ~15 instances,
diverse `k`). We do **not** download all of CVRPLIB, ever. Set XL, VRPTW,
Solomon, Gehring-Homberger, job-shop, and facility-location are excluded
from Phase 0–1.

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Running

```bash
# Phase 0: ingest & inspect (downloads fallback subset if data/raw/cvrplib is empty)
python -m vrpbench.experiments.phase0 \
  --config configs/phase0_data.yaml --repo-root .

# Phase 1: pilot (nominal + capacity-reduction perturbations)
python -m vrpbench.experiments.phase1 \
  --config configs/phase1_pilot.yaml \
  --registry data/processed/instance_registry.csv \
  --repo-root .

# Build Phase 1 report + PROCEED/REVISE/STOP decision
python -m vrpbench.experiments.report_phase1 \
  --config configs/phase1_pilot.yaml \
  --registry data/processed/instance_registry.csv \
  --repo-root .

# Tests (required by protocol)
pytest tests/
```

## Outputs

- `reports/phase0/phase0_instance_inspection.md` — parse success, `n` / `k` /
  edge-weight stats, BKS availability, provenance.
- `reports/phase1/solutions.jsonl` — one `SolutionArtifact` per solve.
- `reports/phase1/comparisons.csv` — per-scenario backend comparisons
  (objective gap, ARI, top-k overlap, BKS gap).
- `reports/phase1/activation.csv` — activation-screen rows (backend + per
  perturbation × backend).
- `reports/phase1/phase1_pilot_report.md` — human-readable report with
  the final PROCEED / REVISE / STOP decision.

## Anti-overbuild guardrails

- No LLMs. No copilot. No trained models.
- No benchmark validity is assumed; the Phase 1 report can reject the data.
- Only capacity-reduction perturbation is fully implemented; demand scaling
  and distance inflation are explicit `NotImplementedError` skeletons. They
  become callable only after a `PROCEED` decision and a dedicated activation
  pass.
- Intervention ordering is **deferred to Phase 2** — requires ≥ 2
  perturbation families.

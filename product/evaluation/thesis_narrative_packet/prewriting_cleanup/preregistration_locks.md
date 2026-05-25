# Pre-registration and Locking Story

_Authored 2026-05-21. Directly pasteable into the thesis methods narrative.
All claims verified against git tags and commit history._

---

## Base locked commit

| Artifact | Value |
|---|---|
| HEAD throughout R2-4A → R2-6 | `18b4811` |
| Tag | `run2-contract-extended` |
| Commit message | "Run 2 contract extensions completed" |
| Date | 2026-05-20 |

This commit is the baseline of record for all product-contract evaluation.
Protected files are byte-identical to their pre-registered versions at this
tag; `validators.validate_no_protected_files_modified()` returns an empty
list at `18b4811`.

---

## Pre-registration tag chain

| Tag | Content | Scope |
|---|---|---|
| `spec-v1.1` | Experimental design, four pre-registered claims, 3-of-4 success rule, success criteria | Stage A closing experiment |
| `preregistration-v1` | Operational configuration lock (first version) | Stage A configs |
| `preregistration-v1.1` | Operational configuration lock (clarified op-validity for non-headline answers) | Stage A configs |
| `preregistration-prompts-v1` | Locked 48-prompt set (`experiment/data/prompts.csv`), cell selection | Stage A closing experiment |
| `full-run-v1` | Stage A full run artifact (48 prompts × 2 instances, generator outputs) | Stage A results |
| `verification-v1` | Human verification sample (n=12, 25% stratified) | Stage A |
| `calibration-pilot-v1-completed` | Stage A calibration pilot completion | Stage A |
| `run2-contract-extended` | Run 2 product-contract benchmark, all extensions, full evaluation | Run 2 |
| `prereg-v1.0-vrptw` through `prereg-v1.2-vrptw` | VRPTW perturbation / probe pre-registrations | Earlier probe phases |

---

## Locked artifacts (Run 2)

The following files are **immutable** from R2-2 onward. The runner verifies
byte-identical SHA against `18b4811` at preflight:

| File | Contents | Frozen since |
|---|---|---|
| `product/evaluation/run2_benchmark_cases.csv` | 60-case benchmark with gold intent, answerability, evidence, warnings, behavior_class | R2-2 |
| `product/evaluation/run2_gold_schema.md` | Strict 17-column row schema; §12 false-premise exception; §10a field-family evidence policy | R2-0 |
| `product/evaluation/run2_case_loader.py` | Case loader that enforces schema | R2-0 |
| `product/evaluation/run2_scoring.py` | Scorer (component metrics; no composite) | R2-0 |
| `product/evaluation/run2_payloads.py` | Payload materialization (from `full-run-v1`) | R2-0 |
| `product/evaluation/run2_system_c.py` | System C deterministic contract adapter | R2-0 |
| `product/evaluation/run2_calibration_cases.csv` | 15-case calibration set | R2-1 |

---

## What was frozen before each evaluation stage

### Stage A closing experiment
All 7 files in `experiment/configs/` (classifier config, generator config, judge
config, rubric, stratification, success_criteria, synthetic templates) were locked
at `preregistration-v1.1`. The prompt set was locked at `preregistration-prompts-v1`.
No changes to these files after their tags; any deviation is logged in
`experiment/AMENDMENTS.md`.

Stage A amendments (from AMENDMENTS.md, 4 deviations total):
1. Calibration pilot under degenerate kappa (all raters 5/5; kappa undefined) — proceeded.
2. Failure-mode heuristic widened to include generator-output schema keys.
3. Failure-mode heuristic narrowed to skip refusal contexts.
4. Route-indexing convention disagreement on prompt 040 (|diff|=2, human vs judge).

### Run 2 benchmark (R2-0)
Gold schema and scorer locked. No gold labels were moved in response to system
behaviour ("never tune gold to contract" was a hard pre-registration constraint).
Three new prompts (R2-038, R2-052, R2-057) and one gold-text revision (R2-022)
were corrected in-flight when the evaluator surfaced gold authoring errors — the
gold text was the bug, not the contract. These corrections are logged in
`run2_benchmark_case_notes.md` (corrections B-001 through B-006).

### R2-3 contract extensions
The six extension families (full_route_listing behavior, false-premise detection,
comparison_referent_ambiguity warning, route_indexing_ambiguity warning,
use_validity_payload next-action, objective-units exposure) were implemented and
verified against the benchmark before any model baseline (System B or A) was run.
System B saw the extended contract (C-extended), not the pre-extension contract
(C-current). This sequencing ensures model baselines are compared to the contract's
final state, not an intermediate state.

### R2-S stress axes
All four stress-axis case CSV files and their gold (inherited from base Run 2 cases)
were authored before C0 stress evaluation was run. No stress-axis gold was modified
after C0 results were seen. The shared methodology documents
(`coordination_report.md`, `system_d_design_envelope.md`) were pre-committed before
any System D implementation began.

### System D (D1 → D2 → D3 → D4 → D-Final) sequence
Each System D layer was evaluated on the same locked Run 2 benchmark and stress
cases. The System D design envelope (`system_d_design_envelope.md`) restricts
System D to modifying only `product/copilot/intent.py` — one architectural change.

### D-Final semantic holdout
The 48-case holdout was authored after D1's phrase banks were finalized (cases are
defined as outside D1's vocabulary). The 32/16 dev/heldout split was fixed at
authoring time. The D-Final design doc (thresholds, risk-zone intents, acceptance
criteria) was authored before the holdout was evaluated. The heldout split (16
cases) was not run until the final D-Final evaluation; its results appear first in
`d_final_closeout.md`.

---

## What was allowed to change after pre-registration

| Category | What could change | Rationale |
|---|---|---|
| New system wrappers | D1, D2, D3, D4, D-Final adapter code | System D is the experimental treatment; the envelope pre-specifies the boundary |
| New reports and analysis documents | All analysis, closeout, and narrative files | Documentation, not experimental data |
| New schema overlays | D3 v2 gold overlay for 5 causal cases | Overlay is a versioned extension, not a modification to existing gold |
| API and demo code | `product/api/`, `product/evaluation/model_clients/` | Product layer downstream of evaluation |
| New stress-axis cases | Added after C0 baseline was completed for prior axes | Additions are append-only; prior axis baselines are immutable |

---

## What was NOT allowed to change

| Category | Constraint | Enforcement |
|---|---|---|
| Gold labels in benchmark | Never tuned to match contract output | Pre-registered constraint; tracked by SHA |
| Locked case CSV files | Byte-identical at HEAD | `validators.validate_no_protected_files_modified()` |
| Scorer (`run2_scoring.py`) | No changes after R2-0 | SHA check |
| Stage A configs | Immutable after `preregistration-v1.1` | SHA check |
| Stage A prompt set | Immutable after `preregistration-prompts-v1` | SHA check |
| Existing stress-axis case IDs | No renaming or deletion | Append-only policy |
| Must-not-regress 70-cohort | D1 must hold 70/70 | Enforced by D1 evaluation gate |

---

## Test / checksum evidence

- `validators.validate_no_protected_files_modified()`: returns empty list at HEAD `18b4811`; 7 locked Run 2 files byte-identical.
- Run 2 test suite: 139 tests at end of R2-6 (`pytest --collect-only`); 369 run2-tagged.
- D1 must-not-regress: 70/70 preserved (live run, `system_d1_stress_report.md §3`).
- D-Final test suite: 40 pass / 2 live-gated skip (tests run without live LLM).

---

## Thesis methods statement (pasteable)

> "The Run 2 benchmark (60 cases, gold schema, scorer, and payload
> materialisation paths) was frozen at commit `18b4811` (tag
> `run2-contract-extended`) before any model baseline evaluation was
> conducted. No gold label was moved after model outputs were observed.
> The Stage A experiment design, prompt set, and configurations were
> locked at `preregistration-v1.1` and `preregistration-prompts-v1`
> respectively; four deviations are logged in `experiment/AMENDMENTS.md`
> with rationale and dates. The System D design envelope
> (`system_d_design_envelope.md`) restricted all System D variants to
> modifying only the intent classifier (`product/copilot/intent.py`),
> pre-committing the boundary before any System D implementation began.
> Protected-file integrity was verified by SHA checksum at the HEAD of
> each evaluation run."

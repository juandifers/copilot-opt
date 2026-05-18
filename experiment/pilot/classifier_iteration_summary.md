# Classifier configuration — iteration summary

Citable artifact for the thesis methodology chapter. Documents the
process that produced the locked zero-shot classifier configuration
for the LLM-in-the-loop closing experiment, including the iteration
that failed and the reason for stopping at zero-shot.

## Decision

**Locked configuration: zero-shot with the four family definitions and
six boundary cases.** Active prompt at
`experiment/configs/classifier_system_prompt.txt`. Generator and judge
configurations are independent and locked separately at
pre-registration.

A documented limitation accompanies the lock: zero-shot achieves
0.667 (2/3) accuracy on STRUCT_SCHEDULE boundary prompts where
"before/after" language refers to visit sequence rather than clock
time. The post-hoc error analysis uses the ground-truth `true_family`
column on the locked prompt set to surface this asymmetry without
adjusting the classifier configuration.

## Timeline

### Stage 1 — Zero-shot pilot on stratified easy prompts (n=12)

- Twelve hand-written prompts, three per claim family, written in
  operator phrasing. Each prompt sits clearly within its family with
  no boundary overlap. Source: `experiment/pilot/classifier_pilot.csv`.
- Model: `claude-haiku-4-5-20251001` via Claude Code headless (`-p`,
  `--system-prompt-file`, `--allowedTools ""`, JSON schema constrained).
- Result: **12/12 = 1.000.** Confusion matrix is the identity.

The trivial pass rate confirmed the headless plumbing worked and
established a baseline. It was deliberately not used as evidence
about classifier capability — the prompts did not exercise family
boundaries.

### Stage 2 — Boundary mini-pilot (n=12)

- Twelve hand-written prompts at five inter-family boundaries:
  3 × PV↔SCHEDULE, 3 × STRUCT↔SCHEDULE, 2 × OBJ↔STRUCT,
  2 × PV↔STRUCT, 2 × OBJ↔SCHEDULE. Each prompt carries a
  `boundary_rationale` justifying its `true_family` label given the
  payload schema's headline claim. Source:
  `experiment/pilot/classifier_boundary_pilot.csv`.
- Same model, same locked zero-shot prompt as Stage 1.
- Result: **11/12 = 0.917.** Above the 0.85 lock threshold overall.

Per-boundary breakdown surfaced a hidden asymmetry: four of five
boundaries scored 1.000, but STRUCT_SCHEDULE scored 0.667 (2/3). The
single error was BSS_03 ("Does route 5 visit customer 12 before or
after customer 17?") predicted as SCHEDULE rather than STRUCT — the
model treated "before/after" as temporal language and missed that
the prompt asks for visit-order, not clock-order.

| boundary_pair | n | correct | accuracy |
| --- | --- | --- | --- |
| OBJ_SCHEDULE | 2 | 2 | 1.000 |
| OBJ_STRUCT | 2 | 2 | 1.000 |
| PV_SCHEDULE | 3 | 3 | 1.000 |
| PV_STRUCT | 2 | 2 | 1.000 |
| **STRUCT_SCHEDULE** | **3** | **2** | **0.667** |

Full per-prompt detail and raw model responses preserved at
`experiment/pilot/classifier_boundary_pilot_results.md` and
`experiment/logs/classifier/boundary_pilot_2026-05-18_181631.jsonl`.

### Stage 3 — Targeted few-shot intervention (n=15)

A surgical bump to address the STRUCT_SCHEDULE weakness in isolation.

- Four exemplars appended to the active system prompt under a new
  "Examples (STRUCT vs SCHEDULE — visit order vs clock time)" section:
  two STRUCT exemplars on sequence-order phrasing without clock
  anchors, two SCHEDULE exemplars on clock-anchored phrasing. The
  family definitions and the six boundary cases were left untouched
  so the only experimental variable was the new section. Archived
  version: `experiment/pilot/classifier_system_prompt_fewshot_v1.txt`.
- Test set: the 12 boundary prompts verbatim plus 3 new
  STRUCT_SCHEDULE prompts (n=15 total; STRUCT_SCHEDULE n=6, other
  boundaries unchanged). Test prompts disjoint from exemplars.
  Source: `experiment/pilot/classifier_fewshot_pilot.csv`.
- Same model. Same headless invocation. Same retry policy
  (single retry only on subprocess returncode=1 transient; 0 retries
  triggered in this run).
- Result: **14/15 = 0.933.**

| boundary_pair | n | correct | accuracy | vs. Stage 2 |
| --- | --- | --- | --- | --- |
| OBJ_SCHEDULE | 2 | 2 | 1.000 | = |
| OBJ_STRUCT | 2 | 2 | 1.000 | = |
| **PV_SCHEDULE** | **3** | **2** | **0.667** | **↓ from 1.000** |
| PV_STRUCT | 2 | 2 | 1.000 | = |
| **STRUCT_SCHEDULE** | **6** | **6** | **1.000** | **↑ from 0.667** |

The targeted fix worked exactly where intended (STRUCT_SCHEDULE
recovered to 1.000 including the BSS_03 case the exemplars were
designed for). But a previously-perfect boundary regressed:
PV_SCHEDULE went from 3/3 to 2/3. The miss was BPS_01 ("Will
customer 42 still get a delivery today?") — unchanged prompt,
classified PV in Stage 2 and SCHEDULE in Stage 3.

Full per-prompt detail and raw model responses preserved at
`experiment/pilot/classifier_fewshot_pilot_results.md` and
`experiment/logs/classifier/fewshot_pilot_2026-05-18_182603.jsonl`.

## Mechanism

The STRUCT_SCHEDULE exemplars all hinge on the same disambiguator:
*temporal-sounding language is STRUCT without a clock anchor and
SCHEDULE with one*. Four exemplars heavily front-load this
disambiguation, and the model appears to generalise the rule beyond
its intended scope: when a non-STRUCT/SCHEDULE prompt contains
temporal language ("today" in BPS_01), the model now over-weights
the temporal cue and routes to SCHEDULE.

This is the isomorphism that justifies the stop. Stage 2 had
STRUCT_SCHEDULE at 0.667 with one error attributable to a single
unfamiliar pattern; Stage 3 has PV_SCHEDULE at 0.667 with one error
attributable to over-fitting on the disambiguator the exemplars were
chosen to teach. Same n, same error rate, different boundary.
Continuing to iterate would chase a moving target — each fix risks
producing an equivalent regression elsewhere.

Two caveats on the mechanism reasoning:

1. The model's reasoning is not visible. The headless response
   returns `result: ""` with `structured_output: {family: ...}`. The
   regression-by-attention-bias hypothesis is consistent with the
   evidence but not directly verified.
2. n=3 per boundary is small. A 0.667 accuracy is a single error;
   the regression *could* be sampling noise on a borderline prompt
   the model would also have missed in Stage 2 under a different
   prompt cache state. The locked prompt set (48 prompts) will
   provide a larger sample for the final error analysis.

## Decision

Lock zero-shot. The classifier ships at the Stage 2 configuration
with the documented STRUCT_SCHEDULE limitation.

Reasons:

- Stage 3 was not a strict-Pareto improvement: STRUCT_SCHEDULE
  recovered but PV_SCHEDULE regressed by the same magnitude on the
  same sample size. Net delta on the original boundary set (excluding
  the 3 new STRUCT_SCHEDULE test prompts) is exactly zero.
- The iteration mechanism is exhausted: further exemplars would
  almost certainly produce another equivalent regression elsewhere
  (the family taxonomy has six pairwise boundaries; the model only
  has so much capacity to differentiate signals).
- The classifier accuracy spec (Section "Pass/fail criteria" in
  `spec.md`) requires ≥ 0.80 overall. Zero-shot achieves 0.917 on
  the boundary set and 1.000 on the easy set. Both clear the spec
  threshold by a margin.

## Audit protocol for the final run

The locked 48-prompt pool will include `true_family` ground-truth
labels per prompt (carried through from the pilot CSV schema). The
final-report analysis can:

1. Compute per-prompt classifier accuracy on the locked set with
   no additional ground-truth labelling required.
2. Compute per-boundary accuracy (using the same `boundary_pair`
   column convention as the pilot CSVs) where the locked-set prompts
   exercise inter-family boundaries.
3. Surface any final-run errors at the per-prompt level so the
   discussion section can examine specific failure modes against
   the rationale text.

The STRUCT_SCHEDULE limitation should be cited in the methodology
chapter where the classifier is introduced. If the locked-set
results show the limitation manifesting (≥ 1 STRUCT prompt routed
to SCHEDULE on the basis of "before/after" phrasing), report it
explicitly in the results section rather than treating it as a
surprise.

## Artifacts

Inputs and outputs of each stage, all preserved in the repo for
audit:

| stage | prompts | results | raw log |
| --- | --- | --- | --- |
| 1 (easy zero-shot) | `experiment/pilot/classifier_pilot.csv` | `experiment/pilot/classifier_pilot_results.md` | `experiment/logs/classifier/pilot_2026-05-18_180703.jsonl` |
| 2 (boundary zero-shot) | `experiment/pilot/classifier_boundary_pilot.csv` | `experiment/pilot/classifier_boundary_pilot_results.md` | `experiment/logs/classifier/boundary_pilot_2026-05-18_181631.jsonl` |
| 3 (boundary few-shot) | `experiment/pilot/classifier_fewshot_pilot.csv` | `experiment/pilot/classifier_fewshot_pilot_results.md` | `experiment/logs/classifier/fewshot_pilot_2026-05-18_182603.jsonl` |

Locked system prompt:
`experiment/configs/classifier_system_prompt.txt` (zero-shot, 23 lines,
sha256: `b180b6929fbb9e86183ca0b64883b2e3893e40f84c60c6ccd91ffc09c8dd96ba`).

Archived (not active) few-shot v1 prompt for reproducibility of
Stage 3: `experiment/pilot/classifier_system_prompt_fewshot_v1.txt`
(32 lines, sha256:
`76794b333bc8c186c426c00e3d088080a182e201c2379040b00fdff8f1834d0a`).

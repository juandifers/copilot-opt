# VRP Copilot — LLM-in-the-loop closing experiment

**Version: v1.1** — locked at the pre-registration commit. Changes vs. v1.0: model choices for classifier / generator / judge specified concretely (Haiku 4.5 generator, Sonnet 4.6 judge, Haiku 4.5 classifier; rationale in the relevant sections); headless invocation mode locked to `bare: false` (OAuth via the Max plan, with the reproducibility caveat documented in §1); classifier iteration evidence referenced; Homberger SCHEDULE quadrant asymmetry surfaced in the Prompt set section. The v1.0 design intent is unchanged; v1.1 is locking the decisions that v1.0 left as "Choice to settle."

**Canonical claim family naming.** Four families: OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE. The data tables (`stage_a_vrptw_consolidated_claim_rows.parquet`, `deployment_config.csv`) use the full label `PLAN_VALIDITY`; this document uses the short form `PV` for brevity. Both refer to the same family.

The thesis methodology hasn't been tested against actual language behaviour yet. Stage A and Homberger established the predictor; this experiment puts the full pipeline together — natural-language prompt in, grounded natural-language answer out — and measures the result against the three-axis decomposition that's the conceptual centrepiece of the thesis.

The deliverable is a standalone validation that the abstractions you defined (claim families, sufficiency, the three axes) operationalise on real prompts and detect distinct failure modes. It's the answer to "where is the LLM?"

## Pipeline (the product)

```
operator prompt
      │
      ▼
[claim-family classifier]  ──►  family ∈ {OBJ, PV, STRUCT, SCHEDULE}
      │
      ▼
[sufficiency predictor]    ──►  P(cheap_sufficient | features, family)
   (per-family locked)
      │
      ▼
[compute-aware policy]     ──►  use_cheap | escalate_to_pyvrp_10s
   (per-family threshold)
      │
      ▼
[answer generator (LLM)]   ──►  natural-language answer grounded in
                                action output
      │
      ▼
[three-axis scorer]        ──►  (faithfulness, sufficiency, op-validity)
```

The product value is: operator gets a grounded natural-language answer fast when cheap suffices, the system escalates when it doesn't, and the three-axis monitor catches the failure modes that single-metric evaluation misses.

What gets validated by the experiment:

1. The classifier maps natural-language prompts to claim families with usable accuracy
2. The locked predictor's decisions produce measurably different language-level outcomes
3. The three axes are separately measurable on real prompts and capture distinct failure modes (faithful-but-insufficient ≠ sufficient-but-unfaithful)
4. The full pipeline meets a deployable quality threshold across claim families

## Components

### 1. Claim-family classifier

**Job:** map a natural-language prompt to one of {OBJ, PV, STRUCT, SCHEDULE}.

**Implementation (locked at v1.1):** Claude Haiku 4.5 (canonical served id `claude-haiku-4-5-20251001`, alias `claude-haiku-4-5`), invoked via Claude Code headless (`-p`, `--system-prompt-file`, `--output-format json`, `--json-schema`, `--allowedTools ""`, `--no-bare`). System prompt at `experiment/configs/classifier_system_prompt.txt`: four family definitions + six boundary cases, zero-shot. No few-shot exemplars (the iteration that tested four targeted exemplars produced an isomorphic regression — see below).

**Iteration evidence (locked, not re-runnable post pre-registration):** the classifier was validated across three pilots: trivial zero-shot (12/12), boundary stress (11/12, STRUCT_SCHEDULE 2/3), targeted few-shot (14/15, PV_SCHEDULE 2/3). Few-shot was reverted as an isomorphic trade rather than a strict-Pareto improvement. Full timeline, mechanism analysis, and the audit protocol at `experiment/pilot/classifier_iteration_summary.md`. **Known limitation locked into the design:** STRUCT_SCHEDULE boundary accuracy ~0.667 in pilot; the analysis section reports Claim 2 (policy effect) both with and without classifier errors using the hand-labelled ground-truth `true_family` column on the locked prompt set.

**Headless mode rationale (`bare: false`).** Claude Code's `--bare` flag strictly requires `ANTHROPIC_API_KEY`; the experiment runs under a Claude Max OAuth session, so `--bare` is dropped. `--system-prompt-file` overrides the default dynamic system-prompt sections (cwd / env info / memory paths / git status), which recovers most of the reproducibility `--bare` would have provided. Hooks / plugins / CLAUDE.md auto-discovery still run; with `--allowedTools ""` no tool use occurs, so PreToolUse/PostToolUse hooks do not fire.

**Validation:** the locked prompt set (48 prompts; see Prompt set section) carries per-prompt hand-labelled `true_family` so post-hoc classifier accuracy on the locked set is computable without a separate held-out pool. The pilot evidence is the iteration summary above.

**Frozen at pre-registration:** prompt template (sha256 of `classifier_system_prompt.txt` recorded in the iteration summary), model id (alias `claude-haiku-4-5`; served version asserted on the first call of every run and the run halts on mismatch), temperature (0; Claude Code does not expose a temperature flag — temperature is the model's default for structured-output mode, locked at run time and asserted to be deterministic across the pilot runs).

### 2. Sufficiency predictor (locked from Stage A)

**Job:** given cell features and claim family, output P(cheap action will be sufficient).

**Implementation:** the deployment configuration from `deployment_config.csv`:

| family | model | feature set | source |
| --- | --- | --- | --- |
| OBJ | HistGB | C_clean | Stage A Run 2 locked |
| PV | HistGB | B_pre_cheap | Stage A Run 2 closure |
| STRUCT | HistGB | C_clean | Stage A Run 2 locked |
| SCHEDULE | HistGB | C_clean | Stage A Run 2 locked |

**Frozen:** model weights, feature pipeline, NaN-handling rule.

### 3. Compute-aware policy (locked)

**Job:** given P(sufficient) and the family-specific threshold, decide cheap or escalate.

**Per-family thresholds:** from `deployment_config.csv` at the 0.90 correctness floor (balanced operating point — tight enough to be deployable, loose enough to keep coverage):

| family | threshold | expected correctness | expected compute |
| --- | --- | --- | --- |
| OBJ | 0.50 | 0.980 | 0.9 s |
| PV | 0.50 | 0.904 | 5.5 s |
| STRUCT | 0.95 | 0.874 | 7.7 s |
| SCHEDULE | 0.98 | 0.892 | 9.5 s |

**Frozen:** thresholds, escalation target (pyvrp_10s).

### 4. Answer generator (LLM)

**Job:** produce a natural-language answer to the operator's question, grounded in the action's output.

**Implementation (locked at v1.1):** Claude Haiku 4.5 (`claude-haiku-4-5` / served `claude-haiku-4-5-20251001`), invoked via Claude Code headless under the same conditions as the classifier (`--no-bare`, `--system-prompt-file`, `--output-format json`, `--json-schema`, `--allowedTools ""`, `max_tokens: 1500`). System prompt + structured output schema at `experiment/configs/generator_system_prompt.txt` and `experiment/configs/generator_output_schema.json`. Three explicit anti-hallucination guards in the system prompt (Haiku needs them; Sonnet wouldn't), wording locked verbatim in `generator_system_prompt.txt`. Structured output is validated against the schema on every call; validation failure halts the run.

**Stress-test framing.** Haiku 4.5 as the generator is a deliberate stress-test choice: a lighter generator is more likely to produce faithfulness failures, which the three-axis decomposition is designed to surface. The pre-registered thresholds are unchanged from this section's pass/fail criteria; the framing note is logged in `experiment/configs/success_criteria.md` and applied at result-interpretation time, not at threshold-setting time.

**Implementation template:**

```
You are an assistant answering an operator's question about a vehicle
routing plan after a perturbation. Use ONLY the information provided
in the SOLUTION DATA section. Do not invent numbers or routes. If the
data does not answer the question, say so explicitly.

QUESTION: {operator_prompt}

CONTEXT:
- Instance: {instance_id}
- Perturbation: {perturbation_description}
- Action taken: {action_name}

SOLUTION DATA:
- Routes: {route_summary}
- Schedule: {schedule_summary}
- Objective: {objective_value}
- Feasibility: {feasibility_flags}
- Late customers: {late_customers_list}

ANSWER:
```

**Frozen at pre-registration:** template (no iteration), model (`claude-haiku-4-5`), temperature (Claude Code default for structured-output mode), `max_tokens: 1500`. The first generator call of every run logs `response.model` and asserts a `claude-haiku-4-5` prefix; mismatch halts the run.

### 5. Three-axis scorer

**Judge model (locked at v1.1):** Claude Sonnet 4.6 (`claude-sonnet-4-6`), invoked via Claude Code headless under the same `--no-bare` conditions as the generator. Sonnet reads Haiku's output; choosing a different model than the generator separates generation and evaluation per spec §"Decisions to settle". The judge prompt explicitly instructs against the known Sonnet-as-judge failure mode of hallucinating constraints the payload doesn't have and then penalising the generator for not mentioning them. System prompt at `experiment/configs/judge_system_prompt.txt`; rubric (loaded by the judge) at `experiment/configs/rubric.md`.

**Op-validity vs faithfulness scoping (locked at v1.1).** Op-validity is the binary deterministic per-family check (one headline claim per family — see below). Faithfulness is the rubric-based prose-vs-payload verification over every payload-supported claim the generator makes; when an answer contains multiple payload-covered claims, faithfulness earns the lower of the per-claim sub-scores. The rubric and the judge prompt both encode this split explicitly.

**Faithfulness:** does the answer accurately reflect what the action's output shows? Did the LLM invent numbers, mis-state the routes, or claim certainty where the data is silent?

- *Method:* rubric-based scoring with LLM-as-judge for scale + human pilot of 20 prompts for calibration
- *Rubric (5-point scale):*
  - 5: every numerical and structural claim matches the data
  - 4: minor imprecision (e.g., rounding); no semantic error
  - 3: one factual claim doesn't match data, but the answer is broadly correct
  - 2: multiple claims don't match; the answer is misleading
  - 1: hallucinated content not present in the data
- *Pre-registered threshold:* binary "faithful" = score ≥ 4

**Sufficiency:** known from the Stage A / Homberger label. Sufficient = 1 if the action's output would have produced the right answer under the reference; 0 otherwise. No new scoring needed; pull from the cell's existing label.

**Operational validity:** is the answer executable? Three deterministic checks per claim family:

- *OBJ:* the answer's stated objective value matches the action output to within 0.5%
- *PV:* the answer correctly identifies whether the plan is feasible (matches `action_feasible` flag)
- *STRUCT:* the route count or assignment claim matches the action output exactly
- *SCHEDULE:* the timing claim matches the action's schedule (within 1 minute tolerance)

Operational validity is binary: passes all relevant checks or doesn't.

## Prompt set

**Size:** 48 prompts. 12 per claim family. Within each family, a 2×2 stratification:

- 3 prompts on cells where cheap is sufficient AND policy accepts (true positives)
- 3 prompts on cells where cheap is sufficient AND policy escalates (false negatives — predictor wrongly escalates)
- 3 prompts on cells where cheap is insufficient AND policy accepts (false positives — predictor wrongly accepts)
- 3 prompts on cells where cheap is insufficient AND policy escalates (true negatives)

This stratification is the analytical engine. The three-axis scorer should produce different patterns in each quadrant; comparing them tells you whether the axes are doing the conceptual work the thesis claims.

**Sources:**

- *Synthetic templates (24 prompts):* hand-written paraphrases of the four claim families. Three template variations per family × 2 instances per template. Locked at design time.
- *LLM-generated variants (24 prompts):* frontier LLM prompted with the cell context and asked to write a realistic operator question of a given claim family. Manual filter for "sounds like operator language, asks the intended claim." Locked once filtered.

The mix exists to test external validity: if scores diverge between synthetic and LLM-generated prompts, that's a finding (the methodology is sensitive to prompt phrasing).

**Cell selection:** stratify across instance class (Solomon C/R/RC), and include both Stage A cells (60 prompts' worth available) and Homberger cells (the OOD slice — include 12 prompts from Homberger, 3 per family). The Homberger inclusion lets the experiment make a cross-scale claim about LLM behaviour, not just Solomon-100.

**Homberger SCHEDULE asymmetry (locked at v1.1).** Per `experiment/discovery_report.md` §3, the Homberger SCHEDULE family has zero cells in the policy-accept quadrants at the locked SCHEDULE threshold of 0.98 (0 in suff×accept, 0 in insuff×accept). The strict 3-per-quadrant Solomon stratification is therefore not satisfiable on Homberger SCHEDULE. The locked sampling rule: Homberger SCHEDULE prompts come from the two escalate quadrants only (sufficient×escalate and insufficient×escalate), distribution maximising informational value subject to the cell counts in the audit. This is a property of the deployment configuration, not a sampling failure; the stratification rule is recorded explicitly in `experiment/configs/stratification.md` so the analysis section can cite it.

## Experimental design

**Primary outcomes (per claim family):**

1. Mean faithfulness score (out of 5) — descriptive
2. Faithfulness pass rate (fraction with score ≥ 4) — binary headline
3. Operational validity pass rate — binary headline
4. Three-axis joint distribution — counts in each of the 8 cells of (faithfulness × sufficiency × op-validity)

**Pre-registered claims to test:**

- *Claim 1 (axis separability):* the three axes are not collinear. Specifically, at least 10% of prompts produce mixed patterns (high on one axis, low on another). If all prompts are either all-pass or all-fail, the axes are redundant and the thesis claim weakens.
- *Claim 2 (policy effect):* policy-accepts vs policy-escalates produces measurably different language-level outcomes. Operational validity rate differs by ≥ 0.20 between the two policy decisions on insufficient cells.
- *Claim 3 (sufficiency manifests):* on insufficient cells, faithfulness and operational validity drop. Mean faithfulness on insufficient cells is at least 0.5 points lower than on sufficient cells (5-point scale).
- *Claim 4 (cross-scale):* Homberger prompts don't produce dramatically worse scores than Stage A prompts. Mean faithfulness drop on Homberger is ≤ 0.5 points.

**Secondary analyses:**

- Failure mode taxonomy: hand-categorise the prompts that fail faithfulness or operational validity. Look for recurring patterns (e.g., "LLM invents customer IDs," "LLM confuses route order").
- Synthetic vs LLM-generated prompt comparison: do the scores differ systematically?
- Per-claim-family qualitative review: read 3 successful and 3 failed answers per family for the discussion section.

## Scoring procedure

**Step 1: human pilot (calibration).** 20 prompts dual-rated by you + an LLM-as-judge using the same rubric. Compute inter-rater agreement (Cohen's kappa or simple correlation). If agreement is below 0.7, refine the rubric before scaling. If above 0.7, proceed.

**Step 2: full LLM-as-judge.** All 48 prompts scored by the LLM-as-judge using the calibrated rubric. Save the judge's reasoning so you can spot-check.

**Step 3: stratified human verification.** Manually verify 25% of LLM-as-judge scores (12 prompts, stratified across the four 2×2 cells per family). Report agreement; flag disagreements for separate analysis.

This three-step process gives you the scale of LLM-as-judge with the trust of human verification on a defensible subset.

## Pre-registration (freeze before running)

In a single version-controlled commit, tagged `preregistration-v1`:

- Prompt set (all 48 prompts, with metadata: family, sufficiency label, expected policy decision, source, hand-labelled `true_family`) — Prompt 5, not this commit
- Classifier config + system prompt (`experiment/configs/classifier_config.yaml`, `classifier_system_prompt.txt`) — locked here
- Generator config + system prompt + structured-output schema (`generator_config.yaml`, `generator_system_prompt.txt`, `generator_output_schema.json`) — locked here
- Judge config + system prompt (`judge_config.yaml`, `judge_system_prompt.txt`) — locked here
- Three-axis rubric (`rubric.md`) — faithfulness wording, op-validity check definitions, op-validity vs faithfulness scoping, refusal handling — locked here
- Pass/fail criteria per claim, 3-of-4 rule, methodology-limit conditions (`success_criteria.md`) — locked here
- Sample size and stratification rule (`stratification.md`) — locked here, including the Homberger SCHEDULE asymmetry handling
- Human pilot calibration protocol (`pilot_protocol.md`) — locked here
- LLM-as-judge model and prompt — locked in `judge_config.yaml` / `judge_system_prompt.txt`
- Verification sampling rate (25%) and deterministic sampling rule with seed=2026 (`verification_protocol.md`) — locked here
- Cost-warmup note for total-cost-of-run reporting (`cost_warmup_note.md`) — locked here
- This document (`spec.md`) tagged `spec-v1.1` — locked immediately before the pre-registration commit

After the commit, no changes until the experiment is done. If something requires changing (e.g., the classifier underperforms badly), document the change and re-run from scratch with the new pre-registered version.

## What success looks like

The experiment succeeds (the thesis methodology validates at the language layer) if **at least three of these four conditions hold:**

1. Claim 1 (axis separability): ≥ 10% of prompts produce mixed-axis patterns
2. Claim 2 (policy effect): operational validity differs by ≥ 0.20 between policy-accepts and policy-escalates on insufficient cells
3. Claim 3 (sufficiency manifests): faithfulness drops by ≥ 0.5 points on insufficient cells
4. Claim 4 (cross-scale): Homberger faithfulness within 0.5 points of Stage A

The experiment flags methodology limits (still publishable, reframed) if:

- The classifier accuracy is below 0.80: the claim-family abstraction may not be as clean in natural language as the predictor work assumed
- Faithfulness pass rate is below 0.70 overall: the LLM-as-grounded-answer-generator part of the product needs more constraint engineering
- Axes are collinear (Claim 1 fails strongly): the three-axis decomposition isn't doing distinct work in this experiment; either the prompts didn't exercise the distinction, or the axes need rethinking

**Framing note 1 — stress-test framing.** Generator is Haiku 4.5; judge is Sonnet 4.6. A lighter generator is more likely to produce faithfulness failures, which the three-axis decomposition is designed to surface. Claim 1 (axis separability) is therefore expected to be easier to demonstrate at the ≥10% threshold than with a production-grade generator. Claim 4 (cross-scale faithfulness within 0.5 of Stage A on Homberger) is expected to be harder, because Haiku's hallucination rate is more sensitive to longer route lists. The pre-registered thresholds are unchanged; this note documents the framing the numbers will be interpreted against.

**Framing note 2 — classifier limitation auditable.** Zero-shot classifier locked with STRUCT_SCHEDULE boundary at ~0.667 in pilot. `prompts.csv` carries hand-labelled `true_family` per prompt; the analysis reports Claim 2 (policy effect) both with and without classifier errors so the classifier contamination is separable from the policy effect.

## Decisions settled at v1.1

| # | Decision | Locked at v1.1 | Rationale |
| --- | --- | --- | --- |
| 1 | Frontier LLM for the answer generator | Claude Haiku 4.5 (`claude-haiku-4-5`) | Stress-test framing: lighter generator surfaces more faithfulness failures, which the three-axis decomposition is designed to detect. Documented in §"What success looks like" framing notes. |
| 2 | LLM for the judge | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | Different from generator; separates generation and evaluation. Sonnet 4.6 is conservative on hallucination, well-suited to rubric-based scoring of Haiku's output. |
| 3 | LLM for the classifier | Claude Haiku 4.5 (`claude-haiku-4-5`), zero-shot | Locked after a documented 3-stage iteration. Same model as generator (not the judge); spec v1.0 recommendation revised because Haiku zero-shot already cleared the 0.85 boundary-pilot accuracy threshold, and matching the generator simplifies the API setup. Evidence: `experiment/pilot/classifier_iteration_summary.md`. |
| 4 | Prompt source mix | 50/50 synthetic / LLM-generated | Synthetic provides a controlled spine, LLM-generated tests external validity. |
| 5 | Sample size | 48 (12 per family) | Supports the 2×2 design. |
| 6 | Human verification rate | 25% (12 prompts) | Catches judge drift, fits in a week. Deterministic sampling rule with seed=2026 in `experiment/configs/verification_protocol.md`. |
| 7 | Cross-scale prompts | Solomon + Homberger | Cross-scale claim worth supporting. Homberger SCHEDULE asymmetry handled per Prompt set section. |
| 8 | Faithfulness rubric scale | 5-point with binary pass threshold ≥ 4 | Standard, defensible. Rubric at `experiment/configs/rubric.md`. |
| 9 | Operational validity tolerance | With-tolerance per family (OBJ 0.5%, SCHEDULE 1 minute, PV exact, STRUCT exact) | Strict exact-match fails too often on rounding. |
| 10 | Failure analysis depth | Quantitative + qualitative (3 successful + 3 failed per family) | Both pieces needed for the discussion section. |
| 11 | Headless invocation mode | `bare: false` everywhere (classifier / generator / judge) | Max-plan OAuth is the credentialed path; `--bare` would require `ANTHROPIC_API_KEY`. Reproducibility caveat (default system-prompt sections still load, but `--system-prompt-file` overrides them) documented in §1. |
| 12 | Classifier prompting style | Zero-shot | Few-shot iteration produced an isomorphic regression (STRUCT_SCHEDULE recovered, PV_SCHEDULE regressed to the same level); reverted. Documented STRUCT_SCHEDULE limitation auditable post-hoc via `prompts.csv` ground-truth labels. |

## Timeline

Two-week design + execution if running in parallel with thesis writing:

- **Days 1-3:** prompt set generation + pre-registration freeze
- **Days 4-5:** human pilot calibration (20 prompts dual-rated)
- **Days 6-8:** full LLM-as-judge run on all 48 prompts
- **Days 9-10:** human verification of 25% sample
- **Days 11-14:** analysis, write-up, discussion section integration

This sequencing assumes scoring goes smoothly. If the rubric needs revision after pilot (agreement < 0.7), add 3-5 days for iteration before scaling.

## Out of scope for this experiment

- Multi-turn dialogue (one-shot Q&A only)
- New claim families (locked taxonomy)
- New problem classes (Solomon-100 and Homberger-200 only)
- Production engineering (no API rate-limiting, no caching, no latency optimisation)
- Comparison against baselines that don't use the predictor (the predictor is locked as the deployment configuration)
- A/B test of different threshold settings (single threshold per family from `deployment_config.csv`)
- LLM fine-tuning (frontier LLM zero-/few-shot only)

## What this experiment gives the thesis

A complete pipeline demonstration that closes the loop:

- The methodology operates end-to-end on natural-language prompts
- The three-axis decomposition catches distinct failure modes (validates the conceptual contribution)
- The locked predictor's decisions surface as language-level outcomes (validates the systems contribution)
- The benchmark labels translate to deployable quality scores (validates the benchmark contribution)
- The interpretable predictor's behaviour can be examined per-prompt (validates the ML contribution)

In one experiment, every one of the five thesis contributions gets a piece of evidence it operates at the language layer the copilot framing implies. Examiners can no longer ask "where is the LLM?" because the LLM is in the pipeline, the three axes are measuring its output, and the predictor is gating its compute.
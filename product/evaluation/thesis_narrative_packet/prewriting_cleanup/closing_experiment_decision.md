# Closing Experiment Decision

_Authored 2026-05-21. Determines whether the Stage A closing experiment
(48 prompts, Haiku generator, Sonnet judge, faithfulness/sufficiency/op-validity)
remains a primary thesis experiment or is retired._

---

## 1. What the closing experiment was

The Stage A closing experiment (locked at `preregistration-v1.1`,
`preregistration-prompts-v1`, `full-run-v1`) evaluated:

- 48 operator-style prompts × 2 instances (Solomon-100, Homberger-200)
- Haiku 4.5 generator → free-form answer text
- Sonnet 4.6 judge → faithfulness (5-point rubric, ≥4 = pass), sufficiency
- Four pre-registered claims, 3-of-4 success rule
- Three-axis decomposition: faithfulness, sufficiency, operational validity

**Results (from `experiment/results_RUN1/analysis/`):**
- Claim 1 (axis separability): **PASS** (0.604 mixed rate)
- Claim 2 (policy effect): **FAIL** (|diff| = 0.143 < 0.20)
- Claim 3 (sufficiency manifests): **FAIL** (insufficient cells at ceiling)
- Claim 4 (cross-scale): **PASS** (Homberger drop ≤ 0.5 pts)

**3-of-4 rule: NOT MET** (2 PASS, 2 FAIL).

---

## 2. Is the thesis now centered on structured contract outputs?

**Yes.** The thesis's primary empirical contribution has shifted to structured
product-contract behavior:

- **Run 2** evaluates whether the copilot maps prompts to correct intent,
  answerability, evidence fields, warnings, behavior class, and compute
  decisions — all structured, not free-form.
- **System D / D-Final** evaluates whether a semantic adapter can canonicalize
  novel operator language into the contract's structured intent frame.
- The contract response object is the observable quantity; operator-visible
  answer text is a rendering layer downstream.

The Stage A closing experiment evaluated the rendering layer (Haiku answer
text, Sonnet faithfulness judge). Run 2 evaluates the contract layer.
These are different layers of the same system.

---

## 3. Recommendation: retire the closing experiment as a main experiment

**The old closing experiment should be RETIRED as a primary experiment.**
It should be reframed as a **pilot study** or **Stage A foundational work**
that motivates the shift to contract-layer evaluation.

Rationale:

1. **3-of-4 rule not met.** The experiment's own pre-registered success
   criterion was not satisfied. This is a genuine empirical finding (the
   generator was at ceiling; insufficient cells were not stressed enough to
   show the predicted policy effect). It should be reported as such, not
   as a primary claim.

2. **The bottleneck is the rendering layer, not what the thesis is now about.**
   The finding from Stage A is that the Haiku generator either refused
   correctly or answered from a legitimate sub-claim — the three-axis
   decomposition did not surface the predicted faithfulness-sufficiency
   divergence on insufficient cells. This is interesting, but the thesis's
   core argument has pivoted to "structured contract correctness," for which
   Run 2 is a cleaner instrument.

3. **Run 2 supersedes Stage A as the evaluation instrument.** Run 2
   evaluates contract behavior directly without a judge model, with
   interpretable component metrics (precision/recall), and with a pre-registered
   gold schema. The Stage A experiment required a Sonnet judge whose agreement
   with human raters was 91.67% within-tolerance (11/12) — adequate, but
   noisier than the deterministic contract-scoring approach.

4. **The Stage A results are still publishable, reframed.** The Stage A
   claim_evaluations.md notes: the three-axis decomposition validated at
   the language layer (Claim 1 PASS), the generator exceeded the complexity
   threshold (generator was at ceiling rather than stressed). This is a
   methodology finding: the three-axis decomposition is sound for separating
   axes; the closing-experiment generator was too capable for the insufficient
   cells to fail on faithfulness.

---

## 4. Where faithfulness still appears in the thesis

Faithfulness remains in the thesis in two contexts:

### 4.1 Stage A as a methods validation finding (retained)

> "Stage A showed that the three-axis decomposition can separate axis
> outcomes: 60.4% of prompts produced mixed patterns (Claim 1 pass, 6×
> the threshold). The policy-effect claim did not register because the
> Haiku generator was at ceiling — insufficient cells neither refused
> incorrectly nor hallucinated. This finding motivated the shift from
> evaluating rendered answer text to evaluating the structured contract
> response that produces it."

This framing lets Stage A contribute a positive methodological finding
(axis separation works) while honestly reporting the negative claim results
(policy effect and sufficiency signals did not emerge at the generator
ceiling).

### 4.2 Faithfulness as an upstream property of the contract

The Run 2 contract enforces **evidence precision** (the structured
analogue of faithfulness): the contract may only cite evidence fields the
payload actually contains. Evidence_precision = 0.980 in the C-extended
evaluation (60/60 cases). This is a structured faithfulness guarantee that
does not require a judge model.

The thesis can state: "Faithfulness at the structured level is enforced by
the contract's evidence-citation rules (98.0% precision on the 60-case
benchmark). Faithfulness at the rendering level, studied in Stage A's 48-
prompt pilot, was found to be ceiling-bound under Haiku 4.5: the generator
produced correctly-grounded answers even on cells predicted to stress it,
which limited our ability to test the policy-effect claim."

---

## 5. What a small verbalization-faithfulness check would look like (if needed)

If the committee or reviewers require evidence that the rendering layer
does not hallucinate, a small targeted check would be:

- **n**: 5–10 cases drawn from Run 2's `target_extension` set (the harder
  cases where the contract produces partial answers or refusals).
- **Generator**: a current-generation model (Claude 3.5 or GPT-4o) with
  the structured contract response as context.
- **Faithfulness check**: does the answer text ground only on the cited
  evidence fields in the contract response? Score by field-grounding, not
  free-form judge.
- **Purpose**: confirm the rendering step does not add hallucinated claims
  beyond what the contract cites.

This is a 1–2 day exercise, not a full experiment. It is a rendering-layer
sanity check, not a primary experiment.

---

## 6. Summary decision

| Item | Decision |
|---|---|
| Retire closing experiment as main experiment | **Yes** |
| Report closing experiment results in thesis | **Yes, reframed as Stage A pilot + negative result** |
| Primary evaluation instrument | **Run 2 structured contract benchmark** |
| Primary D-Final evaluation instrument | **Semantic holdout (47/48) + Run 2 regression check** |
| Faithfulness in thesis | **Structured: evidence_precision (98.0%). Rendering: Stage A pilot finding (ceiling-bound generator)** |
| Optional rendering check needed | **No — unless committee requires it** |

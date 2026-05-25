# What This Thesis Is Not

_Authored 2026-05-21. Clear boundary statements for dissertation writing and
defense. Each boundary is paired with one sentence describing what the thesis
does instead._

---

## 1. Not a productivity study

This thesis does not evaluate whether routing operators complete tasks faster
or make better decisions when using the copilot. It evaluates whether the
copilot contract emits answerability-aware, evidence-backed responses from
structured payloads — the prerequisite for productivity claims that would
require a separate user study.

---

## 2. Not a user study

This thesis does not measure operator satisfaction, task-completion rates,
error rates, or preference between system variants. It evaluates the
structured response object the copilot emits before any rendering layer
converts it into operator-visible text — the correctness of that response
object is a necessary (not sufficient) condition for user-facing quality.

---

## 3. Not a pure hallucination benchmark

This thesis does not measure whether the copilot's answer text contains
hallucinated content in the sense of LLM benchmarks (e.g. TruthfulQA, MMLU).
It measures whether the copilot's structured contract response cites evidence
fields that are actually present in the payload (`evidence_precision = 0.980`
on the 60-case benchmark) — a structured faithfulness guarantee at the
contract layer, not a probe of generative hallucination in the rendering layer.

---

## 4. Not a broad natural-language generalisation claim

This thesis does not claim that the copilot handles arbitrary operator
natural language. The Run 2 benchmark is a 60-case locked set authored
against known contract behaviors; the D-Final semantic holdout covers 5
semantic subtypes (48 novel paraphrases). The thesis claims that a semantic
adapter can handle unseen paraphrases within the space of intents the
contract already supports — not that the system generalises to arbitrary
queries outside that space.

---

## 5. Not a solver-optimality study

This thesis does not evaluate whether the VRPTW solver produces optimal or
near-optimal routes, whether the solver parameters are correctly calibrated,
or whether the backend planner outperforms competing algorithms. It evaluates
whether the copilot correctly reports what the solver produced — the accuracy
of the reporting layer, not the quality of the underlying solve.

---

## 6. Not a production recomputation system

This thesis does not ship a deployed system that operators can use to
recompute routes. The D4 compute-decision layer identifies when recomputation
is needed and what mode is appropriate, but does not execute solver calls,
manage job queues, or provide a production deployment. D4 is an evaluation of
the contract logic for recommending recomputation, not a deployment of the
recomputation itself.

---

## 7. Not a deployed learned sufficiency gate

The Stage A HistGB sufficiency predictor is a research prototype evaluated on
a controlled benchmark. It is not a deployed gate in a production routing
system. The thesis evaluates the predictor's accuracy on the pre-registered
48-prompt benchmark and its role in motivating the Run 2 product-contract
evaluation — not its production readiness or impact on actual dispatching
decisions.

---

## 8. Not proof that LLMs solve VRPTW

This thesis does not claim that LLMs can optimise vehicle routing, generate
valid routes, or replace OR-based solvers. The LLM in the D-Final semantic
adapter maps operator natural language to a validated query frame; it has no
access to route data, does not output route assignments, and cannot call the
solver. The copilot interprets and reports; the solver optimises.

---

## 9. Not a claim that deterministic contracts beat LLMs universally

The B→A→C reliability spectrum (pass^k_all: 0.30 → 0.50 → 1.00) shows
that the deterministic contract outperforms prompt-only LLM on structured
contract-correctness tasks with pre-specified gold. This is expected: the
contract was designed against the gold. The claim is that deterministic
contracts are the right tool for the correctness-critical layers
(answerability, evidence, warnings, behavior class) — not that LLMs are
generally worse than rule-based systems.

---

## 10. Not a replication of prior VRP literature

This thesis does not replicate or compare against prior VRP heuristic or
exact methods. The Solomon-100 and Homberger-200 instances are standard
benchmarks used to provide realistic payload conditions; the comparison of
interest is the copilot's contract correctness across payload conditions,
not the optimality of the solutions generated for those instances.

---

## Compact version (for abstract / introduction)

> This thesis studies the product-contract layer of an LLM-in-the-loop
> VRPTW copilot: whether the copilot can correctly identify operator intent,
> determine payload answerability, and emit evidence-backed responses. It is
> not a productivity study, user study, hallucination benchmark, broad
> language-generalisation claim, solver-optimality evaluation, production
> deployment, or proof that LLMs replace combinatorial optimisers.

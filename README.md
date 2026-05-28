# Routing Copilot

A controlled LLM copilot that lets a dispatcher interrogate a live vehicle-routing optimizer in plain English — and refuses to answer when the solver's state can't actually support an answer.

Think of it as **RAG, but the corpus is a live optimization backend's state** instead of documents — with one addition naive RAG doesn't have: a *sufficiency gate* that decides whether the retrieved state can answer the question at all, before anything gets generated. The LLM never writes the answer. It only translates the question. Everything that could be wrong — what's true, what's missing, whether to refuse — is owned by a deterministic contract.

![Architecture: the LLM proposes a query frame; a deterministic contract pipeline grounds, gates, and answers](docs/architecture.svg)

## What it does

A vehicle-routing solver produces a plan: who goes on which route, in what order, arriving when, at what cost, with which time-window violations. The output is a wall of structured state that an operations person can't easily read. The usual fix is to bolt an LLM on top so they can "just ask." The usual result is an LLM that confidently makes things up.

Routing Copilot is the architecture that fixes the second problem. An operator types a question. The LLM's *only* job is to map that question to a structured query frame — an intent plus the entities it refers to. It is forbidden, in code and enforced by validation, from writing the answer, deciding what's answerable, citing evidence, or choosing whether to recompute. A deterministic contract pipeline does all of that: it checks whether the solver state can support the question, pulls the exact fields that ground the answer, applies false-premise and ambiguity guards, and only then turns real fields into text.

## What it looks like in practice

It answers, with every claim traceable to a real solver field:

```
Q: "What am I looking at?"

intent:        scenario_summary
answerability: answerable
behavior:      direct_answer
answer:        "This scenario is instance C202, under a time-window perturbation...
                Tightened windows make on-time delivery harder. Objective 591.6."
evidence:      explanation_context.scenario_id        = "C202__TW_3"
               explanation_context.instance.instance_id = "C202"
```

And — this is the half people skip — it refuses instead of guessing:

```
Q: "If travel times got 10% worse, would we survive?"

intent:        unknown
answerability: not_answerable
behavior:      useful_refusal
answer:        "This question cannot be answered from the current payload."
next action:   "Narrow the question to a specific customer, route, or claim type,
                or pick a field from the available payload fields list."
```

The current solver snapshot has no perturbed-travel-time scenario, so the system says so and tells the operator what *would* let it answer. It doesn't invent a survival estimate.

## Why build it this way

A dispatcher acting on a hallucinated route summary is a real operational failure, not a bad chat experience. So the design goal isn't "sound helpful," it's "never state something the solver state doesn't support." Putting the LLM on a leash — propose, don't dispose — is what makes that guarantee hold while still getting the LLM's flexibility on the one thing it's good at: understanding a messy natural-language question.

## Does it actually work?

Yes, and the gains come from exactly where the design predicts.

On a 109-query operator corpus written to mirror how dispatchers actually ask things, turning the LLM adapter on lifts genuinely useful answers from **40% to 62%** over the deterministic-only baseline. On the 62 queries where the LLM changed the outcome, it **helped 24 and hurt 3** — the contract layer absorbs most of what the LLM gets wrong before it reaches the operator.

A separate 60-case benchmark shows the reliability gradient the architecture is built around. Pass@k (same query, k samples, all must succeed) climbs as control moves from the model to the contract:

| Configuration | pass@k |
|---|---|
| Prompt-only LLM | 0.30 |
| Hybrid (deterministic prior + LLM) | 0.50 |
| Contract-grounded | 1.00 |

*(k differs between rows — 5, 3, and by-construction respectively — so read the direction, not the exact gap.)*

**Where it's still weak, stated plainly.** Action-recommendation queries are near-useless (~0%) and risk/fragility questions land around 13%. Most of those failures are the intent classifier misrouting the question, not the contract grounding the wrong thing — which is a fixable front-end problem, and it's diagnosed case by case in the reports rather than averaged away. The honest per-category breakdown is in [`docs/`](docs/) and the evaluation reports under [`product/evaluation/reports/`](product/evaluation/reports/).

## What this project demonstrates

- **Making an opaque backend usable in the field.** Taking a powerful but unreadable system (a constraint solver) and giving a non-expert a safe way to interrogate it is the core of forward-deployed work. This is that, end to end.
- **Designing an LLM system that can't lie.** Grounding every claim in a real field and refusing rather than bluffing is a production-safety decision, made in the architecture instead of patched in the prompt.
- **Owning the whole stack.** A typed contract pipeline (~40k lines of Python), a FastAPI service, and a React operator UI with a route map and schedule view.
- **Measuring like someone who has to ship it.** Four ablations, pass@k stability, a pre-registered benchmark with locked file hashes, 1,176 tests, and negative results reported instead of buried.

## Repo map

| Path | What's here |
|---|---|
| [`product/`](product/) | The system. `api/` (FastAPI), `copilot/` (the contract pipeline: semantic adapter, sufficiency gate, refusal policy, verbalization), `data/` (payload projection, evidence, answerability), `evaluation/` (runners + reports). |
| [`frontend/`](frontend/) | React + Vite operator UI — copilot panel, route map, schedule, evidence panel. |
| [`docs/`](docs/) | Architecture diagram, reproducibility guide, threshold rationale. |
| [`tests/`](tests/) | 1,176 tests; the thesis-load-bearing ones are pinned. |
| `experiment/`, `instances/`, `logs/`, `src/` | Scenario data, solver instances, runtime telemetry, and the original Stage-A benchmark package. Load-bearing for the API and for reproducing results — *not* where the product logic lives. |
| [`research/`](research/) | Earlier experimental phases and engineering notes, kept for history. Nothing here is needed to run the system. |

## Run it locally

```bash
# Backend (Python 3.10+)
pip install -r requirements.txt
pip install -e .
cp .env.example .env          # add OPENAI_API_KEY for the LLM path
uvicorn product.api.app:app --reload

# Frontend (Node 18+)
cd frontend
npm install
npm run dev
```

Open the Vite URL and ask a question against any loaded scenario. The deterministic path (sufficiency gate, evidence, refusals) runs **without an API key**; the key is only needed for the LLM semantic adapter.

## Reproduce the evaluation

No setup, ~30 seconds — reads the frozen reports and prints the headline numbers:

```bash
python -m product.evaluation.verify_reports
python -m product.evaluation.verify_reports --per-category
```

Re-run the deterministic configuration bit-exact, or the LLM configurations (subject to ~±3pp model variance): see [`docs/reproducing_results.md`](docs/reproducing_results.md).

## Stack

Python · FastAPI · Pydantic · OpenAI API · PyVRP · React · TypeScript · Vite · Plotly · React Flow

## Origins

This began as the bachelor's thesis *Payload Contracts for LLM Copilots in Vehicle Routing* and is built to research-grade evaluation standards — pre-registration, locked benchmarks, ablations, and honest negative results. The thesis-facing reproduction details live in [`docs/reproducing_results.md`](docs/reproducing_results.md); the original thesis README is preserved at [`docs/README_thesis_original.md`](docs/README_thesis_original.md).

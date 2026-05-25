# Frontend — Stage 3 Product Inspector

A React + Vite + TypeScript single-page app that consumes the Stage 2
backend (`product/api`) and lets a thesis reader inspect Run 1 as a product
artifact: prompts, grounded answers, evidence, answerability, warnings,
useful refusals, and the augmented payload.

## How to run

Two terminals, from the repository root.

### Terminal 1 — backend

```
uvicorn product.api.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/healthz` → `{"status":"ok"}`.

### Terminal 2 — frontend

```
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to the
FastAPI server on port 8000, so all frontend calls use relative paths.

## Scripts

- `npm run dev` — Vite dev server
- `npm run build` — TypeScript build + Vite production bundle
- `npm run preview` — preview the production build
- `npm run typecheck` — `tsc --noEmit`

## What the Stage 3 frontend shows

- **Run 1 product metrics** — grouped by metric type (quality, compliance,
  probe, future user study). Includes:
  - `grounded_answer_accuracy`
  - `evidence_coverage`
  - `route_label_ambiguity_incidents`
  - `useful_refusal_rate`
  - `user_requested_unsupported_comparison_detection`
  - `volunteered_or_risky_comparison_guardrail_hits`
  - `route_indexing_warning_count`
  - `struct_membership_warning_count`
  - `convention_consistency`
  - `time_to_answer_reduction` (marked as not measured, requires task study)
- **Prompt table** with filters for family, source, quadrant, action,
  sufficiency, policy, faithfulness score, refusal status.
- **Selected prompt detail** — metadata, user question, generator answer,
  intent, answerability badge, faithfulness, metric flags, suggested next
  actions.
- **Evidence panel** — evidence items, missing fields, useful refusal
  with available subclaims and next actions, visual-action hints rendered
  as text.
- **Warning panel** — human-readable explanation for each warning code
  (`route_indexing_ambiguity`, `struct_membership_ambiguity`,
  `unsupported_comparison`, `missing_new_customer_attribution`).
- **Known-issue banner** — short note for selected prompts that exercise
  product-layer behavior (002, 010, 025, 029, 031–036, 040, 041).
- **Payload inspector** — top-level fields, route preview table
  (`route_idx` → `display_route_number` → `route_label`), counts for
  schedule and route-end-time arrays, full JSON in a `<details>` block.
- **Domain cards** — `ObjectiveCard`, `FeasibilityCard`, `RouteTableCard`,
  `ScheduleCard` (with highlighted-customer emphasis driven by
  visual actions).

## Stage 4 — visual grounding

Stage 4 adds spatial visualisation backed by a backend ``visual-context``
endpoint that combines the Stage 2 product contract with instance
geometry, route polylines, and perturbation context. The frontend
renders that object; it does not invent route or evidence logic.

- **PerturbationPanel** — perturbation_id / family, short human-readable
  summary with magnitude, known fields, missing fields, and any
  prompt-level limitations (e.g. unsupported comparison, missing
  ``new_customer_ids``).
- **RouteMap** — Plotly coordinate-plane plot with depot square, customer
  scatter, all route polylines, and a highlighted overlay for any
  highlighted customer(s) and route(s) implied by the Stage 2
  evidence. Solomon/Homberger coordinates are synthetic Euclidean (not
  geographic); the title makes that explicit.
- **RouteSequence** — Depot → C42 → C15 → … → Depot for the highlighted
  route(s). When a SCHEDULE payload is present, arrival / start_service
  appear in the node subtitle.

## What it does NOT yet show

- Live model calls.
- Solver re-runs.
- Before/after baseline-vs-perturbed diff render (the backend reports
  "Baseline/diff payload unavailable" for the four 033-class prompts).
- React Flow route diagram (Stage 4 uses a simple horizontal sequence
  for now; React Flow remains an option for a later stage).
- User task-study event logging.

## Key prompts to inspect

| prompt | what to look for |
| --- | --- |
| 001 | Clean OBJ answer; ObjectiveCard populated. |
| 002 | Volunteered/risky comparison guardrail (probe). |
| 010 | Volunteered/risky comparison guardrail (probe). |
| 025 | Missing `new_customer_ids`; useful refusal. |
| 029 | STRUCT membership + route convention drift. |
| 033 | Unsupported before/after comparison; useful refusal. |
| 040 | Route-indexing convention; route-end-time evidence. |
| 046 | Customer-arrival evidence; ScheduleCard highlights customer 42. |

## API endpoints consumed

- `GET /api/healthz`
- `GET /api/runs/{run_id}/results`
- `GET /api/runs/{run_id}/product-metrics`
- `GET /api/prompts/{prompt_id}`
- `GET /api/prompts/{prompt_id}/copilot-context`
- `GET /api/prompts/{prompt_id}/evidence`
- `GET /api/prompts/{prompt_id}/answerability`
- `GET /api/prompts/{prompt_id}/visual-context` *(Stage 4)*
- `GET /api/prompts/{prompt_id}/perturbation-context` *(Stage 4)*
- `GET /api/instances/{instance_id}/geometry` *(Stage 4)*

All call signatures live in `src/api/client.ts`. Types live in
`src/types.ts` and mirror the Stage 2 backend contract.

## Component structure

```
src/
├── api/client.ts            typed fetch wrappers
├── types.ts                 Stage 2 contract mirror
├── App.tsx                  shell, state, layout
├── index.css                styling
└── components/
    ├── ProductMetricsPanel.tsx
    ├── Sidebar.tsx
    ├── ResultsTable.tsx
    ├── PromptDetail.tsx
    ├── EvidencePanel.tsx
    ├── WarningPanel.tsx
    ├── KnownIssueBanner.tsx
    ├── PayloadInspector.tsx
    ├── DomainCards.tsx
    ├── RouteMap.tsx          Plotly coordinate-plane route map (Stage 4)
    ├── RouteSequence.tsx     Depot → customers → depot horizontal flow (Stage 4)
    └── PerturbationPanel.tsx Perturbation summary + limitations (Stage 4)
```

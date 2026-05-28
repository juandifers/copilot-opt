# VRPTW Copilot Dashboard

A read-only inspector for Run 1 of the VRPTW copilot closing experiment,
served as a FastAPI backend and a React frontend.

The dashboard turns the locked Run 1 artifacts into an interactive product
surface so a reader can browse the 48 prompts, inspect each grounded answer,
see which payload fields supported (or failed to support) the answer, and —
once the visualization stages land — see routes and schedules rendered
spatially and as sequence diagrams.

## What it does

- Loads the joined Run 1 results and the per-prompt generator / judge JSONL.
- Lets you filter prompts by family, source, quadrant, action, sufficiency,
  policy decision, faithfulness score, op-validity, and refusal status.
- Lets you select a prompt and see the operator question, the generator
  answer, the judge rationale, the deterministic op-validity check, and the
  payload snapshot the generator saw.
- Flags known product-level issues surfaced by Run 1 (route-label ambiguity,
  STRUCT membership semantics, missing before/after payloads).

## What it does not do (Phase 1)

- It does not call any model.
- It does not re-run any solver. PyVRP is not required to run the dashboard.
- It does not modify any locked experiment configuration or result file.
- It does not regenerate payloads from scratch — it reads what Run 1 stored.

## Architecture

```
product/         Pure-Python backend package
  data/          Loaders, evidence extraction, product schema helpers
  api/           FastAPI app — thin layer over product.data
frontend/        React + Vite + TypeScript app
  src/           Components, typed API client, visualization panels
dashboard/       Product-level docs and dependency manifest (this directory)
```

Frontend visualization uses **Plotly** (`react-plotly.js`) for spatial route
maps and **React Flow** for route-as-sequence diagrams. Solomon VRPTW
coordinates are a synthetic Euclidean grid, not geographic, so no map-tile
library is included.

## Run 1 artifacts consumed

All paths are relative to the repository root.

- `experiment/results/joined/full-run-v1.csv` — denormalized 48-row table.
- `experiment/results/generator/full-run-v1.jsonl` — generator outputs.
- `experiment/results/judge/full-run-v1.jsonl` — judge outputs.
- `experiment/data/prompts.csv` — locked prompt metadata index.

The dashboard does not write to any of these files.

## Install

From the repository root:

### Backend

```
python3 -m venv .venv-dashboard
source .venv-dashboard/bin/activate
pip install -r dashboard/requirements-dashboard.txt
```

### Frontend

```
cd frontend
npm install
cd ..
```

## Run

Open two terminals from the repository root.

### Terminal 1 — backend

```
source .venv-dashboard/bin/activate
uvicorn product.api.main:app --reload --port 8000
```

Verify with `curl http://localhost:8000/healthz` — expect `{"status":"ok"}`.

### Terminal 2 — frontend

```
cd frontend
npm run dev
```

Open `http://localhost:5173` in a browser. The Vite dev server proxies
`/api/*` to the FastAPI backend, so the frontend code calls relative paths
only.

In Stage 0 the frontend renders a single page showing backend connection
status; Stages 1–7 add the inspector UI.

## Scope

This is a product prototype layered on top of a preregistered experiment.
The experiment itself (configs, locked prompts, locked results) is
immutable. Anything the dashboard surfaces about Run 1 is read-through; any
product fixes the dashboard suggests (e.g. `route_label`,
`display_route_number`, baseline / diff payloads) are described as gaps and
not yet implemented in the payload builder.

## Stage 4 — visual grounding

Stage 4 adds three product surfaces on top of the Stage 2 contract:

- **Instance geometry** (`/instances/{id}/geometry`): reads the original
  Solomon / Homberger ``.vrp`` file via the existing
  ``vrp_copilot_bench.vrptw_instances.load_vrptw_instance`` parser and
  returns depot + per-customer coordinates / time windows / demand /
  service time. The coordinates are **synthetic Euclidean**, not
  geographic, which is why the dashboard uses Plotly (coordinate plane)
  and intentionally does not introduce Leaflet.
- **Visual context** (`/prompts/{prompt_id}/visual-context`): combines
  the Stage 2 ``ProductCopilotResponse`` with instance geometry, route
  polylines (derived from the augmented payload's ``routes`` or, for
  SCHEDULE-only payloads, by grouping ``customer_schedule`` by
  ``route_idx``), highlighted customers / routes drawn from
  ``visual_actions``, and a ``limitations`` list that surfaces unsupported
  before/after comparison and missing-new-customer-id cases instead of
  silently degrading.
- **Perturbation context** (`/prompts/{prompt_id}/perturbation-context`):
  per-family human-readable summary with magnitude phrasing
  (``+50% multiplier``, ``new window width ≈ 10%`` etc.), plus an
  explicit ``missing_fields`` list for things Run 1 did not record per
  prompt (e.g. inserted customer IDs, per-customer original/new TWs).

The frontend renders these via three new components:

- **RouteMap** (Plotly) — depot, customer scatter, all route polylines,
  with a highlighted overlay (star marker + thicker line) for the
  customers / routes the Stage 2 evidence implies.
- **RouteSequence** — Depot → C42 → C15 → … → Depot for the highlighted
  route(s), with arrival / service start times in the node subtitle
  when a SCHEDULE payload is present.
- **PerturbationPanel** — perturbation_id, family, human-readable
  summary, known fields, missing fields, and the visual context's
  limitations block.

Key prompt demos:

- **029** STRUCT membership — customer 42 is highlighted on Route 5
  (route_idx=4); route sequence shows the depot → 42 → 15 → … → depot
  ordering with the route_idx vs display convention visible.
- **033** unsupported comparison — limitation explains baseline/diff is
  unavailable and the map shows the current routes without pretending a
  before/after diff exists.
- **040** route-indexing convention — Route 1 (display) corresponds to
  route_idx=0; ``route_indexing_ambiguity`` warning + map highlight make
  this concrete.
- **046** customer arrival — schedule fallback derives 9 route polylines
  from ``customer_schedule``; customer 42 highlighted on Route 7; route
  sequence includes arrival times.

### Stage 4 dependency

`product/data/instance_geom.py` uses ``vrplib`` to parse the original
.vrp files. The dashboard requirements file lists it. Install with:

```
pip install -r dashboard/requirements-dashboard.txt
```

### Stage 4 backend tests

```
pytest tests/test_instance_geom.py tests/test_visual_context.py tests/test_perturbation_context.py
```

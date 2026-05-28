# Payload Contracts for LLM Copilots in Vehicle Routing

This repository contains the codebase for the bachelor's thesis *Payload Contracts for LLM Copilots in Vehicle Routing*. The thesis defends a payload-contract architecture for grounded copilots over Vehicle Routing Problem with Time Windows (VRPTW) solver state, evaluated in two phases: a 60-case product-contract benchmark (Run 2) and a 109-query operator-persona corpus organized by cognitive operation.

## What's in this repository

```
.
├── product/                    The thesis system (API + copilot + evaluation)
│   ├── api/                    FastAPI backend
│   ├── copilot/                Semantic adapter, contract layers, threshold layer, verbalization
│   ├── data/                   Payload projection, evidence resolution, answerability
│   └── evaluation/             Run 2 + operator-persona evaluation runners and reports
├── frontend/                   React + Vite operator UI
├── docs/                       Threshold rationale and pilot runbook
├── tests/                      Unit and integration tests
├── logs/                       Runtime telemetry (variance panel, copilot logs)
├── src/vrp_copilot_bench/      Earlier Stage A benchmark package (imported by tests)
├── experiment/                 Test fixtures from Run 1 (preserved for test_run2_payloads.py)
├── archive/                    Earlier experimental phases and engineering logs (preserved for history; not part of the thesis-facing system)
├── pyproject.toml
└── requirements.txt
```

The thesis-facing system lives under `product/` and `frontend/`. Everything in `archive/` is preserved for history and does not need to be installed or run for the thesis-facing system to work.

## Installation

```bash
# Python (3.10+)
pip install -r requirements.txt
pip install -e .

# Environment variables
cp .env.example .env
# Edit .env and fill in OPENAI_API_KEY (required for LLM-on configurations).
# The deterministic path (Tier 2) and report verification (Tier 1) work without it.

# Frontend (Node 18+)
cd frontend
npm install
```

## Running the system

Start the API:

```bash
uvicorn product.api.app:app --reload
```

Start the frontend (in another terminal):

```bash
cd frontend
npm run dev
```

The frontend connects to the API on the default Vite port. Open the Vite URL and issue an operator query against any loaded scenario.

## Reproducing the thesis results

### Run 2 benchmark (Sections 4.1–4.5)

The 60-case product-contract benchmark uses the deterministic reference at `product/evaluation/system_d_final/d_final_system_c.py` and the LLM-on path through `product/copilot/llm_semantic_intent_adapter.py`. The locked benchmark cases are at `product/evaluation/run2_benchmark_cases.csv`. Pre-computed Run 2 outputs are at `product/evaluation/reports/run2_*` (CSV and Markdown reports).

### Operator-persona evaluation (Sections 4.6–4.7)

The 109-query corpus is at `product/evaluation/operator_persona_cases.jsonl`. The runner is at `product/evaluation/operator_persona_runner.py`. The four ablation configurations cited in the thesis are pre-computed in:

- `product/evaluation/reports/ablation_v1_full/` — full architecture
- `product/evaluation/reports/ablation_v2_no_retry/` — retry layer disabled
- `product/evaluation/reports/ablation_v3_no_alternatives/` — structured ranking-disambiguation disabled
- `product/evaluation/reports/ablation_v4_llm_off/` — LLM semantic adapter disabled (deterministic dispatch only)

Each report directory contains:
- `operator_persona_responses.jsonl` — every response the system produced
- `operator_persona_results.csv` — per-query scoring
- `operator_persona_strict_rebucket.csv` — strict re-bucketer output (the locked scorer)
- `operator_persona_summary.json` — headline numbers
- `strict_rebucket_summary.txt` — strict-useful percentages by category

The variance panel data referenced in Section 3.9.3 is at `logs/variance_panel.jsonl`.

### Threshold rationale

The per-family threshold values used by the evaluation verdict layer (Section 3.9.1) are documented at `docs/threshold_rationale.md`. The implementation is at `product/copilot/thresholds.py`.

## Tests

```bash
pytest tests/product_api/ tests/product_copilot/ tests/system_d_final/ tests/test_evaluation.py tests/test_llm_adapter.py
```

These are the tests load-bearing for the thesis. Other tests in `tests/` cover the earlier Stage A benchmark code (`src/vrp_copilot_bench/`); they are preserved but their input data lives under `archive/stage-a-data/`, so some will skip or fail in this checkout.

## Reproducibility

The thesis results are reproducible in three tiers, detailed in [docs/reproducing_results.md](docs/reproducing_results.md):

1. **Verify the pre-computed reports** (no setup, 30 seconds):

   ```bash
   python -m product.evaluation.verify_reports
   ```

2. **Re-run the deterministic configuration** (bit-exact):

   ```bash
   python -m product.evaluation.operator_persona_runner --config v4_llm_off
   ```

3. **Re-run the LLM-on configurations** (subject to ~±3 pp LLM variance): see the guide.

File-level integrity hashes for the canonical reports are recorded in [docs/canonical_hashes.txt](docs/canonical_hashes.txt). The exact dependency versions used for the canonical runs are in [requirements-frozen.txt](requirements-frozen.txt).

## Earlier work

The `archive/` directory preserves earlier experimental phases for history. See `archive/README.md` for a guide. None of this is required for the thesis-facing system to run.

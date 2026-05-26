# Reproducing the thesis results

This document describes how to verify or reproduce the headline numbers cited in the thesis. It is organized in three tiers, from cheapest to most expensive.

## Reproducibility tiers

**Tier 1: Verify the pre-computed reports.** The pre-computed report files in `product/evaluation/reports/ablation_v{1..4}*/` are the canonical record of the runs the thesis tables cite. A reviewer can confirm the thesis matches the data without re-running anything.

**Tier 2: Re-run the deterministic path.** The LLM-off configuration runs no LLM and depends only on the deterministic dispatch code over a fixed solver state. It is bit-exact reproducible.

**Tier 3: Re-run the LLM-on path.** The LLM-on configurations are subject to the LLM intent-instability documented in Section 3.9.3 of the thesis (15.6% on the full corpus, 20% on the variance panel). Re-running produces numbers within roughly ±3 percentage points of the canonical, not bit-exact equality.

## Tier 1: Verify the pre-computed reports

The fastest way to confirm the thesis numbers match the data files.

```bash
python -m product.evaluation.verify_reports
```

Expected output (abridged):

```
Operator-persona — Full architecture
  combined strict-useful: 56.1%
  LLM-on strict-useful:   61.5%
  LLM-off strict-useful:  39.8%

Operator-persona — Retry disabled
  combined strict-useful: 56.7%
  ...

Operator-persona — Disambiguation disabled
  combined strict-useful: 57.1%
  ...

Operator-persona — LLM disabled (deterministic only)
  combined strict-useful: 39.8%
  ...
```

For per-category strict-useful (Table 10 in the thesis):

```bash
python -m product.evaluation.verify_reports --per-category
```

For file-level integrity (confirms the data files have not been modified since submission):

```bash
python -m product.evaluation.verify_reports --checksums
```

The expected hashes are recorded in `docs/canonical_hashes.txt`. Compare against this file.

## Tier 2: Re-run the deterministic path

The LLM-off configuration is bit-exact reproducible because it runs no LLM.

```bash
python -m product.evaluation.operator_persona_runner \
  --config v4_llm_off \
  --output-dir /tmp/repro_v4
```

To verify bit-exact equality with the canonical run:

```bash
diff product/evaluation/reports/ablation_v4_llm_off/operator_persona_responses.jsonl \
     /tmp/repro_v4/operator_persona_responses.jsonl
```

No diff output indicates exact match. Any diff is unexpected and indicates a regression in the deterministic dispatch.

## Tier 3: Re-run the LLM-on path

The LLM-on configurations depend on the OpenAI API and are subject to LLM session variance.

### LLM environment lock

The runs reported in the thesis used:

- OpenAI model: `gpt-5.4-mini` (pinned snapshot: `gpt-5.4-mini-2026-03-17`)
- Temperature: `0` (treated as "use model default" by the OpenAI API)
- `max_completion_tokens`: `2048`
- `response_format`: `{"type": "json_object"}`
- Retry policy: `max_retries=2`, linear backoff `2s × attempt`
- SDK: `openai>=1.40.0` (canonical run used `openai==2.29.0`)

The model is configured in `product/copilot/llm_semantic_intent_adapter.py` (constant `_LLM_MODEL`). API credentials are loaded from `OPENAI_API_KEY` in the environment:

```bash
cp .env.example .env
# Edit .env and fill in your OpenAI API key
```

### Running each configuration

```bash
# Full architecture
python -m product.evaluation.operator_persona_runner --config v1_full --output-dir /tmp/repro_v1

# Retry disabled
python -m product.evaluation.operator_persona_runner --config v2_no_retry --output-dir /tmp/repro_v2

# Ranking disambiguation disabled
python -m product.evaluation.operator_persona_runner --config v3_no_alternatives --output-dir /tmp/repro_v3
```

### Expected variance envelope

For each LLM-on configuration, the combined strict-useful from a fresh run should fall within:

| Configuration | Canonical | Expected envelope |
|---|---|---|
| Full architecture | 56.1% | 53–59% |
| Retry disabled | 56.7% | 54–60% |
| Disambiguation disabled | 57.1% | 54–60% |

A run outside this envelope is suspicious — check the LLM model version and API settings against the lock above.

### Variance panel reproduction

To reproduce the 15.6% / 20% variance figures:

```bash
python -m product.evaluation.variance_panel --runs 5
```

This runs the 20-prompt variance panel five times under the full architecture and computes intent-instability across runs. Expected: 15–20% intent-unstable (matching the canonical `logs/variance_panel.jsonl`).

## Environment

The Python environment used for the canonical runs is captured in `requirements-frozen.txt`. To recreate it exactly:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements-frozen.txt
pip install -e .
```

Python 3.10+ is required. Major dependencies: `openai`, `pyvrp>=0.9`, `pandas>=2.0`, `numpy>=1.24`, `pydantic`, `fastapi`, `uvicorn`.

## Known sources of variance

- **LLM intent classification.** The dominant source. Documented at 15.6% on the full corpus.
- **OpenAI model updates.** A model silently updated by OpenAI will produce different outputs. The model lock above pins the version used.
- **Network timeouts.** Rare; the retry layer is intended to handle these in the V1 configuration.
- **PyVRP determinism.** Given a fixed seed, PyVRP is deterministic. Seeds are documented in `product/evaluation/run2_payloads.py`.

## Troubleshooting

- **`verify_reports.py` matches the JSON summaries but re-running produces different numbers.** Expected behavior for LLM-on configurations. Compare against the variance envelope above.
- **Tier 2 byte-identical comparison fails.** A regression in the deterministic dispatch. Run `git log -p product/copilot/` to see if deterministic code changed since the canonical run.
- **`verify_reports.py` cannot find a report file.** Confirm the file paths in `product/evaluation/reports/ablation_v{1..4}*/`. If files are missing, the cleanup may have unintentionally moved something.

# Reproducing the closing experiment

This experiment has two execution backends. The canonical run uses Claude Code
(Max-plan OAuth); external reviewers should use the API backend, which produces
equivalent results without requiring a Max subscription. Equivalence is
documented in `experiment/results/equivalence/smoke-equiv-v1.md`.

## Prerequisites

- Python 3.11+
- An Anthropic API key with access to `claude-haiku-4-5` and `claude-sonnet-4-6`
- ~$10 USD of API budget for a full reproduction (smoke + calibration + full run + judge)
- git

## Setup

```bash
git clone <repo-url>
cd copilot-opt
git checkout preregistration-prompts-v1  # The locked prompt set
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Verify your environment matches

```bash
python experiment/src/smoke_test.py --backend api --run-id smoke-repro-v1
```

Expected: 4/4 faithfulness=5, op_validity_pass on all gradable prompts, no
failure modes triggered. Compare output to
`experiment/results/joined/smoke-v1.csv` (the canonical Claude Code smoke) —
faithfulness should agree on all 4 prompts.

## Full reproduction

```bash
python experiment/src/run_experiment.py --backend api \
       --run-id full-run-repro-v1 --prompt-ids all
```

Outputs land at `experiment/results/joined/full-run-repro-v1.csv`. Compare to
the original `full-run-v1.csv` (also in this repo if a Claude Code run was
committed) using:

```bash
python experiment/src/compare_runs.py \
       experiment/results/joined/full-run-v1.csv \
       experiment/results/joined/full-run-repro-v1.csv
```

The `compare_runs.py` script reports per-prompt agreement on faithfulness,
op_validity, and structured fields. Disagreements are expected at rates
documented in the equivalence report.

## What can differ between backends

- **Latency**: API backend is typically faster (~10-20s per prompt vs ~40s for
  Claude Code with its preamble loading).
- **Cost**: ~$10 for API full run vs subscription-included for Max.
- **Exact answer_text wording**: The model is non-deterministic in word choice
  even at temperature=0; semantic content should agree.
- **claude-code-specific fields**: `command_line`, `session_id`,
  `claude_duration_ms`, `total_cost_usd` will be null in API results.

## What must agree

- `op_validity_pass` (deterministic check; binary)
- Family classifier predictions (exact)
- `faithfulness_score` within ±1 (judge-mediated; small noise expected)
- `model_version` prefix (`claude-haiku-4-5` for generator,
  `claude-sonnet-4-6` for judge)

Disagreements outside these ranges should be reported as issues; the
equivalence claim is built on the smoke + calibration paired data and may not
hold for new prompt patterns.

## Locked files (do not modify)

The following files are integrity-verified at run start against git tags:

| File | Tag |
|---|---|
| `spec.md` | `spec-v1.1` |
| `experiment/configs/*` | `preregistration-v1.1` |
| `experiment/data/prompts.csv` | `preregistration-prompts-v1` |
| `experiment/data/cell_selection.csv` | `preregistration-prompts-v1` |

Any modification to these files will cause the run to halt at preflight.
To reproduce with a known-good state:

```bash
git stash
git checkout preregistration-v1.1 -- experiment/configs/
git checkout preregistration-prompts-v1 -- experiment/data/
```

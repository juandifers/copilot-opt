# CLAUDE.md

You are operating in the closing experiment workspace for a PhD thesis on
optimization copilots. This file orients you to the project structure and
the operational disciplines this repo uses.

## What this project is

A benchmark and closing experiment for an LLM-in-the-loop VRP copilot. The
thesis tests four claim families (OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE)
under a three-axis decomposition (faithfulness, sufficiency, operational
validity). The closing experiment validates the methodology end-to-end
against operator-style natural language prompts.

Authoritative documents:
- `spec.md` (repo root, at tag spec-v1.1) — the experimental design
- `experiment/ARCHITECTURE.md` — system structure and rationale
- `experiment/AMENDMENTS.md` — log of locked-config amendments

## Pre-registration tags (immutable)

Three tag chains anchor the design. Do NOT modify files at these tags
without explicit user instruction:

- `spec-v1.1` — experimental design
- `preregistration-v1` → `preregistration-v1.1` — operational configurations
- `preregistration-prompts-v1` — locked 48-prompt set + cell selection

Latest run-script commit: 79f0706 (smoke verified, 4/4 clean).

## Operational constraints

- **Locked configs**: Files under `experiment/configs/` and `experiment/data/`
  are integrity-verified at run start via git blob SHA. Do not edit without
  an explicit amendment instruction.
- **Halt semantics**: The runner writes `halt_report.md` and exits non-zero
  on any assertion failure. Do not silence or bypass halt conditions.
- **Idempotency**: A run halts at preflight if output files already exist.
  Delete or rename the output directory before re-running.
- **bare: false**: The `--bare` flag is forbidden in claude-code invocations.
  Removing it would break Max-plan OAuth.

## Backends

Two execution backends share the locked configs:

- **Claude Code** (default): subprocess `claude -p` via Max OAuth.
  Loads local context; `bare: false` constraint applies. Used for
  Juan's canonical runs because Max plan absorbs the cost.
- **API** (reproducibility): Anthropic SDK direct calls. Stateless;
  no local context. Used for external reproduction. Requires
  `ANTHROPIC_API_KEY` env var.

Both produce equivalent results within documented tolerances
(see `experiment/results/equivalence/smoke-equiv-v1.md` and
`experiment/REPRODUCING.md`). The model versions, system prompts,
schemas, and rubric are identical; only the transport differs.

Run script selects via `--backend {claude-code,api}` flag.

## Repository layout

```
/Users/jd/Documents/copilot-opt/
├── spec.md                  # Pre-registered experimental design
├── CLAUDE.md                # This file
├── requirements.txt         # Python deps for experiment (anthropic SDK etc.)
├── experiment/
│   ├── REPRODUCING.md       # External reviewer reproduction guide
│   ├── ARCHITECTURE.md      # System design rationale
│   ├── AMENDMENTS.md        # Locked-config amendment log
│   ├── configs/             # LOCKED at preregistration-v1.1
│   ├── data/                # LOCKED at preregistration-prompts-v1
│   ├── src/                 # Operational code (mutable; commits logged)
│   │   ├── backends/        # Transport abstraction (claude-code + api)
│   │   │   ├── __init__.py  # get_backend(name)
│   │   │   ├── base.py      # ModelBackend, ModelResponse, HaltError
│   │   │   ├── claude_code.py
│   │   │   └── api.py
│   │   ├── run_experiment.py
│   │   ├── smoke_test.py
│   │   ├── equivalence_smoke.py
│   │   └── compare_runs.py
│   ├── results/<run_id>/    # Per-run outputs (append-only, immutable)
│   ├── pilot/               # Iteration evidence (append-only)
│   ├── discovery/           # Discovery audit (append-only)
│   └── logs/                # Per-call API logs (append-only)
└── src/                     # Broader project code (Stage A scaffolding)
```

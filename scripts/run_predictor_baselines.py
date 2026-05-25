#!/usr/bin/env python3
"""Run the baseline policy suite on Stage A artifacts.

Convenience wrapper around :mod:`vrp_copilot_bench.predictor_baselines.runner`.
Run from the repo root::

    python scripts/run_predictor_baselines.py \
        --long-parquet data/stage_a_vrptw_consolidated_claim_rows.parquet \
        --output-dir   reports/predictor_baselines
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vrp_copilot_bench.predictor_baselines.runner import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

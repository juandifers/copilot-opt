#!/usr/bin/env python3
"""Top-level entrypoint for Stage A.

Thin wrapper around :func:`vrp_copilot_bench.cli.main`. Run as::

    python scripts/run_stage_a.py [args...]
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running the script directly without an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

"""Re-runs Experiments 1-3, regenerates plots/tables, and rewrites the summary.

Idempotent: every invocation rebuilds artifacts/ from the union of prior
solution sources plus whatever rows are in
``data/processed/phase3/pyvrp60s_reference.jsonl`` at this moment.

Use this after ``compute_references.py`` finishes, or at any later point
when prior phases' artifacts change.
"""
from __future__ import annotations

import logging
import sys

from experiments.phase3_information_sufficiency import run_experiments, make_plots, write_summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rc1 = run_experiments.main()
    if rc1 != 0:
        return rc1
    rc2 = make_plots.main()
    if rc2 != 0:
        return rc2
    return write_summary.main()


if __name__ == "__main__":
    sys.exit(main())

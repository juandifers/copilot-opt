"""Homberger-200 methodology probe — Stage B-ish scope.

The probe evaluates whether Stage A's design (three-axis decomposition,
claim-family taxonomy, 5-rung ladder, reference-anchored sufficiency)
produces sensible results when the problem class scales from Solomon-100
to Homberger-200. The Stage A predictors are scored *zero-shot* on the
Homberger cells as a secondary output — the methodology evaluation is
the primary output.

This package only does analysis on top of an already-collected Homberger
wide/long parquet pair. Data collection happens via the existing
``scripts/run_stage_a_vrptw.py`` driver pointed at the Homberger roster
and instance directory.
"""

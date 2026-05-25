"""Integration harness for the learned sufficiency gate.

This package contains a synthetic evaluation harness that drives the
gate via the deterministic D4 pipeline and reports:

* gate invocation count
* abstain (no_decision) count
* accept_current count
* recommend_recompute count
* overrides blocked by hard contract logic
* unsafe override count (expected 0)
* ``pyvrp_60s`` recommendation count (expected 0)
* D4 / D5 / D-Final regression deltas
"""

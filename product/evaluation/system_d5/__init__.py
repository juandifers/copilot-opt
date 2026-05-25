"""System D5 — Operator-Authorized Recompute Execution.

D4 *recommends* compute. D5 *executes* compute. Execution only happens
when the explicit ``POST /scenarios/{scenario_id}/recompute`` endpoint
receives a confirmed, validated request matching D4's recommendation.

D5 has no evaluation harness of its own — the contract layer for the
recompute pipeline is the FastAPI endpoint, tested under
``tests/product_api/test_recompute_api.py``. This package exists to
host the design document, closeout, and follow-up reports.
"""

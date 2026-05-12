"""Solver wrappers and shared cost utilities.

The two modules here are the only places that depend on PyVRP. All other
package code consumes the abstractions defined in this subpackage:

- :mod:`marginal_costs` — per-customer removal-cost computation. Pure
  Python; no PyVRP dependency. Reused by action wrappers and by the
  baseline computation pipeline.
- :mod:`pyvrp_wrapper` — converts an :class:`~vrp_copilot_bench.instances.Instance`
  to a PyVRP ``ProblemData``, runs PyVRP, and returns a :class:`SolveResult`.
"""

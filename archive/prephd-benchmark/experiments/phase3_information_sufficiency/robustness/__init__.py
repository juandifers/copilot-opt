"""Phase 3 robustness pass.

Existing Phase 3 outputs in ``experiments/phase3_information_sufficiency/artifacts/``
are NOT modified by this package. New outputs land under
``artifacts/robustness/`` and the narrative goes to
``PHASE3_ROBUSTNESS_SUMMARY.md`` at the Phase 3 root.

Six sections:

1. ``feasibility_split``      — split reuse_direct results by
   ``feasible_under_perturbation``.
2. ``feasibility_penalty``    — λ curves with three penalty variants for
   infeasible reuse_direct (penalty=1.0, penalty=0.5, mark unanswerable).
3. ``distance_only``          — clean regional-distance subset analysis.
4. ``capacity_only``          — capacity-reduction subset with
   feasibility-aware breakdown.
5. ``tie_audit``              — λ=0 tie-breaking audit (which actions tie
   pyvrp_60s, and how the tie-breaking rule resolves them).
6. ``write_summary``          — narrative.
"""

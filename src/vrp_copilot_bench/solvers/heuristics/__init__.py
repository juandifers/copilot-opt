"""Construction heuristics package.

Two construction heuristics consumed by the Stage A action wrappers:

- :mod:`.nearest_neighbor` — greedy NN construction.
- :mod:`.clarke_wright` — parallel CW savings.

Both expose a ``construct(perturbed, distance_matrix) -> list[list[int]]``
function. They take the perturbed distance matrix as an argument (rather
than rebuilding it) so that *construction* and *evaluation* use the same
matrix — this is the load-bearing correctness guarantee for DISTANCE
perturbations described in :mod:`vrp_copilot_bench.actions.evaluate`.

Both heuristics raise :class:`vrp_copilot_bench.actions.ActionFailure`
when a single customer's demand exceeds vehicle capacity (the only
construction-failure mode in this benchmark; capacity is the sole
feasibility constraint).
"""

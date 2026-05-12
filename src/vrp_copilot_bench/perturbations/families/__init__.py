"""Family-specific perturbation realizations.

Each family module exposes a single ``apply_<family>`` function:

- :func:`capacity.apply_capacity` (prereg §6.1)
- :func:`distance.apply_distance` (prereg §6.2)
- :func:`demand.apply_demand` (prereg §6.3)
- :func:`insertion.apply_insertion` (prereg §6.4)

The dispatcher in :mod:`vrp_copilot_bench.perturbations` routes
``PerturbationSpec`` values to the right family.
"""

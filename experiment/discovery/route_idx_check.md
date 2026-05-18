# Within-action route_idx consistency check

Empirical verification of the two invariants documented in the STRUCT
tolerance notes of `experiment/configs/payload_schemas_rationale.md`.
Read-only; no schema changes follow from this check (both invariants
hold).

## Cell

- `instance_id`: `C101` (Solomon-100, C-class)
- `perturbation_id`: `OC_1` (ORDER_CHANGE, magnitude 0.05 — inserts one
  new customer near the highest-slack baseline route)
- `affected_customers`: `[101]` — the inserted customer ID
- `perturbed.n_customers`: 101

## Actions tested

Both actions were run on the same `(C101, OC_1)` perturbed instance,
with the C101 baseline routes loaded from
`data/vrptw_baselines/C101.json` and the OC_1 perturbation applied via
`vrp_copilot_bench.vrptw_perturbations.apply_vrptw_perturbation`.

- `local_repair_insert` — instantiated as
  `vrp_copilot_bench.vrptw.actions.LocalRepairInsert()` and applied to
  the baseline routes.
- `pyvrp_60s_reference` — materialised via
  `vrp_copilot_bench.vrptw.actions.materialize_reference_action` from
  the on-disk reference solve at
  `data/stage_a_vrptw_checkpoints/refs/C101__OC_1__seed1.json`
  (reference seed 1, 60 s budget).

## Invariants

- **(a)** For each entry in `customer_schedule`, `route_idx` points to a
  route in `routes` whose `customer_ids` contains the entry's
  `customer_id`.
- **(b)** The set of customers across all `customer_schedule` entries
  equals the union of customers across all `routes`, minus
  `unserved_customer_ids` from the PV projection.

## Per-action raw values and verdict

```json
{
  "local_repair_insert": {
    "n_routes": 10,
    "n_schedule_entries": 101,
    "unserved": [],
    "invariant_a_failures": [],
    "invariant_b_extra_in_schedule": [],
    "invariant_b_missing_from_schedule": []
  },
  "pyvrp_60s_reference": {
    "n_routes": 11,
    "n_schedule_entries": 101,
    "unserved": [],
    "invariant_a_failures": [],
    "invariant_b_extra_in_schedule": [],
    "invariant_b_missing_from_schedule": []
  }
}
```

### `local_repair_insert`

- Action evaluation: `feasible = False`, `n_routes = 10`,
  `unserved_customers = []` (the inserted customer 101 was placed into
  one of the existing routes; infeasibility on this action is
  time-window-related, not coverage-related).
- Invariant (a): **passes**. Zero failures across 101 schedule entries.
- Invariant (b): **passes**. Zero extras in `customer_schedule`, zero
  missing.

### `pyvrp_60s_reference`

- Action evaluation: `feasible = True`, `n_routes = 11`,
  `unserved_customers = []`.
- Invariant (a): **passes**. Zero failures across 101 schedule entries.
- Invariant (b): **passes**. Zero extras, zero missing.

## Discrepancies

None.

## Conclusion

Both invariants hold for both `local_repair_insert` and
`pyvrp_60s_reference` on the (C101, OC_1) cell. The route_idx claim in
the STRUCT tolerance notes is verified for the two action shapes the
spec exercises: a heuristic action and the canonical reference solver.
The schema in `payload_schemas.json` requires no projection-level
revision.

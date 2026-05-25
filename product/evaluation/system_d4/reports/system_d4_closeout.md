# System D4 — closeout

## 1. Purpose

D4 adds a deterministic **compute-decision / recompute-policy layer** on top
of D3. It tells the frontend/operator, for any given prompt, whether the
current payload is sufficient to answer the question or whether a comparison
payload, a cheap recomputation, or a solver escalation is required.

D4 is the contract layer only — it never runs a solver, never trains a
model, and never modifies the locked Run 2 artifacts.

## 2. Relationship to D1 / D2 / D3

D4 sits **after** D3 answerability/warning and **before** frontend rendering.
The wrapper (`d4_system_c.py`) calls `run_system_d3_on_case` verbatim and
attaches a `compute_decision` field to the response. Every existing D3 field
is forwarded unchanged. The D3 regression check (`system_d4_core_run2_report`)
confirms 100% field-level equality across 156 cases (Run 2 core + Axes 1-4).

```
user prompt
  → D1 semantic intent adapter
  → D2 answerability / warnings
  → D3 schema-v2 causal warning overlay
  → D4 compute-decision policy     ← new
  → ProductCopilotResponse + compute_decision
  → frontend / API
```

## 3. Relationship to earlier predictor / routing-policy work

The Stage A benchmark (`src/vrp_copilot_bench/predictor_models/`,
`predictor_baselines/`) trained per-claim-family binary gates for
"cheap action sufficient vs escalate to `pyvrp_10s`," with features
drawn from VRPTW perturbation diagnostics. That work is **not** wired
into D4 yet, for three reasons documented in `design.md` §7:

1. The benchmark claim families do not coincide with the app's intent
   enum.
2. The benchmark features (`baseline_n_routes`, `action_time_warp`, …)
   are perturbation diagnostics, not contract-payload features.
3. Production has no `pyvrp_60s` reference solve at inference time;
   the benchmark used it only to generate training labels.

D4 v1 is therefore deterministic. A learned sufficiency gate
(`deterministic_d4_v1` → `learned_d4_v2`) is reserved as future work
once the feature set has been adapted. The benchmark's
`run_pyvrp_10s` rung is exposed by D4 as a recommended action, but
`pyvrp_60s` is **not** exposed — it was a label generator, not a
deployable rung.

## 4. Payload contract addition

```json
"compute_decision": {
  "mode": "answer_from_payload",
  "requires_recompute": false,
  "recommended_action": "none",
  "query_family": "SCHEDULE",
  "reason": "The contract reports the prompt is answerable from the current payload.",
  "confidence": 1.0,
  "required_fields": ["route_end_times"],
  "available_fields": ["route_end_times", "customer_schedule", ...],
  "missing_for_full_answer": [],
  "expected_runtime_seconds": null,
  "policy_source": "deterministic_d4_v1"
}
```

Field semantics, enum membership, and per-intent required-field tables
live in `compute_decision.py` and are pinned by `tests/system_d4/test_d4.py`.

## 5. Deterministic policy rules

Precedence (highest to lowest):

1. `unsupported`            — out-of-schema concept (driver preferences, fuel cost, …)
2. `clarification_needed`   — hedged inquiry shape (`can you improve this?`, `is route N okay?`)
3. `needs_recompute`        — hypothetical / optimization / repair directive
4. `needs_comparison_payload` — explicit comparison referent (`compared to`, `the baseline`, …)
5. `partial_from_payload`   — causal "why" framing OR `causal_mechanism_unsupported` warning from D3
6. `answer_from_payload`    — default when no trigger fires and the contract is answerable

Trigger phrase lists are exposed as `UNSUPPORTED_TRIGGERS`,
`CLARIFICATION_TRIGGERS`, `RECOMPUTE_TRIGGERS`, `COMPARISON_TRIGGERS`
in `compute_decision.py` so they can be extended without touching the
policy core.

Recommended-action selection for `needs_recompute` (deployable ladder
in escalation order):

| Hint in prompt | Action |
|---|---|
| `reuse current` / `still feasible` / `without re-solving` | `run_reuse_direct` |
| `nearest neighbor` / `NN heuristic` | `run_nearest_neighbor` |
| `clarke wright` / `quick heuristic` / `cheap solve` | `run_clarke_wright` |
| `find a better` / `stronger solver` / `fresh solve` / `improve the plan` | `run_pyvrp_10s` |
| otherwise | `run_pyvrp_10s` (safe default) |

`pyvrp_60s` is intentionally absent.

## 6. D4 evaluation set

`d4_cases.csv` — 32 cases.

| mode | count |
|---|---:|
| answer_from_payload | 8 |
| needs_comparison_payload | 8 |
| needs_recompute | 8 |
| partial_from_payload | 4 |
| clarification_needed | 2 |
| unsupported | 2 |

Split: 16 dev / 16 heldout. Splits are balanced across modes (mostly).

## 7. Results

Headline (current run; see `system_d4_stress_report.md` for the
authoritative version):

| metric | value |
|---|---:|
| compute_mode_accuracy | **1.000** |
| requires_recompute_accuracy | **1.000** |
| recommended_action_accuracy | **1.000** |
| query_family_accuracy | **1.000** |
| missing_for_full_answer_recall | **1.000** |
| safe_no_solver_rate | **1.000** |
| needs_recompute → requires_recompute | **1.000** (8/8) |

D3 regression (Run 2 core + Axes 1-4, n=156):

| metric | value |
|---|---:|
| intent_match_rate | 1.000 |
| answerability_match_rate | 1.000 |
| warnings_match_rate | 1.000 |
| evidence_paths_match_rate | 1.000 |
| missing_fields_match_rate | 1.000 |
| next_actions_match_rate | 1.000 |
| behavior_class_match_rate | 1.000 |
| **all_fields_match_rate** | **1.000** |

## 8. Failure analysis

No failures on the current 32-case set. Known semantic edges (kept as
notes for future curation):

- **Causal + comparative-verb overlap.** Prompts like "Why did the
  objective increase?" mix a causal framing with a comparative verb.
  D4 resolves this by treating any `why` framing as causal (overrides
  the bare-verb comparison fallback). Prompts with an explicit
  baseline referent (`compared to`, `the baseline`) bypass causal and
  go to `needs_comparison_payload` per spec §6 Rule 2.
- **Hedged improve language.** "Can you improve this?" is hedged
  inquiry (clarification); "Improve the plan and reduce lateness" is
  a directive (recompute). D4 separates these via the
  `CLARIFICATION_TRIGGERS` set (hedged phrases only) and the absence
  of the bare `"improve this"` token from `RECOMPUTE_TRIGGERS`.
- **`before_after_comparison` intent excluded from D3 causal set.**
  D3 does not emit `causal_mechanism_unsupported` for this intent. D4
  falls back to a lexical causal detector so "Why did the route count
  change?" still routes to `partial_from_payload`.

## 9. What D4 does not do yet

- D4 is **not** a solver. It does not run `pyvrp_10s`, `reuse_direct`,
  `nearest_neighbor`, `clarke_wright`, or any heuristic.
- D4 is **not** the learned benchmark predictor. Per the design doc, a
  feature-set adaptation is required first.
- D4 does **not** add a `/recompute` HTTP endpoint. The runtime that
  acts on `recommended_action` belongs in a future API layer.
- D4 does **not** modify D1/D2/D3 semantics. The D4 wrapper forwards
  every D3 field unchanged (verified by 156-case regression).

## 10. How frontend / API should use `compute_decision`

```
POST /copilot/ask
  → response.compute_decision

if compute_decision.mode == "answer_from_payload":
    render the contract response as today.
elif compute_decision.mode == "partial_from_payload":
    render the contract response with a notice ("I can give you these
    facts but not the cause / not the full comparison").
elif compute_decision.mode == "needs_comparison_payload":
    surface a CTA: "Load comparison / build baseline diff."
elif compute_decision.mode == "needs_recompute":
    surface a CTA referencing compute_decision.recommended_action +
    compute_decision.expected_runtime_seconds.
elif compute_decision.mode == "clarification_needed":
    open the clarification dialog.
elif compute_decision.mode == "unsupported":
    show an explicit "outside current schema" message.
```

The frontend MUST NOT execute the recommended action itself. Solver
execution will live behind a separate (future) endpoint.

## 11. Future learned sufficiency gate


The deterministic D4 v1 should be a stepping stone, not a destination.
Next steps:

- Adapt benchmark features (`predictor_models/features.py`) to
  contract-payload features: evidence-field coverage, prompt-embedding
  signals, prompt-classified intent, payload shape.
- Re-train per-family gates against an app-side label
  (`contract_chosen_behavior == gold_behavior`).
- Add `policy_source = "learned_d4_v2"` and run both deterministic and
  learned in shadow mode for one release cycle.

## 12. Reproduction commands

```bash
# D4 evaluation (32-case set + D3 regression on Run 2 core + Axes)
python3 -m product.evaluation.system_d4.run_system_d4

# D4 tests (mode classification, no-solver invariant, locked-file pin)
python3 -m pytest tests/system_d4 -q

# Upstream regression — D1 / D2 / D3 suites still pass
python3 -m pytest tests/system_d1 tests/system_d2 tests/system_d3 -q
```

Reports written under `product/evaluation/system_d4/reports/`:

- `system_d4_decision_report.csv` — per-case D4 decision detail
- `system_d4_stress_report.csv` / `.md` — D4 metrics + failure analysis
- `system_d4_core_run2_report.csv` / `.md` — D3 regression (full surface)
- `api_contract_update.md` — frontend/API contract note

# R2-S Axis 1 Look-alike Intent Stress — Baseline Report

_System: C0. Run started: 2026-05-20T21:47:03Z. HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747`. Seed run_id: `full-run-v1`._

## Purpose

Axis 1 tests whether the System C0 deterministic intent classifier (`product/copilot/intent.py`) can be tricked into **confidently misrouting** an operator question to a neighbouring wrong intent by surface-token attractors. Each of the 24 cases inherits its gold contract response verbatim from a Run 2 base case; only `prompt_text` is rewritten to embed the named attractor tokens. The diagnostic split complements Axis 3 (which measures the *unknown*-intent failure mode under unseen vocabulary).

## Method

- 24 cases, split 12 dev / 12 heldout via an explicit `split` column; 4 confusion bands of 6 cases each (3 dev + 3 heldout).
- Payloads materialized via `run2_payloads.materialize_case_payload(run_id='full-run-v1')` — identical to the locked-benchmark path.
- No solver calls. No model calls (System C0 is deterministic).
- Scores reuse `run2_scoring.score_case` against gold rows inherited verbatim from the named `base_case_id` in the locked Run 2 benchmark.
- No locked Run 2 file is read for write or modified. The stress split lives entirely under `product/evaluation/run2_stress/axis1_lookalike/`.

### Case distribution

| Stratum | n |
|---|---:|
| total | 24 |
| split = dev | 12 |
| split = heldout | 12 |
| band = `comparison_vs_status_or_objective` | 6 |
| band = `lateness_vs_feasibility_status` | 6 |
| band = `membership_vs_new_customer_assignment` | 6 |
| band = `route_listing_vs_route_end_time` | 6 |

## Guardrails and caveats

- **Not a user study.** All gold labels were author-derived from the base Run 2 case.
- **Not solver validation.** No optimization run, no objective or feasibility check was performed.
- **Not a Run 2 replacement.** Axis 1 is a diagnostic stress split, not a benchmark.
- **Not evidence of broad generalization.** The case count is small (24); a non-zero misroute count is suggestive, not conclusive.
- **Heldout must not be tuned on.** Iteration on C0 or a future System D consumes the `dev` split only.

## Overall metrics

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | 24 | 87.5% | 100.0% | 100.0% | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Metrics by split

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | 12 | 83.3% | 100.0% | 100.0% | 88.3% | 100.0% | 100.0% | 100.0% | 100.0% |
| heldout | 12 | 91.7% | 100.0% | 100.0% | 91.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| overall | 24 | 87.5% | 100.0% | 100.0% | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Metrics by confusion band

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| comparison_vs_status_or_objective | 6 | 50.0% | 100.0% | 100.0% | 60.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| lateness_vs_feasibility_status | 6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| membership_vs_new_customer_assignment | 6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| route_listing_vs_route_end_time | 6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Failure taxonomy (bucket counts)

Mutually exclusive, exhaustive over all 24 cases. See `design.md` §8 for the bucket definitions.

| Bucket | n |
|---|---:|
| `wrong_adjacent_intent` | 3 |
| `downstream_mismatch` | 3 |
| `guard_protected` | 18 |

### Buckets by split

| Split | wrong_adjacent | unknown | downstream_mismatch | guard_protected |
|---|---:|---:|---:|---:|
| dev | 2 | 0 | 1 | 9 |
| heldout | 1 | 0 | 2 | 9 |

### Buckets by band

| Band | wrong_adjacent | unknown | downstream_mismatch | guard_protected |
|---|---:|---:|---:|---:|
| `comparison_vs_status_or_objective` | 3 | 0 | 3 | 0 |
| `lateness_vs_feasibility_status` | 0 | 0 | 0 | 6 |
| `membership_vs_new_customer_assignment` | 0 | 0 | 0 | 6 |
| `route_listing_vs_route_end_time` | 0 | 0 | 0 | 6 |

## Downstream metrics conditional on intent correct

Among cases where the front-door intent was predicted correctly, how does the downstream contract response look? This isolates language-mapping failures from contract-response failures.

| Group | n | Intent acc | Ans acc | Behavior acc | Ev prec | Ev rec | Warn prec | Warn rec | Miss rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| intent_correct only | 21 | 100.0% | 100.0% | 100.0% | 97.1% | 100.0% | 100.0% | 100.0% | 100.0% |
| overall (for reference) | 24 | 87.5% | 100.0% | 100.0% | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Diagnostic table — non-guard-protected cases (6)

| case_id | split | band | bucket | prompt | gold intent | pred intent | attractor | gold cls | pred cls | ev p/r | warn p/r |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1D-10 | dev | `comparison_vs_status_or_objective` | `downstream_mismatch` | Compared with what's typical, is the plan still feasible after the time windows got tighter? | feasibility_status | feasibility_status | before_after_comparison | direct_answer | direct_answer | 0.80/1.00 | 1.00/1.00 |
| A1D-11 | dev | `comparison_vs_status_or_objective` | `wrong_adjacent_intent` | What's the total cost on this plan — has anything actually changed in the report format? | objective_value | objective_delta | objective_delta | direct_answer | direct_answer | 0.40/1.00 | 1.00/1.00 |
| A1D-12 | dev | `comparison_vs_status_or_objective` | `wrong_adjacent_intent` | What's the total cost on this plan now, compared with the rate card we use internally? | objective_value | objective_delta | objective_delta | direct_answer | direct_answer | 0.40/1.00 | 1.00/1.00 |
| A1H-10 | heldout | `comparison_vs_status_or_objective` | `downstream_mismatch` | Compared to nothing else, is the plan still able to handle the deliveries after travel times went up 20%? | feasibility_status | feasibility_status | before_after_comparison | direct_answer | direct_answer | 0.80/1.00 | 1.00/1.00 |
| A1H-11 | heldout | `comparison_vs_status_or_objective` | `wrong_adjacent_intent` | What does this plan end up costing — still a single total, right? | objective_value | objective_delta | objective_delta | direct_answer | direct_answer | 0.40/1.00 | 1.00/1.00 |
| A1H-12 | heldout | `comparison_vs_status_or_objective` | `downstream_mismatch` | Have things changed feasibility-wise after the new customers were added — can the routes handle them all and is anything different? | feasibility_status | feasibility_status | before_after_comparison | direct_answer | direct_answer | 0.80/1.00 | 1.00/1.00 |

## Interpretation

C0 produced 3/24 **wrong_adjacent_intent**, 0/24 **unknown_intent**, 3/24 **downstream_mismatch**, and 18/24 **guard_protected** outcomes across the 24 look-alike cases. See `axis1_closeout.md` for the full methodological interpretation, including which guards held, which heuristics misfired, and the implications for System D scope.


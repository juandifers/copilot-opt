# D-Final pass^5 Reliability — Semantic Holdout (all)

_Experiment date: 2026-05-21. Split: `all`. k = 5._

## Methodological note

This pass^k experiment is **not** testing full-response LLM generation.
It is testing constrained semantic parsing under a deterministic downstream contract.
The downstream contract (D2/D3/D4) is deterministic and unchanged across repetitions.
Any variation across repetitions comes from the LLM semantic adapter or its guarded fallback path.

Earlier pass^k experiments (R2-4A/R2-5) tested whether an LLM could stably emit an entire
contract response. D-Final pass^k instead tests whether the LLM remains stable when constrained
to a query-frame role. This directly evaluates the architecture's claim that limiting the LLM
to semantic parsing improves reliability while deterministic code owns answerability, evidence,
warnings, and recomputation decisions.

**Success definition**: `intent_correct == True` (primary).
The downstream contract is deterministic — intent stability implies downstream stability.

## Headline results

| Metric | Value |
|---|---|
| Cases | 48 |
| k | 5 |
| Total LLM reps | 240 |
| **pass_k_all** (all 5 reps succeed) | **43/48 = 89.6%** |
| pass_at_k (≥1 rep succeeds) | 100.0% |
| stable_success | 43 |
| flaky | 5 |
| stable_failure | 0 |
| Mean success rate per case | 93.3% |
| Schema valid rate | 71.2% if metrics['schema_valid_rate'] else 'n/a' |
| Adapter accept rate | 97.9% if metrics['adapter_accept_rate'] else 'n/a' |
| Fallback rate | 2.1% |
| Wrong-adjacent intent | 16 / 240 = 6.7% |
| Unknown rate | 0.0% |
| Mean latency (LLM call) | 1135 ms |
| Mean prompt tokens | 745 if metrics['mean_prompt_tokens'] else 'n/a' |
| Mean completion tokens | 75 if metrics['mean_completion_tokens'] else 'n/a' |
| Estimated cost | ~$0.0275 |

## Results by subtype

| Subtype | Cases | pass^k_all | Source: llm | Source: d1 |
|---|---:|---:|---:|---:|
| `route_end_time` | 12 | 12/12 | 60 | 0 |
| `full_route_listing` | 12 | 12/12 | 60 | 0 |
| `lateness_summary` | 12 | 10/12 | 60 | 0 |
| `movement_comparison` | 6 | 6/6 | 30 | 0 |
| `recompute` | 6 | 3/6 | 26 | 4 |

## Case matrix

| case_id | subtype | gold_intent | rep1 | rep2 | rep3 | rep4 | rep5 | status |
|---|---|---|---|---|---|---|---|---|
| SH-01 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-02 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-03 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-04 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-05 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-06 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-07 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-08 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-09 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-10 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-11 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-12 | route_end_time | route_end_time | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-13 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-14 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-15 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-16 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-17 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-18 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-19 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-20 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-21 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-22 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-23 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-24 | full_route_listing | full_route_listing | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-25 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-26 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-27 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-28 | lateness_summary | lateness_summary | ✗ | ✗ | ✓ | ✗ | ✗ | flaky |
| SH-29 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-30 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-31 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-32 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-33 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-34 | lateness_summary | lateness_summary | ✓ | ✗ | ✗ | ✓ | ✗ | flaky |
| SH-35 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-36 | lateness_summary | lateness_summary | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-37 | movement_comparison | before_after_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-38 | movement_comparison | before_after_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-39 | movement_comparison | before_after_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-40 | movement_comparison | before_after_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-41 | recompute | objective_delta | ✗ | ✗ | ✓ | ✗ | ✗ | flaky |
| SH-42 | recompute | objective_delta | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-43 | recompute | objective_delta | ✗ | ✓ | ✓ | ✓ | ✗ | flaky |
| SH-44 | recompute | objective_delta | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-45 | movement_comparison | before_after_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-46 | movement_comparison | before_after_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-47 | recompute | objective_delta | ✓ | ✓ | ✓ | ✓ | ✓ | stable_success |
| SH-48 | recompute | objective_delta | ✓ | ✗ | ✗ | ✓ | ✗ | flaky |

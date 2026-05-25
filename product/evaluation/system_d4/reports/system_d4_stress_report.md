# System D4 — evaluation report

D4 deterministic compute-decision policy evaluated against the 32-case D4 evaluation set (dev=16, heldout=16).

## 1. Headline metrics

- compute_mode_accuracy: **1.000**
- requires_recompute_accuracy: **1.000**
- recommended_action_accuracy: **1.000**
- query_family_accuracy: **1.000**
- missing_for_full_answer_recall: **1.000**
- safe_no_solver_rate: **1.000**
- needs_recompute → requires_recompute rate: **1.000** (8 cases)

## 2. Per-split

| split | n | mode | requires_recompute | action | family |
|---|---:|---:|---:|---:|---:|
| dev | 16 | 1.000 | 1.000 | 1.000 | 1.000 |
| heldout | 16 | 1.000 | 1.000 | 1.000 | 1.000 |

## 3. Failure analysis

No mode failures.

## 4. Mode distribution

- answer_from_payload: 8
- clarification_needed: 2
- needs_comparison_payload: 8
- needs_recompute: 8
- partial_from_payload: 4
- unsupported: 2

# R2-S axis4_payload — C0 baseline

- HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` (tag `run2-contract-extended`)
- Cases: 24 (low=12, high=12)
- Split: dev=14, heldout=10

## 1. Aggregate metrics

| scope | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | 24 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| band=low | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| band=high | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| intent=customer_arrival | 8 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| intent=route_end_time | 8 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| intent=lateness_summary | 8 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| split=dev | 14 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| split=heldout | 10 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## 2. Per (band × intent) breakdown

| band | intent | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| low | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| low | route_end_time | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| low | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| high | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| high | route_end_time | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| high | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## 3. Predicted-vs-observed (C0 only)

Predicted ranges are the C0 column of the design-doc prediction table; delta is observed minus prediction-midpoint.

| band | metric | predicted_range | observed | delta_vs_midpoint | in_range |
|---|---|---|---:|---:|:-:|
| low | intent_correct | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| low | answerability_correct | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| low | behavior_class_correct | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| low | evidence_precision | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| low | evidence_recall | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| low | warning_precision | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| low | warning_recall | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| high | intent_correct | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| high | answerability_correct | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| high | behavior_class_correct | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| high | evidence_precision | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| high | evidence_recall | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| high | warning_precision | 1.00–1.00 | 1.000 | +0.000 | ✓ |
| high | warning_recall | 1.00–1.00 | 1.000 | +0.000 | ✓ |

## 4. Per-case scores (sorted by n_routes)

| case_id | band | n_routes | intent | sub_pattern | split | ev_prec | ev_rec | warn_prec | warn_rec | beh_correct |
|---|---|---:|---|---|---|---:|---:|---:|---:|:-:|
| R2-101 | low | 8 | customer_arrival | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-102 | low | 8 | customer_arrival | multi-entity | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-105 | low | 8 | route_end_time | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-109 | low | 8 | lateness_summary | multi-entity | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-110 | low | 9 | lateness_summary | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-111 | low | 9 | lateness_summary | multi-entity | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-103 | low | 10 | customer_arrival | mid-list | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-106 | low | 10 | route_end_time | mid-list | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-107 | low | 11 | route_end_time | routes-by-position | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-104 | low | 12 | customer_arrival | multi-entity | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-108 | low | 12 | route_end_time | routes-by-position | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-112 | low | 12 | lateness_summary | multi-entity | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-113 | high | 19 | customer_arrival | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-117 | high | 19 | route_end_time | routes-by-position | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-122 | high | 19 | lateness_summary | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-114 | high | 20 | customer_arrival | multi-entity | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-115 | high | 20 | customer_arrival | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-118 | high | 20 | route_end_time | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-119 | high | 21 | route_end_time | routes-by-position | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-116 | high | 22 | customer_arrival | multi-entity | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-120 | high | 22 | route_end_time | mid-list | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-121 | high | 22 | lateness_summary | multi-entity | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-123 | high | 22 | lateness_summary | multi-entity | dev | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |
| R2-124 | high | 22 | lateness_summary | multi-entity | heldout | 1.00 | 1.00 | 1.00 | 1.00 | ✓ |

## 5. Heldout sample-size feasibility

| band | dev n | heldout n | heldout ≥ 3 |
|---|---:|---:|:-:|
| low | 6 | 6 | ✓ |
| high | 8 | 4 | ✓ |

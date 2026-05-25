# axis4 — System B baseline
- HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` (tag `run2-contract-extended`)
- Model: `gpt-5.4-mini` (observed: gpt-5.4-mini-2026-03-17)
- Cases: 24
- Total latency: 42.62s
- Total prompt tokens: 184,679
- Total completion tokens: 2,881
- Errors: 0

## Aggregate

| scope | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | 24 | 0.917 | 0.583 | 0.375 | 0.424 | 0.812 | 0.375 | 0.917 | 1.000 |
| band=low | 12 | 1.000 | 0.583 | 0.417 | 0.528 | 1.000 | 0.417 | 0.917 | 1.000 |
| band=high | 12 | 0.833 | 0.583 | 0.333 | 0.319 | 0.625 | 0.333 | 0.917 | 1.000 |
| intent=customer_arrival | 8 | 1.000 | 0.375 | 0.375 | 0.375 | 0.750 | 0.375 | 1.000 | 1.000 |
| intent=route_end_time | 8 | 1.000 | 0.625 | 0.250 | 0.500 | 1.000 | 0.250 | 0.750 | 1.000 |
| intent=lateness_summary | 8 | 0.750 | 0.750 | 0.500 | 0.396 | 0.688 | 0.500 | 1.000 | 1.000 |
| split=dev | 14 | 0.929 | 0.500 | 0.286 | 0.393 | 0.750 | 0.286 | 0.857 | 1.000 |
| split=heldout | 10 | 0.900 | 0.700 | 0.500 | 0.467 | 0.900 | 0.500 | 1.000 | 1.000 |

## Per-case scores (sorted by n_routes)

| case_id | band | n_routes | intent | split | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| R2-101 | low | 8 | customer_arrival | dev | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-102 | low | 8 | customer_arrival | dev | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-105 | low | 8 | route_end_time | dev | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 0.00 | 0.00 |
| R2-109 | low | 8 | lateness_summary | dev | 1.00 | 1.00 | 0.00 | 0.67 | 1.00 | 0.00 | 1.00 |
| R2-110 | low | 9 | lateness_summary | dev | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-111 | low | 9 | lateness_summary | heldout | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 | 1.00 |
| R2-103 | low | 10 | customer_arrival | heldout | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-106 | low | 10 | route_end_time | heldout | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-107 | low | 11 | route_end_time | dev | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-104 | low | 12 | customer_arrival | heldout | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-108 | low | 12 | route_end_time | heldout | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-112 | low | 12 | lateness_summary | heldout | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-113 | high | 19 | customer_arrival | dev | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| R2-117 | high | 19 | route_end_time | heldout | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-122 | high | 19 | lateness_summary | dev | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-114 | high | 20 | customer_arrival | dev | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-115 | high | 20 | customer_arrival | dev | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| R2-118 | high | 20 | route_end_time | dev | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-119 | high | 21 | route_end_time | heldout | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 0.00 | 1.00 |
| R2-116 | high | 22 | customer_arrival | heldout | 1.00 | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| R2-120 | high | 22 | route_end_time | dev | 1.00 | 0.00 | 0.00 | 0.50 | 1.00 | 0.00 | 0.00 |
| R2-121 | high | 22 | lateness_summary | dev | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| R2-123 | high | 22 | lateness_summary | dev | 0.00 | 1.00 | 1.00 | 0.33 | 0.50 | 1.00 | 1.00 |
| R2-124 | high | 22 | lateness_summary | heldout | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |

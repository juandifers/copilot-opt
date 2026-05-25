# R2-S axis4_payload — combined (C0, A, B) summary
- HEAD: `18b4811a1f85c166ea3ba8c777dfc021b2a5f747` (tag `run2-contract-extended`)
- Model: `gpt-5.4-mini` (observed: B=gpt-5.4-mini-2026-03-17; A=gpt-5.4-mini-2026-03-17)
- Cases: 24 (low=12, high=12)
- Wall-clock: B 42.6s + A 39.6s = 82.3s
- API tokens: B prompt=184,679 comp=2,881; A prompt=183,427 comp=3,048
- Errors: B=0, A=0

## 1. Per-(system × band) metrics

| system | band | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec | miss_rec |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | low | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A | low | 12 | 1.000 | 1.000 | 0.917 | 0.667 | 1.000 | 0.917 | 1.000 | 1.000 |
| A | high | 12 | 1.000 | 1.000 | 1.000 | 0.567 | 1.000 | 1.000 | 1.000 | 1.000 |
| B | low | 12 | 1.000 | 0.583 | 0.417 | 0.528 | 1.000 | 0.417 | 0.917 | 1.000 |
| B | high | 12 | 0.833 | 0.583 | 0.333 | 0.319 | 0.625 | 0.333 | 0.917 | 1.000 |

## 2. Per-(system × band × intent) breakdown

| system | band | intent | n | intent | ans | beh | ev_prec | ev_rec | warn_prec | warn_rec |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | low | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | low | route_end_time | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | low | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | route_end_time | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| C0 | high | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A | low | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 |
| A | low | route_end_time | 4 | 1.000 | 1.000 | 0.750 | 0.500 | 1.000 | 0.750 | 1.000 |
| A | low | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| A | high | customer_arrival | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 |
| A | high | route_end_time | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 |
| A | high | lateness_summary | 4 | 1.000 | 1.000 | 1.000 | 0.700 | 1.000 | 1.000 | 1.000 |
| B | low | customer_arrival | 4 | 1.000 | 0.500 | 0.500 | 0.500 | 1.000 | 0.500 | 1.000 |
| B | low | route_end_time | 4 | 1.000 | 0.500 | 0.250 | 0.500 | 1.000 | 0.250 | 0.750 |
| B | low | lateness_summary | 4 | 1.000 | 0.750 | 0.500 | 0.583 | 1.000 | 0.500 | 1.000 |
| B | high | customer_arrival | 4 | 1.000 | 0.250 | 0.250 | 0.250 | 0.500 | 0.250 | 1.000 |
| B | high | route_end_time | 4 | 1.000 | 0.750 | 0.250 | 0.500 | 1.000 | 0.250 | 0.750 |
| B | high | lateness_summary | 4 | 0.500 | 0.750 | 0.500 | 0.208 | 0.375 | 0.500 | 1.000 |

## 3. Predicted-vs-observed delta (A, B)

Predictions from `design.md` §6. `δ` is observed minus prediction-midpoint.

| system | band | metric | predicted | observed | δ | in_range |
|---|---|---|---|---:|---:|:-:|
| A | low | intent_correct | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| A | low | answerability_correct | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| A | low | behavior_class_correct | 0.90–0.95 | 0.917 | -0.008 | ✓ |
| A | low | evidence_precision | 0.75–0.85 | 0.667 | -0.133 | ✗ |
| A | low | evidence_recall | 0.90–1.00 | 1.000 | +0.050 | ✓ |
| A | low | warning_precision | 0.95–1.00 | 0.917 | -0.058 | ✗ |
| A | low | warning_recall | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| A | high | intent_correct | 0.90–0.95 | 1.000 | +0.075 | ✗ |
| A | high | answerability_correct | 0.95–1.00 | 1.000 | +0.025 | ✓ |
| A | high | behavior_class_correct | 0.85–0.90 | 1.000 | +0.125 | ✗ |
| A | high | evidence_precision | 0.55–0.75 | 0.567 | -0.083 | ✓ |
| A | high | evidence_recall | 0.85–0.95 | 1.000 | +0.100 | ✗ |
| A | high | warning_precision | 0.90–0.95 | 1.000 | +0.075 | ✗ |
| A | high | warning_recall | 0.90–0.95 | 1.000 | +0.075 | ✗ |
| B | low | intent_correct | 0.90–0.95 | 1.000 | +0.075 | ✗ |
| B | low | answerability_correct | 0.95–1.00 | 0.583 | -0.392 | ✗ |
| B | low | behavior_class_correct | 0.80–0.90 | 0.417 | -0.433 | ✗ |
| B | low | evidence_precision | 0.65–0.80 | 0.528 | -0.197 | ✗ |
| B | low | evidence_recall | 0.85–0.95 | 1.000 | +0.100 | ✗ |
| B | low | warning_precision | 0.90–0.95 | 0.417 | -0.508 | ✗ |
| B | low | warning_recall | 0.90–0.95 | 0.917 | -0.008 | ✓ |
| B | high | intent_correct | 0.85–0.95 | 0.833 | -0.067 | ✗ |
| B | high | answerability_correct | 0.90–1.00 | 0.583 | -0.367 | ✗ |
| B | high | behavior_class_correct | 0.75–0.85 | 0.333 | -0.467 | ✗ |
| B | high | evidence_precision | 0.45–0.65 | 0.319 | -0.231 | ✗ |
| B | high | evidence_recall | 0.80–0.90 | 0.625 | -0.225 | ✗ |
| B | high | warning_precision | 0.85–0.95 | 0.333 | -0.567 | ✗ |
| B | high | warning_recall | 0.85–0.95 | 0.917 | +0.017 | ✓ |

## 4. Case-level surprises (A / B failures not anticipated by prediction)

A surprise is any per-case metric score below the lower bound of the predicted (band, system) range. Listed by case + metric.

| case_id | band | intent | n_routes | system | metric | observed | predicted_lo |
|---|---|---|---:|---|---|---:|---:|
| R2-101 | low | customer_arrival | 8 | A | evidence_precision | 0.500 | 0.75 |
| R2-102 | low | customer_arrival | 8 | A | evidence_precision | 0.500 | 0.75 |
| R2-103 | low | customer_arrival | 10 | A | evidence_precision | 0.500 | 0.75 |
| R2-104 | low | customer_arrival | 12 | A | evidence_precision | 0.500 | 0.75 |
| R2-105 | low | route_end_time | 8 | A | evidence_precision | 0.500 | 0.75 |
| R2-106 | low | route_end_time | 10 | A | evidence_precision | 0.500 | 0.75 |
| R2-107 | low | route_end_time | 11 | A | evidence_precision | 0.500 | 0.75 |
| R2-108 | low | route_end_time | 12 | A | behavior_class_correct | 0.000 | 0.90 |
| R2-108 | low | route_end_time | 12 | A | evidence_precision | 0.500 | 0.75 |
| R2-108 | low | route_end_time | 12 | A | warning_precision | 0.000 | 0.95 |
| R2-113 | high | customer_arrival | 19 | A | evidence_precision | 0.500 | 0.55 |
| R2-114 | high | customer_arrival | 20 | A | evidence_precision | 0.500 | 0.55 |
| R2-115 | high | customer_arrival | 20 | A | evidence_precision | 0.500 | 0.55 |
| R2-116 | high | customer_arrival | 22 | A | evidence_precision | 0.500 | 0.55 |
| R2-117 | high | route_end_time | 19 | A | evidence_precision | 0.500 | 0.55 |
| R2-118 | high | route_end_time | 20 | A | evidence_precision | 0.500 | 0.55 |
| R2-119 | high | route_end_time | 21 | A | evidence_precision | 0.500 | 0.55 |
| R2-120 | high | route_end_time | 22 | A | evidence_precision | 0.500 | 0.55 |
| R2-121 | high | lateness_summary | 22 | A | evidence_precision | 0.400 | 0.55 |
| R2-124 | high | lateness_summary | 22 | A | evidence_precision | 0.400 | 0.55 |
| R2-101 | low | customer_arrival | 8 | B | answerability_correct | 0.000 | 0.95 |
| R2-101 | low | customer_arrival | 8 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-101 | low | customer_arrival | 8 | B | evidence_precision | 0.500 | 0.65 |
| R2-101 | low | customer_arrival | 8 | B | warning_precision | 0.000 | 0.90 |
| R2-102 | low | customer_arrival | 8 | B | answerability_correct | 0.000 | 0.95 |
| R2-102 | low | customer_arrival | 8 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-102 | low | customer_arrival | 8 | B | evidence_precision | 0.500 | 0.65 |
| R2-102 | low | customer_arrival | 8 | B | warning_precision | 0.000 | 0.90 |
| R2-103 | low | customer_arrival | 10 | B | evidence_precision | 0.500 | 0.65 |
| R2-104 | low | customer_arrival | 12 | B | evidence_precision | 0.500 | 0.65 |
| R2-105 | low | route_end_time | 8 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-105 | low | route_end_time | 8 | B | evidence_precision | 0.500 | 0.65 |
| R2-105 | low | route_end_time | 8 | B | warning_precision | 0.000 | 0.90 |
| R2-105 | low | route_end_time | 8 | B | warning_recall | 0.000 | 0.90 |
| R2-106 | low | route_end_time | 10 | B | evidence_precision | 0.500 | 0.65 |
| R2-107 | low | route_end_time | 11 | B | answerability_correct | 0.000 | 0.95 |
| R2-107 | low | route_end_time | 11 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-107 | low | route_end_time | 11 | B | evidence_precision | 0.500 | 0.65 |
| R2-107 | low | route_end_time | 11 | B | warning_precision | 0.000 | 0.90 |
| R2-108 | low | route_end_time | 12 | B | answerability_correct | 0.000 | 0.95 |
| R2-108 | low | route_end_time | 12 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-108 | low | route_end_time | 12 | B | evidence_precision | 0.500 | 0.65 |
| R2-108 | low | route_end_time | 12 | B | warning_precision | 0.000 | 0.90 |
| R2-109 | low | lateness_summary | 8 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-109 | low | lateness_summary | 8 | B | warning_precision | 0.000 | 0.90 |
| R2-110 | low | lateness_summary | 9 | B | evidence_precision | 0.500 | 0.65 |
| R2-112 | low | lateness_summary | 12 | B | answerability_correct | 0.000 | 0.95 |
| R2-112 | low | lateness_summary | 12 | B | behavior_class_correct | 0.000 | 0.80 |
| R2-112 | low | lateness_summary | 12 | B | evidence_precision | 0.500 | 0.65 |
| R2-112 | low | lateness_summary | 12 | B | warning_precision | 0.000 | 0.90 |
| R2-113 | high | customer_arrival | 19 | B | answerability_correct | 0.000 | 0.90 |
| R2-113 | high | customer_arrival | 19 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-113 | high | customer_arrival | 19 | B | evidence_precision | 0.000 | 0.45 |
| R2-113 | high | customer_arrival | 19 | B | evidence_recall | 0.000 | 0.80 |
| R2-113 | high | customer_arrival | 19 | B | warning_precision | 0.000 | 0.85 |
| R2-114 | high | customer_arrival | 20 | B | answerability_correct | 0.000 | 0.90 |
| R2-114 | high | customer_arrival | 20 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-114 | high | customer_arrival | 20 | B | warning_precision | 0.000 | 0.85 |
| R2-115 | high | customer_arrival | 20 | B | answerability_correct | 0.000 | 0.90 |
| R2-115 | high | customer_arrival | 20 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-115 | high | customer_arrival | 20 | B | evidence_precision | 0.000 | 0.45 |
| R2-115 | high | customer_arrival | 20 | B | evidence_recall | 0.000 | 0.80 |
| R2-115 | high | customer_arrival | 20 | B | warning_precision | 0.000 | 0.85 |
| R2-117 | high | route_end_time | 19 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-117 | high | route_end_time | 19 | B | warning_precision | 0.000 | 0.85 |
| R2-119 | high | route_end_time | 21 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-119 | high | route_end_time | 21 | B | warning_precision | 0.000 | 0.85 |
| R2-120 | high | route_end_time | 22 | B | answerability_correct | 0.000 | 0.90 |
| R2-120 | high | route_end_time | 22 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-120 | high | route_end_time | 22 | B | warning_precision | 0.000 | 0.85 |
| R2-120 | high | route_end_time | 22 | B | warning_recall | 0.000 | 0.85 |
| R2-121 | high | lateness_summary | 22 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-121 | high | lateness_summary | 22 | B | evidence_precision | 0.000 | 0.45 |
| R2-121 | high | lateness_summary | 22 | B | evidence_recall | 0.000 | 0.80 |
| R2-121 | high | lateness_summary | 22 | B | warning_precision | 0.000 | 0.85 |
| R2-123 | high | lateness_summary | 22 | B | intent_correct | 0.000 | 0.85 |
| R2-123 | high | lateness_summary | 22 | B | evidence_precision | 0.333 | 0.45 |
| R2-123 | high | lateness_summary | 22 | B | evidence_recall | 0.500 | 0.80 |
| R2-124 | high | lateness_summary | 22 | B | intent_correct | 0.000 | 0.85 |
| R2-124 | high | lateness_summary | 22 | B | answerability_correct | 0.000 | 0.90 |
| R2-124 | high | lateness_summary | 22 | B | behavior_class_correct | 0.000 | 0.75 |
| R2-124 | high | lateness_summary | 22 | B | evidence_precision | 0.000 | 0.45 |
| R2-124 | high | lateness_summary | 22 | B | evidence_recall | 0.000 | 0.80 |
| R2-124 | high | lateness_summary | 22 | B | warning_precision | 0.000 | 0.85 |

## 6. Failure-mode analysis (C1 design signals)

### 6.1 Over-cited evidence paths

Field-family paths the model emitted beyond the gold for that intent. Confirms the R2-4A/R2-5 prediction that identifier fields are spuriously added alongside value fields.

| field path | A count (/24) | B count (/24) |
|---|---:|---:|
| `customer_schedule[].customer_id` | 10 | 9 |
| `route_end_times[].route_idx` | 8 | 8 |
| `customer_schedule[].is_late` | 2 | 6 |
| `customer_schedule[].lateness_minutes` | 1 | 2 |
| `customer_schedule[].route_idx` | 1 | 0 |
| `customer_schedule[].arrival` | 0 | 1 |

### 6.2 B truncation-induced false-premise

System B fires `false_premise_detected` on customer_arrival questions whose customer ID lies in the truncated tail of the 60-row schedule projection (the prompt builder caps `customer_schedule` at `_MAX_SCHEDULE_ROWS_INLINE = 60`). C0 and A check the full payload via the deterministic answerability layer; B reads only the compacted view and concludes the customer does not exist.

Affected cases: R2-101, R2-102, R2-113, R2-114, R2-115 (n=5).

C1 design signal: either (a) preserve customer-ID coverage in the compaction (e.g. cite by ID, fetch on demand), or (b) have C1 consume the deterministic answerability check instead of the LLM's read of the truncated payload.

### 6.3 B over-firing of warning codes

B fires `route_indexing_ambiguity` on positional phrasings (`the 11th route`, `the 15th route`) and on plural enumerations (`routes 8, 12, and 17`). The C0 contract's regex `\broute\s+\d+\b` is intentionally narrow and only matches `route N` singular. B also fires `struct_membership_ambiguity` on lateness_summary questions naming multiple customers — that code is bound to `single_customer_route_membership` intent.

| case | prompt | gold_warnings | pred_warnings |
|---|---|---|---|
| R2-101 | When does customer 142 arrive? | (none) | false_premise_detected |
| R2-102 | When does the driver reach customers 87, 142, and 199? | (none) | false_premise_detected |
| R2-105 | What time does route 5 finish? | route_indexing_ambiguity | (none) |
| R2-107 | What's the end time of the 9th route? | (none) | route_indexing_ambiguity |
| R2-108 | When does the 11th route finish? | (none) | route_indexing_ambiguity |
| R2-109 | Which customers are late on routes 1-4? | (none) | route_indexing_ambiguity |
| R2-112 | Are customers 87, 142, and 199 all on time? | (none) | struct_membership_ambiguity |
| R2-113 | When does customer 142 arrive? | (none) | false_premise_detected |
| R2-114 | When does the driver reach customers 87, 142, and 199? | (none) | false_premise_detected |
| R2-115 | When does customer 178 arrive? | (none) | false_premise_detected |
| R2-117 | When does the 15th route finish? | (none) | route_indexing_ambiguity |
| R2-119 | What's the end time of the 18th route? | (none) | route_indexing_ambiguity |
| R2-120 | When does route 17 finish? | route_indexing_ambiguity | false_premise_detected |
| R2-121 | Which customers are late on routes 8, 12, and 17? | (none) | route_indexing_ambiguity |
| R2-124 | Are customers 87, 142, and 199 all on time? | (none) | struct_membership_ambiguity |

C1 design signal: warning emission needs the contract's regex-pinned rules, not the model's intuition about when a warning "makes sense". This is exactly the deterministic-prior role A is meant to play — A holds these warnings correctly on 11/12 low-band and 12/12 high-band cases.

### 6.4 A silent prior override

System A added warnings beyond the prior on the following cases without flagging `prior_disagreement=true`. The deterministic prior locks warnings; A is supposed to copy them unchanged.

| case | prompt | gold_warnings | A pred warnings | prior_disagreement |
|---|---|---|---|:-:|
| R2-108 | When does the 11th route finish? | (none) | route_indexing_ambiguity | ✗ |

C1 design signal: A's prior-lock instruction is not strictly honored on positional-route phrasings. Tightening the prompt template or post-validating the model's emitted warnings against the prior would close this gap.


## 5. Per-case × per-system × per-metric scatter

One row per (case_id, system, metric). This is the data the cross-axis joint analysis will plot.

| case_id | split | band | n_routes | intent | system | metric | score |
|---|---|---|---:|---|---|---|---:|
| R2-101 | dev | low | 8 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | A | evidence_precision | 0.500 |
| R2-101 | dev | low | 8 | customer_arrival | A | evidence_recall | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | A | intent_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | A | answerability_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | A | warning_precision | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | A | warning_recall | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | B | evidence_precision | 0.500 |
| R2-101 | dev | low | 8 | customer_arrival | B | evidence_recall | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | B | intent_correct | 1.000 |
| R2-101 | dev | low | 8 | customer_arrival | B | answerability_correct | 0.000 |
| R2-101 | dev | low | 8 | customer_arrival | B | behavior_class_correct | 0.000 |
| R2-101 | dev | low | 8 | customer_arrival | B | warning_precision | 0.000 |
| R2-101 | dev | low | 8 | customer_arrival | B | warning_recall | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | A | evidence_precision | 0.500 |
| R2-102 | dev | low | 8 | customer_arrival | A | evidence_recall | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | A | intent_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | A | answerability_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | A | warning_precision | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | A | warning_recall | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | B | evidence_precision | 0.500 |
| R2-102 | dev | low | 8 | customer_arrival | B | evidence_recall | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | B | intent_correct | 1.000 |
| R2-102 | dev | low | 8 | customer_arrival | B | answerability_correct | 0.000 |
| R2-102 | dev | low | 8 | customer_arrival | B | behavior_class_correct | 0.000 |
| R2-102 | dev | low | 8 | customer_arrival | B | warning_precision | 0.000 |
| R2-102 | dev | low | 8 | customer_arrival | B | warning_recall | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | A | evidence_precision | 0.500 |
| R2-103 | heldout | low | 10 | customer_arrival | A | evidence_recall | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | A | intent_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | A | answerability_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | A | warning_precision | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | A | warning_recall | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | B | evidence_precision | 0.500 |
| R2-103 | heldout | low | 10 | customer_arrival | B | evidence_recall | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | B | intent_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | B | answerability_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | B | behavior_class_correct | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | B | warning_precision | 1.000 |
| R2-103 | heldout | low | 10 | customer_arrival | B | warning_recall | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | A | evidence_precision | 0.500 |
| R2-104 | heldout | low | 12 | customer_arrival | A | evidence_recall | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | A | intent_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | A | answerability_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | A | warning_precision | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | A | warning_recall | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | B | evidence_precision | 0.500 |
| R2-104 | heldout | low | 12 | customer_arrival | B | evidence_recall | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | B | intent_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | B | answerability_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | B | behavior_class_correct | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | B | warning_precision | 1.000 |
| R2-104 | heldout | low | 12 | customer_arrival | B | warning_recall | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | intent_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | warning_precision | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | C0 | warning_recall | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | A | evidence_precision | 0.500 |
| R2-105 | dev | low | 8 | route_end_time | A | evidence_recall | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | A | intent_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | A | answerability_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | A | warning_precision | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | A | warning_recall | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | B | evidence_precision | 0.500 |
| R2-105 | dev | low | 8 | route_end_time | B | evidence_recall | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | B | intent_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | B | answerability_correct | 1.000 |
| R2-105 | dev | low | 8 | route_end_time | B | behavior_class_correct | 0.000 |
| R2-105 | dev | low | 8 | route_end_time | B | warning_precision | 0.000 |
| R2-105 | dev | low | 8 | route_end_time | B | warning_recall | 0.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | intent_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | warning_precision | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | C0 | warning_recall | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | A | evidence_precision | 0.500 |
| R2-106 | heldout | low | 10 | route_end_time | A | evidence_recall | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | A | intent_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | A | answerability_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | A | warning_precision | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | A | warning_recall | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | B | evidence_precision | 0.500 |
| R2-106 | heldout | low | 10 | route_end_time | B | evidence_recall | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | B | intent_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | B | answerability_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | B | behavior_class_correct | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | B | warning_precision | 1.000 |
| R2-106 | heldout | low | 10 | route_end_time | B | warning_recall | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | intent_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | warning_precision | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | C0 | warning_recall | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | A | evidence_precision | 0.500 |
| R2-107 | dev | low | 11 | route_end_time | A | evidence_recall | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | A | intent_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | A | answerability_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | A | warning_precision | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | A | warning_recall | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | B | evidence_precision | 0.500 |
| R2-107 | dev | low | 11 | route_end_time | B | evidence_recall | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | B | intent_correct | 1.000 |
| R2-107 | dev | low | 11 | route_end_time | B | answerability_correct | 0.000 |
| R2-107 | dev | low | 11 | route_end_time | B | behavior_class_correct | 0.000 |
| R2-107 | dev | low | 11 | route_end_time | B | warning_precision | 0.000 |
| R2-107 | dev | low | 11 | route_end_time | B | warning_recall | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | intent_correct | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | warning_precision | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | C0 | warning_recall | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | A | evidence_precision | 0.500 |
| R2-108 | heldout | low | 12 | route_end_time | A | evidence_recall | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | A | intent_correct | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | A | answerability_correct | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | A | behavior_class_correct | 0.000 |
| R2-108 | heldout | low | 12 | route_end_time | A | warning_precision | 0.000 |
| R2-108 | heldout | low | 12 | route_end_time | A | warning_recall | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | B | evidence_precision | 0.500 |
| R2-108 | heldout | low | 12 | route_end_time | B | evidence_recall | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | B | intent_correct | 1.000 |
| R2-108 | heldout | low | 12 | route_end_time | B | answerability_correct | 0.000 |
| R2-108 | heldout | low | 12 | route_end_time | B | behavior_class_correct | 0.000 |
| R2-108 | heldout | low | 12 | route_end_time | B | warning_precision | 0.000 |
| R2-108 | heldout | low | 12 | route_end_time | B | warning_recall | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | evidence_precision | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | evidence_recall | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | intent_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | answerability_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | warning_precision | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | A | warning_recall | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | B | evidence_precision | 0.667 |
| R2-109 | dev | low | 8 | lateness_summary | B | evidence_recall | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | B | intent_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | B | answerability_correct | 1.000 |
| R2-109 | dev | low | 8 | lateness_summary | B | behavior_class_correct | 0.000 |
| R2-109 | dev | low | 8 | lateness_summary | B | warning_precision | 0.000 |
| R2-109 | dev | low | 8 | lateness_summary | B | warning_recall | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | evidence_precision | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | evidence_recall | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | intent_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | answerability_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | warning_precision | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | A | warning_recall | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | B | evidence_precision | 0.500 |
| R2-110 | dev | low | 9 | lateness_summary | B | evidence_recall | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | B | intent_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | B | answerability_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | B | behavior_class_correct | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | B | warning_precision | 1.000 |
| R2-110 | dev | low | 9 | lateness_summary | B | warning_recall | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | evidence_precision | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | evidence_recall | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | intent_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | answerability_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | warning_precision | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | A | warning_recall | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | B | evidence_precision | 0.667 |
| R2-111 | heldout | low | 9 | lateness_summary | B | evidence_recall | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | B | intent_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | B | answerability_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | B | behavior_class_correct | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | B | warning_precision | 1.000 |
| R2-111 | heldout | low | 9 | lateness_summary | B | warning_recall | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | evidence_precision | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | evidence_recall | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | intent_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | answerability_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | warning_precision | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | A | warning_recall | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | B | evidence_precision | 0.500 |
| R2-112 | heldout | low | 12 | lateness_summary | B | evidence_recall | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | B | intent_correct | 1.000 |
| R2-112 | heldout | low | 12 | lateness_summary | B | answerability_correct | 0.000 |
| R2-112 | heldout | low | 12 | lateness_summary | B | behavior_class_correct | 0.000 |
| R2-112 | heldout | low | 12 | lateness_summary | B | warning_precision | 0.000 |
| R2-112 | heldout | low | 12 | lateness_summary | B | warning_recall | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | A | evidence_precision | 0.500 |
| R2-113 | dev | high | 19 | customer_arrival | A | evidence_recall | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | A | intent_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | A | answerability_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | A | warning_precision | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | A | warning_recall | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | evidence_precision | 0.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | evidence_recall | 0.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | intent_correct | 1.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | answerability_correct | 0.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | behavior_class_correct | 0.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | warning_precision | 0.000 |
| R2-113 | dev | high | 19 | customer_arrival | B | warning_recall | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | A | evidence_precision | 0.500 |
| R2-114 | dev | high | 20 | customer_arrival | A | evidence_recall | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | A | intent_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | A | answerability_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | A | warning_precision | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | A | warning_recall | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | B | evidence_precision | 0.500 |
| R2-114 | dev | high | 20 | customer_arrival | B | evidence_recall | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | B | intent_correct | 1.000 |
| R2-114 | dev | high | 20 | customer_arrival | B | answerability_correct | 0.000 |
| R2-114 | dev | high | 20 | customer_arrival | B | behavior_class_correct | 0.000 |
| R2-114 | dev | high | 20 | customer_arrival | B | warning_precision | 0.000 |
| R2-114 | dev | high | 20 | customer_arrival | B | warning_recall | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | A | evidence_precision | 0.500 |
| R2-115 | dev | high | 20 | customer_arrival | A | evidence_recall | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | A | intent_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | A | answerability_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | A | warning_precision | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | A | warning_recall | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | evidence_precision | 0.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | evidence_recall | 0.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | intent_correct | 1.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | answerability_correct | 0.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | behavior_class_correct | 0.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | warning_precision | 0.000 |
| R2-115 | dev | high | 20 | customer_arrival | B | warning_recall | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | evidence_precision | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | evidence_recall | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | intent_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | answerability_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | behavior_class_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | warning_precision | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | C0 | warning_recall | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | A | evidence_precision | 0.500 |
| R2-116 | heldout | high | 22 | customer_arrival | A | evidence_recall | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | A | intent_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | A | answerability_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | A | behavior_class_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | A | warning_precision | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | A | warning_recall | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | B | evidence_precision | 0.500 |
| R2-116 | heldout | high | 22 | customer_arrival | B | evidence_recall | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | B | intent_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | B | answerability_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | B | behavior_class_correct | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | B | warning_precision | 1.000 |
| R2-116 | heldout | high | 22 | customer_arrival | B | warning_recall | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | intent_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | warning_precision | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | C0 | warning_recall | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | A | evidence_precision | 0.500 |
| R2-117 | heldout | high | 19 | route_end_time | A | evidence_recall | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | A | intent_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | A | answerability_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | A | warning_precision | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | A | warning_recall | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | B | evidence_precision | 0.500 |
| R2-117 | heldout | high | 19 | route_end_time | B | evidence_recall | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | B | intent_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | B | answerability_correct | 1.000 |
| R2-117 | heldout | high | 19 | route_end_time | B | behavior_class_correct | 0.000 |
| R2-117 | heldout | high | 19 | route_end_time | B | warning_precision | 0.000 |
| R2-117 | heldout | high | 19 | route_end_time | B | warning_recall | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | intent_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | warning_precision | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | C0 | warning_recall | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | A | evidence_precision | 0.500 |
| R2-118 | dev | high | 20 | route_end_time | A | evidence_recall | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | A | intent_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | A | answerability_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | A | warning_precision | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | A | warning_recall | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | B | evidence_precision | 0.500 |
| R2-118 | dev | high | 20 | route_end_time | B | evidence_recall | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | B | intent_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | B | answerability_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | B | behavior_class_correct | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | B | warning_precision | 1.000 |
| R2-118 | dev | high | 20 | route_end_time | B | warning_recall | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | intent_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | warning_precision | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | C0 | warning_recall | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | A | evidence_precision | 0.500 |
| R2-119 | heldout | high | 21 | route_end_time | A | evidence_recall | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | A | intent_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | A | answerability_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | A | warning_precision | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | A | warning_recall | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | B | evidence_precision | 0.500 |
| R2-119 | heldout | high | 21 | route_end_time | B | evidence_recall | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | B | intent_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | B | answerability_correct | 1.000 |
| R2-119 | heldout | high | 21 | route_end_time | B | behavior_class_correct | 0.000 |
| R2-119 | heldout | high | 21 | route_end_time | B | warning_precision | 0.000 |
| R2-119 | heldout | high | 21 | route_end_time | B | warning_recall | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | evidence_precision | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | evidence_recall | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | intent_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | answerability_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | behavior_class_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | warning_precision | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | C0 | warning_recall | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | A | evidence_precision | 0.500 |
| R2-120 | dev | high | 22 | route_end_time | A | evidence_recall | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | A | intent_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | A | answerability_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | A | behavior_class_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | A | warning_precision | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | A | warning_recall | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | B | evidence_precision | 0.500 |
| R2-120 | dev | high | 22 | route_end_time | B | evidence_recall | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | B | intent_correct | 1.000 |
| R2-120 | dev | high | 22 | route_end_time | B | answerability_correct | 0.000 |
| R2-120 | dev | high | 22 | route_end_time | B | behavior_class_correct | 0.000 |
| R2-120 | dev | high | 22 | route_end_time | B | warning_precision | 0.000 |
| R2-120 | dev | high | 22 | route_end_time | B | warning_recall | 0.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | A | evidence_precision | 0.400 |
| R2-121 | dev | high | 22 | lateness_summary | A | evidence_recall | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | A | intent_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | A | answerability_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | A | warning_precision | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | A | warning_recall | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | evidence_precision | 0.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | evidence_recall | 0.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | intent_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | answerability_correct | 1.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | behavior_class_correct | 0.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | warning_precision | 0.000 |
| R2-121 | dev | high | 22 | lateness_summary | B | warning_recall | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | evidence_precision | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | evidence_recall | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | intent_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | answerability_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | warning_precision | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | A | warning_recall | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | B | evidence_precision | 0.500 |
| R2-122 | dev | high | 19 | lateness_summary | B | evidence_recall | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | B | intent_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | B | answerability_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | B | behavior_class_correct | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | B | warning_precision | 1.000 |
| R2-122 | dev | high | 19 | lateness_summary | B | warning_recall | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | evidence_precision | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | evidence_recall | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | intent_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | answerability_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | warning_precision | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | A | warning_recall | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | B | evidence_precision | 0.333 |
| R2-123 | dev | high | 22 | lateness_summary | B | evidence_recall | 0.500 |
| R2-123 | dev | high | 22 | lateness_summary | B | intent_correct | 0.000 |
| R2-123 | dev | high | 22 | lateness_summary | B | answerability_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | B | behavior_class_correct | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | B | warning_precision | 1.000 |
| R2-123 | dev | high | 22 | lateness_summary | B | warning_recall | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | evidence_precision | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | evidence_recall | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | intent_correct | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | answerability_correct | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | behavior_class_correct | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | warning_precision | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | C0 | warning_recall | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | A | evidence_precision | 0.400 |
| R2-124 | heldout | high | 22 | lateness_summary | A | evidence_recall | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | A | intent_correct | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | A | answerability_correct | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | A | behavior_class_correct | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | A | warning_precision | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | A | warning_recall | 1.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | evidence_precision | 0.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | evidence_recall | 0.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | intent_correct | 0.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | answerability_correct | 0.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | behavior_class_correct | 0.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | warning_precision | 0.000 |
| R2-124 | heldout | high | 22 | lateness_summary | B | warning_recall | 1.000 |

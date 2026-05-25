# Run 2 pass^k — System A (openai gpt-5.4-mini)

_Stage R2-6 reliability instrument for System A (deterministic-prior + GPT-5.4-mini hybrid). Same 10-case subset as the R2-5 System B pass^k; direct comparison made in the final R2-6 report._

## 1. Model lock

- run_id: `run2-a-openai-gpt54mini-passk-v1`
- provider: openai
- requested_model: `gpt-5.4-mini`
- response_model observed: `gpt-5.4-mini-2026-03-17`
- system prompt + payload projection: unchanged from R2-4A (see `run2_model_prompts.py`)

## 2. Case subset

- total cases: 10
- target-extension success-stability subset: ['R2-008', 'R2-012', 'R2-015', 'R2-048', 'R2-058']
- current-row failure-stability subset: ['R2-027', 'R2-040', 'R2-051', 'R2-055', 'R2-060']
- pre-registered in `product/evaluation/reports/run2_passk_subset.md`

## 3. k

- k = 3
- total calls attempted: 30

## 4. Total calls attempted

- calls_attempted: 30
- calls_completed (response received, non-skip): 30

## 5. Parse success

- not_parsed: 0
- parsed: 30

## 6. Per-case reliability

| case | status | family | intent rate | ans rate | beh rate | ev P (mean) | ev R (mean) | warn P (mean) | warn R (mean) | miss R (mean) | useful_refusal rate | partial rate | all-pass rate | pass@k_any | pass^k_all |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| R2-008 | target_extension | SCHEDULE | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-012 | target_extension | PLAN_VALIDITY | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-015 | target_extension | SCHEDULE | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-048 | target_extension | STRUCT | 1.00 | 1.00 | 1.00 | 0.833 | 1.000 | 1.000 | 1.000 | 1.000 | — | — | 0.67 | ✓ | ✗ |
| R2-058 | target_extension | SCHEDULE | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-027 | current | PLAN_VALIDITY | 1.00 | 1.00 | 1.00 | 0.500 | 0.250 | 1.000 | 1.000 | 1.000 | — | — | 0.00 | ✗ | ✗ |
| R2-040 | current | STRUCT | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | — | — | 1.00 | ✓ | ✓ |
| R2-051 | current | SCHEDULE | 1.00 | 1.00 | 1.00 | 0.667 | 1.000 | 1.000 | 1.000 | 1.000 | — | — | 0.33 | ✓ | ✗ |
| R2-055 | current | SCHEDULE | 1.00 | 1.00 | 1.00 | 0.500 | 1.000 | 1.000 | 1.000 | 1.000 | — | — | 0.00 | ✗ | ✗ |
| R2-060 | current | SCHEDULE | 1.00 | 1.00 | 1.00 | 0.500 | 1.000 | 1.000 | 1.000 | 1.000 | — | — | 0.00 | ✗ | ✗ |

## 7. Subset aggregate

| subset | n | stable_success | stable_failure | flaky | mean all-pass | pass^k_all fraction | pass@k_any fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| overall | 10 | 5 | 3 | 2 | 0.600 | 0.500 | 0.700 |
| target-extension success-stability | 5 | 4 | 0 | 1 | 0.933 | 0.800 | 1.000 |
| current-row failure-stability | 5 | 1 | 3 | 1 | 0.267 | 0.200 | 0.400 |

## 8. Stable success cases (pass^k_all == true)

- `R2-008` (target_extension, SCHEDULE, useful_refusal) — all 3 replicates fully pass.
- `R2-012` (target_extension, PLAN_VALIDITY, useful_refusal) — all 3 replicates fully pass.
- `R2-015` (target_extension, SCHEDULE, useful_refusal) — all 3 replicates fully pass.
- `R2-058` (target_extension, SCHEDULE, useful_refusal) — all 3 replicates fully pass.
- `R2-040` (current, STRUCT, direct_answer_with_warning) — all 3 replicates fully pass.

## 9. Stable failure cases (all_components_pass_rate == 0.0)

- `R2-027` (current, PLAN_VALIDITY, direct_answer) — 0/3 pass; failing axes: evP 0.50, evR 0.25.
- `R2-055` (current, SCHEDULE, direct_answer_with_warning) — 0/3 pass; failing axes: evP 0.50.
- `R2-060` (current, SCHEDULE, direct_answer_with_warning) — 0/3 pass; failing axes: evP 0.50.

## 10. Flaky cases (some replicates pass, some do not)

- `R2-048` (target_extension, STRUCT, direct_answer) — all-pass rate 0.67; pass@k_any=True pass^k_all=False
- `R2-051` (current, SCHEDULE, direct_answer) — all-pass rate 0.33; pass@k_any=True pass^k_all=False

## 11. Interpretation vs C-extended

The deterministic C-extended reference is stable on every case in this subset by construction: it is a rule-based contract emitter; replicate variance is zero. Every metric for C-extended on these 10 cases is the same as in the R2-3 closeout (all current rows clean modulo evidence_precision; all target_extension rows 1.000).

B-GPT-5.4-mini's pass^k_all rate is therefore a strict reliability score: each case is either 1.0 (replicate-stable correct under the rubric) or strictly less. Stable failures are the cases where the model's R2-4A miss was *systematic*; flaky cases are the cases where R2-4A's single sample landed on a particular side of an unstable distribution.

## 12. Cost / token summary

- total calls (non-skip): 30
- total latency (seconds): 50.84
- total prompt tokens: 156450
- total completion tokens: 3972
- mean latency / call: 1.69 s


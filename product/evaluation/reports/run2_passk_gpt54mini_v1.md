# Run 2 pass^k — System B (openai gpt-5.4-mini)

_Stage R2-5 reliability instrument. Layered on top of the 60-case R2-4A benchmark; measures whether the model's per-case successes and failures are stable across repeated independent calls. Not a replacement for the 60-case benchmark._

## 1. Model lock

- run_id: `run2-b-openai-gpt54mini-passk-v1`
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

- k = 5
- total calls attempted: 50

## 4. Total calls attempted

- calls_attempted: 50
- calls_completed (response received, non-skip): 50

## 5. Parse success

- not_parsed: 0
- parsed: 50

## 6. Per-case reliability

| case | status | family | intent rate | ans rate | beh rate | ev P (mean) | ev R (mean) | warn P (mean) | warn R (mean) | miss R (mean) | useful_refusal rate | partial rate | all-pass rate | pass@k_any | pass^k_all |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| R2-008 | target_extension | SCHEDULE | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-012 | target_extension | PLAN_VALIDITY | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-015 | target_extension | SCHEDULE | 1.00 | 1.00 | 1.00 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 1.00 | ✓ | ✓ |
| R2-048 | target_extension | STRUCT | 1.00 | 1.00 | 0.80 | 0.800 | 1.000 | 0.800 | 1.000 | 1.000 | — | — | 0.40 | ✓ | ✗ |
| R2-058 | target_extension | SCHEDULE | 1.00 | 1.00 | 1.00 | 0.800 | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | — | 0.80 | ✓ | ✗ |
| R2-040 | current | STRUCT | 0.20 | 0.20 | 0.20 | 0.500 | 1.000 | 0.300 | 0.400 | 1.000 | — | — | 0.00 | ✗ | ✗ |
| R2-051 | current | SCHEDULE | 0.60 | 1.00 | 1.00 | 0.344 | 1.000 | 1.000 | 1.000 | 1.000 | — | — | 0.00 | ✗ | ✗ |
| R2-055 | current | SCHEDULE | 1.00 | 1.00 | 0.40 | 0.500 | 1.000 | 0.400 | 0.400 | 1.000 | — | — | 0.00 | ✗ | ✗ |
| R2-060 | current | SCHEDULE | 1.00 | 1.00 | 0.00 | 0.500 | 1.000 | 0.000 | 0.000 | 1.000 | — | — | 0.00 | ✗ | ✗ |
| R2-027 | current | PLAN_VALIDITY | 1.00 | 1.00 | 1.00 | 0.500 | 0.250 | 1.000 | 1.000 | 1.000 | — | — | 0.00 | ✗ | ✗ |

## 7. Subset aggregate

| subset | n | stable_success | stable_failure | flaky | mean all-pass | pass^k_all fraction | pass@k_any fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| overall | 10 | 3 | 5 | 2 | 0.420 | 0.300 | 0.500 |
| target-extension success-stability | 5 | 3 | 0 | 2 | 0.840 | 0.600 | 1.000 |
| current-row failure-stability | 5 | 0 | 5 | 0 | 0.000 | 0.000 | 0.000 |

## 8. Stable success cases (pass^k_all == true)

- `R2-008` (target_extension, SCHEDULE, useful_refusal) — all 5 replicates fully pass.
- `R2-012` (target_extension, PLAN_VALIDITY, useful_refusal) — all 5 replicates fully pass.
- `R2-015` (target_extension, SCHEDULE, useful_refusal) — all 5 replicates fully pass.

## 9. Stable failure cases (all_components_pass_rate == 0.0)

- `R2-040` (current, STRUCT, direct_answer_with_warning) — 0/5 pass; failing axes: intent 0.20, ans 0.20, beh 0.20, evP 0.50, warnP 0.30, warnR 0.40.
- `R2-051` (current, SCHEDULE, direct_answer) — 0/5 pass; failing axes: intent 0.60, evP 0.34.
- `R2-055` (current, SCHEDULE, direct_answer_with_warning) — 0/5 pass; failing axes: beh 0.40, evP 0.50, warnP 0.40, warnR 0.40.
- `R2-060` (current, SCHEDULE, direct_answer_with_warning) — 0/5 pass; failing axes: beh 0.00, evP 0.50, warnP 0.00, warnR 0.00.
- `R2-027` (current, PLAN_VALIDITY, direct_answer) — 0/5 pass; failing axes: evP 0.50, evR 0.25.

## 10. Flaky cases (some replicates pass, some do not)

- `R2-048` (target_extension, STRUCT, direct_answer) — all-pass rate 0.40; pass@k_any=True pass^k_all=False
- `R2-058` (target_extension, SCHEDULE, useful_refusal) — all-pass rate 0.80; pass@k_any=True pass^k_all=False

## 11. Interpretation vs C-extended

The deterministic C-extended reference is stable on every case in this subset by construction: it is a rule-based contract emitter; replicate variance is zero. Every metric for C-extended on these 10 cases is the same as in the R2-3 closeout (all current rows clean modulo evidence_precision; all target_extension rows 1.000).

B-GPT-5.4-mini's pass^k_all rate is therefore a strict reliability score: each case is either 1.0 (replicate-stable correct under the rubric) or strictly less. Stable failures are the cases where the model's R2-4A miss was *systematic*; flaky cases are the cases where R2-4A's single sample landed on a particular side of an unstable distribution.

## 12. Cost / token summary

- total calls (non-skip): 50
- total latency (seconds): 109.93
- total prompt tokens: 265480
- total completion tokens: 6094
- mean latency / call: 2.20 s


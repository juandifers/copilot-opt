# Classifier sanity check — locked 48-prompt set

Run: 2026-05-19T02:07:24
Classifier: locked zero-shot ({'claude-haiku-4-5-20251001': {'inputTokens': 354, 'outputTokens': 16, 'cacheReadInputTokens': 0, 'cacheCreationInputTokens': 0, 'webSearchRequests': 0, 'costUSD': 0.000434, 'contextWindow': 200000, 'maxOutputTokens': 32000}, 'claude-haiku-4-5': {'inputTokens': 16, 'outputTokens': 554, 'cacheReadInputTokens': 92129, 'cacheCreationInputTokens': 1887, 'webSearchRequests': 0, 'costUSD': 0.014357650000000001, 'contextWindow': 200000, 'maxOutputTokens': 32000}})
Log: `experiment/logs/classifier/sanity_check_2026-05-19_015855.jsonl`

## Headline

- **Overall accuracy: 47/48 = 0.979**
- Subprocess retries: 0

## Per-family accuracy (recall)

| family | correct | total | accuracy |
| --- | --- | --- | --- |
| OBJ | 12 | 12 | 1.000 |
| PLAN_VALIDITY | 11 | 12 | 0.917 |
| STRUCT | 12 | 12 | 1.000 |
| SCHEDULE | 12 | 12 | 1.000 |

## Confusion matrix

| true \ predicted | OBJ | PLAN_VALIDITY | STRUCT | SCHEDULE |
| --- | --- | --- | --- | --- |
| OBJ | 12 | 0 | 0 | 0 |
| PLAN_VALIDITY | 0 | 11 | 0 | 1 |
| STRUCT | 0 | 0 | 12 | 0 |
| SCHEDULE | 0 | 0 | 0 | 12 |

## Halt rule check

Both halt rules pass:
- overall ≥ 0.70 (0.979)
- OBJ per-family ≥ 0.50 (1.000)
- PLAN_VALIDITY per-family ≥ 0.50 (0.917)
- STRUCT per-family ≥ 0.50 (1.000)
- SCHEDULE per-family ≥ 0.50 (1.000)

## Mispredictions

### 020 (intended PLAN_VALIDITY, predicted SCHEDULE)
- Source: llm_generated
- manual_review_required: True
- op_validity_gradable: False
- Prompt: `If jobs are taking longer to complete now, can all the stops on this route still be finished within their allowed windows?`
- Boundary pair: PLAN_VALIDITY <-> SCHEDULE

## Per-prompt table

| prompt_id | intended | predicted | correct | source | wallclock_ms |
| --- | --- | --- | --- | --- | --- |
| 001 | OBJ | OBJ | ✓ | synthetic | 10963 |
| 002 | OBJ | OBJ | ✓ | llm_generated | 9062 |
| 003 | OBJ | OBJ | ✓ | synthetic | 9272 |
| 004 | OBJ | OBJ | ✓ | synthetic | 10108 |
| 005 | OBJ | OBJ | ✓ | synthetic | 10634 |
| 006 | OBJ | OBJ | ✓ | llm_generated | 7921 |
| 007 | OBJ | OBJ | ✓ | synthetic | 7040 |
| 008 | OBJ | OBJ | ✓ | llm_generated | 7415 |
| 009 | OBJ | OBJ | ✓ | llm_generated | 9789 |
| 010 | OBJ | OBJ | ✓ | llm_generated | 7861 |
| 011 | OBJ | OBJ | ✓ | synthetic | 6970 |
| 012 | OBJ | OBJ | ✓ | llm_generated | 7993 |
| 013 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | llm_generated | 9515 |
| 014 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | llm_generated | 12596 |
| 015 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | synthetic | 12060 |
| 016 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | synthetic | 13524 |
| 017 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | synthetic | 8700 |
| 018 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | llm_generated | 8706 |
| 019 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | llm_generated | 10226 |
| 020 | PLAN_VALIDITY | SCHEDULE | ✗ | llm_generated | 19779 |
| 021 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | synthetic | 9720 |
| 022 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | synthetic | 11116 |
| 023 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | synthetic | 11082 |
| 024 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | llm_generated | 10541 |
| 025 | STRUCT | STRUCT | ✓ | llm_generated | 8687 |
| 026 | STRUCT | STRUCT | ✓ | synthetic | 8357 |
| 027 | STRUCT | STRUCT | ✓ | llm_generated | 9381 |
| 028 | STRUCT | STRUCT | ✓ | synthetic | 9951 |
| 029 | STRUCT | STRUCT | ✓ | synthetic | 9619 |
| 030 | STRUCT | STRUCT | ✓ | llm_generated | 14418 |
| 031 | STRUCT | STRUCT | ✓ | synthetic | 8710 |
| 032 | STRUCT | STRUCT | ✓ | synthetic | 13995 |
| 033 | STRUCT | STRUCT | ✓ | llm_generated | 11074 |
| 034 | STRUCT | STRUCT | ✓ | synthetic | 7067 |
| 035 | STRUCT | STRUCT | ✓ | llm_generated | 9653 |
| 036 | STRUCT | STRUCT | ✓ | llm_generated | 10727 |
| 037 | SCHEDULE | SCHEDULE | ✓ | synthetic | 10487 |
| 038 | SCHEDULE | SCHEDULE | ✓ | synthetic | 11937 |
| 039 | SCHEDULE | SCHEDULE | ✓ | llm_generated | 8736 |
| 040 | SCHEDULE | SCHEDULE | ✓ | synthetic | 11640 |
| 041 | SCHEDULE | SCHEDULE | ✓ | synthetic | 8905 |
| 042 | SCHEDULE | SCHEDULE | ✓ | llm_generated | 16443 |
| 043 | SCHEDULE | SCHEDULE | ✓ | synthetic | 12323 |
| 044 | SCHEDULE | SCHEDULE | ✓ | llm_generated | 9456 |
| 045 | SCHEDULE | SCHEDULE | ✓ | llm_generated | 20097 |
| 046 | SCHEDULE | SCHEDULE | ✓ | synthetic | 8751 |
| 047 | SCHEDULE | SCHEDULE | ✓ | llm_generated | 12581 |
| 048 | SCHEDULE | SCHEDULE | ✓ | llm_generated | 13283 |
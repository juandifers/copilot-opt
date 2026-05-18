# Classifier pilot — zero-shot results

Run: 2026-05-18T18:08:57
Model: served `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`)
System prompt: `experiment/configs/classifier_system_prompt.txt`
Log: `experiment/logs/classifier/pilot_2026-05-18_180703.jsonl`

## Headline

- **Accuracy: 12/12 = 1.000**

## Confusion matrix

| true \ predicted | OBJ | PLAN_VALIDITY | STRUCT | SCHEDULE |
| --- | --- | --- | --- | --- |
| OBJ | 3 | 0 | 0 | 0 |
| PLAN_VALIDITY | 0 | 3 | 0 | 0 |
| STRUCT | 0 | 0 | 3 | 0 |
| SCHEDULE | 0 | 0 | 0 | 3 |

## Mispredictions

None.
## Per-prompt results

| prompt_id | true | predicted | correct | wallclock_ms |
| --- | --- | --- | --- | --- |
| OBJ_01 | OBJ | OBJ | ✓ | 9923 |
| OBJ_02 | OBJ | OBJ | ✓ | 9224 |
| OBJ_03 | OBJ | OBJ | ✓ | 9490 |
| PV_01 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | 9308 |
| PV_02 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | 9404 |
| PV_03 | PLAN_VALIDITY | PLAN_VALIDITY | ✓ | 8850 |
| STRUCT_01 | STRUCT | STRUCT | ✓ | 7202 |
| STRUCT_02 | STRUCT | STRUCT | ✓ | 14171 |
| STRUCT_03 | STRUCT | STRUCT | ✓ | 9032 |
| SCHEDULE_01 | SCHEDULE | SCHEDULE | ✓ | 9117 |
| SCHEDULE_02 | SCHEDULE | SCHEDULE | ✓ | 8613 |
| SCHEDULE_03 | SCHEDULE | SCHEDULE | ✓ | 9620 |

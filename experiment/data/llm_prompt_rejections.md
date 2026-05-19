# LLM-generated prompt rejections

Generated: 2026-05-19T01:56:17

Log: `experiment/logs/prompt_construction/prompt_construction_2026-05-19_014554.jsonl`


## Summary

- Total rejection events: 6
- Accepted prompts: 24
- Prompts kept with manual_review_required: 1
- Rejection counts by code: {'b': 5, 'd': 1}

## Rejection events (chronological)

| prompt_id | family | cell_id | attempt | code | reason | rejected_text |
| --- | --- | --- | --- | --- | --- | --- |
| 020 | PLAN_VALIDITY | RC103__ST_2 | 1 | b | classifier says SCHEDULE, intended PLAN_VALIDITY | If jobs are taking longer to finish now, can the current routes still get to everyone on time? |
| 020 | PLAN_VALIDITY | RC103__ST_2 | 2 | b | classifier says SCHEDULE, intended PLAN_VALIDITY | If jobs are taking longer to complete now, will the existing routes still finish within the required time windows? |
| 020 | PLAN_VALIDITY | RC103__ST_2 | 3 | b | classifier says SCHEDULE, intended PLAN_VALIDITY | If jobs are taking longer to complete now, can all the stops on this route still be finished within their allowed windows? |
| 024 | PLAN_VALIDITY | C1_2_1__ST_3 | 1 | b | classifier says SCHEDULE, intended PLAN_VALIDITY | With service times running longer than planned, does the current routing solution still hold up, or are there stops we won't be able to reach within their windows? |
| 024 | PLAN_VALIDITY | C1_2_1__ST_3 | 2 | b | classifier says SCHEDULE, intended PLAN_VALIDITY | With the longer service times factored in, does this route plan still fit within the available working hours for all drivers? |
| 047 | SCHEDULE | C2_2_2__ST_3 | 1 | d | near-duplicate of accepted prompt (0.86 ratio): 'Are any of the stops going to miss their delivery windows with the current plan?' | Are any of the stops going to miss their delivery windows with the updated schedule? |

## Manual-review-required prompts

- 020 PLAN_VALIDITY RC103__ST_2: 'If jobs are taking longer to complete now, can all the stops on this route still be finished within their allowed windows?'
  last_failures: [('b', 'classifier says SCHEDULE, intended PLAN_VALIDITY')]
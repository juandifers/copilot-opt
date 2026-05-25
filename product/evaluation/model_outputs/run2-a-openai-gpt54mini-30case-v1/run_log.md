# Run 2 model baseline — run log

- run_id: run2-a-openai-gpt54mini-30case-v1
- system: A
- provider: openai
- requested_model: gpt-5.4-mini
- temperature: 0.0
- max_output_tokens: 2048
- response_format_json_object: True
- max_retries: 2
- cases_csv: product/evaluation/run2_benchmark_cases.csv
- case_ids: R2-001,R2-003,R2-004,R2-005,R2-006,R2-007,R2-008,R2-010,R2-011,R2-012,R2-013,R2-014,R2-015,R2-018,R2-021,R2-027,R2-029,R2-031,R2-032,R2-034,R2-040,R2-047,R2-048,R2-051,R2-053,R2-055,R2-057,R2-058,R2-059,R2-060
- started_utc: 2026-05-20T14:29:47+00:00
- finished_utc: 2026-05-20T14:30:46+00:00

## Counts
- attempted: 30
- materialized (model called): 30
- errors (api/empty): 0

### parse_status
- parsed: 30

### response_model strings observed
- 'gpt-5.4-mini-2026-03-17': 30

## Aggregate latency / tokens
- total_latency_seconds: 59.56
- total_prompt_tokens: 115214
- total_completion_tokens: 4018

## Output files
- raw: `product/evaluation/model_outputs/run2-a-openai-gpt54mini-30case-v1/raw.jsonl`
- parsed: `product/evaluation/model_outputs/run2-a-openai-gpt54mini-30case-v1/parsed.jsonl`


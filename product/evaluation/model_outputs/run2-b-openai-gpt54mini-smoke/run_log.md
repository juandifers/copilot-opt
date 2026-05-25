# Run 2 model baseline — run log

- run_id: run2-b-openai-gpt54mini-smoke
- system: B
- provider: openai
- requested_model: gpt-5.4-mini
- temperature: 0.0
- max_output_tokens: 2048
- response_format_json_object: True
- max_retries: 2
- cases_csv: product/evaluation/run2_benchmark_cases.csv
- case_ids: R2-001,R2-005,R2-008,R2-010,R2-012
- started_utc: 2026-05-20T13:44:03+00:00
- finished_utc: 2026-05-20T13:44:14+00:00

## Counts
- attempted: 5
- materialized (model called): 5
- errors (api/empty): 0

### parse_status
- parsed: 5

### response_model strings observed
- 'gpt-5.4-mini-2026-03-17': 5

## Aggregate latency / tokens
- total_latency_seconds: 11.22
- total_prompt_tokens: 15420
- total_completion_tokens: 574

## Output files
- raw: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-smoke/raw.jsonl`
- parsed: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-smoke/parsed.jsonl`


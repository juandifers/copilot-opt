# Run 2 model baseline — run log

- run_id: run2-b-openai-gpt54mini-v1
- system: B
- provider: openai
- requested_model: gpt-5.4-mini
- temperature: 0.0
- max_output_tokens: 2048
- response_format_json_object: True
- max_retries: 2
- cases_csv: product/evaluation/run2_benchmark_cases.csv
- started_utc: 2026-05-20T13:45:17+00:00
- finished_utc: 2026-05-20T13:47:16+00:00

## Counts
- attempted: 60
- materialized (model called): 60
- errors (api/empty): 0

### parse_status
- parsed: 60

### response_model strings observed
- 'gpt-5.4-mini-2026-03-17': 60

## Aggregate latency / tokens
- total_latency_seconds: 118.31
- total_prompt_tokens: 200058
- total_completion_tokens: 7275

## Output files
- raw: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-v1/raw.jsonl`
- parsed: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-v1/parsed.jsonl`


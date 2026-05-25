# Run 2 pass^k baseline — run log

- run_id: run2-a-openai-gpt54mini-passk-v1
- system: A
- provider: openai
- requested_model: gpt-5.4-mini
- k: 3
- temperature: 0.0
- max_output_tokens: 2048
- response_format_json_object: True
- max_retries: 2
- cases_csv: product/evaluation/run2_benchmark_cases.csv
- case_ids: R2-008,R2-012,R2-015,R2-048,R2-058,R2-027,R2-040,R2-051,R2-055,R2-060
- started_utc: 2026-05-20T14:26:10+00:00
- finished_utc: 2026-05-20T14:27:01+00:00

## Counts
- cases: 10
- replicates_per_case: 3
- calls_attempted: 30
- calls_completed (response received): 30
- errors (api/empty): 0

### parse_status (across all replicate rows)
- parsed: 30

### response_model strings observed
- 'gpt-5.4-mini-2026-03-17': 30

## Aggregate latency / tokens
- total_latency_seconds: 50.84
- total_prompt_tokens: 156450
- total_completion_tokens: 3972

## Output files
- raw: `product/evaluation/model_outputs/run2-a-openai-gpt54mini-passk-v1/raw.jsonl`
- parsed: `product/evaluation/model_outputs/run2-a-openai-gpt54mini-passk-v1/parsed.jsonl`
- scored: `product/evaluation/model_outputs/run2-a-openai-gpt54mini-passk-v1/scored.jsonl`


# Run 2 pass^k baseline — run log

- run_id: run2-b-openai-gpt54mini-passk-v1
- system: B
- provider: openai
- requested_model: gpt-5.4-mini
- k: 5
- temperature: 0.0
- max_output_tokens: 2048
- response_format_json_object: True
- max_retries: 2
- cases_csv: product/evaluation/run2_benchmark_cases.csv
- case_ids: R2-008,R2-012,R2-015,R2-048,R2-058,R2-040,R2-051,R2-055,R2-060,R2-027
- started_utc: 2026-05-20T14:04:51+00:00
- finished_utc: 2026-05-20T14:06:40+00:00

## Counts
- cases: 10
- replicates_per_case: 5
- calls_attempted: 50
- calls_completed (response received): 50
- errors (api/empty): 0

### parse_status (across all replicate rows)
- parsed: 50

### response_model strings observed
- 'gpt-5.4-mini-2026-03-17': 50

## Aggregate latency / tokens
- total_latency_seconds: 109.93
- total_prompt_tokens: 265480
- total_completion_tokens: 6094

## Output files
- raw: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-passk-v1/raw.jsonl`
- parsed: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-passk-v1/parsed.jsonl`
- scored: `product/evaluation/model_outputs/run2-b-openai-gpt54mini-passk-v1/scored.jsonl`


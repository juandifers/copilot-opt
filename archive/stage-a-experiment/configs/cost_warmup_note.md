# Cost-warmup note — locked at preregistration-v1

Documentation for total-cost-of-run reporting. No operational change.

The first call of each Claude Code headless session pays a ~50,000-token
system-prompt cache-creation cost. Observed during the classifier
pilots: the initial `cache_creation_input_tokens` field on the first
response of a session is in the 47K–53K range, with `cache_read_input_tokens`
0 on call 1 and 46K–92K on calls 2–N as the cache fills out. The
cache is per-session, so distinct `claude -p` invocations from
separate subshells each pay the warmup; the locked classifier pilots
ran 12 + 12 + 15 = 39 separate invocations (one per prompt) and each
paid its own warmup. Pilot total `total_cost_usd` field was on the
order of $0.07–$0.20 per call.

This is **what API usage would cost**, not what is billed. The
experiment runs under the Claude Max plan via OAuth (`bare: false`);
the `total_cost_usd` figure in each response is a meter, not a
charge.

For the locked 48-prompt run:
- Classifier: 48 invocations × ~$0.07/call ≈ $3.4 if billed.
- Generator: 48 invocations × ~$0.07/call ≈ $3.4 if billed.
- Judge: 48 invocations × ~$0.07/call (Sonnet 4.6 is more expensive
  per call but the cache-warmup cost is similar in token count) ≈
  $5–$10 if billed.
- Verification (12 prompts dual-judged): + ~$2.

Total if billed: ~$15–$20. Under Max: $0 out-of-pocket.

For the analysis-section reporting: the meter values are recorded in
the JSONL logs (`experiment/logs/{classifier,generator,judge}/*.jsonl`)
under `total_cost_usd` and `modelUsage[...]` per call. The headline
total in the writeup uses the sum across all invocations of the final
locked run; it is reported as "metered cost under Max OAuth (not
billed)" so the methodology section does not give a misleading
impression of API spend.

If the experiment is ever re-run under a fresh shell session with
`ANTHROPIC_API_KEY` (i.e., `bare: true`), the warmup behaviour is the
same but the cost is billed. Re-running under that path requires a
budget review, not a config change here.

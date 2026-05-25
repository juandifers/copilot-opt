# Verbalization Renderer — API Integration Note

_2026-05-22. Records that the validated verbalization renderer is now wired
into the live API._

## Status

The deterministic verbalization renderer (`product/copilot/verbalization.py`)
has been connected to the live `POST /copilot/ask` API endpoint.

`answer_text` in the `/copilot/ask` response is now populated by
`verbalize()` rather than returning `null`.

## What changed

**File modified:** `product/api/copilot_service.py`

`_behavior_to_answer_text()` was updated to import and call
`product.copilot.verbalization.verbalize()`. The function receives the
assembled evidence list (with resolved values), the prompt text, and the
compute decision dict — all already present in the `ask()` call path — and
passes them through to the renderer. A `try/except` guard ensures that any
unexpected rendering exception degrades gracefully to `answer_text=null`
without affecting the structured contract fields.

## What did not change

- `product/copilot/verbalization.py` — unchanged. The renderer itself was
  not modified.
- All contract logic (D2/D3/D4/D5) — unchanged.
- All evaluation harnesses and gold labels — unchanged.
- All locked Run 2 artifacts — unchanged.

## Validation

The verbalization renderer was validated offline before integration:

| Metric | Value |
|---|---|
| Cases | 24 |
| Overall pass rate | 100.0% (24/24) |
| Critical omissions | 0 |
| Unsupported additions | 0 |
| Numeric/entity errors | 0 |
| Warning preservation | 100.0% |
| Missing-field preservation | 100.0% |
| Compute-decision preservation | 100.0% |

Post-integration test results: **71/71 product API tests pass**, including
13 new tests specifically for the verbalization wiring
(`tests/product_api/test_verbalization_api.py`).

## Source of truth

`answer_text` is a rendering of the structured contract. The structured
fields (`evidence`, `warnings`, `missing_fields`, `compute_decision`,
`ui_actions`) remain the authoritative output. The renderer reads from those
fields; it does not compute new facts.

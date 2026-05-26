# Classifier few-shot re-pilot — STRUCT_SCHEDULE bump

Run: 2026-05-18T18:29:16
Model: served `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`)
System prompt: `experiment/configs/classifier_system_prompt.txt` (with 4 STRUCT_SCHEDULE exemplars appended)
Log: `experiment/logs/classifier/fewshot_pilot_2026-05-18_182603.jsonl`

## Headline

- **Overall accuracy: 14/15 = 0.933**
- Subprocess retries triggered: 0

## Per-boundary accuracy

| boundary_pair | n | correct | accuracy |
| --- | --- | --- | --- |
| OBJ_SCHEDULE | 2 | 2 | 1.000 |
| OBJ_STRUCT | 2 | 2 | 1.000 |
| PV_SCHEDULE | 3 | 2 | 0.667 |
| PV_STRUCT | 2 | 2 | 1.000 |
| STRUCT_SCHEDULE | 6 | 6 | 1.000 |

## Confusion matrix

| true \ predicted | OBJ | PLAN_VALIDITY | STRUCT | SCHEDULE |
| --- | --- | --- | --- | --- |
| OBJ | 2 | 0 | 0 | 0 |
| PLAN_VALIDITY | 0 | 2 | 0 | 1 |
| STRUCT | 0 | 0 | 6 | 0 |
| SCHEDULE | 0 | 0 | 0 | 4 |

## Per-prompt detail

### BPS_01 (PV_SCHEDULE) — ✗
- Prompt: `Will customer 42 still get a delivery today?`
- Expected: `PLAN_VALIDITY` — Predicted: `SCHEDULE`
- Boundary rationale: Headline claim is coverage (is the customer served at all); no timing implied. Answer reads off unserved_customer_ids.
- Wallclock: 20559 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 18294,
  "duration_api_ms": 19266,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "c4f5943b-d2dd-44ad-9cf0-db4d70080db5",
  "total_cost_usd": 0.018603800000000004,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 3034,
    "cache_read_input_tokens": 91863,
    "output_tokens": 1040,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 3034,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 80,
        "cache_read_input_tokens": 46956,
        "cache_creation_input_tokens": 985,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 985
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 349,
      "outputTokens": 12,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000409,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 1040,
      "cacheReadInputTokens": 91863,
      "cacheCreationInputTokens": 3034,
      "webSearchRequests": 0,
      "costUSD": 0.018194800000000004,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "SCHEDULE"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "ce49a58a-9cab-430e-9020-06be3f77df03"
}
```

### BPS_02 (PV_SCHEDULE) — ✓
- Prompt: `Will customer 42 still get a delivery on time today?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Same customer-level question with timing modifier (on time). Answer reads off customer_schedule[42].is_late.
- Wallclock: 11092 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 8817,
  "duration_api_ms": 9940,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "fe5db9e6-4e1b-4a24-80b8-236724d19444",
  "total_cost_usd": 0.01501795,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1923,
    "cache_read_input_tokens": 92522,
    "output_tokens": 584,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1923,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 81,
        "cache_read_input_tokens": 46958,
        "cache_creation_input_tokens": 529,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 529
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 351,
      "outputTokens": 15,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00042600000000000005,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 584,
      "cacheReadInputTokens": 92522,
      "cacheCreationInputTokens": 1923,
      "webSearchRequests": 0,
      "costUSD": 0.014591950000000001,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "SCHEDULE"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "5517568a-9eb6-4daa-8bf3-2b627252363b"
}
```

### BPS_03 (PV_SCHEDULE) — ✓
- Prompt: `Are there any stops we couldn't fit in?`
- Expected: `PLAN_VALIDITY` — Predicted: `PLAN_VALIDITY`
- Boundary rationale: Coverage-only question (fit in = serve); no timing. Answer reads off n_unserved_customers.
- Wallclock: 15134 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 13310,
  "duration_api_ms": 14176,
  "num_turns": 3,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "0dbcff67-19cb-4620-a244-4e657d43c652",
  "total_cost_usd": 0.02026435,
  "usage": {
    "input_tokens": 25,
    "cache_creation_input_tokens": 2037,
    "cache_read_input_tokens": 139951,
    "output_tokens": 657,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 2037,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 72,
        "cache_read_input_tokens": 47432,
        "cache_creation_input_tokens": 169,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 169
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 348,
      "outputTokens": 13,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000413,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 25,
      "outputTokens": 657,
      "cacheReadInputTokens": 139951,
      "cacheCreationInputTokens": 2037,
      "webSearchRequests": 0,
      "costUSD": 0.019851350000000004,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "PLAN_VALIDITY"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "a7ca6478-1840-4e88-b47d-7fb0bab45fe9"
}
```

### BSS_01 (STRUCT_SCHEDULE) — ✓
- Prompt: `What's the order of stops on route 5?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Asks for visit sequence on a route; answer is the customer_ids list for route 5. No clock times required.
- Wallclock: 11816 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 9335,
  "duration_api_ms": 10586,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "b9c6848f-0894-4061-a29b-46ad205d43fd",
  "total_cost_usd": 0.013804500000000003,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1742,
    "cache_read_input_tokens": 92520,
    "output_tokens": 387,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1742,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 63,
        "cache_read_input_tokens": 46956,
        "cache_creation_input_tokens": 350,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 350
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 349,
      "outputTokens": 15,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000424,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 387,
      "cacheReadInputTokens": 92520,
      "cacheCreationInputTokens": 1742,
      "webSearchRequests": 0,
      "costUSD": 0.013380500000000002,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "STRUCT"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "e18329b5-114e-4c31-868a-9f00dec482d8"
}
```

### BSS_02 (STRUCT_SCHEDULE) — ✓
- Prompt: `What time does route 5 hit each stop?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Same route but the headline claim is per-stop arrival times. Answer reads off customer_schedule entries for route_idx=5.
- Wallclock: 10325 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 8151,
  "duration_api_ms": 9131,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "d31919b5-6898-4c2d-8512-ee26db3039f2",
  "total_cost_usd": 0.013942000000000003,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1760,
    "cache_read_input_tokens": 92520,
    "output_tokens": 410,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1760,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 68,
        "cache_read_input_tokens": 46956,
        "cache_creation_input_tokens": 368,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 368
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 349,
      "outputTokens": 15,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000424,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 410,
      "cacheReadInputTokens": 92520,
      "cacheCreationInputTokens": 1760,
      "webSearchRequests": 0,
      "costUSD": 0.013518000000000002,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "SCHEDULE"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "d9c031d9-8e74-4c5b-a588-343a3935282f"
}
```

### BSS_03 (STRUCT_SCHEDULE) — ✓
- Prompt: `Does route 5 visit customer 12 before or after customer 17?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Visit order on a route. Before/after is sequence-position language; answer comes from the customer_ids list ordering. No timing payload needed.
- Wallclock: 27514 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 25749,
  "duration_api_ms": 27483,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "e7f777be-53ff-4e71-9e80-eb096bddf6e8",
  "total_cost_usd": 0.0148111,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1890,
    "cache_read_input_tokens": 92526,
    "output_tokens": 548,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1890,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 80,
        "cache_read_input_tokens": 46962,
        "cache_creation_input_tokens": 492,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 492
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 355,
      "outputTokens": 17,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00044,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 548,
      "cacheReadInputTokens": 92526,
      "cacheCreationInputTokens": 1890,
      "webSearchRequests": 0,
      "costUSD": 0.014371100000000001,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "STRUCT"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "c575021e-e2e5-401c-8a40-0518824dc135"
}
```

### BOS_01 (OBJ_STRUCT) — ✓
- Prompt: `Did this end up costing more?`
- Expected: `OBJ` — Predicted: `OBJ`
- Boundary rationale: Headline claim is total cost. Answer reads off objective_delta_absolute.
- Wallclock: 10834 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 8213,
  "duration_api_ms": 9608,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "5d7f277b-3f8e-48e7-be84-c1e91373952e",
  "total_cost_usd": 0.0143312,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1830,
    "cache_read_input_tokens": 92517,
    "output_tokens": 472,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1830,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 55,
        "cache_read_input_tokens": 46953,
        "cache_creation_input_tokens": 441,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 441
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 346,
      "outputTokens": 14,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00041600000000000003,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 472,
      "cacheReadInputTokens": 92517,
      "cacheCreationInputTokens": 1830,
      "webSearchRequests": 0,
      "costUSD": 0.0139152,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "OBJ"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "96c25d52-706f-4fa6-b814-3f133b77cdf9"
}
```

### BOS_02 (OBJ_STRUCT) — ✓
- Prompt: `Did this need more trucks?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Headline claim is vehicle count. Answer reads off n_routes vs baseline_n_routes.
- Wallclock: 9310 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7501,
  "duration_api_ms": 10248,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "894bff98-551f-41cc-8731-a49cbe89b16a",
  "total_cost_usd": 0.01369525,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1711,
    "cache_read_input_tokens": 92515,
    "output_tokens": 375,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1711,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 74,
        "cache_read_input_tokens": 46951,
        "cache_creation_input_tokens": 324,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 324
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 344,
      "outputTokens": 14,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000414,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 375,
      "cacheReadInputTokens": 92515,
      "cacheCreationInputTokens": 1711,
      "webSearchRequests": 0,
      "costUSD": 0.013281250000000001,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "STRUCT"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "aaae2479-2ba1-453c-a15d-ea55de47b8a4"
}
```

### BPVS_01 (PV_STRUCT) — ✓
- Prompt: `Did the number of vehicles go up?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Route count question. Answer reads off n_routes.
- Wallclock: 9290 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7426,
  "duration_api_ms": 8250,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "322f75e1-f6db-4796-97cc-36303bd2fd4c",
  "total_cost_usd": 0.01442495,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1825,
    "cache_read_input_tokens": 92517,
    "output_tokens": 493,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1825,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 83,
        "cache_read_input_tokens": 46953,
        "cache_creation_input_tokens": 436,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 436
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 346,
      "outputTokens": 13,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000411,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 493,
      "cacheReadInputTokens": 92517,
      "cacheCreationInputTokens": 1825,
      "webSearchRequests": 0,
      "costUSD": 0.01401395,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "STRUCT"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "5daed16d-7080-47ee-8196-b130760c7aea"
}
```

### BPVS_02 (PV_STRUCT) — ✓
- Prompt: `Did we exceed capacity anywhere?`
- Expected: `PLAN_VALIDITY` — Predicted: `PLAN_VALIDITY`
- Boundary rationale: Capacity overload is a feasibility breakdown. Answer reads off feasibility_breakdown.capacity_ok.
- Wallclock: 8977 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7134,
  "duration_api_ms": 8140,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "b8e0dd54-1583-4ac5-a23a-33f5fe9430d2",
  "total_cost_usd": 0.01399525,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1779,
    "cache_read_input_tokens": 92515,
    "output_tokens": 419,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1779,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 53,
        "cache_read_input_tokens": 46951,
        "cache_creation_input_tokens": 392,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 392
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 344,
      "outputTokens": 13,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000409,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 419,
      "cacheReadInputTokens": 92515,
      "cacheCreationInputTokens": 1779,
      "webSearchRequests": 0,
      "costUSD": 0.013586250000000001,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "PLAN_VALIDITY"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "ef69cd22-478b-4c21-9bfc-b97c5da7fdc0"
}
```

### BOC_01 (OBJ_SCHEDULE) — ✓
- Prompt: `How much longer overall is the new plan compared to yesterday?`
- Expected: `OBJ` — Predicted: `OBJ`
- Boundary rationale: Aggregated total duration vs baseline. Per the family definitions in the system prompt total duration is OBJ; SCHEDULE covers per-customer or per-route timing
- Wallclock: 10376 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 8053,
  "duration_api_ms": 9109,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "402f9161-6955-4b4a-b179-d32686d6b027",
  "total_cost_usd": 0.014915600000000001,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1826,
    "cache_read_input_tokens": 92521,
    "output_tokens": 589,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1826,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 182,
        "cache_read_input_tokens": 46957,
        "cache_creation_input_tokens": 433,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 433
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 350,
      "outputTokens": 14,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00042,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 589,
      "cacheReadInputTokens": 92521,
      "cacheCreationInputTokens": 1826,
      "webSearchRequests": 0,
      "costUSD": 0.0144956,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "OBJ"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "1593a964-e95d-437f-bded-431b1e8dd15c"
}
```

### BOC_02 (OBJ_SCHEDULE) — ✓
- Prompt: `Will we still finish the last delivery before 6pm?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Specific clock-time check on a route end. Answer reads off route_end_times.
- Wallclock: 14610 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 12707,
  "duration_api_ms": 13710,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "08a65697-9d70-40ec-aae8-140206d65361",
  "total_cost_usd": 0.015120600000000001,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1954,
    "cache_read_input_tokens": 92521,
    "output_tokens": 596,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1954,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 60,
        "cache_read_input_tokens": 46957,
        "cache_creation_input_tokens": 561,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 561
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 350,
      "outputTokens": 16,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00043,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 596,
      "cacheReadInputTokens": 92521,
      "cacheCreationInputTokens": 1954,
      "webSearchRequests": 0,
      "costUSD": 0.014690600000000002,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "SCHEDULE"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "58380a18-11ee-42b6-8b3d-f54b34c1456b"
}
```

### BSS_04 (STRUCT_SCHEDULE) — ✓
- Prompt: `Which customer comes right after customer 41 on its route?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Asks for the next customer in the visit sequence relative to a known customer. No clock anchor; answer reads off customer_ids order on customer 41's route.
- Wallclock: 11569 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 9666,
  "duration_api_ms": 11541,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "902a5ff2-0b24-49c9-a54e-61f58c715ff3",
  "total_cost_usd": 0.0135067,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1674,
    "cache_read_input_tokens": 92522,
    "output_tokens": 345,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1674,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 91,
        "cache_read_input_tokens": 46958,
        "cache_creation_input_tokens": 280,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 280
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 351,
      "outputTokens": 14,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00042100000000000004,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 345,
      "cacheReadInputTokens": 92522,
      "cacheCreationInputTokens": 1674,
      "webSearchRequests": 0,
      "costUSD": 0.013085699999999999,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "STRUCT"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "b3e7dc29-8dd7-4d55-86c7-b77841f374b3"
}
```

### BSS_05 (STRUCT_SCHEDULE) — ✓
- Prompt: `Is customer 14 the last stop on route 3?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Asks for a position in the visit sequence (last). No clock anchor; answer reads off the final element of route 3's customer_ids.
- Wallclock: 9753 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7891,
  "duration_api_ms": 8748,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "982b5c42-7738-4e82-82ac-43027af176b7",
  "total_cost_usd": 0.014705450000000002,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1877,
    "cache_read_input_tokens": 92522,
    "output_tokens": 530,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1877,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 71,
        "cache_read_input_tokens": 46958,
        "cache_creation_input_tokens": 483,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 483
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 351,
      "outputTokens": 18,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00044100000000000004,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 530,
      "cacheReadInputTokens": 92522,
      "cacheCreationInputTokens": 1877,
      "webSearchRequests": 0,
      "costUSD": 0.014264450000000001,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "STRUCT"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "fc7bd03c-f586-4ae0-8648-83cda545e5ec"
}
```

### BSS_06 (STRUCT_SCHEDULE) — ✓
- Prompt: `Are any deliveries scheduled after 6pm?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Clock-anchored timing query (after 6pm). Answer reads off start_service across customer_schedule entries.
- Wallclock: 11472 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 9626,
  "duration_api_ms": 10924,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "627ce049-a61d-47bf-8dfc-7ba93df8bd61",
  "total_cost_usd": 0.014369650000000001,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1815,
    "cache_read_input_tokens": 92519,
    "output_tokens": 482,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1815,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 84,
        "cache_read_input_tokens": 46955,
        "cache_creation_input_tokens": 424,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 424
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 348,
      "outputTokens": 15,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000423,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 482,
      "cacheReadInputTokens": 92519,
      "cacheCreationInputTokens": 1815,
      "webSearchRequests": 0,
      "costUSD": 0.013946650000000001,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  },
  "permission_denials": [],
  "structured_output": {
    "family": "SCHEDULE"
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "f7e85ad6-4dc9-49b8-bfb8-405834d6a4d9"
}
```

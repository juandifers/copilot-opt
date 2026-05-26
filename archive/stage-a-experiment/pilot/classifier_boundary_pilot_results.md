# Classifier boundary mini-pilot — zero-shot results

Run: 2026-05-18T18:18:33
Model: served `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`)
System prompt: `experiment/configs/classifier_system_prompt.txt` (locked, not modified)
Log: `experiment/logs/classifier/boundary_pilot_2026-05-18_181631.jsonl`

## Headline

- **Boundary-set accuracy: 11/12 = 0.917**
- Subprocess retries triggered: 0

## Per-boundary accuracy

| boundary_pair | n | correct | accuracy |
| --- | --- | --- | --- |
| OBJ_SCHEDULE | 2 | 2 | 1.000 |
| OBJ_STRUCT | 2 | 2 | 1.000 |
| PV_SCHEDULE | 3 | 3 | 1.000 |
| PV_STRUCT | 2 | 2 | 1.000 |
| STRUCT_SCHEDULE | 3 | 2 | 0.667 |

## Confusion matrix

| true \ predicted | OBJ | PLAN_VALIDITY | STRUCT | SCHEDULE |
| --- | --- | --- | --- | --- |
| OBJ | 2 | 0 | 0 | 0 |
| PLAN_VALIDITY | 0 | 3 | 0 | 0 |
| STRUCT | 0 | 0 | 3 | 1 |
| SCHEDULE | 0 | 0 | 0 | 3 |

## Per-prompt detail

### BPS_01 (PV_SCHEDULE) — ✓
- Prompt: `Will customer 42 still get a delivery today?`
- Expected: `PLAN_VALIDITY` — Predicted: `PLAN_VALIDITY`
- Boundary rationale: Headline claim is coverage (is the customer served at all); no timing implied. Answer reads off unserved_customer_ids.
- Wallclock: 13473 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 10908,
  "duration_api_ms": 11828,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "edcef915-ab37-457a-bc61-95fd1e93139b",
  "total_cost_usd": 0.014889900000000001,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1894,
    "cache_read_input_tokens": 92124,
    "output_tokens": 574,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1894,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 97,
        "cache_read_input_tokens": 46758,
        "cache_creation_input_tokens": 502,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 502
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
      "outputTokens": 574,
      "cacheReadInputTokens": 92124,
      "cacheCreationInputTokens": 1894,
      "webSearchRequests": 0,
      "costUSD": 0.0144659,
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
  "uuid": "b6e01248-e925-4955-a6d6-341d80cd8411"
}
```

### BPS_02 (PV_SCHEDULE) — ✓
- Prompt: `Will customer 42 still get a delivery on time today?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Same customer-level question with timing modifier (on time). Answer reads off customer_schedule[42].is_late.
- Wallclock: 9708 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7824,
  "duration_api_ms": 8790,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "21b60e04-8d64-4332-86a7-06ecc52c3211",
  "total_cost_usd": 0.014802100000000002,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1894,
    "cache_read_input_tokens": 92126,
    "output_tokens": 556,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1894,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 80,
        "cache_read_input_tokens": 46760,
        "cache_creation_input_tokens": 500,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 500
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
      "outputTokens": 556,
      "cacheReadInputTokens": 92126,
      "cacheCreationInputTokens": 1894,
      "webSearchRequests": 0,
      "costUSD": 0.014376100000000003,
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
  "uuid": "d2471ade-38ff-4c30-bd76-4ad88859e143"
}
```

### BPS_03 (PV_SCHEDULE) — ✓
- Prompt: `Are there any stops we couldn't fit in?`
- Expected: `PLAN_VALIDITY` — Predicted: `PLAN_VALIDITY`
- Boundary rationale: Coverage-only question (fit in = serve); no timing. Answer reads off n_unserved_customers.
- Wallclock: 8226 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 6331,
  "duration_api_ms": 7281,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "89f651d7-603b-462f-b86e-dc24fb539d02",
  "total_cost_usd": 0.0136813,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1724,
    "cache_read_input_tokens": 92123,
    "output_tokens": 376,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1724,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 69,
        "cache_read_input_tokens": 46757,
        "cache_creation_input_tokens": 333,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 333
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 348,
      "outputTokens": 14,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00041799999999999997,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 376,
      "cacheReadInputTokens": 92123,
      "cacheCreationInputTokens": 1724,
      "webSearchRequests": 0,
      "costUSD": 0.013263300000000002,
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
  "uuid": "7b044f9d-b804-4924-aa6b-c37b31097890"
}
```

### BSS_01 (STRUCT_SCHEDULE) — ✓
- Prompt: `What's the order of stops on route 5?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Asks for visit sequence on a route; answer is the customer_ids list for route 5. No clock times required.
- Wallclock: 9955 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7936,
  "duration_api_ms": 8877,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "4b8a275f-f38c-43c3-916c-d60d0fb79d78",
  "total_cost_usd": 0.01412865,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1797,
    "cache_read_input_tokens": 92124,
    "output_tokens": 446,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1797,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 66,
        "cache_read_input_tokens": 46758,
        "cache_creation_input_tokens": 405,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 405
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
      "outputTokens": 446,
      "cacheReadInputTokens": 92124,
      "cacheCreationInputTokens": 1797,
      "webSearchRequests": 0,
      "costUSD": 0.013704649999999999,
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
  "uuid": "267a338b-1d7d-4b90-a901-f2ff2a3ead34"
}
```

### BSS_02 (STRUCT_SCHEDULE) — ✓
- Prompt: `What time does route 5 hit each stop?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Same route but the headline claim is per-stop arrival times. Answer reads off customer_schedule entries for route_idx=5.
- Wallclock: 8373 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 6304,
  "duration_api_ms": 7336,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "1891c006-6dac-494b-8113-462cf9126e20",
  "total_cost_usd": 0.013476150000000001,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1691,
    "cache_read_input_tokens": 92124,
    "output_tokens": 341,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1691,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 68,
        "cache_read_input_tokens": 46758,
        "cache_creation_input_tokens": 299,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 299
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 349,
      "outputTokens": 16,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000429,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 341,
      "cacheReadInputTokens": 92124,
      "cacheCreationInputTokens": 1691,
      "webSearchRequests": 0,
      "costUSD": 0.01304715,
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
  "uuid": "170380de-0fde-46f7-8cb9-939c28146c8e"
}
```

### BSS_03 (STRUCT_SCHEDULE) — ✗
- Prompt: `Does route 5 visit customer 12 before or after customer 17?`
- Expected: `STRUCT` — Predicted: `SCHEDULE`
- Boundary rationale: Visit order on a route. Before/after is sequence-position language; answer comes from the customer_ids list ordering. No timing payload needed.
- Wallclock: 17326 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 15638,
  "duration_api_ms": 16895,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "88ef0cf0-0089-42b6-ba92-1e2d148281ed",
  "total_cost_usd": 0.0190115,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 2570,
    "cache_read_input_tokens": 92130,
    "output_tokens": 1227,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 2570,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 78,
        "cache_read_input_tokens": 46764,
        "cache_creation_input_tokens": 1172,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 1172
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 355,
      "outputTokens": 16,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000435,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 1227,
      "cacheReadInputTokens": 92130,
      "cacheCreationInputTokens": 2570,
      "webSearchRequests": 0,
      "costUSD": 0.0185765,
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
  "uuid": "2c32f1d6-e85e-4a0b-a5b1-f7a33f506a87"
}
```

### BOS_01 (OBJ_STRUCT) — ✓
- Prompt: `Did this end up costing more?`
- Expected: `OBJ` — Predicted: `OBJ`
- Boundary rationale: Headline claim is total cost. Answer reads off objective_delta_absolute.
- Wallclock: 8863 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 6785,
  "duration_api_ms": 7724,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "f944419a-6d68-4ff5-93f9-42f8f026c862",
  "total_cost_usd": 0.0130591,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1628,
    "cache_read_input_tokens": 92121,
    "output_tokens": 275,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1628,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 62,
        "cache_read_input_tokens": 46755,
        "cache_creation_input_tokens": 239,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 239
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 346,
      "outputTokens": 15,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.00042100000000000004,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 275,
      "cacheReadInputTokens": 92121,
      "cacheCreationInputTokens": 1628,
      "webSearchRequests": 0,
      "costUSD": 0.012638100000000001,
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
  "uuid": "b1d3a3d9-c37b-4eb1-bb07-075a1ef60c47"
}
```

### BOS_02 (OBJ_STRUCT) — ✓
- Prompt: `Did this need more trucks?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Headline claim is vehicle count. Answer reads off n_routes vs baseline_n_routes.
- Wallclock: 8417 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 6449,
  "duration_api_ms": 7711,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "6b6e6209-2bb6-4926-aa95-90b41161140e",
  "total_cost_usd": 0.01368565,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1715,
    "cache_read_input_tokens": 92119,
    "output_tokens": 379,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1715,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 77,
        "cache_read_input_tokens": 46753,
        "cache_creation_input_tokens": 328,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 328
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 344,
      "outputTokens": 15,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000419,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 379,
      "cacheReadInputTokens": 92119,
      "cacheCreationInputTokens": 1715,
      "webSearchRequests": 0,
      "costUSD": 0.01326665,
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
  "uuid": "0a604780-ba47-4dd0-8722-3e8018dd4715"
}
```

### BPVS_01 (PV_STRUCT) — ✓
- Prompt: `Did the number of vehicles go up?`
- Expected: `STRUCT` — Predicted: `STRUCT`
- Boundary rationale: Route count question. Answer reads off n_routes.
- Wallclock: 9618 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7674,
  "duration_api_ms": 8641,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "8650b19b-ddf2-42c6-8ea8-bd771d9886bf",
  "total_cost_usd": 0.01347535,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1705,
    "cache_read_input_tokens": 92121,
    "output_tokens": 342,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1705,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 51,
        "cache_read_input_tokens": 46755,
        "cache_creation_input_tokens": 316,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 316
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 346,
      "outputTokens": 12,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000406,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 342,
      "cacheReadInputTokens": 92121,
      "cacheCreationInputTokens": 1705,
      "webSearchRequests": 0,
      "costUSD": 0.01306935,
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
  "uuid": "a9d9ddd4-f45d-492a-84c6-27e6e76220d2"
}
```

### BPVS_02 (PV_STRUCT) — ✓
- Prompt: `Did we exceed capacity anywhere?`
- Expected: `PLAN_VALIDITY` — Predicted: `PLAN_VALIDITY`
- Boundary rationale: Capacity overload is a feasibility breakdown. Answer reads off feasibility_breakdown.capacity_ok.
- Wallclock: 7876 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 5793,
  "duration_api_ms": 6982,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "abe3180b-570f-4ab2-a86b-829d1345f603",
  "total_cost_usd": 0.01358065,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1679,
    "cache_read_input_tokens": 92119,
    "output_tokens": 369,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1679,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 103,
        "cache_read_input_tokens": 46753,
        "cache_creation_input_tokens": 292,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 292
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
      "outputTokens": 369,
      "cacheReadInputTokens": 92119,
      "cacheCreationInputTokens": 1679,
      "webSearchRequests": 0,
      "costUSD": 0.01317165,
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
  "uuid": "d9ea3aad-f3ad-41dc-9d35-29da6ae2ee30"
}
```

### BOC_01 (OBJ_SCHEDULE) — ✓
- Prompt: `How much longer overall is the new plan compared to yesterday?`
- Expected: `OBJ` — Predicted: `OBJ`
- Boundary rationale: Aggregated total duration vs baseline. Per the family definitions in the system prompt total duration is OBJ; SCHEDULE covers per-customer or per-route timing
- Wallclock: 9317 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 7234,
  "duration_api_ms": 8187,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "3edc2805-fd29-4a67-8d21-0c33bb6f9715",
  "total_cost_usd": 0.01360725,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1695,
    "cache_read_input_tokens": 92125,
    "output_tokens": 368,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1695,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 90,
        "cache_read_input_tokens": 46759,
        "cache_creation_input_tokens": 302,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 302
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
      "outputTokens": 368,
      "cacheReadInputTokens": 92125,
      "cacheCreationInputTokens": 1695,
      "webSearchRequests": 0,
      "costUSD": 0.013187250000000001,
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
  "uuid": "c8c039f2-76ea-4742-adad-d5b4d7609435"
}
```

### BOC_02 (OBJ_SCHEDULE) — ✓
- Prompt: `Will we still finish the last delivery before 6pm?`
- Expected: `SCHEDULE` — Predicted: `SCHEDULE`
- Boundary rationale: Specific clock-time check on a route end. Answer reads off route_end_times.
- Wallclock: 10638 ms; attempts: 1
- Full headless response:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 8857,
  "duration_api_ms": 9815,
  "num_turns": 2,
  "result": "",
  "stop_reason": "end_turn",
  "session_id": "3d66fe47-ad88-45ec-a1c0-7c48a50ad382",
  "total_cost_usd": 0.01518475,
  "usage": {
    "input_tokens": 16,
    "cache_creation_input_tokens": 1881,
    "cache_read_input_tokens": 92125,
    "output_tokens": 638,
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 1881,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [
      {
        "input_tokens": 7,
        "output_tokens": 176,
        "cache_read_input_tokens": 46759,
        "cache_creation_input_tokens": 488,
        "cache_creation": {
          "ephemeral_5m_input_tokens": 0,
          "ephemeral_1h_input_tokens": 488
        },
        "type": "message"
      }
    ],
    "speed": "standard"
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {
      "inputTokens": 350,
      "outputTokens": 13,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
      "webSearchRequests": 0,
      "costUSD": 0.000415,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    },
    "claude-haiku-4-5": {
      "inputTokens": 16,
      "outputTokens": 638,
      "cacheReadInputTokens": 92125,
      "cacheCreationInputTokens": 1881,
      "webSearchRequests": 0,
      "costUSD": 0.01476975,
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
  "uuid": "be301647-1ad8-43c1-8865-891b2f1464eb"
}
```

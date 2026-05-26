"""Request-level telemetry for the copilot API.

Writes one JSON object per `/copilot/ask` request to ``logs/copilot_ask.jsonl``
(relative to the repo root). The log is the primary measurement substrate for
the aspectual-fallback amendment — historical unknown-intent rate, validation-
outcome distribution, and (after PR 3) aspect-dispatch lift are all read from
this file.

Decision on prompt content: raw text is logged, not a hash. The thesis methods
section must cite this. The log is local-only; nothing ships outside the
repo. To disable entirely, set ``COPILOT_TELEMETRY_DISABLED=1``.

Failure isolation: every entry point swallows exceptions. Telemetry never
fails a request.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = _REPO_ROOT / "logs"
_LOG_PATH = _LOG_DIR / "copilot_ask.jsonl"


def _telemetry_disabled() -> bool:
    return os.environ.get("COPILOT_TELEMETRY_DISABLED", "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def _safe_get(d: Optional[dict[str, Any]], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _extract_warning_kinds(result: dict[str, Any]) -> list[str]:
    warnings = result.get("warnings") or []
    out: list[str] = []
    for w in warnings:
        if isinstance(w, str):
            out.append(w)
        elif isinstance(w, dict):
            kind = w.get("kind") or w.get("code") or w.get("type")
            if isinstance(kind, str):
                out.append(kind)
    return out


def log_copilot_ask(
    *,
    request_id: str,
    scenario_id: str,
    prompt: str,
    result: Optional[dict[str, Any]],
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    started_at: Optional[float] = None,
) -> None:
    """Append one event to the telemetry log. Never raises."""
    if _telemetry_disabled():
        return
    try:
        adapter_meta = _safe_get(result, "semantic_adapter") or {}
        compute = _safe_get(result, "compute_decision") or {}
        entities = _safe_get(adapter_meta, "entities") or {}
        evidence = _safe_get(result, "evidence") or []
        event: dict[str, Any] = {
            "ts": time.time(),
            "request_id": request_id,
            "scenario_id": scenario_id,
            "prompt": prompt,
            "predicted_intent": _safe_get(result, "intent"),
            "behavior_class": _safe_get(result, "behavior_class"),
            "validation_outcome": adapter_meta.get("validation_outcome"),
            "adapter_source": adapter_meta.get("source"),
            "fallback_used": adapter_meta.get("fallback_used"),
            "fallback_reason": adapter_meta.get("fallback_reason"),
            "d1_intent": adapter_meta.get("d1_intent"),
            "llm_intent": adapter_meta.get("llm_intent"),
            "rejected_llm_entities": adapter_meta.get("rejected_llm_entities"),
            "validation_error_details": adapter_meta.get("validation_error_details"),
            "entities": {
                "customer_ids": entities.get("customer_ids") or [],
                "route_labels": entities.get("route_labels") or [],
            },
            "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
            "warnings": _extract_warning_kinds(result or {}),
            "compute_decision_mode": compute.get("mode"),
            "aspectual_dispatch_triggered": bool(
                _safe_get(result, "aspectual_dispatch", "triggered")
            ),
            "error_code": error_code,
            "error_message": error_message,
        }
        if started_at is not None:
            event["latency_ms"] = round((time.time() - started_at) * 1000.0, 2)
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 — telemetry must never fail the caller
        pass

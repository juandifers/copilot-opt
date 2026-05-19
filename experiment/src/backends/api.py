"""Anthropic API SDK backend.

Implements ModelBackend using the anthropic Python SDK with structured
outputs via tool_use forced with tool_choice={"type":"tool","name":"report_answer"}.

Retry policy:
- Retry once on: RateLimitError (429), InternalServerError (5xx),
  schema validation failure on first attempt.
- Halt immediately on: AuthenticationError (401), PermissionDeniedError,
  budget exhaustion, schema failure on retry.

capture_environment() returns SDK version, endpoint URL, and an API key
fingerprint (first 8 + last 4 chars only — never the full key).
"""
from __future__ import annotations

import os
import time
from typing import Any

import jsonschema

from .base import HaltError, ModelBackend, ModelResponse


def _require_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HaltError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "The API backend requires this before use. "
            "Set it with: export ANTHROPIC_API_KEY='sk-ant-...'"
        )
    return key


def _fingerprint(key: str) -> str:
    """Return first-8 + last-4 chars; never expose the full key."""
    if len(key) < 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


class APIBackend(ModelBackend):
    """Backend using the Anthropic Python SDK (direct API calls)."""

    def __init__(self) -> None:
        self._api_key = _require_api_key()

    def name(self) -> str:
        return "api"

    def call(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        output_schema: dict,
        max_tokens: int,
        temperature: float = 0,
    ) -> ModelResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        tool_def = {
            "name": "report_answer",
            "description": "Report the structured answer per the output schema.",
            "input_schema": output_schema,
        }

        def _single_call() -> tuple[Any, int]:
            t0 = time.perf_counter()
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                tools=[tool_def],
                tool_choice={"type": "tool", "name": "report_answer"},
            )
            return resp, int((time.perf_counter() - t0) * 1000)

        # First attempt.
        try:
            response, elapsed_ms = _single_call()
        except anthropic.AuthenticationError as exc:
            raise HaltError(f"API authentication failed (401): {exc}") from exc
        except anthropic.PermissionDeniedError as exc:
            raise HaltError(f"API permission denied: {exc}") from exc
        except (anthropic.RateLimitError, anthropic.InternalServerError):
            time.sleep(30)
            try:
                response, elapsed_ms = _single_call()
            except anthropic.AuthenticationError as exc:
                raise HaltError(
                    f"API authentication failed (401) on retry: {exc}"
                ) from exc
            except Exception as exc:
                raise HaltError(f"API call failed on retry: {exc}") from exc
        except Exception as exc:
            raise HaltError(f"API call failed: {exc}") from exc

        # Extract tool_use block (model is forced to call "report_answer").
        tool_use = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_use is None:
            raise HaltError(
                f"API response has no tool_use block; "
                f"stop_reason={response.stop_reason!r}; "
                f"content_types={[b.type for b in response.content]}"
            )
        structured = tool_use.input
        if not isinstance(structured, dict):
            raise HaltError(
                f"tool_use.input is not a dict: {type(structured)!r}"
            )

        # Validate; retry the full call once on schema failure.
        try:
            jsonschema.validate(structured, output_schema)
        except jsonschema.ValidationError:
            time.sleep(30)
            try:
                response, elapsed_ms = _single_call()
            except anthropic.AuthenticationError as exc:
                raise HaltError(
                    f"API authentication failed (401) on schema-retry: {exc}"
                ) from exc
            except Exception as exc:
                raise HaltError(f"API call failed on schema-retry: {exc}") from exc

            tool_use = next(
                (b for b in response.content if b.type == "tool_use"), None
            )
            if tool_use is None:
                raise HaltError(
                    "API retry response has no tool_use block"
                )
            structured = tool_use.input
            try:
                jsonschema.validate(structured, output_schema)
            except jsonschema.ValidationError as exc:
                raise HaltError(
                    f"schema validation failed on API retry: {exc.message}; "
                    f"path={list(exc.absolute_path)}",
                    last_response=structured,
                ) from exc

        # Extract any text blocks (typically empty when tool_choice forces a tool).
        text_blocks = [b.text for b in response.content if b.type == "text"]
        answer_text_from_blocks = "\n".join(text_blocks)
        answer_text = structured.get("answer_text", answer_text_from_blocks)

        raw_response = response.model_dump()

        return ModelResponse(
            answer_text=answer_text,
            structured_output=structured,
            raw_response=raw_response,
            model_version=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=elapsed_ms,
            backend_name="api",
        )

    def capture_environment(self) -> dict:
        import anthropic

        try:
            import httpx
            httpx_version = httpx.__version__
        except ImportError:
            httpx_version = "unknown"

        return {
            "backend": "api",
            "note": (
                "backend=api; no local context loaded; "
                "configs sourced from locked files only"
            ),
            "anthropic_sdk_version": anthropic.__version__,
            "endpoint_url": "https://api.anthropic.com",
            "api_key_fingerprint": _fingerprint(self._api_key),
            "httpx_version": httpx_version,
        }

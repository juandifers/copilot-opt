"""OpenAI API backend for the closing experiment.

Implements ModelBackend using the OpenAI Python SDK with JSON-mode
structured outputs.  Both generator and judge calls use gpt-5.4-mini,
regardless of the Claude model name passed by the caller — the model
parameter from run_experiment.py is a Claude identifier; this backend
maps all calls to gpt-5.4-mini.

Retry policy:
- Retry once on: transient network/rate errors, JSON parse failure,
  schema validation failure on first attempt.
- Halt immediately on: missing API key, non-retryable API errors,
  schema failure on retry.

This backend reuses the transport layer in
``product.evaluation.model_clients.openai_client`` which already
handles gpt-5-class parameter naming (max_completion_tokens,
temperature=0 handling).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

# Reach product package from experiment/src/backends/
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from product.evaluation.model_clients.openai_client import (
    OpenAIKeyMissingError,
    call_openai_contract_model,
    load_openai_client,
)

from .base import HaltError, ModelBackend, ModelResponse

# Both generator and judge use the same model.
OPENAI_MODEL = "gpt-5.4-mini"
OPENAI_MODEL_PREFIX = "gpt-5.4-mini"


class OpenAIBackend(ModelBackend):
    """Backend using the OpenAI SDK (JSON mode structured outputs)."""

    def __init__(self) -> None:
        try:
            self._client = load_openai_client()
        except OpenAIKeyMissingError as exc:
            raise HaltError(
                f"OPENAI_API_KEY not found. "
                f"Add it to .env or set the environment variable. ({exc})"
            ) from exc

    def name(self) -> str:
        return "openai"

    # ------------------------------------------------------------------
    # Model prefix helpers (consumed by run_experiment.assert_model_version)

    @property
    def generator_model(self) -> str:
        return OPENAI_MODEL

    @property
    def generator_model_prefix(self) -> str:
        return OPENAI_MODEL_PREFIX

    @property
    def judge_model(self) -> str:
        return OPENAI_MODEL

    @property
    def judge_model_prefix(self) -> str:
        return OPENAI_MODEL_PREFIX

    # ------------------------------------------------------------------

    def call(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        output_schema: dict,
        max_tokens: int,
        temperature: float = 0,
    ) -> ModelResponse:
        # `model` is a Claude identifier passed by run_experiment.py; ignore it.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        result = self._call_once(messages, max_tokens)

        # Parse JSON.
        structured = self._parse_json(result, messages, max_tokens, attempt=1)

        # Validate against schema; retry once on failure.
        try:
            jsonschema.validate(structured, output_schema)
        except jsonschema.ValidationError:
            result = self._call_once(messages, max_tokens)
            structured = self._parse_json(result, messages, max_tokens, attempt=2)
            try:
                jsonschema.validate(structured, output_schema)
            except jsonschema.ValidationError as ve:
                raise HaltError(
                    f"schema validation failed on retry: {ve.message}; "
                    f"path={list(ve.absolute_path)}",
                    last_response=structured,
                ) from ve

        answer_text = structured.get("answer_text", "")

        return ModelResponse(
            answer_text=answer_text,
            structured_output=structured,
            raw_response={
                "response_model": result.response_model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "finish_reason": result.finish_reason,
                "retry_count": result.retry_count,
            },
            model_version=result.response_model,
            input_tokens=result.prompt_tokens or 0,
            output_tokens=result.completion_tokens or 0,
            latency_ms=int(result.latency_seconds * 1000),
            backend_name="openai",
        )

    def _call_once(self, messages: list[dict], max_tokens: int) -> Any:
        result = call_openai_contract_model(
            self._client,
            model=OPENAI_MODEL,
            messages=messages,
            max_output_tokens=max_tokens,
            response_format_json_object=True,
        )
        if result.error:
            raise HaltError(
                f"OpenAI API call failed: {result.error}",
                last_response={"error": result.error},
            )
        return result

    def _parse_json(
        self, result: Any, messages: list[dict], max_tokens: int, attempt: int
    ) -> dict:
        try:
            return json.loads(result.raw_response_text)
        except json.JSONDecodeError as exc:
            if attempt >= 2:
                raise HaltError(
                    f"JSON parse failed on attempt {attempt}: {exc}",
                    last_response=result.raw_response_text,
                ) from exc
            # Retry the API call once before giving up.
            result2 = self._call_once(messages, max_tokens)
            try:
                return json.loads(result2.raw_response_text)
            except json.JSONDecodeError as exc2:
                raise HaltError(
                    f"JSON parse failed on retry: {exc2}",
                    last_response=result2.raw_response_text,
                ) from exc2

    def capture_environment(self) -> dict:
        try:
            import openai
            sdk_version = openai.__version__
        except (ImportError, AttributeError):
            sdk_version = "unknown"
        return {
            "backend": "openai",
            "model": OPENAI_MODEL,
            "note": (
                "OpenAI backend; generator and judge both use gpt-5.4-mini. "
                "Structured outputs via JSON mode (response_format=json_object)."
            ),
            "openai_sdk_version": sdk_version,
        }

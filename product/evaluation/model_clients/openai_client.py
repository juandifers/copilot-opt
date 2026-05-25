"""OpenAI API client wrapper for Run 2 model baselines.

Used by:
- product.evaluation.run2_model_baseline_runner (System B prompt-only)
- (future) pass^k repeated-call experiments

Design points:
- API key is loaded from a local `.env` file (via python-dotenv) or
  from the process environment. The key is never echoed; if it is
  missing the wrapper raises with a clear, actionable message.
- The wrapper is transport-agnostic w.r.t. the prompt content — it
  takes a `messages` list and returns a structured `ModelCallResult`
  dataclass with the raw text, response model string, token usage if
  available, latency, and retry count. Parsing/scoring live elsewhere.
- A small retry loop handles transient network/rate failures only.
- The wrapper does NOT mutate any caller state, does NOT print the API
  key, and does NOT write to disk. The runner is responsible for
  persistence.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - exercised only when dep missing
    raise ImportError(
        "openai package is required for the Run 2 model baseline. "
        "Install with: pip install -r requirements.txt"
    ) from exc

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover - exercised only when dep missing
    raise ImportError(
        "python-dotenv is required to load OPENAI_API_KEY from .env. "
        "Install with: pip install -r requirements.txt"
    ) from exc


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ModelCallResult:
    """The outcome of a single OpenAI chat completion call.

    The wrapper records what was actually sent (model, temperature,
    max tokens) and what came back (response model string, raw text,
    token usage). Parsing is the caller's job.
    """

    requested_model: str
    response_model: str
    raw_response_text: str
    latency_seconds: float
    retry_count: int = 0
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    error: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class OpenAIKeyMissingError(RuntimeError):
    """Raised when OPENAI_API_KEY is not available in env or .env."""


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def load_openai_client(env_path: Optional[str] = None) -> OpenAI:
    """Load OPENAI_API_KEY (from .env or environment) and return a client.

    The function does not return or print the API key. If the key is
    missing the standard error message instructs the operator to add
    it to `.env` or the shell environment.
    """
    # `load_dotenv` is a no-op when no .env file is found; passing an
    # explicit path is used by tests that want to point at a temp file.
    if env_path is not None:
        load_dotenv(env_path)
    else:
        load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        raise OpenAIKeyMissingError(
            "OPENAI_API_KEY not found. Add it to .env or environment variables."
        )

    # The OpenAI SDK reads OPENAI_API_KEY from os.environ on init.
    return OpenAI()


# ---------------------------------------------------------------------------
# Single contract-model call
# ---------------------------------------------------------------------------


# Transient OpenAI error class names we retry on. Importing the SDK's
# error hierarchy by name keeps this wrapper resilient to SDK version
# changes — we match on class name rather than `isinstance`.
_RETRYABLE_ERROR_NAMES = frozenset(
    {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "BadGatewayError",
        "ServiceUnavailableError",
    }
)


def _is_retryable(exc: BaseException) -> bool:
    return type(exc).__name__ in _RETRYABLE_ERROR_NAMES


def call_openai_contract_model(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
    response_format_json_object: bool = True,
    max_retries: int = 2,
    retry_backoff_seconds: float = 2.0,
    extra_request_kwargs: Optional[dict[str, Any]] = None,
) -> ModelCallResult:
    """Call the OpenAI chat completions API and capture the response.

    Parameters
    ----------
    client:
        Constructed by `load_openai_client()`.
    model:
        Model identifier, e.g. ``"gpt-5.4-mini"``. Passed through
        verbatim — the wrapper never silently substitutes.
    messages:
        Chat-format messages list. Build via
        `product.evaluation.run2_model_prompts.build_prompt_only_json_prompt`.
    temperature:
        Default 0 for deterministic-as-possible baselines.
    max_output_tokens:
        Soft cap. The wrapper passes this through as ``max_tokens`` on
        the chat completions API.
    response_format_json_object:
        Whether to request `response_format={"type": "json_object"}`.
        Defaults to True for the contract-emitter task.
    max_retries:
        Transient errors are retried up to this many times with linear
        backoff. Non-transient errors are returned as `ModelCallResult`
        with `error` set so the runner can log and continue.
    """
    # gpt-5-class models (gpt-5, gpt-5.x, o1, o3, o4-mini, …) reject the
    # legacy `max_tokens` knob and require `max_completion_tokens`. Older
    # models (gpt-4, gpt-4o, gpt-3.5) accept either. We pick the newer
    # name for any model whose name begins with one of the families that
    # requires it; everything else keeps `max_tokens` to stay backward
    # compatible.
    model_lc = model.lower()
    uses_completion_tokens = (
        model_lc.startswith("gpt-5")
        or model_lc.startswith("o1")
        or model_lc.startswith("o3")
        or model_lc.startswith("o4")
    )
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if uses_completion_tokens:
        request_kwargs["max_completion_tokens"] = max_output_tokens
    else:
        request_kwargs["max_tokens"] = max_output_tokens
    # Some gpt-5-class models accept only temperature=1 (the default);
    # passing a value of 0 raises a 400. Treat 0 as "use the model default"
    # for these and only attach a non-default temperature when the model
    # is one of the older families that accepts arbitrary values.
    if not uses_completion_tokens or temperature != 0.0:
        request_kwargs["temperature"] = temperature
    if response_format_json_object:
        request_kwargs["response_format"] = {"type": "json_object"}
    if extra_request_kwargs:
        request_kwargs.update(extra_request_kwargs)

    last_error: Optional[BaseException] = None
    started = time.monotonic()
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(**request_kwargs)
            elapsed = time.monotonic() - started
            choice = response.choices[0] if response.choices else None
            raw_text = choice.message.content if choice and choice.message else ""
            finish_reason = choice.finish_reason if choice else None
            usage = getattr(response, "usage", None)
            return ModelCallResult(
                requested_model=model,
                response_model=getattr(response, "model", model),
                raw_response_text=raw_text or "",
                latency_seconds=elapsed,
                retry_count=attempt,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=(
                    getattr(usage, "completion_tokens", None) if usage else None
                ),
                total_tokens=getattr(usage, "total_tokens", None) if usage else None,
                finish_reason=finish_reason,
            )
        except Exception as exc:  # noqa: BLE001 - SDK raises broad set
            last_error = exc
            if attempt < max_retries and _is_retryable(exc):
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            break

    elapsed = time.monotonic() - started
    return ModelCallResult(
        requested_model=model,
        response_model="",
        raw_response_text="",
        latency_seconds=elapsed,
        retry_count=max_retries if last_error is not None else 0,
        error=f"{type(last_error).__name__}: {last_error}" if last_error else None,
    )

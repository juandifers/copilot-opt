"""Abstract backend interface for the closing experiment.

Both the Claude Code subprocess backend and the Anthropic API SDK backend
implement ModelBackend.  Callers (run_experiment.py, equivalence_smoke.py)
are fully backend-agnostic — they accept a ModelBackend and call .call().

HaltError is defined here so both backends and run_experiment.py can import
it from a single canonical location.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class HaltError(RuntimeError):
    """Raised when the run must stop unconditionally.

    Mirrors the halt semantics from the pre-registration spec: callers catch
    this, write halt_report.md, and exit non-zero.
    """

    def __init__(
        self,
        message: str,
        *,
        last_cmd: list[str] | None = None,
        last_response: dict | str | None = None,
        last_prompt_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.last_cmd = last_cmd
        self.last_response = last_response
        self.last_prompt_id = last_prompt_id


@dataclass
class ModelResponse:
    """Normalised response returned by either backend."""

    answer_text: str
    """Canonical answer string (from structured_output['answer_text'])."""

    structured_output: dict | None
    """Parsed structured fields (tool_use input or json-schema object)."""

    raw_response: dict
    """Full response payload as returned by the transport layer."""

    model_version: str
    """Exact model identifier returned by the serving infrastructure."""

    input_tokens: int
    output_tokens: int
    latency_ms: int
    backend_name: str


class ModelBackend(ABC):
    """Transport-layer abstraction for calling an LLM in the experiment."""

    @abstractmethod
    def call(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        output_schema: dict,
        max_tokens: int,
        temperature: float = 0,
    ) -> ModelResponse:
        """Make a single structured LLM call.

        Implementations handle their own retry logic (once on transient errors
        or first-attempt schema validation failure).  Unrecoverable errors
        raise HaltError.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the backend identifier: 'claude-code' or 'api'."""
        ...

    @abstractmethod
    def capture_environment(self) -> dict:
        """Return backend-specific reproducibility metadata dict.

        claude-code: CLAUDE.md contents, ~/.claude state, git commit hash, etc.
        api: SDK version, endpoint URL, API key fingerprint (first 8 + last 4
             chars only — never the full key).
        """
        ...

"""Backend registry for the closing experiment."""
from __future__ import annotations

from .base import ModelBackend


def get_backend(name: str) -> ModelBackend:
    """Instantiate and return the named backend.

    Args:
        name: One of 'claude-code', 'api', or 'openai'.

    Raises:
        ValueError: For unknown names.
    """
    if name == "claude-code":
        from .claude_code import ClaudeCodeBackend
        return ClaudeCodeBackend()
    if name == "api":
        from .api import APIBackend
        return APIBackend()
    if name == "openai":
        from .openai_backend import OpenAIBackend
        return OpenAIBackend()
    raise ValueError(
        f"unknown backend {name!r}; valid choices are 'claude-code', 'api', 'openai'"
    )

"""Backend registry for the closing experiment."""
from __future__ import annotations

from .base import ModelBackend


def get_backend(name: str) -> ModelBackend:
    """Instantiate and return the named backend.

    Args:
        name: One of 'claude-code' or 'api'.

    Raises:
        ValueError: For unknown names.
    """
    if name == "claude-code":
        from .claude_code import ClaudeCodeBackend
        return ClaudeCodeBackend()
    if name == "api":
        from .api import APIBackend
        return APIBackend()
    raise ValueError(
        f"unknown backend {name!r}; valid choices are 'claude-code' and 'api'"
    )

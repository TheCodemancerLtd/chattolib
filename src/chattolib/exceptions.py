"""Exception hierarchy for chattolib."""

from __future__ import annotations

from typing import Any


class ChattoError(Exception):
    """Base exception for all chattolib errors."""


class ChattoGraphQLError(ChattoError):
    """One or more GraphQL errors were returned by the API."""

    def __init__(self, errors: list[dict[str, Any]], data: Any = None) -> None:
        self.errors = errors
        self.data = data
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        super().__init__(messages)


class ChattoAuthError(ChattoError):
    """Authentication failed (missing token, expired session, etc.)."""

"""Exception hierarchy for chattolib."""

from __future__ import annotations

from typing import Any


class ChattoError(Exception):
    """Base exception for all chattolib errors."""


class ChattoConnectError(ChattoError):
    """A ConnectRPC call returned a protocol error.

    The Chatto Connect API returns errors as JSON bodies of the shape
    ``{"code": "<code>", "message": "<message>", "details": [...]}`` alongside a
    non-2xx HTTP status. See https://connectrpc.com/docs/protocol#error-codes for
    the canonical code list.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        super().__init__(f"{code}: {message}")


class ChattoAuthError(ChattoError):
    """Authentication failed (missing token, expired session, or bad credentials)."""

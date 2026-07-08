"""Connect JSON transport for chattolib.

Chatto exposes its public API as ConnectRPC services under ``/api/connect/``.
Each service method is invoked with an HTTP ``POST`` to::

    /api/connect/<full.service.Name>/<Method>

with a JSON-encoded request body and returns a JSON-encoded response body. This
module provides the low-level helpers; the high-level surface lives in
``chattolib.client``.
"""

from __future__ import annotations

from typing import Any

import httpx

from chattolib.exceptions import ChattoAuthError, ChattoConnectError

CONNECT_PREFIX = "/api/connect"


def _headers(token: str | None, session_cookie: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_cookie:
        headers["Cookie"] = f"chatto_session={session_cookie}"
    return headers


def _raise_for_error(response: httpx.Response) -> None:
    if 200 <= response.status_code < 300:
        return

    if response.status_code == 401:
        raise ChattoAuthError("Authentication failed")

    code = "unknown"
    message = response.text
    details: list[dict[str, Any]] = []
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            body = response.json()
            code = body.get("code") or code
            message = body.get("message") or message
            details = body.get("details") or details
        except ValueError:
            pass

    raise ChattoConnectError(
        code=code,
        message=message,
        status_code=response.status_code,
        details=details,
    )


async def call(
    http: httpx.AsyncClient,
    base_url: str,
    service: str,
    method: str,
    request: dict[str, Any] | None,
    *,
    token: str | None,
    session_cookie: str | None,
) -> dict[str, Any]:
    """Invoke a Connect unary RPC and return the decoded response JSON."""
    url = f"{base_url}{CONNECT_PREFIX}/{service}/{method}"
    response = await http.post(
        url,
        content=b"{}" if not request else _to_json(request),
        headers=_headers(token, session_cookie),
    )
    _raise_for_error(response)
    body: dict[str, Any] = response.json()
    return body


def _to_json(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload, separators=(",", ":")).encode("utf-8")

"""A minimal hand-rolled Connect-over-HTTP client.

This replaces the ``connectrpc`` package (and with it its ``pyqwest``
dependency) for the one thing chattolib actually uses: unary request/response
calls over the Connect JSON/binary protocol.

The Connect unary protocol, in full::

    POST {address}/{service_name}/{Method}
        Content-Type: application/proto
        Authorization: Bearer <token>        (chattolib adds this)
        <binary protobuf request body>

    -> 200, body is the binary protobuf response
    -> non-200, body is a JSON error envelope::

        {"code": "NOT_FOUND", "message": "...", "details": [...]}

Everything else ``connectrpc`` ships (compression, interceptors, the sync
client, the ASGI/WSGI server apps, streaming) is not used by chattolib and is
deliberately not implemented here.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from google.protobuf.message import Message

from chattolib.exceptions import ChattoError


class Code(enum.Enum):
    """Connect/gRPC status codes (the subset the protocol can return)."""

    CANCELED = "canceled"
    UNKNOWN = "unknown"
    INVALID_ARGUMENT = "invalid_argument"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    FAILED_PRECONDITION = "failed_precondition"
    ABORTED = "aborted"
    OUT_OF_RANGE = "out_of_range"
    UNIMPLEMENTED = "unimplemented"
    INTERNAL = "internal"
    UNAVAILABLE = "unavailable"
    DATA_LOSS = "data_loss"
    UNAUTHENTICATED = "unauthenticated"


# HTTP status -> Connect code, for non-JSON error bodies. Mirrors the
# mapping in the Connect protocol spec.
_HTTP_STATUS_TO_CODE: dict[int, Code] = {
    400: Code.INVALID_ARGUMENT,
    401: Code.UNAUTHENTICATED,
    403: Code.PERMISSION_DENIED,
    404: Code.NOT_FOUND,
    409: Code.ALREADY_EXISTS,
    413: Code.RESOURCE_EXHAUSTED,
    429: Code.RESOURCE_EXHAUSTED,
    500: Code.INTERNAL,
    501: Code.UNIMPLEMENTED,
    503: Code.UNAVAILABLE,
}


class ConnectError(Exception):
    """A ConnectRPC call returned a protocol error.

    Mirrors the shape ``connectrpc.errors.ConnectError`` exposes (``.code``,
    ``.message``, ``.details``) so ``_transport.translate_connect_error`` can
    consume it unchanged.
    """

    def __init__(
        self,
        code: Code,
        message: str,
        details: list[Any] | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])
        self.status_code = status_code

    def __str__(self) -> str:
        # Match connectrpc's ConnectError: str() is the message only, so
        # callers that embed str(exc) in a larger message don't double the code.
        return self.message


@dataclass(frozen=True)
class MethodInfo:
    """Static description of one unary method (what the stubs pass in)."""

    name: str
    service_name: str
    input: type[Message]
    output: type[Message]
    idempotency_level: str = "UNKNOWN"


class _BinaryCodec:
    """Encode/decode protobuf messages as raw bytes (the `proto` codec)."""

    def name(self) -> str:
        return "proto"

    def encode(self, message: Message) -> bytes:
        return message.SerializeToString()

    def decode(self, data: bytes, message_class: type[Message]) -> Message:
        return message_class.FromString(data)


def google_protobuf_binary_codec() -> _BinaryCodec:
    """Return the binary protobuf codec (drop-in for connectrpc's)."""
    return _BinaryCodec()


def _code_from_name(name: str) -> Code:
    try:
        return Code(name.lower())
    except ValueError:
        return Code.UNKNOWN


class ConnectClient:
    """Async unary Connect client.

    Subclassed by each generated ``*ServiceClient``; those subclasses add one
    method per RPC that calls :meth:`execute_unary`.
    """

    def __init__(
        self,
        address: str,
        *,
        codec: _BinaryCodec | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._address = address
        self._codec = codec or _BinaryCodec()
        self._timeout_ms = timeout_ms
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout((timeout_ms / 1000.0) if timeout_ms else None)
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def execute_unary(
        self,
        *,
        request: Message,
        method: MethodInfo,
        headers: Mapping[str, str] | None = None,
    ) -> Message:
        url = f"{self._address}/{method.service_name}/{method.name}"
        body = self._codec.encode(request)
        req_headers = {"Content-Type": "application/proto", **(headers or {})}

        try:
            resp = await self._http.post(url, content=body, headers=req_headers)
        except httpx.TimeoutException as e:
            raise ConnectError(Code.DEADLINE_EXCEEDED, "Request timed out") from e
        except httpx.HTTPError as e:
            raise ConnectError(Code.UNAVAILABLE, str(e)) from e

        if resp.status_code == 200:
            return self._codec.decode(resp.content, method.output)
        raise self._error_from_response(resp)

    @staticmethod
    def _error_from_response(resp: httpx.Response) -> ConnectError:
        try:
            data = resp.json()
        except Exception:
            data = None
        if isinstance(data, dict) and data.get("code"):
            code = _code_from_name(str(data["code"]))
            message = str(data.get("message", ""))
        else:
            code = _HTTP_STATUS_TO_CODE.get(resp.status_code, Code.UNKNOWN)
            message = resp.reason_phrase or ""
        return ConnectError(code, message, status_code=resp.status_code)


class ConnectClientSync:
    """Synchronous unary Connect client.

    Wraps the async :class:`ConnectClient`: it runs the *same*
    ``execute_unary`` on a private event loop, so the protocol logic (codec,
    error parsing) is implemented once. Use it from synchronous code; from
    inside a running event loop it raises a clear :class:`ChattoError` instead
    of a nested-loop ``RuntimeError``.
    """

    def __init__(
        self,
        address: str,
        *,
        codec: _BinaryCodec | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._async = ConnectClient(address, codec=codec, timeout_ms=timeout_ms)
        self._loop = asyncio.new_event_loop()

    def execute_unary(
        self,
        *,
        request: Message,
        method: MethodInfo,
        headers: Mapping[str, str] | None = None,
    ) -> Message:
        self._guard_no_running_loop()
        return self._loop.run_until_complete(
            self._async.execute_unary(request=request, method=method, headers=headers)
        )

    def close(self) -> None:
        self._loop.run_until_complete(self._async.close())
        self._loop.close()

    @staticmethod
    def _guard_no_running_loop() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop: safe to run_until_complete
        raise ChattoError(
            "the sync client cannot be used from within a running event loop; "
            "use the async ConnectClient in async code"
        )


__all__ = [
    "Code",
    "ConnectClient",
    "ConnectClientSync",
    "ConnectError",
    "MethodInfo",
    "google_protobuf_binary_codec",
]

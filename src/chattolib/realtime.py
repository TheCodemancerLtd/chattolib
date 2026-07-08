"""Placeholder for the Chatto realtime WebSocket protocol.

Chatto's realtime protocol (see ``proto/chatto/realtime/v1/realtime.proto``)
uses binary protobuf frames over WebSocket at ``/api/realtime``. This module
exports the endpoint metadata and a stub subscribe function. Wiring up actual
frame encoding/decoding requires protobuf Python bindings and is tracked in a
separate follow-up bean.
"""

from __future__ import annotations

REALTIME_PATH = "/api/realtime"
REALTIME_PROTOCOL_VERSION = 1


def realtime_url(base_url: str) -> str:
    """Convert an HTTP(S) base URL to the realtime WebSocket URL."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        scheme = "wss://"
        rest = base[len("https://") :]
    elif base.startswith("http://"):
        scheme = "ws://"
        rest = base[len("http://") :]
    else:
        scheme = "wss://"
        rest = base
    return f"{scheme}{rest}{REALTIME_PATH}"


class RealtimeNotImplementedError(NotImplementedError):
    """Raised when realtime is requested but the protobuf bindings are absent."""


async def subscribe_events(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the realtime event stream.

    Chatto's realtime protocol is a binary protobuf WebSocket. Consuming it
    requires generated protobuf bindings for
    ``chatto.realtime.v1.RealtimeClientFrame`` / ``RealtimeServerFrame`` and
    their dependencies. Once bindings are shipped, this function should
    connect to :data:`REALTIME_PATH`, send a ``RealtimeClientHello`` frame,
    exchange the server ``hello``, send ``RealtimeSubscribeEvents``, and yield
    decoded ``RealtimeEventEnvelope`` values.
    """
    raise RealtimeNotImplementedError(
        "chattolib does not yet ship protobuf bindings for the Chatto realtime "
        "WebSocket protocol. Track the follow-up bean for status."
    )

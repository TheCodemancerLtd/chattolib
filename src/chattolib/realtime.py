"""Chatto realtime WebSocket client.

Chatto exposes a binary-protobuf realtime channel at ``/api/realtime`` (see
``proto/chatto/realtime/v1/realtime.proto``). This module speaks that
protocol: it opens the WebSocket, exchanges ``hello`` frames, subscribes to
the caller's authorized server-projection stream, and yields decoded events.

Chatto 0.4.19 introduced protocol version 2, splitting realtime delivery into
two channels multiplexed over the same WebSocket:

* **Transient events** (``user_typing``, ``presence_changed``, mention/DM/reply
  notifications, ``session_terminated``) carried inside
  ``RealtimeEventEnvelope`` — never replayed.
* **Durable projection events** carried by ``RealtimeProjectionEvent``, which
  contains ordered operations that mutate the caller's server-scoped
  projection.

Both are yielded through the same iterator as :class:`RealtimeEvent`;
``kind`` names the frame or envelope case. A ``caught_up`` cursor is also
surfaced as a synthetic event so callers can persist the resume cursor.

Usage::

    async with await ChattoClient.login(...) as client:
        async for event in stream_events(client):
            print(event.kind, event.payload)

Requires the ``chattolib[realtime]`` extra (which pulls in ``websockets`` and
``protobuf``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from chattolib import _pb  # noqa: F401 — installs pb import path
from chattolib.exceptions import ChattoError
from chattolib.types import parse_datetime

if TYPE_CHECKING:
    from chattolib.client import ChattoClient

REALTIME_PATH = "/api/realtime"
REALTIME_PROTOCOL_VERSION = 2


class ChattoRealtimeError(ChattoError):
    """Server returned a protocol error over the realtime WebSocket."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        fatal: bool = False,
        retry_after_ms: int | None = None,
        room_id: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.fatal = fatal
        self.retry_after_ms = retry_after_ms
        self.room_id = room_id
        super().__init__(f"{code}: {message}")


class ChattoRealtimeCloseError(ChattoError):
    """Server sent a close frame."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        reconnect: bool = False,
        retry_after_ms: int = 0,
    ) -> None:
        self.code = code
        self.message = message
        self.reconnect = reconnect
        self.retry_after_ms = retry_after_ms
        super().__init__(f"{code}: {message}")


def realtime_url(base_url: str) -> str:
    """Convert an HTTP(S) base URL to the realtime WebSocket URL."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + REALTIME_PATH
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :] + REALTIME_PATH
    return "wss://" + base + REALTIME_PATH


@dataclass
class ServerHello:
    """Server's response to the initial hello frame."""

    protocol_version: int
    server_version: str
    heartbeat_interval_seconds: int
    capabilities: list[str]


@dataclass
class RealtimeEvent:
    """One frame delivered over the realtime WebSocket.

    ``kind`` names either the ``oneof event`` case on
    ``RealtimeEventEnvelope`` (``user_typing``, ``presence_changed``,
    ``mention_notification``, …) or the top-level server-frame case for
    non-envelope deliveries: ``projection_event`` and ``caught_up``.
    ``payload`` is the concrete protobuf sub-message; access its fields
    directly (e.g. ``event.payload.room_id``).

    For transient envelope events, ``id`` / ``created_at`` / ``actor_id`` come
    from :class:`RealtimeEventEnvelope`. For ``projection_event`` frames the
    same fields are copied from :class:`RealtimeProjectionEvent` (which also
    carries an optional ``resume_cursor``). For ``caught_up`` frames, ``id``
    is empty; ``payload`` is the ``RealtimeCaughtUp`` message whose
    ``cursor`` field is the durable resume cursor.
    """

    id: str
    created_at: datetime | None
    actor_id: str | None
    kind: str
    payload: Any
    raw: Any  # the full RealtimeEventEnvelope or RealtimeServerFrame


class RealtimeConnection:
    """Live realtime WebSocket session.

    Prefer :func:`stream_events` for the common case; use this class directly
    when you also need to send client pings, close cleanly, or inspect the
    negotiated :class:`ServerHello`.
    """

    def __init__(
        self,
        client: ChattoClient,
        *,
        protocol_version: int = REALTIME_PROTOCOL_VERSION,
        resume_cursor: str | None = None,
        retained_room_ids: list[str] | None = None,
    ) -> None:
        self._client = client
        self._protocol_version = protocol_version
        self._resume_cursor = resume_cursor
        self._retained_room_ids = list(retained_room_ids) if retained_room_ids else []
        self._ws: Any = None
        self._server_hello: ServerHello | None = None

    @property
    def server_hello(self) -> ServerHello | None:
        return self._server_hello

    async def __aenter__(self) -> RealtimeConnection:
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def connect(self) -> None:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover
            raise ChattoError(
                "The realtime channel requires the 'websockets' package. "
                "Install with `pip install chattolib[realtime]`."
            ) from exc

        from chattolib._pb.chatto.realtime.v1 import realtime_pb2

        url = realtime_url(self._client.base_url)
        headers: dict[str, str] = {}
        if self._client.session_cookie:
            headers["Cookie"] = f"chatto_session={self._client.session_cookie}"

        self._ws = await websockets.connect(url, additional_headers=headers)

        client_hello = realtime_pb2.RealtimeClientFrame()
        client_hello.hello.protocol_version = self._protocol_version
        if self._client.token:
            client_hello.hello.bearer_token = self._client.token
        await self._ws.send(client_hello.SerializeToString())

        first = await self._ws.recv()
        first_frame = realtime_pb2.RealtimeServerFrame()
        first_frame.ParseFromString(first)
        if first_frame.WhichOneof("frame") != "hello":
            _raise_for_control(first_frame)
            raise ChattoRealtimeError(
                "unexpected_frame",
                f"expected server hello, got {first_frame.WhichOneof('frame')!r}",
            )
        hello = first_frame.hello
        self._server_hello = ServerHello(
            protocol_version=hello.protocol_version,
            server_version=hello.server_version,
            heartbeat_interval_seconds=hello.heartbeat_interval_seconds,
            capabilities=list(hello.capabilities),
        )

        subscribe = realtime_pb2.RealtimeClientFrame()
        subscribe.subscribe_events.SetInParent()
        if self._resume_cursor is not None:
            subscribe.subscribe_events.resume_cursor = self._resume_cursor
        if self._retained_room_ids:
            subscribe.subscribe_events.retained_room_ids.extend(self._retained_room_ids)
        await self._ws.send(subscribe.SerializeToString())

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.close()
        finally:
            self._ws = None

    async def ping(self, nonce: str = "") -> None:
        """Send a client ping. The server replies with a matching pong."""
        if self._ws is None:
            raise ChattoError("realtime connection is closed")
        from chattolib._pb.chatto.realtime.v1 import realtime_pb2

        frame = realtime_pb2.RealtimeClientFrame()
        frame.ping.nonce = nonce
        await self._ws.send(frame.SerializeToString())

    async def hydrate_room(self, room_id: str) -> None:
        """Request lazy materialisation of one joined room's recent timeline.

        The server responds on the same projection stream with a
        ``room_timeline_replace`` operation for ``room_id``. Repeats are
        idempotent. Errors surface as non-fatal ``RealtimeError`` frames
        whose ``room_id`` matches.
        """
        if self._ws is None:
            raise ChattoError("realtime connection is closed")
        from chattolib._pb.chatto.realtime.v1 import realtime_pb2

        frame = realtime_pb2.RealtimeClientFrame()
        frame.hydrate_room.room_id = room_id
        await self._ws.send(frame.SerializeToString())

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        """Yield decoded live events until the connection closes."""
        if self._ws is None:
            raise ChattoError("realtime connection is not open")
        from chattolib._pb.chatto.realtime.v1 import realtime_pb2

        async for raw in self._ws:
            if isinstance(raw, str):
                # The protocol is binary; a text frame indicates a protocol violation.
                raise ChattoRealtimeError(
                    "unexpected_text_frame",
                    "server sent a text frame; realtime protocol expects binary",
                )
            frame = realtime_pb2.RealtimeServerFrame()
            frame.ParseFromString(raw)
            case = frame.WhichOneof("frame")
            if case == "event":
                yield _wrap_event(frame.event)
            elif case == "projection_event":
                yield _wrap_projection_event(frame)
            elif case == "caught_up":
                yield _wrap_caught_up(frame)
            elif case in ("heartbeat", "pong", "subscribed"):
                continue
            elif case == "error":
                err = frame.error
                exc = ChattoRealtimeError(
                    err.code,
                    err.message,
                    fatal=err.fatal,
                    retry_after_ms=(
                        err.retry_after_ms if err.HasField("retry_after_ms") else None
                    ),
                    room_id=err.room_id if err.HasField("room_id") else None,
                )
                if err.fatal:
                    raise exc
                # Non-fatal errors are surfaced but the stream continues.
                # Callers can still receive them if desired; for now we log
                # by re-raising on fatal only.
                continue
            elif case == "close":
                close = frame.close
                raise ChattoRealtimeCloseError(
                    close.code,
                    close.message,
                    reconnect=close.reconnect,
                    retry_after_ms=close.retry_after_ms,
                )
            else:
                raise ChattoRealtimeError(
                    "unexpected_frame",
                    f"unknown server frame: {case!r}",
                )


def _raise_for_control(frame: Any) -> None:
    """If ``frame`` is an error or close frame, translate it and raise."""
    case = frame.WhichOneof("frame")
    if case == "error":
        err = frame.error
        raise ChattoRealtimeError(
            err.code,
            err.message,
            fatal=err.fatal,
            retry_after_ms=(
                err.retry_after_ms if err.HasField("retry_after_ms") else None
            ),
            room_id=err.room_id if err.HasField("room_id") else None,
        )
    if case == "close":
        close = frame.close
        raise ChattoRealtimeCloseError(
            close.code,
            close.message,
            reconnect=close.reconnect,
            retry_after_ms=close.retry_after_ms,
        )


def _wrap_event(envelope: Any) -> RealtimeEvent:
    kind = envelope.WhichOneof("event") or ""
    payload = getattr(envelope, kind, None) if kind else None
    created_at = None
    if envelope.HasField("created_at"):
        created_at = parse_datetime(envelope.created_at.ToJsonString())
    actor_id: str | None = None
    if envelope.HasField("actor_id"):
        actor_id = envelope.actor_id
    return RealtimeEvent(
        id=envelope.id,
        created_at=created_at,
        actor_id=actor_id,
        kind=kind,
        payload=payload,
        raw=envelope,
    )


def _wrap_projection_event(frame: Any) -> RealtimeEvent:
    """Wrap a top-level projection_event frame as a :class:`RealtimeEvent`."""
    pe = frame.projection_event
    created_at = None
    if pe.HasField("created_at"):
        created_at = parse_datetime(pe.created_at.ToJsonString())
    actor_id: str | None = pe.actor_id if pe.HasField("actor_id") else None
    return RealtimeEvent(
        id=pe.id,
        created_at=created_at,
        actor_id=actor_id,
        kind="projection_event",
        payload=pe,
        raw=frame,
    )


def _wrap_caught_up(frame: Any) -> RealtimeEvent:
    """Wrap a caught_up frame as a synthetic :class:`RealtimeEvent`."""
    return RealtimeEvent(
        id="",
        created_at=None,
        actor_id=None,
        kind="caught_up",
        payload=frame.caught_up,
        raw=frame,
    )


async def stream_events(
    client: ChattoClient,
    *,
    protocol_version: int = REALTIME_PROTOCOL_VERSION,
    resume_cursor: str | None = None,
    retained_room_ids: list[str] | None = None,
) -> AsyncIterator[RealtimeEvent]:
    """Open a realtime connection and yield events until the server closes.

    Pass ``resume_cursor`` from the most recently observed ``caught_up`` (or
    ``projection_event.resume_cursor``) to resume a durable stream, and
    ``retained_room_ids`` to declare which joined rooms' timeline windows the
    client still retains locally.

    Raises :class:`ChattoRealtimeCloseError` when the server sends a close frame,
    :class:`ChattoRealtimeError` on fatal protocol errors, or
    :class:`ChattoConnectError` if the initial HTTP handshake fails.
    """
    conn = RealtimeConnection(
        client,
        protocol_version=protocol_version,
        resume_cursor=resume_cursor,
        retained_room_ids=retained_room_ids,
    )
    try:
        await conn.connect()
        async for event in conn.events():
            yield event
    finally:
        await conn.close()


__all__ = [
    "REALTIME_PATH",
    "REALTIME_PROTOCOL_VERSION",
    "ChattoRealtimeCloseError",
    "ChattoRealtimeError",
    "RealtimeConnection",
    "RealtimeEvent",
    "ServerHello",
    "realtime_url",
    "stream_events",
]

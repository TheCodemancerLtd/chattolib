"""Chatto realtime WebSocket client.

Chatto exposes a binary-protobuf realtime channel at ``/api/realtime`` (see
``proto/chatto/realtime/v1/realtime.proto``). This module speaks that
protocol: it opens the WebSocket, exchanges ``hello`` frames, subscribes to
the caller's authorized live-event stream, and yields decoded events.

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

    def __init__(self, code: str, message: str, *, fatal: bool = False) -> None:
        self.code = code
        self.message = message
        self.fatal = fatal
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
class RealtimeProjectionOperation:
    """One durable state change inside a :class:`RealtimeProjectionEvent`.

    ``operation`` names the ``oneof operation`` case set on the operation
    (``reset``, ``server_upsert``, ``viewer_upsert``, ``user_upsert``,
    ``user_remove``, ``room_upsert``, ``room_remove``,
    ``room_groups_replace``, ``room_timeline_replace``,
    ``room_timeline_event_upsert``, ``server_state_upsert``,
    ``room_timeline_event_remove``, ``room_viewer_state_replace``,
    ``active_calls_replace``, ``presences_replace``,
    ``thread_viewer_states_replace``, ``room_activity``,
    ``notification_occurrences_replace``). ``payload`` is the concrete
    protobuf sub-message.
    """

    operation: str
    payload: Any
    raw: Any  # the full RealtimeProjectionOperation


@dataclass
class RealtimeProjectionEvent:
    """A server-projection frame: the durable state the server wants clients
    to converge on, as a batch of :class:`RealtimeProjectionOperation` s.
    """

    id: str
    created_at: datetime | None
    actor_id: str | None
    resume_cursor: str | None
    operations: list[RealtimeProjectionOperation]
    raw: Any  # the full RealtimeProjectionEvent


@dataclass
class RealtimeEvent:
    """One live event delivered over the realtime WebSocket.

    ``kind`` names the ``oneof event`` case set on the envelope
    (``message_posted``, ``reaction_added``, ``presence_changed``, …).
    ``payload`` is the concrete protobuf sub-message; access its fields
    directly (e.g. ``event.payload.room_id``). Callers that want to hydrate
    the referenced resource should follow the hydration hints documented on
    each event message in ``realtime.proto``.
    """

    id: str
    created_at: datetime | None
    actor_id: str | None
    kind: str
    payload: Any
    raw: Any  # the full RealtimeEventEnvelope


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
        self._retained_room_ids = list(retained_room_ids or [])
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
        if self._resume_cursor:
            subscribe.subscribe_events.resume_cursor = self._resume_cursor
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
        """Ask the server to re-send the projection state for a room."""
        if self._ws is None:
            raise ChattoError("realtime connection is closed")
        from chattolib._pb.chatto.realtime.v1 import realtime_pb2

        frame = realtime_pb2.RealtimeClientFrame()
        frame.hydrate_room.room_id = room_id
        await self._ws.send(frame.SerializeToString())

    async def events(
        self,
    ) -> AsyncIterator[RealtimeEvent | RealtimeProjectionEvent]:
        """Yield decoded live events and projection events until the
        connection closes."""
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
            elif case in ("heartbeat", "pong", "subscribed", "caught_up"):
                continue
            elif case == "projection_event":
                yield _wrap_projection_event(frame.projection_event)
            elif case == "error":
                err = frame.error
                exc = ChattoRealtimeError(err.code, err.message, fatal=err.fatal)
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
        raise ChattoRealtimeError(err.code, err.message, fatal=err.fatal)
    if case == "close":
        close = frame.close
        raise ChattoRealtimeCloseError(
            close.code,
            close.message,
            reconnect=close.reconnect,
            retry_after_ms=close.retry_after_ms,
        )


def _wrap_projection_event(envelope: Any) -> RealtimeProjectionEvent:
    created_at = None
    if envelope.HasField("created_at"):
        created_at = parse_datetime(envelope.created_at.ToJsonString())
    actor_id: str | None = None
    if envelope.HasField("actor_id"):
        actor_id = envelope.actor_id
    resume_cursor: str | None = None
    if envelope.HasField("resume_cursor"):
        resume_cursor = envelope.resume_cursor
    operations = [_wrap_projection_operation(op) for op in envelope.operations]
    return RealtimeProjectionEvent(
        id=envelope.id,
        created_at=created_at,
        actor_id=actor_id,
        resume_cursor=resume_cursor,
        operations=operations,
        raw=envelope,
    )


def _wrap_projection_operation(op: Any) -> RealtimeProjectionOperation:
    kind = op.WhichOneof("operation") or ""
    payload = getattr(op, kind, None) if kind else None
    return RealtimeProjectionOperation(operation=kind, payload=payload, raw=op)


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


async def stream_events(
    client: ChattoClient,
    *,
    protocol_version: int = REALTIME_PROTOCOL_VERSION,
    resume_cursor: str | None = None,
    retained_room_ids: list[str] | None = None,
) -> AsyncIterator[RealtimeEvent | RealtimeProjectionEvent]:
    """Open a realtime connection and yield events until the server closes.

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
    "RealtimeProjectionEvent",
    "RealtimeProjectionOperation",
    "ServerHello",
    "realtime_url",
    "stream_events",
]

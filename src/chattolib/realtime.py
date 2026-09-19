"""Chatto realtime WebSocket client.

Chatto exposes a binary-protobuf realtime channel at ``/api/realtime`` (see
``proto/chatto/realtime/v1/realtime.proto``). This module speaks the
protocol-4 variant of that channel: it opens the WebSocket, sends a single
:class:`RealtimeSubscribe` handshake message, then yields the decoded
server frames — live events, the initial snapshot, recovery boundaries,
heartbeats, and close frames.

Usage::

    async with ChattoClient(token="cht_...") as client:
        async for frame in stream_events(client):
            if isinstance(frame, RealtimeEvent):
                print(frame.kind, frame.payload)

Requires the ``chattolib[realtime]`` extra (which pulls in ``websockets`` and
``protobuf``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from chattolib import _pb  # noqa: F401 — installs pb import path
from chattolib.exceptions import ChattoError
from chattolib.types import parse_datetime

if TYPE_CHECKING:
    from chattolib.client import ChattoClient

REALTIME_PATH = "/api/realtime"
REALTIME_PROTOCOL_VERSION = 4

# RealtimeInitialState values (see realtime.proto).
INITIAL_STATE_LIVE_ONLY = 1
INITIAL_STATE_SNAPSHOT = 2


class ChattoRealtimeError(ChattoError):
    """Server returned a protocol error over the realtime WebSocket."""

    def __init__(self, code: str, message: str, *, fatal: bool = False) -> None:
        self.code = code
        self.message = message
        self.fatal = fatal
        super().__init__(f"{code}: {message}")


class ChattoRealtimeCloseError(ChattoError):
    """Server sent a close frame.

    ``code`` is the short name of the :class:`RealtimeCloseCode` enum value
    (e.g. ``"SESSION_TERMINATED"``), ``reconnect`` mirrors the server's
    reconnect guidance, and ``retry_after_ms`` is the suggested delay in
    milliseconds before reconnecting.
    """

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
class RealtimeEvent:
    """One live event delivered over the realtime WebSocket.

    ``kind`` names the ``oneof event`` case set on the envelope
    (``message_posted``, ``presence_changed``, ``reaction_added``, …).
    ``payload`` is the concrete protobuf sub-message; access its fields
    directly (e.g. ``event.payload.room_id``). In protocol 4 most payloads are
    thin, caller-scoped hints (identifiers rather than full resources), so
    callers that need the full resource should hydrate it through the
    corresponding ConnectRPC with the event's ``cursor`` as the boundary.

    ``cursor`` is the opaque resume cursor safe to retain after this complete
    event has been applied; it is ``None`` when the event cannot be replayed
    (its state is recoverable from a snapshot or a ConnectRPC read).
    """

    id: str
    created_at: datetime | None
    actor_id: str | None
    cursor: str | None
    kind: str
    payload: Any
    raw: Any  # the full RealtimeEvent


@dataclass
class RealtimeSnapshot:
    """One exact authorized snapshot of current server content.

    The server sends at most one snapshot (when the subscription's
    ``initial_state`` requested one) before the recovery-to-live boundary.
    List-valued fields replace the complete local family; large paginated
    resources (such as message history) are not part of the snapshot and
    remain available through ConnectRPC.
    """

    server: Any  # chatto.api.v1.ServerPublicProfile, or None if absent
    rooms: list[Any] = field(default_factory=list)
    room_groups: list[Any] = field(default_factory=list)
    users: list[Any] = field(default_factory=list)
    active_calls: list[Any] = field(default_factory=list)
    raw: Any = None  # the full RealtimeSnapshot


def _close_code_name(code: int) -> str:
    """Map a ``RealtimeCloseCode`` enum value to its short name."""
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    try:
        raw = realtime_pb2.RealtimeCloseCode.Name(code)
    except ValueError:
        return f"UNKNOWN_{code}"
    name: str = raw
    prefix = "REALTIME_CLOSE_CODE_"
    return name[len(prefix) :] if name.startswith(prefix) else name


def _duration_to_ms(duration: Any) -> int:
    if duration is None:
        return 0
    return int(duration.seconds) * 1000 + int(duration.nanos) // 1_000_000


class RealtimeConnection:
    """Live realtime WebSocket session.

    Prefer :func:`stream_events` for the common case; use this class directly
    when you need to inspect the negotiated subscription state.
    """

    def __init__(
        self,
        client: ChattoClient,
        *,
        protocol_version: int = REALTIME_PROTOCOL_VERSION,
        resume_cursor: str | None = None,
        initial_state: int | None = None,
    ) -> None:
        self._client = client
        self._protocol_version = protocol_version
        self._resume_cursor = resume_cursor
        # When no resume cursor is supplied the server starts from the current
        # boundary; the caller may opt into an initial snapshot instead.
        self._initial_state = INITIAL_STATE_LIVE_ONLY if initial_state is None else initial_state
        self._ws: Any = None
        self.last_cursor: str | None = None

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

        subscribe = realtime_pb2.RealtimeSubscribe()
        subscribe.protocol_version = self._protocol_version
        if self._client.token:
            subscribe.bearer_token = self._client.token
        if self._resume_cursor:
            subscribe.resume_cursor = self._resume_cursor
        subscribe.initial_state = self._initial_state
        await self._ws.send(subscribe.SerializeToString())

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.close()
        finally:
            self._ws = None

    async def events(
        self,
    ) -> AsyncIterator[RealtimeEvent | RealtimeSnapshot]:
        """Yield decoded live events and snapshots until the connection
        closes or a close frame arrives."""
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
                event = _wrap_event(frame.event)
                if event.cursor:
                    self.last_cursor = event.cursor
                yield event
            elif case == "snapshot":
                yield _wrap_snapshot(frame.snapshot)
            elif case == "caught_up":
                if frame.caught_up.cursor:
                    self.last_cursor = frame.caught_up.cursor
                continue
            elif case == "heartbeat":
                if frame.heartbeat.HasField("cursor") and frame.heartbeat.cursor:
                    self.last_cursor = frame.heartbeat.cursor
                continue
            elif case == "close":
                close = frame.close
                raise ChattoRealtimeCloseError(
                    _close_code_name(int(close.code)),
                    close.message,
                    reconnect=close.reconnect,
                    retry_after_ms=_duration_to_ms(close.retry_after),
                )
            else:
                raise ChattoRealtimeError(
                    "unexpected_frame",
                    f"unknown server frame: {case!r}",
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
    cursor: str | None = None
    if envelope.HasField("cursor"):
        cursor = envelope.cursor
    return RealtimeEvent(
        id=envelope.id,
        created_at=created_at,
        actor_id=actor_id,
        cursor=cursor,
        kind=kind,
        payload=payload,
        raw=envelope,
    )


def _wrap_snapshot(frame: Any) -> RealtimeSnapshot:
    return RealtimeSnapshot(
        server=frame.server if frame.HasField("server") else None,
        rooms=list(frame.rooms),
        room_groups=list(frame.room_groups),
        users=list(frame.users),
        active_calls=list(frame.active_calls),
        raw=frame,
    )


async def stream_events(
    client: ChattoClient,
    *,
    protocol_version: int = REALTIME_PROTOCOL_VERSION,
    resume_cursor: str | None = None,
    initial_state: int | None = None,
) -> AsyncIterator[RealtimeEvent | RealtimeSnapshot]:
    """Open a realtime connection and yield frames until the server closes.

    ``resume_cursor`` resumes from a previously received event/caught-up
    cursor. ``initial_state`` selects the fallback behavior when the cursor
    cannot resume: :data:`INITIAL_STATE_LIVE_ONLY` (default, start at the
    current boundary without current resources) or
    :data:`INITIAL_STATE_SNAPSHOT` (send one authorized snapshot first).

    Raises :class:`ChattoRealtimeCloseError` when the server sends a close
    frame, :class:`ChattoRealtimeError` on protocol errors, or
    :class:`ChattoConnectError` if the initial WebSocket handshake fails.
    """
    conn = RealtimeConnection(
        client,
        protocol_version=protocol_version,
        resume_cursor=resume_cursor,
        initial_state=initial_state,
    )
    try:
        await conn.connect()
        async for event in conn.events():
            yield event
    finally:
        await conn.close()


__all__ = [
    "INITIAL_STATE_LIVE_ONLY",
    "INITIAL_STATE_SNAPSHOT",
    "REALTIME_PATH",
    "REALTIME_PROTOCOL_VERSION",
    "ChattoRealtimeCloseError",
    "ChattoRealtimeError",
    "RealtimeConnection",
    "RealtimeEvent",
    "RealtimeSnapshot",
    "realtime_url",
    "stream_events",
]

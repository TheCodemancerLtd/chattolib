"""Tests for the realtime WebSocket helpers.

Exercises the pure functions and the frame decoding path. The WebSocket
handshake itself is covered by the live integration test.
"""

from __future__ import annotations

import pytest

from chattolib.realtime import (
    ChattoRealtimeCloseError,
    ChattoRealtimeError,
    RealtimeEvent,
    RealtimeSnapshot,
    _close_code_name,
    _wrap_event,
    _wrap_snapshot,
    realtime_url,
)


def test_realtime_url_https_to_wss():
    assert realtime_url("https://chat.chatto.run") == "wss://chat.chatto.run/api/realtime"


def test_realtime_url_http_to_ws():
    assert realtime_url("http://localhost:9000") == "ws://localhost:9000/api/realtime"


def test_realtime_url_strips_trailing_slash():
    assert realtime_url("https://chat.chatto.run/") == "wss://chat.chatto.run/api/realtime"


def test_wrap_event_user_typing():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeEvent()
    envelope.id = "evt_1"
    envelope.actor_id = "u1"
    envelope.cursor = "cur_1"
    envelope.user_typing.room_id = "r1"

    wrapped = _wrap_event(envelope)
    assert isinstance(wrapped, RealtimeEvent)
    assert wrapped.id == "evt_1"
    assert wrapped.kind == "user_typing"
    assert wrapped.actor_id == "u1"
    assert wrapped.cursor == "cur_1"
    assert wrapped.payload.room_id == "r1"


def test_wrap_event_presence_changed():
    from chattolib._pb.chatto.api.v1 import presence_pb2
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeEvent()
    envelope.id = "evt_2"
    envelope.presence_changed.status = presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE

    wrapped = _wrap_event(envelope)
    assert wrapped.kind == "presence_changed"
    # In protocol 4 the actor lives on the envelope, not the payload.
    assert wrapped.actor_id is None
    assert wrapped.payload.status == presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE


def test_wrap_event_without_variant():
    """Envelope with no oneof set (server bug or truncation) should still wrap."""
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeEvent()
    envelope.id = "evt_3"

    wrapped = _wrap_event(envelope)
    assert wrapped.kind == ""
    assert wrapped.payload is None
    assert wrapped.cursor is None


def test_wrap_snapshot_copies_families():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    snap = realtime_pb2.RealtimeSnapshot()
    snap.server.name = "Acme"
    snap.rooms.add().room.id = "r1"
    snap.rooms.add().room.id = "r2"
    snap.users.add().user.id = "u1"

    wrapped = _wrap_snapshot(snap)
    assert isinstance(wrapped, RealtimeSnapshot)
    assert wrapped.server is not None
    assert wrapped.server.name == "Acme"
    assert [r.room.id for r in wrapped.rooms] == ["r1", "r2"]
    assert [u.user.id for u in wrapped.users] == ["u1"]
    assert wrapped.room_groups == []
    assert wrapped.active_calls == []


def test_close_code_name_strips_prefix():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    assert (
        _close_code_name(realtime_pb2.REALTIME_CLOSE_CODE_SESSION_TERMINATED)
        == "SESSION_TERMINATED"
    )
    assert _close_code_name(12345) == "UNKNOWN_12345"


def test_close_exception_carries_reconnect_hint():
    exc = ChattoRealtimeCloseError(
        "auth_expired", "please reconnect", reconnect=True, retry_after_ms=5000
    )
    assert exc.code == "auth_expired"
    assert exc.reconnect is True
    assert exc.retry_after_ms == 5000
    assert "auth_expired" in str(exc)


def test_error_exception_marks_fatal():
    fatal = ChattoRealtimeError("protocol_error", "bad frame", fatal=True)
    assert fatal.fatal is True
    recoverable = ChattoRealtimeError("noop", "ignore me")
    assert recoverable.fatal is False


def test_subscribe_roundtrip():
    """The v4 handshake message serializes and parses back with the fields set."""
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    frame = realtime_pb2.RealtimeSubscribe()
    frame.protocol_version = 4
    frame.bearer_token = "cht_abc"
    frame.initial_state = realtime_pb2.REALTIME_INITIAL_STATE_LIVE_ONLY
    wire = frame.SerializeToString()

    parsed = realtime_pb2.RealtimeSubscribe()
    parsed.ParseFromString(wire)
    assert parsed.protocol_version == 4
    assert parsed.bearer_token == "cht_abc"
    assert parsed.initial_state == realtime_pb2.REALTIME_INITIAL_STATE_LIVE_ONLY


@pytest.mark.parametrize(
    "case,set_",
    [
        ("event", lambda s: s.__setattr__("id", "e")),
        ("heartbeat", lambda s: s.__setattr__("cursor", "c")),
        ("close", lambda s: s.__setattr__("message", "x")),
        ("caught_up", lambda s: s.__setattr__("cursor", "c")),
        ("snapshot", lambda s: s.server.__setattr__("name", "x")),
    ],
)
def test_server_frame_oneof_cases(case: str, set_):
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    frame = realtime_pb2.RealtimeServerFrame()
    set_(getattr(frame, case))  # touching a (nested) field marks the oneof case as set
    assert frame.WhichOneof("frame") == case

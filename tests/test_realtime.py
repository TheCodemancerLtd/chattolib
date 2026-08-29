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
    RealtimeProjectionEvent,
    _wrap_event,
    _wrap_projection_event,
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

    envelope = realtime_pb2.RealtimeEventEnvelope()
    envelope.id = "evt_1"
    envelope.actor_id = "u1"
    envelope.user_typing.room_id = "r1"

    wrapped = _wrap_event(envelope)
    assert isinstance(wrapped, RealtimeEvent)
    assert wrapped.id == "evt_1"
    assert wrapped.kind == "user_typing"
    assert wrapped.actor_id == "u1"
    assert wrapped.payload.room_id == "r1"


def test_wrap_projection_event():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeProjectionEvent()
    envelope.id = "proj_1"
    envelope.resume_cursor = "cur_1"
    op = envelope.operations.add()
    op.room_remove.room_id = "r1"
    op2 = envelope.operations.add()
    op2.reset.SetInParent()

    wrapped = _wrap_projection_event(envelope)
    assert isinstance(wrapped, RealtimeProjectionEvent)
    assert wrapped.id == "proj_1"
    assert wrapped.resume_cursor == "cur_1"
    assert [o.operation for o in wrapped.operations] == ["room_remove", "reset"]
    assert wrapped.operations[0].payload.room_id == "r1"


def test_wrap_event_presence_changed():
    from chattolib._pb.chatto.api.v1 import presence_pb2
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeEventEnvelope()
    envelope.id = "evt_2"
    envelope.presence_changed.user_id = "u1"
    envelope.presence_changed.status = presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE

    wrapped = _wrap_event(envelope)
    assert wrapped.kind == "presence_changed"
    assert wrapped.payload.user_id == "u1"
    assert wrapped.payload.status == presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE
    # No actor_id set on this envelope, so it should be None.
    assert wrapped.actor_id is None


def test_wrap_event_without_variant():
    """Envelope with no oneof set (server bug or truncation) should still wrap."""
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeEventEnvelope()
    envelope.id = "evt_3"

    wrapped = _wrap_event(envelope)
    assert wrapped.kind == ""
    assert wrapped.payload is None


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


def test_frame_roundtrip_hello():
    """Client hello serializes and parses back with the fields we set."""
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    frame = realtime_pb2.RealtimeClientFrame()
    frame.hello.protocol_version = 1
    frame.hello.bearer_token = "cht_abc"
    wire = frame.SerializeToString()

    parsed = realtime_pb2.RealtimeClientFrame()
    parsed.ParseFromString(wire)
    assert parsed.WhichOneof("frame") == "hello"
    assert parsed.hello.protocol_version == 1
    assert parsed.hello.bearer_token == "cht_abc"


@pytest.mark.parametrize(
    "case,attr",
    [
        ("subscribe_events", "subscribe_events"),
        ("ping", "ping"),
    ],
)
def test_client_frame_oneof_cases(case: str, attr: str):
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    frame = realtime_pb2.RealtimeClientFrame()
    getattr(frame, attr).SetInParent()
    assert frame.WhichOneof("frame") == case

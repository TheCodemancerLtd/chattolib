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
    _wrap_event,
    realtime_url,
)


def test_realtime_url_https_to_wss():
    assert realtime_url("https://chat.chatto.run") == "wss://chat.chatto.run/api/realtime"


def test_realtime_url_http_to_ws():
    assert realtime_url("http://localhost:9000") == "ws://localhost:9000/api/realtime"


def test_realtime_url_strips_trailing_slash():
    assert (
        realtime_url("https://chat.chatto.run/") == "wss://chat.chatto.run/api/realtime"
    )


def test_wrap_event_user_typing():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    envelope = realtime_pb2.RealtimeEventEnvelope()
    envelope.id = "evt_1"
    envelope.actor_id = "u1"
    envelope.user_typing.room_id = "r1"
    envelope.user_typing.thread_root_event_id = "t1"

    wrapped = _wrap_event(envelope)
    assert isinstance(wrapped, RealtimeEvent)
    assert wrapped.id == "evt_1"
    assert wrapped.kind == "user_typing"
    assert wrapped.actor_id == "u1"
    assert wrapped.payload.room_id == "r1"
    assert wrapped.payload.thread_root_event_id == "t1"


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
    frame.hello.protocol_version = 2
    frame.hello.bearer_token = "cht_abc"
    wire = frame.SerializeToString()

    parsed = realtime_pb2.RealtimeClientFrame()
    parsed.ParseFromString(wire)
    assert parsed.WhichOneof("frame") == "hello"
    assert parsed.hello.protocol_version == 2
    assert parsed.hello.bearer_token == "cht_abc"


@pytest.mark.parametrize(
    "case,attr",
    [
        ("subscribe_events", "subscribe_events"),
        ("ping", "ping"),
        ("hydrate_room", "hydrate_room"),
    ],
)
def test_client_frame_oneof_cases(case: str, attr: str):
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2

    frame = realtime_pb2.RealtimeClientFrame()
    getattr(frame, attr).SetInParent()
    assert frame.WhichOneof("frame") == case


def test_wrap_projection_event_carries_resume_cursor():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2
    from chattolib.realtime import _wrap_projection_event

    frame = realtime_pb2.RealtimeServerFrame()
    frame.projection_event.id = "pe_1"
    frame.projection_event.actor_id = "u1"
    frame.projection_event.resume_cursor = "cursor_xyz"
    frame.projection_event.operations.add().reset.SetInParent()

    wrapped = _wrap_projection_event(frame)
    assert wrapped.kind == "projection_event"
    assert wrapped.id == "pe_1"
    assert wrapped.actor_id == "u1"
    assert wrapped.payload.resume_cursor == "cursor_xyz"
    assert len(wrapped.payload.operations) == 1


def test_wrap_caught_up_exposes_cursor():
    from chattolib._pb.chatto.realtime.v1 import realtime_pb2
    from chattolib.realtime import _wrap_caught_up

    frame = realtime_pb2.RealtimeServerFrame()
    frame.caught_up.cursor = "cursor_live_boundary"

    wrapped = _wrap_caught_up(frame)
    assert wrapped.kind == "caught_up"
    assert wrapped.id == ""
    assert wrapped.payload.cursor == "cursor_live_boundary"


def test_error_exception_carries_hydrate_hints():
    exc = ChattoRealtimeError(
        "too_many_retained_rooms",
        "cap exceeded",
        retry_after_ms=1000,
        room_id="r1",
    )
    assert exc.retry_after_ms == 1000
    assert exc.room_id == "r1"

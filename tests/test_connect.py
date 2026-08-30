"""Unit tests for the hand-rolled Connect client (chattolib._connect)."""

import asyncio

import pytest

from chattolib._connect import ConnectClientSync
from chattolib.exceptions import ChattoError


def test_sync_client_round_trips_through_async(monkeypatch):
    """A sync execute_unary delegates to the shared async execute_unary."""
    from google.protobuf import struct_pb2

    from chattolib._connect import MethodInfo

    captured = {}

    async def fake_execute_unary(self, *, request, method, headers=None):
        captured["request"] = request
        captured["method"] = method
        return request  # echo the request back as the "response"

    monkeypatch.setattr("chattolib._connect.ConnectClient.execute_unary", fake_execute_unary)

    client = ConnectClientSync("https://example.test")
    msg = struct_pb2.Struct()
    out = client.execute_unary(
        request=msg,
        method=MethodInfo(name="M", service_name="s.S", input=msg, output=msg),
    )
    assert out is msg
    assert captured["request"] is msg
    client.close()


def test_sync_client_refuses_inside_running_loop():
    """Calling the sync client from within a running loop raises ChattoError."""
    client = ConnectClientSync("https://example.test")

    async def call_from_async():
        from google.protobuf import struct_pb2

        from chattolib._connect import MethodInfo

        msg = struct_pb2.Struct()
        client.execute_unary(
            request=msg,
            method=MethodInfo(name="M", service_name="s.S", input=msg, output=msg),
        )

    with pytest.raises(ChattoError):
        asyncio.run(call_from_async())

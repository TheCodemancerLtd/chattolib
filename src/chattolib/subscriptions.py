"""WebSocket subscription handling for real-time Chatto events."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from chattolib import queries as Q

# graphql-ws protocol messages
_GQL_CONNECTION_INIT = "connection_init"
_GQL_CONNECTION_ACK = "connection_ack"
_GQL_SUBSCRIBE = "subscribe"
_GQL_NEXT = "next"
_GQL_ERROR = "error"
_GQL_COMPLETE = "complete"
_GQL_PING = "ping"
_GQL_PONG = "pong"

_KEEPALIVE_INTERVAL = 30  # seconds


def _ws_url(http_url: str) -> str:
    """Convert an HTTP(S) GraphQL URL to its WebSocket equivalent."""
    return http_url.replace("https://", "wss://").replace("http://", "ws://")


async def _connect(url: str, token: str) -> ClientConnection:
    """Establish a graphql-ws connection with auth."""
    ws = await websockets.connect(
        _ws_url(url),
        subprotocols=["graphql-transport-ws"],
        additional_headers={"Authorization": f"Bearer {token}"},
        ping_interval=20,
        ping_timeout=20,
    )
    # Send connection_init
    await ws.send(json.dumps({"type": _GQL_CONNECTION_INIT}))
    # Wait for connection_ack
    ack = json.loads(await ws.recv())
    if ack.get("type") != _GQL_CONNECTION_ACK:
        await ws.close()
        raise ConnectionError(f"Expected connection_ack, got: {ack}")
    return ws


async def _keepalive(ws: ClientConnection) -> None:
    """Send periodic graphql-ws pings to keep the connection alive."""
    try:
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            await ws.send(json.dumps({"type": _GQL_PING}))
    except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
        pass


async def subscribe_space_events(
    url: str,
    token: str,
    space_id: str,
    *,
    subscription_id: str = "1",
) -> AsyncIterator[dict[str, Any]]:
    """Subscribe to real-time events for a space.

    Yields event dicts from the mySpaceEvents subscription.
    """
    ws = await _connect(url, token)
    ping_task = asyncio.create_task(_keepalive(ws))
    try:
        await ws.send(
            json.dumps(
                {
                    "id": subscription_id,
                    "type": _GQL_SUBSCRIBE,
                    "payload": {
                        "query": Q.SUBSCRIPTION_SPACE_EVENTS,
                        "variables": {"spaceId": space_id},
                    },
                }
            )
        )
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("type")
            if msg_type == _GQL_NEXT:
                yield msg["payload"]["data"]["mySpaceEvents"]
            elif msg_type == _GQL_PING:
                await ws.send(json.dumps({"type": _GQL_PONG}))
            elif msg_type == _GQL_PONG:
                pass
            elif msg_type == _GQL_ERROR:
                raise ConnectionError(f"Subscription error: {msg.get('payload')}")
            elif msg_type == _GQL_COMPLETE:
                break
    finally:
        ping_task.cancel()
        await ws.close()


async def subscribe_instance_events(
    url: str,
    token: str,
    *,
    subscription_id: str = "1",
) -> AsyncIterator[dict[str, Any]]:
    """Subscribe to real-time instance-wide events.

    Yields event dicts from the myInstanceEvents subscription.
    """
    ws = await _connect(url, token)
    ping_task = asyncio.create_task(_keepalive(ws))
    try:
        await ws.send(
            json.dumps(
                {
                    "id": subscription_id,
                    "type": _GQL_SUBSCRIBE,
                    "payload": {"query": Q.SUBSCRIPTION_INSTANCE_EVENTS},
                }
            )
        )
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("type")
            if msg_type == _GQL_NEXT:
                yield msg["payload"]["data"]["myInstanceEvents"]
            elif msg_type == _GQL_PING:
                await ws.send(json.dumps({"type": _GQL_PONG}))
            elif msg_type == _GQL_PONG:
                pass
            elif msg_type == _GQL_ERROR:
                raise ConnectionError(f"Subscription error: {msg.get('payload')}")
            elif msg_type == _GQL_COMPLETE:
                break
    finally:
        ping_task.cancel()
        await ws.close()

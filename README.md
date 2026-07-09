# chattolib

**Unofficial** async Python client library for the [Chatto](https://chat.chatto.run) webchat API.

> Chattolib versions track the Chatto server version they target. **0.4.2**
> targets Chatto 0.4.2's ConnectRPC API. The upstream server dropped GraphQL
> in favour of a protobuf-first Connect API (see ADR-042 in chattocorp/chatto),
> and this release is a full rewrite for that transport. Request/response
> traffic uses Connect JSON over HTTP; the realtime channel is a binary
> protobuf WebSocket at `/api/realtime` (needs the ``[realtime]`` extra).

## Install

```bash
pip install chattolib
```

## Quick start

```python
import asyncio
from chattolib import ChattoClient

async def main():
    # Public discovery — no auth required
    async with ChattoClient() as anon:
        profile, login = await anon.get_server()
        print(f"Chatto {profile.version}: {profile.name}")

    # Authenticated calls
    async with await ChattoClient.login("username", "password") as client:
        me = await client.me()
        print(f"Logged in as {me.display_name}")

        for entry in await client.list_rooms():
            if entry.room:
                print(f"  - {entry.room.name}")

asyncio.run(main())
```

## Realtime

Install with the extra:

```bash
pip install 'chattolib[realtime]'
```

Then stream live events:

```python
from chattolib import stream_events

async with await ChattoClient.login("username", "password") as client:
    async for event in stream_events(client):
        print(event.kind, event.actor_id, event.payload)
```

`event.kind` names the protobuf ``oneof`` case (`message_posted`,
`reaction_added`, `presence_changed`, `notification_created`, …).
`event.payload` is the concrete protobuf sub-message — access its fields
directly (e.g. `event.payload.room_id`). Realtime events are invalidation
signals; use the corresponding Connect RPC (`GetRoomEventsAround`,
`GetNotification`, `GetUser`, …) to hydrate the referenced resource.

## Escape hatch

`ChattoClient.call(service, method, request)` invokes any Connect RPC by full
service name, e.g.
`await client.call("chatto.api.v1.MessageService", "GetMessage", {"roomId": ..., "eventId": ...})`.

## License

MIT

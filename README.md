# chattolib

**Unofficial** async Python library for building **bots** for the
[Chatto](https://chat.chatto.run) webchat server.

chattolib gives you a typed, Pythonic client for Chatto's protobuf-first
Connect API (every public, admin, auth and discovery RPC is wrapped, with
dataclasses for the responses) and a realtime WebSocket client that streams
server events as they happen. On top of those sits a small bot framework
(`Bot`) that handles joining rooms, replying, and reacting to events.

> **chattolib is a bot library.** It drives *bot* accounts, which
> authenticate with a key used directly as a bearer token (no password,
> no `/auth/login` round-trip). Normal humans use the Chatto web app; you
> reach the API here as a bot. See the [bot guide](docs/bots.md).
>
> Chattolib versions track the Chatto server version they target. The
> request/response side is a self-contained Connect client over `httpx`
> with generated protobuf bindings (no `connectrpc` dependency); the
> realtime channel is a binary protobuf WebSocket at `/api/realtime`
> (needs the ``[realtime]`` extra).

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

    # Authenticated calls — a bot key is used directly as a bearer token
    async with ChattoClient(token="cht_BK_...") as client:
        me = await client.me()
        print(f"Authenticated as {me.display_name}")

        for entry in await client.list_rooms():
            if entry.room:
                print(f"  - {entry.room.name}")


asyncio.run(main())
```

For a full bot (event handlers, `say`/`reply`/`react`, presence, auto-join),
use the higher-level :class:`~chattolib.bot.Bot` facade — see
[docs/bots.md](docs/bots.md).

## Realtime

Install with the extra:

```bash
pip install 'chattolib[realtime]'
```

Then stream live events:

```python
from chattolib import stream_events

async with ChattoClient(token="cht_BK_...") as client:
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

`ChattoClient.services` exposes the generated Connect service clients
directly (one per Chatto service), for anything the Pythonic wrappers don't
yet cover. For example:

```python
from chattolib._pb.chatto.api.v1 import messages_pb2

resp = await client.services.messages.get_message(
    messages_pb2.GetMessageRequest(room_id=..., event_id=...)
)
```

## License

- chattolib's own code is licensed under **MPL-2.0** (Mozilla Public License
  2.0) — a weak, file-level copyleft. You can use, distribute, and embed
  chattolib in commercial or proprietary software; modifications to the
  library's own files must be released under MPL-2.0.
- Vendored Chatto protobuf definitions under `proto/chatto/**` and the
  generated bindings under `src/chattolib/_pb/chatto/**` are **Apache-2.0**,
  matching upstream [`chattocorp/chatto`](https://github.com/chattocorp/chatto).
- Vendored `buf.validate` material is Apache-2.0 (from
  [`bufbuild/protovalidate`](https://github.com/bufbuild/protovalidate)).

See [LICENSING.md](LICENSING.md) for the full picture and
[REUSE.toml](REUSE.toml) for the machine-readable licence map.

Note: chattolib versions **0.0.1 through 0.4.9** were released under **MIT**.
Those releases remain MIT-licensed forever on PyPI; the MPL-2.0 relicence
applies to newly published releases only.

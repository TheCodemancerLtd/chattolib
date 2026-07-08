# chattolib

**Unofficial** async Python client library for the [Chatto](https://chat.chatto.run) webchat API.

> **Pre-alpha (1.0.0a1)** — targets Chatto 0.4.x's ConnectRPC API. The
> upstream server dropped GraphQL in favour of a protobuf-first Connect API
> (see ADR-042 in chattocorp/chatto), and this release is a full rewrite for
> that transport. The library speaks Connect JSON over HTTP; realtime
> WebSocket support is a follow-up.

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

## Escape hatch

`ChattoClient.call(service, method, request)` invokes any Connect RPC by full
service name, e.g.
`await client.call("chatto.api.v1.MessageService", "GetMessage", {"roomId": ..., "eventId": ...})`.

## License

MIT

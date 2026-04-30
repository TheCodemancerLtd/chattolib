# chattolib

**Unofficial** async Python client library for the [Chatto](https://chat.chatto.run) webchat GraphQL API.

> **Pre-alpha** — API may change without notice. Use at your own risk.

## Install

```bash
pip install chattolib
```

## Quick start

```python
import asyncio
from chattolib import ChattoClient

async def main():
    async with await ChattoClient.login("username", "password") as client:
        me = await client.me()
        print(f"Logged in as {me.display_name}")

        spaces = await client.spaces()
        for space in spaces:
            print(f"  - {space.name}")

asyncio.run(main())
```

## License

MIT

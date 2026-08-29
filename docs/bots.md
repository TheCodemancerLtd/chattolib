# Building bots with chattolib

Chatto 0.5.0 introduced **bot accounts**: user identities flagged `is_bot`
that authenticate with a **key** instead of a username and password. This
module makes chattolib the standard library for building those bots.

## How bot auth works

A bot key (it looks like `cht_BK_...`) is used **directly as a bearer token**.
There is no `/auth/login` round-trip — the key *is* the credential. When you
present it, the server resolves it to a `User` with `is_bot: true` and a
capability grant set, and every Connect RPC you make is authorized by that
grant set.

```python
from chattolib.bot import Bot

async with await Bot.login("cht_BK_...") as bot:
    print(bot.login_name, bot.user.is_bot)   # 'felix_bot' True
```

`Bot.login` also accepts `base_url=` to target a self-hosted or preview
deployment (e.g. `https://next.preview.chatto.run`).

## The three layers

A `Bot` is a thin, opinionated layer over the raw `ChattoClient`:

1. **Key login** — `Bot.login(key, base_url=...)`.
2. **An event dispatcher** — `bot.run()` opens the realtime stream and routes
   incoming events to the async handlers you register with `bot.on(...)`.
3. **Flattened verbs** — `say`, `reply`, `react`, `set_status`, `join_room`,
   `create_room`, and friends, so a bot's brain reads like natural language.

Under the hood the dispatcher consumes the realtime **projection** stream
(protocol v2): durable state (messages, reactions, room changes, presence)
arrives as `RealtimeProjectionEvent`s, while transient signals (typing,
presence) arrive as live `RealtimeEvent`s. You don't have to think about that
split — handlers just receive typed events.

## Events

| `kind`      | Event class          | When it fires                                   |
|-------------|----------------------|-------------------------------------------------|
| `"message"` | `BotMessageEvent`    | a new/updated message in a room you can see      |
| `"reaction"`| `BotReactionEvent`   | a reaction added to / removed from a message    |
| `"presence"`| `BotPresenceEvent`   | a user's presence status changed                 |
| `"typing"`  | `BotTypingEvent`     | a user started/stopped typing in a room/thread  |
| `"room"`    | `BotRoomEvent`       | a room was created/updated/archived, or a member joined/left |
| `"user"`    | `BotUserEvent`       | a user profile was upserted or removed          |
| `"*"`       | (any)                | **all** events — use for logging or a catch-all |

Every event carries a `bot` reference, so a handler can act on it directly:

```python
async def on_message(event):
    if event.is_mention:
        await event.bot.reply(event, "hi!")
```

`BotMessageEvent` exposes `message` (the full `Message`), `actor` (the
author's `User`, when the server included it), `room_id`, `body`, and a
best-effort `is_mention` flag.

## A complete bot

```python
import asyncio
from chattolib.bot import Bot, BotMessageEvent
from chattolib.types import PresenceStatus

async def on_message(event: BotMessageEvent) -> None:
    if event.is_mention:
        await event.bot.reply(event, f"you said: {event.body!r}")

async def main() -> None:
    async with await Bot.login("cht_BK_...") as bot:
        bot.on("message", on_message)
        await bot.set_presence(PresenceStatus.ONLINE)
        for room in await bot.list_rooms():
            if room.room:
                await bot.join_room(room.room.id)
        await bot.run()   # blocks until the stream closes

asyncio.run(main())
```

See [`examples/bot/echo_bot.py`](../examples/bot/echo_bot.py) for a runnable
version that also handles presence and typing, and installs clean signal
handlers for Ctrl-C.

## The verb reference

| Method | Wraps | Notes |
|--------|-------|-------|
| `await bot.say(room_id, body)` | `post_message` | post a plain message |
| `await bot.reply(target, body)` | `post_message` | `target` is a `Message` or `BotMessageEvent`; threads to its room |
| `await bot.react(room_id, event_id, emoji)` | `add_reaction` | |
| `await bot.unreact(room_id, event_id, emoji)` | `remove_reaction` | |
| `await bot.set_presence(status)` | `update_presence` | `ONLINE` / `AWAY` / `DO_NOT_DISTURB` |
| `await bot.set_status(emoji, text)` | `update_custom_status` | |
| `await bot.clear_status()` | `delete_custom_status` | |
| `await bot.join_room(room_id)` | `join_room` | |
| `await bot.leave_room(room_id)` | `leave_room` | |
| `await bot.create_room(name, group_id, ...)` | `create_room` | |
| `await bot.list_rooms()` | `list_rooms` | rooms the bot is a member of |
| `await bot.mark_read(room_id)` | `mark_room_as_read` | |

Anything not wrapped here is available on `bot.client` (the raw
`ChattoClient`) and `bot.client.services` (the raw ConnectRPC stubs), so the
framework never becomes a ceiling on what you can do.

## Reconnection

`bot.run()` reconnects automatically when the server drops the connection,
resuming from the last `resume_cursor`. Pass `until=<asyncio.Event>` to stop
the loop on an external signal, and `retained_room_ids=[...]` to have the
server re-send the projection for specific rooms on (re)connect.

## Requirements

The bot framework needs the **realtime** extra (it drives the WebSocket
stream):

```
pip install "chattolib[realtime]"
```

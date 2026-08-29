"""A minimal, runnable Chatto bot using the chattolib bot framework.

Run it against a preview deployment::

    export CHATTO_BOT_KEY="cht_BK_..."
    export CHATTO_BASE_URL="https://next.preview.chatto.run"   # optional
    python examples/bot/echo_bot.py

The bot:

* logs in with its key (used directly as a bearer token),
* sets its presence to online,
* joins every room it can see,
* and echoes back any message that mentions it.

It also reacts to presence changes and typing, to show the full event
surface. Ctrl-C stops the bot cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal

from chattolib.bot import Bot, BotMessageEvent, BotPresenceEvent, BotTypingEvent
from chattolib.types import PresenceStatus


async def on_message(bot: Bot, event: BotMessageEvent) -> None:
    # Only answer when we're actually mentioned, to keep things quiet.
    if not event.is_mention:
        return
    if event.actor is not None and event.actor.id == bot.user.id:
        return  # ignore our own echoes
    await bot.reply(event, f"you said: {event.body!r}")


async def on_presence(bot: Bot, event: BotPresenceEvent) -> None:
    print(f"[presence] {event.user_id} is now {event.status.value}")


async def on_typing(bot: Bot, event: BotTypingEvent) -> None:
    print(f"[typing] someone is typing in {event.room_id}")


async def main() -> None:
    key = os.environ.get("CHATTO_BOT_KEY")
    if not key:
        raise SystemExit("set CHATTO_BOT_KEY to your bot key (cht_BK_...)")
    base_url = os.environ.get("CHATTO_BASE_URL")

    async with await Bot.login(key, base_url=base_url) as bot:
        print(f"logged in as {bot.login_name!r} (is_bot={bot.user.is_bot})")

        # Register handlers. `on` returns the handler, so it doubles as a
        # decorator if you prefer that style.
        bot.on("message", lambda e: on_message(bot, e))
        bot.on("presence", lambda e: on_presence(bot, e))
        bot.on("typing", lambda e: on_typing(bot, e))

        # Get online and join the rooms we can see.
        await bot.set_presence(PresenceStatus.ONLINE)
        for room in await bot.list_rooms():
            room_id = room.room.id if room.room else ""
            if room_id:
                await bot.join_room(room_id)
                print(f"joined {room_id}")

        # Run until interrupted.
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        await bot.run(until=stop)
        print("stopped")


if __name__ == "__main__":
    asyncio.run(main())

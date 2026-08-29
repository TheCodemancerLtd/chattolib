"""Integration tests for the :class:`~chattolib.bot.Bot` realtime event path.

These run against a live Chatto server and exercise the *receive* side of the
bot framework end-to-end: open the ``/api/realtime`` WebSocket, subscribe to
rooms, and confirm that posted messages come back as typed
:class:`~chattolib.bot.BotMessageEvent` values.

Run with::

    CHATTO_BOT_KEY=cht_BK_... pytest tests/test_bot_integration.py -v

Requires the ``CHATTO_BOT_KEY`` environment variable (a bot key, used
directly as a bearer token). The optional ``CHATTO_BASE_URL`` overrides the
target server (defaults to the production ``https://chat.chatto.run``).

Unlike ``test_integration.py`` (which needs a human login/password), a bot
key is enough here — the bot posts to itself, so no second identity is
required. The ``test_bot_receives_message_from_another_user`` test is skipped
unless ``CHATTO_SECOND_LOGIN``/``CHATTO_SECOND_PASSWORD`` are also set.
"""

import asyncio
import os

import pytest

from chattolib.bot import Bot, BotMessageEvent

pytestmark = pytest.mark.skipif(
    not os.environ.get("CHATTO_BOT_KEY"),
    reason="CHATTO_BOT_KEY env var required",
)

BASE_URL = os.environ.get("CHATTO_BASE_URL", "https://chat.chatto.run")
BOT_KEY = os.environ.get("CHATTO_BOT_KEY")
SENTINEL = "[chattolib-bot-integration] receive-path check"


async def _login_bot() -> Bot:
    assert BOT_KEY is not None  # guaranteed by the module-level skipif
    return await Bot.login(BOT_KEY, base_url=BASE_URL)


async def _pick_member_room_id(bot: Bot) -> str:
    """Return the id of a room the bot is a member of (joining one if needed)."""
    rooms = await bot.list_rooms()
    target = next((r for r in rooms if r.room and r.viewer_state.is_member), None)
    if target is not None:
        return target.room.id
    # No member room yet — join the first room in the first group.
    groups = await bot.list_room_groups()
    if not groups or not groups[0].rooms:
        pytest.skip("bot has no rooms and no room groups to join")
    first = groups[0].rooms[0].room
    if first is None:
        pytest.skip("first room group has no rooms")
    await bot.join_room(first.id)
    return first.id


async def _wait_for_event(
    bot: Bot,
    room_id: str,
    *,
    trigger,
    matches,
    timeout: float = 30.0,
) -> list[BotMessageEvent]:
    """Subscribe to ``room_id``'s timeline, fire ``trigger``, await the event.

    ``trigger`` is an awaitable fired *after* the stream is subscribed (so the
    posted message is not projected before we're listening). ``matches`` is
    called with each incoming :class:`BotMessageEvent`; the first call that
    returns ``True`` ends the wait. Returns the list of matching events.

    Uses ``bot.run(until=...)`` so the stream shuts down cleanly — cancelling
    the run task directly would propagate into the websocket recv loop.
    """
    received: list[BotMessageEvent] = []
    done = asyncio.Event()

    def on_event(event: BotMessageEvent) -> None:
        if matches(event):
            received.append(event)
            done.set()

    bot.on("message", on_event)
    stop = asyncio.Event()
    run_task = asyncio.create_task(bot.run(retained_room_ids=[room_id], until=stop))
    await asyncio.sleep(2)  # let the stream connect + subscribe

    try:
        await trigger()
        await asyncio.wait_for(done.wait(), timeout=timeout)
    finally:
        stop.set()  # tell run() to stop looping
        try:
            await asyncio.wait_for(run_task, timeout=10)
        except (TimeoutError, asyncio.CancelledError, Exception):
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):
                pass
    return received


async def test_bot_receives_its_own_message():
    """Post a message and confirm it comes back over the realtime stream.

    This is the core receive-path check: the bot subscribes to a room, posts
    into it, and the server projects the ``message_posted`` timeline event
    back to the bot as a ``BotMessageEvent``.
    """
    bot = await _login_bot()
    try:
        target_id = await _pick_member_room_id(bot)
        received = await _wait_for_event(
            bot,
            target_id,
            trigger=lambda: bot.say(target_id, SENTINEL),
            matches=lambda e: e.room_id == target_id and e.body == SENTINEL,
        )
        assert len(received) >= 1, "bot did not receive its own posted message"
        # The echoed event should carry the same body and the bot as actor.
        assert received[0].body == SENTINEL
        assert received[0].message.actor_id == bot.user.id
    finally:
        await bot.close()


async def test_bot_receives_message_from_another_user():
    """Receive a message posted by a *different* user (needs 2nd identity).

    Skipped unless ``CHATTO_SECOND_LOGIN``/``CHATTO_SECOND_PASSWORD`` are set.
    """
    second_login = os.environ.get("CHATTO_SECOND_LOGIN")
    second_password = os.environ.get("CHATTO_SECOND_PASSWORD")
    if not second_login or not second_password:
        pytest.skip("CHATTO_SECOND_LOGIN / CHATTO_SECOND_PASSWORD not set")

    from chattolib.client import ChattoClient

    bot = await _login_bot()
    try:
        target_id = await _pick_member_room_id(bot)

        async def trigger() -> None:
            login = ChattoClient.login(second_login, second_password, base_url=BASE_URL)
            async with await login as other:
                await other.post_message(target_id, SENTINEL)

        received = await _wait_for_event(
            bot,
            target_id,
            trigger=trigger,
            matches=lambda e: e.message.actor_id != bot.user.id and e.room_id == target_id,
        )
        assert len(received) >= 1, "bot did not receive the second user's message"
        assert received[0].message.actor_id != bot.user.id
    finally:
        await bot.close()

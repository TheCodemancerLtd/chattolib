"""Tests for the chattolib bot framework (chattolib.bot).

The realtime WebSocket handshake is not exercised here (that is the job of
the live integration test); instead we feed synthetic realtime frames through
the dispatcher and assert the typed events and the convenience verbs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from chattolib._pb.chatto.api.v1 import (
    messages_pb2,
    presence_pb2,
    rooms_pb2,
)
from chattolib._pb.chatto.realtime.v1 import realtime_pb2
from chattolib.bot import (
    Bot,
    BotMessageEvent,
    BotPresenceEvent,
    BotTypingEvent,
)
from chattolib.client import ChattoClient
from chattolib.realtime import _wrap_projection_event
from chattolib.types import PresenceStatus, Room, User


def _bot() -> Bot:
    client = ChattoClient(token="cht_BK_test", base_url="https://example.test")
    bot = Bot.from_client(client)
    bot._user = User(id="u_bot", login="felix_bot", display_name="Felix - the bot", is_bot=True)
    return bot


def _mock(client: ChattoClient, service: str, method: str, response):
    svc = getattr(client._svc, service)
    setattr(svc, method, AsyncMock(return_value=response))
    return getattr(svc, method)


# --- verbs ---------------------------------------------------------------


async def test_say_posts_message():
    bot = _bot()
    resp = messages_pb2.CreateMessageResponse()
    resp.message.id = "e1"
    resp.message.room_id = "r1"
    resp.message.body = "hello"
    m = _mock(bot.client, "messages", "create_message", resp)

    msg = await bot.say("r1", "hello")
    assert msg.body == "hello"
    m.assert_awaited_once()


async def test_reply_threads_to_original():
    bot = _bot()
    resp = messages_pb2.CreateMessageResponse()
    resp.message.id = "e2"
    resp.message.room_id = "r1"
    resp.message.body = "hi!"
    resp.message.in_reply_to = "e1"
    _mock(bot.client, "messages", "create_message", resp)

    target = BotMessageEvent(bot=bot, kind="message", message=resp.message)
    out = await bot.reply(target, "hi!")
    assert out.in_reply_to == "e1"


async def test_react_and_unreact():
    bot = _bot()
    bot.client.add_reaction = AsyncMock(return_value=True)  # type: ignore[method-assign]
    bot.client.remove_reaction = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await bot.react("r1", "e1", "👍") is True
    assert await bot.unreact("r1", "e1", "👍") is True


async def test_set_presence_and_status():
    bot = _bot()
    bot.client.update_presence = AsyncMock(return_value=PresenceStatus.ONLINE)  # type: ignore[method-assign]
    assert await bot.set_presence(PresenceStatus.ONLINE) is PresenceStatus.ONLINE

    bot.client.update_custom_status = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]
    assert await bot.set_status("🛠️", "working") == {"ok": True}


async def test_join_and_create_room():
    bot = _bot()
    join_resp = rooms_pb2.JoinRoomResponse()
    join_resp.room.id = "r1"
    join_resp.room.name = "general"
    _mock(bot.client, "rooms", "join_room", join_resp)
    room = await bot.join_room("r1")
    assert isinstance(room, Room) and room.id == "r1"

    create_resp = rooms_pb2.CreateRoomResponse()
    create_resp.room.id = "r2"
    create_resp.room.name = "new"
    _mock(bot.client, "rooms", "create_room", create_resp)
    created = await bot.create_room("new", "g1")
    assert created.name == "new"


# --- event dispatch -------------------------------------------------------


async def test_dispatch_message_event():
    bot = _bot()
    seen: list[BotMessageEvent] = []

    async def on_message(event: BotMessageEvent) -> None:
        seen.append(event)

    bot.on("message", on_message)

    # Build a projection frame carrying a message_posted timeline event.
    frame = realtime_pb2.RealtimeProjectionEvent()
    frame.id = "p1"
    op = frame.operations.add()
    op.room_timeline_event_upsert.room_id = "r1"
    evt = op.room_timeline_event_upsert.event
    mp = evt.message_posted
    mp.message.id = "e1"
    mp.message.room_id = "r1"
    mp.message.body = "hello @felix_bot"
    mp.message.actor_id = "u1"
    mp.message.created_at.FromJsonString("2026-01-01T00:00:00Z")

    await bot._handle_projection(_wrap_projection_event(frame))
    assert len(seen) == 1
    assert seen[0].message.body == "hello @felix_bot"
    assert seen[0].room_id == "r1"
    assert seen[0].is_mention  # body mentions the bot's login


async def test_dispatch_presence_event():
    bot = _bot()
    seen: list[BotPresenceEvent] = []

    async def on_presence(event: BotPresenceEvent) -> None:
        seen.append(event)

    bot.on("presence", on_presence)

    frame = realtime_pb2.RealtimeProjectionEvent()
    frame.id = "p2"
    op = frame.operations.add()
    op.presences_replace.statuses["u1"] = presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE

    await bot._handle_projection(_wrap_projection_event(frame))
    assert len(seen) == 1
    assert seen[0].user_id == "u1"
    assert seen[0].status is PresenceStatus.ONLINE


async def test_dispatch_live_typing():
    bot = _bot()
    seen: list[BotTypingEvent] = []

    async def on_typing(event: BotTypingEvent) -> None:
        seen.append(event)

    bot.on("typing", on_typing)

    from chattolib.realtime import RealtimeEvent

    live = RealtimeEvent(
        id="evt",
        created_at=None,
        actor_id="u1",
        kind="user_typing",
        payload=realtime_pb2.RealtimeTypingEvent(room_id="r1"),
        raw=None,
    )
    await bot._handle_live(live)
    assert len(seen) == 1
    assert seen[0].room_id == "r1"


async def test_wildcard_handler_receives_all():
    bot = _bot()
    seen: list[str] = []

    async def on_any(event) -> None:
        seen.append(event.kind)

    bot.on("*", on_any)

    frame = realtime_pb2.RealtimeProjectionEvent()
    frame.id = "p3"
    op = frame.operations.add()
    op.presences_replace.statuses["u1"] = presence_pb2.PresenceStatus.PRESENCE_STATUS_AWAY
    await bot._handle_projection(_wrap_projection_event(frame))
    assert seen == ["presence"]


async def test_a_failing_handler_does_not_stop_the_loop():
    bot = _bot()
    calls: list[int] = []

    async def bad(event) -> None:
        raise RuntimeError("boom")

    async def good(event) -> None:
        calls.append(1)

    bot.on("presence", bad)
    bot.on("presence", good)

    frame = realtime_pb2.RealtimeProjectionEvent()
    frame.id = "p4"
    op = frame.operations.add()
    op.presences_replace.statuses["u1"] = presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE
    await bot._handle_projection(_wrap_projection_event(frame))
    assert calls == [1]  # the good handler still ran after the bad one raised

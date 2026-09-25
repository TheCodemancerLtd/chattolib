"""Tests for the chattolib bot framework (chattolib.bot).

The realtime WebSocket handshake is not exercised here (that is the job of
the live integration test); instead we feed synthetic protocol-4 realtime
events through the dispatcher and assert the typed events and the
convenience verbs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from chattolib._pb.chatto.api.v1 import messages_pb2, presence_pb2, rooms_pb2
from chattolib._pb.chatto.realtime.v1 import events_pb2
from chattolib.bot import (
    Bot,
    BotMessageEvent,
    BotPresenceEvent,
    BotPresencePreferenceEvent,
    BotReactionEvent,
    BotRoomEvent,
    BotTypingEvent,
    BotUserEvent,
)
from chattolib.client import ChattoClient
from chattolib.realtime import RealtimeEvent
from chattolib.types import BotInfo, Message, PresenceStatus, Room, User


def _bot() -> Bot:
    client = ChattoClient(token="cht_BK_test", base_url="https://example.test")
    bot = Bot.from_client(client)
    bot._user = User(
        id="u_bot",
        login="felix_bot",
        display_name="Felix - the bot",
        bot=BotInfo(),
    )
    return bot


def _live(
    kind: str, payload, *, actor_id: str | None = None, event_id: str = "e1"
) -> RealtimeEvent:
    """Build a protocol-4 :class:`RealtimeEvent` envelope for the dispatcher."""
    return RealtimeEvent(
        id=event_id,
        created_at=None,
        actor_id=actor_id,
        cursor=None,
        kind=kind,
        payload=payload,
        raw=None,
    )


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
    bot.client.set_presence = AsyncMock(return_value=PresenceStatus.ONLINE)  # type: ignore[method-assign]
    assert await bot.set_presence(PresenceStatus.ONLINE) is PresenceStatus.ONLINE

    bot.client.set_custom_status = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]
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

    # Protocol-4 message_posted is a thin hint; the bot hydrates the full
    # message via get_message, so mock that to supply the body.
    posted = events_pb2.MessagePostedEvent(room_id="r1", body_plaintext="hello @felix_bot")
    msg = Message(id="e1", room_id="r1", created_at=None, actor_id="u1", body="hello @felix_bot")
    bot.client.get_message = AsyncMock(return_value=msg)  # type: ignore[method-assign]

    await bot._handle_live(_live("message_posted", posted, actor_id="u1"))
    assert len(seen) == 1
    assert seen[0].message.body == "hello @felix_bot"
    assert seen[0].room_id == "r1"
    assert seen[0].is_mention  # body mentions the bot's login


async def test_dispatch_message_event_skips_when_hydration_fails():
    bot = _bot()
    seen: list[BotMessageEvent] = []

    async def on_message(event: BotMessageEvent) -> None:
        seen.append(event)

    bot.on("message", on_message)
    posted = events_pb2.MessagePostedEvent(room_id="r1")
    bot.client.get_message = AsyncMock(return_value=None)  # type: ignore[method-assign]

    await bot._handle_live(_live("message_posted", posted, actor_id="u1"))
    assert seen == []


async def test_dispatch_room_lifecycle_event():
    bot = _bot()
    seen: list[BotRoomEvent] = []

    async def on_room(event: BotRoomEvent) -> None:
        seen.append(event)

    bot.on("room", on_room)

    await bot._handle_live(
        _live("room_created", events_pb2.RoomCreatedEvent(room_id="r1", name="general"))
    )
    assert len(seen) == 1
    assert seen[0].detail == "room_created"
    assert seen[0].room is not None
    assert seen[0].room.id == "r1"


async def test_dispatch_presence_event():
    bot = _bot()
    seen: list[BotPresenceEvent] = []

    async def on_presence(event: BotPresenceEvent) -> None:
        seen.append(event)

    bot.on("presence", on_presence)

    payload = events_pb2.PresenceChangedEvent()
    payload.status = presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE
    await bot._handle_live(_live("presence_changed", payload, actor_id="u1"))
    assert len(seen) == 1
    assert seen[0].user_id == "u1"
    assert seen[0].status is PresenceStatus.ONLINE


async def test_dispatch_presence_preference_event():
    """0.5.0b6: the empty viewer_presence_preference_changed hint dispatches as
    a ``presence_preference`` event; handlers hydrate the choice themselves."""
    bot = _bot()
    seen: list[BotPresencePreferenceEvent] = []

    async def on_pref(event: BotPresencePreferenceEvent) -> None:
        seen.append(event)

    bot.on("presence_preference", on_pref)

    await bot._handle_live(
        _live(
            "viewer_presence_preference_changed", events_pb2.ViewerPresencePreferenceChangedEvent()
        )
    )
    assert len(seen) == 1
    assert seen[0].kind == "presence_preference"


async def test_dispatch_reaction_event():
    bot = _bot()
    seen: list[BotReactionEvent] = []

    async def on_reaction(event: BotReactionEvent) -> None:
        seen.append(event)

    bot.on("reaction", on_reaction)

    payload = events_pb2.ReactionAddedEvent(room_id="r1", message_event_id="e1", emoji="👍")
    await bot._handle_live(_live("reaction_added", payload, actor_id="u1"))
    assert len(seen) == 1
    assert seen[0].emoji == "👍"
    assert seen[0].user_id == "u1"
    assert seen[0].added is True


async def test_dispatch_live_typing():
    bot = _bot()
    seen: list[BotTypingEvent] = []

    async def on_typing(event: BotTypingEvent) -> None:
        seen.append(event)

    bot.on("typing", on_typing)

    await bot._handle_live(
        _live("user_typing", events_pb2.UserTypingEvent(room_id="r1"), actor_id="u1")
    )
    assert len(seen) == 1
    assert seen[0].room_id == "r1"


async def test_dispatch_user_event():
    bot = _bot()
    seen: list[BotUserEvent] = []

    async def on_user(event: BotUserEvent) -> None:
        seen.append(event)

    bot.on("user", on_user)

    await bot._handle_live(
        _live("user_account_deleted", events_pb2.UserAccountDeletedEvent(user_id="u1"))
    )
    assert len(seen) == 1
    assert seen[0].removed is True


async def test_wildcard_handler_receives_all():
    bot = _bot()
    seen: list[str] = []

    async def on_any(event) -> None:
        seen.append(event.kind)

    bot.on("*", on_any)

    payload = events_pb2.PresenceChangedEvent()
    payload.status = presence_pb2.PresenceStatus.PRESENCE_STATUS_AWAY
    await bot._handle_live(_live("presence_changed", payload, actor_id="u1"))
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

    payload = events_pb2.PresenceChangedEvent()
    payload.status = presence_pb2.PresenceStatus.PRESENCE_STATUS_ONLINE
    await bot._handle_live(_live("presence_changed", payload, actor_id="u1"))
    assert calls == [1]  # the good handler still ran after the bad one raised


# --- group-aware joining & auto-join say() ------------------------------


async def test_join_room_group():
    bot = _bot()
    join_resp = rooms_pb2.JoinRoomGroupResponse()
    join_resp.joined_room_ids.extend(["r1", "r2"])
    m = _mock(bot.client, "rooms", "join_room_group", join_resp)

    joined = await bot.join_room_group("g1")
    assert joined == ["r1", "r2"]
    m.assert_awaited_once()


async def test_say_auto_joins_when_not_member():
    bot = _bot()
    from chattolib.exceptions import ChattoConnectError

    post = messages_pb2.CreateMessageResponse()
    post.message.id = "e1"
    post.message.room_id = "r1"
    post.message.body = "hi"

    state = {"joined": False}

    async def fake_post(room_id, body, **kwargs):
        if not state["joined"]:
            raise ChattoConnectError("permission_denied", "not a member of this room")
        return post.message

    bot.client.post_message = fake_post  # type: ignore[method-assign]
    join_resp = rooms_pb2.JoinRoomResponse()
    join_resp.room.id = "r1"

    async def fake_join(room_id):
        state["joined"] = True  # joining makes the subsequent post succeed
        return join_resp.room

    bot.client.join_room = fake_join  # type: ignore[method-assign]

    msg = await bot.say("r1", "hi")
    assert msg.id == "e1"
    assert state["joined"] is True


async def test_say_no_join_when_disabled():
    bot = _bot()
    from chattolib.exceptions import ChattoConnectError

    async def deny(room_id, body, **kwargs):
        raise ChattoConnectError("permission_denied", "not a member of this room")

    bot.client.post_message = deny  # type: ignore[method-assign]
    bot.client.join_room = AsyncMock()  # type: ignore[method-assign]

    try:
        await bot.say("r1", "hi", join_if_needed=False)
        raise AssertionError("expected ChattoConnectError to propagate")
    except ChattoConnectError:
        pass
    bot.client.join_room.assert_not_awaited()

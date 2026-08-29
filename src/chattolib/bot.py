"""A small, opinionated framework for building bots on Chatto.

Chatto 0.5.0 introduced *bot accounts*: user identities flagged ``is_bot``
that authenticate with a **key** (e.g. ``cht_BK_...``) rather than a
username/password. The key is used **directly as a bearer token** — there is
no ``/auth/login`` round-trip — and it resolves to a ``User`` with a
capability grant set.

This module turns :class:`chattolib.client.ChattoClient` into the standard
library for bots by adding three things on top of the raw client:

* **Key-based login** — :meth:`Bot.login` builds an authenticated client from
  a bot key in one call.
* **An event dispatcher** — :meth:`Bot.run` opens the realtime stream and
  routes incoming events (messages, reactions, mentions, presence, typing,
  room changes) to the async handlers you register.
* **Flattened verbs** — :meth:`Bot.say`, :meth:`Bot.reply`,
  :meth:`Bot.react`, :meth:`Bot.set_status`, :meth:`Bot.join_room`,
  :meth:`Bot.create_room`, and friends, so a bot's "brain" reads like
  natural language instead of protobuf plumbing.

A minimal bot::

    import asyncio
    from chattolib.bot import Bot

    async def on_message(event):
        if event.body.startswith("!hello"):
            await event.bot.reply(event, "hi!")

    async def main():
        async with await Bot.login("cht_BK_...") as bot:
            bot.on("message", on_message)
            await bot.run()

    asyncio.run(main())

Requires the ``chattolib[realtime]`` extra for the live stream.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from chattolib import _pb  # noqa: F401 — installs the generated pb import path
from chattolib._pb.chatto.api.v1 import presence_pb2
from chattolib.client import ChattoClient
from chattolib.exceptions import ChattoError
from chattolib.realtime import (
    ChattoRealtimeCloseError,
    ChattoRealtimeError,
    RealtimeConnection,
    RealtimeEvent,
    RealtimeProjectionEvent,
    stream_events,
)
from chattolib.types import (
    Message,
    PresenceStatus,
    Room,
    RoomGroup,
    RoomWithViewerState,
    User,
)


def _presence(value: Any) -> PresenceStatus:
    """Coerce a protobuf presence value (int or enum) to a PresenceStatus."""
    name = value.name if hasattr(value, "name") else presence_pb2.PresenceStatus.Name(int(value))
    # The protobuf name is the *value* of our StrEnum (e.g. "PRESENCE_STATUS_ONLINE"),
    # so look it up by value, not by member name.
    for member in PresenceStatus:
        if member.value == name:
            return member
    return PresenceStatus.UNSPECIFIED


__all__ = [
    "Bot",
    "BotError",
    "BotEvent",
    "BotMessageEvent",
    "BotPresenceEvent",
    "BotReactionEvent",
    "BotRoomEvent",
    "BotTypingEvent",
    "BotUserEvent",
]


class BotError(ChattoError):
    """Raised for bot-framework-level errors (bad handlers, bad keys, ...)."""


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass
class BotEvent:
    """Base class for every event the dispatcher delivers to a handler.

    ``bot`` is the owning :class:`Bot`, so a handler can act on the event
    (e.g. ``await event.bot.reply(event, "...")``) without closing over
    globals.
    """

    bot: Bot
    kind: str

    async def _noop(self) -> None:  # pragma: no cover - interface
        ...


@dataclass
class BotMessageEvent(BotEvent):
    """A new or updated message in a room the bot can see.

    ``message`` is the full :class:`Message`. ``actor`` is the author's
    :class:`User` when the server included it; otherwise ``None`` (hydrate
    with ``await bot.get_user(message.actor_id)`` if you need it).
    """

    message: Message
    actor: User | None = None

    @property
    def room_id(self) -> str:
        return self.message.room_id

    @property
    def body(self) -> str | None:
        return self.message.body

    @property
    def is_mention(self) -> bool:
        """True when this message mentions the bot (best-effort)."""
        me = self.bot.user
        if me is None or not self.message.body:
            return False
        return f"@{me.login}" in self.message.body or me.display_name in self.message.body


@dataclass
class BotReactionEvent(BotEvent):
    """A reaction was added to (or removed from) a message."""

    room_id: str
    message_event_id: str
    emoji: str
    user_id: str
    added: bool = True


@dataclass
class BotPresenceEvent(BotEvent):
    """A user's presence status changed."""

    user_id: str
    status: PresenceStatus


@dataclass
class BotTypingEvent(BotEvent):
    """A user started (or stopped) typing in a room/thread."""

    room_id: str
    thread_root_event_id: str | None = None


@dataclass
class BotRoomEvent(BotEvent):
    """A room lifecycle change (created, updated, archived, member join/...)."""

    room: Room | None = None
    detail: str = ""  # e.g. "created", "updated", "archived", "user_joined"


@dataclass
class BotUserEvent(BotEvent):
    """A user profile upsert or removal observed in the projection."""

    user: User | None = None
    removed: bool = False


# ---------------------------------------------------------------------------
# The Bot
# ---------------------------------------------------------------------------


Handler = Callable[[BotEvent], Awaitable[None]]


class Bot:
    """A Chatto bot: an authenticated client plus an event dispatcher and a
    set of convenience verbs.

    Create one with :meth:`login` (from a bot key) or :meth:`from_client`
    (wrapping an already-authenticated :class:`ChattoClient`).
    """

    def __init__(
        self,
        client: ChattoClient,
        *,
        base_url: str | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url or client.base_url
        self._user: User | None = None
        self._handlers: dict[str, list[Handler]] = {}
        self._connection: RealtimeConnection | None = None
        self._running = False

    # -- construction ------------------------------------------------------

    @classmethod
    async def login(
        cls,
        key: str,
        *,
        base_url: str | None = None,
    ) -> Bot:
        """Authenticate a bot with its **key**.

        The key (e.g. ``cht_BK_...``) is used directly as the bearer token —
        no username/password. ``base_url`` defaults to the public Chatto
        server; pass it to target a self-hosted or preview deployment.
        """
        if base_url is None:
            base_url = ChattoClient.DEFAULT_BASE_URL
        client = ChattoClient(token=key, base_url=base_url)
        bot = cls(client, base_url=base_url)
        await bot._probe_identity()
        return bot

    @classmethod
    def from_client(cls, client: ChattoClient) -> Bot:
        """Wrap an already-authenticated client (e.g. a human login)."""
        return cls(client)

    async def _probe_identity(self) -> None:
        """Resolve the bot's own identity and warn (not fail) if not a bot."""
        try:
            self._user = await self._client.me()
        except ChattoError:
            self._user = None
            return
        if self._user is not None and not self._user.is_bot:
            # Not fatal — a human client can drive the same verbs — but surface
            # it so a misconfigured key is obvious.
            import warnings

            warnings.warn(
                f"Bot key authenticated as {self._user.login!r}, which is not "
                "flagged is_bot. It will still work, but this is usually a "
                "misconfigured key.",
                stacklevel=2,
            )

    # -- identity ----------------------------------------------------------

    @property
    def client(self) -> ChattoClient:
        """The underlying :class:`ChattoClient` for any RPC not wrapped here."""
        return self._client

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def user(self) -> User | None:
        """The bot's own :class:`User` profile, once known."""
        return self._user

    @property
    def login_name(self) -> str | None:
        return self._user.login if self._user else None

    @property
    def display_name(self) -> str | None:
        return self._user.display_name if self._user else None

    # -- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> Bot:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()
            self._connection = None
        self._running = False
        await self._client.close()

    # -- event registration ------------------------------------------------

    def on(self, kind: str, handler: Handler) -> Handler:
        """Register ``handler`` for events of ``kind``.

        ``kind`` is one of: ``message``, ``reaction``, ``presence``,
        ``typing``, ``room``, ``user``, ``*`` (all events). ``handler`` is an
        ``async def`` taking a single :class:`BotEvent`. Returns the handler
        so ``on`` can be used as a decorator.
        """
        self._handlers.setdefault(kind, []).append(handler)
        return handler

    def off(self, kind: str, handler: Handler) -> None:
        with contextlib.suppress(ValueError):
            self._handlers[kind].remove(handler)

    async def _dispatch(self, event: BotEvent) -> None:
        handlers = list(self._handlers.get(event.kind, [])) + list(self._handlers.get("*", []))
        for handler in handlers:
            try:
                await handler(event)
            except Exception:  # noqa: BLE001 - one bad handler must not kill the loop
                import logging

                logging.exception("bot handler for %r raised", event.kind)

    # -- the run loop ------------------------------------------------------

    # -- verbs: messaging --------------------------------------------------

    async def say(self, room_id: str, body: str = "", *, join_if_needed: bool = True) -> Message:
        """Post a message to a room. Returns the created :class:`Message`.

        With ``join_if_needed`` (the default), the bot joins the room first if
        it isn't already a member — so a bot that wants to be present
        everywhere can simply ``await bot.say(room_id, ...)`` without a
        separate join step. Pass ``join_if_needed=False`` to instead surface
        the server's ``permission_denied`` if the bot can't post.
        """
        try:
            return await self._client.post_message(room_id, body)
        except ChattoError as exc:
            if not join_if_needed or "not a member" not in str(exc):
                raise
            await self._client.join_room(room_id)
            return await self._client.post_message(room_id, body)

    async def reply(
        self,
        target: BotMessageEvent | Message,
        body: str,
        *,
        also_send_to_channel: bool = False,
    ) -> Message:
        """Reply to a message (or a :class:`BotMessageEvent`) in its room/thread."""
        if isinstance(target, BotMessageEvent):
            target = target.message
        return await self._client.post_message(
            target.room_id,
            body,
            thread_root_event_id=target.thread_root_event_id,
            in_reply_to=target.id,
            also_send_to_channel=also_send_to_channel,
        )

    async def react(self, room_id: str, message_event_id: str, emoji: str) -> bool:
        """Add an emoji reaction to a message."""
        return await self._client.add_reaction(room_id, message_event_id, emoji)

    async def unreact(self, room_id: str, message_event_id: str, emoji: str) -> bool:
        """Remove one of the bot's emoji reactions from a message."""
        return await self._client.remove_reaction(room_id, message_event_id, emoji)

    # -- verbs: presence & status -----------------------------------------

    async def set_presence(self, status: PresenceStatus) -> PresenceStatus:
        """Set the bot's presence (``ONLINE`` / ``IDLE`` / ``DO_NOT_DISTURB``)."""
        return await self._client.update_presence(status)

    async def set_status(self, emoji: str, text: str) -> dict[str, Any]:
        """Set the bot's custom status (e.g. a "working on X" note)."""
        return await self._client.update_custom_status(emoji, text)

    async def clear_status(self) -> dict[str, Any]:
        """Clear the bot's custom status."""
        return await self._client.delete_custom_status()

    # -- verbs: rooms ------------------------------------------------------

    async def join_room(self, room_id: str) -> Room:
        """Join a room. Returns the joined :class:`Room`."""
        return await self._client.join_room(room_id)

    async def join_room_group(self, group_id: str) -> list[str]:
        """Join **all** the rooms in a room group in one call.

        Mirrors the Chatto UI's one-click "join group" action. Returns the
        list of room IDs the bot is now a member of as a result.
        """
        return await self._client.join_room_group(group_id)

    async def list_room_groups(self) -> list[RoomGroup]:
        """List the room groups (and the rooms each contains) the bot can see."""
        return await self._client.list_room_groups()

    async def join_all_rooms(self) -> list[str]:
        """Join every room the bot can see, grouped the way the UI does.

        Joins each room group in one call (so a bot becomes a member of all
        the rooms in a group at once), then joins any ungrouped rooms
        individually. Returns the room IDs the bot is now a member of.
        """
        joined: list[str] = []
        groups = await self.list_room_groups()
        grouped_room_ids: set[str] = set()
        for group in groups:
            for rws in group.rooms:
                if rws.room is not None:
                    grouped_room_ids.add(rws.room.id)
            try:
                joined.extend(await self.join_room_group(group.id))
            except ChattoError:
                # A group the bot can't join is skipped, not fatal.
                continue
        # Rooms that are not part of any group.
        for rws in await self.list_rooms():
            if rws.room is None or rws.room.id in grouped_room_ids:
                continue
            if rws.viewer_state.is_member:
                continue
            try:
                joined.append((await self.join_room(rws.room.id)).id)
            except ChattoError:
                continue
        return joined

    async def leave_room(self, room_id: str) -> bool:
        """Leave a room."""
        return await self._client.leave_room(room_id)

    async def create_room(
        self,
        name: str,
        group_id: str,
        *,
        description: str = "",
        universal: bool = False,
    ) -> Room:
        """Create a room in a room group."""
        return await self._client.create_room(
            name, group_id, description=description, universal=universal
        )

    async def list_rooms(self) -> list[RoomWithViewerState]:
        """List the rooms the bot is a member of."""
        return await self._client.list_rooms()

    async def mark_read(self, room_id: str) -> None:
        """Mark a room as read (clears its unread state for the bot)."""
        await self._client.mark_room_as_read(room_id)

    # -- the run loop ------------------------------------------------------

    async def run(
        self,
        *,
        resume_cursor: str | None = None,
        retained_room_ids: list[str] | None = None,
        until: asyncio.Event | None = None,
    ) -> None:
        """Connect the realtime stream and dispatch events until it closes.

        Reconnects automatically (with the last ``resume_cursor``) when the
        server drops the connection, unless a fatal protocol error is raised.
        Pass ``until`` to stop the loop on an external signal.
        """
        self._running = True
        cursor = resume_cursor
        while self._running:
            if until is not None and until.is_set():
                break
            try:
                async for frame in stream_events(
                    self._client,
                    resume_cursor=cursor,
                    retained_room_ids=retained_room_ids,
                ):
                    if until is not None and until.is_set():
                        break
                    if isinstance(frame, RealtimeProjectionEvent):
                        cursor = frame.resume_cursor or cursor
                        await self._handle_projection(frame)
                    else:
                        await self._handle_live(frame)
            except ChattoRealtimeCloseError as close:
                if not close.reconnect:
                    raise
                # reconnectable close: loop again, resuming from the cursor
                continue
            except ChattoRealtimeError:
                raise
        self._running = False

    async def _handle_live(self, frame: RealtimeEvent) -> None:
        if frame.kind == "presence_changed":
            payload = frame.payload
            event = BotPresenceEvent(
                bot=self,
                kind="presence",
                user_id=payload.user_id,
                status=_presence(payload.status),
            )
            await self._dispatch(event)
        elif frame.kind == "user_typing":
            payload = frame.payload
            await self._dispatch(
                BotTypingEvent(
                    bot=self,
                    kind="typing",
                    room_id=payload.room_id,
                    thread_root_event_id=payload.thread_root_event_id or None,
                )
            )
        elif frame.kind == "session_terminated":
            self._running = False

    async def _handle_projection(self, frame: RealtimeProjectionEvent) -> None:
        for op in frame.operations:
            case = op.operation
            if case == "room_timeline_event_upsert":
                await self._on_timeline_upsert(op)
            elif case == "presences_replace":
                for user_id, status in op.payload.statuses.items():
                    await self._dispatch(
                        BotPresenceEvent(
                            bot=self,
                            kind="presence",
                            user_id=user_id,
                            status=_presence(status),
                        )
                    )
            elif case == "room_upsert":
                room = op.payload.room
                if room is not None:
                    await self._dispatch(
                        BotRoomEvent(
                            bot=self,
                            kind="room",
                            room=Room.parse(_pb_to_dict(room)),
                            detail="upsert",
                        )
                    )
            elif case == "room_remove":
                await self._dispatch(
                    BotRoomEvent(bot=self, kind="room", room=None, detail="removed")
                )
            elif case == "user_upsert":
                await self._dispatch(
                    BotUserEvent(
                        bot=self,
                        kind="user",
                        user=User.parse(_pb_to_dict(op.payload)),
                    )
                )
            elif case == "user_remove":
                await self._dispatch(BotUserEvent(bot=self, kind="user", user=None, removed=True))

    async def _on_timeline_upsert(self, op: Any) -> None:
        payload = op.payload
        event = payload.event
        case = event.WhichOneof("event") if event is not None else None
        if case == "message_posted":
            posted = event.message_posted
            msg = Message.parse(_pb_to_dict(posted.message)) if posted.HasField("message") else None
            if msg is None:
                return
            actor = None
            includes = payload.includes
            if includes is not None and msg.actor_id:
                u = includes.users.get(msg.actor_id)
                if u is not None:
                    actor = User.parse(_pb_to_dict(u))
            await self._dispatch(
                BotMessageEvent(bot=self, kind="message", message=msg, actor=actor)
            )
        elif case in (
            "room_created",
            "room_updated",
            "room_deleted",
            "room_archived",
            "room_unarchived",
            "room_threading_mode_changed",
            "user_joined_room",
            "user_left_room",
        ):
            room = None
            sub = getattr(event, case, None)
            if sub is not None and sub.HasField("room"):
                room = Room.parse(_pb_to_dict(sub.room))
            await self._dispatch(BotRoomEvent(bot=self, kind="room", room=room, detail=case))


def _pb_to_dict(msg: Any) -> dict[str, Any]:
    """Best-effort protobuf -> camelCase dict for the dataclass parsers."""
    from chattolib._transport import pb_to_dict

    return pb_to_dict(msg)

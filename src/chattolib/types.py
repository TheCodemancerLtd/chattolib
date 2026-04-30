"""Dataclasses mirroring Chatto GraphQL object types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# --- Enums ---


class FitMode(str, Enum):
    CONTAIN = "CONTAIN"
    COVER = "COVER"
    EXACT = "EXACT"


class NotificationLevel(str, Enum):
    DEFAULT = "DEFAULT"
    MUTED = "MUTED"
    NORMAL = "NORMAL"
    ALL_MESSAGES = "ALL_MESSAGES"


class PresenceStatus(str, Enum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    AWAY = "AWAY"
    DO_NOT_DISTURB = "DO_NOT_DISTURB"


class TimeFormat(str, Enum):
    UNSPECIFIED = "UNSPECIFIED"
    TWELVE_HOUR = "TWELVE_HOUR"
    TWENTY_FOUR_HOUR = "TWENTY_FOUR_HOUR"


class VideoProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# --- Core types ---


@dataclass
class User:
    id: str
    login: str
    display_name: str
    created_at: datetime | None = None
    avatar_url: str | None = None
    presence_status: PresenceStatus | None = None


@dataclass
class Space:
    id: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    banner_url: str | None = None
    member_count: int = 0
    room_count: int = 0
    viewer_is_member: bool = False


@dataclass
class Room:
    id: str
    space_id: str
    name: str
    description: str | None = None
    archived: bool = False
    auto_join: bool = False
    has_unread: bool = False
    has_mention: bool = False


@dataclass
class Attachment:
    id: str
    space_id: str
    room_id: str
    filename: str
    content_type: str
    size: int
    url: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class LinkPreview:
    url: str
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    site_name: str | None = None
    embed_type: str | None = None
    embed_id: str | None = None


@dataclass
class Reaction:
    emoji: str
    count: int
    has_reacted: bool = False
    users: list[User] = field(default_factory=list)


@dataclass
class MessageEvent:
    """A message event from roomEvents / threadEvents."""

    id: str
    space_id: str
    room_id: str
    body: str | None = None
    created_at: datetime | None = None
    actor: User | None = None
    attachments: list[Attachment] = field(default_factory=list)
    reactions: list[Reaction] = field(default_factory=list)
    in_reply_to: str | None = None
    in_thread: str | None = None
    reply_count: int = 0
    link_preview: LinkPreview | None = None


@dataclass
class RoomEventsPage:
    events: list[MessageEvent]
    has_older: bool = False
    has_newer: bool = False


@dataclass
class FollowedThread:
    space_id: str
    room_id: str
    thread_root_event_id: str
    reply_count: int = 0
    last_reply_at: datetime | None = None
    has_unread: bool = False

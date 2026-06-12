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
    """User presence status as observed on the server."""

    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    AWAY = "AWAY"
    DO_NOT_DISTURB = "DO_NOT_DISTURB"


class PresenceStatusInput(str, Enum):
    """User-settable presence status (server cannot be told OFFLINE)."""

    ONLINE = "ONLINE"
    AWAY = "AWAY"
    DO_NOT_DISTURB = "DO_NOT_DISTURB"


class RoomType(str, Enum):
    CHANNEL = "CHANNEL"
    DM = "DM"


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
class UserSettings:
    timezone: str | None = None
    time_format: TimeFormat = TimeFormat.UNSPECIFIED


@dataclass
class User:
    id: str
    login: str
    display_name: str
    presence_status: PresenceStatus = PresenceStatus.OFFLINE
    created_at: datetime | None = None
    avatar_url: str | None = None
    settings: UserSettings | None = None


@dataclass
class ServerProfile:
    name: str
    logo_url: str | None = None
    banner_url: str | None = None
    welcome_message: str | None = None
    motd: str | None = None
    description: str | None = None


@dataclass
class RoomGroup:
    id: str
    name: str
    description: str = ""
    room_ids: list[str] = field(default_factory=list)


@dataclass
class Room:
    id: str
    name: str
    type: RoomType | None = None
    description: str | None = None
    archived: bool = False
    group_id: str | None = None
    has_unread: bool = False


@dataclass
class RoomBan:
    id: str
    room_id: str
    user_id: str
    moderator_id: str
    reason: str
    created_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass
class AssetURL:
    url: str
    expires_at: datetime | None = None


@dataclass
class Attachment:
    id: str
    room_id: str
    filename: str
    content_type: str
    size: int
    width: int = 0
    height: int = 0
    url: str = ""
    thumbnail_url: str | None = None


@dataclass
class LinkPreview:
    url: str
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    image_asset_id: str | None = None
    site_name: str | None = None
    embed_type: str | None = None
    embed_id: str | None = None


@dataclass
class ReactionSummary:
    emoji: str
    count: int
    has_reacted: bool = False
    users: list[User] = field(default_factory=list)


# Backwards-compatible alias for the renamed Reaction type.
Reaction = ReactionSummary


@dataclass
class MessageEvent:
    """A message event from roomEvents / threadReplies."""

    id: str
    room_id: str
    body: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    actor: User | None = None
    attachments: list[Attachment] = field(default_factory=list)
    reactions: list[ReactionSummary] = field(default_factory=list)
    in_reply_to: str | None = None
    thread_root_event_id: str | None = None
    reply_count: int = 0
    last_reply_at: datetime | None = None
    link_preview: LinkPreview | None = None
    echo_of_event_id: str | None = None
    echo_from_thread_root_event_id: str | None = None
    viewer_is_following_thread: bool | None = None


@dataclass
class RoomEventsPage:
    events: list[MessageEvent]
    has_older: bool = False
    has_newer: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None


@dataclass
class FollowedThread:
    room_id: str
    thread_root_event_id: str
    reply_count: int = 0
    last_reply_at: datetime | None = None
    has_unread: bool = False


@dataclass
class FollowedThreadsPage:
    threads: list[FollowedThread]
    total_count: int = 0
    has_more: bool = False


@dataclass
class NotificationsPage:
    items: list[dict[str, object]]
    total_count: int = 0
    has_more: bool = False

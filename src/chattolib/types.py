"""Dataclasses and enums mirroring Chatto's Connect API messages.

Enum ``value`` strings match the proto JSON encoding used on the wire
(e.g. ``PRESENCE_STATUS_ONLINE``). Parsers below accept both the fully-qualified
form and the short/legacy tail (``ONLINE``) for robustness against older
snapshots or clients that construct short enum strings by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

# --- Enums ---------------------------------------------------------------


def _parse_enum(cls: type[Enum], raw: Any, default: Enum) -> Enum:
    """Accept either the full ``FOO_BAR_BAZ`` form or its tail (``BAZ``)."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, cls):
        return raw
    try:
        return cls(raw)
    except ValueError:
        pass
    # Tolerate integer values from proto JSON alternate encoding.
    if isinstance(raw, int):
        for member in cls:
            if getattr(member, "_proto_index", None) == raw:
                return member
    text = str(raw)
    for member in cls:
        value = member.value if isinstance(member.value, str) else ""
        if value.endswith("_" + text) or value == text:
            return member
    return default


class PresenceStatus(StrEnum):
    UNSPECIFIED = "PRESENCE_STATUS_UNSPECIFIED"
    ONLINE = "PRESENCE_STATUS_ONLINE"
    AWAY = "PRESENCE_STATUS_AWAY"
    DO_NOT_DISTURB = "PRESENCE_STATUS_DO_NOT_DISTURB"
    OFFLINE = "PRESENCE_STATUS_OFFLINE"


class TimeFormat(StrEnum):
    UNSPECIFIED = "TIME_FORMAT_UNSPECIFIED"
    AUTO = "TIME_FORMAT_AUTO"
    HOUR_12 = "TIME_FORMAT_12_HOUR"
    HOUR_24 = "TIME_FORMAT_24_HOUR"


class RoomKind(StrEnum):
    UNSPECIFIED = "ROOM_KIND_UNSPECIFIED"
    CHANNEL = "ROOM_KIND_CHANNEL"
    DM = "ROOM_KIND_DM"


class RoomThreadingMode(StrEnum):
    UNSPECIFIED = "ROOM_THREADING_MODE_UNSPECIFIED"
    REQUIRED = "ROOM_THREADING_MODE_REQUIRED"
    ENCOURAGED = "ROOM_THREADING_MODE_ENCOURAGED"
    ENABLED = "ROOM_THREADING_MODE_ENABLED"
    DISABLED = "ROOM_THREADING_MODE_DISABLED"


class RoomDirectoryScope(StrEnum):
    UNSPECIFIED = "ROOM_DIRECTORY_SCOPE_UNSPECIFIED"
    ALL = "ROOM_DIRECTORY_SCOPE_ALL"
    CHANNELS = "ROOM_DIRECTORY_SCOPE_CHANNELS"
    DMS = "ROOM_DIRECTORY_SCOPE_DMS"


class NotificationLevel(StrEnum):
    UNSPECIFIED = "NOTIFICATION_LEVEL_UNSPECIFIED"
    DEFAULT = "NOTIFICATION_LEVEL_DEFAULT"
    MUTED = "NOTIFICATION_LEVEL_MUTED"
    NORMAL = "NOTIFICATION_LEVEL_NORMAL"
    ALL_MESSAGES = "NOTIFICATION_LEVEL_ALL_MESSAGES"


class ImageFitMode(StrEnum):
    UNSPECIFIED = "IMAGE_FIT_MODE_UNSPECIFIED"
    CONTAIN = "IMAGE_FIT_MODE_CONTAIN"
    COVER = "IMAGE_FIT_MODE_COVER"


class VideoProcessingStatus(StrEnum):
    UNSPECIFIED = "MESSAGE_VIDEO_PROCESSING_STATUS_UNSPECIFIED"
    PROCESSING = "MESSAGE_VIDEO_PROCESSING_STATUS_PROCESSING"
    COMPLETED = "MESSAGE_VIDEO_PROCESSING_STATUS_COMPLETED"
    FAILED = "MESSAGE_VIDEO_PROCESSING_STATUS_FAILED"


class AssetUploadStatus(StrEnum):
    UNSPECIFIED = "ASSET_UPLOAD_STATUS_UNSPECIFIED"
    OPEN = "ASSET_UPLOAD_STATUS_OPEN"
    COMPLETED = "ASSET_UPLOAD_STATUS_COMPLETED"
    CANCELLED = "ASSET_UPLOAD_STATUS_CANCELLED"


class AdminRoomLayoutItemKind(StrEnum):
    UNSPECIFIED = "ADMIN_ROOM_LAYOUT_ITEM_KIND_UNSPECIFIED"
    ROOM = "ADMIN_ROOM_LAYOUT_ITEM_KIND_ROOM"
    SIDEBAR_LINK = "ADMIN_ROOM_LAYOUT_ITEM_KIND_SIDEBAR_LINK"


# --- Time helpers --------------------------------------------------------


def parse_datetime(value: Any) -> datetime | None:
    """Parse an RFC 3339 timestamp string (proto JSON encoding for Timestamp)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_datetime(value: datetime) -> str:
    """Format a ``datetime`` as an RFC 3339 UTC timestamp (``...Z``)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- Core resource dataclasses ------------------------------------------


@dataclass
class CustomUserStatus:
    emoji: str
    text: str
    expires_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> CustomUserStatus | None:
        if not data:
            return None
        return cls(
            emoji=data.get("emoji", ""),
            text=data.get("text", ""),
            expires_at=parse_datetime(data.get("expiresAt")),
        )


@dataclass
class User:
    id: str
    login: str
    display_name: str
    presence_status: PresenceStatus = PresenceStatus.UNSPECIFIED
    avatar_url: str | None = None
    deleted: bool = False
    custom_status: CustomUserStatus | None = None
    is_bot: bool = False
    bio: str | None = None
    timezone: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> User | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            login=data.get("login", ""),
            display_name=data.get("displayName", ""),
            presence_status=_parse_enum(
                PresenceStatus, data.get("presenceStatus"), PresenceStatus.UNSPECIFIED
            ),  # type: ignore[arg-type]
            avatar_url=data.get("avatarUrl"),
            deleted=bool(data.get("deleted", False)),
            custom_status=CustomUserStatus.parse(data.get("customStatus")),
            is_bot=bool(data.get("isBot", False)),
            bio=data.get("bio"),
            timezone=data.get("timezone"),
        )


@dataclass
class UserSettings:
    timezone: str | None = None
    time_format: TimeFormat = TimeFormat.UNSPECIFIED

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> UserSettings:
        data = data or {}
        return cls(
            timezone=data.get("timezone"),
            time_format=_parse_enum(TimeFormat, data.get("timeFormat"), TimeFormat.UNSPECIFIED),  # type: ignore[arg-type]
        )


@dataclass
class ViewerUser:
    profile: User | None
    settings: UserSettings
    has_verified_email: bool = False
    viewer_can_delete_account: bool = False
    last_login_change: datetime | None = None
    has_password: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ViewerUser | None:
        if not data:
            return None
        return cls(
            profile=User.parse(data.get("profile")),
            settings=UserSettings.parse(data.get("settings")),
            has_verified_email=bool(data.get("hasVerifiedEmail", False)),
            viewer_can_delete_account=bool(data.get("viewerCanDeleteAccount", False)),
            last_login_change=parse_datetime(data.get("lastLoginChange")),
            has_password=bool(data.get("hasPassword", False)),
        )


@dataclass
class DirectoryMember:
    user: User | None
    roles: list[str] = field(default_factory=list)
    created_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> DirectoryMember | None:
        if not data:
            return None
        return cls(
            user=User.parse(data.get("user")),
            roles=list(data.get("roles") or []),
            created_at=parse_datetime(data.get("createdAt")),
        )


@dataclass
class Page:
    total_count: int = 0
    has_more: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> Page:
        data = data or {}
        return cls(
            total_count=int(data.get("totalCount", 0)),
            has_more=bool(data.get("hasMore", False)),
        )


@dataclass
class ServerProfile:
    name: str
    version: str = ""
    logo_url: str | None = None
    banner_url: str | None = None
    welcome_message: str | None = None
    description: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerProfile:
        data = data or {}
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            logo_url=data.get("logoUrl"),
            banner_url=data.get("bannerUrl"),
            welcome_message=data.get("welcomeMessage"),
            description=data.get("description"),
        )


@dataclass
class ProviderMetadata:
    id: str
    type: str
    label: str
    login_url: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ProviderMetadata:
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            label=data.get("label", ""),
            login_url=data.get("loginUrl", ""),
        )


@dataclass
class ServerLogin:
    direct_registration_enabled: bool = False
    providers: list[ProviderMetadata] = field(default_factory=list)
    authorize_url: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerLogin:
        data = data or {}
        return cls(
            direct_registration_enabled=bool(data.get("directRegistrationEnabled", False)),
            providers=[ProviderMetadata.parse(p) for p in data.get("providers") or []],
            authorize_url=data.get("authorizeUrl", ""),
        )


@dataclass
class ServerRuntimeConfig:
    push_notifications_enabled: bool = False
    vapid_public_key: str | None = None
    livekit_url: str | None = None
    video_processing_enabled: bool = False
    max_upload_size: int = 0
    max_video_upload_size: int = 0
    message_edit_window_seconds: int = 0

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerRuntimeConfig:
        data = data or {}
        return cls(
            push_notifications_enabled=bool(data.get("pushNotificationsEnabled", False)),
            vapid_public_key=data.get("vapidPublicKey"),
            livekit_url=data.get("livekitUrl"),
            video_processing_enabled=bool(data.get("videoProcessingEnabled", False)),
            max_upload_size=int(data.get("maxUploadSize", 0)),
            max_video_upload_size=int(data.get("maxVideoUploadSize", 0)),
            message_edit_window_seconds=int(data.get("messageEditWindowSeconds", 0)),
        )


@dataclass
class Room:
    id: str
    kind: RoomKind = RoomKind.UNSPECIFIED
    name: str = ""
    description: str = ""
    archived: bool = False
    group_id: str = ""
    universal: bool = False
    slow_mode_seconds: int = 0
    threading_mode: RoomThreadingMode = RoomThreadingMode.UNSPECIFIED

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> Room | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            kind=_parse_enum(RoomKind, data.get("kind"), RoomKind.UNSPECIFIED),  # type: ignore[arg-type]
            name=data.get("name", ""),
            description=data.get("description", ""),
            archived=bool(data.get("archived", False)),
            group_id=data.get("groupId", ""),
            universal=bool(data.get("universal", False)),
            slow_mode_seconds=int(data.get("slowModeSeconds") or 0),
            threading_mode=_parse_enum(
                RoomThreadingMode,
                data.get("threadingMode"),
                RoomThreadingMode.UNSPECIFIED,
            ),  # type: ignore[arg-type]
        )


@dataclass
class RoomSummary:
    id: str
    kind: RoomKind = RoomKind.UNSPECIFIED
    name: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomSummary | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            kind=_parse_enum(RoomKind, data.get("kind"), RoomKind.UNSPECIFIED),  # type: ignore[arg-type]
            name=data.get("name", ""),
        )


@dataclass
class RoomViewerState:
    is_member: bool = False
    has_unread: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomViewerState:
        data = data or {}
        return cls(
            is_member=bool(data.get("isMember", False)),
            has_unread=bool(data.get("hasUnread", False)),
        )


@dataclass
class RoomWithViewerState:
    room: Room | None
    viewer_state: RoomViewerState

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomWithViewerState | None:
        if not data:
            return None
        return cls(
            room=Room.parse(data.get("room")),
            viewer_state=RoomViewerState.parse(data.get("viewerState")),
        )


@dataclass
class SidebarLink:
    id: str
    label: str
    url: str


@dataclass
class RoomGroup:
    id: str
    name: str
    description: str = ""
    rooms: list[RoomWithViewerState] = field(default_factory=list)
    sidebar_links: list[SidebarLink] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomGroup | None:
        if not data:
            return None
        rooms: list[RoomWithViewerState] = []
        links: list[SidebarLink] = []
        for item in data.get("items") or []:
            room = RoomWithViewerState.parse(item.get("room"))
            if room:
                rooms.append(room)
            sl = item.get("sidebarLink")
            if sl:
                links.append(
                    SidebarLink(
                        id=sl.get("id", ""),
                        label=sl.get("label", ""),
                        url=sl.get("url", ""),
                    )
                )
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            rooms=rooms,
            sidebar_links=links,
        )


@dataclass
class RoomBan:
    id: str
    room_id: str
    user_id: str
    moderator_id: str = ""
    reason: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    room: Room | None = None
    user: DirectoryMember | None = None
    moderator: DirectoryMember | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomBan | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            room_id=data.get("roomId", ""),
            user_id=data.get("userId", ""),
            moderator_id=data.get("moderatorId", ""),
            reason=data.get("reason", ""),
            created_at=parse_datetime(data.get("createdAt")),
            expires_at=parse_datetime(data.get("expiresAt")),
            room=Room.parse(data.get("room")),
            user=DirectoryMember.parse(data.get("user")),
            moderator=DirectoryMember.parse(data.get("moderator")),
        )


@dataclass
class AssetUrl:
    url: str
    expires_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> AssetUrl | None:
        if not data:
            return None
        return cls(
            url=data.get("url", ""),
            expires_at=parse_datetime(data.get("expiresAt")),
        )


@dataclass
class VideoVariant:
    quality: str
    width: int
    height: int
    size: int
    asset_url: AssetUrl | None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> VideoVariant:
        return cls(
            quality=data.get("quality", ""),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            size=int(data.get("size", 0)),
            asset_url=AssetUrl.parse(data.get("assetUrl")),
        )


@dataclass
class VideoProcessing:
    status: VideoProcessingStatus = VideoProcessingStatus.UNSPECIFIED
    duration_ms: int = 0
    width: int = 0
    height: int = 0
    source_available: bool = False
    reason_code: str = ""
    thumbnail_asset_url: AssetUrl | None = None
    variants: list[VideoVariant] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> VideoProcessing | None:
        if not data:
            return None
        return cls(
            status=_parse_enum(
                VideoProcessingStatus,
                data.get("status"),
                VideoProcessingStatus.UNSPECIFIED,
            ),  # type: ignore[arg-type]
            duration_ms=int(data.get("durationMs", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            source_available=bool(data.get("sourceAvailable", False)),
            reason_code=data.get("reasonCode", ""),
            thumbnail_asset_url=AssetUrl.parse(data.get("thumbnailAssetUrl")),
            variants=[VideoVariant.parse(v) for v in data.get("variants") or []],
        )


@dataclass
class MessageAttachment:
    id: str
    filename: str
    content_type: str
    width: int = 0
    height: int = 0
    asset_url: AssetUrl | None = None
    thumbnail_asset_url: AssetUrl | None = None
    video_processing: VideoProcessing | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> MessageAttachment:
        return cls(
            id=data.get("id", ""),
            filename=data.get("filename", ""),
            content_type=data.get("contentType", ""),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            asset_url=AssetUrl.parse(data.get("assetUrl")),
            thumbnail_asset_url=AssetUrl.parse(data.get("thumbnailAssetUrl")),
            video_processing=VideoProcessing.parse(data.get("videoProcessing")),
        )


@dataclass
class SocialPostAuthor:
    display_name: str = ""
    handle: str = ""
    avatar_url: str | None = None
    avatar_asset_id: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> SocialPostAuthor | None:
        if not data:
            return None
        return cls(
            display_name=data.get("displayName", ""),
            handle=data.get("handle", ""),
            avatar_url=data.get("avatarUrl"),
            avatar_asset_id=data.get("avatarAssetId"),
        )


@dataclass
class SocialPostImage:
    url: str = ""
    asset_id: str = ""
    alt: str = ""
    width: int = 0
    height: int = 0

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> SocialPostImage | None:
        if not data:
            return None
        return cls(
            url=data.get("url", ""),
            asset_id=data.get("assetId", ""),
            alt=data.get("alt", ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
        )


@dataclass
class SocialPostExternalLink:
    url: str = ""
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    image_asset_id: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> SocialPostExternalLink | None:
        if not data:
            return None
        return cls(
            url=data.get("url", ""),
            title=data.get("title"),
            description=data.get("description"),
            image_url=data.get("imageUrl"),
            image_asset_id=data.get("imageAssetId"),
        )


@dataclass
class SocialPostPreview:
    provider: str = ""
    author: SocialPostAuthor | None = None
    text: str | None = None
    published_at: datetime | None = None
    images: list[SocialPostImage] = field(default_factory=list)
    external_link: SocialPostExternalLink | None = None
    content_warning: str | None = None
    url: str | None = None
    quoted_post: SocialPostPreview | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> SocialPostPreview | None:
        if not data:
            return None
        return cls(
            provider=data.get("provider", ""),
            author=SocialPostAuthor.parse(data.get("author")),
            text=data.get("text"),
            published_at=parse_datetime(data.get("publishedAt")),
            images=[
                i
                for i in (SocialPostImage.parse(i) for i in data.get("images") or [])
                if i is not None
            ],
            external_link=SocialPostExternalLink.parse(data.get("externalLink")),
            content_warning=data.get("contentWarning"),
            url=data.get("url"),
            quoted_post=SocialPostPreview.parse(data.get("quotedPost")),
        )


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
    social_post: SocialPostPreview | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> LinkPreview | None:
        if not data:
            return None
        return cls(
            url=data.get("url", ""),
            title=data.get("title"),
            description=data.get("description"),
            image_url=data.get("imageUrl"),
            image_asset_id=data.get("imageAssetId"),
            site_name=data.get("siteName"),
            embed_type=data.get("embedType"),
            embed_id=data.get("embedId"),
            social_post=SocialPostPreview.parse(data.get("socialPost")),
        )


@dataclass
class PinnedMessage:
    """A pinned message in a room (wraps the pinned :class:`Message")."""

    message: Message | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> PinnedMessage | None:
        if not data:
            return None
        return cls(message=Message.parse(data.get("message")))


@dataclass
class PinnedMessagesPage:
    pinned_messages: list[PinnedMessage] = field(default_factory=list)
    page: Page = field(default_factory=Page)
    latest_pin_marker: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> PinnedMessagesPage:
        return cls(
            pinned_messages=[
                p
                for p in (PinnedMessage.parse(m) for m in data.get("pinnedMessages") or [])
                if p is not None
            ],
            page=Page.parse(data.get("page")),
            latest_pin_marker=data.get("latestPinMarker"),
        )


@dataclass
class MessageReaction:
    emoji: str
    count: int = 0
    has_reacted: bool = False
    preview_user_ids: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> MessageReaction:
        return cls(
            emoji=data.get("emoji", ""),
            count=int(data.get("count", 0)),
            has_reacted=bool(data.get("hasReacted", False)),
            preview_user_ids=list(data.get("previewUserIds") or []),
        )


@dataclass
class ThreadSummary:
    thread_root_event_id: str
    reply_count: int = 0
    last_reply_at: datetime | None = None
    participant_preview_user_ids: list[str] = field(default_factory=list)
    participant_count: int = 0
    is_following: bool | None = None
    has_unread: bool | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ThreadSummary | None:
        if not data:
            return None
        viewer = data.get("viewerState") or {}
        return cls(
            thread_root_event_id=data.get("threadRootEventId", ""),
            reply_count=int(data.get("replyCount", 0)),
            last_reply_at=parse_datetime(data.get("lastReplyAt")),
            participant_preview_user_ids=list(data.get("participantPreviewUserIds") or []),
            participant_count=int(data.get("participantCount", 0)),
            is_following=viewer.get("isFollowing") if "isFollowing" in viewer else None,
            has_unread=viewer.get("hasUnread") if "hasUnread" in viewer else None,
        )


@dataclass
class Message:
    id: str
    room_id: str
    created_at: datetime | None
    actor_id: str
    body: str | None = None
    attachments: list[MessageAttachment] = field(default_factory=list)
    link_preview: LinkPreview | None = None
    updated_at: datetime | None = None
    in_reply_to: str = ""
    thread_root_event_id: str = ""
    echo_of_event_id: str = ""
    echo_from_thread_root_event_id: str = ""
    channel_echo_event_id: str = ""
    reactions: list[MessageReaction] = field(default_factory=list)
    thread: ThreadSummary | None = None
    deleted_at: datetime | None = None
    pinned: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> Message | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            room_id=data.get("roomId", ""),
            created_at=parse_datetime(data.get("createdAt")),
            actor_id=data.get("actorId", ""),
            body=data.get("body"),
            attachments=[MessageAttachment.parse(a) for a in data.get("attachments") or []],
            link_preview=LinkPreview.parse(data.get("linkPreview")),
            updated_at=parse_datetime(data.get("updatedAt")),
            in_reply_to=data.get("inReplyTo", ""),
            thread_root_event_id=data.get("threadRootEventId", ""),
            echo_of_event_id=data.get("echoOfEventId", ""),
            echo_from_thread_root_event_id=data.get("echoFromThreadRootEventId", ""),
            channel_echo_event_id=data.get("channelEchoEventId", ""),
            reactions=[MessageReaction.parse(r) for r in data.get("reactions") or []],
            thread=ThreadSummary.parse(data.get("thread")),
            deleted_at=parse_datetime(data.get("deletedAt")),
            pinned=bool(data.get("pinned", False)),
        )


@dataclass
class TimelineEvent:
    id: str
    created_at: datetime | None
    actor_id: str = ""
    kind: str = ""  # "message_posted", "room_created", "user_joined_room", ...
    message: Message | None = None
    room_id: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> TimelineEvent:
        kind = ""
        message: Message | None = None
        room_id = ""
        for candidate in (
            "messagePosted",
            "roomCreated",
            "roomUpdated",
            "roomDeleted",
            "roomArchived",
            "roomUnarchived",
            "userJoinedRoom",
            "userLeftRoom",
        ):
            payload = data.get(candidate)
            if payload is None:
                continue
            kind = _snake_case(candidate)
            if candidate == "messagePosted":
                message = Message.parse(payload.get("message"))
            else:
                room_id = payload.get("roomId", "")
            break
        return cls(
            id=data.get("id", ""),
            created_at=parse_datetime(data.get("createdAt")),
            actor_id=data.get("actorId", ""),
            kind=kind,
            message=message,
            room_id=room_id,
        )


def _snake_case(name: str) -> str:
    out: list[str] = []
    for ch in name:
        if ch.isupper() and out:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


@dataclass
class TimelinePage:
    events: list[TimelineEvent] = field(default_factory=list)
    start_cursor: str = ""
    end_cursor: str = ""
    has_older: bool = False
    has_newer: bool = False
    users_by_id: dict[str, User] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> TimelinePage:
        data = data or {}
        includes = data.get("includes") or {}
        users_raw = includes.get("users") or {}
        users: dict[str, User] = {}
        for uid, user_data in users_raw.items():
            parsed_user = User.parse(user_data)
            if parsed_user is not None:
                users[uid] = parsed_user
        return cls(
            events=[TimelineEvent.parse(e) for e in data.get("events") or []],
            start_cursor=data.get("startCursor", ""),
            end_cursor=data.get("endCursor", ""),
            has_older=bool(data.get("hasOlder", False)),
            has_newer=bool(data.get("hasNewer", False)),
            users_by_id=users,
        )


@dataclass
class FollowedThread:
    room: RoomSummary | None
    root_message: Message | None
    thread: ThreadSummary | None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> FollowedThread:
        return cls(
            room=RoomSummary.parse(data.get("room")),
            root_message=Message.parse(data.get("rootMessage")),
            thread=ThreadSummary.parse(data.get("thread")),
        )


@dataclass
class FollowedThreadsPage:
    threads: list[FollowedThread] = field(default_factory=list)
    page: Page = field(default_factory=Page)
    users_by_id: dict[str, User] = field(default_factory=dict)


@dataclass
@dataclass
class NotificationMessageReference:
    """A reference to the message a notification signal points at."""

    room: RoomSummary | None = None
    event_id: str = ""
    thread_root_event_id: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationMessageReference | None:
        if not data:
            return None
        return cls(
            room=RoomSummary.parse(data.get("room")),
            event_id=data.get("eventId", ""),
            thread_root_event_id=data.get("threadRootEventId"),
        )


@dataclass
class NotificationSignal:
    """The concrete signal that produced a :class:`NotificationOccurrence`.

    ``kind`` names the ``oneof kind`` case set on the signal
    (``direct_message_received``, ``direct_mention_received``,
    ``reply_received``, ``role_mention_received``, ``here_mention_received``,
    ``all_mention_received``, ``followed_thread_activity``,
    ``followed_room_activity``, ``reaction_received``,
    ``room_message_received``). ``message`` is the referenced
    :class:`NotificationMessageReference`.
    """

    kind: str
    message: NotificationMessageReference | None
    role_names: list[str] = field(default_factory=list)
    emoji: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationSignal | None:
        if not data:
            return None
        kind = ""
        message: NotificationMessageReference | None = None
        for candidate in (
            "directMessageReceived",
            "directMentionReceived",
            "replyReceived",
            "roleMentionReceived",
            "hereMentionReceived",
            "allMentionReceived",
            "followedThreadActivity",
            "followedRoomActivity",
            "reactionReceived",
            "roomMessageReceived",
        ):
            payload = data.get(candidate)
            if payload is None:
                continue
            kind = _snake_case(candidate)
            message = NotificationMessageReference.parse(payload.get("message"))
            break
        return cls(
            kind=kind,
            message=message,
            role_names=list(data.get("roleNames") or []),
            emoji=data.get("emoji", ""),
        )


@dataclass
class NotificationOccurrence:
    """One stored notification in the viewer's notification center.

    Replaces the pre-0.5 ``Notification`` message: the old oneof of
    ``directMessage``/``mention``/``reply``/``roomMessage`` is now the
    ``signal`` field, and dismissals became read/deletions.
    """

    id: str
    created_at: datetime | None
    actor: User | None
    signal: NotificationSignal | None = None
    unread: bool = False
    expires_at: datetime | None = None
    attention_level: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationOccurrence | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            created_at=parse_datetime(data.get("createdAt")),
            actor=User.parse(data.get("actor")),
            signal=NotificationSignal.parse(data.get("signal")),
            unread=bool(data.get("unread", False)),
            expires_at=parse_datetime(data.get("expiresAt")),
            attention_level=data.get("attentionLevel", ""),
        )


@dataclass
class NotificationRoomUnreadCount:
    room_id: str
    unread_count: int = 0
    important_unread_count: int = 0

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationRoomUnreadCount | None:
        if not data:
            return None
        return cls(
            room_id=data.get("roomId", ""),
            unread_count=int(data.get("unreadCount") or 0),
            important_unread_count=int(data.get("importantUnreadCount") or 0),
        )


@dataclass
class NotificationPolicy:
    """Effective notification policy for a scope (server, room group, room)."""

    overrides: dict[str, Any] | None = None
    effective: dict[str, Any] | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationPolicy:
        data = data or {}
        return cls(
            overrides=data.get("overrides"),
            effective=data.get("effective"),
        )


@dataclass
class NotificationOccurrencesPage:
    occurrences: list[NotificationOccurrence] = field(default_factory=list)
    page: Page = field(default_factory=Page)
    unread_count: int = 0
    next_expiry_at: datetime | None = None
    room_unread_counts: list[NotificationRoomUnreadCount] = field(default_factory=list)
    important_unread_count: int = 0

    @classmethod
    def parse(cls, data: dict[str, Any]) -> NotificationOccurrencesPage:
        return cls(
            occurrences=[
                o
                for o in (NotificationOccurrence.parse(n) for n in data.get("occurrences") or [])
                if o is not None
            ],
            page=Page.parse(data.get("page")),
            unread_count=int(data.get("unreadCount") or 0),
            next_expiry_at=parse_datetime(data.get("nextExpiryAt")),
            room_unread_counts=[
                c
                for c in (
                    NotificationRoomUnreadCount.parse(r) for r in data.get("roomUnreadCounts") or []
                )
                if c is not None
            ],
            important_unread_count=int(data.get("importantUnreadCount") or 0),
        )


@dataclass
class NotificationPreference:
    level: NotificationLevel = NotificationLevel.UNSPECIFIED
    effective_level: NotificationLevel = NotificationLevel.UNSPECIFIED

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationPreference:
        data = data or {}
        return cls(
            level=_parse_enum(NotificationLevel, data.get("level"), NotificationLevel.UNSPECIFIED),  # type: ignore[arg-type]
            effective_level=_parse_enum(
                NotificationLevel,
                data.get("effectiveLevel"),
                NotificationLevel.UNSPECIFIED,
            ),  # type: ignore[arg-type]
        )


@dataclass
class Asset:
    id: str
    filename: str
    content_type: str
    size: int
    width: int = 0
    height: int = 0
    asset_url: AssetUrl | None = None
    thumbnail_asset_url: AssetUrl | None = None
    video_processing: VideoProcessing | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> Asset | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            filename=data.get("filename", ""),
            content_type=data.get("contentType", ""),
            size=int(data.get("size", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            asset_url=AssetUrl.parse(data.get("assetUrl")),
            thumbnail_asset_url=AssetUrl.parse(data.get("thumbnailAssetUrl")),
            video_processing=VideoProcessing.parse(data.get("videoProcessing")),
        )


@dataclass
class ImageTransformOptions:
    width: int
    height: int
    fit: ImageFitMode = ImageFitMode.UNSPECIFIED

    def to_wire(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "fit": self.fit.value,
        }


@dataclass
class ActiveCallParticipant:
    user: User | None = None
    joined_at: datetime | None = None
    call_id: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ActiveCallParticipant:
        return cls(
            user=User.parse(data.get("user")),
            joined_at=parse_datetime(data.get("joinedAt")),
            call_id=data.get("callId", ""),
        )


@dataclass
class ActiveCall:
    call_id: str
    room: RoomSummary | None
    participants: list[ActiveCallParticipant] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ActiveCall:
        return cls(
            call_id=data.get("callId", ""),
            room=RoomSummary.parse(data.get("room")),
            participants=[ActiveCallParticipant.parse(p) for p in data.get("participants") or []],
        )


# --- Roles ----------------------------------------------------------------


@dataclass
class Role:
    name: str
    display_name: str = ""
    description: str = ""
    is_system: bool = False
    position: int = 0
    pingable: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> Role | None:
        if not data:
            return None
        return cls(
            name=data.get("name", ""),
            display_name=data.get("displayName", ""),
            description=data.get("description", ""),
            is_system=bool(data.get("isSystem", False)),
            position=int(data.get("position", 0)),
            pingable=bool(data.get("pingable", False)),
        )


@dataclass
class AdminRole:
    role: Role | None
    permissions: list[str] = field(default_factory=list)
    permission_denials: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> AdminRole | None:
        if not data:
            return None
        return cls(
            role=Role.parse(data.get("role")),
            permissions=list(data.get("permissions") or []),
            permission_denials=list(data.get("permissionDenials") or []),
        )


# --- Asset uploads --------------------------------------------------------


@dataclass
class AssetUpload:
    upload_id: str
    room_id: str
    status: AssetUploadStatus = AssetUploadStatus.UNSPECIFIED
    committed_offset: int = 0
    size: int = 0
    max_chunk_size: int = 0
    sha256: str = ""
    expires_at: datetime | None = None
    asset_id: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> AssetUpload | None:
        if not data:
            return None
        return cls(
            upload_id=data.get("uploadId", ""),
            room_id=data.get("roomId", ""),
            status=_parse_enum(
                AssetUploadStatus,
                data.get("status"),
                AssetUploadStatus.UNSPECIFIED,
            ),  # type: ignore[arg-type]
            committed_offset=int(data.get("committedOffset", 0)),
            size=int(data.get("size", 0)),
            max_chunk_size=int(data.get("maxChunkSize", 0)),
            sha256=data.get("sha256", ""),
            expires_at=parse_datetime(data.get("expiresAt")),
            asset_id=data.get("assetId", ""),
        )


# --- External identity ----------------------------------------------------


@dataclass
class ExternalIdentityProvider:
    provider: ProviderMetadata | None
    link_url: str = ""
    linked: bool = False
    linked_identity_subject_hash: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ExternalIdentityProvider:
        provider_data = data.get("provider")
        provider = ProviderMetadata.parse(provider_data) if provider_data else None
        return cls(
            provider=provider,
            link_url=data.get("linkUrl", ""),
            linked=bool(data.get("linked", False)),
            linked_identity_subject_hash=data.get("linkedIdentitySubjectHash", ""),
        )


@dataclass
class LinkedExternalIdentity:
    provider_id: str
    provider_type: str = ""
    provider_label: str = ""
    subject_hash: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> LinkedExternalIdentity:
        return cls(
            provider_id=data.get("providerId", ""),
            provider_type=data.get("providerType", ""),
            provider_label=data.get("providerLabel", ""),
            subject_hash=data.get("subjectHash", ""),
        )


# --- Admin: server / members ---------------------------------------------


@dataclass
class ServerConfig:
    server_name: str = ""
    description: str = ""
    motd: str = ""
    welcome_message: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerConfig:
        data = data or {}
        return cls(
            server_name=data.get("serverName", ""),
            description=data.get("description", ""),
            motd=data.get("motd", ""),
            welcome_message=data.get("welcomeMessage", ""),
        )


@dataclass
class AdminMember:
    user: User | None
    roles: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    has_verified_email: bool = False
    verified_emails: list[str] = field(default_factory=list)
    viewer_can_delete_account: bool = False
    last_login_change: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> AdminMember | None:
        if not data:
            return None
        return cls(
            user=User.parse(data.get("user")),
            roles=list(data.get("roles") or []),
            created_at=parse_datetime(data.get("createdAt")),
            has_verified_email=bool(data.get("hasVerifiedEmail", False)),
            verified_emails=list(data.get("verifiedEmails") or []),
            viewer_can_delete_account=bool(data.get("viewerCanDeleteAccount", False)),
            last_login_change=parse_datetime(data.get("lastLoginChange")),
        )


# --- Admin: room layout --------------------------------------------------


@dataclass
class AdminRoomLayoutGroup:
    id: str
    name: str
    description: str = ""
    rooms: list[Room] = field(default_factory=list)
    sidebar_links: list[SidebarLink] = field(default_factory=list)
    can_create_room: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> AdminRoomLayoutGroup | None:
        if not data:
            return None
        rooms: list[Room] = []
        links: list[SidebarLink] = []
        for item in data.get("items") or []:
            room = Room.parse(item.get("room"))
            if room is not None:
                rooms.append(room)
            sl = item.get("sidebarLink")
            if sl:
                links.append(
                    SidebarLink(
                        id=sl.get("id", ""),
                        label=sl.get("label", ""),
                        url=sl.get("url", ""),
                    )
                )
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            rooms=rooms,
            sidebar_links=links,
            can_create_room=bool(data.get("canCreateRoom", False)),
        )

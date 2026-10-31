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


def coerce_presence(value: Any) -> PresenceStatus:
    """Coerce any wire shape of a presence status to a :class:`PresenceStatus`.

    The realtime channel delivers ``PresenceChangedEvent.status`` as a plain
    ``int`` (the protobuf runtime has no native enum wrappers), a protobuf
    enum wrapper carries the full name via its own ``.name``, and parsed
    payloads already hold a :class:`PresenceStatus`. All three arrive at this
    one function:

    - ``1`` / proto wrapper ``ONLINE`` → ``PresenceStatus.ONLINE``
    - ``PresenceStatus.ONLINE`` → ``PresenceStatus.ONLINE`` (unchanged)
    - anything unrecognised (out-of-range int, ``None``) → ``UNSPECIFIED``

    Note that a :class:`PresenceStatus` member's own ``.name`` is the *short*
    form (``"ONLINE"``), which does NOT match the proto value
    (``"PRESENCE_STATUS_ONLINE"``) — that mismatch is why an isinstance check
    must run before any ``.name`` read.
    """
    if isinstance(value, PresenceStatus):
        return value
    if value is None:
        return PresenceStatus.UNSPECIFIED
    if isinstance(value, int) and not isinstance(value, bool):
        from chattolib._pb.chatto.api.v1 import presence_pb2

        try:
            name = presence_pb2.PresenceStatus.Name(value)
        except ValueError:
            return PresenceStatus.UNSPECIFIED
        return PresenceStatus(name)
    # A protobuf enum wrapper exposes the full name via ``.name``; the
    # isinstance check above already routed StrEnum members elsewhere.
    name = getattr(value, "name", None)
    if isinstance(name, str):
        try:
            return PresenceStatus(name)
        except ValueError:
            return PresenceStatus.UNSPECIFIED
    return PresenceStatus.UNSPECIFIED


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


class RoomInvitationStatus(StrEnum):
    UNSPECIFIED = "ROOM_INVITATION_STATUS_UNSPECIFIED"
    PENDING = "ROOM_INVITATION_STATUS_PENDING"
    ACCEPTED = "ROOM_INVITATION_STATUS_ACCEPTED"
    DECLINED = "ROOM_INVITATION_STATUS_DECLINED"
    EXPIRED = "ROOM_INVITATION_STATUS_EXPIRED"


class NotificationLevel(StrEnum):
    UNSPECIFIED = "NOTIFICATION_LEVEL_UNSPECIFIED"
    DEFAULT = "NOTIFICATION_LEVEL_DEFAULT"
    MUTED = "NOTIFICATION_LEVEL_MUTED"
    NORMAL = "NOTIFICATION_LEVEL_NORMAL"
    ALL_MESSAGES = "NOTIFICATION_LEVEL_ALL_MESSAGES"


class ThreadRootAuthorFilter(StrEnum):
    UNSPECIFIED = "THREAD_ROOT_AUTHOR_FILTER_UNSPECIFIED"
    VIEWER = "THREAD_ROOT_AUTHOR_FILTER_VIEWER"
    OTHERS = "THREAD_ROOT_AUTHOR_FILTER_OTHERS"


class ThreadOrder(StrEnum):
    UNSPECIFIED = "THREAD_ORDER_UNSPECIFIED"
    ACTIVITY = "THREAD_ORDER_ACTIVITY"
    CREATED = "THREAD_ORDER_CREATED"


class MessageSearchOrder(StrEnum):
    UNSPECIFIED = "MESSAGE_SEARCH_ORDER_UNSPECIFIED"
    RELEVANCE = "MESSAGE_SEARCH_ORDER_RELEVANCE"
    NEWEST = "MESSAGE_SEARCH_ORDER_NEWEST"
    THREAD_ACTIVITY = "MESSAGE_SEARCH_ORDER_THREAD_ACTIVITY"
    THREAD_CREATED = "MESSAGE_SEARCH_ORDER_THREAD_CREATED"


class MessageSearchScope(StrEnum):
    UNSPECIFIED = "MESSAGE_SEARCH_SCOPE_UNSPECIFIED"
    FOLLOWED_THREADS = "MESSAGE_SEARCH_SCOPE_FOLLOWED_THREADS"


class MessageSearchGroupBy(StrEnum):
    UNSPECIFIED = "MESSAGE_SEARCH_GROUP_BY_UNSPECIFIED"
    THREAD = "MESSAGE_SEARCH_GROUP_BY_THREAD"


class MessageSearchState(StrEnum):
    UNSPECIFIED = "MESSAGE_SEARCH_STATE_UNSPECIFIED"
    DISABLED = "MESSAGE_SEARCH_STATE_DISABLED"
    STARTING = "MESSAGE_SEARCH_STATE_STARTING"
    INDEXING = "MESSAGE_SEARCH_STATE_INDEXING"
    READY = "MESSAGE_SEARCH_STATE_READY"
    DEGRADED = "MESSAGE_SEARCH_STATE_DEGRADED"
    UNAVAILABLE = "MESSAGE_SEARCH_STATE_UNAVAILABLE"


class InvitationCodeStatus(StrEnum):
    UNSPECIFIED = "INVITATION_CODE_STATUS_UNSPECIFIED"
    ACTIVE = "INVITATION_CODE_STATUS_ACTIVE"
    EXPIRED = "INVITATION_CODE_STATUS_EXPIRED"
    USED = "INVITATION_CODE_STATUS_USED"
    REVOKED = "INVITATION_CODE_STATUS_REVOKED"


class AccountCreationPolicy(StrEnum):
    UNSPECIFIED = "ACCOUNT_CREATION_POLICY_UNSPECIFIED"
    OPEN = "ACCOUNT_CREATION_POLICY_OPEN"
    INVITE_ONLY = "ACCOUNT_CREATION_POLICY_INVITE_ONLY"


class DisconnectEligibility(StrEnum):
    UNSPECIFIED = "DISCONNECT_ELIGIBILITY_UNSPECIFIED"
    ALLOWED = "DISCONNECT_ELIGIBILITY_ALLOWED"
    LAST_ENABLED_SIGN_IN_METHOD = "DISCONNECT_ELIGIBILITY_LAST_ENABLED_SIGN_IN_METHOD"
    DISABLED_BY_OPERATOR = "DISCONNECT_ELIGIBILITY_DISABLED_BY_OPERATOR"


class UsernameChoiceAvailability(StrEnum):
    UNSPECIFIED = "USERNAME_CHOICE_AVAILABILITY_UNSPECIFIED"
    ALLOWED = "USERNAME_CHOICE_AVAILABILITY_ALLOWED"
    PROVIDER_MANAGED = "USERNAME_CHOICE_AVAILABILITY_PROVIDER_MANAGED"


class UsernameChangeState(StrEnum):
    UNSPECIFIED = "STATE_UNSPECIFIED"
    ALLOWED = "STATE_ALLOWED"
    PROVIDER_MANAGED = "STATE_PROVIDER_MANAGED"


class PasswordChangeAvailability(StrEnum):
    UNSPECIFIED = "PASSWORD_CHANGE_AVAILABILITY_UNSPECIFIED"
    ALLOWED = "PASSWORD_CHANGE_AVAILABILITY_ALLOWED"
    DIRECT_LOGIN_DISABLED = "PASSWORD_CHANGE_AVAILABILITY_DIRECT_LOGIN_DISABLED"
    UNSUPPORTED_ACCOUNT = "PASSWORD_CHANGE_AVAILABILITY_UNSUPPORTED_ACCOUNT"


class AccountDeletionAvailability(StrEnum):
    UNSPECIFIED = "ACCOUNT_DELETION_AVAILABILITY_UNSPECIFIED"
    ALLOWED = "ACCOUNT_DELETION_AVAILABILITY_ALLOWED"
    PERMISSION_DENIED = "ACCOUNT_DELETION_AVAILABILITY_PERMISSION_DENIED"
    UNSUPPORTED_ACCOUNT = "ACCOUNT_DELETION_AVAILABILITY_UNSUPPORTED_ACCOUNT"


class OauthClientSource(StrEnum):
    UNSPECIFIED = "OAUTH_CLIENT_SOURCE_UNSPECIFIED"
    CIMD = "OAUTH_CLIENT_SOURCE_CIMD"
    BUILT_IN = "OAUTH_CLIENT_SOURCE_BUILT_IN"


class OauthClientPolicy(StrEnum):
    UNSPECIFIED = "OAUTH_CLIENT_POLICY_UNSPECIFIED"
    DEFAULT = "OAUTH_CLIENT_POLICY_DEFAULT"
    TRUSTED = "OAUTH_CLIENT_POLICY_TRUSTED"
    BLOCKED = "OAUTH_CLIENT_POLICY_BLOCKED"


class PermissionDecision(StrEnum):
    UNSPECIFIED = "PERMISSION_DECISION_UNSPECIFIED"
    ALLOW = "PERMISSION_DECISION_ALLOW"
    DENY = "PERMISSION_DECISION_DENY"
    NONE = "PERMISSION_DECISION_NONE"


class PermissionScopeKind(StrEnum):
    UNSPECIFIED = "PERMISSION_SCOPE_KIND_UNSPECIFIED"
    SERVER = "PERMISSION_SCOPE_KIND_SERVER"
    GROUP = "PERMISSION_SCOPE_KIND_GROUP"
    ROOM = "PERMISSION_SCOPE_KIND_ROOM"
    DM = "PERMISSION_SCOPE_KIND_DM"


class CallMediaPublisherKind(StrEnum):
    UNSPECIFIED = "CALL_MEDIA_PUBLISHER_KIND_UNSPECIFIED"
    GAME_SHARE = "CALL_MEDIA_PUBLISHER_KIND_GAME_SHARE"


class ExternalIdentityFlowKind(StrEnum):
    UNSPECIFIED = "EXTERNAL_IDENTITY_FLOW_KIND_UNSPECIFIED"
    CREATE_ACCOUNT = "EXTERNAL_IDENTITY_FLOW_KIND_CREATE_ACCOUNT"
    LINK_ACCOUNT = "EXTERNAL_IDENTITY_FLOW_KIND_LINK_ACCOUNT"


class CredentialLastUsedState(StrEnum):
    UNSPECIFIED = "CREDENTIAL_LAST_USED_STATE_UNSPECIFIED"
    NO_USE_RECORDED = "CREDENTIAL_LAST_USED_STATE_NO_USE_RECORDED"
    RECORDED = "CREDENTIAL_LAST_USED_STATE_RECORDED"
    UNAVAILABLE = "CREDENTIAL_LAST_USED_STATE_UNAVAILABLE"


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
class BotInfo:
    """Metadata identifying a bot account and the human that owns it.

    Present on a :class:`User` only when the identity is a bot; its presence
    (rather than a boolean flag) is what marks a bot in Chatto 0.5.0.
    """

    owner_user_id: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> BotInfo | None:
        if not data:
            return None
        return cls(owner_user_id=data.get("ownerUserId", ""))


@dataclass
class User:
    id: str
    login: str
    display_name: str
    presence_status: PresenceStatus = PresenceStatus.UNSPECIFIED
    avatar_url: str | None = None
    deleted: bool = False
    custom_status: CustomUserStatus | None = None
    bot: BotInfo | None = None
    bio: str | None = None
    timezone: str | None = None
    # Since 0.5.0b27: True while the account is deactivated (cannot sign in or
    # use the server); its data is retained and access can be restored.
    deactivated: bool = False

    @property
    def is_bot(self) -> bool:
        """True when this identity is a bot (i.e. ``bot`` is present)."""
        return self.bot is not None

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
            bot=BotInfo.parse(data.get("bot")),
            bio=data.get("bio"),
            timezone=data.get("timezone"),
            deactivated=bool(data.get("deactivated", False)),
        )


@dataclass
class PresencePreference:
    """The authenticated account's private, saved availability choice.

    This is distinct from :class:`PresenceStatus` as a *live* report: the
    preference survives disconnects and applies across every device on the
    server. ``revision`` is an opaque token that must be echoed back (as
    ``expected_revision``) when replacing the choice; a stale one yields
    ``ABORTED``.
    """

    status: PresenceStatus = PresenceStatus.UNSPECIFIED
    revision: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> PresencePreference | None:
        if not data:
            return None
        return cls(
            status=_parse_enum(PresenceStatus, data.get("status"), PresenceStatus.UNSPECIFIED),  # type: ignore[arg-type]
            revision=data.get("revision", ""),
        )


@dataclass
class UserSettings:
    timezone: str | None = None
    time_format: TimeFormat = TimeFormat.UNSPECIFIED
    share_timezone: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> UserSettings:
        data = data or {}
        return cls(
            timezone=data.get("timezone"),
            time_format=_parse_enum(TimeFormat, data.get("timeFormat"), TimeFormat.UNSPECIFIED),  # type: ignore[arg-type]
            share_timezone=bool(data.get("shareTimezone", False)),
        )


@dataclass
class ViewerUser:
    profile: User | None
    settings: UserSettings
    has_verified_email: bool = False
    viewer_can_delete_account: bool = False
    last_login_change: datetime | None = None
    has_password: bool = False
    # Since 0.5.0b27: self-service account action snapshots (absent on older
    # servers; ``viewer_can_delete_account`` above is deprecated in favor of
    # ``actions.delete_account``).
    actions: AccountActions | None = None

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
            actions=AccountActions.parse(data.get("actions")),
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
class NeighborhoodServer:
    """One server in the Neighborhood discovered by the called server.

    ``profile`` is the public profile the called server loaded (no welcome
    message); its ``logoUrl``/``bannerUrl`` are server-relative paths of
    copies on the called server — resolve them against that server's origin.
    """

    origin: str
    profile: ServerProfile | None = None
    direct_neighbor: bool = False
    recommended_by_origins: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NeighborhoodServer | None:
        if not data:
            return None
        return cls(
            origin=data.get("origin", ""),
            profile=ServerProfile.parse(data.get("profile")),
            direct_neighbor=bool(data.get("directNeighbor", False)),
            recommended_by_origins=list(data.get("recommendedByOrigins") or []),
        )


@dataclass
class NeighborhoodServersPage:
    """The Neighborhood of the called server, as it last discovered it.

    The called server lists each Neighbor whose public profile loaded, plus
    servers that a mutually advertising Neighbor recommends when the
    recommendation is also mutual. No ordering contract. ``refreshed_at`` is
    absent before the server's first completed discovery.
    """

    servers: list[NeighborhoodServer] = field(default_factory=list)
    refreshed_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NeighborhoodServersPage:
        data = data or {}
        return cls(
            servers=[
                s
                for s in (NeighborhoodServer.parse(s) for s in data.get("servers") or [])
                if s is not None
            ],
            refreshed_at=parse_datetime(data.get("refreshedAt")),
        )


@dataclass
class ServerLogin:
    direct_registration_enabled: bool = False
    providers: list[ProviderMetadata] = field(default_factory=list)
    authorize_url: str = ""
    # Since 0.5.0b26: admission policy for direct registration and provider
    # auto-provisioning (UNSPECIFIED on older servers means treat as open).
    account_creation_policy: AccountCreationPolicy = AccountCreationPolicy.UNSPECIFIED

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerLogin:
        data = data or {}
        return cls(
            direct_registration_enabled=bool(data.get("directRegistrationEnabled", False)),
            providers=[ProviderMetadata.parse(p) for p in data.get("providers") or []],
            authorize_url=data.get("authorizeUrl", ""),
            account_creation_policy=_parse_enum(  # type: ignore[arg-type]
                AccountCreationPolicy,
                data.get("accountCreationPolicy"),
                AccountCreationPolicy.UNSPECIFIED,
            ),
        )


@dataclass
class Neighbor:
    """One server advertised in the public Neighbor directory.

    ``origin`` is the canonical HTTP(S) origin; ``revision`` is an opaque
    token required to update or delete the entry (admin side).
    """

    id: str
    origin: str
    revision: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> Neighbor | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            origin=data.get("origin", ""),
            revision=data.get("revision", ""),
        )


@dataclass
class ServerRuntimeConfig:
    push_notifications_enabled: bool = False
    vapid_public_key: str | None = None
    livekit_url: str | None = None
    video_processing_enabled: bool = False
    max_upload_size: int = 0
    # Deprecated since 0.5.0b16: an alias of ``max_upload_size`` (same value).
    # Since 0.5.0b16 one size limit applies to all attachments, GIFs/videos included.
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
    thread_slow_mode_seconds: int | None = None
    # Since 0.5.0b27: when the room was created (absent on older servers),
    # and whether clients show join/leave activity (absent on older servers
    # means True; membership state and event delivery are unaffected either
    # way).
    created_at: datetime | None = None
    show_membership_events: bool | None = None

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
            thread_slow_mode_seconds=(
                int(data["threadSlowModeSeconds"])
                if data.get("threadSlowModeSeconds") is not None
                else None
            ),
            created_at=parse_datetime(data.get("createdAt")),
            show_membership_events=(
                data["showMembershipEvents"] if "showMembershipEvents" in data else None
            ),
        )


@dataclass
class RoomNotice:
    """The current member-only notice in a channel room (since 0.5.0b27).

    ``version`` is an opaque concurrency token that every mutation must send
    back (empty before the first publish). ``publication_id`` is an opaque
    dismissal revision: corrections preserve it, publish/republish replace it,
    and it is empty when nothing is published. ``published_at`` is absent when
    the notice is cleared or unavailable on an older server.
    """

    body: str = ""
    version: str = ""
    publication_id: str = ""
    published_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomNotice:
        data = data or {}
        return cls(
            body=data.get("body", ""),
            version=data.get("version", ""),
            publication_id=data.get("publicationId", ""),
            published_at=parse_datetime(data.get("publishedAt")),
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
class RoomInvitation:
    """An invitation to join a room (since 0.5.0b20), visible only to its
    sender and recipient. Membership is granted only after the recipient
    accepts; expiry does not extend when the invitation is read."""

    id: str
    room_id: str = ""
    sender_id: str = ""
    recipient_id: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    status: RoomInvitationStatus = RoomInvitationStatus.UNSPECIFIED
    can_accept: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomInvitation | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            room_id=data.get("roomId", ""),
            sender_id=data.get("senderId", ""),
            recipient_id=data.get("recipientId", ""),
            created_at=parse_datetime(data.get("createdAt")),
            expires_at=parse_datetime(data.get("expiresAt")),
            status=_parse_enum(
                RoomInvitationStatus, data.get("status"), RoomInvitationStatus.UNSPECIFIED
            ),  # type: ignore[arg-type]
            can_accept=bool(data.get("canAccept", False)),
        )


@dataclass
class RoomViewerState:
    is_member: bool = False
    has_unread: bool = False
    # Since 0.5.0b20: the viewer's pending invitation for this room (does not
    # grant access to room content), and whether current permissions/room state
    # allow joining without an invitation (absent on servers that do not
    # report this decision).
    invitation: RoomInvitation | None = None
    can_rejoin: bool | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomViewerState:
        data = data or {}
        return cls(
            is_member=bool(data.get("isMember", False)),
            has_unread=bool(data.get("hasUnread", False)),
            invitation=RoomInvitation.parse(data.get("invitation")),
            can_rejoin=data.get("canRejoin") if "canRejoin" in data else None,
        )


@dataclass
class RoomWithViewerState:
    room: Room | None
    viewer_state: RoomViewerState
    member_user_ids: list[str] = field(default_factory=list)
    has_message_history: bool | None = None
    last_message_at: datetime | None = None
    last_root_message_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomWithViewerState | None:
        if not data:
            return None
        return cls(
            room=Room.parse(data.get("room")),
            viewer_state=RoomViewerState.parse(data.get("viewerState")),
            member_user_ids=list(data.get("memberUserIds") or []),
            has_message_history=(
                data.get("hasMessageHistory") if "hasMessageHistory" in data else None
            ),
            last_message_at=parse_datetime(data.get("lastMessageAt")),
            last_root_message_at=parse_datetime(data.get("lastRootMessageAt")),
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
class RoomSuspension:
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
    def parse(cls, data: dict[str, Any] | None) -> RoomSuspension | None:
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
    description: str | None = None

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
            description=data.get("description"),
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
    has_unread_replies: bool | None = None
    slow_mode_next_post_at: datetime | None = None

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
            has_unread_replies=(
                viewer.get("hasUnreadReplies") if "hasUnreadReplies" in viewer else None
            ),
            slow_mode_next_post_at=parse_datetime(viewer.get("slowModeNextPostAt")),
        )


@dataclass
class MessageViewerState:
    """Viewer-specific capability for one message, independent of whether its
    canonical thread has been established. ``can_reply_in_thread`` reflects
    read access, room policy, and broad or interaction-scoped posting
    authority; it is ``None`` when the server has not resolved viewer state."""

    can_reply_in_thread: bool | None = None
    thread_slow_mode_next_post_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> MessageViewerState:
        data = data or {}
        return cls(
            can_reply_in_thread=(
                data.get("canReplyInThread") if "canReplyInThread" in data else None
            ),
            thread_slow_mode_next_post_at=parse_datetime(data.get("threadSlowModeNextPostAt")),
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
    viewer_state: MessageViewerState | None = None

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
            viewer_state=MessageViewerState.parse(data.get("viewerState")),
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
    """snake_case a camelCase oneof field name (acronym-aware).

    Mirrors the chattolib protoc plugin's ``_method_name``: an underscore
    goes before an uppercase letter only at a word boundary — after a
    lowercase/digit, or before the final capital of a run that is followed
    by a lowercase letter. A naive per-capital split would turn a future
    acronym field like ``startDMReceived`` into ``start_d_m_received`` and
    silently break any ``kind == "..."`` comparison.
    """
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and out:
            prev = name[i - 1]
            nxt = name[i + 1] if i + 1 < len(name) else ""
            if not prev.isupper() or nxt.islower():
                out.append("_")
        out.append(ch.lower())
    return "".join(out)


@dataclass
class ThreadViewerState:
    """Viewer-specific follow / unread / slow-mode state for one thread, as
    returned by ``GetThreadEvents``/``GetThreadEventsAround`` (since
    0.5.0b18). ``slow_mode_next_post_at`` is the earliest time the viewer may
    reply in the thread (the root message starts its author's thread
    cooldown); it is ``None`` when thread slow mode is disabled, expired, or
    bypassed."""

    is_following: bool | None = None
    has_unread_replies: bool | None = None
    slow_mode_next_post_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ThreadViewerState | None:
        if not data:
            return None
        return cls(
            is_following=data.get("isFollowing") if "isFollowing" in data else None,
            has_unread_replies=data.get("hasUnreadReplies") if "hasUnreadReplies" in data else None,
            slow_mode_next_post_at=parse_datetime(data.get("slowModeNextPostAt")),
        )


@dataclass
class TimelinePage:
    events: list[TimelineEvent] = field(default_factory=list)
    start_cursor: str = ""
    end_cursor: str = ""
    has_older: bool = False
    has_newer: bool = False
    users_by_id: dict[str, User] = field(default_factory=dict)
    # Thread viewer state, populated only on thread-timeline pages
    # (GetThreadEvents / GetThreadEventsAround, since 0.5.0b18).
    thread_viewer_state: ThreadViewerState | None = None

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
    latest_reply: Message | None = None
    direct_message_participant_user_ids: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> FollowedThread:
        return cls(
            room=RoomSummary.parse(data.get("room")),
            root_message=Message.parse(data.get("rootMessage")),
            thread=ThreadSummary.parse(data.get("thread")),
            latest_reply=Message.parse(data.get("latestReply")),
            direct_message_participant_user_ids=list(
                data.get("directMessageParticipantUserIds") or []
            ),
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
    ``room_message_received``, ``room_invitation_received``). ``message`` is
    the referenced :class:`NotificationMessageReference`; for
    ``room_invitation_received`` (since 0.5.0b20) the destination is the room
    instead — ``room`` carries the :class:`RoomSummary` and ``invitation_id``
    the stable invitation identifier.
    """

    kind: str
    message: NotificationMessageReference | None
    role_names: list[str] = field(default_factory=list)
    emoji: str = ""
    room: RoomSummary | None = None
    invitation_id: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> NotificationSignal | None:
        if not data:
            return None
        kind = ""
        message: NotificationMessageReference | None = None
        room: RoomSummary | None = None
        invitation_id = ""
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
            "roomInvitationReceived",
        ):
            payload = data.get(candidate)
            if payload is None:
                continue
            kind = _snake_case(candidate)
            if candidate == "roomInvitationReceived":
                room = RoomSummary.parse(payload.get("room"))
                invitation_id = payload.get("invitationId", "")
            else:
                message = NotificationMessageReference.parse(payload.get("message"))
            break
        return cls(
            kind=kind,
            message=message,
            role_names=list(data.get("roleNames") or []),
            emoji=data.get("emoji", ""),
            room=room,
            invitation_id=invitation_id,
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
    # Since 0.5.0b27: disconnect eligibility evaluated by
    # ListExternalIdentities. Only ALLOWED enables the action; UNSPECIFIED
    # means not evaluated (older servers) — unknown future states remain
    # disabled client-side.
    disconnect_eligibility: DisconnectEligibility = DisconnectEligibility.UNSPECIFIED

    @classmethod
    def parse(cls, data: dict[str, Any]) -> LinkedExternalIdentity:
        return cls(
            provider_id=data.get("providerId", ""),
            provider_type=data.get("providerType", ""),
            provider_label=data.get("providerLabel", ""),
            subject_hash=data.get("subjectHash", ""),
            disconnect_eligibility=_parse_enum(  # type: ignore[arg-type]
                DisconnectEligibility,
                data.get("disconnectEligibility"),
                DisconnectEligibility.UNSPECIFIED,
            ),
        )


# --- Admin: server / members ---------------------------------------------


@dataclass
class RegistrationSettings:
    """Account-creation admission settings (since 0.5.0b27). OPEN permits
    signup without an invitation; INVITE_ONLY requires a valid single-use
    registration code (see ``admin_create_invitation_code``)."""

    admission: AccountCreationPolicy = AccountCreationPolicy.UNSPECIFIED

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RegistrationSettings:
        data = data or {}
        return cls(
            admission=_parse_enum(  # type: ignore[arg-type]
                AccountCreationPolicy, data.get("admission"), AccountCreationPolicy.UNSPECIFIED
            ),
        )


@dataclass
class ServerConfig:
    server_name: str = ""
    description: str = ""
    motd: str = ""
    welcome_message: str = ""
    # Since 0.5.0b27: settings for new self-service accounts.
    registration: RegistrationSettings = field(default_factory=RegistrationSettings)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerConfig:
        data = data or {}
        return cls(
            server_name=data.get("serverName", ""),
            description=data.get("description", ""),
            motd=data.get("motd", ""),
            welcome_message=data.get("welcomeMessage", ""),
            registration=RegistrationSettings.parse(data.get("registration")),
        )


@dataclass
class UsernameChangeAvailability:
    """Self-service username-change decision (since 0.5.0b27). ``state``
    (the nested ``UsernameChangeAvailability.State`` enum) gates the action;
    ``available_at`` is an independent earliest attempt time — when absent
    there is no time restriction. Commands still recheck policy."""

    state: UsernameChangeState = UsernameChangeState.UNSPECIFIED
    available_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> UsernameChangeAvailability | None:
        if not data:
            return None
        return cls(
            state=_parse_enum(  # type: ignore[arg-type]
                UsernameChangeState, data.get("state"), UsernameChangeState.UNSPECIFIED
            ),
            available_at=parse_datetime(data.get("availableAt")),
        )


@dataclass
class AccountActions:
    """Self-service account action snapshots carried by the viewer since
    0.5.0b27. Absent sub-fields mean the server did not report that action;
    only ALLOWED enables it client-side — the mutation RPCs always recheck."""

    change_username: UsernameChangeAvailability | None = None
    change_password: PasswordChangeAvailability | None = None
    delete_account: AccountDeletionAvailability | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> AccountActions | None:
        if not data:
            return None
        return cls(
            change_username=UsernameChangeAvailability.parse(data.get("changeUsername")),
            change_password=(
                _parse_enum(  # type: ignore[arg-type]
                    PasswordChangeAvailability,
                    data["changePassword"],
                    PasswordChangeAvailability.UNSPECIFIED,
                )
                if data.get("changePassword") is not None
                else None
            ),
            delete_account=(
                _parse_enum(  # type: ignore[arg-type]
                    AccountDeletionAvailability,
                    data["deleteAccount"],
                    AccountDeletionAvailability.UNSPECIFIED,
                )
                if data.get("deleteAccount") is not None
                else None
            ),
        )


@dataclass
class ServerFeature:
    """An advisory product feature reported by the public feature catalog
    (``ServerDiscoveryService.ListFeatures``, since 0.5.0b27). ``id`` is a
    stable feature identifier — clients must accept unknown IDs. This is
    upgrade guidance, not permission, configuration, or API negotiation."""

    id: str = ""
    name: str = ""
    description: str = ""
    introduced_version: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ServerFeature | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            introduced_version=data.get("introducedVersion", ""),
        )


@dataclass
class AdminMember:
    user: User | None
    roles: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    has_verified_email: bool = False
    verified_emails: list[str] = field(default_factory=list)
    primary_verified_email: str | None = None
    viewer_can_delete_account: bool = False
    last_login_change: datetime | None = None
    # Since 0.5.0b27: deactivated accounts retain their data but cannot use
    # the server; ``viewer_can_change_deactivation`` is absent on servers that
    # do not support account deactivation.
    deactivated: bool = False
    viewer_can_change_deactivation: bool | None = None

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
            primary_verified_email=data.get("primaryVerifiedEmail"),
            viewer_can_delete_account=bool(data.get("viewerCanDeleteAccount", False)),
            last_login_change=parse_datetime(data.get("lastLoginChange")),
            deactivated=bool(data.get("deactivated", False)),
            viewer_can_change_deactivation=(
                data["viewerCanChangeDeactivation"]
                if "viewerCanChangeDeactivation" in data
                else None
            ),
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


# --- Message search --------------------------------------------------------


@dataclass
class SearchStatus:
    state: MessageSearchState = MessageSearchState.UNSPECIFIED
    retry_after_seconds: int | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> SearchStatus:
        data = data or {}
        retry = data.get("retryAfter")
        retry_seconds: int | None = None
        if retry is not None:
            try:
                retry_seconds = int(str(retry).rstrip("s"))
            except ValueError:
                retry_seconds = None
        return cls(
            state=_parse_enum(
                MessageSearchState, data.get("state"), MessageSearchState.UNSPECIFIED
            ),  # type: ignore[arg-type]
            retry_after_seconds=retry_seconds,
        )


@dataclass
class ThreadSearchContext:
    root_message: Message | None = None
    room: RoomSummary | None = None
    thread: ThreadSummary | None = None
    latest_reply: Message | None = None
    direct_message_participant_user_ids: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ThreadSearchContext | None:
        if not data:
            return None
        return cls(
            root_message=Message.parse(data.get("rootMessage")),
            room=RoomSummary.parse(data.get("room")),
            thread=ThreadSummary.parse(data.get("thread")),
            latest_reply=Message.parse(data.get("latestReply")),
            direct_message_participant_user_ids=list(
                data.get("directMessageParticipantUserIds") or []
            ),
        )


@dataclass
class MessageSearchResult:
    message: Message | None = None
    relevance_score: float = 0.0
    thread_context: ThreadSearchContext | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> MessageSearchResult:
        return cls(
            message=Message.parse(data.get("message")),
            relevance_score=float(data.get("relevanceScore", 0.0)),
            thread_context=ThreadSearchContext.parse(data.get("threadContext")),
        )


@dataclass
class SearchResultsPage:
    results: list[MessageSearchResult] = field(default_factory=list)
    next_cursor: str = ""
    thread_total_count: int | None = None
    users_by_id: dict[str, User] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> SearchResultsPage:
        data = data or {}
        users: dict[str, User] = {}
        includes = data.get("includes") or {}
        for uid, user_data in (includes.get("users") or {}).items():
            parsed = User.parse(user_data)
            if parsed is not None:
                users[uid] = parsed
        return cls(
            results=[MessageSearchResult.parse(r) for r in data.get("results") or []],
            next_cursor=data.get("nextCursor", ""),
            thread_total_count=(
                int(data["threadTotalCount"]) if "threadTotalCount" in data else None
            ),
            users_by_id=users,
        )


# --- Read state ------------------------------------------------------------


@dataclass
class ReadMarker:
    last_read_event_id: str = ""
    last_read_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ReadMarker | None:
        if not data:
            return None
        return cls(
            last_read_event_id=data.get("lastReadEventId", ""),
            last_read_at=parse_datetime(data.get("lastReadAt")),
        )


@dataclass
class RoomReadState:
    room_id: str = ""
    marker: ReadMarker | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> RoomReadState | None:
        if not data:
            return None
        return cls(
            room_id=data.get("roomId", ""),
            marker=ReadMarker.parse(data.get("marker")),
        )


@dataclass
class ThreadReadState:
    room_id: str = ""
    thread_root_event_id: str = ""
    marker: ReadMarker | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> ThreadReadState | None:
        if not data:
            return None
        return cls(
            room_id=data.get("roomId", ""),
            thread_root_event_id=data.get("threadRootEventId", ""),
            marker=ReadMarker.parse(data.get("marker")),
        )


# --- Account: emails, external identities, privileged mode ----------------


@dataclass
class VerifiedEmail:
    email: str = ""
    verified_at: datetime | None = None
    primary: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any]) -> VerifiedEmail:
        return cls(
            email=data.get("email", ""),
            verified_at=parse_datetime(data.get("verifiedAt")),
            primary=bool(data.get("primary", False)),
        )


@dataclass
class PendingExternalIdentity:
    kind: ExternalIdentityFlowKind = ExternalIdentityFlowKind.UNSPECIFIED
    provider_id: str = ""
    provider_type: str = ""
    provider_label: str = ""
    verified_email: str = ""
    login_hint: str = ""
    display_name_hint: str = ""
    bound_user_id: str = ""
    redirect_path: str = ""
    # Since 0.5.0b27: whether the user can choose a username during creation
    # (None when the server does not report it), and whether a create flow
    # requires an invitation code.
    choose_username: UsernameChoiceAvailability | None = None
    invitation_required: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> PendingExternalIdentity | None:
        if not data:
            return None
        return cls(
            kind=_parse_enum(  # type: ignore[arg-type]
                ExternalIdentityFlowKind, data.get("kind"), ExternalIdentityFlowKind.UNSPECIFIED
            ),
            provider_id=data.get("providerId", ""),
            provider_type=data.get("providerType", ""),
            provider_label=data.get("providerLabel", ""),
            verified_email=data.get("verifiedEmail", ""),
            login_hint=data.get("loginHint", ""),
            display_name_hint=data.get("displayNameHint", ""),
            bound_user_id=data.get("boundUserId", ""),
            redirect_path=data.get("redirectPath", ""),
            choose_username=(
                _parse_enum(  # type: ignore[arg-type]
                    UsernameChoiceAvailability,
                    data["chooseUsername"],
                    UsernameChoiceAvailability.UNSPECIFIED,
                )
                if data.get("chooseUsername") is not None
                else None
            ),
            invitation_required=bool(data.get("invitationRequired", False)),
        )


@dataclass
class PrivilegedModeState:
    available: bool = False
    active: bool = False
    expires_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> PrivilegedModeState | None:
        if not data:
            return None
        return cls(
            available=bool(data.get("available", False)),
            active=bool(data.get("active", False)),
            expires_at=parse_datetime(data.get("expiresAt")),
        )


# --- Bots ------------------------------------------------------------------


@dataclass
class BotApiKey:
    id: str = ""
    name: str = ""
    created_at: datetime | None = None
    last_used_state: CredentialLastUsedState = CredentialLastUsedState.UNSPECIFIED
    last_used_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> BotApiKey:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            created_at=parse_datetime(data.get("createdAt")),
            last_used_state=_parse_enum(  # type: ignore[arg-type]
                CredentialLastUsedState,
                data.get("lastUsedState"),
                CredentialLastUsedState.UNSPECIFIED,
            ),
            last_used_at=parse_datetime(data.get("lastUsedAt")),
        )


@dataclass
class BotIncomingWebhook:
    id: str = ""
    name: str = ""
    created_at: datetime | None = None
    last_used_state: CredentialLastUsedState = CredentialLastUsedState.UNSPECIFIED
    last_used_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> BotIncomingWebhook:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            created_at=parse_datetime(data.get("createdAt")),
            last_used_state=_parse_enum(  # type: ignore[arg-type]
                CredentialLastUsedState,
                data.get("lastUsedState"),
                CredentialLastUsedState.UNSPECIFIED,
            ),
            last_used_at=parse_datetime(data.get("lastUsedAt")),
        )


@dataclass
class BotAccount:
    """A managed bot account (proto ``Bot``).

    Named ``BotAccount`` rather than ``Bot`` to avoid clashing with
    chattolib's ``chattolib.bot.Bot`` framework facade, which is what the
    package exports as ``Bot``.
    """

    user: User | None = None
    owner_user_id: str = ""
    created_at: datetime | None = None
    api_key_created_at: datetime | None = None
    incoming_webhooks: list[BotIncomingWebhook] = field(default_factory=list)
    api_keys: list[BotApiKey] = field(default_factory=list)
    last_login_change: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> BotAccount | None:
        if not data:
            return None
        return cls(
            user=User.parse(data.get("user")),
            owner_user_id=data.get("ownerUserId", ""),
            created_at=parse_datetime(data.get("createdAt")),
            api_key_created_at=parse_datetime(data.get("apiKeyCreatedAt")),
            incoming_webhooks=[
                BotIncomingWebhook.parse(w) for w in data.get("incomingWebhooks") or []
            ],
            api_keys=[BotApiKey.parse(k) for k in data.get("apiKeys") or []],
            last_login_change=parse_datetime(data.get("lastLoginChange")),
        )


@dataclass
class BotWebhookFailure:
    id: str = ""
    reason: str = ""
    attempts: int = 0
    http_status: int = 0
    completed_at: datetime | None = None
    source_event_id: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> BotWebhookFailure:
        return cls(
            id=data.get("id", ""),
            reason=data.get("reason", ""),
            attempts=int(data.get("attempts", 0)),
            http_status=int(data.get("httpStatus", 0)),
            completed_at=parse_datetime(data.get("completedAt")),
            source_event_id=data.get("sourceEventId", ""),
        )


@dataclass
class BotOutboundWebhook:
    id: str = ""
    enabled: bool = False
    has_authorization: bool = False
    latest_failure: BotWebhookFailure | None = None
    url: str = ""
    name: str = ""
    created_at: datetime | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> BotOutboundWebhook:
        return cls(
            id=data.get("id", ""),
            enabled=bool(data.get("enabled", False)),
            has_authorization=bool(data.get("hasAuthorization", False)),
            latest_failure=(
                BotWebhookFailure.parse(data["latestFailure"])
                if data.get("latestFailure")
                else None
            ),
            url=data.get("url", ""),
            name=data.get("name", ""),
            created_at=parse_datetime(data.get("createdAt")),
        )


# --- Admin: invite links, OAuth clients ------------------------------------


@dataclass
class InvitationCode:
    """A single-use registration code on an invite-only server (since 0.5.0b27,
    chatto #3085 replaced invite links). ``code`` is the recoverable bearer
    capability — it is only ever returned to callers with ``user.invite`` and
    must never be logged."""

    id: str = ""
    code: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    status: InvitationCodeStatus = InvitationCodeStatus.UNSPECIFIED
    revoked_at: datetime | None = None
    note: str = ""

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> InvitationCode | None:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            code=data.get("code", ""),
            created_by=data.get("createdBy", ""),
            created_at=parse_datetime(data.get("createdAt")),
            expires_at=parse_datetime(data.get("expiresAt")),
            status=_parse_enum(  # type: ignore[arg-type]
                InvitationCodeStatus, data.get("status"), InvitationCodeStatus.UNSPECIFIED
            ),
            revoked_at=parse_datetime(data.get("revokedAt")),
            note=data.get("note", ""),
        )


@dataclass
class OAuthClient:
    client_id: str = ""
    client_name: str = ""
    client_origin: str = ""
    source: OauthClientSource = OauthClientSource.UNSPECIFIED
    policy: OauthClientPolicy = OauthClientPolicy.UNSPECIFIED
    first_authorization_at: datetime | None = None
    last_authorization_at: datetime | None = None
    redirect_origins: list[str] = field(default_factory=list)
    authorized_user_count: int = 0

    @classmethod
    def parse(cls, data: dict[str, Any] | None) -> OAuthClient | None:
        if not data:
            return None
        return cls(
            client_id=data.get("clientId", ""),
            client_name=data.get("clientName", ""),
            client_origin=data.get("clientOrigin", ""),
            source=_parse_enum(
                OauthClientSource, data.get("source"), OauthClientSource.UNSPECIFIED
            ),  # type: ignore[arg-type]
            policy=_parse_enum(
                OauthClientPolicy, data.get("policy"), OauthClientPolicy.UNSPECIFIED
            ),  # type: ignore[arg-type]
            first_authorization_at=parse_datetime(data.get("firstAuthorizationAt")),
            last_authorization_at=parse_datetime(data.get("lastAuthorizationAt")),
            redirect_origins=list(data.get("redirectOrigins") or []),
            authorized_user_count=int(data.get("authorizedUserCount", 0)),
        )

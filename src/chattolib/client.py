"""Main async client for the Chatto Connect API.

Chatto migrated from GraphQL to a protobuf-first Connect API in v0.4.x
(see ADR-042). The client speaks Connect binary protobuf over a
hand-rolled transport (``chattolib._connect``) and the generated service
stubs under ``chattolib._pb`` for all request/response operations. Realtime
events live in ``chattolib.realtime``.
"""

# mypy: disable-error-code="no-any-return"
# Rationale: attribute access on generated protobuf messages is Any-typed
# from mypy's perspective (the generated modules skip type checking via
# follow_imports=skip). The runtime types are exactly what the return-type
# annotations claim.

from __future__ import annotations

import hashlib
from collections.abc import Awaitable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

# ConnectError is raised by our hand-rolled Connect client (chattolib._connect);
# catch it here to translate into the library's public exception hierarchy.
from chattolib._connect import ConnectError  # noqa: E402
from chattolib._pb.chatto.admin.v1 import (
    event_log_pb2,
    room_layout_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    invitations_pb2 as admin_invitations_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    members_pb2 as admin_members_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    oauth_clients_pb2 as admin_oauth_clients_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    permissions_pb2 as admin_permissions_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    roles_pb2 as admin_roles_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    server_pb2 as admin_server_pb2,
)
from chattolib._pb.chatto.api.v1 import (
    account_pb2,
    asset_uploads_pb2,
    attachments_pb2,
    bots_pb2,
    common_pb2,
    link_previews_pb2,
    member_directory_pb2,
    message_search_pb2,
    messages_pb2,
    notifications_pb2,
    pagination_pb2,
    permissions_pb2,
    presence_pb2,
    push_notifications_pb2,
    reactions_pb2,
    read_state_pb2,
    roles_pb2,
    room_directory_pb2,
    room_invitations_pb2,
    room_timeline_pb2,
    rooms_pb2,
    server_state_pb2,
    threads_pb2,
    user_service_pb2,
    user_status_pb2,
    viewer_pb2,
    voice_calls_pb2,
)
from chattolib._pb.chatto.auth.v1 import (
    external_identity_auth_pb2,
    push_subscription_cleanup_pb2,
    setup_pb2,
)
from chattolib._pb.chatto.discovery.v1 import server_pb2 as discovery_server_pb2
from chattolib._transport import (
    ServiceClients,
    build_service_clients,
    pb_to_dict,
    translate_connect_error,
)
from chattolib.exceptions import ChattoAuthError, ChattoError
from chattolib.types import (
    AccountCreationPolicy,
    ActiveCall,
    ActiveCallParticipant,
    AdminMember,
    AdminRole,
    AdminRoomLayoutGroup,
    Asset,
    AssetUpload,
    BotAccount,
    BotApiKey,
    BotOutboundWebhook,
    BotWebhookFailure,
    CallMediaPublisherKind,
    DirectoryMember,
    ExternalIdentityProvider,
    FollowedThread,
    FollowedThreadsPage,
    ImageTransformOptions,
    InvitationCode,
    LinkedExternalIdentity,
    LinkPreview,
    Message,
    MessageSearchGroupBy,
    MessageSearchOrder,
    MessageSearchScope,
    Neighbor,
    NeighborhoodServersPage,
    NotificationOccurrence,
    NotificationOccurrencesPage,
    NotificationPolicy,
    OAuthClient,
    OauthClientPolicy,
    Page,
    PendingExternalIdentity,
    PermissionDecision,
    PermissionScopeKind,
    PinnedMessage,
    PinnedMessagesPage,
    PresencePreference,
    PresenceStatus,
    Role,
    Room,
    RoomDirectoryScope,
    RoomGroup,
    RoomInvitation,
    RoomNotice,
    RoomReadState,
    RoomSuspension,
    RoomThreadingMode,
    RoomWithViewerState,
    SearchResultsPage,
    SearchStatus,
    ServerConfig,
    ServerFeature,
    ServerLogin,
    ServerProfile,
    ServerRuntimeConfig,
    ThreadOrder,
    ThreadReadState,
    ThreadRootAuthorFilter,
    ThreadViewerState,
    TimeFormat,
    TimelinePage,
    User,
    UserSettings,
    VerifiedEmail,
    ViewerUser,
    format_datetime,
    parse_datetime,
)

RES = TypeVar("RES")


def _page_pb(limit: int | None, offset: int | None) -> pagination_pb2.PageRequest | None:
    if limit is None and offset is None:
        return None
    return pagination_pb2.PageRequest(limit=limit or 0, offset=offset or 0)


def _policy_scope(*, room_id: str = "", room_group_id: str = "") -> Any:
    """Build a ``NotificationPolicyScope`` selecting server / group / room."""
    scope = notifications_pb2.NotificationPolicyScope()
    if room_id:
        scope.room_id = room_id
    elif room_group_id:
        scope.room_group_id = room_group_id
    else:
        scope.server.SetCachedValue()
    return scope


def _layout_item(target: Any, kind: str, item_id: str) -> None:
    """Set the required ``oneof item`` on an ``AdminRoomLayoutItemInput``."""
    if kind == "room":
        target.room_id = item_id
    elif kind == "sidebar_link":
        target.sidebar_link_id = item_id
    else:
        raise ValueError(f"unknown room-layout item kind: {kind!r} (use 'room' or 'sidebar_link')")


def _thumbnail_pb(
    opts: ImageTransformOptions | None,
) -> common_pb2.ImageTransformOptions | None:
    if opts is None:
        return None
    return common_pb2.ImageTransformOptions(
        width=opts.width, height=opts.height, fit=opts.fit.value
    )


def _timestamp_pb(value: datetime | None) -> Any:
    from google.protobuf import timestamp_pb2

    if value is None:
        return None
    ts = timestamp_pb2.Timestamp()
    ts.FromJsonString(format_datetime(value))
    return ts


def _permission_scope_pb(kind: PermissionScopeKind, scope_id: str) -> Any:
    """Build an ``admin.v1.PermissionScope`` (SERVER/DM take an empty ID)."""
    scope = admin_permissions_pb2.PermissionScope()
    scope.kind = admin_permissions_pb2.PermissionScopeKind.Value(kind.value)
    if scope_id:
        scope.id = scope_id
    return scope


class ChattoClient:
    """Async client for the Chatto Connect API.

    Usage::

        async with await ChattoClient.login("user", "pass") as client:
            viewer = await client.get_viewer()
            rooms = await client.list_rooms()

        # Or with an existing token:
        async with ChattoClient(token="cht_...") as client:
            ...
    """

    DEFAULT_BASE_URL = "https://chat.chatto.run"

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session_cookie: str | None = None,
        service_clients: ServiceClients | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session_cookie = session_cookie
        self._svc = service_clients or build_service_clients(self._base_url)
        self._owns_clients = service_clients is None

    async def __aenter__(self) -> ChattoClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_clients:
            await self._svc.close()

    # --- Transport ------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def session_cookie(self) -> str | None:
        return self._session_cookie

    @property
    def services(self) -> ServiceClients:
        """Direct access to the underlying ConnectRPC service clients.

        Useful when a caller wants to reach an RPC that this class doesn't
        expose yet, or wants full protobuf messages instead of the
        dataclass views returned by the high-level helpers.
        """
        return self._svc

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._session_cookie:
            headers["Cookie"] = f"chatto_session={self._session_cookie}"
        return headers

    async def _rpc(self, coro: Awaitable[RES]) -> RES:
        """Await a ConnectRPC coroutine, translating errors."""
        try:
            return await coro
        except ConnectError as exc:
            raise translate_connect_error(exc) from exc

    # --- Server discovery ----------------------------------------------

    async def get_server(self) -> tuple[ServerProfile, ServerLogin]:
        """Public server profile and login options. Does not require auth."""
        resp = await self._rpc(
            self._svc.server_discovery.get_server(
                discovery_server_pb2.GetServerRequest(),
                headers=self._headers(),
            )
        )
        return (
            ServerProfile.parse(pb_to_dict(resp.profile)),
            ServerLogin.parse(pb_to_dict(resp.login)),
        )

    async def list_neighbors(self) -> list[str]:
        """Public Neighbor directory: the advertised canonical server origins.

        Does not require auth. The response has no ordering contract.
        """
        resp = await self._rpc(
            self._svc.server_discovery.list_neighbors(
                discovery_server_pb2.ListNeighborsRequest(),
                headers=self._headers(),
            )
        )
        return list(resp.origins)

    async def list_neighborhood_servers(self) -> NeighborhoodServersPage:
        """Servers in the Neighborhood the called server has discovered.

        Does not require auth. The server loads other servers' public profiles
        in the background and caches the result (refreshed at least hourly),
        so the call itself contacts no other server. The response has no
        ordering contract; ``refreshed_at`` is absent before the server's
        first completed discovery.
        """
        resp = await self._rpc(
            self._svc.server_discovery.list_neighborhood_servers(
                discovery_server_pb2.ListNeighborhoodServersRequest(),
                headers=self._headers(),
            )
        )
        return NeighborhoodServersPage.parse(pb_to_dict(resp))

    async def list_features(
        self, *, locale: str | None = None, introduced_after_version: str | None = None
    ) -> list[ServerFeature]:
        """Public feature catalog of the server software (since 0.5.0b27).

        Does not require auth. Advisory upgrade guidance, not capability
        negotiation — accept previously unknown feature IDs. Older servers
        return UNIMPLEMENTED; catch that if you need to support them.
        ``introduced_after_version`` must be a full Semantic Version
        (including any prerelease stage) or INVALID_ARGUMENT is raised.
        """
        req = discovery_server_pb2.ListFeaturesRequest()
        if locale is not None:
            req.locale = locale
        if introduced_after_version is not None:
            req.introduced_after_version = introduced_after_version
        resp = await self._rpc(
            self._svc.server_discovery.list_features(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return [
            f
            for f in (ServerFeature.parse(row) for row in data.get("features") or [])
            if f is not None
        ]

    async def get_motd(self) -> str | None:
        resp = await self._rpc(
            self._svc.server.get_motd(server_state_pb2.GetMotdRequest(), headers=self._headers())
        )
        if not resp.HasField("motd"):
            return None
        return resp.motd

    async def get_runtime_config(self) -> ServerRuntimeConfig:
        resp = await self._rpc(
            self._svc.server.get_runtime_config(
                server_state_pb2.GetRuntimeConfigRequest(),
                headers=self._headers(),
            )
        )
        return ServerRuntimeConfig.parse(pb_to_dict(resp.runtime))

    # --- Viewer ---------------------------------------------------------

    async def get_viewer(self) -> dict[str, Any]:
        """Full authenticated viewer snapshot (camelCase JSON dict).

        The response contains ``user``, ``capabilities``, notification
        preferences, permissions and viewer state. Callers that only need the
        current user's public profile should use ``me()`` for a typed result.
        """
        resp = await self._rpc(
            self._svc.viewer.get_viewer(viewer_pb2.GetViewerRequest(), headers=self._headers())
        )
        return pb_to_dict(resp)

    async def viewer_user(self) -> ViewerUser | None:
        data = await self.get_viewer()
        return ViewerUser.parse(data.get("user"))

    async def me(self) -> User:
        """Return the authenticated user's public profile."""
        viewer = await self.viewer_user()
        if viewer is None or viewer.profile is None:
            raise ChattoAuthError("No authenticated viewer")
        return viewer.profile

    # --- MyAccount -----------------------------------------------------

    async def update_user_profile(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        login: str | None = None,
        bio: str | None = None,
    ) -> User:
        """Update a user's public profile via ``UserService.UpdateUserProfile``.

        This is the one wire path for profile edits in 0.5.0-beta.9. Users
        update their own account without extra authority; updating another
        human requires ``user.manage-accounts`` (and, for a bot target,
        ownership of the bot, ``user.manage-accounts``, or ``bot.manage``) —
        the server enforces that. A ``login`` change is rate-limited by the
        server's username-change cooldown. Returns the updated ``User``.
        """
        req = user_service_pb2.UpdateUserProfileRequest(user_id=user_id)
        if display_name is not None:
            req.display_name = display_name
        if login is not None:
            req.login = login
        if bio is not None:
            req.bio = bio
        resp = await self._rpc(self._svc.user.update_user_profile(req, headers=self._headers()))
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

    async def update_profile(
        self,
        *,
        display_name: str | None = None,
        login: str | None = None,
        bio: str | None = None,
    ) -> User:
        """Update the authenticated user's own public profile.

        The pre-0.5.0b9 ``MyAccountService.UpdateProfile`` RPC was removed;
        profile edits now go through ``UserService.UpdateUserProfile``, which
        needs a target ``user_id`` — so this resolves the caller's own id from
        the viewer snapshot first and then delegates to
        :meth:`update_user_profile`.
        """
        me = await self.me()
        return await self.update_user_profile(
            me.id, display_name=display_name, login=login, bio=bio
        )

    async def update_settings(
        self,
        *,
        timezone: str | None = None,
        time_format: TimeFormat | None = None,
        share_timezone: bool | None = None,
    ) -> UserSettings:
        req = account_pb2.UpdateSettingsRequest()
        if timezone is not None:
            req.timezone = timezone
        if time_format is not None:
            req.time_format = time_format.value
        if share_timezone is not None:
            req.share_timezone = share_timezone
        resp = await self._rpc(self._svc.account.update_settings(req, headers=self._headers()))
        return UserSettings.parse(pb_to_dict(resp.settings))

    async def set_presence(
        self,
        status: PresenceStatus,
        *,
        user_selected: bool = True,
    ) -> PresenceStatus:
        """Report a *live* presence status (the pre-0.5.0b6 mechanism).

        This is the legacy, transient report: it expires after 60 seconds
        without a refresh and a saved private choice (see
        :meth:`set_presence_preference`) overrides it, including when
        ``user_selected`` is set. New clients should prefer the
        :meth:`set_presence_preference` / :meth:`refresh_presence` pair.
        """
        if status in (PresenceStatus.UNSPECIFIED, PresenceStatus.OFFLINE):
            raise ValueError(
                "UNSPECIFIED and OFFLINE cannot be set as presence status; "
                "stop refreshing to go offline"
            )
        req = presence_pb2.SetPresenceRequest(status=status.value, user_selected=user_selected)
        resp = await self._rpc(self._svc.account.set_presence(req, headers=self._headers()))
        name = presence_pb2.PresenceStatus.Name(resp.status)
        return PresenceStatus(name)

    async def get_presence_preference(self) -> PresencePreference | None:
        """Read the authenticated account's private saved availability choice.

        Returns ``None`` until the account has saved a choice for the first
        time. This is the read side of the 0.5.0b6 preference pair; use
        :meth:`set_presence_preference` to change it.
        """
        resp = await self._rpc(
            self._svc.account.get_presence_preference(
                presence_pb2.GetPresencePreferenceRequest(), headers=self._headers()
            )
        )
        return PresencePreference.parse(pb_to_dict(resp.preference))

    async def set_presence_preference(
        self,
        status: PresenceStatus,
        *,
        expected_revision: str = "",
    ) -> PresencePreference:
        """Save an availability choice for every device on this server.

        Unlike :meth:`set_presence`, the choice persists across disconnects
        and ``OFFLINE`` is a valid value (it means "Appear Offline" and
        suppresses public presence and typing). Pass ``expected_revision``
        from a prior :meth:`get_presence_preference` to guard against a
        concurrent change; a stale revision is rejected with ``ABORTED``.
        Leave it empty only when initialising an absent choice.
        """
        if status is PresenceStatus.UNSPECIFIED:
            raise ValueError("UNSPECIFIED cannot be saved as a presence preference")
        req = presence_pb2.SetPresencePreferenceRequest(
            status=status.value, expected_revision=expected_revision
        )
        resp = await self._rpc(
            self._svc.account.set_presence_preference(req, headers=self._headers())
        )
        pref = PresencePreference.parse(pb_to_dict(resp.preference))
        assert pref is not None
        return pref

    async def refresh_presence(self) -> PresencePreference | None:
        """Refresh connection liveness without changing the saved choice.

        Call roughly every 30 seconds to stay "live" (liveness expires after
        60 seconds). Accounts with a saved ``OFFLINE`` choice may refresh
        without emitting public presence signals. Returns the current private
        choice so a client can recover a choice it missed while disconnected.
        """
        resp = await self._rpc(
            self._svc.account.refresh_presence(
                presence_pb2.RefreshPresenceRequest(), headers=self._headers()
            )
        )
        return PresencePreference.parse(pb_to_dict(resp.preference))

    async def set_custom_status(
        self,
        emoji: str,
        text: str,
        *,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        req = user_status_pb2.SetCustomStatusRequest(emoji=emoji, text=text)
        if expires_at is not None:
            req.expires_at.CopyFrom(_timestamp_pb(expires_at))
        resp = await self._rpc(self._svc.account.set_custom_status(req, headers=self._headers()))
        return pb_to_dict(resp)

    async def delete_custom_status(self) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.account.delete_custom_status(
                user_status_pb2.DeleteCustomStatusRequest(), headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    # --- Roles (public) -----------------------------------------------

    async def list_roles(self) -> list[Role]:
        resp = await self._rpc(
            self._svc.roles.list_roles(roles_pb2.ListRolesRequest(), headers=self._headers())
        )
        data = pb_to_dict(resp)
        return [r for r in (Role.parse(row) for row in data.get("roles") or []) if r is not None]

    async def get_role(self, name: str) -> Role | None:
        resp = await self._rpc(
            self._svc.roles.get_role(roles_pb2.GetRoleRequest(name=name), headers=self._headers())
        )
        return Role.parse(pb_to_dict(resp.role))

    async def batch_get_roles(self, names: list[str]) -> list[Role]:
        resp = await self._rpc(
            self._svc.roles.batch_get_roles(
                roles_pb2.BatchGetRolesRequest(names=names), headers=self._headers()
            )
        )
        data = pb_to_dict(resp)
        return [r for r in (Role.parse(row) for row in data.get("roles") or []) if r is not None]

    # --- Room directory ------------------------------------------------

    async def list_rooms(
        self, scope: RoomDirectoryScope = RoomDirectoryScope.ALL
    ) -> list[RoomWithViewerState]:
        resp = await self._rpc(
            self._svc.room_directory.list_rooms(
                room_directory_pb2.ListRoomsRequest(scope=scope.value),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            r
            for r in (RoomWithViewerState.parse(row) for row in data.get("rooms") or [])
            if r is not None
        ]

    async def list_room_groups(self) -> list[RoomGroup]:
        resp = await self._rpc(
            self._svc.room_directory.list_room_groups(
                room_directory_pb2.ListRoomGroupsRequest(),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            g for g in (RoomGroup.parse(row) for row in data.get("groups") or []) if g is not None
        ]

    async def get_room_group(self, group_id: str) -> RoomGroup | None:
        resp = await self._rpc(
            self._svc.room_directory.get_room_group(
                room_directory_pb2.GetRoomGroupRequest(group_id=group_id),
                headers=self._headers(),
            )
        )
        return RoomGroup.parse(pb_to_dict(resp.group))

    async def batch_get_room_groups(self, group_ids: list[str]) -> list[RoomGroup]:
        resp = await self._rpc(
            self._svc.room_directory.batch_get_room_groups(
                room_directory_pb2.BatchGetRoomGroupsRequest(group_ids=group_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            g for g in (RoomGroup.parse(row) for row in data.get("groups") or []) if g is not None
        ]

    async def get_room(self, room_id: str) -> RoomWithViewerState | None:
        resp = await self._rpc(
            self._svc.room_directory.get_room(
                room_directory_pb2.GetRoomRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return RoomWithViewerState.parse(pb_to_dict(resp.room))

    async def batch_get_rooms(self, room_ids: list[str]) -> list[RoomWithViewerState]:
        resp = await self._rpc(
            self._svc.room_directory.batch_get_rooms(
                room_directory_pb2.BatchGetRoomsRequest(room_ids=room_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            r
            for r in (RoomWithViewerState.parse(row) for row in data.get("rooms") or [])
            if r is not None
        ]

    # --- Room invitations (since 0.5.0b20) ------------------------------

    async def create_room_invitation(self, room_id: str, recipient_id: str) -> RoomInvitation:
        """Invite ``recipient_id`` to ``room_id``. Requires room membership and
        ``room.invite``. A duplicate from the same sender returns the existing
        pending invitation; a pending invitation from a *different* sender
        raises ``INVALID_ARGUMENT``."""
        resp = await self._rpc(
            self._svc.room_invitations.create_room_invitation(
                room_invitations_pb2.CreateRoomInvitationRequest(
                    room_id=room_id, recipient_id=recipient_id
                ),
                headers=self._headers(),
            )
        )
        invitation = RoomInvitation.parse(pb_to_dict(resp.invitation))
        assert invitation is not None
        return invitation

    async def get_room_invitation(self, invitation_id: str) -> RoomInvitation | None:
        """Fetch one invitation by ID. ``NOT_FOUND`` for absent or
        inaccessible invitations (raised as :class:`ChattoConnectError`)."""
        resp = await self._rpc(
            self._svc.room_invitations.get_room_invitation(
                room_invitations_pb2.GetRoomInvitationRequest(invitation_id=invitation_id),
                headers=self._headers(),
            )
        )
        return RoomInvitation.parse(pb_to_dict(resp.invitation))

    async def batch_get_room_invitations(self, invitation_ids: list[str]) -> list[RoomInvitation]:
        """Fetch up to 100 invitations; absent/inaccessible IDs are omitted."""
        resp = await self._rpc(
            self._svc.room_invitations.batch_get_room_invitations(
                room_invitations_pb2.BatchGetRoomInvitationsRequest(invitation_ids=invitation_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            i
            for i in (RoomInvitation.parse(row) for row in data.get("invitations") or [])
            if i is not None
        ]

    async def list_room_invitations(
        self,
        *,
        sent: bool = False,
        pending_only: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[RoomInvitation], Page]:
        """List the caller's received (default) or sent invitations, newest
        first. Default page size 50, maximum 100. ``pending_only`` restricts to
        unexpired pending invitations."""
        req = room_invitations_pb2.ListRoomInvitationsRequest(sent=sent, pending_only=pending_only)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(
            self._svc.room_invitations.list_room_invitations(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        invitations = [
            i
            for i in (RoomInvitation.parse(row) for row in data.get("invitations") or [])
            if i is not None
        ]
        return invitations, Page.parse(data.get("page"))

    async def accept_room_invitation(self, invitation_id: str) -> RoomInvitation:
        """Accept an invitation (recipient-only). Rechecks the sender's
        authority at accept time and bypasses only ``room.join``; membership is
        granted by acceptance."""
        resp = await self._rpc(
            self._svc.room_invitations.accept_room_invitation(
                room_invitations_pb2.AcceptRoomInvitationRequest(invitation_id=invitation_id),
                headers=self._headers(),
            )
        )
        invitation = RoomInvitation.parse(pb_to_dict(resp.invitation))
        assert invitation is not None
        return invitation

    async def decline_room_invitation(self, invitation_id: str) -> RoomInvitation:
        """Decline an invitation (recipient-only). Does not change membership
        or notification preferences."""
        resp = await self._rpc(
            self._svc.room_invitations.decline_room_invitation(
                room_invitations_pb2.DeclineRoomInvitationRequest(invitation_id=invitation_id),
                headers=self._headers(),
            )
        )
        invitation = RoomInvitation.parse(pb_to_dict(resp.invitation))
        assert invitation is not None
        return invitation

    # --- Room lifecycle & membership -----------------------------------

    async def create_room(
        self,
        name: str,
        group_id: str,
        *,
        description: str = "",
        universal: bool = False,
        threading_mode: RoomThreadingMode | None = None,
    ) -> Room:
        req = rooms_pb2.CreateRoomRequest(
            name=name,
            group_id=group_id,
            description=description,
            universal=universal,
        )
        if threading_mode is not None:
            req.threading_mode = threading_mode.value
        resp = await self._rpc(self._svc.rooms.create_room(req, headers=self._headers()))
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def update_room(
        self,
        room_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        universal: bool | None = None,
        slow_mode_seconds: int | None = None,
        threading_mode: RoomThreadingMode | None = None,
        thread_slow_mode_seconds: int | None = None,
        show_membership_events: bool | None = None,
    ) -> Room:
        req = rooms_pb2.UpdateRoomRequest(room_id=room_id)
        if name is not None:
            req.name = name
        if description is not None:
            req.description = description
        if universal is not None:
            req.universal = universal
        if slow_mode_seconds is not None:
            req.slow_mode_seconds = slow_mode_seconds
        if threading_mode is not None:
            req.threading_mode = threading_mode.value
        if thread_slow_mode_seconds is not None:
            req.thread_slow_mode_seconds = thread_slow_mode_seconds
        if show_membership_events is not None:
            req.show_membership_events = show_membership_events
        resp = await self._rpc(self._svc.rooms.update_room(req, headers=self._headers()))
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def get_notice(self, room_id: str) -> RoomNotice:
        """Read the current channel notice (since 0.5.0b27). Requires current
        room membership (including archived rooms). A room without a notice
        returns an empty body; ``version`` is still present for CAS."""
        resp = await self._rpc(
            self._svc.rooms.get_notice(
                rooms_pb2.GetNoticeRequest(room_id=room_id), headers=self._headers()
            )
        )
        return RoomNotice.parse(pb_to_dict(resp.notice))

    async def publish_notice(
        self, room_id: str, body: str, *, expected_version: str = "", republish: bool = False
    ) -> RoomNotice:
        """Publish or replace a channel notice (since 0.5.0b27). Send the
        current ``expected_version`` for concurrency control. Replacements
        preserve member dismissals unless ``republish=True`` announces the
        replacement to members who dismissed the previous notice."""
        req = rooms_pb2.PublishNoticeRequest(
            room_id=room_id, body=body, expected_version=expected_version, republish=republish
        )
        resp = await self._rpc(self._svc.rooms.publish_notice(req, headers=self._headers()))
        return RoomNotice.parse(pb_to_dict(resp.notice))

    async def clear_notice(self, room_id: str, *, expected_version: str = "") -> RoomNotice:
        """Clear the current notice without removing its concurrency version
        (since 0.5.0b27)."""
        resp = await self._rpc(
            self._svc.rooms.clear_notice(
                rooms_pb2.ClearNoticeRequest(room_id=room_id, expected_version=expected_version),
                headers=self._headers(),
            )
        )
        return RoomNotice.parse(pb_to_dict(resp.notice))

    async def archive_room(self, room_id: str) -> Room:
        resp = await self._rpc(
            self._svc.rooms.archive_room(
                rooms_pb2.ArchiveRoomRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def unarchive_room(self, room_id: str) -> Room:
        resp = await self._rpc(
            self._svc.rooms.unarchive_room(
                rooms_pb2.UnarchiveRoomRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def join_room(self, room_id: str) -> Room:
        resp = await self._rpc(
            self._svc.rooms.join_room(
                rooms_pb2.JoinRoomRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def join_room_group(self, group_id: str) -> list[str]:
        resp = await self._rpc(
            self._svc.rooms.join_room_group(
                rooms_pb2.JoinRoomGroupRequest(group_id=group_id),
                headers=self._headers(),
            )
        )
        return list(resp.joined_room_ids)

    async def start_dm(self, participant_ids: list[str]) -> Room:
        resp = await self._rpc(
            self._svc.rooms.start_dm(
                rooms_pb2.StartDMRequest(participant_ids=participant_ids),
                headers=self._headers(),
            )
        )
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def leave_room(self, room_id: str) -> None:
        await self._rpc(
            self._svc.rooms.leave_room(
                rooms_pb2.LeaveRoomRequest(room_id=room_id),
                headers=self._headers(),
            )
        )

    async def add_member(self, room_id: str, user_id: str) -> DirectoryMember | None:
        resp = await self._rpc(
            self._svc.rooms.add_member(
                rooms_pb2.AddMemberRequest(room_id=room_id, user_id=user_id),
                headers=self._headers(),
            )
        )
        return DirectoryMember.parse(pb_to_dict(resp.member))

    async def remove_member(self, room_id: str, user_id: str) -> bool:
        resp = await self._rpc(
            self._svc.rooms.remove_member(
                rooms_pb2.RemoveMemberRequest(room_id=room_id, user_id=user_id),
                headers=self._headers(),
            )
        )
        return resp.removed

    async def list_room_members(
        self,
        room_id: str,
        *,
        search: str = "",
        presence_statuses: list[PresenceStatus] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[str], Page]:
        """List a room's member IDs (plus page metadata).

        The server returns member IDs only, not full profiles; hydrate them
        with :meth:`batch_get_room_members`. ``presence_statuses`` filters to
        members in any of the given connected states (max 4).
        """
        req = member_directory_pb2.ListMembersRequest(room_id=room_id, search=search)
        if presence_statuses:
            req.presence_statuses.extend(
                presence_pb2.PresenceStatus.Value(p.value) for p in presence_statuses
            )
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.rooms.list_members(req, headers=self._headers()))
        data = pb_to_dict(resp)
        return list(data.get("userIds") or []), Page.parse(data.get("page"))

    async def get_room_member(self, room_id: str, user_id: str) -> DirectoryMember | None:
        resp = await self._rpc(
            self._svc.rooms.get_member(
                member_directory_pb2.GetMemberRequest(room_id=room_id, user_id=user_id),
                headers=self._headers(),
            )
        )
        return DirectoryMember.parse(pb_to_dict(resp.member))

    async def batch_get_room_members(
        self, room_id: str, user_ids: list[str]
    ) -> list[DirectoryMember]:
        resp = await self._rpc(
            self._svc.rooms.batch_get_members(
                member_directory_pb2.BatchGetMembersRequest(room_id=room_id, user_ids=user_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            m
            for m in (DirectoryMember.parse(row) for row in data.get("members") or [])
            if m is not None
        ]

    async def remove_user(
        self,
        room_id: str,
        user_id: str,
        reason: str,
        *,
        suspension_expires_at: datetime | None = None,
        suspend_indefinitely: bool = False,
    ) -> None:
        """Remove a current room member, optionally suspending them.

        Maps to ``RoomService.RemoveUser`` (the 0.5.0b7 replacement for
        ``BanMember``). Without a suspension the user may rejoin under normal
        room permissions; with one, they cannot rejoin until the suspension
        expires or ``lift_suspension`` is called. At most one of the two
        suspension choices may be given.
        """
        if suspend_indefinitely and suspension_expires_at is not None:
            raise ValueError(
                "choose either suspension_expires_at or suspend_indefinitely, not both"
            )
        req = rooms_pb2.RemoveUserRequest(room_id=room_id, user_id=user_id, reason=reason)
        if suspend_indefinitely:
            req.suspend_indefinitely = True
        elif suspension_expires_at is not None:
            req.suspension_expires_at.CopyFrom(_timestamp_pb(suspension_expires_at))
        await self._rpc(self._svc.rooms.remove_user(req, headers=self._headers()))

    async def lift_suspension(self, room_id: str, user_id: str, reason: str) -> None:
        await self._rpc(
            self._svc.rooms.lift_suspension(
                rooms_pb2.LiftSuspensionRequest(room_id=room_id, user_id=user_id, reason=reason),
                headers=self._headers(),
            )
        )

    async def list_suspensions(
        self,
        *,
        room_id: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[RoomSuspension], Page]:
        req = rooms_pb2.ListSuspensionsRequest(room_id=room_id)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.rooms.list_suspensions(req, headers=self._headers()))
        data = pb_to_dict(resp)
        suspensions = [
            s
            for s in (RoomSuspension.parse(row) for row in data.get("suspensions") or [])
            if s is not None
        ]
        return suspensions, Page.parse(data.get("page"))

    async def refresh_typing_indicator(
        self, room_id: str, *, thread_root_event_id: str = ""
    ) -> None:
        await self._rpc(
            self._svc.rooms.refresh_typing_indicator(
                rooms_pb2.RefreshTypingIndicatorRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )

    # --- Room timeline / read state -----------------------------------

    async def get_room_events(
        self,
        room_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> TimelinePage:
        req = room_timeline_pb2.GetRoomEventsRequest(room_id=room_id)
        if limit is not None:
            req.limit = limit
        if before is not None:
            req.before = before
        elif after is not None:
            req.after = after
        resp = await self._rpc(self._svc.rooms.get_room_events(req, headers=self._headers()))
        return TimelinePage.parse(pb_to_dict(resp.page))

    async def get_room_events_around(
        self,
        room_id: str,
        event_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[TimelinePage, int]:
        req = room_timeline_pb2.GetRoomEventsAroundRequest(room_id=room_id, event_id=event_id)
        if limit is not None:
            req.limit = limit
        resp = await self._rpc(self._svc.rooms.get_room_events_around(req, headers=self._headers()))
        return TimelinePage.parse(pb_to_dict(resp.page)), resp.target_index

    async def mark_room_as_read(
        self, room_id: str, up_to_event_id: str = ""
    ) -> tuple[datetime | None, datetime | None]:
        resp = await self._rpc(
            self._svc.rooms.mark_room_as_read(
                read_state_pb2.MarkRoomAsReadRequest(
                    room_id=room_id, up_to_event_id=up_to_event_id
                ),
                headers=self._headers(),
            )
        )
        d = pb_to_dict(resp)
        return (
            parse_datetime(d.get("lastReadAt")),
            parse_datetime(d.get("previousLastReadAt")),
        )

    async def list_room_attachments(
        self,
        room_id: str,
        *,
        thumbnail: ImageTransformOptions | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[dict[str, Any]], Page]:
        req = rooms_pb2.ListRoomAttachmentsRequest(room_id=room_id)
        thumb = _thumbnail_pb(thumbnail)
        if thumb is not None:
            req.thumbnail.CopyFrom(thumb)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.rooms.list_room_attachments(req, headers=self._headers()))
        data = pb_to_dict(resp)
        return list(data.get("attachments") or []), Page.parse(data.get("page"))

    async def list_pinned_messages(
        self,
        room_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> PinnedMessagesPage:
        req = rooms_pb2.ListPinnedMessagesRequest(room_id=room_id)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.rooms.list_pinned_messages(req, headers=self._headers()))
        return PinnedMessagesPage.parse(pb_to_dict(resp))

    async def pin_message(self, room_id: str, message_event_id: str) -> PinnedMessage:
        resp = await self._rpc(
            self._svc.rooms.create_pinned_message(
                rooms_pb2.CreatePinnedMessageRequest(
                    room_id=room_id, message_event_id=message_event_id
                ),
                headers=self._headers(),
            )
        )
        pm = PinnedMessage.parse(pb_to_dict(resp.pinned_message))
        assert pm is not None
        return pm

    async def unpin_message(self, room_id: str, message_event_id: str) -> bool:
        resp = await self._rpc(
            self._svc.rooms.delete_pinned_message(
                rooms_pb2.DeletePinnedMessageRequest(
                    room_id=room_id, message_event_id=message_event_id
                ),
                headers=self._headers(),
            )
        )
        return resp.deleted

    # --- Messages -------------------------------------------------------

    async def fetch_link_preview(self, url: str) -> tuple[LinkPreview | None, str]:
        resp = await self._rpc(
            self._svc.messages.fetch_link_preview(
                link_previews_pb2.FetchLinkPreviewRequest(url=url),
                headers=self._headers(),
            )
        )
        return LinkPreview.parse(pb_to_dict(resp.preview)), resp.preview_token

    async def post_message(
        self,
        room_id: str,
        body: str = "",
        *,
        attachment_asset_ids: list[str] | None = None,
        thread_root_event_id: str = "",
        in_reply_to: str = "",
        also_send_to_channel: bool = False,
        link_preview_token: str = "",
        idempotency_key: str | None = None,
    ) -> Message:
        req = messages_pb2.CreateMessageRequest(
            room_id=room_id,
            body=body,
            thread_root_event_id=thread_root_event_id,
            in_reply_to=in_reply_to,
            also_send_to_channel=also_send_to_channel,
            link_preview_token=link_preview_token,
        )
        if idempotency_key is not None:
            # Since 0.5.0b27: caller-generated UUID. For 30 minutes after first
            # acceptance an exact retry (same room + arguments) returns the same
            # message ID; changed arguments are rejected.
            req.idempotency_key = idempotency_key
        if attachment_asset_ids:
            req.attachment_asset_ids.extend(attachment_asset_ids)
        resp = await self._rpc(self._svc.messages.create_message(req, headers=self._headers()))
        message = Message.parse(pb_to_dict(resp.message))
        assert message is not None
        return message

    async def update_message(
        self,
        room_id: str,
        event_id: str,
        *,
        body: str | None = None,
        also_send_to_channel: bool | None = None,
    ) -> Message:
        req = messages_pb2.UpdateMessageRequest(room_id=room_id, event_id=event_id)
        if body is not None:
            req.body = body
        if also_send_to_channel is not None:
            req.also_send_to_channel = also_send_to_channel
        resp = await self._rpc(self._svc.messages.update_message(req, headers=self._headers()))
        message = Message.parse(pb_to_dict(resp.message))
        assert message is not None
        return message

    async def delete_message(self, room_id: str, event_id: str) -> None:
        await self._rpc(
            self._svc.messages.delete_message(
                messages_pb2.DeleteMessageRequest(room_id=room_id, event_id=event_id),
                headers=self._headers(),
            )
        )

    async def delete_attachment(self, room_id: str, event_id: str, attachment_id: str) -> None:
        await self._rpc(
            self._svc.messages.delete_attachment(
                messages_pb2.DeleteAttachmentRequest(
                    room_id=room_id, event_id=event_id, attachment_id=attachment_id
                ),
                headers=self._headers(),
            )
        )

    async def delete_link_preview(self, room_id: str, event_id: str, url: str) -> None:
        await self._rpc(
            self._svc.messages.delete_link_preview(
                messages_pb2.DeleteLinkPreviewRequest(room_id=room_id, event_id=event_id, url=url),
                headers=self._headers(),
            )
        )

    async def get_message(self, room_id: str, event_id: str) -> Message | None:
        resp = await self._rpc(
            self._svc.messages.get_message(
                messages_pb2.GetMessageRequest(room_id=room_id, event_id=event_id),
                headers=self._headers(),
            )
        )
        return Message.parse(pb_to_dict(resp.message))

    async def batch_get_messages(self, room_id: str, event_ids: list[str]) -> list[Message]:
        resp = await self._rpc(
            self._svc.messages.batch_get_messages(
                messages_pb2.BatchGetMessagesRequest(room_id=room_id, event_ids=event_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            m for m in (Message.parse(row) for row in data.get("messages") or []) if m is not None
        ]

    async def add_reaction(self, room_id: str, message_event_id: str, emoji: str) -> bool:
        resp = await self._rpc(
            self._svc.messages.add_reaction(
                reactions_pb2.AddReactionRequest(
                    room_id=room_id, message_event_id=message_event_id, emoji=emoji
                ),
                headers=self._headers(),
            )
        )
        return resp.added

    async def remove_reaction(self, room_id: str, message_event_id: str, emoji: str) -> bool:
        resp = await self._rpc(
            self._svc.messages.remove_reaction(
                reactions_pb2.RemoveReactionRequest(
                    room_id=room_id, message_event_id=message_event_id, emoji=emoji
                ),
                headers=self._headers(),
            )
        )
        return resp.removed

    # --- Threads --------------------------------------------------------

    async def follow_thread(self, room_id: str, thread_root_event_id: str) -> None:
        await self._rpc(
            self._svc.threads.follow_thread(
                threads_pb2.FollowThreadRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )

    async def unfollow_thread(self, room_id: str, thread_root_event_id: str) -> None:
        await self._rpc(
            self._svc.threads.unfollow_thread(
                threads_pb2.UnfollowThreadRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )

    async def list_followed_threads(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        include_direct_message_threads: bool | None = None,
        unread_only: bool | None = None,
        root_author_filter: ThreadRootAuthorFilter | None = None,
        order: ThreadOrder | None = None,
    ) -> FollowedThreadsPage:
        """Followed threads, newest activity first by default.

        ``unread_only`` returns only threads with unread replies (older
        servers ignore it); ``include_direct_message_threads`` also lists
        followed direct-message threads; ``root_author_filter`` (since
        0.5.0b16) filters by the author of the thread *root* —
        ``VIEWER`` for threads you started, ``OTHERS`` for threads started
        by someone else (older servers ignore it); ``order`` (since
        0.5.0b18) sorts the feed — ``ACTIVITY`` (default) by newest
        activity, ``CREATED`` by newest root-message creation with unknown
        dates last (older servers ignore it and use activity order).
        """
        req = threads_pb2.ListFollowedThreadsRequest()
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        if include_direct_message_threads is not None:
            req.include_direct_message_threads = include_direct_message_threads
        if unread_only is not None:
            req.unread_only = unread_only
        if root_author_filter is not None:
            req.root_author_filter = threads_pb2.ThreadRootAuthorFilter.Value(
                root_author_filter.value
            )
        if order is not None:
            req.order = threads_pb2.ThreadOrder.Value(order.value)
        resp = await self._rpc(
            self._svc.threads.list_followed_threads(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        threads = [FollowedThread.parse(t) for t in data.get("threads") or []]
        users: dict[str, User] = {}
        includes = data.get("includes") or {}
        for uid, user_data in (includes.get("users") or {}).items():
            parsed = User.parse(user_data)
            if parsed is not None:
                users[uid] = parsed
        return FollowedThreadsPage(
            threads=threads, page=Page.parse(data.get("page")), users_by_id=users
        )

    async def get_thread_events(
        self,
        room_id: str,
        thread_root_event_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> TimelinePage:
        req = room_timeline_pb2.GetThreadEventsRequest(
            room_id=room_id, thread_root_event_id=thread_root_event_id
        )
        if limit is not None:
            req.limit = limit
        if before is not None:
            req.before = before
        elif after is not None:
            req.after = after
        resp = await self._rpc(self._svc.threads.get_thread_events(req, headers=self._headers()))
        data = pb_to_dict(resp)
        page = TimelinePage.parse(data.get("page"))
        page.thread_viewer_state = ThreadViewerState.parse(data.get("viewerState"))
        return page

    async def get_thread_events_around(
        self,
        room_id: str,
        thread_root_event_id: str,
        event_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[TimelinePage, int]:
        req = room_timeline_pb2.GetThreadEventsAroundRequest(
            room_id=room_id,
            thread_root_event_id=thread_root_event_id,
            event_id=event_id,
        )
        if limit is not None:
            req.limit = limit
        resp = await self._rpc(
            self._svc.threads.get_thread_events_around(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        page = TimelinePage.parse(data.get("page"))
        page.thread_viewer_state = ThreadViewerState.parse(data.get("viewerState"))
        return page, resp.target_index

    async def mark_thread_as_read(
        self,
        room_id: str,
        thread_root_event_id: str,
        up_to_event_id: str = "",
    ) -> datetime | None:
        resp = await self._rpc(
            self._svc.threads.mark_thread_as_read(
                read_state_pb2.MarkThreadAsReadRequest(
                    room_id=room_id,
                    thread_root_event_id=thread_root_event_id,
                    up_to_event_id=up_to_event_id,
                ),
                headers=self._headers(),
            )
        )
        d = pb_to_dict(resp)
        return parse_datetime(d.get("previousLastReadAt"))

    # --- Notifications --------------------------------------------------

    async def list_notification_occurrences(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> NotificationOccurrencesPage:
        req = notifications_pb2.ListNotificationOccurrencesRequest()
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(
            self._svc.notifications.list_notification_occurrences(req, headers=self._headers())
        )
        return NotificationOccurrencesPage.parse(pb_to_dict(resp))

    async def get_notification_occurrence(
        self, notification_id: str
    ) -> NotificationOccurrence | None:
        resp = await self._rpc(
            self._svc.notifications.get_notification_occurrence(
                notifications_pb2.GetNotificationOccurrenceRequest(notification_id=notification_id),
                headers=self._headers(),
            )
        )
        raw = pb_to_dict(resp).get("occurrence")
        return NotificationOccurrence.parse(raw) if raw else None

    async def batch_get_notification_occurrences(
        self, notification_ids: list[str]
    ) -> list[NotificationOccurrence]:
        resp = await self._rpc(
            self._svc.notifications.batch_get_notification_occurrences(
                notifications_pb2.BatchGetNotificationOccurrencesRequest(
                    notification_ids=notification_ids
                ),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            o
            for o in (NotificationOccurrence.parse(n) for n in data.get("occurrences") or [])
            if o is not None
        ]

    async def mark_notification_read(self, notification_id: str) -> NotificationOccurrence | None:
        resp = await self._rpc(
            self._svc.notifications.mark_notification_read(
                notifications_pb2.MarkNotificationReadRequest(notification_id=notification_id),
                headers=self._headers(),
            )
        )
        raw = pb_to_dict(resp).get("occurrence")
        return NotificationOccurrence.parse(raw) if raw else None

    async def delete_notification_occurrence(self, notification_id: str) -> bool:
        resp = await self._rpc(
            self._svc.notifications.delete_notification_occurrence(
                notifications_pb2.DeleteNotificationOccurrenceRequest(
                    notification_id=notification_id
                ),
                headers=self._headers(),
            )
        )
        return resp.deleted

    async def batch_delete_notification_occurrences(self, notification_ids: list[str]) -> int:
        resp = await self._rpc(
            self._svc.notifications.batch_delete_notification_occurrences(
                notifications_pb2.BatchDeleteNotificationOccurrencesRequest(
                    notification_ids=notification_ids
                ),
                headers=self._headers(),
            )
        )
        return resp.deleted_count

    async def delete_all_notification_occurrences(self) -> int:
        resp = await self._rpc(
            self._svc.notifications.delete_all_notification_occurrences(
                notifications_pb2.DeleteAllNotificationOccurrencesRequest(),
                headers=self._headers(),
            )
        )
        return resp.deleted_count

    async def get_notification_policy(
        self, *, room_id: str = "", room_group_id: str = ""
    ) -> NotificationPolicy:
        """Get the notification policy for one scope (server / group / room)."""
        req = notifications_pb2.NotificationPolicyServiceGetNotificationPolicyRequest(
            scope=_policy_scope(room_id=room_id, room_group_id=room_group_id)
        )
        resp = await self._rpc(
            self._svc.notification_policy.get_notification_policy(req, headers=self._headers())
        )
        return NotificationPolicy.parse(pb_to_dict(resp.policy.policy))

    async def batch_get_notification_policies(
        self, scopes: list[dict[str, str]]
    ) -> list[NotificationPolicy]:
        """Get a bounded set of notification policies (one per scope).

        Each scope is a dict with ``room_id`` and/or ``room_group_id`` (empty
        dict selects the server scope).
        """
        req = notifications_pb2.BatchGetNotificationPoliciesRequest()
        for scope in scopes:
            req.scopes.add().CopyFrom(
                _policy_scope(
                    room_id=scope.get("room_id", ""),
                    room_group_id=scope.get("room_group_id", ""),
                )
            )
        resp = await self._rpc(
            self._svc.notification_policy.batch_get_notification_policies(
                req, headers=self._headers()
            )
        )
        return [NotificationPolicy.parse(pb_to_dict(p.policy)) for p in resp.policies]

    async def update_notification_policy(
        self,
        *,
        room_id: str = "",
        room_group_id: str = "",
        overrides: dict[str, Any] | None = None,
        update_mask: str | None = None,
    ) -> NotificationPolicy:
        """Sparsely set notification-policy delivery-mode overrides at one scope.

        ``overrides`` maps delivery-mode fields (e.g. ``direct_mentions``,
        ``all_mentions``) to their mode names; ``update_mask`` lists the fields
        to set or clear (``*`` selects all).
        """
        req = notifications_pb2.NotificationPolicyServiceUpdateNotificationPolicyRequest(
            scope=_policy_scope(room_id=room_id, room_group_id=room_group_id)
        )
        if overrides:
            from google.protobuf.json_format import ParseDict

            ParseDict(overrides, req.overrides)
        if update_mask:
            req.update_mask.paths.extend(p for p in update_mask.split(",") if p)
        resp = await self._rpc(
            self._svc.notification_policy.update_notification_policy(req, headers=self._headers())
        )
        return NotificationPolicy.parse(pb_to_dict(resp.policy.policy))

    # --- Push notifications --------------------------------------------

    async def subscribe_push(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        *,
        user_agent: str | None = None,
    ) -> bool:
        req = push_notifications_pb2.SubscribeRequest(endpoint=endpoint, p256dh=p256dh, auth=auth)
        if user_agent is not None:
            req.user_agent = user_agent
        await self._rpc(self._svc.push.subscribe(req, headers=self._headers()))
        return True

    async def unsubscribe_push(self, endpoint: str) -> bool:
        await self._rpc(
            self._svc.push.unsubscribe(
                push_notifications_pb2.UnsubscribeRequest(endpoint=endpoint),
                headers=self._headers(),
            )
        )
        return True

    # --- Assets ---------------------------------------------------------

    async def get_asset(
        self,
        room_id: str,
        asset_id: str,
        *,
        thumbnail: ImageTransformOptions | None = None,
    ) -> Asset | None:
        req = attachments_pb2.GetAssetRequest(room_id=room_id, asset_id=asset_id)
        thumb = _thumbnail_pb(thumbnail)
        if thumb is not None:
            req.thumbnail.CopyFrom(thumb)
        resp = await self._rpc(self._svc.assets.get_asset(req, headers=self._headers()))
        return Asset.parse(pb_to_dict(resp.asset))

    async def batch_get_assets(
        self,
        room_id: str,
        asset_ids: list[str],
        *,
        thumbnail: ImageTransformOptions | None = None,
    ) -> list[Asset]:
        req = attachments_pb2.BatchGetAssetsRequest(room_id=room_id, asset_ids=asset_ids)
        thumb = _thumbnail_pb(thumbnail)
        if thumb is not None:
            req.thumbnail.CopyFrom(thumb)
        resp = await self._rpc(self._svc.assets.batch_get_assets(req, headers=self._headers()))
        data = pb_to_dict(resp)
        return [a for a in (Asset.parse(row) for row in data.get("assets") or []) if a is not None]

    # --- Asset uploads ------------------------------------------------

    async def create_upload(
        self,
        room_id: str,
        filename: str,
        size: int,
        sha256: str,
        *,
        content_type: str = "",
    ) -> AssetUpload:
        resp = await self._rpc(
            self._svc.asset_uploads.create_upload(
                asset_uploads_pb2.CreateUploadRequest(
                    room_id=room_id,
                    filename=filename,
                    content_type=content_type,
                    size=size,
                    sha256=sha256,
                ),
                headers=self._headers(),
            )
        )
        upload = AssetUpload.parse(pb_to_dict(resp.upload))
        assert upload is not None
        return upload

    async def upload_chunk(
        self, upload_id: str, offset: int, content: bytes, chunk_sha256: str
    ) -> AssetUpload:
        resp = await self._rpc(
            self._svc.asset_uploads.upload_chunk(
                asset_uploads_pb2.UploadChunkRequest(
                    upload_id=upload_id,
                    offset=offset,
                    content=content,
                    chunk_sha256=chunk_sha256,
                ),
                headers=self._headers(),
            )
        )
        upload = AssetUpload.parse(pb_to_dict(resp.upload))
        assert upload is not None
        return upload

    async def get_upload(self, upload_id: str) -> AssetUpload:
        resp = await self._rpc(
            self._svc.asset_uploads.get_upload(
                asset_uploads_pb2.GetUploadRequest(upload_id=upload_id),
                headers=self._headers(),
            )
        )
        upload = AssetUpload.parse(pb_to_dict(resp.upload))
        assert upload is not None
        return upload

    async def complete_upload(self, upload_id: str) -> tuple[AssetUpload, Asset | None]:
        resp = await self._rpc(
            self._svc.asset_uploads.complete_upload(
                asset_uploads_pb2.CompleteUploadRequest(upload_id=upload_id),
                headers=self._headers(),
            )
        )
        upload = AssetUpload.parse(pb_to_dict(resp.upload))
        assert upload is not None
        return upload, Asset.parse(pb_to_dict(resp.asset))

    async def cancel_upload(self, upload_id: str) -> AssetUpload:
        resp = await self._rpc(
            self._svc.asset_uploads.cancel_upload(
                asset_uploads_pb2.CancelUploadRequest(upload_id=upload_id),
                headers=self._headers(),
            )
        )
        upload = AssetUpload.parse(pb_to_dict(resp.upload))
        assert upload is not None
        return upload

    async def upload_attachment(
        self,
        room_id: str,
        file_path: str | Path,
        *,
        content_type: str = "",
        filename: str | None = None,
    ) -> Asset:
        """Upload a file as a room attachment and return the resulting Asset."""
        path = Path(file_path)
        data = path.read_bytes()
        size = len(data)
        sha = hashlib.sha256(data).hexdigest()
        upload = await self.create_upload(
            room_id, filename or path.name, size, sha, content_type=content_type
        )
        chunk_size = upload.max_chunk_size or 512 * 1024
        offset = upload.committed_offset
        while offset < size:
            end = min(offset + chunk_size, size)
            chunk = data[offset:end]
            chunk_sha = hashlib.sha256(chunk).hexdigest()
            upload = await self.upload_chunk(upload.upload_id, offset, chunk, chunk_sha)
            if upload.committed_offset <= offset:
                raise ChattoError(
                    f"upload stalled at offset {offset} (server reported "
                    f"committed_offset={upload.committed_offset})"
                )
            offset = upload.committed_offset
        upload, asset = await self.complete_upload(upload.upload_id)
        if asset is None:
            raise ChattoError("upload completed but server returned no asset")
        return asset

    # --- Voice calls ----------------------------------------------------

    async def list_active_calls(self) -> list[ActiveCall]:
        resp = await self._rpc(
            self._svc.voice_calls.list_active_calls(
                voice_calls_pb2.ListActiveCallsRequest(), headers=self._headers()
            )
        )
        data = pb_to_dict(resp)
        return [ActiveCall.parse(c) for c in data.get("calls") or []]

    async def get_active_call(self, room_id: str) -> ActiveCall | None:
        resp = await self._rpc(
            self._svc.voice_calls.get_active_call(
                voice_calls_pb2.GetActiveCallRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        raw = pb_to_dict(resp).get("call")
        return ActiveCall.parse(raw) if raw else None

    async def batch_get_active_calls(self, room_ids: list[str]) -> list[ActiveCall]:
        resp = await self._rpc(
            self._svc.voice_calls.batch_get_active_calls(
                voice_calls_pb2.BatchGetActiveCallsRequest(room_ids=room_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [ActiveCall.parse(c) for c in data.get("calls") or []]

    async def join_call(self, room_id: str) -> bool:
        resp = await self._rpc(
            self._svc.voice_calls.join_call(
                voice_calls_pb2.JoinCallRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return resp.joined

    async def leave_call(self, room_id: str) -> bool:
        resp = await self._rpc(
            self._svc.voice_calls.leave_call(
                voice_calls_pb2.LeaveCallRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return resp.left

    async def create_call_token(self, room_id: str) -> str:
        resp = await self._rpc(
            self._svc.voice_calls.create_call_token(
                voice_calls_pb2.CreateCallTokenRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return resp.token

    # --- Permissions ----------------------------------------------------

    async def list_effective_permissions(self, user_id: str) -> list[dict[str, Any]]:
        """List every permission decision that applies to one user.

        Returns raw protobuf JSON dicts (the decision shape is
        server-version-dependent).
        """
        resp = await self._rpc(
            self._svc.permissions.list_effective_permissions(
                permissions_pb2.ListEffectivePermissionsRequest(user_id=user_id),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return list(data.get("permissions") or [])

    # --- Admin: server --------------------------------------------------

    async def admin_get_server_config(self) -> tuple[ServerConfig, ServerProfile]:
        resp = await self._rpc(
            self._svc.admin_server.get_server_config(
                admin_server_pb2.GetServerConfigRequest(),
                headers=self._headers(),
            )
        )
        return (
            ServerConfig.parse(pb_to_dict(resp.config)),
            ServerProfile.parse(pb_to_dict(resp.public_profile)),
        )

    async def admin_update_server_config(
        self,
        *,
        server_name: str | None = None,
        description: str | None = None,
        motd: str | None = None,
        welcome_message: str | None = None,
        registration_admission: AccountCreationPolicy | None = None,
    ) -> tuple[ServerConfig, ServerProfile]:
        req = admin_server_pb2.UpdateServerConfigRequest()
        if server_name is not None:
            req.server_name = server_name
        if description is not None:
            req.description = description
        if motd is not None:
            req.motd = motd
        if welcome_message is not None:
            req.welcome_message = welcome_message
        if registration_admission is not None:
            # Since 0.5.0b27: partial account-creation settings. Server-side
            # mask inference does not see nested message fields, so once
            # ``registration`` participates we send an explicit mask covering
            # every provided field.
            req.registration.admission = registration_admission.value
            paths = [
                name
                for name, value in (
                    ("server_name", server_name),
                    ("description", description),
                    ("motd", motd),
                    ("welcome_message", welcome_message),
                )
                if value is not None
            ]
            paths.append("registration.admission")
            req.update_mask.paths.extend(paths)
        resp = await self._rpc(
            self._svc.admin_server.update_server_config(req, headers=self._headers())
        )
        return (
            ServerConfig.parse(pb_to_dict(resp.config)),
            ServerProfile.parse(pb_to_dict(resp.public_profile)),
        )

    async def admin_upload_server_logo(
        self,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> ServerProfile:
        p = Path(file_path)
        req = admin_server_pb2.UploadServerLogoRequest(
            image=common_pb2.ImageUpload(
                image=p.read_bytes(), filename=p.name, content_type=content_type
            )
        )
        resp = await self._rpc(
            self._svc.admin_server.upload_server_logo(req, headers=self._headers())
        )
        return ServerProfile.parse(pb_to_dict(resp.public_profile))

    async def admin_delete_server_logo(self) -> ServerProfile:
        resp = await self._rpc(
            self._svc.admin_server.delete_server_logo(
                admin_server_pb2.DeleteServerLogoRequest(),
                headers=self._headers(),
            )
        )
        return ServerProfile.parse(pb_to_dict(resp.public_profile))

    async def admin_upload_server_banner(
        self,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> ServerProfile:
        p = Path(file_path)
        req = admin_server_pb2.UploadServerBannerRequest(
            image=common_pb2.ImageUpload(
                image=p.read_bytes(), filename=p.name, content_type=content_type
            )
        )
        resp = await self._rpc(
            self._svc.admin_server.upload_server_banner(req, headers=self._headers())
        )
        return ServerProfile.parse(pb_to_dict(resp.public_profile))

    async def admin_delete_server_banner(self) -> ServerProfile:
        resp = await self._rpc(
            self._svc.admin_server.delete_server_banner(
                admin_server_pb2.DeleteServerBannerRequest(),
                headers=self._headers(),
            )
        )
        return ServerProfile.parse(pb_to_dict(resp.public_profile))

    async def admin_get_server_security_config(self) -> list[str]:
        resp = await self._rpc(
            self._svc.admin_server.get_server_security_config(
                admin_server_pb2.GetServerSecurityConfigRequest(),
                headers=self._headers(),
            )
        )
        return list(resp.blocked_usernames)

    async def admin_update_blocked_usernames(self, usernames: list[str]) -> list[str]:
        resp = await self._rpc(
            self._svc.admin_server.update_blocked_usernames(
                admin_server_pb2.UpdateBlockedUsernamesRequest(blocked_usernames=usernames),
                headers=self._headers(),
            )
        )
        return list(resp.blocked_usernames)

    # --- Admin: neighbors ---------------------------------------------

    async def admin_list_neighbors(self) -> list[Neighbor]:
        """List configured Neighbors. Requires ``server.manage-neighbors``."""
        resp = await self._rpc(
            self._svc.admin_server.list_neighbors(
                admin_server_pb2.ListNeighborsRequest(),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [n for n in (Neighbor.parse(x) for x in data.get("neighbors") or []) if n]

    async def admin_get_neighbor(self, neighbor_id: str) -> Neighbor | None:
        """Get one configured Neighbor. Requires ``server.manage-neighbors``."""
        resp = await self._rpc(
            self._svc.admin_server.get_neighbor(
                admin_server_pb2.GetNeighborRequest(neighbor_id=neighbor_id),
                headers=self._headers(),
            )
        )
        return Neighbor.parse(pb_to_dict(resp).get("neighbor"))

    async def admin_create_neighbor(self, origin: str) -> Neighbor:
        """Advertise one server origin. Requires ``server.manage-neighbors``."""
        resp = await self._rpc(
            self._svc.admin_server.create_neighbor(
                admin_server_pb2.CreateNeighborRequest(origin=origin),
                headers=self._headers(),
            )
        )
        neighbor = Neighbor.parse(pb_to_dict(resp).get("neighbor"))
        assert neighbor is not None
        return neighbor

    async def admin_update_neighbor(self, neighbor_id: str, origin: str, revision: str) -> Neighbor:
        """Change one advertised origin. Requires ``server.manage-neighbors``."""
        resp = await self._rpc(
            self._svc.admin_server.update_neighbor(
                admin_server_pb2.UpdateNeighborRequest(
                    neighbor_id=neighbor_id, origin=origin, revision=revision
                ),
                headers=self._headers(),
            )
        )
        neighbor = Neighbor.parse(pb_to_dict(resp).get("neighbor"))
        assert neighbor is not None
        return neighbor

    async def admin_delete_neighbor(self, neighbor_id: str, revision: str) -> None:
        """Stop advertising one origin. Requires ``server.manage-neighbors``."""
        await self._rpc(
            self._svc.admin_server.delete_neighbor(
                admin_server_pb2.DeleteNeighborRequest(neighbor_id=neighbor_id, revision=revision),
                headers=self._headers(),
            )
        )

    # --- Admin: room layout & sidebar links ---------------------------

    async def admin_list_room_groups(self) -> list[AdminRoomLayoutGroup]:
        resp = await self._rpc(
            self._svc.admin_room_layout.list_room_groups(
                room_layout_pb2.ListRoomGroupsRequest(),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            g
            for g in (AdminRoomLayoutGroup.parse(row) for row in data.get("groups") or [])
            if g is not None
        ]

    async def admin_create_room_group(
        self, name: str, description: str = ""
    ) -> AdminRoomLayoutGroup:
        resp = await self._rpc(
            self._svc.admin_room_layout.create_room_group(
                room_layout_pb2.CreateRoomGroupRequest(name=name, description=description),
                headers=self._headers(),
            )
        )
        group = AdminRoomLayoutGroup.parse(pb_to_dict(resp.group))
        assert group is not None
        return group

    async def admin_update_room_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> AdminRoomLayoutGroup:
        req = room_layout_pb2.UpdateRoomGroupRequest(group_id=group_id)
        if name is not None:
            req.name = name
        if description is not None:
            req.description = description
        resp = await self._rpc(
            self._svc.admin_room_layout.update_room_group(req, headers=self._headers())
        )
        group = AdminRoomLayoutGroup.parse(pb_to_dict(resp.group))
        assert group is not None
        return group

    async def admin_delete_room_group(self, group_id: str) -> bool:
        resp = await self._rpc(
            self._svc.admin_room_layout.delete_room_group(
                room_layout_pb2.DeleteRoomGroupRequest(group_id=group_id),
                headers=self._headers(),
            )
        )
        return resp.deleted

    async def admin_reorder_room_groups(
        self, ordered_group_ids: list[str]
    ) -> list[AdminRoomLayoutGroup]:
        resp = await self._rpc(
            self._svc.admin_room_layout.reorder_room_groups(
                room_layout_pb2.ReorderRoomGroupsRequest(ordered_group_ids=ordered_group_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            g
            for g in (AdminRoomLayoutGroup.parse(row) for row in data.get("groups") or [])
            if g is not None
        ]

    async def admin_move_room_group(
        self, group_id: str, before_group_id: str | None = None
    ) -> list[AdminRoomLayoutGroup]:
        """Move one room group before another (or to the end if omitted)."""
        req = room_layout_pb2.MoveRoomGroupRequest(group_id=group_id)
        if before_group_id is not None:
            req.before_group_id = before_group_id
        resp = await self._rpc(
            self._svc.admin_room_layout.move_room_group(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return [
            g
            for g in (AdminRoomLayoutGroup.parse(row) for row in data.get("groups") or [])
            if g is not None
        ]

    async def admin_move_room_to_group(self, room_id: str, group_id: str) -> Room:
        resp = await self._rpc(
            self._svc.admin_room_layout.move_room_to_group(
                room_layout_pb2.MoveRoomToGroupRequest(room_id=room_id, group_id=group_id),
                headers=self._headers(),
            )
        )
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

    async def admin_reorder_sidebar_items_in_group(
        self,
        group_id: str,
        items: list[tuple[str, str]],
    ) -> AdminRoomLayoutGroup:
        req = room_layout_pb2.ReorderSidebarItemsInGroupRequest(group_id=group_id)
        for kind, item_id in items:
            _layout_item(req.items.add(), kind, item_id)
        resp = await self._rpc(
            self._svc.admin_room_layout.reorder_sidebar_items_in_group(req, headers=self._headers())
        )
        group = AdminRoomLayoutGroup.parse(pb_to_dict(resp.group))
        assert group is not None
        return group

    async def admin_move_sidebar_item(
        self,
        item: tuple[str, str],
        group_id: str,
        before: tuple[str, str] | None = None,
    ) -> AdminRoomLayoutGroup:
        """Move one room or sidebar link to a position in a room group.

        ``item`` is ``(kind, id)`` where kind is ``"room"`` or ``"sidebar_link"``;
        ``before`` is the same tuple for the entry to place ahead of (omit to
        place it last in ``group_id``).
        """
        req = room_layout_pb2.MoveSidebarItemRequest(group_id=group_id)
        _layout_item(req.item, item[0], item[1])
        if before is not None:
            _layout_item(req.before, before[0], before[1])
        resp = await self._rpc(
            self._svc.admin_room_layout.move_sidebar_item(req, headers=self._headers())
        )
        group = AdminRoomLayoutGroup.parse(pb_to_dict(resp.group))
        assert group is not None
        return group

    async def admin_create_sidebar_link(
        self, group_id: str, label: str, url: str
    ) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_room_layout.create_sidebar_link(
                room_layout_pb2.CreateSidebarLinkRequest(group_id=group_id, label=label, url=url),
                headers=self._headers(),
            )
        )
        sl = resp.sidebar_link
        return {"id": sl.id, "label": sl.label, "url": sl.url}

    async def admin_update_sidebar_link(
        self,
        link_id: str,
        *,
        label: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        req = room_layout_pb2.UpdateSidebarLinkRequest(link_id=link_id)
        if label is not None:
            req.label = label
        if url is not None:
            req.url = url
        resp = await self._rpc(
            self._svc.admin_room_layout.update_sidebar_link(req, headers=self._headers())
        )
        sl = resp.sidebar_link
        return {"id": sl.id, "label": sl.label, "url": sl.url}

    async def admin_delete_sidebar_link(self, link_id: str) -> bool:
        resp = await self._rpc(
            self._svc.admin_room_layout.delete_sidebar_link(
                room_layout_pb2.DeleteSidebarLinkRequest(link_id=link_id),
                headers=self._headers(),
            )
        )
        return resp.deleted

    async def admin_move_sidebar_link_to_group(self, link_id: str, group_id: str) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_room_layout.move_sidebar_link_to_group(
                room_layout_pb2.MoveSidebarLinkToGroupRequest(link_id=link_id, group_id=group_id),
                headers=self._headers(),
            )
        )
        sl = resp.sidebar_link
        return {"id": sl.id, "label": sl.label, "url": sl.url}

    # --- Admin: users --------------------------------------------------

    async def admin_list_members(
        self,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[str], Page]:
        """List server member IDs (plus page metadata).

        The server returns member IDs only; hydrate full rows with
        :meth:`admin_batch_get_members`.
        """
        req = admin_members_pb2.ListMembersRequest(search=search)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.admin_users.list_members(req, headers=self._headers()))
        data = pb_to_dict(resp)
        return list(data.get("userIds") or []), Page.parse(data.get("page"))

    async def admin_get_member(
        self,
        *,
        user_id: str | None = None,
        login: str | None = None,
    ) -> dict[str, Any]:
        if bool(user_id) == bool(login):
            raise ValueError("admin_get_member requires exactly one of user_id or login")
        req = admin_members_pb2.GetMemberRequest()
        if user_id:
            req.user_id = user_id
        else:
            assert login is not None
            req.login = login
        resp = await self._rpc(self._svc.admin_users.get_member(req, headers=self._headers()))
        return pb_to_dict(resp)

    async def admin_batch_get_members(self, user_ids: list[str]) -> list[AdminMember]:
        resp = await self._rpc(
            self._svc.admin_users.batch_get_members(
                admin_members_pb2.BatchGetMembersRequest(user_ids=user_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            m
            for m in (AdminMember.parse(row) for row in data.get("members") or [])
            if m is not None
        ]

    async def admin_assign_role(self, user_id: str, role_name: str) -> AdminMember | None:
        resp = await self._rpc(
            self._svc.admin_users.assign_role(
                admin_members_pb2.AssignRoleRequest(user_id=user_id, role_name=role_name),
                headers=self._headers(),
            )
        )
        return AdminMember.parse(pb_to_dict(resp.member))

    async def admin_revoke_role(self, user_id: str, role_name: str) -> AdminMember | None:
        resp = await self._rpc(
            self._svc.admin_users.revoke_role(
                admin_members_pb2.RevokeRoleRequest(user_id=user_id, role_name=role_name),
                headers=self._headers(),
            )
        )
        return AdminMember.parse(pb_to_dict(resp.member))

    async def admin_update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        login: str | None = None,
        bio: str | None = None,
    ) -> tuple[User | None, AdminMember | None]:
        """Update a user's login / display name / bio as a server-admin action.

        The pre-0.5.0b9 ``AdminUserService.UpdateUser`` RPC was removed; admin
        profile edits are now just a privileged
        :meth:`update_user_profile` (``user.manage-accounts`` bypasses the
        username-change cooldown and does not start one), so the second
        returned value is always ``None`` — re-fetch the member row with
        :meth:`admin_get_member` when it is needed.
        """
        user = await self.update_user_profile(
            user_id, display_name=display_name, login=login, bio=bio
        )
        return user, None

    async def admin_change_user_password(self, user_id: str, password: str) -> AdminMember | None:
        resp = await self._rpc(
            self._svc.admin_users.change_user_password(
                admin_members_pb2.ChangeUserPasswordRequest(user_id=user_id, password=password),
                headers=self._headers(),
            )
        )
        return AdminMember.parse(pb_to_dict(resp.member))

    async def admin_clear_username_cooldown(self, user_id: str) -> None:
        await self._rpc(
            self._svc.admin_users.clear_username_cooldown(
                admin_members_pb2.ClearUsernameCooldownRequest(user_id=user_id),
                headers=self._headers(),
            )
        )

    async def admin_delete_user(self, user_id: str) -> None:
        await self._rpc(
            self._svc.admin_users.delete_user(
                admin_members_pb2.DeleteUserRequest(user_id=user_id),
                headers=self._headers(),
            )
        )

    async def admin_set_user_deactivated(self, user_id: str, deactivated: bool) -> AdminMember:
        """Deactivate or reactivate a human account (since 0.5.0b27, requires
        ``user.manage-accounts``). Cannot target your own account or an owner
        account. Deactivation immediately invalidates existing sessions and
        prevents sign-in; reactivation permits new sign-ins but old sessions
        remain invalid. Repeating the current state succeeds unchanged."""
        resp = await self._rpc(
            self._svc.admin_users.set_user_deactivated(
                admin_members_pb2.SetUserDeactivatedRequest(
                    user_id=user_id, deactivated=deactivated
                ),
                headers=self._headers(),
            )
        )
        member = AdminMember.parse(pb_to_dict(resp.member))
        assert member is not None
        return member

    # --- Admin: roles --------------------------------------------------

    async def admin_list_roles(self) -> list[AdminRole]:
        resp = await self._rpc(
            self._svc.admin_roles.list_roles(
                admin_roles_pb2.ListRolesRequest(), headers=self._headers()
            )
        )
        data = pb_to_dict(resp)
        return [
            r for r in (AdminRole.parse(row) for row in data.get("roles") or []) if r is not None
        ]

    async def admin_get_role(self, name: str) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_roles.get_role(
                admin_roles_pb2.GetRoleRequest(name=name), headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    async def admin_create_role(
        self,
        name: str,
        *,
        display_name: str = "",
        description: str = "",
        pingable: bool = False,
    ) -> AdminRole | None:
        resp = await self._rpc(
            self._svc.admin_roles.create_role(
                admin_roles_pb2.CreateRoleRequest(
                    name=name,
                    display_name=display_name,
                    description=description,
                    pingable=pingable,
                ),
                headers=self._headers(),
            )
        )
        return AdminRole.parse(pb_to_dict(resp.role))

    async def admin_update_role(
        self,
        name: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        pingable: bool | None = None,
    ) -> AdminRole | None:
        req = admin_roles_pb2.UpdateRoleRequest(name=name)
        if display_name is not None:
            req.display_name = display_name
        if description is not None:
            req.description = description
        if pingable is not None:
            req.pingable = pingable
        resp = await self._rpc(self._svc.admin_roles.update_role(req, headers=self._headers()))
        return AdminRole.parse(pb_to_dict(resp.role))

    async def admin_delete_role(self, name: str) -> None:
        await self._rpc(
            self._svc.admin_roles.delete_role(
                admin_roles_pb2.DeleteRoleRequest(name=name),
                headers=self._headers(),
            )
        )

    async def admin_reorder_roles(self, role_names: list[str]) -> list[AdminRole]:
        resp = await self._rpc(
            self._svc.admin_roles.reorder_roles(
                admin_roles_pb2.ReorderRolesRequest(role_names=role_names),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            r for r in (AdminRole.parse(row) for row in data.get("roles") or []) if r is not None
        ]

    async def admin_role_list_members(
        self,
        name: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[User], Page]:
        """List a role's explicitly-assigned members (one page)."""
        req = admin_roles_pb2.AdminRoleServiceListMembersRequest(name=name)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.admin_roles.list_members(req, headers=self._headers()))
        data = pb_to_dict(resp)
        members = [
            u for u in (User.parse(row) for row in data.get("members") or []) if u is not None
        ]
        return members, Page.parse(data.get("page"))

    # --- Admin: event log / diagnostics / permissions ----------------

    async def admin_list_events(
        self,
        *,
        event_types: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        req = event_log_pb2.ListEventsRequest()
        if event_types:
            req.event_types.extend(event_types)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.admin_event_log.list_events(req, headers=self._headers()))
        return pb_to_dict(resp)

    async def admin_list_event_types(self) -> list[str]:
        resp = await self._rpc(
            self._svc.admin_event_log.list_event_types(
                event_log_pb2.ListEventTypesRequest(),
                headers=self._headers(),
            )
        )
        return list(resp.event_types)

    async def admin_get_event(self, event_id: str) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_event_log.get_event(
                event_log_pb2.GetEventRequest(event_id=event_id),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    async def admin_get_system_info(self) -> dict[str, Any]:
        from chattolib._pb.chatto.admin.v1 import diagnostics_pb2

        resp = await self._rpc(
            self._svc.admin_diagnostics.get_system_info(
                diagnostics_pb2.GetSystemInfoRequest(),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    async def admin_get_role_permission_matrix(self) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_permissions.get_role_permission_matrix(
                admin_permissions_pb2.GetRolePermissionMatrixRequest(),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    async def admin_list_role_permission_decisions(self, role_name: str) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_permissions.list_role_permission_decisions(
                admin_permissions_pb2.ListRolePermissionDecisionsRequest(role_name=role_name),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    async def admin_get_user_permission_matrix(self, user_id: str) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_permissions.get_user_permission_matrix(
                admin_permissions_pb2.GetUserPermissionMatrixRequest(user_id=user_id),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    async def admin_list_user_permission_decisions(self, user_id: str) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.admin_permissions.list_user_permission_decisions(
                admin_permissions_pb2.ListUserPermissionDecisionsRequest(user_id=user_id),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    # --- Message search -------------------------------------------------

    async def get_search_status(self) -> SearchStatus:
        """Current message-search availability on this server.

        Available even when search is disabled. ``FAILED_PRECONDITION``
        means the operator disabled search; ``UNAVAILABLE`` means the
        search provider is not ready to answer queries yet.
        """
        resp = await self._rpc(
            self._svc.message_search.get_status(
                message_search_pb2.GetStatusRequest(),
                headers=self._headers(),
            )
        )
        return SearchStatus.parse(pb_to_dict(resp))

    async def search_messages(
        self,
        query: str,
        *,
        room_id: str | None = None,
        author_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        has_attachments: bool | None = None,
        order: MessageSearchOrder | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        scope: MessageSearchScope | None = None,
        group_by: MessageSearchGroupBy | None = None,
        root_author_filter: ThreadRootAuthorFilter | None = None,
    ) -> SearchResultsPage:
        """Full-text search over current message bodies you can read.

        ``query`` supports required words, quoted exact phrases, and the
        ``in:``, ``from:``, ``before:``, ``after:``, and ``has:attachment``
        filters. ``group_by=THREAD`` returns one row per matching thread
        (with ``thread_context`` and ``thread_total_count`` populated).
        Scope, grouping, and ordering are part of the cursor: keep them
        identical when paging with ``cursor``. Raises ``ChattoConnectError``
        with ``code='failed_precondition'`` when search is disabled and
        ``code='unavailable'`` while the provider is catching up.
        """
        req = message_search_pb2.SearchMessagesRequest(query=query)
        if room_id is not None:
            req.room_id = room_id
        if author_id is not None:
            req.author_id = author_id
        if created_after is not None:
            req.created_after.CopyFrom(_timestamp_pb(created_after))
        if created_before is not None:
            req.created_before.CopyFrom(_timestamp_pb(created_before))
        if has_attachments is not None:
            req.has_attachments = has_attachments
        if order is not None:
            req.order = message_search_pb2.MessageSearchOrder.Value(order.value)
        if page_size is not None:
            req.page_size = page_size
        if cursor is not None:
            req.cursor = cursor
        if scope is not None:
            req.scope = message_search_pb2.MessageSearchScope.Value(scope.value)
        if group_by is not None:
            req.group_by = message_search_pb2.MessageSearchGroupBy.Value(group_by.value)
        if root_author_filter is not None:
            req.root_author_filter = threads_pb2.ThreadRootAuthorFilter.Value(
                root_author_filter.value
            )
        resp = await self._rpc(
            self._svc.message_search.search_messages(req, headers=self._headers())
        )
        return SearchResultsPage.parse(pb_to_dict(resp))

    # --- Read state ------------------------------------------------------

    async def get_room_read_state(self, room_id: str) -> RoomReadState | None:
        resp = await self._rpc(
            self._svc.rooms.get_room_read_state(
                read_state_pb2.GetRoomReadStateRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return RoomReadState.parse(pb_to_dict(resp.state))

    async def batch_get_room_read_states(self, room_ids: list[str]) -> list[RoomReadState]:
        resp = await self._rpc(
            self._svc.rooms.batch_get_room_read_states(
                read_state_pb2.BatchGetRoomReadStatesRequest(room_ids=room_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            s
            for s in (RoomReadState.parse(row) for row in data.get("states") or [])
            if s is not None
        ]

    async def get_thread_read_state(
        self, room_id: str, thread_root_event_id: str
    ) -> ThreadReadState | None:
        resp = await self._rpc(
            self._svc.threads.get_thread_read_state(
                read_state_pb2.GetThreadReadStateRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )
        return ThreadReadState.parse(pb_to_dict(resp.state))

    async def batch_get_thread_read_states(
        self, targets: list[tuple[str, str]]
    ) -> list[ThreadReadState]:
        """Thread read states for (room_id, thread_root_event_id) pairs."""
        req = read_state_pb2.BatchGetThreadReadStatesRequest()
        for room_id, thread_root_event_id in targets:
            req.targets.add(room_id=room_id, thread_root_event_id=thread_root_event_id)
        resp = await self._rpc(
            self._svc.threads.batch_get_thread_read_states(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return [
            s
            for s in (ThreadReadState.parse(row) for row in data.get("states") or [])
            if s is not None
        ]

    # --- Messages: extras -------------------------------------------------

    async def list_reaction_users(
        self,
        room_id: str,
        message_event_id: str,
        emoji: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[str], Page]:
        """User IDs who added ``emoji`` to a message (ordered by user ID).

        Use :meth:`batch_get_users` to hydrate profiles.
        """
        req = reactions_pb2.ListReactionUsersRequest(
            room_id=room_id, message_event_id=message_event_id, emoji=emoji
        )
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.messages.list_reaction_users(req, headers=self._headers()))
        data = pb_to_dict(resp)
        return list(data.get("userIds") or []), Page.parse(data.get("page"))

    async def set_attachment_description(
        self, room_id: str, event_id: str, attachment_id: str, description: str
    ) -> Message:
        """Set or clear (empty string) one attachment's alt description."""
        resp = await self._rpc(
            self._svc.messages.set_attachment_description(
                messages_pb2.SetAttachmentDescriptionRequest(
                    room_id=room_id,
                    event_id=event_id,
                    attachment_id=attachment_id,
                    description=description,
                ),
                headers=self._headers(),
            )
        )
        message = Message.parse(pb_to_dict(resp.message))
        assert message is not None
        return message

    # --- Threads: extras --------------------------------------------------

    async def list_thread_participants(
        self,
        room_id: str,
        thread_root_event_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[str], Page]:
        """Distinct authors of non-retracted replies in a thread."""
        req = threads_pb2.ListThreadParticipantsRequest(
            room_id=room_id, thread_root_event_id=thread_root_event_id
        )
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(
            self._svc.threads.list_thread_participants(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return list(data.get("userIds") or []), Page.parse(data.get("page"))

    # --- Server -----------------------------------------------------------

    async def get_server_profile(self) -> ServerProfile:
        """Public server profile for an authenticated caller."""
        resp = await self._rpc(
            self._svc.server.get_server_profile(
                server_state_pb2.GetServerProfileRequest(),
                headers=self._headers(),
            )
        )
        return ServerProfile.parse(pb_to_dict(resp.profile))

    # --- Users ------------------------------------------------------------

    async def list_users(
        self,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[DirectoryMember], Page]:
        """User directory page, oldest account first."""
        req = user_service_pb2.ListUsersRequest(search=search)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.user.list_users(req, headers=self._headers()))
        data = pb_to_dict(resp)
        users = [
            u
            for u in (DirectoryMember.parse(row) for row in data.get("users") or [])
            if u is not None
        ]
        return users, Page.parse(data.get("page"))

    async def batch_get_users(self, user_ids: list[str]) -> list[DirectoryMember]:
        """Directory rows for several user IDs; unknown IDs are omitted."""
        resp = await self._rpc(
            self._svc.user.batch_get_users(
                user_service_pb2.BatchGetUsersRequest(user_ids=user_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            u
            for u in (DirectoryMember.parse(row) for row in data.get("users") or [])
            if u is not None
        ]

    async def upload_avatar(
        self,
        user_id: str,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> User:
        """Upload and set one user's avatar (self, or managed accounts)."""
        p = Path(file_path)
        req = user_service_pb2.UploadAvatarRequest(
            user_id=user_id,
            image=common_pb2.ImageUpload(
                image=p.read_bytes(), filename=p.name, content_type=content_type
            ),
        )
        resp = await self._rpc(self._svc.user.upload_avatar(req, headers=self._headers()))
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

    async def delete_avatar(self, user_id: str) -> User:
        resp = await self._rpc(
            self._svc.user.delete_avatar(
                user_service_pb2.DeleteAvatarRequest(user_id=user_id),
                headers=self._headers(),
            )
        )
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

    # --- My account: password, email, settings, identities, lifecycle -----

    async def change_password(self, password: str, current_password: str = "") -> User:
        """Set or change the authenticated account's password.

        ``current_password`` is required when the account already has a
        password and omitted when adding the first one.
        """
        req = account_pb2.ChangePasswordRequest(password=password)
        if current_password:
            req.current_password = current_password
        resp = await self._rpc(self._svc.account.change_password(req, headers=self._headers()))
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

    async def list_verified_emails(self, expected_user_id: str) -> list[VerifiedEmail]:
        resp = await self._rpc(
            self._svc.account.list_verified_emails(
                account_pb2.ListVerifiedEmailsRequest(expected_user_id=expected_user_id),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [VerifiedEmail.parse(e) for e in data.get("verifiedEmails") or []]

    async def request_email_verification(self, email: str, expected_user_id: str) -> None:
        """Send a six-digit verification code to a new email address."""
        await self._rpc(
            self._svc.account.request_email_verification(
                account_pb2.RequestEmailVerificationRequest(
                    email=email, expected_user_id=expected_user_id
                ),
                headers=self._headers(),
            )
        )

    async def confirm_email_verification(
        self, email: str, code: str, expected_user_id: str
    ) -> list[VerifiedEmail]:
        resp = await self._rpc(
            self._svc.account.confirm_email_verification(
                account_pb2.ConfirmEmailVerificationRequest(
                    email=email, code=code, expected_user_id=expected_user_id
                ),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [VerifiedEmail.parse(e) for e in data.get("verifiedEmails") or []]

    async def set_primary_email(self, email: str, expected_user_id: str) -> list[VerifiedEmail]:
        resp = await self._rpc(
            self._svc.account.set_primary_email(
                account_pb2.SetPrimaryEmailRequest(email=email, expected_user_id=expected_user_id),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [VerifiedEmail.parse(e) for e in data.get("verifiedEmails") or []]

    async def get_settings(self) -> UserSettings:
        """The authenticated user's display preferences."""
        resp = await self._rpc(
            self._svc.account.get_settings(
                account_pb2.GetSettingsRequest(), headers=self._headers()
            )
        )
        return UserSettings.parse(pb_to_dict(resp.settings))

    async def list_external_identities(
        self,
    ) -> tuple[list[ExternalIdentityProvider], list[LinkedExternalIdentity]]:
        """Configured providers and identities linked to this account."""
        resp = await self._rpc(
            self._svc.account.list_external_identities(
                account_pb2.ListExternalIdentitiesRequest(), headers=self._headers()
            )
        )
        data = pb_to_dict(resp)
        providers = [ExternalIdentityProvider.parse(p) for p in data.get("providers") or []]
        linked = [LinkedExternalIdentity.parse(x) for x in data.get("linkedIdentities") or []]
        return providers, linked

    async def start_external_identity_link(
        self,
        provider_id: str,
        *,
        redirect_path: str = "",
        current_password: str = "",
    ) -> str:
        """Begin linking a provider; returns the browser start URL."""
        req = account_pb2.StartExternalIdentityLinkRequest(provider_id=provider_id)
        if redirect_path:
            req.redirect_path = redirect_path
        if current_password:
            req.current_password = current_password
        resp = await self._rpc(
            self._svc.account.start_external_identity_link(req, headers=self._headers())
        )
        return resp.start_url

    async def disconnect_external_identity(
        self, subject_hash: str, *, current_password: str = ""
    ) -> None:
        req = account_pb2.DisconnectExternalIdentityRequest(subject_hash=subject_hash)
        if current_password:
            req.current_password = current_password
        await self._rpc(
            self._svc.account.disconnect_external_identity(req, headers=self._headers())
        )

    async def request_account_deletion(self) -> str:
        """Get the short-lived confirmation token for account deletion."""
        resp = await self._rpc(
            self._svc.account.request_account_deletion(
                account_pb2.RequestAccountDeletionRequest(), headers=self._headers()
            )
        )
        return resp.confirmation_token

    async def delete_my_account(self, confirmation_token: str) -> None:
        """Permanently delete the authenticated account. Irreversible."""
        await self._rpc(
            self._svc.account.delete_my_account(
                account_pb2.DeleteMyAccountRequest(confirmation_token=confirmation_token),
                headers=self._headers(),
            )
        )

    # --- Viewer: privileged mode ------------------------------------------

    async def activate_privileged_mode(self) -> dict[str, Any]:
        """Elevate entitled permissions for a fixed window (humans only)."""
        resp = await self._rpc(
            self._svc.viewer.activate_privileged_mode(
                viewer_pb2.ActivatePrivilegedModeRequest(), headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    async def deactivate_privileged_mode(self) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.viewer.deactivate_privileged_mode(
                viewer_pb2.DeactivatePrivilegedModeRequest(), headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    # --- Push ---------------------------------------------------------------

    async def send_test_notification(self) -> None:
        """Send a test Web Push notification to this account's subscriptions."""
        await self._rpc(
            self._svc.push.send_test_notification(
                push_notifications_pb2.SendTestNotificationRequest(),
                headers=self._headers(),
            )
        )

    # --- Voice calls ---------------------------------------------------------

    async def list_call_participants(self, room_id: str) -> list[ActiveCallParticipant]:
        resp = await self._rpc(
            self._svc.voice_calls.list_call_participants(
                voice_calls_pb2.ListCallParticipantsRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [ActiveCallParticipant.parse(p) for p in data.get("participants") or []]

    async def create_call_media_publisher_token(
        self, room_id: str, kind: CallMediaPublisherKind
    ) -> dict[str, Any]:
        """Native companion publisher credential (token, e2ee_key, call_id)."""
        resp = await self._rpc(
            self._svc.voice_calls.create_call_media_publisher_token(
                voice_calls_pb2.CreateCallMediaPublisherTokenRequest(
                    room_id=room_id,
                    kind=voice_calls_pb2.CallMediaPublisherKind.Value(kind.value),
                ),
                headers=self._headers(),
            )
        )
        return pb_to_dict(resp)

    # --- Bots ---------------------------------------------------------------

    async def list_bots(
        self,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[BotAccount], Page]:
        """Bots visible to the caller (owners see their own; managers all)."""
        req = bots_pb2.ListBotsRequest(search=search)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.bots.list_bots(req, headers=self._headers()))
        data = pb_to_dict(resp)
        bots = [
            b for b in (BotAccount.parse(row) for row in data.get("bots") or []) if b is not None
        ]
        return bots, Page.parse(data.get("page"))

    async def get_bot(self, bot_user_id: str) -> BotAccount | None:
        resp = await self._rpc(
            self._svc.bots.get_bot(
                bots_pb2.GetBotRequest(bot_user_id=bot_user_id),
                headers=self._headers(),
            )
        )
        return BotAccount.parse(pb_to_dict(resp.bot))

    async def batch_get_bots(self, bot_user_ids: list[str]) -> list[BotAccount]:
        resp = await self._rpc(
            self._svc.bots.batch_get_bots(
                bots_pb2.BatchGetBotsRequest(bot_user_ids=bot_user_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            b for b in (BotAccount.parse(row) for row in data.get("bots") or []) if b is not None
        ]

    async def create_bot(
        self, login: str, display_name: str, *, api_key_name: str | None = None
    ) -> tuple[BotAccount, str, BotApiKey]:
        """Create a bot owned by the authenticated human. Requires bot.create.

        Returns (bot, api_key, api_key_metadata). ``api_key`` is shown once.
        """
        req = bots_pb2.CreateBotRequest(login=login, display_name=display_name)
        if api_key_name is not None:
            req.api_key_name = api_key_name
        resp = await self._rpc(self._svc.bots.create_bot(req, headers=self._headers()))
        bot = BotAccount.parse(pb_to_dict(resp.bot))
        assert bot is not None
        meta = BotApiKey.parse(pb_to_dict(resp.api_key_metadata))
        return bot, resp.api_key, meta

    async def delete_bot(self, bot_user_id: str) -> bool:
        resp = await self._rpc(
            self._svc.bots.delete_bot(
                bots_pb2.DeleteBotRequest(bot_user_id=bot_user_id),
                headers=self._headers(),
            )
        )
        return resp.deleted

    async def create_bot_api_key(
        self, bot_user_id: str, name: str
    ) -> tuple[BotAccount, str, BotApiKey]:
        """Issue a named API key. ``api_key`` is shown once."""
        resp = await self._rpc(
            self._svc.bots.create_bot_api_key(
                bots_pb2.CreateBotApiKeyRequest(bot_user_id=bot_user_id, name=name),
                headers=self._headers(),
            )
        )
        bot = BotAccount.parse(pb_to_dict(resp.bot))
        assert bot is not None
        meta = BotApiKey.parse(pb_to_dict(resp.api_key_metadata))
        return bot, resp.api_key, meta

    async def revoke_bot_api_key(self, bot_user_id: str, key_id: str) -> BotAccount:
        resp = await self._rpc(
            self._svc.bots.revoke_bot_api_key(
                bots_pb2.RevokeBotApiKeyRequest(bot_user_id=bot_user_id, key_id=key_id),
                headers=self._headers(),
            )
        )
        bot = BotAccount.parse(pb_to_dict(resp.bot))
        assert bot is not None
        return bot

    async def create_bot_incoming_webhook(
        self, bot_user_id: str, name: str
    ) -> tuple[BotAccount, str]:
        """Create a named incoming webhook. Returns (bot, webhook_url-once)."""
        resp = await self._rpc(
            self._svc.bots.create_bot_incoming_webhook(
                bots_pb2.CreateBotIncomingWebhookRequest(bot_user_id=bot_user_id, name=name),
                headers=self._headers(),
            )
        )
        bot = BotAccount.parse(pb_to_dict(resp.bot))
        assert bot is not None
        return bot, resp.webhook_url

    async def revoke_bot_incoming_webhook(self, bot_user_id: str, webhook_id: str) -> BotAccount:
        resp = await self._rpc(
            self._svc.bots.revoke_bot_incoming_webhook(
                bots_pb2.RevokeBotIncomingWebhookRequest(
                    bot_user_id=bot_user_id, webhook_id=webhook_id
                ),
                headers=self._headers(),
            )
        )
        bot = BotAccount.parse(pb_to_dict(resp.bot))
        assert bot is not None
        return bot

    async def reassign_bot_owner(self, bot_user_id: str, owner_user_id: str) -> BotAccount:
        resp = await self._rpc(
            self._svc.bots.reassign_bot_owner(
                bots_pb2.ReassignBotOwnerRequest(
                    bot_user_id=bot_user_id, owner_user_id=owner_user_id
                ),
                headers=self._headers(),
            )
        )
        bot = BotAccount.parse(pb_to_dict(resp.bot))
        assert bot is not None
        return bot

    async def list_bot_outbound_webhooks(self, bot_user_id: str) -> list[BotOutboundWebhook]:
        resp = await self._rpc(
            self._svc.bots.list_bot_outbound_webhooks(
                bots_pb2.ListBotOutboundWebhooksRequest(bot_user_id=bot_user_id),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [BotOutboundWebhook.parse(w) for w in data.get("webhooks") or []]

    async def get_bot_outbound_webhook(
        self, bot_user_id: str, webhook_id: str
    ) -> BotOutboundWebhook | None:
        resp = await self._rpc(
            self._svc.bots.get_bot_outbound_webhook(
                bots_pb2.GetBotOutboundWebhookRequest(
                    bot_user_id=bot_user_id, webhook_id=webhook_id
                ),
                headers=self._headers(),
            )
        )
        return BotOutboundWebhook.parse(pb_to_dict(resp.webhook))

    async def create_bot_outbound_webhook(
        self,
        bot_user_id: str,
        url: str,
        name: str,
        *,
        enabled: bool = True,
        authorization: str = "",
    ) -> tuple[BotOutboundWebhook, str]:
        """Create an outbound webhook. Returns (webhook, signing_secret-once)."""
        resp = await self._rpc(
            self._svc.bots.create_bot_outbound_webhook(
                bots_pb2.CreateBotOutboundWebhookRequest(
                    bot_user_id=bot_user_id,
                    url=url,
                    authorization=authorization,
                    enabled=enabled,
                    name=name,
                ),
                headers=self._headers(),
            )
        )
        webhook = BotOutboundWebhook.parse(pb_to_dict(resp.webhook))
        assert webhook is not None
        return webhook, resp.signing_secret

    async def update_bot_outbound_webhook(
        self,
        bot_user_id: str,
        webhook_id: str,
        *,
        enabled: bool | None = None,
        url: str | None = None,
        authorization: str | None = None,
    ) -> BotOutboundWebhook:
        req = bots_pb2.UpdateBotOutboundWebhookRequest(
            bot_user_id=bot_user_id, webhook_id=webhook_id
        )
        fields: list[str] = []
        if enabled is not None:
            req.enabled = enabled
            fields.append("enabled")
        if url is not None:
            req.url = url
            fields.append("url")
        if authorization is not None:
            req.authorization = authorization
            fields.append("authorization")
        if fields:
            req.update_mask.paths.extend(fields)
        resp = await self._rpc(
            self._svc.bots.update_bot_outbound_webhook(req, headers=self._headers())
        )
        webhook = BotOutboundWebhook.parse(pb_to_dict(resp.webhook))
        assert webhook is not None
        return webhook

    async def revoke_bot_outbound_webhook(self, bot_user_id: str, webhook_id: str) -> None:
        await self._rpc(
            self._svc.bots.revoke_bot_outbound_webhook(
                bots_pb2.RevokeBotOutboundWebhookRequest(
                    bot_user_id=bot_user_id, webhook_id=webhook_id
                ),
                headers=self._headers(),
            )
        )

    async def list_bot_webhook_failures(
        self,
        bot_user_id: str,
        webhook_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> tuple[list[BotWebhookFailure], str]:
        """Retained outbound delivery failures, oldest first.

        Returns (failures, next_cursor); empty ``next_cursor`` means done.
        """
        req = bots_pb2.ListBotWebhookFailuresRequest(bot_user_id=bot_user_id, webhook_id=webhook_id)
        if page_size is not None:
            req.page_size = page_size
        if cursor is not None:
            req.cursor = cursor
        resp = await self._rpc(
            self._svc.bots.list_bot_webhook_failures(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return (
            [BotWebhookFailure.parse(f) for f in data.get("failures") or []],
            data.get("nextCursor", ""),
        )

    # --- External identity auth (public, capability-token flows) ----------

    async def get_pending_external_identity(self, token: str) -> PendingExternalIdentity | None:
        resp = await self._rpc(
            self._svc.external_identity_auth.get_pending_external_identity(
                external_identity_auth_pb2.GetPendingExternalIdentityRequest(token=token),
                headers=self._headers(),
            )
        )
        return PendingExternalIdentity.parse(pb_to_dict(resp.pending))

    async def create_external_identity_account(
        self, token: str, login: str, display_name: str = "", *, invitation_code: str = ""
    ) -> dict[str, Any]:
        """Create a passwordless account from a pending provider identity.

        Since 0.5.0b27: ``login`` is ignored when the pending flow reports
        ``choose_username`` as provider-managed, and ``invitation_code`` is
        required on invite-only servers when the flow has no valid invitation
        (a supplied code replaces the flow's invitation for this attempt; an
        invalid code fails without fallback and is consumed only on success).
        """
        req = external_identity_auth_pb2.CreateExternalIdentityAccountRequest(
            token=token, login=login
        )
        if display_name:
            req.display_name = display_name
        if invitation_code:
            req.invitation_code = invitation_code
        resp = await self._rpc(
            self._svc.external_identity_auth.create_external_identity_account(
                req, headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    async def confirm_external_identity_link(self, token: str) -> LinkedExternalIdentity | None:
        resp = await self._rpc(
            self._svc.external_identity_auth.confirm_external_identity_link(
                external_identity_auth_pb2.ConfirmExternalIdentityLinkRequest(token=token),
                headers=self._headers(),
            )
        )
        return LinkedExternalIdentity.parse(pb_to_dict(resp.linked_identity))

    async def cancel_external_identity_flow(self, token: str) -> None:
        await self._rpc(
            self._svc.external_identity_auth.cancel_external_identity_flow(
                external_identity_auth_pb2.CancelExternalIdentityFlowRequest(token=token),
                headers=self._headers(),
            )
        )

    # --- Admin: permission writes ------------------------------------------

    async def admin_get_role_permission_tier_matrix(
        self,
        *,
        scope_kind: PermissionScopeKind = PermissionScopeKind.SERVER,
        scope_id: str = "",
    ) -> dict[str, Any]:
        req = admin_permissions_pb2.GetRolePermissionTierMatrixRequest()
        if scope_kind != PermissionScopeKind.SERVER or scope_id:
            req.scope.CopyFrom(_permission_scope_pb(scope_kind, scope_id))
        resp = await self._rpc(
            self._svc.admin_permissions.get_role_permission_tier_matrix(
                req, headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    async def admin_explain_permissions(
        self,
        user_id: str,
        *,
        room_id: str = "",
        scope_kind: PermissionScopeKind | None = None,
        scope_id: str = "",
    ) -> list[dict[str, Any]]:
        req = admin_permissions_pb2.ExplainPermissionsRequest(user_id=user_id)
        if room_id:
            req.room_id = room_id
        if scope_kind is not None:
            req.scope.CopyFrom(_permission_scope_pb(scope_kind, scope_id))
        resp = await self._rpc(
            self._svc.admin_permissions.explain_permissions(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return list(data.get("explanations") or [])

    async def admin_set_role_permission(
        self,
        role_name: str,
        permission: str,
        decision: PermissionDecision,
        *,
        scope_kind: PermissionScopeKind = PermissionScopeKind.SERVER,
        scope_id: str = "",
    ) -> dict[str, Any]:
        req = admin_permissions_pb2.SetRolePermissionRequest(
            role_name=role_name,
            permission=permission,
            decision=admin_permissions_pb2.PermissionDecision.Value(decision.value),
        )
        if scope_kind != PermissionScopeKind.SERVER or scope_id:
            req.scope.CopyFrom(_permission_scope_pb(scope_kind, scope_id))
        resp = await self._rpc(
            self._svc.admin_permissions.set_role_permission(req, headers=self._headers())
        )
        return pb_to_dict(resp)

    async def admin_set_user_permission(
        self,
        user_id: str,
        permission: str,
        decision: PermissionDecision,
        *,
        scope_kind: PermissionScopeKind = PermissionScopeKind.SERVER,
        scope_id: str = "",
    ) -> dict[str, Any]:
        req = admin_permissions_pb2.SetUserPermissionRequest(
            user_id=user_id,
            permission=permission,
            decision=admin_permissions_pb2.PermissionDecision.Value(decision.value),
        )
        if scope_kind != PermissionScopeKind.SERVER or scope_id:
            req.scope.CopyFrom(_permission_scope_pb(scope_kind, scope_id))
        resp = await self._rpc(
            self._svc.admin_permissions.set_user_permission(req, headers=self._headers())
        )
        return pb_to_dict(resp)

    # --- Admin: registration codes ---------------------------------------

    async def admin_list_invitation_codes(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> tuple[list[InvitationCode], Page]:
        req = admin_invitations_pb2.ListInvitationCodesRequest()
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(
            self._svc.admin_invitation_codes.list_invitation_codes(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return (
            [
                code
                for code in (InvitationCode.parse(row) for row in data.get("invitationCodes") or [])
                if code is not None
            ],
            Page.parse(data.get("page")),
        )

    async def admin_get_invitation_code(self, code_id: str) -> InvitationCode | None:
        resp = await self._rpc(
            self._svc.admin_invitation_codes.get_invitation_code(
                admin_invitations_pb2.GetInvitationCodeRequest(id=code_id),
                headers=self._headers(),
            )
        )
        return InvitationCode.parse(pb_to_dict(resp.invitation_code))

    async def admin_create_invitation_code(
        self, *, expires_at: datetime | None = None, note: str = ""
    ) -> InvitationCode:
        """Create a single-use registration code. Not idempotent: retrying
        creates another code. Every code is single-use even when expiry is
        omitted. ``note`` is an optional manager-only note (max 250 chars)."""
        req = admin_invitations_pb2.CreateInvitationCodeRequest()
        if expires_at is not None:
            req.expires_at.CopyFrom(_timestamp_pb(expires_at))
        if note:
            req.note = note
        resp = await self._rpc(
            self._svc.admin_invitation_codes.create_invitation_code(req, headers=self._headers())
        )
        code = InvitationCode.parse(pb_to_dict(resp.invitation_code))
        assert code is not None
        return code

    async def admin_revoke_invitation_code(self, code_id: str) -> InvitationCode:
        resp = await self._rpc(
            self._svc.admin_invitation_codes.revoke_invitation_code(
                admin_invitations_pb2.RevokeInvitationCodeRequest(id=code_id),
                headers=self._headers(),
            )
        )
        code = InvitationCode.parse(pb_to_dict(resp.invitation_code))
        assert code is not None
        return code

    # --- Admin: OAuth clients -------------------------------------------------

    async def admin_list_oauth_clients(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> tuple[list[OAuthClient], Page]:
        req = admin_oauth_clients_pb2.ListOAuthClientsRequest()
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(
            self._svc.admin_oauth_clients.list_oauth_clients(req, headers=self._headers())
        )
        data = pb_to_dict(resp)
        return (
            [
                c
                for c in (OAuthClient.parse(row) for row in data.get("oauthClients") or [])
                if c is not None
            ],
            Page.parse(data.get("page")),
        )

    async def admin_get_oauth_client(self, client_id: str) -> OAuthClient | None:
        resp = await self._rpc(
            self._svc.admin_oauth_clients.get_oauth_client(
                admin_oauth_clients_pb2.GetOAuthClientRequest(client_id=client_id),
                headers=self._headers(),
            )
        )
        return OAuthClient.parse(pb_to_dict(resp.oauth_client))

    async def admin_update_oauth_client_policy(
        self, client_id: str, policy: OauthClientPolicy
    ) -> OAuthClient:
        resp = await self._rpc(
            self._svc.admin_oauth_clients.update_oauth_client_policy(
                admin_oauth_clients_pb2.UpdateOAuthClientPolicyRequest(
                    client_id=client_id,
                    policy=admin_oauth_clients_pb2.OauthClientPolicy.Value(policy.value),
                ),
                headers=self._headers(),
            )
        )
        client = OAuthClient.parse(pb_to_dict(resp.oauth_client))
        assert client is not None
        return client

    # --- Auth: setup & push cleanup (public, unauthenticated) --------------

    async def complete_server_setup(
        self,
        server_name: str,
        login: str,
        display_name: str,
        password: str,
        *,
        description: str = "",
    ) -> None:
        """Create the first owner on a fresh server (public until used)."""
        req = setup_pb2.CompleteSetupRequest(
            server_name=server_name, login=login, display_name=display_name, password=password
        )
        if description:
            req.description = description
        await self._rpc(self._svc.setup.complete_setup(req, headers=self._headers()))

    async def delete_push_subscription(self, endpoint: str, auth: str, cleanup_token: str) -> None:
        """Capability-authenticated cleanup of a browser push subscription."""
        await self._rpc(
            self._svc.push_cleanup.delete_subscription(
                push_subscription_cleanup_pb2.DeleteSubscriptionRequest(
                    endpoint=endpoint, auth=auth, cleanup_token=cleanup_token
                ),
                headers=self._headers(),
            )
        )

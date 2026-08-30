"""Main async client for the Chatto Connect API.

Chatto migrated from GraphQL to a protobuf-first Connect API in v0.4.x
(see ADR-042). The client speaks Connect binary protobuf via the official
``connectrpc`` Python package and the generated service stubs under
``chattolib._pb`` for all request/response operations. Realtime events
live in ``chattolib.realtime``.
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

# ConnectError isn't re-exported publicly by connectrpc.__init__; import from
# its submodule so the top-level import path stays clean for callers.
from connectrpc.errors import ConnectError  # noqa: E402

from chattolib._pb.chatto.admin.v1 import (
    event_log_pb2,
    room_layout_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    members_pb2 as admin_members_pb2,
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
    common_pb2,
    link_previews_pb2,
    member_directory_pb2,
    messages_pb2,
    notification_preferences_pb2,
    notifications_pb2,
    pagination_pb2,
    presence_pb2,
    push_notifications_pb2,
    reactions_pb2,
    read_state_pb2,
    roles_pb2,
    room_directory_pb2,
    room_timeline_pb2,
    rooms_pb2,
    server_state_pb2,
    threads_pb2,
    user_status_pb2,
    viewer_pb2,
    voice_calls_pb2,
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
    ActiveCall,
    AdminMember,
    AdminRole,
    AdminRoomLayoutGroup,
    AdminRoomLayoutItemKind,
    Asset,
    AssetUpload,
    DirectoryMember,
    FollowedThread,
    FollowedThreadsPage,
    ImageTransformOptions,
    LinkPreview,
    Message,
    Neighbor,
    NotificationLevel,
    NotificationOccurrence,
    NotificationOccurrencesPage,
    NotificationPolicy,
    NotificationPreference,
    Page,
    PinnedMessage,
    PinnedMessagesPage,
    PresenceStatus,
    Role,
    Room,
    RoomBan,
    RoomDirectoryScope,
    RoomGroup,
    RoomThreadingMode,
    RoomWithViewerState,
    ServerConfig,
    ServerLogin,
    ServerProfile,
    ServerRuntimeConfig,
    TimeFormat,
    TimelinePage,
    User,
    UserSettings,
    ViewerUser,
    format_datetime,
    parse_datetime,
)

RES = TypeVar("RES")


def _page_pb(limit: int | None, offset: int | None) -> pagination_pb2.PageRequest | None:
    if limit is None and offset is None:
        return None
    return pagination_pb2.PageRequest(limit=limit or 0, offset=offset or 0)


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

    async def update_profile(
        self,
        *,
        display_name: str | None = None,
        login: str | None = None,
    ) -> User:
        req = account_pb2.UpdateProfileRequest()
        if display_name is not None:
            req.display_name = display_name
        if login is not None:
            req.login = login
        resp = await self._rpc(self._svc.account.update_profile(req, headers=self._headers()))
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

    async def upload_avatar(
        self,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> User:
        p = Path(file_path)
        req = account_pb2.UploadAvatarRequest(
            image=common_pb2.ImageUpload(
                image=p.read_bytes(),
                filename=p.name,
                content_type=content_type,
            )
        )
        resp = await self._rpc(self._svc.account.upload_avatar(req, headers=self._headers()))
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

    async def delete_avatar(self) -> User:
        resp = await self._rpc(
            self._svc.account.delete_avatar(
                account_pb2.DeleteAvatarRequest(), headers=self._headers()
            )
        )
        user = User.parse(pb_to_dict(resp.user))
        assert user is not None
        return user

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

    async def update_presence(
        self,
        status: PresenceStatus,
        *,
        user_selected: bool = True,
    ) -> PresenceStatus:
        if status in (PresenceStatus.UNSPECIFIED, PresenceStatus.OFFLINE):
            raise ValueError(
                "UNSPECIFIED and OFFLINE cannot be set as presence status; "
                "stop refreshing to go offline"
            )
        req = presence_pb2.UpdatePresenceRequest(status=status.value, user_selected=user_selected)
        resp = await self._rpc(self._svc.account.update_presence(req, headers=self._headers()))
        name = presence_pb2.PresenceStatus.Name(resp.status)
        return PresenceStatus(name)

    async def update_custom_status(
        self,
        emoji: str,
        text: str,
        *,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        req = user_status_pb2.UpdateCustomStatusRequest(emoji=emoji, text=text)
        if expires_at is not None:
            req.expires_at.CopyFrom(_timestamp_pb(expires_at))
        resp = await self._rpc(self._svc.account.update_custom_status(req, headers=self._headers()))
        return pb_to_dict(resp)

    async def delete_custom_status(self) -> dict[str, Any]:
        resp = await self._rpc(
            self._svc.account.delete_custom_status(
                user_status_pb2.DeleteCustomStatusRequest(), headers=self._headers()
            )
        )
        return pb_to_dict(resp)

    # --- Users ----------------------------------------------------------

    async def list_users(
        self,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[DirectoryMember], Page]:
        req = member_directory_pb2.ListUsersRequest(search=search)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.users.list_users(req, headers=self._headers()))
        data = pb_to_dict(resp)
        users = [
            u
            for u in (DirectoryMember.parse(row) for row in data.get("users") or [])
            if u is not None
        ]
        return users, Page.parse(data.get("page"))

    async def get_user(
        self, *, user_id: str | None = None, login: str | None = None
    ) -> DirectoryMember | None:
        if bool(user_id) == bool(login):
            raise ValueError("get_user requires exactly one of user_id or login")
        req = member_directory_pb2.GetUserRequest()
        if user_id:
            req.user_id = user_id
        else:
            assert login is not None
            req.login = login
        resp = await self._rpc(self._svc.users.get_user(req, headers=self._headers()))
        return DirectoryMember.parse(pb_to_dict(resp.user))

    async def batch_get_users(self, user_ids: list[str]) -> list[DirectoryMember]:
        resp = await self._rpc(
            self._svc.users.batch_get_users(
                member_directory_pb2.BatchGetUsersRequest(user_ids=user_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            u
            for u in (DirectoryMember.parse(row) for row in data.get("users") or [])
            if u is not None
        ]

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
        resp = await self._rpc(self._svc.rooms.update_room(req, headers=self._headers()))
        room = Room.parse(pb_to_dict(resp.room))
        assert room is not None
        return room

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

    async def leave_room(self, room_id: str) -> bool:
        resp = await self._rpc(
            self._svc.rooms.leave_room(
                rooms_pb2.LeaveRoomRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return resp.left

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
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[DirectoryMember], Page]:
        req = member_directory_pb2.ListRoomMembersRequest(room_id=room_id, search=search)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.rooms.list_members(req, headers=self._headers()))
        data = pb_to_dict(resp)
        members = [
            m
            for m in (DirectoryMember.parse(row) for row in data.get("members") or [])
            if m is not None
        ]
        return members, Page.parse(data.get("page"))

    async def get_room_member(self, room_id: str, user_id: str) -> DirectoryMember | None:
        resp = await self._rpc(
            self._svc.rooms.get_member(
                member_directory_pb2.GetRoomMemberRequest(room_id=room_id, user_id=user_id),
                headers=self._headers(),
            )
        )
        return DirectoryMember.parse(pb_to_dict(resp.member))

    async def batch_get_room_members(
        self, room_id: str, user_ids: list[str]
    ) -> list[DirectoryMember]:
        resp = await self._rpc(
            self._svc.rooms.batch_get_members(
                member_directory_pb2.BatchGetRoomMembersRequest(room_id=room_id, user_ids=user_ids),
                headers=self._headers(),
            )
        )
        data = pb_to_dict(resp)
        return [
            m
            for m in (DirectoryMember.parse(row) for row in data.get("members") or [])
            if m is not None
        ]

    async def ban_member(
        self,
        room_id: str,
        user_id: str,
        reason: str,
        *,
        expires_at: datetime | None = None,
    ) -> bool:
        req = rooms_pb2.BanMemberRequest(room_id=room_id, user_id=user_id, reason=reason)
        if expires_at is not None:
            req.expires_at.CopyFrom(_timestamp_pb(expires_at))
        resp = await self._rpc(self._svc.rooms.ban_member(req, headers=self._headers()))
        return resp.banned

    async def unban_member(self, room_id: str, user_id: str, reason: str) -> bool:
        resp = await self._rpc(
            self._svc.rooms.unban_member(
                rooms_pb2.UnbanMemberRequest(room_id=room_id, user_id=user_id, reason=reason),
                headers=self._headers(),
            )
        )
        return resp.unbanned

    async def list_bans(
        self,
        *,
        room_id: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[RoomBan], Page]:
        req = rooms_pb2.ListBansRequest(room_id=room_id)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.rooms.list_bans(req, headers=self._headers()))
        data = pb_to_dict(resp)
        bans = [b for b in (RoomBan.parse(row) for row in data.get("bans") or []) if b is not None]
        return bans, Page.parse(data.get("page"))

    async def update_typing_indicator(
        self, room_id: str, *, thread_root_event_id: str = ""
    ) -> bool:
        resp = await self._rpc(
            self._svc.rooms.update_typing_indicator(
                rooms_pb2.UpdateTypingIndicatorRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )
        return resp.updated

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
    ) -> Message:
        req = messages_pb2.CreateMessageRequest(
            room_id=room_id,
            body=body,
            thread_root_event_id=thread_root_event_id,
            in_reply_to=in_reply_to,
            also_send_to_channel=also_send_to_channel,
            link_preview_token=link_preview_token,
        )
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

    async def delete_message(self, room_id: str, event_id: str) -> bool:
        resp = await self._rpc(
            self._svc.messages.delete_message(
                messages_pb2.DeleteMessageRequest(room_id=room_id, event_id=event_id),
                headers=self._headers(),
            )
        )
        return resp.deleted

    async def delete_attachment(self, room_id: str, event_id: str, attachment_id: str) -> bool:
        resp = await self._rpc(
            self._svc.messages.delete_attachment(
                messages_pb2.DeleteAttachmentRequest(
                    room_id=room_id, event_id=event_id, attachment_id=attachment_id
                ),
                headers=self._headers(),
            )
        )
        return resp.deleted

    async def delete_link_preview(self, room_id: str, event_id: str, url: str) -> bool:
        resp = await self._rpc(
            self._svc.messages.delete_link_preview(
                messages_pb2.DeleteLinkPreviewRequest(room_id=room_id, event_id=event_id, url=url),
                headers=self._headers(),
            )
        )
        return resp.deleted

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

    async def follow_thread(self, room_id: str, thread_root_event_id: str) -> bool:
        resp = await self._rpc(
            self._svc.threads.follow_thread(
                threads_pb2.FollowThreadRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )
        return resp.following

    async def unfollow_thread(self, room_id: str, thread_root_event_id: str) -> bool:
        resp = await self._rpc(
            self._svc.threads.unfollow_thread(
                threads_pb2.UnfollowThreadRequest(
                    room_id=room_id, thread_root_event_id=thread_root_event_id
                ),
                headers=self._headers(),
            )
        )
        return resp.following

    async def list_followed_threads(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> FollowedThreadsPage:
        req = threads_pb2.ListFollowedThreadsRequest()
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
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
        return TimelinePage.parse(pb_to_dict(resp.page))

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
        return TimelinePage.parse(pb_to_dict(resp.page)), resp.target_index

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
        return parse_datetime(d.get("previousReadAt"))

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

    async def get_notification_policy(self, room_id: str = "") -> NotificationPolicy:
        req = notifications_pb2.GetNotificationPolicyRequest()
        if room_id:
            req.room_id = room_id
        resp = await self._rpc(
            self._svc.notifications.get_notification_policy(req, headers=self._headers())
        )
        return NotificationPolicy.parse(pb_to_dict(resp.policy))

    async def update_notification_policy(
        self,
        level: NotificationLevel,
        *,
        room_id: str = "",
    ) -> NotificationPolicy:
        req = notifications_pb2.UpdateNotificationPolicyRequest(level=level.value)
        if room_id:
            req.room_id = room_id
        resp = await self._rpc(
            self._svc.notifications.update_notification_policy(req, headers=self._headers())
        )
        return NotificationPolicy.parse(pb_to_dict(resp.policy))

    # --- Notification preferences --------------------------------------

    async def get_server_notification_preference(self) -> NotificationPreference:
        resp = await self._rpc(
            self._svc.notification_prefs.get_server_notification_preference(
                notification_preferences_pb2.GetServerNotificationPreferenceRequest(),
                headers=self._headers(),
            )
        )
        return NotificationPreference.parse(pb_to_dict(resp.preference))

    async def update_server_notification_preference(
        self, level: NotificationLevel
    ) -> NotificationPreference:
        resp = await self._rpc(
            self._svc.notification_prefs.update_server_notification_preference(
                notification_preferences_pb2.UpdateServerNotificationPreferenceRequest(
                    level=level.value
                ),
                headers=self._headers(),
            )
        )
        return NotificationPreference.parse(pb_to_dict(resp.preference))

    async def get_room_notification_preference(self, room_id: str) -> NotificationPreference:
        resp = await self._rpc(
            self._svc.notification_prefs.get_room_notification_preference(
                notification_preferences_pb2.GetRoomNotificationPreferenceRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return NotificationPreference.parse(pb_to_dict(resp.preference))

    async def update_room_notification_preference(
        self, room_id: str, level: NotificationLevel
    ) -> NotificationPreference:
        resp = await self._rpc(
            self._svc.notification_prefs.update_room_notification_preference(
                notification_preferences_pb2.UpdateRoomNotificationPreferenceRequest(
                    room_id=room_id, level=level.value
                ),
                headers=self._headers(),
            )
        )
        return NotificationPreference.parse(pb_to_dict(resp.preference))

    # --- Push notifications --------------------------------------------

    async def subscribe_push(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        *,
        user_agent: str | None = None,
    ) -> bool:
        req = push_notifications_pb2.SubscribePushRequest(
            endpoint=endpoint, p256dh=p256dh, auth=auth
        )
        if user_agent is not None:
            req.user_agent = user_agent
        resp = await self._rpc(self._svc.push.subscribe(req, headers=self._headers()))
        return resp.subscribed

    async def unsubscribe_push(self, endpoint: str) -> bool:
        resp = await self._rpc(
            self._svc.push.unsubscribe(
                push_notifications_pb2.UnsubscribePushRequest(endpoint=endpoint),
                headers=self._headers(),
            )
        )
        return resp.unsubscribed

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

    async def get_call_token(self, room_id: str) -> str:
        resp = await self._rpc(
            self._svc.voice_calls.get_call_token(
                voice_calls_pb2.GetCallTokenRequest(room_id=room_id),
                headers=self._headers(),
            )
        )
        return resp.token

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
        items: list[tuple[AdminRoomLayoutItemKind, str]],
    ) -> AdminRoomLayoutGroup:
        req = room_layout_pb2.ReorderSidebarItemsInGroupRequest(group_id=group_id)
        for kind, item_id in items:
            item = req.items.add()
            item.kind = kind.value
            item.id = item_id
        resp = await self._rpc(
            self._svc.admin_room_layout.reorder_sidebar_items_in_group(req, headers=self._headers())
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
    ) -> tuple[list[AdminMember], list[Role], Page]:
        req = admin_members_pb2.ListMembersRequest(search=search)
        page = _page_pb(limit, offset)
        if page is not None:
            req.page.CopyFrom(page)
        resp = await self._rpc(self._svc.admin_users.list_members(req, headers=self._headers()))
        data = pb_to_dict(resp)
        members = [
            m
            for m in (AdminMember.parse(row) for row in data.get("members") or [])
            if m is not None
        ]
        roles = [r for r in (Role.parse(row) for row in data.get("roles") or []) if r is not None]
        return members, roles, Page.parse(data.get("page"))

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
    ) -> tuple[User | None, AdminMember | None]:
        req = admin_members_pb2.UpdateUserRequest(user_id=user_id)
        if display_name is not None:
            req.display_name = display_name
        if login is not None:
            req.login = login
        resp = await self._rpc(self._svc.admin_users.update_user(req, headers=self._headers()))
        return (
            User.parse(pb_to_dict(resp.user)),
            AdminMember.parse(pb_to_dict(resp.member)),
        )

    async def admin_update_user_password(self, user_id: str, password: str) -> AdminMember | None:
        resp = await self._rpc(
            self._svc.admin_users.update_user_password(
                admin_members_pb2.UpdateUserPasswordRequest(user_id=user_id, password=password),
                headers=self._headers(),
            )
        )
        return AdminMember.parse(pb_to_dict(resp.member))

    async def admin_clear_username_cooldown(self, user_id: str) -> bool:
        resp = await self._rpc(
            self._svc.admin_users.clear_username_cooldown(
                admin_members_pb2.ClearUsernameCooldownRequest(user_id=user_id),
                headers=self._headers(),
            )
        )
        return resp.cleared

    async def admin_delete_user(self, user_id: str, *, current_password: str = "") -> bool:
        resp = await self._rpc(
            self._svc.admin_users.delete_user(
                admin_members_pb2.DeleteUserRequest(
                    user_id=user_id, current_password=current_password
                ),
                headers=self._headers(),
            )
        )
        return resp.deleted

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

    async def admin_delete_role(self, name: str) -> bool:
        resp = await self._rpc(
            self._svc.admin_roles.delete_role(
                admin_roles_pb2.DeleteRoleRequest(name=name),
                headers=self._headers(),
            )
        )
        return resp.deleted

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

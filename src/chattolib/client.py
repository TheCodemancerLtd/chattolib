"""Main async client for the Chatto Connect API.

Chatto migrated from GraphQL to a protobuf-first Connect API in v0.4.x
(see ADR-042). The client speaks Connect JSON over HTTP for all
request/response operations; realtime events live in ``chattolib.realtime``.
"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from chattolib import _transport
from chattolib.exceptions import ChattoAuthError
from chattolib.types import (
    ActiveCall,
    Asset,
    DirectoryMember,
    FollowedThread,
    FollowedThreadsPage,
    ImageTransformOptions,
    LinkPreview,
    Message,
    Notification,
    NotificationLevel,
    NotificationPreference,
    NotificationsPage,
    Page,
    PresenceStatus,
    Room,
    RoomBan,
    RoomDirectoryScope,
    RoomGroup,
    RoomWithViewerState,
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

API_V1 = "chatto.api.v1"
AUTH_V1 = "chatto.auth.v1"
DISCOVERY_V1 = "chatto.discovery.v1"


def _page_arg(limit: int | None, offset: int | None) -> dict[str, Any] | None:
    if limit is None and offset is None:
        return None
    return {"limit": limit or 0, "offset": offset or 0}


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
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session_cookie = session_cookie
        self._owns_client = httpx_client is None
        self._http = httpx_client or httpx.AsyncClient()

    @classmethod
    async def login(
        cls,
        login: str,
        password: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ) -> ChattoClient:
        """Authenticate with username and password, returning a connected client.

        Uses Chatto's ``/auth/login`` HTTP endpoint (which is still exposed
        alongside the Connect API) and captures both the returned bearer token
        and any ``chatto_session`` cookie.
        """
        base = base_url.rstrip("/")
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{base}/auth/login",
                json={"login": login, "password": password},
            )
            if resp.status_code == 401:
                raise ChattoAuthError("Invalid credentials")
            resp.raise_for_status()
            body = resp.json()

        token = body.get("token")
        session_cookie = None
        if "set-cookie" in resp.headers:
            for cookie_header in resp.headers.get_list("set-cookie"):
                if cookie_header.startswith("chatto_session="):
                    session_cookie = cookie_header.split(";")[0].split("=", 1)[1]
                    break

        return cls(token=token, base_url=base_url, session_cookie=session_cookie)

    async def __aenter__(self) -> ChattoClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    # --- Transport ------------------------------------------------------

    async def call(
        self,
        service: str,
        method: str,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke an arbitrary Connect RPC and return the JSON response.

        Convenience escape hatch for callers who need to reach a service
        method that this client doesn't yet expose directly.
        """
        return await _transport.call(
            self._http,
            self._base_url,
            service,
            method,
            request,
            token=self._token,
            session_cookie=self._session_cookie,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def session_cookie(self) -> str | None:
        return self._session_cookie

    # --- Server discovery ----------------------------------------------

    async def get_server(self) -> tuple[ServerProfile, ServerLogin]:
        """Public server profile and login options. Does not require auth."""
        data = await self.call(f"{DISCOVERY_V1}.ServerDiscoveryService", "GetServer")
        return ServerProfile.parse(data.get("profile")), ServerLogin.parse(data.get("login"))

    async def get_motd(self) -> str | None:
        data = await self.call(f"{API_V1}.ServerService", "GetMotd")
        return data.get("motd")

    async def get_runtime_config(self) -> ServerRuntimeConfig:
        data = await self.call(f"{API_V1}.ServerService", "GetRuntimeConfig")
        return ServerRuntimeConfig.parse(data.get("runtime"))

    # --- Viewer ---------------------------------------------------------

    async def get_viewer(self) -> dict[str, Any]:
        """Full authenticated viewer snapshot (raw JSON).

        The response contains ``user``, ``capabilities``, notification
        preferences, permissions and viewer state. Callers that only need the
        current user's public profile should use ``me()`` for a typed result.
        """
        return await self.call(f"{API_V1}.ViewerService", "GetViewer")

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
        request: dict[str, Any] = {}
        if display_name is not None:
            request["displayName"] = display_name
        if login is not None:
            request["login"] = login
        data = await self.call(f"{API_V1}.MyAccountService", "UpdateProfile", request)
        user = User.parse(data.get("user"))
        assert user is not None
        return user

    async def upload_avatar(
        self,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> User:
        p = Path(file_path)
        payload = {
            "image": {
                "image": base64.b64encode(p.read_bytes()).decode("ascii"),
                "filename": p.name,
                "contentType": content_type,
            }
        }
        data = await self.call(f"{API_V1}.MyAccountService", "UploadAvatar", payload)
        user = User.parse(data.get("user"))
        assert user is not None
        return user

    async def delete_avatar(self) -> User:
        data = await self.call(f"{API_V1}.MyAccountService", "DeleteAvatar")
        user = User.parse(data.get("user"))
        assert user is not None
        return user

    async def update_password(self, new_password: str, current_password: str = "") -> User:
        data = await self.call(
            f"{API_V1}.MyAccountService",
            "UpdatePassword",
            {"password": new_password, "currentPassword": current_password},
        )
        user = User.parse(data.get("user"))
        assert user is not None
        return user

    async def update_settings(
        self,
        *,
        timezone: str | None = None,
        time_format: TimeFormat | None = None,
    ) -> UserSettings:
        request: dict[str, Any] = {}
        if timezone is not None:
            request["timezone"] = timezone
        if time_format is not None:
            request["timeFormat"] = time_format.value
        data = await self.call(f"{API_V1}.MyAccountService", "UpdateSettings", request)
        return UserSettings.parse(data.get("settings"))

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
        data = await self.call(
            f"{API_V1}.MyAccountService",
            "UpdatePresence",
            {"status": status.value, "userSelected": user_selected},
        )
        return PresenceStatus(data.get("status", PresenceStatus.UNSPECIFIED.value))

    async def update_custom_status(
        self,
        emoji: str,
        text: str,
        *,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {"emoji": emoji, "text": text}
        if expires_at is not None:
            request["expiresAt"] = format_datetime(expires_at)
        return await self.call(
            f"{API_V1}.MyAccountService",
            "UpdateCustomStatus",
            request,
        )

    async def delete_custom_status(self) -> dict[str, Any]:
        return await self.call(f"{API_V1}.MyAccountService", "DeleteCustomStatus")

    async def request_account_deletion(self) -> str:
        data = await self.call(f"{API_V1}.MyAccountService", "RequestAccountDeletion")
        return str(data.get("confirmationToken", ""))

    async def delete_my_account(self, confirmation_token: str) -> bool:
        data = await self.call(
            f"{API_V1}.MyAccountService",
            "DeleteMyAccount",
            {"confirmationToken": confirmation_token},
        )
        return bool(data.get("deleted", False))

    # --- Users ----------------------------------------------------------

    async def list_users(
        self,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[DirectoryMember], Page]:
        request: dict[str, Any] = {}
        if search:
            request["search"] = search
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(f"{API_V1}.UserService", "ListUsers", request)
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
        request: dict[str, Any] = (
            {"userId": user_id} if user_id else {"login": login}
        )
        data = await self.call(f"{API_V1}.UserService", "GetUser", request)
        return DirectoryMember.parse(data.get("user"))

    async def batch_get_users(self, user_ids: list[str]) -> list[DirectoryMember]:
        data = await self.call(
            f"{API_V1}.UserService",
            "BatchGetUsers",
            {"userIds": user_ids},
        )
        return [
            u
            for u in (DirectoryMember.parse(row) for row in data.get("users") or [])
            if u is not None
        ]

    # --- Room directory ------------------------------------------------

    async def list_rooms(
        self, scope: RoomDirectoryScope = RoomDirectoryScope.ALL
    ) -> list[RoomWithViewerState]:
        data = await self.call(
            f"{API_V1}.RoomDirectoryService",
            "ListRooms",
            {"scope": scope.value},
        )
        return [
            r
            for r in (RoomWithViewerState.parse(row) for row in data.get("rooms") or [])
            if r is not None
        ]

    async def list_room_groups(self) -> list[RoomGroup]:
        data = await self.call(f"{API_V1}.RoomDirectoryService", "ListRoomGroups")
        return [
            g
            for g in (RoomGroup.parse(row) for row in data.get("groups") or [])
            if g is not None
        ]

    async def get_room_group(self, group_id: str) -> RoomGroup | None:
        data = await self.call(
            f"{API_V1}.RoomDirectoryService",
            "GetRoomGroup",
            {"groupId": group_id},
        )
        return RoomGroup.parse(data.get("group"))

    async def batch_get_room_groups(self, group_ids: list[str]) -> list[RoomGroup]:
        data = await self.call(
            f"{API_V1}.RoomDirectoryService",
            "BatchGetRoomGroups",
            {"groupIds": group_ids},
        )
        return [
            g
            for g in (RoomGroup.parse(row) for row in data.get("groups") or [])
            if g is not None
        ]

    async def get_room(self, room_id: str) -> RoomWithViewerState | None:
        data = await self.call(
            f"{API_V1}.RoomDirectoryService",
            "GetRoom",
            {"roomId": room_id},
        )
        return RoomWithViewerState.parse(data.get("room"))

    async def batch_get_rooms(self, room_ids: list[str]) -> list[RoomWithViewerState]:
        data = await self.call(
            f"{API_V1}.RoomDirectoryService",
            "BatchGetRooms",
            {"roomIds": room_ids},
        )
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
    ) -> Room:
        data = await self.call(
            f"{API_V1}.RoomService",
            "CreateRoom",
            {
                "name": name,
                "description": description,
                "groupId": group_id,
                "universal": universal,
            },
        )
        room = Room.parse(data.get("room"))
        assert room is not None
        return room

    async def update_room(
        self,
        room_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        universal: bool | None = None,
    ) -> Room:
        request: dict[str, Any] = {"roomId": room_id}
        if name is not None:
            request["name"] = name
        if description is not None:
            request["description"] = description
        if universal is not None:
            request["universal"] = universal
        data = await self.call(f"{API_V1}.RoomService", "UpdateRoom", request)
        room = Room.parse(data.get("room"))
        assert room is not None
        return room

    async def archive_room(self, room_id: str) -> Room:
        data = await self.call(
            f"{API_V1}.RoomService", "ArchiveRoom", {"roomId": room_id}
        )
        room = Room.parse(data.get("room"))
        assert room is not None
        return room

    async def unarchive_room(self, room_id: str) -> Room:
        data = await self.call(
            f"{API_V1}.RoomService", "UnarchiveRoom", {"roomId": room_id}
        )
        room = Room.parse(data.get("room"))
        assert room is not None
        return room

    async def join_room(self, room_id: str) -> Room:
        data = await self.call(f"{API_V1}.RoomService", "JoinRoom", {"roomId": room_id})
        room = Room.parse(data.get("room"))
        assert room is not None
        return room

    async def join_room_group(self, group_id: str) -> list[str]:
        data = await self.call(
            f"{API_V1}.RoomService", "JoinRoomGroup", {"groupId": group_id}
        )
        return list(data.get("joinedRoomIds") or [])

    async def start_dm(self, participant_ids: list[str]) -> Room:
        data = await self.call(
            f"{API_V1}.RoomService", "StartDM", {"participantIds": participant_ids}
        )
        room = Room.parse(data.get("room"))
        assert room is not None
        return room

    async def leave_room(self, room_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.RoomService", "LeaveRoom", {"roomId": room_id}
        )
        return bool(data.get("left", False))

    async def add_member(self, room_id: str, user_id: str) -> DirectoryMember | None:
        data = await self.call(
            f"{API_V1}.RoomService",
            "AddMember",
            {"roomId": room_id, "userId": user_id},
        )
        return DirectoryMember.parse(data.get("member"))

    async def remove_member(self, room_id: str, user_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.RoomService",
            "RemoveMember",
            {"roomId": room_id, "userId": user_id},
        )
        return bool(data.get("removed", False))

    async def list_room_members(
        self,
        room_id: str,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[DirectoryMember], Page]:
        request: dict[str, Any] = {"roomId": room_id}
        if search:
            request["search"] = search
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(f"{API_V1}.RoomService", "ListMembers", request)
        members = [
            m
            for m in (DirectoryMember.parse(row) for row in data.get("members") or [])
            if m is not None
        ]
        return members, Page.parse(data.get("page"))

    async def get_room_member(self, room_id: str, user_id: str) -> DirectoryMember | None:
        data = await self.call(
            f"{API_V1}.RoomService",
            "GetMember",
            {"roomId": room_id, "userId": user_id},
        )
        return DirectoryMember.parse(data.get("member"))

    async def batch_get_room_members(
        self, room_id: str, user_ids: list[str]
    ) -> list[DirectoryMember]:
        data = await self.call(
            f"{API_V1}.RoomService",
            "BatchGetMembers",
            {"roomId": room_id, "userIds": user_ids},
        )
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
        request: dict[str, Any] = {
            "roomId": room_id,
            "userId": user_id,
            "reason": reason,
        }
        if expires_at is not None:
            request["expiresAt"] = format_datetime(expires_at)
        data = await self.call(f"{API_V1}.RoomService", "BanMember", request)
        return bool(data.get("banned", False))

    async def unban_member(self, room_id: str, user_id: str, reason: str) -> bool:
        data = await self.call(
            f"{API_V1}.RoomService",
            "UnbanMember",
            {"roomId": room_id, "userId": user_id, "reason": reason},
        )
        return bool(data.get("unbanned", False))

    async def list_bans(
        self,
        *,
        room_id: str = "",
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[RoomBan], Page]:
        request: dict[str, Any] = {}
        if room_id:
            request["roomId"] = room_id
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(f"{API_V1}.RoomService", "ListBans", request)
        bans = [
            b
            for b in (RoomBan.parse(row) for row in data.get("bans") or [])
            if b is not None
        ]
        return bans, Page.parse(data.get("page"))

    async def update_typing_indicator(
        self, room_id: str, *, thread_root_event_id: str = ""
    ) -> bool:
        request: dict[str, Any] = {"roomId": room_id}
        if thread_root_event_id:
            request["threadRootEventId"] = thread_root_event_id
        data = await self.call(
            f"{API_V1}.RoomService", "UpdateTypingIndicator", request
        )
        return bool(data.get("updated", False))

    # --- Room timeline / read state -----------------------------------

    async def get_room_events(
        self,
        room_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> TimelinePage:
        request: dict[str, Any] = {"roomId": room_id}
        if limit is not None:
            request["limit"] = limit
        if before is not None:
            request["before"] = before
        elif after is not None:
            request["after"] = after
        data = await self.call(f"{API_V1}.RoomService", "GetRoomEvents", request)
        return TimelinePage.parse(data.get("page"))

    async def get_room_events_around(
        self,
        room_id: str,
        event_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[TimelinePage, int]:
        request: dict[str, Any] = {"roomId": room_id, "eventId": event_id}
        if limit is not None:
            request["limit"] = limit
        data = await self.call(
            f"{API_V1}.RoomService", "GetRoomEventsAround", request
        )
        return TimelinePage.parse(data.get("page")), int(data.get("targetIndex", 0))

    async def mark_room_as_read(
        self, room_id: str, up_to_event_id: str = ""
    ) -> tuple[datetime | None, datetime | None]:
        request: dict[str, Any] = {"roomId": room_id}
        if up_to_event_id:
            request["upToEventId"] = up_to_event_id
        data = await self.call(f"{API_V1}.RoomService", "MarkRoomAsRead", request)
        return (
            parse_datetime(data.get("lastReadAt")),
            parse_datetime(data.get("previousLastReadAt")),
        )

    async def list_room_attachments(
        self,
        room_id: str,
        *,
        thumbnail: ImageTransformOptions | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[dict[str, Any]], Page]:
        request: dict[str, Any] = {"roomId": room_id}
        if thumbnail is not None:
            request["thumbnail"] = thumbnail.to_wire()
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(
            f"{API_V1}.RoomService", "ListRoomAttachments", request
        )
        return list(data.get("attachments") or []), Page.parse(data.get("page"))

    # --- Messages -------------------------------------------------------

    async def fetch_link_preview(self, url: str) -> tuple[LinkPreview | None, str]:
        data = await self.call(
            f"{API_V1}.MessageService", "FetchLinkPreview", {"url": url}
        )
        return LinkPreview.parse(data.get("preview")), data.get("previewToken", "")

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
        request: dict[str, Any] = {"roomId": room_id, "body": body}
        if attachment_asset_ids:
            request["attachmentAssetIds"] = attachment_asset_ids
        if thread_root_event_id:
            request["threadRootEventId"] = thread_root_event_id
        if in_reply_to:
            request["inReplyTo"] = in_reply_to
        if also_send_to_channel:
            request["alsoSendToChannel"] = True
        if link_preview_token:
            request["linkPreviewToken"] = link_preview_token
        data = await self.call(f"{API_V1}.MessageService", "CreateMessage", request)
        message = Message.parse(data.get("message"))
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
        request: dict[str, Any] = {"roomId": room_id, "eventId": event_id}
        if body is not None:
            request["body"] = body
        if also_send_to_channel is not None:
            request["alsoSendToChannel"] = also_send_to_channel
        data = await self.call(f"{API_V1}.MessageService", "UpdateMessage", request)
        message = Message.parse(data.get("message"))
        assert message is not None
        return message

    async def delete_message(self, room_id: str, event_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.MessageService",
            "DeleteMessage",
            {"roomId": room_id, "eventId": event_id},
        )
        return bool(data.get("deleted", False))

    async def delete_attachment(
        self, room_id: str, event_id: str, attachment_id: str
    ) -> bool:
        data = await self.call(
            f"{API_V1}.MessageService",
            "DeleteAttachment",
            {
                "roomId": room_id,
                "eventId": event_id,
                "attachmentId": attachment_id,
            },
        )
        return bool(data.get("deleted", False))

    async def delete_link_preview(self, room_id: str, event_id: str, url: str) -> bool:
        data = await self.call(
            f"{API_V1}.MessageService",
            "DeleteLinkPreview",
            {"roomId": room_id, "eventId": event_id, "url": url},
        )
        return bool(data.get("deleted", False))

    async def get_message(self, room_id: str, event_id: str) -> Message | None:
        data = await self.call(
            f"{API_V1}.MessageService",
            "GetMessage",
            {"roomId": room_id, "eventId": event_id},
        )
        return Message.parse(data.get("message"))

    async def batch_get_messages(
        self, room_id: str, event_ids: list[str]
    ) -> list[Message]:
        data = await self.call(
            f"{API_V1}.MessageService",
            "BatchGetMessages",
            {"roomId": room_id, "eventIds": event_ids},
        )
        return [
            m
            for m in (Message.parse(row) for row in data.get("messages") or [])
            if m is not None
        ]

    async def add_reaction(
        self, room_id: str, message_event_id: str, emoji: str
    ) -> bool:
        data = await self.call(
            f"{API_V1}.MessageService",
            "AddReaction",
            {
                "roomId": room_id,
                "messageEventId": message_event_id,
                "emoji": emoji,
            },
        )
        return bool(data.get("added", False))

    async def remove_reaction(
        self, room_id: str, message_event_id: str, emoji: str
    ) -> bool:
        data = await self.call(
            f"{API_V1}.MessageService",
            "RemoveReaction",
            {
                "roomId": room_id,
                "messageEventId": message_event_id,
                "emoji": emoji,
            },
        )
        return bool(data.get("removed", False))

    # --- Threads --------------------------------------------------------

    async def follow_thread(self, room_id: str, thread_root_event_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.ThreadService",
            "FollowThread",
            {"roomId": room_id, "threadRootEventId": thread_root_event_id},
        )
        return bool(data.get("following", False))

    async def unfollow_thread(self, room_id: str, thread_root_event_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.ThreadService",
            "UnfollowThread",
            {"roomId": room_id, "threadRootEventId": thread_root_event_id},
        )
        return bool(data.get("following", False))

    async def list_followed_threads(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> FollowedThreadsPage:
        request: dict[str, Any] = {}
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(
            f"{API_V1}.ThreadService", "ListFollowedThreads", request
        )
        threads = [FollowedThread.parse(t) for t in data.get("threads") or []]
        users: dict[str, User] = {}
        includes = data.get("includes") or {}
        for uid, user_data in (includes.get("users") or {}).items():
            parsed = User.parse(user_data)
            if parsed is not None:
                users[uid] = parsed
        return FollowedThreadsPage(
            threads=threads,
            page=Page.parse(data.get("page")),
            users_by_id=users,
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
        request: dict[str, Any] = {
            "roomId": room_id,
            "threadRootEventId": thread_root_event_id,
        }
        if limit is not None:
            request["limit"] = limit
        if before is not None:
            request["before"] = before
        elif after is not None:
            request["after"] = after
        data = await self.call(
            f"{API_V1}.ThreadService", "GetThreadEvents", request
        )
        return TimelinePage.parse(data.get("page"))

    async def get_thread_events_around(
        self,
        room_id: str,
        thread_root_event_id: str,
        event_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[TimelinePage, int]:
        request: dict[str, Any] = {
            "roomId": room_id,
            "threadRootEventId": thread_root_event_id,
            "eventId": event_id,
        }
        if limit is not None:
            request["limit"] = limit
        data = await self.call(
            f"{API_V1}.ThreadService", "GetThreadEventsAround", request
        )
        return TimelinePage.parse(data.get("page")), int(data.get("targetIndex", 0))

    async def mark_thread_as_read(
        self,
        room_id: str,
        thread_root_event_id: str,
        up_to_event_id: str = "",
    ) -> datetime | None:
        request: dict[str, Any] = {
            "roomId": room_id,
            "threadRootEventId": thread_root_event_id,
        }
        if up_to_event_id:
            request["upToEventId"] = up_to_event_id
        data = await self.call(
            f"{API_V1}.ThreadService", "MarkThreadAsRead", request
        )
        return parse_datetime(data.get("previousReadAt"))

    # --- Notifications --------------------------------------------------

    async def list_notifications(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> NotificationsPage:
        request: dict[str, Any] = {}
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(
            f"{API_V1}.NotificationService", "ListNotifications", request
        )
        notifications = [Notification.parse(n) for n in data.get("notifications") or []]
        return NotificationsPage(
            notifications=notifications,
            page=Page.parse(data.get("page")),
        )

    async def has_notifications(self) -> bool:
        data = await self.call(f"{API_V1}.NotificationService", "HasNotifications")
        return bool(data.get("hasNotifications", False))

    async def get_notification(self, notification_id: str) -> Notification | None:
        data = await self.call(
            f"{API_V1}.NotificationService",
            "GetNotification",
            {"notificationId": notification_id},
        )
        raw = data.get("notification")
        return Notification.parse(raw) if raw else None

    async def batch_get_notifications(
        self, notification_ids: list[str]
    ) -> list[Notification]:
        data = await self.call(
            f"{API_V1}.NotificationService",
            "BatchGetNotifications",
            {"notificationIds": notification_ids},
        )
        return [Notification.parse(n) for n in data.get("notifications") or []]

    async def list_room_notifications(
        self,
        room_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> NotificationsPage:
        request: dict[str, Any] = {"roomId": room_id}
        page = _page_arg(limit, offset)
        if page is not None:
            request["page"] = page
        data = await self.call(
            f"{API_V1}.NotificationService", "ListRoomNotifications", request
        )
        return NotificationsPage(
            notifications=[
                Notification.parse(n) for n in data.get("notifications") or []
            ],
            page=Page.parse(data.get("page")),
        )

    async def list_room_notification_counts(self) -> dict[str, int]:
        data = await self.call(
            f"{API_V1}.NotificationService", "ListRoomNotificationCounts"
        )
        return {
            row.get("roomId", ""): int(row.get("totalCount", 0))
            for row in data.get("roomCounts") or []
        }

    async def dismiss_notification(self, notification_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.NotificationService",
            "DismissNotification",
            {"notificationId": notification_id},
        )
        return bool(data.get("dismissed", False))

    async def dismiss_all_notifications(self) -> int:
        data = await self.call(
            f"{API_V1}.NotificationService", "DismissAllNotifications"
        )
        return int(data.get("dismissedCount", 0))

    # --- Notification preferences --------------------------------------

    async def get_server_notification_preference(self) -> NotificationPreference:
        data = await self.call(
            f"{API_V1}.NotificationPreferencesService",
            "GetServerNotificationPreference",
        )
        return NotificationPreference.parse(data.get("preference"))

    async def update_server_notification_preference(
        self, level: NotificationLevel
    ) -> NotificationPreference:
        data = await self.call(
            f"{API_V1}.NotificationPreferencesService",
            "UpdateServerNotificationPreference",
            {"level": level.value},
        )
        return NotificationPreference.parse(data.get("preference"))

    async def get_room_notification_preference(
        self, room_id: str
    ) -> NotificationPreference:
        data = await self.call(
            f"{API_V1}.NotificationPreferencesService",
            "GetRoomNotificationPreference",
            {"roomId": room_id},
        )
        return NotificationPreference.parse(data.get("preference"))

    async def update_room_notification_preference(
        self, room_id: str, level: NotificationLevel
    ) -> NotificationPreference:
        data = await self.call(
            f"{API_V1}.NotificationPreferencesService",
            "UpdateRoomNotificationPreference",
            {"roomId": room_id, "level": level.value},
        )
        return NotificationPreference.parse(data.get("preference"))

    # --- Push notifications --------------------------------------------

    async def subscribe_push(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        *,
        user_agent: str | None = None,
    ) -> bool:
        request: dict[str, Any] = {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}
        if user_agent is not None:
            request["userAgent"] = user_agent
        data = await self.call(
            f"{API_V1}.PushNotificationService", "Subscribe", request
        )
        return bool(data.get("subscribed", False))

    async def unsubscribe_push(self, endpoint: str) -> bool:
        data = await self.call(
            f"{API_V1}.PushNotificationService",
            "Unsubscribe",
            {"endpoint": endpoint},
        )
        return bool(data.get("unsubscribed", False))

    # --- Assets ---------------------------------------------------------

    async def get_asset(
        self,
        room_id: str,
        asset_id: str,
        *,
        thumbnail: ImageTransformOptions | None = None,
    ) -> Asset | None:
        request: dict[str, Any] = {"roomId": room_id, "assetId": asset_id}
        if thumbnail is not None:
            request["thumbnail"] = thumbnail.to_wire()
        data = await self.call(f"{API_V1}.AssetService", "GetAsset", request)
        return Asset.parse(data.get("asset"))

    async def batch_get_assets(
        self,
        room_id: str,
        asset_ids: list[str],
        *,
        thumbnail: ImageTransformOptions | None = None,
    ) -> list[Asset]:
        request: dict[str, Any] = {"roomId": room_id, "assetIds": asset_ids}
        if thumbnail is not None:
            request["thumbnail"] = thumbnail.to_wire()
        data = await self.call(f"{API_V1}.AssetService", "BatchGetAssets", request)
        return [
            a
            for a in (Asset.parse(row) for row in data.get("assets") or [])
            if a is not None
        ]

    # --- Voice calls ----------------------------------------------------

    async def list_active_calls(self) -> list[ActiveCall]:
        data = await self.call(f"{API_V1}.VoiceCallService", "ListActiveCalls")
        return [ActiveCall.parse(c) for c in data.get("calls") or []]

    async def get_active_call(self, room_id: str) -> ActiveCall | None:
        data = await self.call(
            f"{API_V1}.VoiceCallService", "GetActiveCall", {"roomId": room_id}
        )
        raw = data.get("call")
        return ActiveCall.parse(raw) if raw else None

    async def batch_get_active_calls(self, room_ids: list[str]) -> list[ActiveCall]:
        data = await self.call(
            f"{API_V1}.VoiceCallService",
            "BatchGetActiveCalls",
            {"roomIds": room_ids},
        )
        return [ActiveCall.parse(c) for c in data.get("calls") or []]

    async def join_call(self, room_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.VoiceCallService", "JoinCall", {"roomId": room_id}
        )
        return bool(data.get("joined", False))

    async def leave_call(self, room_id: str) -> bool:
        data = await self.call(
            f"{API_V1}.VoiceCallService", "LeaveCall", {"roomId": room_id}
        )
        return bool(data.get("left", False))

    async def get_call_token(self, room_id: str) -> str:
        data = await self.call(
            f"{API_V1}.VoiceCallService", "GetCallToken", {"roomId": room_id}
        )
        return str(data.get("token", ""))

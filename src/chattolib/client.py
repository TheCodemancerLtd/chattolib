"""Main async client for the Chatto GraphQL API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from chattolib import queries as Q
from chattolib.exceptions import ChattoAuthError, ChattoGraphQLError
from chattolib.types import (
    Attachment,
    FollowedThread,
    FollowedThreadsPage,
    LinkPreview,
    MessageEvent,
    NotificationLevel,
    NotificationsPage,
    PresenceStatus,
    PresenceStatusInput,
    ReactionSummary,
    Room,
    RoomEventsPage,
    RoomGroup,
    RoomType,
    ServerProfile,
    TimeFormat,
    User,
    UserSettings,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _parse_user_settings(data: dict[str, Any] | None) -> UserSettings | None:
    if data is None:
        return None
    return UserSettings(
        timezone=data.get("timezone"),
        time_format=TimeFormat(data["timeFormat"])
        if data.get("timeFormat")
        else TimeFormat.UNSPECIFIED,
    )


def _parse_user(data: dict[str, Any]) -> User:
    status_raw = data.get("presenceStatus")
    return User(
        id=data["id"],
        login=data["login"],
        display_name=data["displayName"],
        presence_status=PresenceStatus(status_raw) if status_raw else PresenceStatus.OFFLINE,
        created_at=_parse_datetime(data.get("createdAt")),
        avatar_url=data.get("avatarUrl"),
        settings=_parse_user_settings(data.get("settings")),
    )


def _parse_room(data: dict[str, Any]) -> Room:
    return Room(
        id=data["id"],
        name=data["name"],
        type=RoomType(data["type"]) if data.get("type") else None,
        description=data.get("description"),
        archived=data.get("archived", False),
        group_id=data.get("groupId"),
        has_unread=data.get("hasUnread", False),
    )


def _parse_room_group(data: dict[str, Any]) -> RoomGroup:
    return RoomGroup(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        room_ids=[r["id"] for r in data.get("rooms", [])],
    )


def _parse_server_profile(data: dict[str, Any]) -> ServerProfile:
    return ServerProfile(
        name=data["name"],
        logo_url=data.get("logoUrl"),
        banner_url=data.get("bannerUrl"),
        welcome_message=data.get("welcomeMessage"),
        motd=data.get("motd"),
        description=data.get("description"),
    )


def _parse_attachment(data: dict[str, Any]) -> Attachment:
    return Attachment(
        id=data["id"],
        room_id=data.get("roomId", ""),
        filename=data["filename"],
        content_type=data["contentType"],
        size=data["size"],
        width=data.get("width", 0),
        height=data.get("height", 0),
        url=data.get("url", ""),
        thumbnail_url=data.get("thumbnailUrl"),
    )


def _parse_reaction(data: dict[str, Any]) -> ReactionSummary:
    return ReactionSummary(
        emoji=data["emoji"],
        count=data["count"],
        has_reacted=data.get("hasReacted", False),
        users=[_parse_user(u) for u in data.get("users", [])],
    )


def _parse_link_preview(data: dict[str, Any]) -> LinkPreview:
    return LinkPreview(
        url=data["url"],
        title=data.get("title"),
        description=data.get("description"),
        image_url=data.get("imageUrl"),
        image_asset_id=data.get("imageAssetId"),
        site_name=data.get("siteName"),
        embed_type=data.get("embedType"),
        embed_id=data.get("embedId"),
    )


def _parse_message_event(data: dict[str, Any]) -> MessageEvent:
    event = data.get("event") or {}
    actor_data = data.get("actor")
    return MessageEvent(
        id=data["id"],
        room_id=event.get("roomId", ""),
        body=event.get("body"),
        created_at=_parse_datetime(data.get("createdAt")),
        updated_at=_parse_datetime(event.get("updatedAt")),
        actor=_parse_user(actor_data) if actor_data else None,
        attachments=[_parse_attachment(a) for a in event.get("attachments", [])],
        reactions=[_parse_reaction(r) for r in event.get("reactions", [])],
        in_reply_to=event.get("inReplyTo"),
        thread_root_event_id=event.get("threadRootEventId"),
        reply_count=event.get("replyCount", 0),
        last_reply_at=_parse_datetime(event.get("lastReplyAt")),
        link_preview=_parse_link_preview(event["linkPreview"])
        if event.get("linkPreview")
        else None,
        echo_of_event_id=event.get("echoOfEventId"),
        echo_from_thread_root_event_id=event.get("echoFromThreadRootEventId"),
        viewer_is_following_thread=event.get("viewerIsFollowingThread"),
    )


class ChattoClient:
    """Async client for the Chatto GraphQL API.

    Usage::

        async with await ChattoClient.login("user", "pass") as client:
            me = await client.me()
            rooms = await client.rooms()

        # Or with a token directly:
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
        self._url = f"{self._base_url}/api/graphql"
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
        """Authenticate with username and password, returning a connected client."""
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

    # --- Transport ---

    async def _execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation and return the data dict."""
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._session_cookie:
            headers["Cookie"] = f"chatto_session={self._session_cookie}"

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self._http.post(self._url, json=payload, headers=headers)

        if response.status_code == 401:
            raise ChattoAuthError("Authentication failed")

        body = response.json()

        if "errors" in body:
            raise ChattoGraphQLError(body["errors"], data=body.get("data"))

        response.raise_for_status()

        return body["data"]

    async def _execute_upload(
        self,
        query: str,
        variables: dict[str, Any],
        file_path: str,
        variable_path: str = "input.file",
    ) -> dict[str, Any]:
        """Execute a GraphQL mutation with a file upload (multipart request spec)."""
        import json as _json
        from pathlib import Path

        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._session_cookie:
            headers["Cookie"] = f"chatto_session={self._session_cookie}"

        p = Path(file_path)
        operations = _json.dumps({"query": query, "variables": variables})
        map_field = _json.dumps({"0": [f"variables.{variable_path}"]})

        response = await self._http.post(
            self._url,
            headers=headers,
            data={"operations": operations, "map": map_field},
            files={"0": (p.name, p.read_bytes(), "application/octet-stream")},
        )

        if response.status_code == 401:
            raise ChattoAuthError("Authentication failed")

        body = response.json()

        if "errors" in body:
            raise ChattoGraphQLError(body["errors"], data=body.get("data"))

        response.raise_for_status()

        return body["data"]

    # --- Queries ---

    async def me(self) -> User:
        data = await self._execute(Q.QUERY_ME)
        return _parse_user(data["viewer"]["user"])

    async def server(self) -> dict[str, Any]:
        data = await self._execute(Q.QUERY_SERVER)
        return data["server"]

    async def server_profile(self) -> ServerProfile:
        data = await self._execute(Q.QUERY_SERVER)
        return _parse_server_profile(data["server"]["profile"])

    async def rooms(self) -> list[Room]:
        data = await self._execute(Q.QUERY_SERVER)
        return [_parse_room(r) for r in data["server"]["rooms"]]

    async def room_groups(self) -> list[RoomGroup]:
        data = await self._execute(Q.QUERY_SERVER)
        return [_parse_room_group(g) for g in data["server"]["roomGroups"]]

    async def room(self, room_id: str) -> Room:
        data = await self._execute(Q.QUERY_ROOM, {"roomId": room_id})
        return _parse_room(data["room"])

    async def room_events(
        self,
        room_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> RoomEventsPage:
        variables: dict[str, Any] = {"roomId": room_id}
        if limit is not None:
            variables["limit"] = limit
        if before is not None:
            variables["before"] = before
        if after is not None:
            variables["after"] = after
        data = await self._execute(Q.QUERY_ROOM_EVENTS, variables)
        conn = data["room"]["events"]
        return RoomEventsPage(
            events=[_parse_message_event(e) for e in conn["events"]],
            has_older=conn["hasOlder"],
            has_newer=conn["hasNewer"],
            start_cursor=conn.get("startCursor"),
            end_cursor=conn.get("endCursor"),
        )

    async def thread_events(
        self,
        room_id: str,
        thread_root_event_id: str,
    ) -> list[MessageEvent]:
        data = await self._execute(
            Q.QUERY_THREAD_EVENTS,
            {"roomId": room_id, "eventId": thread_root_event_id},
        )
        root = data["room"]["event"] or {}
        event = root.get("event") or {}
        thread = event.get("threadReplies") or {}
        return [_parse_message_event(e) for e in thread.get("events", [])]

    async def user(self, user_id: str) -> User:
        data = await self._execute(Q.QUERY_USER, {"userId": user_id})
        return _parse_user(data["user"])

    async def user_by_login(self, login: str) -> User:
        data = await self._execute(Q.QUERY_USER_BY_LOGIN, {"login": login})
        return _parse_user(data["userByLogin"])

    async def server_members(self) -> list[User]:
        data = await self._execute(Q.QUERY_SERVER_MEMBERS)
        return [_parse_user(u) for u in data["server"]["members"]["users"]]

    async def notifications(self) -> NotificationsPage:
        data = await self._execute(Q.QUERY_NOTIFICATIONS)
        conn = data["viewer"]["notifications"]
        return NotificationsPage(
            items=conn["items"],
            total_count=conn.get("totalCount", 0),
            has_more=conn.get("hasMore", False),
        )

    async def followed_threads(self) -> FollowedThreadsPage:
        data = await self._execute(Q.QUERY_FOLLOWED_THREADS)
        conn = data["viewer"]["followedThreads"]
        return FollowedThreadsPage(
            threads=[
                FollowedThread(
                    room_id=t["roomId"],
                    thread_root_event_id=t["threadRootEventId"],
                    reply_count=t.get("replyCount", 0),
                    last_reply_at=_parse_datetime(t.get("lastReplyAt")),
                    has_unread=t.get("hasUnread", False),
                )
                for t in conn["threads"]
            ],
            total_count=conn.get("totalCount", 0),
            has_more=conn.get("hasMore", False),
        )

    async def link_preview(self, url: str) -> LinkPreview | None:
        data = await self._execute(Q.QUERY_LINK_PREVIEW, {"url": url})
        lp = data.get("linkPreview")
        return _parse_link_preview(lp) if lp else None

    async def active_call_room_ids(self) -> list[str]:
        data = await self._execute(Q.QUERY_ACTIVE_CALL_ROOM_IDS)
        return data["activeCallRoomIds"]

    # --- Message mutations ---

    async def post_message(
        self,
        room_id: str,
        body: str | None = None,
        *,
        thread_root_event_id: str | None = None,
        in_reply_to: str | None = None,
        also_send_to_channel: bool | None = None,
        link_preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {"roomId": room_id}
        if body is not None:
            input_data["body"] = body
        if thread_root_event_id is not None:
            input_data["threadRootEventId"] = thread_root_event_id
        if in_reply_to is not None:
            input_data["inReplyTo"] = in_reply_to
        if also_send_to_channel is not None:
            input_data["alsoSendToChannel"] = also_send_to_channel
        if link_preview is not None:
            input_data["linkPreview"] = link_preview
        data = await self._execute(Q.MUTATION_POST_MESSAGE, {"input": input_data})
        return data["postMessage"]

    async def update_message(
        self,
        room_id: str,
        event_id: str,
        body: str,
    ) -> dict[str, Any]:
        data = await self._execute(
            Q.MUTATION_UPDATE_MESSAGE,
            {"input": {"roomId": room_id, "eventId": event_id, "body": body}},
        )
        return data["updateMessage"]

    edit_message = update_message

    async def delete_message(self, room_id: str, event_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DELETE_MESSAGE,
            {"input": {"roomId": room_id, "eventId": event_id}},
        )
        return data["deleteMessage"]

    async def delete_attachment(self, room_id: str, event_id: str, attachment_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DELETE_ATTACHMENT,
            {
                "input": {
                    "roomId": room_id,
                    "eventId": event_id,
                    "attachmentId": attachment_id,
                }
            },
        )
        return data["deleteAttachment"]

    async def delete_link_preview(self, room_id: str, event_id: str, url: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DELETE_LINK_PREVIEW,
            {"input": {"roomId": room_id, "eventId": event_id, "url": url}},
        )
        return data["deleteLinkPreview"]

    # --- Reactions ---

    async def add_reaction(self, room_id: str, message_event_id: str, emoji: str) -> Any:
        data = await self._execute(
            Q.MUTATION_ADD_REACTION,
            {"input": {"roomId": room_id, "messageEventId": message_event_id, "emoji": emoji}},
        )
        return data["addReaction"]

    async def remove_reaction(self, room_id: str, message_event_id: str, emoji: str) -> Any:
        data = await self._execute(
            Q.MUTATION_REMOVE_REACTION,
            {"input": {"roomId": room_id, "messageEventId": message_event_id, "emoji": emoji}},
        )
        return data["removeReaction"]

    # --- Rooms ---

    async def create_room(
        self,
        name: str,
        group_id: str,
        description: str | None = None,
    ) -> Room:
        input_data: dict[str, Any] = {"name": name, "groupId": group_id}
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_CREATE_ROOM, {"input": input_data})
        return _parse_room(data["createRoom"])

    async def update_room(
        self,
        room_id: str,
        name: str,
        description: str | None = None,
    ) -> Room:
        input_data: dict[str, Any] = {"roomId": room_id, "name": name}
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_UPDATE_ROOM, {"input": input_data})
        return _parse_room(data["updateRoom"])

    async def archive_room(self, room_id: str) -> Any:
        data = await self._execute(Q.MUTATION_ARCHIVE_ROOM, {"input": {"roomId": room_id}})
        return data["archiveRoom"]

    async def unarchive_room(self, room_id: str) -> Any:
        data = await self._execute(Q.MUTATION_UNARCHIVE_ROOM, {"input": {"roomId": room_id}})
        return data["unarchiveRoom"]

    async def join_room(self, room_id: str) -> dict[str, Any]:
        data = await self._execute(Q.MUTATION_JOIN_ROOM, {"input": {"roomId": room_id}})
        return data["joinRoom"]

    async def leave_room(self, room_id: str) -> Any:
        data = await self._execute(Q.MUTATION_LEAVE_ROOM, {"input": {"roomId": room_id}})
        return data["leaveRoom"]

    async def join_group(self, group_id: str) -> Any:
        data = await self._execute(Q.MUTATION_JOIN_GROUP, {"input": {"groupId": group_id}})
        return data["joinGroup"]

    async def ban_room_member(
        self,
        room_id: str,
        user_id: str,
        reason: str,
        expires_at: str | None = None,
    ) -> Any:
        input_data: dict[str, Any] = {
            "roomId": room_id,
            "userId": user_id,
            "reason": reason,
        }
        if expires_at is not None:
            input_data["expiresAt"] = expires_at
        data = await self._execute(Q.MUTATION_BAN_ROOM_MEMBER, {"input": input_data})
        return data["banRoomMember"]

    async def unban_room_member(self, room_id: str, user_id: str, reason: str) -> Any:
        data = await self._execute(
            Q.MUTATION_UNBAN_ROOM_MEMBER,
            {"input": {"roomId": room_id, "userId": user_id, "reason": reason}},
        )
        return data["unbanRoomMember"]

    async def mark_room_as_read(
        self, room_id: str, up_to_event_id: str | None = None
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {"roomId": room_id}
        if up_to_event_id is not None:
            input_data["upToEventId"] = up_to_event_id
        data = await self._execute(Q.MUTATION_MARK_ROOM_AS_READ, {"input": input_data})
        return data["markRoomAsRead"]

    async def mark_thread_as_read(
        self,
        room_id: str,
        thread_root_event_id: str,
        up_to_event_id: str | None = None,
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {
            "roomId": room_id,
            "threadRootEventId": thread_root_event_id,
        }
        if up_to_event_id is not None:
            input_data["upToEventId"] = up_to_event_id
        data = await self._execute(Q.MUTATION_MARK_THREAD_AS_READ, {"input": input_data})
        return data["markThreadAsRead"]

    async def follow_thread(self, room_id: str, thread_root_event_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_FOLLOW_THREAD,
            {"input": {"roomId": room_id, "threadRootEventId": thread_root_event_id}},
        )
        return data["followThread"]

    async def unfollow_thread(self, room_id: str, thread_root_event_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_UNFOLLOW_THREAD,
            {"input": {"roomId": room_id, "threadRootEventId": thread_root_event_id}},
        )
        return data["unfollowThread"]

    async def send_typing_indicator(
        self, room_id: str, thread_root_event_id: str | None = None
    ) -> Any:
        input_data: dict[str, Any] = {"roomId": room_id}
        if thread_root_event_id is not None:
            input_data["threadRootEventId"] = thread_root_event_id
        data = await self._execute(Q.MUTATION_SEND_TYPING, {"input": input_data})
        return data["sendTypingIndicator"]

    async def start_dm(self, participant_ids: list[str]) -> dict[str, Any]:
        data = await self._execute(
            Q.MUTATION_START_DM, {"input": {"participantIds": participant_ids}}
        )
        return data["startDM"]

    # --- Profile / account ---

    async def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        login: str | None = None,
    ) -> User:
        input_data: dict[str, Any] = {"userId": user_id}
        if display_name is not None:
            input_data["displayName"] = display_name
        if login is not None:
            input_data["login"] = login
        data = await self._execute(Q.MUTATION_UPDATE_PROFILE, {"input": input_data})
        return _parse_user(data["updateProfile"])

    async def upload_avatar(self, file_path: str, user_id: str) -> dict[str, Any]:
        variables: dict[str, Any] = {"input": {"userId": user_id, "file": None}}
        data = await self._execute_upload(
            Q.MUTATION_UPLOAD_AVATAR,
            variables,
            file_path,
        )
        return data["uploadAvatar"]

    async def delete_avatar(self, user_id: str) -> dict[str, Any]:
        data = await self._execute(Q.MUTATION_DELETE_AVATAR, {"input": {"userId": user_id}})
        return data["deleteAvatar"]

    async def update_presence(self, status: PresenceStatusInput | PresenceStatus) -> Any:
        # The server's UpdateMyPresenceInput uses PresenceStatusInput, which omits OFFLINE.
        if isinstance(status, PresenceStatus) and status == PresenceStatus.OFFLINE:
            raise ValueError("OFFLINE is not a settable presence status")
        data = await self._execute(Q.MUTATION_UPDATE_PRESENCE, {"input": {"status": status.value}})
        return data["updateMyPresence"]

    async def update_settings(
        self,
        user_id: str,
        *,
        timezone: str | None = None,
        time_format: TimeFormat | None = None,
    ) -> UserSettings:
        input_data: dict[str, Any] = {"userId": user_id}
        if timezone is not None:
            input_data["timezone"] = timezone
        if time_format is not None:
            input_data["timeFormat"] = time_format.value
        data = await self._execute(Q.MUTATION_UPDATE_SETTINGS, {"input": input_data})
        return _parse_user_settings(data["updateSettings"]) or UserSettings()

    async def request_account_deletion(self) -> Any:
        data = await self._execute(Q.MUTATION_REQUEST_ACCOUNT_DELETION)
        return data["requestAccountDeletion"]

    async def delete_my_account(self, confirmation_token: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DELETE_MY_ACCOUNT,
            {"input": {"confirmationToken": confirmation_token}},
        )
        return data["deleteMyAccount"]

    # --- Notifications & push ---

    async def set_server_notification_level(self, level: NotificationLevel) -> Any:
        data = await self._execute(
            Q.MUTATION_SET_SERVER_NOTIFICATION_LEVEL,
            {"input": {"level": level.value}},
        )
        return data["setServerNotificationLevel"]

    async def set_room_notification_level(self, room_id: str, level: NotificationLevel) -> Any:
        data = await self._execute(
            Q.MUTATION_SET_ROOM_NOTIFICATION_LEVEL,
            {"input": {"roomId": room_id, "level": level.value}},
        )
        return data["setRoomNotificationLevel"]

    async def dismiss_notification(self, notification_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DISMISS_NOTIFICATION,
            {"input": {"notificationId": notification_id}},
        )
        return data["dismissNotification"]

    async def dismiss_all_notifications(self) -> Any:
        data = await self._execute(Q.MUTATION_DISMISS_ALL_NOTIFICATIONS)
        return data["dismissAllNotifications"]

    async def subscribe_to_push(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str | None = None,
    ) -> Any:
        input_data: dict[str, Any] = {
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
        }
        if user_agent is not None:
            input_data["userAgent"] = user_agent
        data = await self._execute(Q.MUTATION_SUBSCRIBE_TO_PUSH, {"input": input_data})
        return data["subscribeToPush"]

    async def unsubscribe_from_push(self, endpoint: str) -> Any:
        data = await self._execute(
            Q.MUTATION_UNSUBSCRIBE_FROM_PUSH, {"input": {"endpoint": endpoint}}
        )
        return data["unsubscribeFromPush"]

    # --- Room groups ---

    async def create_room_group(self, name: str, description: str | None = None) -> RoomGroup:
        input_data: dict[str, Any] = {"name": name}
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_CREATE_ROOM_GROUP, {"input": input_data})
        g = data["createRoomGroup"]
        return RoomGroup(id=g["id"], name=g["name"], description=g.get("description", ""))

    async def update_room_group(
        self, group_id: str, name: str, description: str | None = None
    ) -> RoomGroup:
        input_data: dict[str, Any] = {"id": group_id, "name": name}
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_UPDATE_ROOM_GROUP, {"input": input_data})
        g = data["updateRoomGroup"]
        return RoomGroup(id=g["id"], name=g["name"], description=g.get("description", ""))

    async def delete_room_group(self, group_id: str) -> Any:
        data = await self._execute(Q.MUTATION_DELETE_ROOM_GROUP, {"input": {"id": group_id}})
        return data["deleteRoomGroup"]

    async def reorder_room_groups(self, ordered_ids: list[str]) -> Any:
        data = await self._execute(
            Q.MUTATION_REORDER_ROOM_GROUPS, {"input": {"orderedIds": ordered_ids}}
        )
        return data["reorderRoomGroups"]

    async def move_room_to_group(self, room_id: str, group_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_MOVE_ROOM_TO_GROUP,
            {"input": {"roomId": room_id, "groupId": group_id}},
        )
        return data["moveRoomToGroup"]

    async def reorder_rooms_in_group(self, group_id: str, ordered_room_ids: list[str]) -> Any:
        data = await self._execute(
            Q.MUTATION_REORDER_ROOMS_IN_GROUP,
            {"input": {"groupId": group_id, "orderedRoomIds": ordered_room_ids}},
        )
        return data["reorderRoomsInGroup"]

    # --- Server admin (logo/banner/config) ---

    async def upload_server_logo(self, file_path: str) -> dict[str, Any]:
        data = await self._execute_upload(
            Q.MUTATION_UPLOAD_SERVER_LOGO,
            {"input": {"file": None}},
            file_path,
        )
        return data["uploadServerLogo"]

    async def delete_server_logo(self) -> dict[str, Any]:
        data = await self._execute(Q.MUTATION_DELETE_SERVER_LOGO)
        return data["deleteServerLogo"]

    async def upload_server_banner(self, file_path: str) -> dict[str, Any]:
        data = await self._execute_upload(
            Q.MUTATION_UPLOAD_SERVER_BANNER,
            {"input": {"file": None}},
            file_path,
        )
        return data["uploadServerBanner"]

    async def delete_server_banner(self) -> dict[str, Any]:
        data = await self._execute(Q.MUTATION_DELETE_SERVER_BANNER)
        return data["deleteServerBanner"]

    async def update_server_config(
        self,
        *,
        server_name: str | None = None,
        welcome_message: str | None = None,
        motd: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {}
        if server_name is not None:
            input_data["serverName"] = server_name
        if welcome_message is not None:
            input_data["welcomeMessage"] = welcome_message
        if motd is not None:
            input_data["motd"] = motd
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_UPDATE_SERVER_CONFIG, {"input": input_data})
        return data["updateServerConfig"]

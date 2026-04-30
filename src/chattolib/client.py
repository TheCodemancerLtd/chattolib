"""Main async client for the Chatto GraphQL API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator

import httpx

from chattolib import queries as Q
from chattolib.exceptions import ChattoAuthError, ChattoGraphQLError
from chattolib.types import (
    Attachment,
    FollowedThread,
    LinkPreview,
    MessageEvent,
    PresenceStatus,
    Reaction,
    Room,
    RoomEventsPage,
    Space,
    User,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _parse_user(data: dict[str, Any]) -> User:
    return User(
        id=data["id"],
        login=data["login"],
        display_name=data["displayName"],
        created_at=_parse_datetime(data.get("createdAt")),
        avatar_url=data.get("avatarUrl"),
        presence_status=PresenceStatus(data["presenceStatus"]) if data.get("presenceStatus") else None,
    )


def _parse_space(data: dict[str, Any]) -> Space:
    return Space(
        id=data["id"],
        name=data["name"],
        description=data.get("description"),
        logo_url=data.get("logoUrl"),
        banner_url=data.get("bannerUrl"),
        member_count=data.get("memberCount", 0),
        room_count=data.get("roomCount", 0),
        viewer_is_member=data.get("viewerIsMember", False),
    )


def _parse_room(data: dict[str, Any]) -> Room:
    return Room(
        id=data["id"],
        space_id=data["spaceId"],
        name=data["name"],
        description=data.get("description"),
        archived=data.get("archived", False),
        auto_join=data.get("autoJoin", False),
        has_unread=data.get("hasUnread", False),
        has_mention=data.get("hasMention", False),
    )


def _parse_attachment(data: dict[str, Any]) -> Attachment:
    return Attachment(
        id=data["id"],
        space_id=data.get("spaceId", ""),
        room_id=data.get("roomId", ""),
        filename=data["filename"],
        content_type=data["contentType"],
        size=data["size"],
        url=data.get("url"),
        width=data.get("width"),
        height=data.get("height"),
    )


def _parse_reaction(data: dict[str, Any]) -> Reaction:
    return Reaction(
        emoji=data["emoji"],
        count=data["count"],
        has_reacted=data.get("hasReacted", False),
        users=[_parse_user(u) for u in data.get("users", [])],
    )


def _parse_message_event(data: dict[str, Any]) -> MessageEvent:
    event = data.get("event", {})
    actor_data = data.get("actor")
    return MessageEvent(
        id=data["id"],
        space_id=event.get("spaceId", ""),
        room_id=event.get("roomId", ""),
        body=event.get("body"),
        created_at=_parse_datetime(data.get("createdAt")),
        actor=_parse_user(actor_data) if actor_data else None,
        attachments=[_parse_attachment(a) for a in event.get("attachments", [])],
        reactions=[_parse_reaction(r) for r in event.get("reactions", [])],
        in_reply_to=event.get("inReplyTo"),
        in_thread=event.get("inThread"),
        reply_count=event.get("replyCount", 0),
        link_preview=_parse_link_preview(event["linkPreview"]) if event.get("linkPreview") else None,
    )


def _parse_link_preview(data: dict[str, Any]) -> LinkPreview:
    return LinkPreview(
        url=data["url"],
        title=data.get("title"),
        description=data.get("description"),
        image_url=data.get("imageUrl"),
        site_name=data.get("siteName"),
        embed_type=data.get("embedType"),
        embed_id=data.get("embedId"),
    )


class ChattoClient:
    """Async client for the Chatto GraphQL API.

    Usage::

        async with ChattoClient.login("user", "pass") as client:
            me = await client.me()
            spaces = await client.spaces()

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

        # Chatto returns 422 with a JSON body for GraphQL validation errors
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

        response.raise_for_status()
        body = response.json()

        if "errors" in body:
            raise ChattoGraphQLError(body["errors"], data=body.get("data"))

        return body["data"]

    # --- Queries ---

    async def me(self) -> User:
        data = await self._execute(Q.QUERY_ME)
        return _parse_user(data["me"])

    async def spaces(self) -> list[Space]:
        data = await self._execute(Q.QUERY_SPACES)
        return [_parse_space(s) for s in data["spaces"]]

    async def space(self, space_id: str) -> Space:
        data = await self._execute(Q.QUERY_SPACE, {"id": space_id})
        return _parse_space(data["space"])

    async def room(self, space_id: str, room_id: str) -> Room:
        data = await self._execute(Q.QUERY_ROOM, {"spaceId": space_id, "roomId": room_id})
        return _parse_room(data["room"])

    async def room_events(
        self,
        space_id: str,
        room_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> RoomEventsPage:
        variables: dict[str, Any] = {"spaceId": space_id, "roomId": room_id}
        if limit is not None:
            variables["limit"] = limit
        if before is not None:
            variables["before"] = before
        if after is not None:
            variables["after"] = after
        data = await self._execute(Q.QUERY_ROOM_EVENTS, variables)
        conn = data["roomEvents"]
        return RoomEventsPage(
            events=[_parse_message_event(e) for e in conn["events"]],
            has_older=conn["hasOlder"],
            has_newer=conn["hasNewer"],
        )

    async def thread_events(
        self,
        space_id: str,
        room_id: str,
        thread_root_event_id: str,
    ) -> list[MessageEvent]:
        data = await self._execute(
            Q.QUERY_THREAD_EVENTS,
            {"spaceId": space_id, "roomId": room_id, "threadRootEventId": thread_root_event_id},
        )
        return [_parse_message_event(e) for e in data["threadEvents"]]

    async def user(self, user_id: str) -> User:
        data = await self._execute(Q.QUERY_USER, {"id": user_id})
        return _parse_user(data["user"])

    async def user_by_login(self, login: str) -> User:
        data = await self._execute(Q.QUERY_USER_BY_LOGIN, {"login": login})
        return _parse_user(data["userByLogin"])

    async def users(self) -> list[User]:
        data = await self._execute(Q.QUERY_USERS)
        return [_parse_user(u) for u in data["users"]]

    async def notifications(self) -> list[dict[str, Any]]:
        data = await self._execute(Q.QUERY_NOTIFICATIONS)
        return data["notifications"]

    async def followed_threads(self, space_id: str) -> list[FollowedThread]:
        data = await self._execute(Q.QUERY_FOLLOWED_THREADS, {"spaceId": space_id})
        return [
            FollowedThread(
                space_id=t["spaceId"],
                room_id=t["roomId"],
                thread_root_event_id=t["threadRootEventId"],
                reply_count=t.get("replyCount", 0),
                last_reply_at=_parse_datetime(t.get("lastReplyAt")),
                has_unread=t.get("hasUnread", False),
            )
            for t in data["myFollowedThreads"]
        ]

    # --- Mutations ---

    async def create_user(self, login: str, display_name: str, password: str) -> User:
        data = await self._execute(
            Q.MUTATION_CREATE_USER,
            {"input": {"login": login, "displayName": display_name, "password": password}},
        )
        return _parse_user(data["createUser"])

    async def post_message(
        self,
        space_id: str,
        room_id: str,
        body: str,
        *,
        in_thread: str | None = None,
        in_reply_to: str | None = None,
        also_send_to_channel: bool | None = None,
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {
            "spaceId": space_id,
            "roomId": room_id,
            "body": body,
        }
        if in_thread is not None:
            input_data["inThread"] = in_thread
        if in_reply_to is not None:
            input_data["inReplyTo"] = in_reply_to
        if also_send_to_channel is not None:
            input_data["alsoSendToChannel"] = also_send_to_channel
        data = await self._execute(Q.MUTATION_POST_MESSAGE, {"input": input_data})
        return data["postMessage"]

    async def edit_message(
        self,
        space_id: str,
        room_id: str,
        event_id: str,
        body: str,
    ) -> dict[str, Any]:
        data = await self._execute(
            Q.MUTATION_EDIT_MESSAGE,
            {"input": {"spaceId": space_id, "roomId": room_id, "eventId": event_id, "body": body}},
        )
        return data["editMessage"]

    async def delete_message(self, space_id: str, room_id: str, event_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DELETE_MESSAGE,
            {"input": {"spaceId": space_id, "roomId": room_id, "eventId": event_id}},
        )
        return data["deleteMessage"]

    async def add_reaction(
        self, space_id: str, room_id: str, message_event_id: str, emoji: str
    ) -> Any:
        data = await self._execute(
            Q.MUTATION_ADD_REACTION,
            {"input": {"spaceId": space_id, "roomId": room_id, "messageEventId": message_event_id, "emoji": emoji}},
        )
        return data["addReaction"]

    async def remove_reaction(
        self, space_id: str, room_id: str, message_event_id: str, emoji: str
    ) -> Any:
        data = await self._execute(
            Q.MUTATION_REMOVE_REACTION,
            {"input": {"spaceId": space_id, "roomId": room_id, "messageEventId": message_event_id, "emoji": emoji}},
        )
        return data["removeReaction"]

    async def create_space(self, name: str, description: str | None = None) -> Space:
        input_data: dict[str, Any] = {"name": name}
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_CREATE_SPACE, {"input": input_data})
        return _parse_space(data["createSpace"])

    async def join_space(self, space_id: str) -> dict[str, Any]:
        data = await self._execute(Q.MUTATION_JOIN_SPACE, {"input": {"spaceId": space_id}})
        return data["joinSpace"]

    async def leave_space(self, space_id: str) -> Any:
        data = await self._execute(Q.MUTATION_LEAVE_SPACE, {"input": {"spaceId": space_id}})
        return data["leaveSpace"]

    async def create_room(
        self, space_id: str, name: str, description: str | None = None
    ) -> Room:
        input_data: dict[str, Any] = {"spaceId": space_id, "name": name}
        if description is not None:
            input_data["description"] = description
        data = await self._execute(Q.MUTATION_CREATE_ROOM, {"input": input_data})
        return _parse_room(data["createRoom"])

    async def join_room(self, space_id: str, room_id: str) -> dict[str, Any]:
        data = await self._execute(
            Q.MUTATION_JOIN_ROOM, {"input": {"spaceId": space_id, "roomId": room_id}}
        )
        return data["joinRoom"]

    async def leave_room(self, space_id: str, room_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_LEAVE_ROOM, {"input": {"spaceId": space_id, "roomId": room_id}}
        )
        return data["leaveRoom"]

    async def mark_room_as_read(self, space_id: str, room_id: str) -> dict[str, Any]:
        data = await self._execute(
            Q.MUTATION_MARK_ROOM_AS_READ, {"input": {"spaceId": space_id, "roomId": room_id}}
        )
        return data["markRoomAsRead"]

    async def follow_thread(
        self, space_id: str, room_id: str, thread_root_event_id: str
    ) -> Any:
        data = await self._execute(
            Q.MUTATION_FOLLOW_THREAD,
            {"input": {"spaceId": space_id, "roomId": room_id, "threadRootEventId": thread_root_event_id}},
        )
        return data["followThread"]

    async def unfollow_thread(
        self, space_id: str, room_id: str, thread_root_event_id: str
    ) -> Any:
        data = await self._execute(
            Q.MUTATION_UNFOLLOW_THREAD,
            {"input": {"spaceId": space_id, "roomId": room_id, "threadRootEventId": thread_root_event_id}},
        )
        return data["unfollowThread"]

    async def send_typing_indicator(
        self, space_id: str, room_id: str, thread_root_event_id: str | None = None
    ) -> Any:
        input_data: dict[str, Any] = {"spaceId": space_id, "roomId": room_id}
        if thread_root_event_id is not None:
            input_data["threadRootEventId"] = thread_root_event_id
        data = await self._execute(Q.MUTATION_SEND_TYPING, {"input": input_data})
        return data["sendTypingIndicator"]

    async def start_dm(self, participant_ids: list[str]) -> dict[str, Any]:
        data = await self._execute(
            Q.MUTATION_START_DM, {"input": {"participantIds": participant_ids}}
        )
        return data["startDM"]

    async def update_my_profile(
        self,
        *,
        display_name: str | None = None,
        login: str | None = None,
    ) -> User:
        input_data: dict[str, Any] = {}
        if display_name is not None:
            input_data["displayName"] = display_name
        if login is not None:
            input_data["login"] = login
        data = await self._execute(Q.MUTATION_UPDATE_MY_PROFILE, {"input": input_data})
        return _parse_user(data["updateMyProfile"])

    async def upload_my_avatar(self, file_path: str) -> dict[str, Any]:
        data = await self._execute_upload(
            Q.MUTATION_UPLOAD_MY_AVATAR,
            {"input": {"file": None}},
            file_path,
        )
        return data["uploadMyAvatar"]

    async def update_presence(self, status: PresenceStatus) -> Any:
        data = await self._execute(
            Q.MUTATION_UPDATE_PRESENCE, {"input": {"status": status.value}}
        )
        return data["updateMyPresence"]

    async def dismiss_notification(self, notification_id: str) -> Any:
        data = await self._execute(
            Q.MUTATION_DISMISS_NOTIFICATION, {"input": {"notificationId": notification_id}}
        )
        return data["dismissNotification"]

    async def dismiss_all_notifications(self) -> Any:
        data = await self._execute(Q.MUTATION_DISMISS_ALL_NOTIFICATIONS)
        return data["dismissAllNotifications"]

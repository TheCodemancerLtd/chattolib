"""Tests for ChattoClient.

Since the client now goes through generated ConnectRPC service stubs, tests
mock at the service-client method level with ``AsyncMock`` rather than at the
HTTP transport layer. This exercises the request-building and response-parsing
paths without any real network traffic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from chattolib._pb.chatto.admin.v1 import (
    room_layout_pb2,
)
from chattolib._pb.chatto.admin.v1 import (
    server_pb2 as admin_server_pb2,
)
from chattolib._pb.chatto.api.v1 import (
    account_pb2,
    asset_uploads_pb2,
    attachments_pb2,
    external_identities_pb2,
    member_directory_pb2,
    messages_pb2,
    notification_preferences_pb2,
    notifications_pb2,
    presence_pb2,
    push_notifications_pb2,
    reactions_pb2,
    read_state_pb2,
    roles_pb2,
    room_directory_pb2,
    room_timeline_pb2,
    rooms_pb2,
    threads_pb2,
    viewer_pb2,
    voice_calls_pb2,
)
from chattolib._pb.chatto.discovery.v1 import server_pb2 as discovery_server_pb2
from chattolib.client import ChattoClient
from chattolib.exceptions import ChattoAuthError
from chattolib.types import (
    ImageFitMode,
    ImageTransformOptions,
    NotificationLevel,
    PresenceStatus,
    RoomKind,
    TimeFormat,
)

BASE = "https://chat.chatto.run"


@pytest.fixture
def client():
    return ChattoClient(token="test-token", base_url=BASE)


def _mock_method(client: ChattoClient, service: str, method: str, response):
    """Replace a service-client method with an AsyncMock returning ``response``."""
    svc = getattr(client._svc, service)
    setattr(svc, method, AsyncMock(return_value=response))
    return getattr(svc, method)


# --- Login flow ---------------------------------------------------------


async def test_login_and_capture_session():
    with respx.mock(base_url=BASE) as api:
        api.post("/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "token": "cht_abc123"},
                headers={"set-cookie": "chatto_session=xyz; Path=/; HttpOnly"},
            )
        )
        c = await ChattoClient.login("alice", "password123")
        assert c.token == "cht_abc123"
        assert c.session_cookie == "xyz"
        await c.close()


async def test_login_invalid():
    with respx.mock(base_url=BASE) as api:
        api.post("/auth/login").mock(
            return_value=httpx.Response(401, json={"error": "Invalid credentials"})
        )
        with pytest.raises(ChattoAuthError, match="Invalid credentials"):
            await ChattoClient.login("bad", "creds")


# --- Server discovery ---------------------------------------------------


async def test_get_server(client):
    resp = discovery_server_pb2.GetServerResponse()
    resp.profile.name = "Chatto HQ"
    resp.profile.version = "0.4.2"
    resp.login.direct_registration_enabled = True
    resp.login.authorize_url = "/oauth"
    _mock_method(client, "server_discovery", "get_server", resp)

    async with client:
        profile, login = await client.get_server()

    assert profile.name == "Chatto HQ"
    assert profile.version == "0.4.2"
    assert login.direct_registration_enabled is True
    assert login.authorize_url == "/oauth"


# --- Viewer -------------------------------------------------------------


async def test_me(client):
    resp = viewer_pb2.GetViewerResponse()
    resp.user.profile.id = "u1"
    resp.user.profile.login = "alice"
    resp.user.profile.display_name = "Alice"
    resp.user.profile.presence_status = "PRESENCE_STATUS_ONLINE"
    resp.user.has_verified_email = True
    resp.user.settings.timezone = "UTC"
    resp.user.settings.time_format = "TIME_FORMAT_24_HOUR"
    resp.user.has_password = True
    _mock_method(client, "viewer", "get_viewer", resp)

    async with client:
        user = await client.me()

    assert user.id == "u1"
    assert user.login == "alice"
    assert user.display_name == "Alice"
    assert user.presence_status is PresenceStatus.ONLINE


# --- Room directory ----------------------------------------------------


async def test_list_rooms(client):
    resp = room_directory_pb2.ListRoomsResponse()
    entry = resp.rooms.add()
    entry.room.id = "r1"
    entry.room.kind = "ROOM_KIND_CHANNEL"
    entry.room.name = "general"
    entry.room.group_id = "g1"
    entry.viewer_state.is_member = True
    entry.viewer_state.has_unread = False
    _mock_method(client, "room_directory", "list_rooms", resp)

    async with client:
        rooms = await client.list_rooms()

    assert len(rooms) == 1
    assert rooms[0].room is not None
    assert rooms[0].room.name == "general"
    assert rooms[0].room.kind is RoomKind.CHANNEL
    assert rooms[0].viewer_state.is_member is True


# --- Messages ----------------------------------------------------------


async def test_post_message(client):
    resp = messages_pb2.CreateMessageResponse()
    resp.message.id = "e1"
    resp.message.room_id = "r1"
    resp.message.actor_id = "u1"
    resp.message.body = "Hello!"
    _mock_method(client, "messages", "create_message", resp)

    async with client:
        message = await client.post_message("r1", "Hello!")

    assert message.id == "e1"
    assert message.body == "Hello!"
    assert message.room_id == "r1"


async def test_update_message(client):
    resp = messages_pb2.UpdateMessageResponse()
    resp.message.id = "e1"
    resp.message.room_id = "r1"
    resp.message.actor_id = "u1"
    resp.message.body = "edited"
    resp.message.updated_at.FromJsonString("2026-01-01T00:01:00Z")
    m = _mock_method(client, "messages", "update_message", resp)

    async with client:
        msg = await client.update_message("r1", "e1", body="edited")

    assert msg.body == "edited"
    assert msg.updated_at is not None
    # verify the request had the optional body field explicitly set
    call_args = m.call_args
    req = call_args.args[0]
    assert isinstance(req, messages_pb2.UpdateMessageRequest)
    assert req.HasField("body")
    assert req.body == "edited"


async def test_delete_message(client):
    resp = messages_pb2.DeleteMessageResponse(deleted=True)
    _mock_method(client, "messages", "delete_message", resp)

    async with client:
        assert await client.delete_message("r1", "e1") is True


async def test_add_reaction(client):
    resp = reactions_pb2.AddReactionResponse(added=True)
    _mock_method(client, "messages", "add_reaction", resp)

    async with client:
        assert await client.add_reaction("r1", "e1", "thumbsup") is True


async def test_remove_reaction(client):
    resp = reactions_pb2.RemoveReactionResponse(removed=True)
    _mock_method(client, "messages", "remove_reaction", resp)

    async with client:
        assert await client.remove_reaction("r1", "e1", "thumbsup") is True


# --- Room lifecycle ---------------------------------------------------


async def test_create_room(client):
    resp = rooms_pb2.CreateRoomResponse()
    resp.room.id = "r1"
    resp.room.kind = "ROOM_KIND_CHANNEL"
    resp.room.name = "general"
    resp.room.group_id = "g1"
    _mock_method(client, "rooms", "create_room", resp)

    async with client:
        room = await client.create_room("general", "g1")

    assert room.id == "r1"
    assert room.name == "general"
    assert room.group_id == "g1"


async def test_archive_room(client):
    resp = rooms_pb2.ArchiveRoomResponse()
    resp.room.id = "r1"
    resp.room.name = "general"
    resp.room.archived = True
    _mock_method(client, "rooms", "archive_room", resp)

    async with client:
        room = await client.archive_room("r1")

    assert room.archived is True


async def test_ban_member(client):
    resp = rooms_pb2.BanMemberResponse(banned=True)
    _mock_method(client, "rooms", "ban_member", resp)

    async with client:
        assert await client.ban_member("r1", "u2", "spam") is True


async def test_start_dm(client):
    resp = rooms_pb2.StartDMResponse()
    resp.room.id = "r1"
    resp.room.kind = "ROOM_KIND_DM"
    _mock_method(client, "rooms", "start_dm", resp)

    async with client:
        room = await client.start_dm(["u1", "u2"])

    assert room.id == "r1"
    assert room.kind is RoomKind.DM


# --- Room timeline ----------------------------------------------------


async def test_get_room_events(client):
    resp = room_timeline_pb2.GetRoomEventsResponse()
    event = resp.page.events.add()
    event.id = "e1"
    event.actor_id = "u1"
    event.created_at.FromJsonString("2026-01-01T00:00:00Z")
    event.message_posted.message.id = "e1"
    event.message_posted.message.room_id = "r1"
    event.message_posted.message.actor_id = "u1"
    event.message_posted.message.body = "hi"
    event.message_posted.message.created_at.FromJsonString("2026-01-01T00:00:00Z")
    resp.page.start_cursor = "cA"
    resp.page.end_cursor = "cB"
    resp.page.includes.users["u1"].id = "u1"
    resp.page.includes.users["u1"].login = "alice"
    resp.page.includes.users["u1"].display_name = "Alice"
    _mock_method(client, "rooms", "get_room_events", resp)

    async with client:
        page = await client.get_room_events("r1", limit=50)

    assert len(page.events) == 1
    assert page.events[0].kind == "message_posted"
    assert page.events[0].message is not None
    assert page.events[0].message.body == "hi"
    assert page.users_by_id["u1"].login == "alice"


async def test_mark_room_as_read(client):
    resp = read_state_pb2.MarkRoomAsReadResponse()
    resp.last_read_at.FromJsonString("2026-01-01T00:00:00Z")
    resp.previous_last_read_at.FromJsonString("2025-12-31T00:00:00Z")
    _mock_method(client, "rooms", "mark_room_as_read", resp)

    async with client:
        last, previous = await client.mark_room_as_read("r1", up_to_event_id="e1")

    assert last is not None
    assert previous is not None


# --- Profile / account ------------------------------------------------


async def test_update_profile(client):
    resp = account_pb2.UpdateProfileResponse()
    resp.user.id = "u1"
    resp.user.login = "newname"
    resp.user.display_name = "New Name"
    resp.user.presence_status = "PRESENCE_STATUS_ONLINE"
    _mock_method(client, "account", "update_profile", resp)

    async with client:
        user = await client.update_profile(login="newname", display_name="New Name")

    assert user.login == "newname"
    assert user.display_name == "New Name"


async def test_upload_avatar(client, tmp_path):
    resp = account_pb2.UploadAvatarResponse()
    resp.user.id = "u1"
    resp.user.login = "alice"
    resp.user.display_name = "Alice"
    resp.user.avatar_url = "https://example.com/avatar.jpg"
    mock = _mock_method(client, "account", "upload_avatar", resp)

    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(b"\x89PNGfake")
    async with client:
        user = await client.upload_avatar(str(avatar), content_type="image/png")

    assert user.avatar_url == "https://example.com/avatar.jpg"
    req = mock.call_args.args[0]
    assert req.image.image == b"\x89PNGfake"
    assert req.image.filename == "avatar.png"
    assert req.image.content_type == "image/png"


async def test_update_presence(client):
    resp = presence_pb2.UpdatePresenceResponse()
    resp.status = "PRESENCE_STATUS_ONLINE"
    _mock_method(client, "account", "update_presence", resp)

    async with client:
        result = await client.update_presence(PresenceStatus.ONLINE)

    assert result is PresenceStatus.ONLINE


async def test_update_presence_offline_rejected(client):
    async with client:
        with pytest.raises(ValueError):
            await client.update_presence(PresenceStatus.OFFLINE)


async def test_update_settings(client):
    resp = account_pb2.UpdateSettingsResponse()
    resp.settings.timezone = "Europe/Rome"
    resp.settings.time_format = "TIME_FORMAT_24_HOUR"
    _mock_method(client, "account", "update_settings", resp)

    async with client:
        settings = await client.update_settings(
            timezone="Europe/Rome", time_format=TimeFormat.HOUR_24
        )

    assert settings.timezone == "Europe/Rome"
    assert settings.time_format is TimeFormat.HOUR_24


# --- Users -------------------------------------------------------------


async def test_get_user_by_id(client):
    resp = member_directory_pb2.GetUserResponse()
    resp.user.user.id = "u1"
    resp.user.user.login = "alice"
    resp.user.user.display_name = "Alice"
    resp.user.user.presence_status = "PRESENCE_STATUS_ONLINE"
    resp.user.roles.append("everyone")
    _mock_method(client, "users", "get_user", resp)

    async with client:
        member = await client.get_user(user_id="u1")

    assert member is not None
    assert member.user is not None
    assert member.user.login == "alice"
    assert "everyone" in member.roles


async def test_get_user_requires_one_target(client):
    with pytest.raises(ValueError):
        await client.get_user()
    with pytest.raises(ValueError):
        await client.get_user(user_id="u1", login="alice")


# --- Threads ----------------------------------------------------------


async def test_list_followed_threads(client):
    resp = threads_pb2.ListFollowedThreadsResponse()
    ft = resp.threads.add()
    ft.room.id = "r1"
    ft.room.name = "general"
    ft.root_message.id = "e1"
    ft.root_message.room_id = "r1"
    ft.root_message.actor_id = "u1"
    ft.root_message.body = "root"
    ft.root_message.created_at.FromJsonString("2026-01-01T00:00:00Z")
    ft.thread.thread_root_event_id = "e1"
    ft.thread.reply_count = 3
    ft.thread.last_reply_at.FromJsonString("2026-01-02T00:00:00Z")
    ft.thread.viewer_state.is_following = True
    ft.thread.viewer_state.has_unread = False
    resp.page.total_count = 1
    resp.page.has_more = False
    _mock_method(client, "threads", "list_followed_threads", resp)

    async with client:
        page = await client.list_followed_threads()

    assert page.page.total_count == 1
    assert page.threads[0].thread is not None
    assert page.threads[0].thread.reply_count == 3
    assert page.threads[0].thread.is_following is True


async def test_follow_and_unfollow_thread(client):
    follow_resp = threads_pb2.FollowThreadResponse(following=True)
    unfollow_resp = threads_pb2.UnfollowThreadResponse(following=False)
    _mock_method(client, "threads", "follow_thread", follow_resp)
    _mock_method(client, "threads", "unfollow_thread", unfollow_resp)

    async with client:
        assert await client.follow_thread("r1", "e1") is True
        assert await client.unfollow_thread("r1", "e1") is False


# --- Notifications ----------------------------------------------------


async def test_list_notifications(client):
    resp = notifications_pb2.ListNotificationsResponse()
    n = resp.notifications.add()
    n.id = "n1"
    n.created_at.FromJsonString("2026-01-01T00:00:00Z")
    n.actor.id = "u1"
    n.actor.login = "alice"
    n.actor.display_name = "Alice"
    n.mention.room.id = "r1"
    n.mention.room.name = "general"
    n.mention.event_id = "e1"
    resp.page.total_count = 1
    _mock_method(client, "notifications", "list_notifications", resp)

    async with client:
        page = await client.list_notifications()

    assert page.page.total_count == 1
    assert page.notifications[0].kind == "mention"
    assert page.notifications[0].room is not None
    assert page.notifications[0].room.name == "general"


async def test_dismiss_notification(client):
    resp = notifications_pb2.DismissNotificationResponse(dismissed=True)
    _mock_method(client, "notifications", "dismiss_notification", resp)

    async with client:
        assert await client.dismiss_notification("n1") is True


async def test_notification_preference(client):
    resp = notification_preferences_pb2.UpdateNotificationPreferenceResponse()
    resp.preference.level = "NOTIFICATION_LEVEL_MUTED"
    resp.preference.effective_level = "NOTIFICATION_LEVEL_MUTED"
    _mock_method(
        client,
        "notification_prefs",
        "update_room_notification_preference",
        resp,
    )

    async with client:
        pref = await client.update_room_notification_preference(
            "r1", NotificationLevel.MUTED
        )

    assert pref.level is NotificationLevel.MUTED
    assert pref.effective_level is NotificationLevel.MUTED


# --- Push -------------------------------------------------------------


async def test_subscribe_push(client):
    resp = push_notifications_pb2.SubscribePushResponse(subscribed=True)
    _mock_method(client, "push", "subscribe", resp)

    async with client:
        assert await client.subscribe_push("https://push", "k", "a") is True


# --- Voice calls ------------------------------------------------------


async def test_active_calls(client):
    resp = voice_calls_pb2.ListActiveCallsResponse()
    call = resp.calls.add()
    call.call_id = "c1"
    call.room.id = "r1"
    call.room.name = "voice"
    p = call.participants.add()
    p.user.id = "u1"
    p.user.login = "alice"
    p.user.display_name = "Alice"
    _mock_method(client, "voice_calls", "list_active_calls", resp)

    async with client:
        calls = await client.list_active_calls()

    assert len(calls) == 1
    assert calls[0].call_id == "c1"
    assert calls[0].room is not None
    assert calls[0].room.name == "voice"


# --- Assets -----------------------------------------------------------


async def test_get_asset_with_thumbnail(client):
    resp = attachments_pb2.GetAssetResponse()
    resp.asset.id = "a1"
    resp.asset.filename = "pic.png"
    resp.asset.content_type = "image/png"
    resp.asset.size = 1024
    resp.asset.asset_url.url = "https://cdn/pic.png"
    mock = _mock_method(client, "assets", "get_asset", resp)

    async with client:
        asset = await client.get_asset(
            "r1",
            "a1",
            thumbnail=ImageTransformOptions(128, 128, ImageFitMode.COVER),
        )

    assert asset is not None
    assert asset.filename == "pic.png"
    assert asset.asset_url is not None
    assert asset.asset_url.url == "https://cdn/pic.png"
    # verify the request encoded thumbnail options
    req = mock.call_args.args[0]
    assert req.thumbnail.width == 128
    assert req.thumbnail.height == 128


# --- Roles ------------------------------------------------------------


async def test_list_roles(client):
    resp = roles_pb2.ListRolesResponse()
    r1 = resp.roles.add()
    r1.name = "everyone"
    r1.display_name = "Everyone"
    r1.is_system = True
    r1.position = 0
    r2 = resp.roles.add()
    r2.name = "admin"
    r2.display_name = "Admin"
    r2.position = 10
    _mock_method(client, "roles", "list_roles", resp)

    async with client:
        roles = await client.list_roles()

    assert [r.name for r in roles] == ["everyone", "admin"]
    assert roles[0].is_system is True


# --- Asset uploads ---------------------------------------------------


async def test_asset_upload_end_to_end(client, tmp_path):
    import hashlib

    payload = b"hello world" * 100
    file = tmp_path / "greet.txt"
    file.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()

    create_resp = asset_uploads_pb2.CreateUploadResponse()
    create_resp.upload.upload_id = "up1"
    create_resp.upload.room_id = "r1"
    create_resp.upload.status = "ASSET_UPLOAD_STATUS_OPEN"
    create_resp.upload.committed_offset = 0
    create_resp.upload.size = len(payload)
    create_resp.upload.max_chunk_size = 4096
    create_resp.upload.sha256 = sha
    create_mock = _mock_method(
        client, "asset_uploads", "create_upload", create_resp
    )

    chunk_resp = asset_uploads_pb2.UploadChunkResponse()
    chunk_resp.upload.upload_id = "up1"
    chunk_resp.upload.room_id = "r1"
    chunk_resp.upload.status = "ASSET_UPLOAD_STATUS_OPEN"
    chunk_resp.upload.committed_offset = len(payload)
    chunk_resp.upload.size = len(payload)
    chunk_resp.upload.max_chunk_size = 4096
    chunk_resp.upload.sha256 = sha
    _mock_method(client, "asset_uploads", "upload_chunk", chunk_resp)

    complete_resp = asset_uploads_pb2.CompleteUploadResponse()
    complete_resp.upload.upload_id = "up1"
    complete_resp.upload.room_id = "r1"
    complete_resp.upload.status = "ASSET_UPLOAD_STATUS_COMPLETED"
    complete_resp.upload.committed_offset = len(payload)
    complete_resp.upload.size = len(payload)
    complete_resp.upload.sha256 = sha
    complete_resp.upload.asset_id = "a1"
    complete_resp.asset.id = "a1"
    complete_resp.asset.filename = "greet.txt"
    complete_resp.asset.content_type = "text/plain"
    complete_resp.asset.size = len(payload)
    _mock_method(client, "asset_uploads", "complete_upload", complete_resp)

    async with client:
        asset = await client.upload_attachment(
            "r1", file, content_type="text/plain"
        )

    assert asset.id == "a1"
    assert asset.filename == "greet.txt"

    create_req = create_mock.call_args.args[0]
    assert create_req.sha256 == sha
    assert create_req.size == len(payload)


# --- External identities --------------------------------------------


async def test_list_external_identities(client):
    resp = external_identities_pb2.ListExternalIdentitiesResponse()
    p = resp.providers.add()
    p.provider.id = "github"
    p.provider.type = "github"
    p.provider.label = "GitHub"
    p.provider.login_url = "/auth/github/login"
    p.link_url = "/auth/github/link"
    p.linked = True
    p.linked_identity_subject_hash = "sha_xyz"
    li = resp.linked_identities.add()
    li.provider_id = "github"
    li.provider_type = "github"
    li.provider_label = "GitHub"
    li.subject_hash = "sha_xyz"
    _mock_method(client, "account", "list_external_identities", resp)

    async with client:
        providers, linked = await client.list_external_identities()

    assert providers[0].linked is True
    assert providers[0].provider is not None
    assert providers[0].provider.id == "github"
    assert linked[0].subject_hash == "sha_xyz"


# --- Admin (structural smoke tests) ----------------------------------


async def test_admin_list_room_groups(client):
    resp = room_layout_pb2.ListRoomGroupsResponse()
    g = resp.groups.add()
    g.id = "g1"
    g.name = "General"
    room_item = g.items.add()
    room_item.room.id = "r1"
    room_item.room.kind = "ROOM_KIND_CHANNEL"
    room_item.room.name = "chat"
    link_item = g.items.add()
    link_item.sidebar_link.id = "sl1"
    link_item.sidebar_link.label = "Docs"
    link_item.sidebar_link.url = "https://x"
    g.can_create_room = True
    _mock_method(client, "admin_room_layout", "list_room_groups", resp)

    async with client:
        groups = await client.admin_list_room_groups()

    assert len(groups) == 1
    assert groups[0].name == "General"
    assert groups[0].rooms[0].id == "r1"
    assert groups[0].sidebar_links[0].label == "Docs"
    assert groups[0].can_create_room is True


async def test_admin_create_sidebar_link(client):
    resp = room_layout_pb2.CreateSidebarLinkResponse()
    resp.sidebar_link.id = "sl1"
    resp.sidebar_link.label = "Docs"
    resp.sidebar_link.url = "https://x"
    _mock_method(client, "admin_room_layout", "create_sidebar_link", resp)

    async with client:
        result = await client.admin_create_sidebar_link("g1", "Docs", "https://x")

    assert result == {"id": "sl1", "label": "Docs", "url": "https://x"}


async def test_admin_update_server_config(client):
    resp = admin_server_pb2.UpdateServerConfigResponse()
    resp.config.server_name = "MyServer"
    resp.config.motd = "hi"
    resp.public_profile.name = "MyServer"
    resp.public_profile.version = "0.4.2"
    _mock_method(client, "admin_server", "update_server_config", resp)

    async with client:
        config, profile = await client.admin_update_server_config(
            server_name="MyServer", motd="hi"
        )

    assert config.server_name == "MyServer"
    assert profile.version == "0.4.2"

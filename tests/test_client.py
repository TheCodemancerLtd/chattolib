"""Tests for ChattoClient against mocked Connect endpoints."""

from __future__ import annotations

import httpx
import pytest
import respx

from chattolib.client import ChattoClient
from chattolib.exceptions import ChattoAuthError, ChattoConnectError
from chattolib.types import (
    ImageFitMode,
    ImageTransformOptions,
    NotificationLevel,
    PresenceStatus,
    RoomKind,
    TimeFormat,
)

BASE = "https://chat.chatto.run"
CONNECT = "/api/connect"
API_V1 = "chatto.api.v1"
ADMIN_V1 = "chatto.admin.v1"
DISCOVERY_V1 = "chatto.discovery.v1"


def _mount(api: respx.Router, service: str, method: str) -> respx.Route:
    return api.post(f"{CONNECT}/{service}/{method}")


@pytest.fixture
def mock_api():
    with respx.mock(base_url=BASE) as api:
        yield api


@pytest.fixture
def client():
    return ChattoClient(token="test-token")


# --- Transport-level ----------------------------------------------------


async def test_connect_error(mock_api, client):
    _mount(mock_api, f"{API_V1}.ViewerService", "GetViewer").mock(
        return_value=httpx.Response(
            403,
            headers={"content-type": "application/json"},
            json={"code": "permission_denied", "message": "Nope"},
        )
    )
    async with client:
        with pytest.raises(ChattoConnectError) as exc:
            await client.me()
    assert exc.value.code == "permission_denied"
    assert exc.value.status_code == 403


async def test_auth_error(mock_api, client):
    _mount(mock_api, f"{API_V1}.ViewerService", "GetViewer").mock(
        return_value=httpx.Response(401)
    )
    async with client:
        with pytest.raises(ChattoAuthError):
            await client.me()


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
        client = await ChattoClient.login("alice", "password123")
        assert client.token == "cht_abc123"
        assert client.session_cookie == "xyz"
        await client.close()


async def test_login_invalid():
    with respx.mock(base_url=BASE) as api:
        api.post("/auth/login").mock(
            return_value=httpx.Response(401, json={"error": "Invalid credentials"})
        )
        with pytest.raises(ChattoAuthError, match="Invalid credentials"):
            await ChattoClient.login("bad", "creds")


# --- Server discovery ---------------------------------------------------


async def test_get_server(mock_api):
    _mount(mock_api, f"{DISCOVERY_V1}.ServerDiscoveryService", "GetServer").mock(
        return_value=httpx.Response(
            200,
            json={
                "profile": {"name": "Chatto HQ", "version": "0.4.2"},
                "login": {"directRegistrationEnabled": True, "authorizeUrl": "/oauth"},
            },
        )
    )
    async with ChattoClient() as c:
        profile, login = await c.get_server()
    assert profile.name == "Chatto HQ"
    assert profile.version == "0.4.2"
    assert login.direct_registration_enabled is True
    assert login.authorize_url == "/oauth"


# --- Viewer -------------------------------------------------------------


async def test_me(mock_api, client):
    _mount(mock_api, f"{API_V1}.ViewerService", "GetViewer").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {
                    "profile": {
                        "id": "u1",
                        "login": "alice",
                        "displayName": "Alice",
                        "presenceStatus": "PRESENCE_STATUS_ONLINE",
                    },
                    "hasVerifiedEmail": True,
                    "settings": {"timezone": "UTC", "timeFormat": "TIME_FORMAT_24_HOUR"},
                    "hasPassword": True,
                }
            },
        )
    )
    async with client:
        user = await client.me()
    assert user.id == "u1"
    assert user.login == "alice"
    assert user.display_name == "Alice"
    assert user.presence_status is PresenceStatus.ONLINE


# --- Room directory ----------------------------------------------------


async def test_list_rooms(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomDirectoryService", "ListRooms").mock(
        return_value=httpx.Response(
            200,
            json={
                "rooms": [
                    {
                        "room": {
                            "id": "r1",
                            "kind": "ROOM_KIND_CHANNEL",
                            "name": "general",
                            "groupId": "g1",
                        },
                        "viewerState": {"isMember": True, "hasUnread": False},
                    }
                ]
            },
        )
    )
    async with client:
        rooms = await client.list_rooms()
    assert len(rooms) == 1
    assert rooms[0].room is not None
    assert rooms[0].room.name == "general"
    assert rooms[0].room.kind is RoomKind.CHANNEL
    assert rooms[0].viewer_state.is_member is True


# --- Messages ----------------------------------------------------------


async def test_post_message(mock_api, client):
    _mount(mock_api, f"{API_V1}.MessageService", "CreateMessage").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "id": "e1",
                    "roomId": "r1",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "actorId": "u1",
                    "body": "Hello!",
                }
            },
        )
    )
    async with client:
        message = await client.post_message("r1", "Hello!")
    assert message.id == "e1"
    assert message.body == "Hello!"
    assert message.room_id == "r1"


async def test_update_message(mock_api, client):
    _mount(mock_api, f"{API_V1}.MessageService", "UpdateMessage").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "id": "e1",
                    "roomId": "r1",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "actorId": "u1",
                    "body": "edited",
                    "updatedAt": "2026-01-01T00:01:00Z",
                }
            },
        )
    )
    async with client:
        m = await client.update_message("r1", "e1", body="edited")
    assert m.body == "edited"
    assert m.updated_at is not None


async def test_delete_message(mock_api, client):
    _mount(mock_api, f"{API_V1}.MessageService", "DeleteMessage").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    async with client:
        assert await client.delete_message("r1", "e1") is True


async def test_add_reaction(mock_api, client):
    _mount(mock_api, f"{API_V1}.MessageService", "AddReaction").mock(
        return_value=httpx.Response(
            200,
            json={"added": True, "reaction": {"emoji": "thumbsup", "count": 1}},
        )
    )
    async with client:
        assert await client.add_reaction("r1", "e1", "thumbsup") is True


async def test_remove_reaction(mock_api, client):
    _mount(mock_api, f"{API_V1}.MessageService", "RemoveReaction").mock(
        return_value=httpx.Response(200, json={"removed": True})
    )
    async with client:
        assert await client.remove_reaction("r1", "e1", "thumbsup") is True


# --- Room lifecycle ---------------------------------------------------


async def test_create_room(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomService", "CreateRoom").mock(
        return_value=httpx.Response(
            200,
            json={
                "room": {
                    "id": "r1",
                    "kind": "ROOM_KIND_CHANNEL",
                    "name": "general",
                    "groupId": "g1",
                }
            },
        )
    )
    async with client:
        room = await client.create_room("general", "g1")
    assert room.id == "r1"
    assert room.name == "general"
    assert room.group_id == "g1"


async def test_archive_room(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomService", "ArchiveRoom").mock(
        return_value=httpx.Response(
            200,
            json={"room": {"id": "r1", "name": "general", "archived": True}},
        )
    )
    async with client:
        room = await client.archive_room("r1")
    assert room.archived is True


async def test_ban_member(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomService", "BanMember").mock(
        return_value=httpx.Response(200, json={"banned": True})
    )
    async with client:
        assert await client.ban_member("r1", "u2", "spam") is True


async def test_start_dm(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomService", "StartDM").mock(
        return_value=httpx.Response(
            200, json={"room": {"id": "r1", "kind": "ROOM_KIND_DM"}}
        )
    )
    async with client:
        room = await client.start_dm(["u1", "u2"])
    assert room.id == "r1"
    assert room.kind is RoomKind.DM


# --- Room timeline ----------------------------------------------------


async def test_get_room_events(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomService", "GetRoomEvents").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": {
                    "events": [
                        {
                            "id": "e1",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "actorId": "u1",
                            "messagePosted": {
                                "message": {
                                    "id": "e1",
                                    "roomId": "r1",
                                    "createdAt": "2026-01-01T00:00:00Z",
                                    "actorId": "u1",
                                    "body": "hi",
                                }
                            },
                        }
                    ],
                    "hasOlder": False,
                    "hasNewer": False,
                    "startCursor": "cA",
                    "endCursor": "cB",
                    "includes": {
                        "users": {
                            "u1": {
                                "id": "u1",
                                "login": "alice",
                                "displayName": "Alice",
                            }
                        }
                    },
                }
            },
        )
    )
    async with client:
        page = await client.get_room_events("r1", limit=50)
    assert len(page.events) == 1
    assert page.events[0].kind == "message_posted"
    assert page.events[0].message is not None
    assert page.events[0].message.body == "hi"
    assert page.users_by_id["u1"].login == "alice"


async def test_mark_room_as_read(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoomService", "MarkRoomAsRead").mock(
        return_value=httpx.Response(
            200,
            json={
                "lastReadAt": "2026-01-01T00:00:00Z",
                "previousLastReadAt": "2025-12-31T00:00:00Z",
            },
        )
    )
    async with client:
        last, previous = await client.mark_room_as_read("r1", up_to_event_id="e1")
    assert last is not None
    assert previous is not None


# --- Profile / account ------------------------------------------------


async def test_update_profile(mock_api, client):
    _mount(mock_api, f"{API_V1}.MyAccountService", "UpdateProfile").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {
                    "id": "u1",
                    "login": "newname",
                    "displayName": "New Name",
                    "presenceStatus": "PRESENCE_STATUS_ONLINE",
                }
            },
        )
    )
    async with client:
        user = await client.update_profile(login="newname", display_name="New Name")
    assert user.login == "newname"
    assert user.display_name == "New Name"


async def test_upload_avatar(mock_api, client, tmp_path):
    _mount(mock_api, f"{API_V1}.MyAccountService", "UploadAvatar").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {
                    "id": "u1",
                    "login": "alice",
                    "displayName": "Alice",
                    "avatarUrl": "https://example.com/avatar.jpg",
                }
            },
        )
    )
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(b"\x89PNGfake")
    async with client:
        user = await client.upload_avatar(str(avatar), content_type="image/png")
    assert user.avatar_url == "https://example.com/avatar.jpg"


async def test_update_presence(mock_api, client):
    _mount(mock_api, f"{API_V1}.MyAccountService", "UpdatePresence").mock(
        return_value=httpx.Response(
            200, json={"status": "PRESENCE_STATUS_ONLINE"}
        )
    )
    async with client:
        result = await client.update_presence(PresenceStatus.ONLINE)
    assert result is PresenceStatus.ONLINE


async def test_update_presence_offline_rejected(client):
    async with client:
        with pytest.raises(ValueError):
            await client.update_presence(PresenceStatus.OFFLINE)


async def test_update_settings(mock_api, client):
    _mount(mock_api, f"{API_V1}.MyAccountService", "UpdateSettings").mock(
        return_value=httpx.Response(
            200,
            json={
                "settings": {"timezone": "Europe/Rome", "timeFormat": "TIME_FORMAT_24_HOUR"}
            },
        )
    )
    async with client:
        settings = await client.update_settings(
            timezone="Europe/Rome", time_format=TimeFormat.HOUR_24
        )
    assert settings.timezone == "Europe/Rome"
    assert settings.time_format is TimeFormat.HOUR_24


# --- Users -------------------------------------------------------------


async def test_get_user_by_id(mock_api, client):
    _mount(mock_api, f"{API_V1}.UserService", "GetUser").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {
                    "user": {
                        "id": "u1",
                        "login": "alice",
                        "displayName": "Alice",
                        "presenceStatus": "PRESENCE_STATUS_ONLINE",
                    },
                    "roles": ["everyone"],
                }
            },
        )
    )
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


async def test_list_followed_threads(mock_api, client):
    _mount(mock_api, f"{API_V1}.ThreadService", "ListFollowedThreads").mock(
        return_value=httpx.Response(
            200,
            json={
                "threads": [
                    {
                        "room": {"id": "r1", "name": "general"},
                        "rootMessage": {
                            "id": "e1",
                            "roomId": "r1",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "actorId": "u1",
                            "body": "root",
                        },
                        "thread": {
                            "threadRootEventId": "e1",
                            "replyCount": 3,
                            "lastReplyAt": "2026-01-02T00:00:00Z",
                            "viewerState": {"isFollowing": True, "hasUnread": False},
                        },
                    }
                ],
                "page": {"totalCount": 1, "hasMore": False},
            },
        )
    )
    async with client:
        page = await client.list_followed_threads()
    assert page.page.total_count == 1
    assert page.threads[0].thread is not None
    assert page.threads[0].thread.reply_count == 3
    assert page.threads[0].thread.is_following is True


async def test_follow_and_unfollow_thread(mock_api, client):
    _mount(mock_api, f"{API_V1}.ThreadService", "FollowThread").mock(
        return_value=httpx.Response(200, json={"following": True})
    )
    _mount(mock_api, f"{API_V1}.ThreadService", "UnfollowThread").mock(
        return_value=httpx.Response(200, json={"following": False})
    )
    async with client:
        assert await client.follow_thread("r1", "e1") is True
        assert await client.unfollow_thread("r1", "e1") is False


# --- Notifications ----------------------------------------------------


async def test_list_notifications(mock_api, client):
    _mount(mock_api, f"{API_V1}.NotificationService", "ListNotifications").mock(
        return_value=httpx.Response(
            200,
            json={
                "notifications": [
                    {
                        "id": "n1",
                        "createdAt": "2026-01-01T00:00:00Z",
                        "actor": {
                            "id": "u1",
                            "login": "alice",
                            "displayName": "Alice",
                        },
                        "mention": {
                            "room": {"id": "r1", "name": "general"},
                            "eventId": "e1",
                        },
                    }
                ],
                "page": {"totalCount": 1, "hasMore": False},
            },
        )
    )
    async with client:
        page = await client.list_notifications()
    assert page.page.total_count == 1
    assert page.notifications[0].kind == "mention"
    assert page.notifications[0].room is not None
    assert page.notifications[0].room.name == "general"


async def test_dismiss_notification(mock_api, client):
    _mount(mock_api, f"{API_V1}.NotificationService", "DismissNotification").mock(
        return_value=httpx.Response(200, json={"dismissed": True})
    )
    async with client:
        assert await client.dismiss_notification("n1") is True


async def test_notification_preference(mock_api, client):
    _mount(
        mock_api,
        f"{API_V1}.NotificationPreferencesService",
        "UpdateRoomNotificationPreference",
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "preference": {
                    "level": "NOTIFICATION_LEVEL_MUTED",
                    "effectiveLevel": "NOTIFICATION_LEVEL_MUTED",
                }
            },
        )
    )
    async with client:
        pref = await client.update_room_notification_preference(
            "r1", NotificationLevel.MUTED
        )
    assert pref.level is NotificationLevel.MUTED
    assert pref.effective_level is NotificationLevel.MUTED


# --- Push -------------------------------------------------------------


async def test_subscribe_push(mock_api, client):
    _mount(mock_api, f"{API_V1}.PushNotificationService", "Subscribe").mock(
        return_value=httpx.Response(200, json={"subscribed": True})
    )
    async with client:
        assert await client.subscribe_push("https://push", "k", "a") is True


# --- Voice calls ------------------------------------------------------


async def test_active_calls(mock_api, client):
    _mount(mock_api, f"{API_V1}.VoiceCallService", "ListActiveCalls").mock(
        return_value=httpx.Response(
            200,
            json={
                "calls": [
                    {
                        "callId": "c1",
                        "room": {"id": "r1", "name": "voice"},
                        "participants": [{"userId": "u1"}],
                    }
                ]
            },
        )
    )
    async with client:
        calls = await client.list_active_calls()
    assert len(calls) == 1
    assert calls[0].call_id == "c1"
    assert calls[0].room is not None
    assert calls[0].room.name == "voice"


# --- Assets -----------------------------------------------------------


async def test_get_asset_with_thumbnail(mock_api, client):
    route = _mount(mock_api, f"{API_V1}.AssetService", "GetAsset").mock(
        return_value=httpx.Response(
            200,
            json={
                "asset": {
                    "id": "a1",
                    "filename": "pic.png",
                    "contentType": "image/png",
                    "size": 1024,
                    "assetUrl": {"url": "https://cdn/pic.png"},
                }
            },
        )
    )
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
    # ensure the request encoded thumbnail options with the wire enum
    body = route.calls.last.request.content
    assert b'"IMAGE_FIT_MODE_COVER"' in body


# --- Roles ------------------------------------------------------------


async def test_list_roles(mock_api, client):
    _mount(mock_api, f"{API_V1}.RoleService", "ListRoles").mock(
        return_value=httpx.Response(
            200,
            json={
                "roles": [
                    {
                        "name": "everyone",
                        "displayName": "Everyone",
                        "isSystem": True,
                        "position": 0,
                    },
                    {"name": "admin", "displayName": "Admin", "position": 10},
                ]
            },
        )
    )
    async with client:
        roles = await client.list_roles()
    assert [r.name for r in roles] == ["everyone", "admin"]
    assert roles[0].is_system is True


# --- Asset uploads ---------------------------------------------------


async def test_asset_upload_end_to_end(mock_api, client, tmp_path):
    import hashlib

    payload = b"hello world" * 100  # 1100 bytes; well under the mock chunk size
    file = tmp_path / "greet.txt"
    file.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()

    create = _mount(mock_api, f"{API_V1}.AssetUploadService", "CreateUpload").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload": {
                    "uploadId": "up1",
                    "roomId": "r1",
                    "status": "ASSET_UPLOAD_STATUS_OPEN",
                    "committedOffset": 0,
                    "size": len(payload),
                    "maxChunkSize": 4096,
                    "sha256": sha,
                }
            },
        )
    )
    _mount(mock_api, f"{API_V1}.AssetUploadService", "UploadChunk").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload": {
                    "uploadId": "up1",
                    "roomId": "r1",
                    "status": "ASSET_UPLOAD_STATUS_OPEN",
                    "committedOffset": len(payload),
                    "size": len(payload),
                    "maxChunkSize": 4096,
                    "sha256": sha,
                }
            },
        )
    )
    _mount(mock_api, f"{API_V1}.AssetUploadService", "CompleteUpload").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload": {
                    "uploadId": "up1",
                    "roomId": "r1",
                    "status": "ASSET_UPLOAD_STATUS_COMPLETED",
                    "committedOffset": len(payload),
                    "size": len(payload),
                    "sha256": sha,
                    "assetId": "a1",
                },
                "asset": {
                    "id": "a1",
                    "filename": "greet.txt",
                    "contentType": "text/plain",
                    "size": len(payload),
                },
            },
        )
    )
    async with client:
        asset = await client.upload_attachment(
            "r1", file, content_type="text/plain"
        )
    assert asset.id == "a1"
    assert asset.filename == "greet.txt"

    # CreateUpload should have carried the correct sha and size.
    body = create.calls.last.request.content
    assert sha.encode() in body
    assert str(len(payload)).encode() in body


# --- External identities --------------------------------------------


async def test_list_external_identities(mock_api, client):
    _mount(mock_api, f"{API_V1}.MyAccountService", "ListExternalIdentities").mock(
        return_value=httpx.Response(
            200,
            json={
                "providers": [
                    {
                        "provider": {
                            "id": "github",
                            "type": "github",
                            "label": "GitHub",
                            "loginUrl": "/auth/github/login",
                        },
                        "linkUrl": "/auth/github/link",
                        "linked": True,
                        "linkedIdentitySubjectHash": "sha_xyz",
                    }
                ],
                "linkedIdentities": [
                    {
                        "providerId": "github",
                        "providerType": "github",
                        "providerLabel": "GitHub",
                        "subjectHash": "sha_xyz",
                    }
                ],
            },
        )
    )
    async with client:
        providers, linked = await client.list_external_identities()
    assert providers[0].linked is True
    assert providers[0].provider is not None
    assert providers[0].provider.id == "github"
    assert linked[0].subject_hash == "sha_xyz"


# --- Admin (structural smoke tests) ----------------------------------


async def test_admin_list_room_groups(mock_api, client):
    _mount(mock_api, f"{ADMIN_V1}.AdminRoomLayoutService", "ListRoomGroups").mock(
        return_value=httpx.Response(
            200,
            json={
                "groups": [
                    {
                        "id": "g1",
                        "name": "General",
                        "items": [
                            {"room": {"id": "r1", "kind": "ROOM_KIND_CHANNEL", "name": "chat"}},
                            {"sidebarLink": {"id": "sl1", "label": "Docs", "url": "https://x"}},
                        ],
                        "canCreateRoom": True,
                    }
                ]
            },
        )
    )
    async with client:
        groups = await client.admin_list_room_groups()
    assert len(groups) == 1
    assert groups[0].name == "General"
    assert groups[0].rooms[0].id == "r1"
    assert groups[0].sidebar_links[0].label == "Docs"
    assert groups[0].can_create_room is True


async def test_admin_create_sidebar_link(mock_api, client):
    _mount(mock_api, f"{ADMIN_V1}.AdminRoomLayoutService", "CreateSidebarLink").mock(
        return_value=httpx.Response(
            200,
            json={"sidebarLink": {"id": "sl1", "label": "Docs", "url": "https://x"}},
        )
    )
    async with client:
        result = await client.admin_create_sidebar_link("g1", "Docs", "https://x")
    assert result == {"id": "sl1", "label": "Docs", "url": "https://x"}


async def test_admin_update_server_config(mock_api, client):
    _mount(mock_api, f"{ADMIN_V1}.AdminServerService", "UpdateServerConfig").mock(
        return_value=httpx.Response(
            200,
            json={
                "config": {"serverName": "MyServer", "motd": "hi"},
                "publicProfile": {"name": "MyServer", "version": "0.4.2"},
            },
        )
    )
    async with client:
        config, profile = await client.admin_update_server_config(
            server_name="MyServer", motd="hi"
        )
    assert config.server_name == "MyServer"
    assert profile.version == "0.4.2"

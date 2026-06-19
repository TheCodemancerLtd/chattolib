"""Tests for ChattoClient using respx to mock HTTP."""

import httpx
import pytest
import respx

from chattolib.client import ChattoClient
from chattolib.exceptions import ChattoAuthError, ChattoGraphQLError
from chattolib.types import PresenceStatusInput


@pytest.fixture
def mock_api():
    with respx.mock(base_url="https://chat.chatto.run") as api:
        yield api


@pytest.fixture
def client():
    return ChattoClient(token="test-token")


def _gql_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


async def test_me(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "viewer": {
                    "user": {
                        "id": "u1",
                        "login": "alice",
                        "displayName": "Alice",
                        "createdAt": "2025-01-01T00:00:00",
                        "avatarUrl": None,
                        "presenceStatus": "ONLINE",
                        "settings": None,
                    }
                }
            }
        )
    )
    async with client:
        user = await client.me()
    assert user.id == "u1"
    assert user.login == "alice"
    assert user.display_name == "Alice"


async def test_rooms(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "server": {
                    "rooms": [
                        {
                            "id": "r1",
                            "type": "CHANNEL",
                            "name": "general",
                            "description": None,
                            "archived": False,
                            "groupId": "g1",
                            "hasUnread": False,
                        }
                    ]
                }
            }
        )
    )
    async with client:
        rooms = await client.rooms()
    assert len(rooms) == 1
    assert rooms[0].name == "general"
    assert rooms[0].type.value == "CHANNEL"


async def test_graphql_error(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "Not authorized"}]},
        )
    )
    async with client:
        with pytest.raises(ChattoGraphQLError, match="Not authorized"):
            await client.me()


async def test_auth_error(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=httpx.Response(401))
    async with client:
        with pytest.raises(ChattoAuthError):
            await client.me()


async def test_post_message(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {"postMessage": {"id": "e1", "createdAt": "2025-01-01T00:00:00"}}
        )
    )
    async with client:
        result = await client.post_message("r1", "Hello!")
    assert result["id"] == "e1"


async def test_room_events(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "room": {
                    "events": {
                        "events": [
                            {
                                "id": "e1",
                                "createdAt": "2025-01-01T00:00:00",
                                "actorId": "u1",
                                "actor": {
                                    "id": "u1",
                                    "login": "alice",
                                    "displayName": "Alice",
                                    "avatarUrl": None,
                                    "presenceStatus": "ONLINE",
                                },
                                "event": {
                                    "roomId": "r1",
                                    "body": "Hello",
                                    "updatedAt": None,
                                    "attachments": [],
                                    "reactions": [],
                                    "inReplyTo": None,
                                    "threadRootEventId": None,
                                    "replyCount": 0,
                                    "lastReplyAt": None,
                                    "echoOfEventId": None,
                                    "echoFromThreadRootEventId": None,
                                    "viewerIsFollowingThread": None,
                                    "linkPreview": None,
                                },
                            }
                        ],
                        "hasOlder": False,
                        "hasNewer": False,
                        "startCursor": None,
                        "endCursor": None,
                    }
                }
            }
        )
    )
    async with client:
        page = await client.room_events("r1", limit=10)
    assert len(page.events) == 1
    assert page.events[0].body == "Hello"
    assert page.events[0].actor.login == "alice"
    assert page.events[0].thread_root_event_id is None


async def test_login():
    with respx.mock(base_url="https://chat.chatto.run") as api:
        api.post("/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "token": "cht_abc123",
                    "user": {"id": "u1", "login": "alice"},
                },
                headers={"set-cookie": "chatto_session=xyz; Path=/; HttpOnly"},
            )
        )
        client = await ChattoClient.login("alice", "password123")
        assert client._token == "cht_abc123"
        assert client._session_cookie == "xyz"
        await client.close()


async def test_login_invalid():
    with respx.mock(base_url="https://chat.chatto.run") as api:
        api.post("/auth/login").mock(
            return_value=httpx.Response(401, json={"error": "Invalid credentials"})
        )
        with pytest.raises(ChattoAuthError, match="Invalid credentials"):
            await ChattoClient.login("bad", "creds")


async def test_update_message(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"updateMessage": True}))
    async with client:
        result = await client.update_message("r1", "e1", "edited body")
    assert result is True


async def test_delete_message(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"deleteMessage": True}))
    async with client:
        result = await client.delete_message("r1", "e1")
    assert result is True


async def test_add_reaction(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"addReaction": True}))
    async with client:
        result = await client.add_reaction("r1", "e1", "thumbsup")
    assert result is True


async def test_remove_reaction(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"removeReaction": True}))
    async with client:
        result = await client.remove_reaction("r1", "e1", "thumbsup")
    assert result is True


async def test_create_room(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "createRoom": {
                    "id": "r1",
                    "type": "CHANNEL",
                    "name": "general",
                    "description": None,
                    "groupId": "g1",
                }
            }
        )
    )
    async with client:
        room = await client.create_room("general", "g1")
    assert room.id == "r1"
    assert room.name == "general"
    assert room.group_id == "g1"


async def test_update_profile(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "updateProfile": {
                    "id": "u1",
                    "login": "newname",
                    "displayName": "New Name",
                    "avatarUrl": None,
                    "presenceStatus": "ONLINE",
                }
            }
        )
    )
    async with client:
        user = await client.update_profile("u1", login="newname", display_name="New Name")
    assert user.login == "newname"
    assert user.display_name == "New Name"


async def test_update_presence(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"updateMyPresence": True}))
    async with client:
        result = await client.update_presence(PresenceStatusInput.ONLINE)
    assert result is True


async def test_upload_avatar(mock_api, client, tmp_path):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {"uploadAvatar": {"id": "u1", "avatarUrl": "https://example.com/avatar.jpg"}}
        )
    )
    avatar = tmp_path / "avatar.jpg"
    avatar.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    async with client:
        result = await client.upload_avatar(str(avatar), "u1")
    assert result["avatarUrl"] == "https://example.com/avatar.jpg"


async def test_user(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "user": {
                    "id": "u1",
                    "login": "alice",
                    "displayName": "Alice",
                    "createdAt": "2025-01-01T00:00:00",
                    "avatarUrl": None,
                    "presenceStatus": "ONLINE",
                }
            }
        )
    )
    async with client:
        user = await client.user("u1")
    assert user.id == "u1"
    assert user.login == "alice"


async def test_user_by_login(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "userByLogin": {
                    "id": "u1",
                    "login": "alice",
                    "displayName": "Alice",
                    "createdAt": None,
                    "avatarUrl": None,
                    "presenceStatus": "OFFLINE",
                }
            }
        )
    )
    async with client:
        user = await client.user_by_login("alice")
    assert user.login == "alice"


async def test_start_dm(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"startDM": {"id": "r1", "name": "DM"}})
    )
    async with client:
        result = await client.start_dm(["u1", "u2"])
    assert result["id"] == "r1"


async def test_dismiss_notification(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"dismissNotification": True}))
    async with client:
        result = await client.dismiss_notification("n1")
    assert result is True


async def test_dismiss_all_notifications(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"dismissAllNotifications": True})
    )
    async with client:
        result = await client.dismiss_all_notifications()
    assert result is True


async def test_followed_threads(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "viewer": {
                    "followedThreads": {
                        "threads": [
                            {
                                "roomId": "r1",
                                "threadRootEventId": "e1",
                                "replyCount": 3,
                                "lastReplyAt": "2025-01-01T00:00:00",
                                "hasUnread": True,
                            }
                        ],
                        "totalCount": 1,
                        "hasMore": False,
                    },
                    "hasUnreadFollowedThreads": True,
                }
            }
        )
    )
    async with client:
        page = await client.followed_threads()
    assert page.total_count == 1
    assert page.threads[0].room_id == "r1"
    assert page.threads[0].has_unread is True


async def test_notifications(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "viewer": {
                    "notifications": {
                        "items": [
                            {
                                "id": "n1",
                                "createdAt": "2025-01-01T00:00:00",
                                "summary": "Mention",
                                "actor": None,
                                "room": {"id": "r1", "name": "general"},
                                "eventId": "e1",
                                "threadRootEventId": None,
                            }
                        ],
                        "totalCount": 1,
                        "hasMore": False,
                    },
                    "hasNotifications": True,
                }
            }
        )
    )
    async with client:
        page = await client.notifications()
    assert page.total_count == 1
    assert page.items[0]["id"] == "n1"


async def test_archive_unarchive_room(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {"archiveRoom": {"id": "r1", "name": "general", "archived": True}}
        )
    )
    async with client:
        room = await client.archive_room("r1")
    assert room.id == "r1"
    assert room.archived is True


async def test_create_room_group(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {"createRoomGroup": {"id": "g1", "name": "Team", "description": ""}}
        )
    )
    async with client:
        group = await client.create_room_group("Team")
    assert group.id == "g1"
    assert group.name == "Team"


async def test_ban_room_member(mock_api, client):
    mock_api.post("/api/graphql").mock(return_value=_gql_response({"banRoomMember": True}))
    async with client:
        result = await client.ban_room_member("r1", "u2", "spam")
    assert result is True


async def test_update_presence_offline_rejected(client):
    from chattolib.types import PresenceStatus

    async with client:
        with pytest.raises(ValueError):
            await client.update_presence(PresenceStatus.OFFLINE)

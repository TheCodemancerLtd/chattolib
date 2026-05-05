"""Tests for ChattoClient using respx to mock HTTP."""

import pytest
import respx
import httpx

from chattolib.client import ChattoClient
from chattolib.exceptions import ChattoGraphQLError, ChattoAuthError
from chattolib.types import PresenceStatus


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
                "me": {
                    "id": "u1",
                    "login": "alice",
                    "displayName": "Alice",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "avatarUrl": None,
                    "presenceStatus": "ONLINE",
                }
            }
        )
    )
    async with client:
        user = await client.me()
    assert user.id == "u1"
    assert user.login == "alice"
    assert user.display_name == "Alice"


async def test_spaces(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "spaces": [
                    {
                        "id": "s1",
                        "name": "General",
                        "description": None,
                        "memberCount": 5,
                        "roomCount": 3,
                        "viewerIsMember": True,
                    }
                ]
            }
        )
    )
    async with client:
        spaces = await client.spaces()
    assert len(spaces) == 1
    assert spaces[0].name == "General"
    assert spaces[0].viewer_is_member is True


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
            {"postMessage": {"id": "e1", "createdAt": "2025-01-01T00:00:00Z"}}
        )
    )
    async with client:
        result = await client.post_message("s1", "r1", "Hello!")
    assert result["id"] == "e1"


async def test_room_events(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "roomEvents": {
                    "events": [
                        {
                            "id": "e1",
                            "createdAt": "2025-01-01T00:00:00Z",
                            "actorId": "u1",
                            "actor": {
                                "id": "u1",
                                "login": "alice",
                                "displayName": "Alice",
                                "avatarUrl": None,
                            },
                            "event": {
                                "spaceId": "s1",
                                "roomId": "r1",
                                "body": "Hello",
                                "attachments": [],
                                "reactions": [],
                                "inReplyTo": None,
                                "inThread": None,
                                "replyCount": 0,
                                "lastReplyAt": None,
                                "linkPreview": None,
                            },
                        }
                    ],
                    "hasOlder": False,
                    "hasNewer": False,
                }
            }
        )
    )
    async with client:
        page = await client.room_events("s1", "r1", limit=10)
    assert len(page.events) == 1
    assert page.events[0].body == "Hello"
    assert page.events[0].actor.login == "alice"


async def test_login():
    with respx.mock(base_url="https://chat.chatto.run") as api:
        api.post("/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "token": "cht_abc123", "user": {"id": "u1", "login": "alice"}},
                headers={"set-cookie": "chatto_session=xyz; Path=/; HttpOnly"},
            )
        )
        client = await ChattoClient.login("alice", "password123")
        assert client._token == "cht_abc123"
        assert client._session_cookie == "xyz"
        await client.close()


async def test_login_invalid():
    with respx.mock(base_url="https://chat.chatto.run") as api:
        api.post("/auth/login").mock(return_value=httpx.Response(401, json={"error": "Invalid credentials"}))
        with pytest.raises(ChattoAuthError, match="Invalid credentials"):
            await ChattoClient.login("bad", "creds")


async def test_edit_message(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"editMessage": {"id": "e1"}})
    )
    async with client:
        result = await client.edit_message("s1", "r1", "e1", "edited body")
    assert result["id"] == "e1"


async def test_delete_message(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"deleteMessage": True})
    )
    async with client:
        result = await client.delete_message("s1", "r1", "e1")
    assert result is True


async def test_add_reaction(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"addReaction": True})
    )
    async with client:
        result = await client.add_reaction("s1", "r1", "e1", "👍")
    assert result is True


async def test_remove_reaction(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"removeReaction": True})
    )
    async with client:
        result = await client.remove_reaction("s1", "r1", "e1", "👍")
    assert result is True


async def test_create_room(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {"createRoom": {"id": "r1", "spaceId": "s1", "name": "general", "description": None}}
        )
    )
    async with client:
        room = await client.create_room("s1", "general")
    assert room.id == "r1"
    assert room.name == "general"


async def test_update_my_profile(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "updateMyProfile": {
                    "id": "u1",
                    "login": "newname",
                    "displayName": "New Name",
                }
            }
        )
    )
    async with client:
        user = await client.update_my_profile(login="newname", display_name="New Name")
    assert user.login == "newname"
    assert user.display_name == "New Name"


async def test_update_presence(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"updateMyPresence": True})
    )
    async with client:
        result = await client.update_presence(PresenceStatus.ONLINE)
    assert result is True


async def test_upload_my_avatar(mock_api, client, tmp_path):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {"uploadMyAvatar": {"id": "u1", "avatarUrl": "https://example.com/avatar.jpg"}}
        )
    )
    avatar = tmp_path / "avatar.jpg"
    avatar.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    async with client:
        result = await client.upload_my_avatar(str(avatar))
    assert result["avatarUrl"] == "https://example.com/avatar.jpg"


async def test_user(mock_api, client):
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response(
            {
                "user": {
                    "id": "u1",
                    "login": "alice",
                    "displayName": "Alice",
                    "createdAt": "2025-01-01T00:00:00Z",
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
                    "presenceStatus": None,
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
    mock_api.post("/api/graphql").mock(
        return_value=_gql_response({"dismissNotification": True})
    )
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

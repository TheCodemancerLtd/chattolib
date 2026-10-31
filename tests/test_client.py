"""Tests for ChattoClient.

Since the client now goes through generated ConnectRPC service stubs, tests
mock at the service-client method level with ``AsyncMock`` rather than at the
HTTP transport layer. This exercises the request-building and response-parsing
paths without any real network traffic.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock

import pytest

from chattolib._pb.chatto.admin.v1 import (
    diagnostics_pb2,
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
    server_pb2 as admin_server_pb2,
)
from chattolib._pb.chatto.api.v1 import (
    account_pb2,
    asset_uploads_pb2,
    attachments_pb2,
    bots_pb2,
    message_search_pb2,
    messages_pb2,
    notifications_pb2,
    presence_pb2,
    push_notifications_pb2,
    reactions_pb2,
    read_state_pb2,
    roles_pb2,
    room_directory_pb2,
    room_invitations_pb2,
    room_timeline_pb2,
    rooms_pb2,
    threads_pb2,
    user_service_pb2,
    viewer_pb2,
    voice_calls_pb2,
)
from chattolib._pb.chatto.discovery.v1 import server_pb2 as discovery_server_pb2
from chattolib.client import ChattoClient
from chattolib.types import (
    AccountCreationPolicy,
    ImageFitMode,
    ImageTransformOptions,
    MessageSearchGroupBy,
    MessageSearchOrder,
    PermissionDecision,
    PresenceStatus,
    RoomInvitationStatus,
    RoomKind,
    ThreadOrder,
    ThreadRootAuthorFilter,
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


async def test_list_neighborhood_servers(client):
    resp = discovery_server_pb2.ListNeighborhoodServersResponse()
    s1 = resp.servers.add()
    s1.origin = "https://neighbor.example"
    s1.profile.name = "Neighbor"
    s1.profile.version = "0.5.0"
    s1.profile.logo_url = "/logos/neighbor.png"
    s1.direct_neighbor = True
    s2 = resp.servers.add()
    s2.origin = "https://referred.example"
    s2.profile.name = "Referred"
    s2.direct_neighbor = False
    s2.recommended_by_origins.append("https://neighbor.example")
    resp.refreshed_at.FromJsonString("2026-09-26T12:00:00Z")
    mocked = _mock_method(client, "server_discovery", "list_neighborhood_servers", resp)

    async with client:
        page = await client.list_neighborhood_servers()

    mocked.assert_awaited_once()
    assert [s.origin for s in page.servers] == [
        "https://neighbor.example",
        "https://referred.example",
    ]
    assert page.servers[0].profile is not None
    assert page.servers[0].profile.name == "Neighbor"
    assert page.servers[0].profile.logo_url == "/logos/neighbor.png"
    assert page.servers[0].direct_neighbor is True
    assert page.servers[1].direct_neighbor is False
    assert page.servers[1].recommended_by_origins == ["https://neighbor.example"]
    assert page.refreshed_at == dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.UTC)


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


async def test_list_rooms_dm_keeps_deleted_participants(client):
    # Since Chatto 0.5.0-beta.10, a DM's member_user_ids keeps participants
    # whose accounts were deleted; the client must surface the full list
    # (resolution to a User then legitimately fails for the deleted one).
    resp = room_directory_pb2.ListRoomsResponse()
    entry = resp.rooms.add()
    entry.room.id = "r-dm"
    entry.room.kind = "ROOM_KIND_DM"
    entry.room.name = "me & u2"
    entry.viewer_state.is_member = True
    entry.member_user_ids.extend(["u1", "u-deleted"])
    _mock_method(client, "room_directory", "list_rooms", resp)

    async with client:
        rooms = await client.list_rooms()

    assert len(rooms) == 1
    assert rooms[0].room is not None
    assert rooms[0].room.kind is RoomKind.DM
    assert rooms[0].member_user_ids == ["u1", "u-deleted"]


async def test_list_rooms_dm_activity_timestamps(client):
    # Since Chatto 0.5.0-beta.19, RoomWithViewerState carries
    # last_message_at (latest ordinary DM message incl. thread replies) and
    # last_root_message_at (root messages only). Absent for channels /
    # message-less DMs / servers predating the feature.
    resp = room_directory_pb2.ListRoomsResponse()
    entry = resp.rooms.add()
    entry.room.id = "r-dm"
    entry.room.kind = "ROOM_KIND_DM"
    entry.viewer_state.is_member = True
    entry.last_message_at.FromDatetime(dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.UTC))
    entry.last_root_message_at.FromDatetime(dt.datetime(2026, 10, 19, 8, 30, tzinfo=dt.UTC))
    channel = resp.rooms.add()
    channel.room.id = "r-ch"
    channel.room.kind = "ROOM_KIND_CHANNEL"
    _mock_method(client, "room_directory", "list_rooms", resp)

    async with client:
        rooms = await client.list_rooms()

    dm = next(r for r in rooms if r.room and r.room.id == "r-dm")
    assert dm.last_message_at == dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.UTC)
    assert dm.last_root_message_at == dt.datetime(2026, 10, 19, 8, 30, tzinfo=dt.UTC)
    ch = next(r for r in rooms if r.room and r.room.id == "r-ch")
    assert ch.last_message_at is None
    assert ch.last_root_message_at is None


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
    _mock_method(client, "messages", "delete_message", messages_pb2.DeleteMessageResponse())

    async with client:
        assert await client.delete_message("r1", "e1") is None


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


async def test_remove_user(client):
    resp = rooms_pb2.RemoveUserResponse()
    mock = _mock_method(client, "rooms", "remove_user", resp)

    async with client:
        await client.remove_user("r1", "u2", "spam")
        await client.remove_user(
            "r1", "u2", "spam", suspension_expires_at=dt.datetime.fromtimestamp(0, dt.UTC)
        )
        await client.remove_user("r1", "u2", "spam", suspend_indefinitely=True)

    calls = [c.args[0] for c in mock.call_args_list]
    assert calls[0].WhichOneof("suspension") is None
    assert calls[1].WhichOneof("suspension") == "suspension_expires_at"
    assert calls[2].WhichOneof("suspension") == "suspend_indefinitely"


async def test_remove_user_rejects_both_suspensions(client):
    _mock_method(client, "rooms", "remove_user", rooms_pb2.RemoveUserResponse())

    async with client:
        with pytest.raises(ValueError, match="not both"):
            await client.remove_user(
                "r1",
                "u2",
                "spam",
                suspension_expires_at=dt.datetime.fromtimestamp(0, dt.UTC),
                suspend_indefinitely=True,
            )


async def test_lift_suspension(client):
    _mock_method(client, "rooms", "lift_suspension", rooms_pb2.LiftSuspensionResponse())

    async with client:
        assert await client.lift_suspension("r1", "u2", "reinstated") is None


async def test_list_suspensions(client):
    resp = rooms_pb2.ListSuspensionsResponse()
    s = resp.suspensions.add()
    s.id = "s1"
    s.room_id = "r1"
    s.user_id = "u2"
    _mock_method(client, "rooms", "list_suspensions", resp)

    async with client:
        suspensions, _ = await client.list_suspensions(room_id="r1")

    assert [x.id for x in suspensions] == ["s1"]


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


async def test_update_user_profile(client):
    resp = user_service_pb2.UpdateUserProfileResponse()
    resp.user.id = "u1"
    resp.user.login = "newname"
    resp.user.display_name = "New Name"
    resp.user.bio = "# Hi"
    resp.user.presence_status = "PRESENCE_STATUS_ONLINE"
    _mock_method(client, "user", "update_user_profile", resp)

    async with client:
        user = await client.update_user_profile(
            "u1", login="newname", display_name="New Name", bio="# Hi"
        )

    assert user.id == "u1"
    assert user.login == "newname"
    assert user.display_name == "New Name"
    assert user.bio == "# Hi"


async def test_update_profile(client):
    """Self-service update resolves the caller id via the viewer, then
    delegates to the new UserService.UpdateUserProfile wire call."""
    viewer = viewer_pb2.GetViewerResponse()
    viewer.user.profile.id = "u1"
    viewer.user.profile.login = "alice"
    viewer.user.profile.display_name = "Alice"
    _mock_method(client, "viewer", "get_viewer", viewer)

    resp = user_service_pb2.UpdateUserProfileResponse()
    resp.user.id = "u1"
    resp.user.login = "newname"
    resp.user.display_name = "New Name"
    resp.user.presence_status = "PRESENCE_STATUS_ONLINE"
    update = _mock_method(client, "user", "update_user_profile", resp)

    async with client:
        user = await client.update_profile(login="newname", display_name="New Name")

    assert user.login == "newname"
    assert user.display_name == "New Name"
    (req,) = update.await_args.args
    assert req.user_id == "u1"


async def test_set_presence(client):
    resp = presence_pb2.SetPresenceResponse()
    resp.status = "PRESENCE_STATUS_ONLINE"
    _mock_method(client, "account", "set_presence", resp)

    async with client:
        result = await client.set_presence(PresenceStatus.ONLINE)

    assert result is PresenceStatus.ONLINE


async def test_set_presence_offline_rejected(client):
    async with client:
        with pytest.raises(ValueError):
            await client.set_presence(PresenceStatus.OFFLINE)


async def test_get_presence_preference(client):
    resp = presence_pb2.GetPresencePreferenceResponse()
    resp.preference.status = "PRESENCE_STATUS_OFFLINE"
    resp.preference.revision = "rev-1"
    _mock_method(client, "account", "get_presence_preference", resp)

    async with client:
        pref = await client.get_presence_preference()

    assert pref is not None
    assert pref.status is PresenceStatus.OFFLINE
    assert pref.revision == "rev-1"


async def test_get_presence_preference_absent(client):
    # No preference saved yet: the response carries no sub-message.
    _mock_method(
        client, "account", "get_presence_preference", presence_pb2.GetPresencePreferenceResponse()
    )

    async with client:
        assert await client.get_presence_preference() is None


async def test_set_presence_preference(client):
    resp = presence_pb2.SetPresencePreferenceResponse()
    resp.preference.status = "PRESENCE_STATUS_DO_NOT_DISTURB"
    resp.preference.revision = "rev-2"
    m = _mock_method(client, "account", "set_presence_preference", resp)

    async with client:
        pref = await client.set_presence_preference(
            PresenceStatus.DO_NOT_DISTURB, expected_revision="rev-1"
        )

    assert pref.status is PresenceStatus.DO_NOT_DISTURB
    assert pref.revision == "rev-2"
    req = m.await_args.args[0]
    assert req.status == presence_pb2.PresenceStatus.Value("PRESENCE_STATUS_DO_NOT_DISTURB")
    assert req.expected_revision == "rev-1"


async def test_set_presence_preference_offline_allowed(client):
    # Unlike set_presence, OFFLINE is a valid saved choice ("Appear Offline").
    resp = presence_pb2.SetPresencePreferenceResponse()
    resp.preference.status = "PRESENCE_STATUS_OFFLINE"
    _mock_method(client, "account", "set_presence_preference", resp)

    async with client:
        assert (await client.set_presence_preference(PresenceStatus.OFFLINE)).status is (
            PresenceStatus.OFFLINE
        )


async def test_set_presence_preference_unspecified_rejected(client):
    async with client:
        with pytest.raises(ValueError):
            await client.set_presence_preference(PresenceStatus.UNSPECIFIED)


async def test_refresh_presence(client):
    resp = presence_pb2.RefreshPresenceResponse()
    resp.preference.status = "PRESENCE_STATUS_ONLINE"
    resp.preference.revision = "rev-3"
    _mock_method(client, "account", "refresh_presence", resp)

    async with client:
        pref = await client.refresh_presence()

    assert pref is not None
    assert pref.status is PresenceStatus.ONLINE
    assert pref.revision == "rev-3"


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
    ft.thread.viewer_state.has_unread_replies = False
    resp.page.total_count = 1
    resp.page.has_more = False
    mocked = _mock_method(client, "threads", "list_followed_threads", resp)

    async with client:
        page = await client.list_followed_threads()
        await client.list_followed_threads(
            limit=5,
            offset=5,
            include_direct_message_threads=True,
            unread_only=True,
            root_author_filter=ThreadRootAuthorFilter.VIEWER,
        )
        await client.list_followed_threads(
            root_author_filter=ThreadRootAuthorFilter.OTHERS,
        )
        await client.list_followed_threads(order=ThreadOrder.CREATED)

    assert page.page.total_count == 1
    assert page.threads[0].thread is not None
    assert page.threads[0].thread.reply_count == 3
    assert page.threads[0].thread.is_following is True
    calls = [c.args[0] for c in mocked.call_args_list]
    assert calls[0].include_direct_message_threads is False
    assert calls[0].unread_only is False
    assert calls[0].root_author_filter == 0
    assert calls[1].include_direct_message_threads is True
    assert calls[1].unread_only is True
    assert calls[1].root_author_filter == threads_pb2.ThreadRootAuthorFilter.Value(
        "THREAD_ROOT_AUTHOR_FILTER_VIEWER"
    )
    assert calls[2].root_author_filter == threads_pb2.ThreadRootAuthorFilter.Value(
        "THREAD_ROOT_AUTHOR_FILTER_OTHERS"
    )
    assert calls[3].order == threads_pb2.ThreadOrder.Value("THREAD_ORDER_CREATED")
    assert calls[1].page.limit == 5
    assert calls[1].page.offset == 5


async def test_update_room_thread_slow_mode(client):
    resp = rooms_pb2.UpdateRoomResponse()
    resp.room.id = "r1"
    resp.room.name = "general"
    resp.room.slow_mode_seconds = 30
    resp.room.thread_slow_mode_seconds = 10
    mocked = _mock_method(client, "rooms", "update_room", resp)

    async with client:
        room = await client.update_room("r1", thread_slow_mode_seconds=10)
        await client.update_room("r1")

    assert room.thread_slow_mode_seconds == 10
    assert room.slow_mode_seconds == 30
    calls = [c.args[0] for c in mocked.call_args_list]
    assert calls[0].HasField("thread_slow_mode_seconds")
    assert calls[0].thread_slow_mode_seconds == 10
    assert not calls[1].HasField("thread_slow_mode_seconds")


async def test_get_thread_events_viewer_state(client):
    resp = room_timeline_pb2.GetThreadEventsResponse()
    ev = resp.page.events.add()
    ev.id = "e2"
    ev.actor_id = "u1"
    ev.message_posted.message.id = "e2"
    ev.message_posted.message.room_id = "r1"
    ev.message_posted.message.actor_id = "u1"
    ev.message_posted.message.body = "reply"
    ev.message_posted.message.thread_root_event_id = "e1"
    ev.message_posted.message.viewer_state.can_reply_in_thread = True
    ev.message_posted.message.viewer_state.thread_slow_mode_next_post_at.FromJsonString(
        "2026-01-03T00:00:00Z"
    )
    resp.page.end_cursor = "c2"
    resp.viewer_state.is_following = True
    resp.viewer_state.has_unread_replies = True
    resp.viewer_state.slow_mode_next_post_at.FromJsonString("2026-01-02T12:00:00Z")
    _mock_method(client, "threads", "get_thread_events", resp)

    async with client:
        page = await client.get_thread_events("r1", "e1")

    assert page.end_cursor == "c2"
    assert page.thread_viewer_state is not None
    assert page.thread_viewer_state.is_following is True
    assert page.thread_viewer_state.has_unread_replies is True
    assert page.thread_viewer_state.slow_mode_next_post_at == dt.datetime(
        2026, 1, 2, 12, 0, tzinfo=dt.UTC
    )
    msg = page.events[0].message
    assert msg is not None
    assert msg.viewer_state is not None
    assert msg.viewer_state.can_reply_in_thread is True
    assert msg.viewer_state.thread_slow_mode_next_post_at == dt.datetime(
        2026, 1, 3, 0, 0, tzinfo=dt.UTC
    )


async def test_get_thread_events_around_viewer_state(client):
    resp = room_timeline_pb2.GetThreadEventsAroundResponse()
    ev = resp.page.events.add()
    ev.id = "e2"
    ev.message_posted.message.id = "e2"
    ev.message_posted.message.room_id = "r1"
    ev.message_posted.message.actor_id = "u1"
    resp.target_index = 0
    resp.viewer_state.is_following = False
    _mock_method(client, "threads", "get_thread_events_around", resp)

    async with client:
        page, idx = await client.get_thread_events_around("r1", "e1", "e2")

    assert idx == 0
    assert page.thread_viewer_state is not None
    assert page.thread_viewer_state.is_following is False
    assert page.thread_viewer_state.slow_mode_next_post_at is None


async def test_thread_summary_slow_mode_next_post_at():
    from chattolib.types import ThreadSummary

    ts = ThreadSummary.parse(
        {
            "threadRootEventId": "e1",
            "viewerState": {
                "isFollowing": True,
                "slowModeNextPostAt": "2026-01-02T00:00:00Z",
            },
        }
    )
    assert ts is not None
    assert ts.slow_mode_next_post_at == dt.datetime(2026, 1, 2, tzinfo=dt.UTC)
    ts2 = ThreadSummary.parse({"threadRootEventId": "e1"})
    assert ts2 is not None
    assert ts2.slow_mode_next_post_at is None


async def test_room_thread_slow_mode_absent_vs_zero():
    from chattolib.types import Room

    absent = Room.parse({"id": "r1"})
    assert absent is not None
    assert absent.thread_slow_mode_seconds is None
    zero = Room.parse({"id": "r1", "threadSlowModeSeconds": 0})
    assert zero is not None
    assert zero.thread_slow_mode_seconds == 0


async def test_follow_and_unfollow_thread(client):
    _mock_method(client, "threads", "follow_thread", threads_pb2.FollowThreadResponse())
    _mock_method(client, "threads", "unfollow_thread", threads_pb2.UnfollowThreadResponse())

    async with client:
        assert await client.follow_thread("r1", "e1") is None
        assert await client.unfollow_thread("r1", "e1") is None


# --- Notifications ----------------------------------------------------


async def test_list_notification_occurrences(client):
    resp = notifications_pb2.ListNotificationOccurrencesResponse()
    occ = resp.occurrences.add()
    occ.id = "n1"
    occ.created_at.FromJsonString("2026-01-01T00:00:00Z")
    occ.actor.id = "u1"
    occ.actor.login = "alice"
    occ.actor.display_name = "Alice"
    occ.unread = True
    sig = occ.signal.direct_mention_received
    sig.message.room.id = "r1"
    sig.message.room.name = "general"
    sig.message.event_id = "e1"
    resp.page.total_count = 1
    resp.unread_count = 1
    _mock_method(client, "notifications", "list_notification_occurrences", resp)

    async with client:
        page = await client.list_notification_occurrences()

    assert page.page.total_count == 1
    assert page.unread_count == 1
    assert page.occurrences[0].signal is not None
    assert page.occurrences[0].signal.kind == "direct_mention_received"
    assert page.occurrences[0].signal.message is not None
    assert page.occurrences[0].signal.message.event_id == "e1"
    assert page.occurrences[0].signal.message.room is not None
    assert page.occurrences[0].signal.message.room.name == "general"


async def test_mark_and_delete_notification_occurrence(client):
    read_resp = notifications_pb2.MarkNotificationReadResponse()
    read_resp.occurrence.id = "n1"
    read_resp.occurrence.unread = False
    _mock_method(client, "notifications", "mark_notification_read", read_resp)

    del_resp = notifications_pb2.DeleteNotificationOccurrenceResponse(deleted=True)
    _mock_method(client, "notifications", "delete_notification_occurrence", del_resp)

    all_resp = notifications_pb2.DeleteAllNotificationOccurrencesResponse(deleted_count=3)
    _mock_method(client, "notifications", "delete_all_notification_occurrences", all_resp)

    async with client:
        occ = await client.mark_notification_read("n1")
        assert occ is not None and occ.unread is False
        assert await client.delete_notification_occurrence("n1") is True
        assert await client.delete_all_notification_occurrences() == 3


# --- Push -------------------------------------------------------------


async def test_subscribe_push(client):
    _mock_method(client, "push", "subscribe", push_notifications_pb2.SubscribeResponse())

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
    create_mock = _mock_method(client, "asset_uploads", "create_upload", create_resp)

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
        asset = await client.upload_attachment("r1", file, content_type="text/plain")

    assert asset.id == "a1"
    assert asset.filename == "greet.txt"

    create_req = create_mock.call_args.args[0]
    assert create_req.sha256 == sha
    assert create_req.size == len(payload)


# --- External identities --------------------------------------------


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


async def test_admin_move_room_group(client):
    resp = room_layout_pb2.MoveRoomGroupResponse()
    g = resp.groups.add()
    g.id = "g1"
    g.name = "General"
    mock = _mock_method(client, "admin_room_layout", "move_room_group", resp)

    async with client:
        groups = await client.admin_move_room_group("g1", before_group_id="g2")

    assert [g.id for g in groups] == ["g1"]
    sent = mock.call_args.args[0]
    assert sent.group_id == "g1"
    assert sent.before_group_id == "g2"


async def test_admin_move_room_group_to_end(client):
    resp = room_layout_pb2.MoveRoomGroupResponse()
    mock = _mock_method(client, "admin_room_layout", "move_room_group", resp)

    async with client:
        await client.admin_move_room_group("g1")

    sent = mock.call_args.args[0]
    assert sent.group_id == "g1"
    assert not sent.HasField("before_group_id")


async def test_admin_move_sidebar_item(client):
    resp = room_layout_pb2.MoveSidebarItemResponse()
    resp.group.id = "g1"
    resp.group.name = "General"
    mock = _mock_method(client, "admin_room_layout", "move_sidebar_item", resp)

    async with client:
        group = await client.admin_move_sidebar_item(
            ("sidebar_link", "sl1"),
            "g1",
            before=("room", "r1"),
        )

    assert group.id == "g1"
    sent = mock.call_args.args[0]
    assert sent.item.sidebar_link_id == "sl1"
    assert sent.before.room_id == "r1"
    assert sent.group_id == "g1"


async def test_admin_get_system_info_livekit(client):
    resp = diagnostics_pb2.GetSystemInfoResponse()
    resp.projections_available = True
    resp.livekit.enabled = True
    resp.livekit.configured = True
    resp.livekit.url = "wss://livekit.example"
    resp.livekit.api_key = "AP1234"
    resp.livekit.separate_webhook_key = True
    resp.livekit.webhook_url = "https://chat.example/api/admin/livekit/webhook"
    resp.livekit.connection_state = diagnostics_pb2.ADMIN_LIVE_KIT_CONNECTION_STATE_OK
    resp.livekit.insecure_url = False
    _mock_method(client, "admin_diagnostics", "get_system_info", resp)

    async with client:
        data = await client.admin_get_system_info()

    lk = data["livekit"]
    assert lk["enabled"] is True
    assert lk["configured"] is True
    assert lk["url"] == "wss://livekit.example"
    assert lk["apiKey"] == "AP1234"
    assert lk["separateWebhookKey"] is True
    # enums render as their full name in Connect JSON (use_integers_for_enums=False)
    assert lk["connectionState"] == "ADMIN_LIVE_KIT_CONNECTION_STATE_OK"
    assert (
        diagnostics_pb2.AdminLiveKitConnectionState.Value(
            "ADMIN_LIVE_KIT_CONNECTION_STATE_UNREACHABLE"
        )
        == 3
    )
    assert "connectionError" not in lk  # empty string omitted by MessageToDict


async def test_admin_update_server_config(client):
    resp = admin_server_pb2.UpdateServerConfigResponse()
    resp.config.server_name = "MyServer"
    resp.config.motd = "hi"
    resp.public_profile.name = "MyServer"
    resp.public_profile.version = "0.4.2"
    _mock_method(client, "admin_server", "update_server_config", resp)

    async with client:
        config, profile = await client.admin_update_server_config(server_name="MyServer", motd="hi")

    assert config.server_name == "MyServer"
    assert profile.version == "0.4.2"


# --- Neighbors (0.5.0-alpha.3) -----------------------------------------


async def test_list_neighbors_public(client):
    resp = discovery_server_pb2.ListNeighborsResponse()
    resp.origins.extend(["https://a.example", "https://b.example"])
    _mock_method(client, "server_discovery", "list_neighbors", resp)

    async with client:
        origins = await client.list_neighbors()

    assert origins == ["https://a.example", "https://b.example"]


async def test_admin_neighbor_crud(client):
    list_resp = admin_server_pb2.ListNeighborsResponse()
    n = list_resp.neighbors.add()
    n.id = "n1"
    n.origin = "https://a.example"
    n.revision = "rev1"
    _mock_method(client, "admin_server", "list_neighbors", list_resp)

    get_resp = admin_server_pb2.GetNeighborResponse()
    get_resp.neighbor.id = "n1"
    get_resp.neighbor.origin = "https://a.example"
    get_resp.neighbor.revision = "rev1"
    _mock_method(client, "admin_server", "get_neighbor", get_resp)

    create_resp = admin_server_pb2.CreateNeighborResponse()
    create_resp.neighbor.id = "n2"
    create_resp.neighbor.origin = "https://b.example"
    create_resp.neighbor.revision = "rev2"
    _mock_method(client, "admin_server", "create_neighbor", create_resp)

    update_resp = admin_server_pb2.UpdateNeighborResponse()
    update_resp.neighbor.id = "n2"
    update_resp.neighbor.origin = "https://b2.example"
    update_resp.neighbor.revision = "rev3"
    _mock_method(client, "admin_server", "update_neighbor", update_resp)

    del_resp = admin_server_pb2.DeleteNeighborResponse()
    _mock_method(client, "admin_server", "delete_neighbor", del_resp)

    async with client:
        listed = await client.admin_list_neighbors()
        assert [x.origin for x in listed] == ["https://a.example"]

        got = await client.admin_get_neighbor("n1")
        assert got is not None and got.revision == "rev1"

        created = await client.admin_create_neighbor("https://b.example")
        assert created.id == "n2" and created.revision == "rev2"

        updated = await client.admin_update_neighbor("n2", "https://b2.example", "rev2")
        assert updated.origin == "https://b2.example" and updated.revision == "rev3"

        await client.admin_delete_neighbor("n2", "rev3")


async def test_update_settings_share_timezone(client):
    resp = account_pb2.UpdateSettingsResponse()
    resp.settings.timezone = "Europe/Berlin"
    resp.settings.share_timezone = True
    _mock_method(client, "account", "update_settings", resp)

    async with client:
        settings = await client.update_settings(timezone="Europe/Berlin", share_timezone=True)

    assert settings.timezone == "Europe/Berlin"
    assert settings.share_timezone is True


def test_snake_case_is_acronym_aware():
    """``types._snake_case`` must not chop acronym runs (same bug class as
    the protoc plugin's old ``StartDM`` -> ``start_d_m``)."""
    from chattolib.types import _snake_case

    assert _snake_case("messagePosted") == "message_posted"
    assert _snake_case("directMessageReceived") == "direct_message_received"
    # hypothetical acronym field: DM stays whole, boundary before the word after it
    assert _snake_case("startDMReceived") == "start_dm_received"
    assert _snake_case("getDMStats") == "get_dm_stats"


# --- Message search -----------------------------------------------------


async def test_get_search_status(client):
    resp = message_search_pb2.GetStatusResponse()
    resp.state = "MESSAGE_SEARCH_STATE_READY"
    _mock_method(client, "message_search", "get_status", resp)

    async with client:
        status = await client.get_search_status()

    assert status.state.value == "MESSAGE_SEARCH_STATE_READY"
    assert status.retry_after_seconds is None


async def test_search_messages(client):
    resp = message_search_pb2.SearchMessagesResponse()
    result = resp.results.add()
    result.message.id = "m1"
    result.message.body = "hello searchable world"
    result.relevance_score = 4.2
    resp.next_cursor = "cur-2"
    resp.includes.users["u1"].id = "u1"
    resp.includes.users["u1"].login = "alice"
    resp.includes.users["u1"].display_name = "Alice"
    mock = _mock_method(client, "message_search", "search_messages", resp)

    async with client:
        page = await client.search_messages(
            "searchable",
            room_id="r1",
            order=MessageSearchOrder.RELEVANCE,
            page_size=20,
        )

    req = mock.await_args.args[0]
    assert req.query == "searchable"
    assert req.room_id == "r1"
    assert req.order == message_search_pb2.MESSAGE_SEARCH_ORDER_RELEVANCE
    assert page.results[0].message.id == "m1"
    assert page.results[0].relevance_score == 4.2
    assert page.next_cursor == "cur-2"
    assert page.users_by_id["u1"].login == "alice"
    assert page.thread_total_count is None


async def test_search_messages_thread_grouping(client):
    resp = message_search_pb2.SearchMessagesResponse()
    result = resp.results.add()
    result.message.id = "reply-1"
    result.thread_context.root_message.id = "root-1"
    result.thread_context.room.id = "r1"
    result.thread_context.thread.thread_root_event_id = "root-1"
    resp.thread_total_count = 7
    _mock_method(client, "message_search", "search_messages", resp)

    async with client:
        page = await client.search_messages("deploy", group_by=MessageSearchGroupBy.THREAD)

    assert page.thread_total_count == 7
    ctx = page.results[0].thread_context
    assert ctx is not None
    assert ctx.root_message.id == "root-1"
    assert ctx.room.id == "r1"


# --- Read state ----------------------------------------------------------


async def test_get_room_read_state(client):
    resp = read_state_pb2.GetRoomReadStateResponse()
    resp.state.room_id = "r1"
    resp.state.marker.last_read_event_id = "e9"
    _mock_method(client, "rooms", "get_room_read_state", resp)

    async with client:
        state = await client.get_room_read_state("r1")

    assert state is not None
    assert state.room_id == "r1"
    assert state.marker.last_read_event_id == "e9"


async def test_batch_get_thread_read_states(client):
    resp = read_state_pb2.BatchGetThreadReadStatesResponse()
    resp.states.add(room_id="r1", thread_root_event_id="root-1")
    mock = _mock_method(client, "threads", "batch_get_thread_read_states", resp)

    async with client:
        states = await client.batch_get_thread_read_states([("r1", "root-1")])

    assert mock.await_args.args[0].targets[0].thread_root_event_id == "root-1"
    assert len(states) == 1
    assert states[0].room_id == "r1"


# --- Messages / threads extras -------------------------------------------


async def test_list_reaction_users(client):
    resp = reactions_pb2.ListReactionUsersResponse()
    resp.user_ids.extend(["u1", "u2"])
    resp.page.total_count = 2
    _mock_method(client, "messages", "list_reaction_users", resp)

    async with client:
        ids, page = await client.list_reaction_users("r1", "m1", "tada")

    assert ids == ["u1", "u2"]
    assert page.total_count == 2


async def test_set_attachment_description(client):
    resp = messages_pb2.SetAttachmentDescriptionResponse()
    resp.message.id = "m1"
    resp.message.attachments.add(id="a1", description="alt text")
    _mock_method(client, "messages", "set_attachment_description", resp)

    async with client:
        msg = await client.set_attachment_description("r1", "m1", "a1", "alt text")

    assert msg.attachments[0].description == "alt text"


async def test_list_thread_participants(client):
    resp = threads_pb2.ListThreadParticipantsResponse()
    resp.user_ids.append("u3")
    _mock_method(client, "threads", "list_thread_participants", resp)

    async with client:
        ids, _page = await client.list_thread_participants("r1", "root-1")

    assert ids == ["u3"]


# --- Users ---------------------------------------------------------------


async def test_list_users(client):
    resp = user_service_pb2.ListUsersResponse()
    resp.users.add(user={"id": "u1", "login": "alice", "display_name": "Alice"})
    resp.page.total_count = 1
    _mock_method(client, "user", "list_users", resp)

    async with client:
        users, page = await client.list_users(search="ali")

    assert users[0].user.login == "alice"
    assert page.total_count == 1


async def test_batch_get_users(client):
    resp = user_service_pb2.BatchGetUsersResponse()
    resp.users.add(user={"id": "u1", "login": "alice", "display_name": "Alice"})
    _mock_method(client, "user", "batch_get_users", resp)

    async with client:
        users = await client.batch_get_users(["u1"])

    assert len(users) == 1


# --- My account ----------------------------------------------------------


async def test_get_settings(client):
    resp = account_pb2.GetSettingsResponse()
    resp.settings.time_format = "TIME_FORMAT_24_HOUR"
    _mock_method(client, "account", "get_settings", resp)

    async with client:
        settings = await client.get_settings()

    assert settings.time_format.value == "TIME_FORMAT_24_HOUR"


async def test_list_verified_emails(client):
    resp = account_pb2.ListVerifiedEmailsResponse()
    resp.verified_emails.add(email="a@example.com", primary=True)
    _mock_method(client, "account", "list_verified_emails", resp)

    async with client:
        emails = await client.list_verified_emails("u1")

    assert emails[0].email == "a@example.com"
    assert emails[0].primary is True


async def test_request_account_deletion(client):
    resp = account_pb2.RequestAccountDeletionResponse()
    resp.confirmation_token = "tok-1"
    _mock_method(client, "account", "request_account_deletion", resp)

    async with client:
        token = await client.request_account_deletion()

    assert token == "tok-1"


# --- Bots ----------------------------------------------------------------


async def test_list_bots(client):
    resp = bots_pb2.ListBotsResponse()
    resp.bots.add(
        user={"id": "b1", "login": "mybot", "display_name": "My Bot"},
        owner_user_id="u1",
    )
    resp.page.total_count = 1
    _mock_method(client, "bots", "list_bots", resp)

    async with client:
        bots, page = await client.list_bots()

    assert bots[0].owner_user_id == "u1"
    assert bots[0].user.login == "mybot"
    assert page.total_count == 1


async def test_create_bot_returns_key_once(client):
    resp = bots_pb2.CreateBotResponse()
    resp.bot.user.id = "b1"
    resp.api_key = "cht_BK_secret"
    resp.api_key_metadata.id = "k1"
    resp.api_key_metadata.name = "Default key"
    _mock_method(client, "bots", "create_bot", resp)

    async with client:
        bot, key, meta = await client.create_bot("mybot", "My Bot")

    assert bot.user.id == "b1"
    assert key == "cht_BK_secret"
    assert meta.id == "k1"


async def test_create_bot_outbound_webhook_returns_secret_once(client):
    resp = bots_pb2.CreateBotOutboundWebhookResponse()
    resp.webhook.id = "w1"
    resp.webhook.url = "https://example.com/hook"
    resp.webhook.name = "main"
    resp.signing_secret = "whsec_x"
    _mock_method(client, "bots", "create_bot_outbound_webhook", resp)

    async with client:
        webhook, secret = await client.create_bot_outbound_webhook(
            "b1", "https://example.com/hook", "main"
        )

    assert webhook.id == "w1"
    assert secret == "whsec_x"


async def test_update_bot_outbound_webhook_infers_mask(client):
    resp = bots_pb2.UpdateBotOutboundWebhookResponse()
    resp.webhook.id = "w1"
    resp.webhook.enabled = False
    mock = _mock_method(client, "bots", "update_bot_outbound_webhook", resp)

    async with client:
        webhook = await client.update_bot_outbound_webhook("b1", "w1", enabled=False)

    req = mock.await_args.args[0]
    assert list(req.update_mask.paths) == ["enabled"]
    assert webhook.enabled is False


# --- Admin: registration codes / OAuth clients ----------------------------


async def test_admin_create_invitation_code(client):
    resp = admin_invitations_pb2.CreateInvitationCodeResponse()
    resp.invitation_code.id = "ic1"
    resp.invitation_code.code = "REG-CODE-123"
    resp.invitation_code.status = "INVITATION_CODE_STATUS_ACTIVE"
    resp.invitation_code.note = "for alice"
    mock = _mock_method(client, "admin_invitation_codes", "create_invitation_code", resp)

    async with client:
        code = await client.admin_create_invitation_code(note="for alice")

    assert mock.await_args.args[0].note == "for alice"
    assert code.id == "ic1"
    assert code.code == "REG-CODE-123"
    assert code.status.value == "INVITATION_CODE_STATUS_ACTIVE"
    assert code.note == "for alice"


async def test_admin_list_invitation_codes(client):
    resp = admin_invitations_pb2.ListInvitationCodesResponse()
    resp.invitation_codes.add(
        id="ic1",
        code="c",
        status="INVITATION_CODE_STATUS_USED",
    )
    resp.page.total_count = 1
    _mock_method(client, "admin_invitation_codes", "list_invitation_codes", resp)

    async with client:
        codes, page = await client.admin_list_invitation_codes()

    assert codes[0].status.value == "INVITATION_CODE_STATUS_USED"
    assert page.total_count == 1


async def test_admin_set_user_deactivated(client):
    resp = admin_members_pb2.SetUserDeactivatedResponse()
    resp.member.user.id = "u1"
    resp.member.deactivated = True
    resp.member.viewer_can_change_deactivation = True
    mock = _mock_method(client, "admin_users", "set_user_deactivated", resp)

    async with client:
        member = await client.admin_set_user_deactivated("u1", True)

    req = mock.await_args.args[0]
    assert req.user_id == "u1" and req.deactivated is True
    assert member.deactivated is True
    assert member.viewer_can_change_deactivation is True


async def test_post_message_idempotency_key(client):
    resp = messages_pb2.CreateMessageResponse()
    resp.message.id = "e1"
    resp.message.room_id = "r1"
    mock = _mock_method(client, "messages", "create_message", resp)

    async with client:
        await client.post_message(
            "r1", "hi", idempotency_key="2b1f8f4c-3e0a-4a3f-9e1d-6f3f2a7b9c11"
        )

    req = mock.await_args.args[0]
    assert req.idempotency_key == "2b1f8f4c-3e0a-4a3f-9e1d-6f3f2a7b9c11"


async def test_post_message_without_idempotency_key(client):
    resp = messages_pb2.CreateMessageResponse()
    resp.message.id = "e1"
    resp.message.room_id = "r1"
    mock = _mock_method(client, "messages", "create_message", resp)

    async with client:
        await client.post_message("r1", "hi")

    req = mock.await_args.args[0]
    assert not req.HasField("idempotency_key")


async def test_room_notice_wrappers(client):
    resp = rooms_pb2.GetNoticeResponse()
    resp.notice.body = "welcome"
    resp.notice.version = "v1"
    resp.notice.publication_id = "p1"
    _mock_method(client, "rooms", "get_notice", resp)

    async with client:
        notice = await client.get_notice("r1")

    assert notice.body == "welcome"
    assert notice.version == "v1"
    assert notice.publication_id == "p1"

    pub = rooms_pb2.PublishNoticeResponse()
    pub.notice.body = "updated"
    pub.notice.version = "v2"
    mock = _mock_method(client, "rooms", "publish_notice", pub)
    async with client:
        notice = await client.publish_notice("r1", "updated", expected_version="v1", republish=True)

    req = mock.await_args.args[0]
    assert req.expected_version == "v1" and req.republish is True
    assert notice.version == "v2"

    cleared = rooms_pb2.ClearNoticeResponse()
    cleared.notice.version = "v2"
    mock = _mock_method(client, "rooms", "clear_notice", cleared)
    async with client:
        notice = await client.clear_notice("r1", expected_version="v2")

    assert mock.await_args.args[0].expected_version == "v2"
    assert notice.body == ""


async def test_list_features(client):
    resp = discovery_server_pb2.ListFeaturesResponse()
    resp.features.add(
        id="room-notices",
        name="Room notices",
        description="Pinned room-level notices.",
        introduced_version="0.5.0-beta.27",
    )
    mock = _mock_method(client, "server_discovery", "list_features", resp)

    async with client:
        features = await client.list_features(locale="en", introduced_after_version="0.5.0-beta.26")

    req = mock.await_args.args[0]
    assert req.locale == "en"
    assert req.introduced_after_version == "0.5.0-beta.26"
    assert features[0].id == "room-notices"
    assert features[0].introduced_version == "0.5.0-beta.27"


async def test_update_room_show_membership_events(client):
    resp = rooms_pb2.UpdateRoomResponse()
    resp.room.id = "r1"
    resp.room.show_membership_events = False
    mock = _mock_method(client, "rooms", "update_room", resp)

    async with client:
        room = await client.update_room("r1", show_membership_events=False)

    req = mock.await_args.args[0]
    assert req.show_membership_events is False
    assert room.show_membership_events is False


async def test_admin_update_server_config_registration_mask(client):
    resp = admin_server_pb2.UpdateServerConfigResponse()
    resp.config.server_name = "S"
    resp.config.registration.admission = "ACCOUNT_CREATION_POLICY_INVITE_ONLY"
    mock = _mock_method(client, "admin_server", "update_server_config", resp)

    async with client:
        config, _profile = await client.admin_update_server_config(
            registration_admission=AccountCreationPolicy.INVITE_ONLY
        )

    req = mock.await_args.args[0]
    assert list(req.update_mask.paths) == ["registration.admission"]
    assert config.registration.admission.value == "ACCOUNT_CREATION_POLICY_INVITE_ONLY"


async def test_admin_list_oauth_clients(client):
    resp = admin_oauth_clients_pb2.ListOAuthClientsResponse()
    resp.oauth_clients.add(
        client_id="https://example.com/cimd.json",
        client_name="Example",
        source="OAUTH_CLIENT_SOURCE_CIMD",
        policy="OAUTH_CLIENT_POLICY_DEFAULT",
    )
    resp.page.total_count = 1
    _mock_method(client, "admin_oauth_clients", "list_oauth_clients", resp)

    async with client:
        clients, page = await client.admin_list_oauth_clients()

    assert clients[0].source.value == "OAUTH_CLIENT_SOURCE_CIMD"
    assert page.total_count == 1


# --- Admin: permission writes ---------------------------------------------


async def test_admin_set_role_permission(client):
    resp = admin_permissions_pb2.SetRolePermissionResponse()
    resp.decision.decision = "PERMISSION_DECISION_ALLOW"
    mock = _mock_method(client, "admin_permissions", "set_role_permission", resp)

    async with client:
        out = await client.admin_set_role_permission(
            "moderators", "message.delete", PermissionDecision.ALLOW
        )

    req = mock.await_args.args[0]
    assert req.decision == admin_permissions_pb2.PERMISSION_DECISION_ALLOW
    assert out["decision"]["decision"] == "PERMISSION_DECISION_ALLOW"


async def test_admin_explain_permissions(client):
    resp = admin_permissions_pb2.ExplainPermissionsResponse()
    resp.explanations.add(permission="message.read")
    _mock_method(client, "admin_permissions", "explain_permissions", resp)

    async with client:
        rows = await client.admin_explain_permissions("u1")

    assert rows[0]["permission"] == "message.read"


# --- Voice / push extras ---------------------------------------------------


async def test_list_call_participants(client):
    resp = voice_calls_pb2.ListCallParticipantsResponse()
    resp.participants.add(
        user={"id": "u1", "login": "alice", "display_name": "Alice"}, call_id="c1"
    )
    _mock_method(client, "voice_calls", "list_call_participants", resp)

    async with client:
        parts = await client.list_call_participants("r1")

    assert parts[0].call_id == "c1"


async def test_send_test_notification(client):
    mock = _mock_method(
        client,
        "push",
        "send_test_notification",
        push_notifications_pb2.SendTestNotificationResponse(),
    )

    async with client:
        await client.send_test_notification()

    assert mock.await_count == 1


# --- Room invitations (0.5.0b20) -----------------------------------------


def _invitation_pb(inv, **kwargs):
    inv.id = kwargs.get("id", "inv1")
    inv.room_id = kwargs.get("room_id", "r1")
    inv.sender_id = kwargs.get("sender_id", "u1")
    inv.recipient_id = kwargs.get("recipient_id", "u2")
    inv.status = kwargs.get("status", room_invitations_pb2.ROOM_INVITATION_STATUS_PENDING)
    inv.can_accept = kwargs.get("can_accept", True)


async def test_create_room_invitation(client):
    resp = room_invitations_pb2.CreateRoomInvitationResponse()
    _invitation_pb(resp.invitation)
    mock = _mock_method(client, "room_invitations", "create_room_invitation", resp)

    async with client:
        inv = await client.create_room_invitation("r1", "u2")

    assert inv.id == "inv1"
    assert inv.status is RoomInvitationStatus.PENDING
    assert inv.can_accept is True
    req = mock.await_args.args[0]
    assert req.room_id == "r1" and req.recipient_id == "u2"


async def test_get_room_invitation(client):
    resp = room_invitations_pb2.GetRoomInvitationResponse()
    _invitation_pb(resp.invitation, status=room_invitations_pb2.ROOM_INVITATION_STATUS_ACCEPTED)
    _mock_method(client, "room_invitations", "get_room_invitation", resp)

    async with client:
        inv = await client.get_room_invitation("inv1")

    assert inv is not None
    assert inv.status is RoomInvitationStatus.ACCEPTED


async def test_batch_get_room_invitations(client):
    resp = room_invitations_pb2.BatchGetRoomInvitationsResponse()
    _invitation_pb(resp.invitations.add(), id="inv1")
    _invitation_pb(resp.invitations.add(), id="inv2")
    _mock_method(client, "room_invitations", "batch_get_room_invitations", resp)

    async with client:
        invs = await client.batch_get_room_invitations(["inv1", "inv2", "missing"])

    assert [i.id for i in invs] == ["inv1", "inv2"]


async def test_list_room_invitations(client):
    resp = room_invitations_pb2.ListRoomInvitationsResponse()
    _invitation_pb(resp.invitations.add(), id="inv1")
    resp.page.total_count = 1
    mock = _mock_method(client, "room_invitations", "list_room_invitations", resp)

    async with client:
        invs, page = await client.list_room_invitations(sent=True, pending_only=True, limit=25)

    assert invs[0].id == "inv1"
    assert page.total_count == 1
    req = mock.await_args.args[0]
    assert req.sent is True and req.pending_only is True and req.page.limit == 25


async def test_accept_and_decline_room_invitation(client):
    acc = room_invitations_pb2.AcceptRoomInvitationResponse()
    _invitation_pb(acc.invitation, status=room_invitations_pb2.ROOM_INVITATION_STATUS_ACCEPTED)
    _mock_method(client, "room_invitations", "accept_room_invitation", acc)
    dec = room_invitations_pb2.DeclineRoomInvitationResponse()
    _invitation_pb(dec.invitation, status=room_invitations_pb2.ROOM_INVITATION_STATUS_DECLINED)
    _mock_method(client, "room_invitations", "decline_room_invitation", dec)

    async with client:
        a = await client.accept_room_invitation("inv1")
        d = await client.decline_room_invitation("inv1")

    assert a.status is RoomInvitationStatus.ACCEPTED
    assert d.status is RoomInvitationStatus.DECLINED


async def test_room_viewer_state_invitation_fields(client):
    """RoomViewerState carries the pending invitation + can_rejoin decision."""
    resp = room_directory_pb2.GetRoomResponse()
    resp.room.room.id = "r1"
    resp.room.viewer_state.is_member = False
    resp.room.viewer_state.can_rejoin = False
    _invitation_pb(resp.room.viewer_state.invitation, can_accept=False)
    _mock_method(client, "room_directory", "get_room", resp)

    async with client:
        r = await client.get_room("r1")

    assert r is not None
    assert r.viewer_state.can_rejoin is False
    assert r.viewer_state.invitation is not None
    assert r.viewer_state.invitation.id == "inv1"
    assert r.viewer_state.invitation.status is RoomInvitationStatus.PENDING

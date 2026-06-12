# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**IMPORTANT**: before you do anything else, run the `beans prime` command and heed its output. Tasks for this project are tracked in `.beans/` via the [beans](https://github.com/hmans/beans) CLI.

## Project Overview

**chattolib** is an async Python client library for the [Chatto](https://chat.chatto.run) webchat GraphQL API (`https://chat.chatto.run/api/graphql`). It wraps the full Chatto GraphQL schema — queries, mutations, and subscriptions — into a typed, Pythonic async interface.

## Build & Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test
pytest tests/test_foo.py::test_bar -v

# Lint & format
ruff check .
ruff format .

# Type checking
mypy src/chattolib
```

## Architecture

The library uses **httpx** for async HTTP and **websockets** for GraphQL subscriptions (real-time events via WebSocket).

### Package layout: `src/chattolib/`

- **client.py** — Main `ChattoClient` async class. Holds the httpx session, auth token, and base URL. All API methods live here or are mixed in from domain modules.
- **types.py** — Dataclasses mirroring GraphQL object types (Room, User, Message, Attachment, etc.). Field names are snake_case translations of the schema's camelCase.
- **queries.py** — Raw GraphQL query/mutation/subscription strings as constants.
- **subscriptions.py** — WebSocket subscription handling for real-time events (server events, instance events, typing indicators, presence changes, etc.).
- **exceptions.py** — Library-specific exception hierarchy wrapping GraphQL error responses.

### Key API domains (from the Chatto GraphQL schema)

| Domain | Queries | Mutations | Subscriptions |
|---|---|---|---|
| **Server** | `server`, `server.profile` | `updateServerConfig`, `uploadServerLogo`, `deleteServerLogo`, `uploadServerBanner`, `deleteServerBanner` | `ServerUpdatedEvent`, `RoomGroupsUpdatedEvent` |
| **Rooms** | `room`, `room.events`, `room.event`, `room.eventsAround` | `createRoom`, `updateRoom`, `archiveRoom`, `unarchiveRoom`, `joinRoom`, `leaveRoom`, `banRoomMember`, `unbanRoomMember`, `markRoomAsRead` | `myEvents` |
| **Room groups** | `server.roomGroups` | `createRoomGroup`, `updateRoomGroup`, `deleteRoomGroup`, `reorderRoomGroups`, `moveRoomToGroup`, `reorderRoomsInGroup`, `joinGroup` | `RoomGroupsUpdatedEvent` |
| **Messages** | (via room.events) | `postMessage`, `updateMessage`, `deleteMessage`, `deleteAttachment`, `deleteLinkPreview` | `MessagePostedEvent`, `MessageEditedEvent`, `MessageRetractedEvent` |
| **Assets** | (via attachment IDs) | (server-driven) | `AssetProcessingStartedEvent`, `AssetProcessingSucceededEvent`, `AssetProcessingFailedEvent`, `AssetDeletedEvent` |
| **Reactions** | (on message events) | `addReaction`, `removeReaction` | `ReactionAddedEvent`, `ReactionRemovedEvent` |
| **Threads** | `room.event.threadReplies` (via `MessagePostedEvent`), `viewer.followedThreads` | `followThread`, `unfollowThread`, `markThreadAsRead` | `ThreadCreatedEvent`, `ThreadFollowChangedEvent` |
| **Users** | `viewer.user`, `user(id)`, `userByLogin`, `server.members` | `updateProfile`, `uploadAvatar`, `deleteAvatar`, `updateSettings`, `requestAccountDeletion`, `deleteMyAccount` | `UserCreatedEvent`, `UserDeletedEvent`, `UserProfileUpdatedEvent`, `PresenceChangedEvent` |
| **DMs** | (via rooms) | `startDM` | `NewDirectMessageNotificationEvent` |
| **Notifications** | `viewer.notifications` (connection), `viewer.hasNotifications` | `dismissNotification`, `dismissAllNotifications`, `setServerNotificationLevel`, `setRoomNotificationLevel` | `NotificationCreatedEvent`, `NotificationDismissedEvent`, `NotificationLevelChangedEvent`, `MentionStatusClearedEvent` |
| **Push** | — | `subscribeToPush`, `unsubscribeFromPush` | — |
| **Permissions/Roles** | `admin.rbac`, `server.roles` | `grantPermission`, `revokePermission`, `createRole`, `updateRole`, `deleteRole`, `assignRole`, plus room/user/group variants | — |
| **Voice calls** | `room.voiceCallToken`, `activeCallRoomIds`, `room.callParticipants` | — | `CallParticipantJoinedEvent`, `CallParticipantLeftEvent` |
| **Admin** | `admin.systemInfo`, `admin.serverConfig`, `admin.eventLog`, `admin.roomBans`, `admin.projections` | `admin.updateUser`, `admin.updateBlockedUsernames`, `admin.clearUsernameCooldown` | via `myEvents` |

### GraphQL conventions

- IDs are opaque strings (`ID` scalar).
- Large integers use `Int64` scalar (e.g., byte counts) — map to Python `int`.
- File uploads use a custom `Upload` scalar (multipart form).
- Pagination uses `limit`/`before`/`after` on room events (`before`/`after` are `Time` scalars, ISO timestamps).
- All mutations take a single `input` argument with a corresponding `*Input` type.
- Single unified subscription: `myEvents` for all server, room, and instance events.
- Rooms have a `type` field: `CHANNEL` or `DM`. Channels live inside a `RoomGroup` (`groupId` is required at creation).
- Threads are addressed by `threadRootEventId` (no separate `inThread` field on messages).
- Presence: `PresenceStatus` (OFFLINE/ONLINE/AWAY/DO_NOT_DISTURB) is the observable type; `PresenceStatusInput` (no OFFLINE) is what callers can set via `updateMyPresence`.
- Image URLs accept optional `width`, `height`, `fit` (enum: `CONTAIN`, `COVER`, `EXACT`) for server-side resizing.

### Naming conventions

- Python field/method names: `snake_case` (translated from GraphQL `camelCase`)
- Type classes: `PascalCase` matching the GraphQL type names
- Query/mutation method names on the client: `verb_noun` style (e.g., `create_room`, `post_message`, `mark_room_as_read`)

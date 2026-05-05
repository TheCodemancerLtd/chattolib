# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- **types.py** — Dataclasses / TypedDicts mirroring GraphQL object types (Space, Room, User, Message, Attachment, etc.). Field names are snake_case translations of the schema's camelCase.
- **queries.py** — Raw GraphQL query/mutation/subscription strings as constants.
- **subscriptions.py** — WebSocket subscription handling for real-time events (space events, instance events, typing indicators, presence changes, etc.).
- **exceptions.py** — Library-specific exception hierarchy wrapping GraphQL error responses.

### Key API domains (from the Chatto GraphQL schema)

| Domain | Queries | Mutations | Subscriptions |
|---|---|---|---|
| **Spaces** | `spaces`, `space(id)` | `updateSpace`, `joinSpace`, `leaveSpace`, logo/banner uploads | `mySpaceEvents` |
| **Rooms** | `room`, `roomEvents`, `roomEventByEventId`, `threadEvents`, `roomEventsAround` | `createRoom`, `updateRoom`, `archiveRoom`, `joinRoom`, `leaveRoom`, `markRoomAsRead` | via space events |
| **Messages** | (via roomEvents) | `postMessage`, `editMessage`, `deleteMessage` | `MessagePostedEvent`, `MessageUpdatedEvent`, `MessageDeletedEvent` |
| **Reactions** | (on message events) | `addReaction`, `removeReaction` | `ReactionAddedEvent`, `ReactionRemovedEvent` |
| **Threads** | `threadEvents`, `myFollowedThreads` | `followThread`, `unfollowThread`, `markThreadAsOpened` | `ThreadFollowChangedEvent` |
| **Users** | `me`, `user(id)`, `userByLogin`, `users` | `updateMyProfile`, `uploadMyAvatar`, `deleteMyAvatar` | `UserProfileUpdatedEvent`, `PresenceChangedEvent` |
| **DMs** | (via rooms) | `startDM` | `NewDirectMessageNotificationEvent` |
| **Notifications** | `notifications`, `hasNotifications` | `dismissNotification`, `dismissAllNotifications` | `NotificationCreatedEvent`, `NotificationDismissedEvent` |
| **Permissions/Roles** | via `admin` query, `space.roles` | `grantInstancePermission`, `createRole`, `assignInstanceRole`, space-level equivalents | — |
| **Voice calls** | `voiceCallToken`, `activeCallRoomIds`, `callParticipants` | — | `CallParticipantJoinedEvent`, `CallParticipantLeftEvent` |
| **Admin** | `admin.systemInfo`, `admin.instanceConfig`, `admin.roles` | `admin.updateInstanceConfig`, `admin.resetInstanceConfig` | `myInstanceEvents` |

### GraphQL conventions

- IDs are opaque strings (`ID` scalar).
- Large integers use `Int64` scalar (e.g., byte counts) — map to Python `int`.
- File uploads use a custom `Upload` scalar (multipart form).
- Pagination uses `limit`/`before`/`after` on room events (`before`/`after` are `Time` scalars, ISO timestamps); `limit`/`offset` on space members.
- All mutations take a single `input` argument with a corresponding `*Input` type.
- Subscriptions use `spaceId` scoping (`mySpaceEvents`) or are instance-wide (`myInstanceEvents`).
- Image URLs accept optional `width`, `height`, `fit` (enum: `CONTAIN`, `COVER`, `EXACT`) for server-side resizing.

### Naming conventions

- Python field/method names: `snake_case` (translated from GraphQL `camelCase`)
- Type classes: `PascalCase` matching the GraphQL type names
- Query/mutation method names on the client: `verb_noun` style (e.g., `create_room`, `post_message`, `mark_room_as_read`)

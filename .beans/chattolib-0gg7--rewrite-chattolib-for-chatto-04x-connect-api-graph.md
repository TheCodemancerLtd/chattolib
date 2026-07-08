---
# chattolib-0gg7
title: Rewrite chattolib for Chatto 0.4.x Connect API (GraphQL removed)
status: completed
type: task
priority: high
created_at: 2026-07-08T23:18:23Z
updated_at: 2026-07-08T23:33:38Z
---

Chatto 0.4.2 has removed GraphQL entirely (ADR-042 supersedes ADR-003). The public API is now ConnectRPC over HTTP at /api/connect/{service}/{method} with a separate protobuf WebSocket for realtime. chattolib must be rewritten to speak Connect JSON to the new services.

## Task list
- [x] Verify chat.chatto.run only serves /api/connect/*
- [x] Inventory relevant Connect services and message shapes
- [x] Write new exceptions.py for Connect errors
- [x] Write new types.py with dataclasses/enums that match proto messages
- [x] Write new client.py against the Connect JSON transport
- [x] Delete queries.py (obsolete)
- [x] Update __init__.py exports
- [x] Rewrite tests
- [x] Update CLAUDE.md
- [x] Update README
- [x] Bump version to 1.0.0a1
- [x] Sanity check with mypy + pytest

## Summary of Changes

Rewrote chattolib against Chatto 0.4.x's ConnectRPC API after confirming that the GraphQL endpoint is gone (`https://chat.chatto.run/api/graphql` returns 404; `https://chat.chatto.run/api/connect/chatto.discovery.v1.ServerDiscoveryService/GetServer` returns the profile). Reference: chattocorp/chatto ADR-042 supersedes ADR-003.

Changes:
- Deleted `queries.py` and the old `subscriptions.py` (both GraphQL-specific).
- Added `_transport.py` — a tiny Connect JSON transport (POST `/api/connect/<Service>/<Method>` with JSON body, Bearer + session cookie auth, JSON error decoding).
- Rewrote `exceptions.py`: `ChattoGraphQLError` → `ChattoConnectError` carrying `code`, `message`, `status_code`, `details`.
- Rewrote `types.py` end-to-end: `StrEnum`s whose values match the wire protobuf enum-name strings (with tolerant parsing), dataclasses for each Connect message we surface (`User`, `ViewerUser`, `Room`/`RoomKind`/`RoomWithViewerState`, `Message`, `MessageAttachment`, `MessageReaction`, `ThreadSummary`, `LinkPreview`, `Notification`, `NotificationPreference`, `RoomGroup`+`SidebarLink`, `ActiveCall`, `Asset`, `TimelinePage`/`TimelineEvent`, `ServerProfile`/`ServerLogin`/`ServerRuntimeConfig`, `RoomBan`, `DirectoryMember`, etc.), plus `parse_datetime` / `format_datetime` RFC 3339 helpers.
- Rewrote `client.py`: `ChattoClient` now speaks Connect JSON for every service the old client used to reach via GraphQL, plus new ones exposed by the current API — `ServerDiscoveryService`, `ServerService`, `ViewerService`, `MyAccountService` (profile/password/avatar/settings/presence/custom status/account deletion), `UserService`, `RoomDirectoryService`, `RoomService` (lifecycle + membership + moderation + timeline + typing + attachments), `MessageService` (create/edit/delete + reactions + link previews + get/batch), `ThreadService`, `NotificationService`, `NotificationPreferencesService`, `PushNotificationService`, `AssetService`, `VoiceCallService`. Public `client.call(service, method, request)` escape hatch for anything not yet wrapped. Login still uses `/auth/login`.
- Added `realtime.py` — placeholder module. The Chatto realtime WebSocket is now a binary protobuf protocol, which needs generated bindings; deferred to a follow-up bean.
- Rewrote `tests/test_client.py` (33 tests, all passing) around mocked `/api/connect/*` endpoints. Refreshed `tests/test_integration.py` for the new surface.
- Bumped version to `1.0.0a1` (breaking rewrite). Made `websockets` an optional `[realtime]` extra since it is only needed for a future WS implementation.
- Refreshed `CLAUDE.md` and `README.md` for the Connect API and new naming conventions.

Verified: `ruff check`, `mypy --strict`, `pytest` all clean. Live sanity check hits `chatto.discovery.v1.ServerDiscoveryService.GetServer` on `chat.chatto.run` and returns Chatto 0.4.2.

## Follow-ups

- Realtime WebSocket protocol needs a protobuf-backed implementation. The stub in `realtime.py` documents the missing piece; would suggest a new `chattolib.realtime` module that ships generated bindings for `chatto.realtime.v1.RealtimeClientFrame` / `RealtimeServerFrame` and their transitive imports.
- `[[add-sidebarlink-support-to-chattolib]]` (existing low-priority bean) is now partly obsolete: `RoomGroup.sidebar_links` is already populated by `RoomDirectoryService`. Only sidebar-link *management* (create/update/delete) is still missing; those live under `AdminRoomLayoutService` which is intentionally out of scope for this rewrite.

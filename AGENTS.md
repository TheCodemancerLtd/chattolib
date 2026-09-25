# AGENTS.md

Guidance for AI coding assistants (Claude Code, Cursor, Aider, etc.) working in this repository. Human contributors are welcome to use it too.

**IMPORTANT**: before you do anything else, run the `beans prime` command and heed its output. Tasks for this project are tracked in `.beans/` via the [beans](https://github.com/hmans/beans) CLI.

## Runbooks

- **Releasing a new chattolib version tracking a Chatto server release** — [`docs/upgrade-chatto.md`](docs/upgrade-chatto.md). Regenerates protos, adapts the client for wire changes, bumps the version, verifies, commits, pushes to both remotes, builds, and publishes to PyPI.

## Project Overview

**chattolib** is an async Python client library for the [Chatto](https://chat.chatto.run) webchat Connect API (`https://chat.chatto.run/api/connect/…`). Chatto migrated from GraphQL to protobuf-first ConnectRPC in v0.4.x (see [ADR-042](https://github.com/chattocorp/chatto/blob/main/docs/adr/ADR-042-protobuf-first-public-api.md), which supersedes ADR-003). This library speaks Connect JSON over HTTP for all request/response operations.

## Versioning

**chattolib's version tracks the Chatto server version it targets.** A new Chatto release triggers a matching chattolib release (e.g. Chatto `0.4.2` → chattolib `0.4.2`). If a chattolib-only fix is needed between server releases, use a post-release suffix (`0.4.2.post1`) rather than bumping the base number ahead of Chatto.

## Build & Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests (mocked)
pytest tests/test_client.py

# Run integration tests (require CHATTO_LOGIN / CHATTO_PASSWORD)
pytest tests/test_integration.py -v

# Lint & format
ruff check .
ruff format .

# Type checking
mypy src/chattolib
```

## Architecture

The library uses the official **`connectrpc` Python package** for the
request/response API surface: `_transport.build_service_clients(base_url)`
instantiates one ConnectRPC service client per Chatto service, all sharing the
same address and the `google.protobuf` binary codec. Realtime events use a
separate binary-protobuf WebSocket protocol (`chatto.realtime.v1`) served at
`/api/realtime`, implemented in `realtime.py` on top of `websockets` and
generated protobuf bindings.

### Package layout: `src/chattolib/`

- **client.py** — `ChattoClient` async class. Each method builds a protobuf request, invokes the appropriate generated service stub via `_rpc`, and normalises the response into the library's dataclass types. `services` is a public escape hatch for reaching the raw ConnectRPC service clients directly.
- **_transport.py** — instantiates the ConnectRPC service clients, translates `connectrpc.errors.ConnectError` into `ChattoConnectError`/`ChattoAuthError`, and exposes `pb_to_dict(message)` for the request/response ↔ dataclass bridge.
- **types.py** — Dataclasses and `StrEnum` types mirroring the protobuf messages, with `.parse(dict)` classmethods that consume Connect JSON.
- **exceptions.py** — `ChattoError`, `ChattoConnectError` (wraps Connect protocol errors), `ChattoAuthError`.
- **realtime.py** — Protobuf realtime WebSocket client. `stream_events(client)` yields `RealtimeEvent(kind, payload, ...)` values. Errors surface as `ChattoRealtimeError` / `ChattoRealtimeCloseError`.
- **_pb/** — Vendored, generated Python protobuf message classes (`*_pb2.py`)
  and ConnectRPC service stubs (`*_connect.py`) for every Chatto service.
  Regenerate with `scripts/generate_pb.sh` (needs `protoc` and
  `protoc-gen-connect-python` on PATH). The script fetches the `.proto`
  sources from `chattocorp/chatto` and rewrites the bindings. The
  `_pb/__init__.py` inserts its own directory onto `sys.path` so the
  generated `from chatto.api.v1 import ...` imports resolve without polluting
  the top-level namespace of dependent projects.

### Connect protocol conventions

- Endpoint: `POST https://<host>/api/connect/<fully.qualified.Service>/<Method>` with a JSON body.
- Empty request messages send `{}`.
- Field names on the wire are **camelCase** (proto → JSON mapping). Python dataclass fields are `snake_case`.
- Enums on the wire are the **full enum value name** as a string, e.g. `"PRESENCE_STATUS_ONLINE"`. `types._parse_enum` also accepts the short tail (`"ONLINE"`) for robustness.
- Timestamps are RFC 3339 strings (usually `Z`-suffixed). Use `types.parse_datetime` / `types.format_datetime` helpers.
- `optional` scalars: absent from JSON when unset. A present empty string is distinct.
- `bytes`: base64-encoded strings (used by `MyAccountService.UploadAvatar` via the `ImageUpload` message).
- Errors: non-2xx HTTP status with a JSON body of `{"code": "...", "message": "...", "details": [...]}`. `ChattoConnectError` surfaces `code`, `message`, `status_code`, `details`.

### Auth

chattolib is a **bot** library. Bots authenticate with a **key** (e.g.
`cht_BK_...`) used **directly as a bearer token** — there is no password
login and no `/auth/login` round-trip. Construct a client with
`ChattoClient(token="cht_BK_...")`, or use the higher-level
`Bot.login(key, base_url=…)` facade (see `bot.py`). A bot is just a `User`
with `is_bot=true` plus a set of capability grants; the Connect API enforces
permissions per call, so a bot can invoke the same RPCs a human can, subject
to its grants.

### Key services exposed by the client

| Domain | Service (`chatto.api.v1.…` unless noted) | Notable RPCs |
|---|---|---|
| Discovery | `chatto.discovery.v1.ServerDiscoveryService` | `GetServer` (public) |
| Server | `ServerService` | `GetMotd`, `GetRuntimeConfig` |
| Viewer | `ViewerService` | `GetViewer` |
| My account | `MyAccountService` | `UpdateProfile`, `UpdateSettings`, `SetPresence` (legacy live report), `GetPresencePreference`, `SetPresencePreference`, `RefreshPresence`, `SetCustomStatus`, `DeleteCustomStatus`, `ChangePassword`, `DeleteMyAccount` (avatar upload was removed in 0.5.0b4) |
| Roles | `RoleService` | `ListRoles`, `GetRole`, `BatchGetRoles` |
| Room directory | `RoomDirectoryService` | `ListRooms`, `ListRoomGroups`, `GetRoomGroup`, `BatchGetRoomGroups`, `GetRoom`, `BatchGetRooms` |
| Rooms | `RoomService` | `CreateRoom`, `UpdateRoom`, `ArchiveRoom`, `UnarchiveRoom`, `JoinRoom`, `JoinRoomGroup`, `StartDM`, `LeaveRoom`, `AddMember`, `RemoveMember`, `ListMembers`, `GetMember`, `BatchGetMembers`, `BanMember`, `UnbanMember`, `ListBans`, `RefreshTypingIndicator`, `GetRoomEvents`, `GetRoomEventsAround`, `MarkRoomAsRead`, `ListRoomAttachments` |
| Messages | `MessageService` | `FetchLinkPreview`, `CreateMessage`, `UpdateMessage`, `DeleteMessage`, `DeleteAttachment`, `DeleteLinkPreview`, `GetMessage`, `BatchGetMessages`, `AddReaction`, `RemoveReaction` |
| Threads | `ThreadService` | `FollowThread`, `UnfollowThread`, `ListFollowedThreads`, `GetThreadEvents`, `GetThreadEventsAround`, `MarkThreadAsRead` |
| Notifications | `NotificationService` | `ListNotifications`, `GetNotification`, `BatchGetNotifications`, `ListRoomNotifications`, `ListRoomNotificationCounts`, `HasNotifications`, `DismissNotification`, `DismissAllNotifications` |
| Notification prefs | `NotificationPreferencesService` | `Get`/`Update` × `Server`/`Room` |
| Notification policy | `NotificationPolicyService` | `GetNotificationPolicy`, `BatchGetNotificationPolicies`, `UpdateNotificationPolicy` — all scoped (server / room group / room) via `NotificationPolicyScope` |
| Permissions | `PermissionService` | `ListEffectivePermissions` (the resolved permission decisions for a user) |
| Push | `PushNotificationService` | `Subscribe`, `Unsubscribe` |
| Assets | `AssetService` | `GetAsset`, `BatchGetAssets` |
| Asset uploads | `AssetUploadService` | `CreateUpload`, `UploadChunk`, `GetUpload`, `CompleteUpload`, `CancelUpload`. `upload_attachment(room, path)` helper computes SHA-256, chunks, and completes in one call. |
| Admin: server | `chatto.admin.v1.AdminServerService` | `GetServerConfig`, `UpdateServerConfig`, `UploadServerLogo`, `DeleteServerLogo`, `UploadServerBanner`, `DeleteServerBanner`, `GetServerSecurityConfig`, `UpdateBlockedUsernames` |
| Admin: room layout | `chatto.admin.v1.AdminRoomLayoutService` | `ListRoomGroups`, `Create/Update/Delete/ReorderRoomGroup(s)`, `MoveRoomGroup`, `MoveRoomToGroup`, `ReorderSidebarItemsInGroup`, `MoveSidebarItem`, `Create/Update/Delete/MoveSidebarLink(ToGroup)` |
| Admin: users | `chatto.admin.v1.AdminUserService` | `ListMembers`, `GetMember`, `BatchGetMembers`, `AssignRole`, `RevokeRole`, `UpdateUser`, `UpdateUserPassword`, `ClearUsernameCooldown`, `DeleteUser` |
| Admin: roles | `chatto.admin.v1.AdminRoleService` | `ListRoles`, `GetRole`, `CreateRole`, `UpdateRole`, `DeleteRole`, `ReorderRoles` |
| Admin: event log | `chatto.admin.v1.AdminEventLogService` | `ListEvents`, `ListEventTypes`, `GetEvent` (raw response) |
| Admin: diagnostics | `chatto.admin.v1.AdminDiagnosticsService` | `GetSystemInfo` (raw response) |
| Admin: permissions | `chatto.admin.v1.AdminPermissionService` | `GetRole/UserPermissionMatrix`, `ListRole/UserPermissionDecisions`, `ExplainPermissions`, `SetRolePermission`, `SetUserPermission` (raw responses where the permission shape is server-version-dependent) |
| Voice calls | `VoiceCallService` | `ListActiveCalls`, `GetActiveCall`, `BatchGetActiveCalls`, `JoinCall`, `LeaveCall`, `CreateCallToken` |
| Realtime (WS) | `chatto.realtime.v1` protobuf WS (protocol v4) | `stream_events(client)` / `RealtimeConnection` — the client sends one `RealtimeSubscribe` handshake; the server streams `event` (a 48-member oneof of thin, caller-scoped hints, incl. `viewer_presence_preference_changed` added in 0.5.0b6), `snapshot`, `caught_up`, `heartbeat`, and `close` (with a `RealtimeCloseCode` and `retry_after`) |

### Naming conventions

- Python method names: `verb_noun` style (`create_room`, `post_message`, `mark_room_as_read`); most method names mirror the Connect method with the service name dropped.
- Python field names: `snake_case`; wire JSON uses `camelCase` and parsers translate.
- Enum classes: `PascalCase` (`PresenceStatus`, `RoomKind`, `NotificationLevel`, `TimeFormat`, `ImageFitMode`, `RoomDirectoryScope`, `VideoProcessingStatus`). Their `value` is the full protobuf enum-name string (e.g. `"ROOM_KIND_CHANNEL"`).
- Dataclasses: `PascalCase` matching the protobuf message names (`Room`, `Message`, `Notification`, `RoomWithViewerState`, etc.).

### Gotchas from the migration

- The old `RoomType` enum is now `RoomKind` (`ROOM_KIND_CHANNEL` / `ROOM_KIND_DM`).
- `Room` no longer carries viewer-scoped state (`hasUnread`, etc.). The directory service returns `RoomWithViewerState { room, viewerState }` for that.
- `PresenceStatus` now includes `UNSPECIFIED`. `SetPresence` (was `UpdatePresence`) rejects both `OFFLINE` and `UNSPECIFIED`.
- `TimeFormat` values changed: `HOUR_12` / `HOUR_24` / `AUTO` (was `TWELVE_HOUR` / `TWENTY_FOUR_HOUR`).
- Notifications are strongly typed via a `oneof` (`direct_message`, `mention`, `reply`, `room_message`); `Notification.kind` carries the tag.
- Timeline events (`RoomTimelineEvent`) are also a `oneof`; `TimelineEvent.kind` names the case (`message_posted`, `room_created`, …). Only `message_posted` populates a `Message` payload.
- `User.is_bot` is gone; a user is a bot when it carries a `bot` (`BotInfo { owner_user_id }`) field. `User.is_bot` is now a derived `@property`.
- Avatar upload was **removed** in 0.5.0b4 — there is no `UploadAvatar`/`ImageUpload` and no `upload_avatar`/`delete_avatar` client methods anymore.
- Server profile fields are no longer inside `server.profile`; the shape is now `ServerPublicProfile` returned by `ServerDiscoveryService.GetServer`.
- No more `motd` on the public profile; it is a separate authenticated RPC (`ServerService.GetMotd`).
- Room groups can contain `SidebarLink` items (not just rooms). `RoomGroup.sidebar_links` exposes them.
- **0.5.0b6 split presence into a *saved preference* and a *live report*.** `SetPresence` is now the legacy, transient live report (still rejects `OFFLINE`/`UNSPECIFIED`); a saved choice takes precedence over it, even a `user_selected` one. The new pair is `GetPresencePreference`/`SetPresencePreference` (choice for every device on the server; `OFFLINE` = "Appear Offline" and *is* allowed there; a stale `expected_revision` returns `ABORTED`) plus `RefreshPresence` for 30-second liveness. `Message` also gained `viewer_state` (`MessageViewerState.can_reply_in_thread`), resolved per viewer even before a thread exists.
- **Never regenerate protos from `chattocorp/chatto@main`.** `scripts/generate_pb.sh` defaults to a tag derived from `pyproject.toml`: `v<base>` for finals, and `v<base>-<kind>.<n>` for PEP 440 pre-releases (`0.5.0b6` → `v0.5.0-beta.6`), probing candidates with `git ls-remote` (exact ref match; the REST `/tags/{name}` endpoint 404s on lightweight tags). Override with `CHATTO_REF=<tag>` only when you know the deployed server has caught up. chattolib 0.4.19 shipped once from `main` and broke realtime for every downstream client because Chatto's main had a protocol-v2 rewrite that the deployed 0.4.19 server did not speak.

### Known bugs

- **Realtime is now protocol v4 — there are no projection frames.** The v2/v3 "projection" frames (`RealtimeProjectionEvent` / per-op `RealtimeProjectionOperation`) no longer exist. Instead the client sends a single `RealtimeSubscribe` handshake and the server streams `event` frames (a 48-member `oneof` of *thin, caller-scoped hints* — identifiers, not full resources), plus `snapshot` (one initial state), `caught_up` (recovery-to-live boundary), `heartbeat`, and `close` (with a `RealtimeCloseCode` and `retry_after`). Live events carry IDs, so clients hydrate the referenced resource via the matching ConnectRPC (e.g. `get_message`) using the event's `cursor`. `Bot._handle_live` re-derives `BotMessageEvent` by hydrating the posted message. Since 0.5.0b6 the oneof has a 48th member, `viewer_presence_preference_changed` (an empty payload delivered only to the account whose own presence *preference* changed; `Bot` dispatches it as `kind="presence_preference"` and the new choice is read back via `get_presence_preference`).
- `RealtimeClose.code` is the enum `RealtimeCloseCode` (e.g. `SESSION_TERMINATED`, `RESYNC_REQUIRED`, `UNSUPPORTED_PROTOCOL`); `chattolib.realtime` maps it to its short name for `ChattoRealtimeCloseError.code`. A non-`reconnect` close (e.g. `SESSION_TERMINATED`) means the bot should stop, not reconnect.

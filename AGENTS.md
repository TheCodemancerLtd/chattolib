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
same address and the `google.protobuf` binary codec. `httpx` remains for the
one non-Connect endpoint (`/auth/login`). Realtime events use a separate
binary-protobuf WebSocket protocol (`chatto.realtime.v1`) served at
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

`ChattoClient.login(login, password, base_url=…)` still uses Chatto's non-Connect `/auth/login` HTTP endpoint. It captures both the returned bearer token and any `chatto_session` cookie, and every subsequent Connect call sends both.

### Key services exposed by the client

| Domain | Service (`chatto.api.v1.…` unless noted) | Notable RPCs |
|---|---|---|
| Discovery | `chatto.discovery.v1.ServerDiscoveryService` | `GetServer` (public) |
| Server | `ServerService` | `GetMotd`, `GetRuntimeConfig` |
| Viewer | `ViewerService` | `GetViewer` |
| My account | `MyAccountService` | `UpdateProfile`, `UploadAvatar`, `DeleteAvatar`, `UpdatePassword`, `UpdateSettings`, `UpdatePresence`, `UpdateCustomStatus`, `DeleteCustomStatus`, `RequestAccountDeletion`, `DeleteMyAccount`, `ListExternalIdentities`, `StartExternalIdentityLink`, `DisconnectExternalIdentity` |
| Users | `UserService` | `ListUsers`, `GetUser`, `BatchGetUsers` |
| Roles | `RoleService` | `ListRoles`, `GetRole`, `BatchGetRoles` |
| External identity auth (public) | `chatto.auth.v1.ExternalIdentityAuthService` | `GetPendingExternalIdentity`, `CreateExternalIdentityAccount`, `ConfirmExternalIdentityLink`, `CancelExternalIdentityFlow` |
| Room directory | `RoomDirectoryService` | `ListRooms`, `ListRoomGroups`, `GetRoomGroup`, `BatchGetRoomGroups`, `GetRoom`, `BatchGetRooms` |
| Rooms | `RoomService` | `CreateRoom`, `UpdateRoom`, `ArchiveRoom`, `UnarchiveRoom`, `JoinRoom`, `JoinRoomGroup`, `StartDM`, `LeaveRoom`, `AddMember`, `RemoveMember`, `ListMembers`, `GetMember`, `BatchGetMembers`, `BanMember`, `UnbanMember`, `ListBans`, `UpdateTypingIndicator`, `GetRoomEvents`, `GetRoomEventsAround`, `MarkRoomAsRead`, `ListRoomAttachments` |
| Messages | `MessageService` | `FetchLinkPreview`, `CreateMessage`, `UpdateMessage`, `DeleteMessage`, `DeleteAttachment`, `DeleteLinkPreview`, `GetMessage`, `BatchGetMessages`, `AddReaction`, `RemoveReaction` |
| Threads | `ThreadService` | `FollowThread`, `UnfollowThread`, `ListFollowedThreads`, `GetThreadEvents`, `GetThreadEventsAround`, `MarkThreadAsRead` |
| Notifications | `NotificationService` | `ListNotifications`, `GetNotification`, `BatchGetNotifications`, `ListRoomNotifications`, `ListRoomNotificationCounts`, `HasNotifications`, `DismissNotification`, `DismissAllNotifications` |
| Notification prefs | `NotificationPreferencesService` | `Get`/`Update` × `Server`/`Room` |
| Push | `PushNotificationService` | `Subscribe`, `Unsubscribe` |
| Assets | `AssetService` | `GetAsset`, `BatchGetAssets` |
| Asset uploads | `AssetUploadService` | `CreateUpload`, `UploadChunk`, `GetUpload`, `CompleteUpload`, `CancelUpload`. `upload_attachment(room, path)` helper computes SHA-256, chunks, and completes in one call. |
| Admin: server | `chatto.admin.v1.AdminServerService` | `GetServerConfig`, `UpdateServerConfig`, `UploadServerLogo`, `DeleteServerLogo`, `UploadServerBanner`, `DeleteServerBanner`, `GetServerSecurityConfig`, `UpdateBlockedUsernames` |
| Admin: room layout | `chatto.admin.v1.AdminRoomLayoutService` | `ListRoomGroups`, `Create/Update/Delete/ReorderRoomGroup(s)`, `MoveRoomToGroup`, `ReorderSidebarItemsInGroup`, `Create/Update/Delete/MoveSidebarLink(ToGroup)` |
| Admin: users | `chatto.admin.v1.AdminUserService` | `ListMembers`, `GetMember`, `BatchGetMembers`, `AssignRole`, `RevokeRole`, `UpdateUser`, `UpdateUserPassword`, `ClearUsernameCooldown`, `DeleteUser` |
| Admin: roles | `chatto.admin.v1.AdminRoleService` | `ListRoles`, `GetRole`, `CreateRole`, `UpdateRole`, `DeleteRole`, `ReorderRoles` |
| Admin: event log | `chatto.admin.v1.AdminEventLogService` | `ListEvents`, `ListEventTypes`, `GetEvent` (raw response) |
| Admin: diagnostics | `chatto.admin.v1.AdminDiagnosticsService` | `GetSystemInfo` (raw response) |
| Admin: permissions | `chatto.admin.v1.AdminPermissionService` | `GetRole/UserPermissionMatrix`, `ListRole/UserPermissionDecisions`, `ExplainPermissions`, `SetRolePermission`, `SetUserPermission` (raw responses where the permission shape is server-version-dependent) |
| Voice calls | `VoiceCallService` | `ListActiveCalls`, `GetActiveCall`, `BatchGetActiveCalls`, `JoinCall`, `LeaveCall`, `GetCallToken` |
| Realtime (WS) | `chatto.realtime.v1` protobuf WS (protocol v1) | `stream_events(client)` / `RealtimeConnection` — full frame set: hello, subscribe, event, heartbeat, ping/pong, error, close |

### Naming conventions

- Python method names: `verb_noun` style (`create_room`, `post_message`, `mark_room_as_read`); most method names mirror the Connect method with the service name dropped.
- Python field names: `snake_case`; wire JSON uses `camelCase` and parsers translate.
- Enum classes: `PascalCase` (`PresenceStatus`, `RoomKind`, `NotificationLevel`, `TimeFormat`, `ImageFitMode`, `RoomDirectoryScope`, `VideoProcessingStatus`). Their `value` is the full protobuf enum-name string (e.g. `"ROOM_KIND_CHANNEL"`).
- Dataclasses: `PascalCase` matching the protobuf message names (`Room`, `Message`, `Notification`, `RoomWithViewerState`, etc.).

### Gotchas from the migration

- The old `RoomType` enum is now `RoomKind` (`ROOM_KIND_CHANNEL` / `ROOM_KIND_DM`).
- `Room` no longer carries viewer-scoped state (`hasUnread`, etc.). The directory service returns `RoomWithViewerState { room, viewerState }` for that.
- `PresenceStatus` now includes `UNSPECIFIED`. `UpdatePresence` still rejects both `OFFLINE` and `UNSPECIFIED`.
- `TimeFormat` values changed: `HOUR_12` / `HOUR_24` / `AUTO` (was `TWELVE_HOUR` / `TWENTY_FOUR_HOUR`).
- Notifications are strongly typed via a `oneof` (`direct_message`, `mention`, `reply`, `room_message`); `Notification.kind` carries the tag.
- Timeline events (`RoomTimelineEvent`) are also a `oneof`; `TimelineEvent.kind` names the case (`message_posted`, `room_created`, …). Only `message_posted` populates a `Message` payload.
- File uploads (avatar) use the `ImageUpload` message with base64-encoded bytes, not multipart. `upload_avatar(path)` handles the base64 encoding.
- Server profile fields are no longer inside `server.profile`; the shape is now `ServerPublicProfile` returned by `ServerDiscoveryService.GetServer`.
- No more `motd` on the public profile; it is a separate authenticated RPC (`ServerService.GetMotd`).
- Room groups can contain `SidebarLink` items (not just rooms). `RoomGroup.sidebar_links` exposes them.
- **Never regenerate protos from `chattocorp/chatto@main`.** `scripts/generate_pb.sh` now defaults to `v<version>` (from `pyproject.toml`); override with `CHATTO_REF=<tag>` only when you know the deployed server has caught up. chattolib 0.4.19 shipped once from `main` and broke realtime for every downstream client because Chatto's main had a protocol-v2 rewrite that the deployed 0.4.19 server did not speak.

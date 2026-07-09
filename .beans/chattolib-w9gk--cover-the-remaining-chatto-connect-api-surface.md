---
# chattolib-w9gk
title: Cover the remaining Chatto Connect API surface
status: completed
type: feature
priority: normal
created_at: 2026-07-09T00:13:58Z
updated_at: 2026-07-09T00:20:16Z
---

Chattolib now covers most user-facing Chatto Connect services. Remaining surface: AssetUploadService (chunked message attachment upload), public RoleService, ExternalIdentityAuthService, MyAccountService external-identity RPCs (List/Start/Disconnect), and the admin services (AdminServerService, AdminRoomLayoutService with sidebar-link management, AdminRoleService, AdminUserService, AdminEventLogService, AdminDiagnosticsService, AdminPermissionService).

## Summary of Changes

Added the remaining Connect services to ChattoClient. The library now covers every non-operator RPC exposed by connectapi.API.Handlers() in chattocorp/chatto main.

### New service coverage
- **AssetUploadService** — CreateUpload, UploadChunk, GetUpload, CompleteUpload, CancelUpload. Plus `upload_attachment(room_id, path)` convenience: reads bytes, computes SHA-256, respects the server's max_chunk_size, then completes. Returns an Asset whose id can be passed to `post_message(attachment_asset_ids=[...])`.
- **RoleService (public)** — ListRoles, GetRole, BatchGetRoles.
- **MyAccountService external identity** — ListExternalIdentities, StartExternalIdentityLink, DisconnectExternalIdentity.
- **ExternalIdentityAuthService (public OAuth handoff)** — GetPendingExternalIdentity, CreateExternalIdentityAccount, ConfirmExternalIdentityLink, CancelExternalIdentityFlow.
- **AdminServerService** — GetServerConfig, UpdateServerConfig, UploadServerLogo, DeleteServerLogo, UploadServerBanner, DeleteServerBanner, GetServerSecurityConfig, UpdateBlockedUsernames.
- **AdminRoomLayoutService** — ListRoomGroups, Create/Update/Delete/ReorderRoomGroup(s), MoveRoomToGroup, ReorderSidebarItemsInGroup, Create/Update/Delete/MoveSidebarLink(ToGroup). Closes the SidebarLink follow-up bean.
- **AdminUserService** — ListMembers, GetMember, BatchGetMembers, AssignRole, RevokeRole, UpdateUser, UpdateUserPassword, ClearUsernameCooldown, DeleteUser.
- **AdminRoleService** — ListRoles, GetRole, CreateRole, UpdateRole, DeleteRole, ReorderRoles.
- **AdminEventLogService, AdminDiagnosticsService, AdminPermissionService** — raw dict responses because the underlying shapes are server-version-dependent and admin-focused (the client caller can decode the JSON directly).

### Types
- New dataclasses: `Role`, `AdminRole`, `AssetUpload`, `ExternalIdentityProvider`, `LinkedExternalIdentity`, `ServerConfig`, `AdminMember`, `AdminRoomLayoutGroup`.
- New enums: `AssetUploadStatus`, `AdminRoomLayoutItemKind`.

### Tests & docs
- 6 new mocked tests covering RoleService, AssetUploadService (full create/chunk/complete cycle), MyAccount ExternalIdentities, AdminRoomLayoutService (list/create sidebar link), and AdminServerService (update config). Total: 50 mocked tests, all passing. ruff and mypy --strict clean.
- Live-verified against Chatto HQ with RoboChatto: RoleService.ListRoles returned the 4 system roles (everyone/moderator/admin/owner) with all fields decoded, MyAccount.ListExternalIdentities returned empty (no OAuth providers configured on Chatto HQ).
- Skipped a live upload test to avoid orphaning assets on Chatto HQ; the mocked upload_attachment round-trip already exercises SHA-256 hashing, base64 chunk encoding, offset tracking, and completion.
- CLAUDE.md refreshed with the new service rows and MyAccount RPC list update.

---
# chattolib-5ggo
title: Update chattolib to Chatto 0.4.9
status: completed
type: task
priority: high
created_at: 2026-07-12T23:46:37Z
updated_at: 2026-07-12T23:48:14Z
---

Chatto HQ is now serving 0.4.9. Regenerate proto bindings from upstream, diff the API surface for breaking or additive changes, adapt the client if needed, bump chattolib to 0.4.9, run the full check + live-verify, publish, and push.

## Summary of Changes
Regenerated proto bindings from upstream. Delta from 0.4.3:

**Additive fields**
- `Message.deleted_at` (google.protobuf.Timestamp) — surface added to the `Message` dataclass and its `.parse()` classmethod.
- `GetSystemInfoResponse.asset_cleanup` (AdminAssetCleanupStatus) with a new AdminAssetCleanupHealth enum. Passes through the existing raw-dict `admin_get_system_info()` return; no code change needed.

**Metadata-only**
- Several RPCs now advertise `idempotency_level`: `DeleteAvatar`, `DeleteCustomStatus`, `DismissNotification`, `Unsubscribe`, `GetServer`. No wire change.

**Server-side validation tightening**
- `CreateMessageRequest.attachment_asset_ids` now capped at 10 items with per-item length constraints. Server-enforced; no client change.

Bumped `pyproject.toml` from `0.4.3` to `0.4.9`. `ruff` + `mypy --strict` + `pytest` (48 passed, 4 skipped) all clean.

Live-verified against Chatto HQ (0.4.9): login, viewer, list_rooms, get_motd all decode correctly.

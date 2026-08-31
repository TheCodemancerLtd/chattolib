---
# chattolib-uuqm
title: 'Fix Bot._on_timeline_upsert: RoomTimelineRoomEvent has room_id not room'
status: completed
type: bug
priority: normal
created_at: 2026-08-31T13:12:27Z
updated_at: 2026-08-31T13:18:42Z
---

## Resolution

Fixed on main (commit a39cb6d). One refinement over the originally proposed patch: `RoomTimelineRoomEvent.room_id` is a plain proto3 string with no presence, so `sub.HasField("room_id")` would itself raise `ValueError`. The fix tests the string by truthiness instead:

    if sub is not None and sub.room_id:
        room = Room.parse({"id": sub.room_id})

Added regression test `test_dispatch_room_lifecycle_event` (builds a room_created upsert, asserts a BotRoomEvent with the room id is dispatched, no raise). Verified it fails against the old code with the exact "room does not have presence" ValueError and passes with the fix. Full suite green (74 passed), ruff + mypy clean.

Note: this is a runtime fix to already-shipped code; it will ride in the next release. The robochatto local-venv patch is now superseded by this.

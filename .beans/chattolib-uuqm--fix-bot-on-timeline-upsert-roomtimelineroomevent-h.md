---
# chattolib-uuqm
title: 'Fix Bot._on_timeline_upsert: RoomTimelineRoomEvent has room_id not room'
status: in-progress
type: bug
created_at: 2026-08-31T13:12:27Z
updated_at: 2026-08-31T13:12:27Z
---

The _on_timeline_upsert handler in bot.py calls sub.HasField('room') for room-lifecycle events (room_created, user_joined_room, etc.), but the RoomTimelineRoomEvent protobuf only has a room_id string field, not a nested room message. This raises a protobuf error that crashes the server task, causing a crash-restart loop when combined with retained room timeline replay.

Fix: change sub.HasField('room') to sub.HasField('room_id') and build the Room from the ID string instead of a nested message.

Discovered during robochatto 0.5 upgrade testing (2026-08-31). Local venv patch applied at robochatto/.venv/lib/python3.14/site-packages/chattolib/bot.py line ~603. The patch:

    room = None
    sub = getattr(event, case, None)
    if sub is not None:
        if sub.HasField("room_id") and sub.room_id:
            room = Room.parse({"id": sub.room_id})
    await self._dispatch(BotRoomEvent(bot=self, kind="room", room=room, detail=case))

Replaces the old:
    if sub is not None and sub.HasField("room"):
        room = Room.parse(_pb_to_dict(sub.room))

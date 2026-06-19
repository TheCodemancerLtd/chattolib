---
# chattolib-l483
title: Cross-check chattolib against chatto v0.3.4 source SDL
status: completed
type: task
priority: high
created_at: 2026-06-19T13:08:27Z
updated_at: 2026-06-19T13:16:46Z
---

I built 0.1.0b3 from live introspection of chat.chatto.run. The server reports version 0.3.4. The canonical SDL lives in cli/internal/graph/*.graphqls in github.com/chattocorp/chatto. Verify the lib matches source-of-truth, not just what introspection happened to expose, and fix any gaps (deprecations, defaults, file-upload helpers, mutation arg ordering, missing operations).

## Tasks
- [x] Concatenate the .graphqls files and diff against chattolib queries/types
- [x] Check for deprecated fields the lib still uses
- [x] Check for new operations missing from the lib that introspection didn't reveal
- [x] Verify input default values and required/optional flags
- [x] Decide whether a follow-up version bump is warranted (yes: 0.1.0b3 → 0.1.0b4)

## Summary of Changes
**Real bugs in 0.1.0b3 found and fixed by comparing against cli/internal/graph/*.graphqls**

Mutation selection sets:
- updateMessage returns Boolean! — I was selecting { id } which would fail at runtime
- archiveRoom/unarchiveRoom return Room! — I selected nothing (required sub-selection)
- setServerNotificationLevel/setRoomNotificationLevel return ViewerNotificationPreference!
- reorderRoomGroups returns [RoomGroup!]!, moveRoomToGroup returns Room!, reorderRoomsInGroup returns RoomGroup!
- updateServerConfig returns ServerProfile! (I had nested .profile which doesn't exist on ServerProfile)

Type fixes in Server query:
- enabledAuthProviders (list of strings) → authProviders { id type label } (list of AuthProvider!)

Pagination cursors:
- Room.events(before/after) takes String (opaque cursors), not Time

Subscription union field conflicts:
- Aliased threadRootEventId on MessagePostedEvent (messageThreadRootEventId) and UserTypingEvent (typingThreadRootEventId) because both are nullable, conflicting with non-null occurrences in ThreadCreatedEvent and ThreadFollowChangedEvent
- Aliased messageEventId on Asset* events (assetMessageEventId) for the same reason
- Aliased reason on MessageRetractedEvent (retractionReason) vs non-null reason on SessionTerminatedEvent
- Aliased roomId on Asset* and NotificationLevelChanged events (assetRoomId, notifRoomId) — nullable variants
- Added missing CallStartedEvent { roomId callId } and CallEndedEvent { roomId callId }

Client surface:
- post_message: added mention_confirmation_token kwarg
- update_message: added also_send_to_channel kwarg, now returns bool
- archive_room/unarchive_room return Room dataclass
- update_server_config returns ServerProfile

Version bumped to 0.1.0b4.

---
# chattolib-kbz0
title: Update chattolib for Chatto v0.1.0-beta.3
status: completed
type: task
priority: high
created_at: 2026-06-12T14:08:43Z
updated_at: 2026-06-12T14:18:28Z
---

Update the library to match the new schema introspected from chat.chatto.run for v0.1.0-beta.3. Key deltas: MessageUpdatedEvent→MessageEditedEvent, MessageDeletedEvent→MessageRetractedEvent, VideoProcessingCompletedEvent→AssetProcessing*Events, plus room groups, room bans, settings/notification preferences, RBAC. See subtask checklist.

## Schema deltas observed

### Event renames (myEvents subscription)
- MessageUpdatedEvent → MessageEditedEvent (now has body, attachments, linkPreview, updatedAt)
- MessageDeletedEvent → MessageRetractedEvent (has reason)
- VideoProcessingCompletedEvent → AssetProcessingStartedEvent / AssetProcessingSucceededEvent / AssetProcessingFailedEvent / AssetDeletedEvent (assetId, not attachmentId)
- ServerConfigUpdatedEvent → gone (use ServerUpdatedEvent which now carries logoUrl/bannerUrl)
- RoomLayoutUpdatedEvent → RoomGroupsUpdatedEvent
- New: ThreadCreatedEvent, RoomMemberBannedEvent, RoomMemberUnbannedEvent, MentionStatusClearedEvent

### Type changes
- Server: server profile fields moved to server.profile sub-object; rooms still on Server; new roomGroups, viewer* flags
- Room: dropped hasMention; added members connection, viewerCan* flags, viewerNotificationPreference
- User: presenceStatus is NON_NULL; new hasVerifiedEmail, settings, etc.
- MessagePostedEvent: inThread → threadRootEventId; reactions returns ReactionSummary; new updatedAt, echoOfEventId, threadParticipants, threadReplies
- Reaction → ReactionSummary (same fields)
- Attachment: width/height NON_NULL; added assetUrl, thumbnailUrl, videoProcessing
- LinkPreview: added imageAssetId
- Viewer.notifications → NotificationsConnection (items, totalCount, hasMore)
- Viewer.followedThreads → FollowedThreadsConnection (threads, totalCount, hasMore)
- root Query.users removed (use server.members)

### Input changes
- PostMessageInput: inThread → threadRootEventId; new attachments: [Upload!], linkPreview: LinkPreviewInput
- CreateRoomInput: groupId now required
- UpdateProfileInput: userId now required
- UpdateSettingsInput: userId required
- UpdateMyPresenceInput: status type is PresenceStatusInput enum (ONLINE/AWAY/DND only — no OFFLINE)
- MarkRoomAsReadInput / MarkThreadAsReadInput: optional upToEventId
- New: BanRoomMemberInput, UnbanRoomMemberInput, CreateRoomGroupInput, UpdateRoomGroupInput, DeleteRoomGroupInput, MoveRoomToGroupInput, ReorderRoomGroupsInput, ReorderRoomsInGroupInput, SetRoomNotificationLevelInput, SetServerNotificationLevelInput, PushSubscriptionInput, UnsubscribeFromPushInput, DeleteAttachmentInput, DeleteLinkPreviewInput, DeleteAvatarInput, DeleteMyAccountInput, JoinGroupInput, UploadServerLogoInput, UploadServerBannerInput, LinkPreviewInput

### New mutations
unarchiveRoom, banRoomMember, unbanRoomMember, deleteAttachment, deleteLinkPreview, deleteAvatar, requestAccountDeletion, deleteMyAccount, setServerNotificationLevel, setRoomNotificationLevel, subscribeToPush, unsubscribeFromPush, createRoomGroup, updateRoomGroup, deleteRoomGroup, reorderRoomGroups, moveRoomToGroup, reorderRoomsInGroup, updateSettings, joinGroup, uploadServerLogo, deleteServerLogo, uploadServerBanner, deleteServerBanner

## Tasks
- [x] Update queries.py: rewrite QUERY_SERVER (profile sub-object, roomGroups), drop hasMention from Room queries, rename inThread→threadRootEventId, fix events subscription fragments
- [x] Update queries.py: add new queries (linkPreview, activeCallRoomIds) and remove QUERY_USERS
- [x] Update queries.py: update mutations (DM, profile, presence, mark read), add new mutations
- [x] Update types.py: rename Reaction→ReactionSummary; drop Room.has_mention; add ServerProfile, RoomGroup, RoomBan, UserSettings; add new event/notification dataclasses; tighten Attachment/User nullability
- [x] Update client.py: rewrite parsers; remove users(); add new client methods; PresenceStatusInput handling
- [x] Update __init__.py exports
- [x] Update test_client.py for new shape
- [x] Bump version in pyproject.toml to 0.1.0b3

## Summary of Changes
- queries.py: rewrote all queries/mutations/subscription fragments to match v0.1.0-beta.3 schema. Server query reads profile sub-object and roomGroups. Room query drops hasMention. Room events query uses threadRootEventId, ReactionSummary, new attachment fields (width/height/thumbnailUrl), updatedAt, echo*, viewerIsFollowingThread. myEvents subscription updated for renamed events (MessageEdited/Retracted, AssetProcessing*, RoomGroupsUpdated) and new ones (ThreadCreated, RoomMemberBanned/Unbanned, MentionStatusCleared).
- types.py: added ServerProfile, RoomGroup, RoomBan, UserSettings, AssetURL, FollowedThreadsPage, NotificationsPage, ReactionSummary (Reaction kept as alias), PresenceStatusInput; removed Room.has_mention; widened User/Attachment defaults.
- client.py: new parsers for the new types; thread_events traverses MessagePostedEvent.threadReplies; followed_threads & notifications now return connection-shaped pages; create_room takes a required group_id; update_profile takes a required user_id; new methods: server_profile, room_groups, server_members, link_preview, active_call_room_ids, delete_attachment, delete_link_preview, update_room, unarchive_room, join_group, ban/unban_room_member, mark_*_as_read with up_to_event_id, delete_avatar, update_settings, request_account_deletion, delete_my_account, set_(server|room)_notification_level, subscribe_to_push, unsubscribe_from_push, create/update/delete/reorder room groups, move_room_to_group, upload/delete server logo+banner, update_server_config. update_presence rejects OFFLINE (PresenceStatusInput has no OFFLINE).
- __init__.py: exports the new types.
- tests/test_client.py: updated mock payloads to match the new schema; added followed_threads, notifications, archive, room group, ban, and presence-rejection tests.
- pyproject.toml: bumped 0.0.174a1 → 0.1.0b3.
- CLAUDE.md: refreshed the API domains table and naming conventions to reflect renames, room groups, and PresenceStatusInput.

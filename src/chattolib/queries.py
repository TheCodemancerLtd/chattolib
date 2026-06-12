"""GraphQL query, mutation, and subscription strings."""

# --- Queries ---

QUERY_ME = """
query Me {
    viewer {
        user {
            id
            login
            displayName
            createdAt
            avatarUrl
            presenceStatus
            settings { timezone timeFormat }
        }
    }
}
"""

QUERY_SERVER = """
query Server {
    server {
        version
        enabledAuthProviders
        pushNotificationsEnabled
        vapidPublicKey
        livekitUrl
        directRegistrationEnabled
        videoProcessingEnabled
        maxUploadSize
        maxVideoUploadSize
        messageEditWindowSeconds
        memberCount
        roomCount
        assetCount
        profile { name logoUrl bannerUrl welcomeMessage motd description }
        rooms { id type name description archived groupId hasUnread }
        roomGroups { id name description rooms { id } }
    }
}
"""

QUERY_ROOM = """
query Room($roomId: ID!) {
    room(roomId: $roomId) {
        id
        type
        name
        description
        archived
        groupId
        hasUnread
    }
}
"""

QUERY_ROOM_EVENTS = """
query RoomEvents($roomId: ID!, $limit: Int, $before: Time, $after: Time) {
    room(roomId: $roomId) {
        events(limit: $limit, before: $before, after: $after) {
            events {
                id
                createdAt
                actorId
                actor { id login displayName avatarUrl presenceStatus }
                event {
                    ... on MessagePostedEvent {
                        roomId
                        body
                        updatedAt
                        attachments {
                            id roomId filename contentType size width height url thumbnailUrl
                        }
                        reactions { emoji count hasReacted users { id login displayName } }
                        inReplyTo
                        threadRootEventId
                        replyCount
                        lastReplyAt
                        echoOfEventId
                        echoFromThreadRootEventId
                        viewerIsFollowingThread
                        linkPreview {
                            url title description imageUrl imageAssetId siteName embedType embedId
                        }
                    }
                }
            }
            hasOlder
            hasNewer
            startCursor
            endCursor
        }
    }
}
"""

QUERY_THREAD_EVENTS = """
query ThreadEvents($roomId: ID!, $eventId: ID!) {
    room(roomId: $roomId) {
        event(eventId: $eventId) {
            id
            event {
                ... on MessagePostedEvent {
                    threadReplies {
                        events {
                            id
                            createdAt
                            actorId
                            actor { id login displayName avatarUrl presenceStatus }
                            event {
                                ... on MessagePostedEvent {
                                    roomId
                                    body
                                    updatedAt
                                    attachments {
                                        id roomId filename contentType size
                                        width height url thumbnailUrl
                                    }
                                    reactions { emoji count hasReacted }
                                    inReplyTo
                                    threadRootEventId
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
"""

QUERY_USER = """
query User($userId: ID!) {
    user(userId: $userId) {
        id
        login
        displayName
        createdAt
        avatarUrl
        presenceStatus
    }
}
"""

QUERY_USER_BY_LOGIN = """
query UserByLogin($login: String!) {
    userByLogin(login: $login) {
        id
        login
        displayName
        createdAt
        avatarUrl
        presenceStatus
    }
}
"""

QUERY_SERVER_MEMBERS = """
query ServerMembers {
    server {
        members {
            users { id login displayName avatarUrl presenceStatus }
            totalCount
            hasMore
        }
    }
}
"""

QUERY_NOTIFICATIONS = """
query Notifications {
    viewer {
        notifications {
            items {
                ... on MentionNotificationItem {
                    id
                    createdAt
                    summary
                    actor { id login displayName avatarUrl }
                    room { id name }
                    eventId
                    threadRootEventId
                }
                ... on ReplyNotificationItem {
                    id
                    createdAt
                    summary
                    actor { id login displayName avatarUrl }
                    room { id name }
                    eventId
                    inReplyToId
                    threadRootEventId
                }
                ... on RoomMessageNotificationItem {
                    id
                    createdAt
                    summary
                    actor { id login displayName avatarUrl }
                    room { id name }
                    eventId
                }
                ... on DMMessageNotificationItem {
                    id
                    createdAt
                    summary
                    actor { id login displayName avatarUrl }
                    room { id name }
                }
            }
            totalCount
            hasMore
        }
        hasNotifications
    }
}
"""

QUERY_FOLLOWED_THREADS = """
query FollowedThreads {
    viewer {
        followedThreads {
            threads {
                roomId
                threadRootEventId
                replyCount
                lastReplyAt
                hasUnread
            }
            totalCount
            hasMore
        }
        hasUnreadFollowedThreads
    }
}
"""

QUERY_LINK_PREVIEW = """
query LinkPreview($url: String!) {
    linkPreview(url: $url) {
        url title description imageUrl imageAssetId siteName embedType embedId
    }
}
"""

QUERY_ACTIVE_CALL_ROOM_IDS = """
query ActiveCallRoomIds {
    activeCallRoomIds
}
"""

# --- Mutations ---

MUTATION_POST_MESSAGE = """
mutation PostMessage($input: PostMessageInput!) {
    postMessage(input: $input) {
        id
        createdAt
    }
}
"""

MUTATION_UPDATE_MESSAGE = """
mutation UpdateMessage($input: UpdateMessageInput!) {
    updateMessage(input: $input) {
        id
    }
}
"""

MUTATION_DELETE_MESSAGE = """
mutation DeleteMessage($input: DeleteMessageInput!) {
    deleteMessage(input: $input)
}
"""

MUTATION_DELETE_ATTACHMENT = """
mutation DeleteAttachment($input: DeleteAttachmentInput!) {
    deleteAttachment(input: $input)
}
"""

MUTATION_DELETE_LINK_PREVIEW = """
mutation DeleteLinkPreview($input: DeleteLinkPreviewInput!) {
    deleteLinkPreview(input: $input)
}
"""

MUTATION_ADD_REACTION = """
mutation AddReaction($input: AddReactionInput!) {
    addReaction(input: $input)
}
"""

MUTATION_REMOVE_REACTION = """
mutation RemoveReaction($input: RemoveReactionInput!) {
    removeReaction(input: $input)
}
"""

MUTATION_CREATE_ROOM = """
mutation CreateRoom($input: CreateRoomInput!) {
    createRoom(input: $input) {
        id
        type
        name
        description
        groupId
    }
}
"""

MUTATION_UPDATE_ROOM = """
mutation UpdateRoom($input: UpdateRoomInput!) {
    updateRoom(input: $input) {
        id
        name
        description
    }
}
"""

MUTATION_ARCHIVE_ROOM = """
mutation ArchiveRoom($input: ArchiveRoomInput!) {
    archiveRoom(input: $input)
}
"""

MUTATION_UNARCHIVE_ROOM = """
mutation UnarchiveRoom($input: UnarchiveRoomInput!) {
    unarchiveRoom(input: $input)
}
"""

MUTATION_JOIN_ROOM = """
mutation JoinRoom($input: JoinRoomInput!) {
    joinRoom(input: $input) {
        id
        name
    }
}
"""

MUTATION_LEAVE_ROOM = """
mutation LeaveRoom($input: LeaveRoomInput!) {
    leaveRoom(input: $input)
}
"""

MUTATION_JOIN_GROUP = """
mutation JoinGroup($input: JoinGroupInput!) {
    joinGroup(input: $input)
}
"""

MUTATION_BAN_ROOM_MEMBER = """
mutation BanRoomMember($input: BanRoomMemberInput!) {
    banRoomMember(input: $input)
}
"""

MUTATION_UNBAN_ROOM_MEMBER = """
mutation UnbanRoomMember($input: UnbanRoomMemberInput!) {
    unbanRoomMember(input: $input)
}
"""

MUTATION_MARK_ROOM_AS_READ = """
mutation MarkRoomAsRead($input: MarkRoomAsReadInput!) {
    markRoomAsRead(input: $input) {
        lastReadAt
        previousLastReadAt
    }
}
"""

MUTATION_MARK_THREAD_AS_READ = """
mutation MarkThreadAsRead($input: MarkThreadAsReadInput!) {
    markThreadAsRead(input: $input) {
        previousReadAt
    }
}
"""

MUTATION_FOLLOW_THREAD = """
mutation FollowThread($input: FollowThreadInput!) {
    followThread(input: $input)
}
"""

MUTATION_UNFOLLOW_THREAD = """
mutation UnfollowThread($input: UnfollowThreadInput!) {
    unfollowThread(input: $input)
}
"""

MUTATION_SEND_TYPING = """
mutation SendTypingIndicator($input: SendTypingIndicatorInput!) {
    sendTypingIndicator(input: $input)
}
"""

MUTATION_START_DM = """
mutation StartDM($input: StartDMInput!) {
    startDM(input: $input) {
        id
        name
    }
}
"""

MUTATION_UPDATE_PROFILE = """
mutation UpdateProfile($input: UpdateProfileInput!) {
    updateProfile(input: $input) {
        id
        login
        displayName
        avatarUrl
    }
}
"""

MUTATION_UPLOAD_AVATAR = """
mutation UploadAvatar($input: UploadAvatarInput!) {
    uploadAvatar(input: $input) {
        id
        avatarUrl
    }
}
"""

MUTATION_DELETE_AVATAR = """
mutation DeleteAvatar($input: DeleteAvatarInput!) {
    deleteAvatar(input: $input) {
        id
        avatarUrl
    }
}
"""

MUTATION_UPDATE_PRESENCE = """
mutation UpdateMyPresence($input: UpdateMyPresenceInput!) {
    updateMyPresence(input: $input)
}
"""

MUTATION_UPDATE_SETTINGS = """
mutation UpdateSettings($input: UpdateSettingsInput!) {
    updateSettings(input: $input) {
        timezone
        timeFormat
    }
}
"""

MUTATION_SET_SERVER_NOTIFICATION_LEVEL = """
mutation SetServerNotificationLevel($input: SetServerNotificationLevelInput!) {
    setServerNotificationLevel(input: $input)
}
"""

MUTATION_SET_ROOM_NOTIFICATION_LEVEL = """
mutation SetRoomNotificationLevel($input: SetRoomNotificationLevelInput!) {
    setRoomNotificationLevel(input: $input)
}
"""

MUTATION_DISMISS_NOTIFICATION = """
mutation DismissNotification($input: DismissNotificationInput!) {
    dismissNotification(input: $input)
}
"""

MUTATION_DISMISS_ALL_NOTIFICATIONS = """
mutation DismissAllNotifications {
    dismissAllNotifications
}
"""

MUTATION_SUBSCRIBE_TO_PUSH = """
mutation SubscribeToPush($input: PushSubscriptionInput!) {
    subscribeToPush(input: $input)
}
"""

MUTATION_UNSUBSCRIBE_FROM_PUSH = """
mutation UnsubscribeFromPush($input: UnsubscribeFromPushInput!) {
    unsubscribeFromPush(input: $input)
}
"""

MUTATION_REQUEST_ACCOUNT_DELETION = """
mutation RequestAccountDeletion {
    requestAccountDeletion
}
"""

MUTATION_DELETE_MY_ACCOUNT = """
mutation DeleteMyAccount($input: DeleteMyAccountInput!) {
    deleteMyAccount(input: $input)
}
"""

MUTATION_CREATE_ROOM_GROUP = """
mutation CreateRoomGroup($input: CreateRoomGroupInput!) {
    createRoomGroup(input: $input) {
        id
        name
        description
    }
}
"""

MUTATION_UPDATE_ROOM_GROUP = """
mutation UpdateRoomGroup($input: UpdateRoomGroupInput!) {
    updateRoomGroup(input: $input) {
        id
        name
        description
    }
}
"""

MUTATION_DELETE_ROOM_GROUP = """
mutation DeleteRoomGroup($input: DeleteRoomGroupInput!) {
    deleteRoomGroup(input: $input)
}
"""

MUTATION_REORDER_ROOM_GROUPS = """
mutation ReorderRoomGroups($input: ReorderRoomGroupsInput!) {
    reorderRoomGroups(input: $input)
}
"""

MUTATION_MOVE_ROOM_TO_GROUP = """
mutation MoveRoomToGroup($input: MoveRoomToGroupInput!) {
    moveRoomToGroup(input: $input)
}
"""

MUTATION_REORDER_ROOMS_IN_GROUP = """
mutation ReorderRoomsInGroup($input: ReorderRoomsInGroupInput!) {
    reorderRoomsInGroup(input: $input)
}
"""

MUTATION_UPLOAD_SERVER_LOGO = """
mutation UploadServerLogo($input: UploadServerLogoInput!) {
    uploadServerLogo(input: $input) {
        profile { logoUrl }
    }
}
"""

MUTATION_DELETE_SERVER_LOGO = """
mutation DeleteServerLogo {
    deleteServerLogo {
        profile { logoUrl }
    }
}
"""

MUTATION_UPLOAD_SERVER_BANNER = """
mutation UploadServerBanner($input: UploadServerBannerInput!) {
    uploadServerBanner(input: $input) {
        profile { bannerUrl }
    }
}
"""

MUTATION_DELETE_SERVER_BANNER = """
mutation DeleteServerBanner {
    deleteServerBanner {
        profile { bannerUrl }
    }
}
"""

MUTATION_UPDATE_SERVER_CONFIG = """
mutation UpdateServerConfig($input: UpdateServerConfigInput!) {
    updateServerConfig(input: $input) {
        profile { name welcomeMessage motd description }
    }
}
"""

# --- Subscriptions ---

SUBSCRIPTION_EVENTS = """
subscription MyEvents {
    myEvents {
        id
        createdAt
        actorId
        actor { id login displayName avatarUrl presenceStatus }
        event {
            ... on MessagePostedEvent {
                roomId
                body
                inReplyTo
                threadRootEventId
                updatedAt
                attachments { id filename contentType size width height url thumbnailUrl }
                linkPreview { url title description imageUrl siteName }
            }
            ... on MessageEditedEvent {
                roomId
                messageEventId
                body
                updatedAt
                attachments { id filename contentType size width height url thumbnailUrl }
                linkPreview { url title description imageUrl siteName }
            }
            ... on MessageRetractedEvent { roomId messageEventId reason }
            ... on ReactionAddedEvent { roomId messageEventId emoji }
            ... on ReactionRemovedEvent { roomId messageEventId emoji }
            ... on UserTypingEvent { roomId threadRootEventId }
            ... on RoomCreatedEvent { roomId name description }
            ... on RoomUpdatedEvent { roomId name description }
            ... on RoomDeletedEvent { roomId }
            ... on RoomArchivedEvent { roomId }
            ... on RoomUnarchivedEvent { roomId }
            ... on UserJoinedRoomEvent { roomId }
            ... on UserLeftRoomEvent { roomId }
            ... on RoomMemberBannedEvent { roomId userId }
            ... on RoomMemberUnbannedEvent { roomId userId }
            ... on ServerMemberDeletedEvent { userId }
            ... on ThreadCreatedEvent { roomId threadRootEventId }
            ... on AssetProcessingStartedEvent { roomId assetId messageEventId }
            ... on AssetProcessingSucceededEvent { roomId assetId messageEventId }
            ... on AssetProcessingFailedEvent { roomId assetId messageEventId reasonCode }
            ... on AssetDeletedEvent { roomId assetId }
            ... on CallParticipantJoinedEvent { roomId }
            ... on CallParticipantLeftEvent { roomId }
            ... on PresenceChangedEvent { status }
            ... on UserCreatedEvent { userId login displayName }
            ... on UserDeletedEvent { userId }
            ... on UserProfileUpdatedEvent { userId displayName avatarUrl login }
            ... on ServerUserPreferencesUpdatedEvent { timezone timeFormat }
            ... on NotificationLevelChangedEvent { roomId level effectiveLevel }
            ... on ServerUpdatedEvent { name description logoUrl bannerUrl }
            ... on MentionNotificationEvent { roomId }
            ... on MentionStatusClearedEvent { roomId }
            ... on NewDirectMessageNotificationEvent { roomId conversationName }
            ... on NotificationCreatedEvent { notificationId roomId eventId inReplyToId }
            ... on NotificationDismissedEvent { notificationId }
            ... on ThreadFollowChangedEvent { roomId threadRootEventId isFollowing }
            ... on RoomMarkedAsReadEvent { roomId }
            ... on RoomGroupsUpdatedEvent { changed }
            ... on SessionTerminatedEvent { reason }
            ... on HeartbeatEvent { alive }
        }
    }
}
"""

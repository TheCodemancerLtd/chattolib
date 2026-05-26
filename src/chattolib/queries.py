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
        livekitUrl
        directRegistrationEnabled
        maxUploadSize
        maxVideoUploadSize
        messageEditWindowSeconds
        memberCount
        roomCount
        rooms { id type name description archived groupId hasUnread hasMention }
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
        hasMention
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
                actor { id login displayName avatarUrl }
                event {
                    ... on MessagePostedEvent {
                        roomId
                        body
                        attachments { id filename contentType size url }
                        reactions { emoji count hasReacted users { id login displayName } }
                        inReplyTo
                        inThread
                        replyCount
                        lastReplyAt
                        linkPreview { url title description siteName }
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
            threadReplies {
                id
                createdAt
                actorId
                actor { id login displayName avatarUrl }
                event {
                    ... on MessagePostedEvent {
                        roomId
                        body
                        attachments { id filename contentType size url }
                        reactions { emoji count hasReacted }
                        inReplyTo
                        inThread
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

QUERY_USERS = """
query Users {
    users {
        id
        login
        displayName
        avatarUrl
        presenceStatus
    }
}
"""

QUERY_NOTIFICATIONS = """
query Notifications {
    viewer {
        notifications {
            ... on MentionNotificationItem {
                id
                createdAt
                summary
                room { id name }
                eventId
            }
            ... on ReplyNotificationItem {
                id
                createdAt
                summary
                room { id name }
                eventId
            }
            ... on RoomMessageNotificationItem {
                id
                createdAt
                summary
                room { id name }
                eventId
            }
            ... on DMMessageNotificationItem {
                id
                createdAt
                summary
                room { id name }
            }
        }
    }
}
"""

QUERY_FOLLOWED_THREADS = """
query FollowedThreads {
    viewer {
        followedThreads {
            roomId
            threadRootEventId
            replyCount
            lastReplyAt
            hasUnread
        }
    }
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
    }
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

MUTATION_MARK_ROOM_AS_READ = """
mutation MarkRoomAsRead($input: MarkRoomAsReadInput!) {
    markRoomAsRead(input: $input) {
        lastReadAt
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

MUTATION_UPDATE_PRESENCE = """
mutation UpdateMyPresence($input: UpdateMyPresenceInput!) {
    updateMyPresence(input: $input)
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

# --- Subscriptions ---

SUBSCRIPTION_EVENTS = """
subscription MyEvents {
    myEvents {
        id
        createdAt
        actorId
        actor { id login displayName avatarUrl }
        event {
            ... on MessagePostedEvent { roomId body inThread }
            ... on MessageUpdatedEvent { roomId messageEventId }
            ... on MessageDeletedEvent { roomId messageEventId }
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
            ... on ServerMemberDeletedEvent { userId }
            ... on CallParticipantJoinedEvent { roomId }
            ... on CallParticipantLeftEvent { roomId }
            ... on VideoProcessingCompletedEvent { roomId attachmentId messageEventId }
            ... on PresenceChangedEvent { status }
            ... on ServerConfigUpdatedEvent { serverName motd }
            ... on UserCreatedEvent { userId login displayName }
            ... on UserDeletedEvent { userId }
            ... on UserProfileUpdatedEvent { userId displayName avatarUrl login }
            ... on ServerUserPreferencesUpdatedEvent { timezone timeFormat }
            ... on NotificationLevelChangedEvent { roomId level effectiveLevel }
            ... on ServerUpdatedEvent { name description }
            ... on MentionNotificationEvent { roomId }
            ... on NewDirectMessageNotificationEvent { roomId conversationName }
            ... on NotificationCreatedEvent { notificationId roomId eventId inReplyToId }
            ... on NotificationDismissedEvent { notificationId }
            ... on ThreadFollowChangedEvent { roomId threadRootEventId isFollowing }
            ... on RoomMarkedAsReadEvent { roomId }
            ... on RoomLayoutUpdatedEvent { changed }
            ... on SessionTerminatedEvent { reason }
            ... on HeartbeatEvent { alive }
        }
    }
}
"""

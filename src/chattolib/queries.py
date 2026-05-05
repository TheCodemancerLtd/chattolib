"""GraphQL query, mutation, and subscription strings."""

# --- Queries ---

QUERY_ME = """
query Me {
    me {
        id
        login
        displayName
        createdAt
        avatarUrl
        presenceStatus
    }
}
"""

QUERY_SPACES = """
query Spaces {
    spaces {
        id
        name
        description
        memberCount
        roomCount
        viewerIsMember
    }
}
"""

QUERY_SPACE = """
query Space($id: ID!) {
    space(id: $id) {
        id
        name
        description
        logoUrl
        bannerUrl
        memberCount
        roomCount
        viewerIsMember
    }
}
"""

QUERY_ROOM = """
query Room($spaceId: ID!, $roomId: ID!) {
    room(spaceId: $spaceId, roomId: $roomId) {
        id
        spaceId
        name
        description
        archived
        autoJoin
        hasUnread
        hasMention
    }
}
"""

QUERY_ROOM_EVENTS = """
query RoomEvents($spaceId: ID!, $roomId: ID!, $limit: Int, $before: Time, $after: Time) {
    roomEvents(spaceId: $spaceId, roomId: $roomId, limit: $limit, before: $before, after: $after) {
        events {
            id
            createdAt
            actorId
            actor { id login displayName avatarUrl }
            event {
                ... on MessagePostedEvent {
                    spaceId
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
    }
}
"""

QUERY_THREAD_EVENTS = """
query ThreadEvents($spaceId: ID!, $roomId: ID!, $threadRootEventId: ID!) {
    threadEvents(spaceId: $spaceId, roomId: $roomId, threadRootEventId: $threadRootEventId) {
        id
        createdAt
        actorId
        actor { id login displayName avatarUrl }
        event {
            ... on MessagePostedEvent {
                spaceId
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
"""

QUERY_USER = """
query User($id: ID!) {
    user(id: $id) {
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
    notifications {
        ... on MentionNotificationItem {
            id
            createdAt
            summary
            space { id name }
            room { id name }
            eventId
        }
        ... on ReplyNotificationItem {
            id
            createdAt
            summary
            space { id name }
            room { id name }
            eventId
        }
        ... on RoomMessageNotificationItem {
            id
            createdAt
            summary
            space { id name }
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
"""

QUERY_FOLLOWED_THREADS = """
query FollowedThreads($spaceId: ID!) {
    myFollowedThreads(spaceId: $spaceId) {
        spaceId
        roomId
        threadRootEventId
        replyCount
        lastReplyAt
        hasUnread
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

MUTATION_EDIT_MESSAGE = """
mutation EditMessage($input: EditMessageInput!) {
    editMessage(input: $input) {
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

MUTATION_JOIN_SPACE = """
mutation JoinSpace($input: JoinSpaceInput!) {
    joinSpace(input: $input) {
        id
        name
    }
}
"""

MUTATION_LEAVE_SPACE = """
mutation LeaveSpace($input: LeaveSpaceInput!) {
    leaveSpace(input: $input)
}
"""

MUTATION_CREATE_ROOM = """
mutation CreateRoom($input: CreateRoomInput!) {
    createRoom(input: $input) {
        id
        spaceId
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

MUTATION_UPDATE_MY_PROFILE = """
mutation UpdateMyProfile($input: UpdateMyProfileInput!) {
    updateMyProfile(input: $input) {
        id
        login
        displayName
    }
}
"""

MUTATION_UPLOAD_MY_AVATAR = """
mutation UploadMyAvatar($input: UploadMyAvatarInput!) {
    uploadMyAvatar(input: $input) {
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

SUBSCRIPTION_SPACE_EVENTS = """
subscription SpaceEvents($spaceId: ID!) {
    mySpaceEvents(spaceId: $spaceId) {
        id
        createdAt
        actorId
        actor { id login displayName avatarUrl }
        event {
            ... on MessagePostedEvent { spaceId roomId body inThread }
            ... on MessageUpdatedEvent { spaceId roomId messageEventId }
            ... on MessageDeletedEvent { spaceId roomId messageEventId }
            ... on ReactionAddedEvent { spaceId roomId messageEventId emoji }
            ... on ReactionRemovedEvent { spaceId roomId messageEventId emoji }
            ... on UserTypingEvent { spaceId roomId threadRootEventId }
            ... on RoomCreatedEvent { roomId name description }
            ... on RoomUpdatedEvent { roomId name description }
            ... on RoomDeletedEvent { roomId }
            ... on RoomArchivedEvent { roomId }
            ... on RoomUnarchivedEvent { roomId }
            ... on UserJoinedRoomEvent { spaceId roomId }
            ... on UserLeftRoomEvent { spaceId roomId }
            ... on SpaceMemberDeletedEvent { spaceId userId }
            ... on CallParticipantJoinedEvent { spaceId roomId }
            ... on CallParticipantLeftEvent { spaceId roomId }
            ... on VideoProcessingCompletedEvent { spaceId roomId attachmentId messageEventId }
            ... on PresenceChangedEvent { status }
        }
    }
}
"""

SUBSCRIPTION_INSTANCE_EVENTS = """
subscription InstanceEvents {
    myInstanceEvents {
        id
        createdAt
        actorId
        actor { id login displayName avatarUrl }
        event {
            ... on InstanceConfigUpdatedEvent { instanceName motd welcomeMessage blockedUsernames }
            ... on UserCreatedEvent { userId login displayName }
            ... on UserDeletedEvent { userId }
            ... on UserProfileUpdatedEvent { userId displayName avatarUrl login }
            ... on InstanceUserPreferencesUpdatedEvent { timezone timeFormat }
            ... on NotificationLevelChangedEvent { spaceId roomId level effectiveLevel }
            ... on UserJoinedSpaceEvent { spaceId }
            ... on UserLeftSpaceEvent { spaceId }
            ... on SpaceCreatedEvent { spaceId name description }
            ... on SpaceUpdatedEvent { spaceId name description }
            ... on SpaceDeletedEvent { spaceId }
            ... on MentionNotificationEvent { spaceId roomId }
            ... on NewDirectMessageNotificationEvent { roomId conversationName }
            ... on NotificationCreatedEvent { notificationId spaceId roomId eventId inReplyToId }
            ... on NotificationDismissedEvent { notificationId }
            ... on ThreadFollowChangedEvent { spaceId roomId threadRootEventId isFollowing }
            ... on NewMessageInSpaceEvent { spaceId roomId }
            ... on RoomMarkedAsReadEvent { spaceId roomId }
            ... on RoomLayoutUpdatedEvent { spaceId }
            ... on SessionTerminatedEvent { reason }
        }
    }
}
"""

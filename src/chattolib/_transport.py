# mypy: disable-error-code="no-any-return"
"""Shared plumbing for the ConnectRPC-based transport.

Chatto's public API is a ConnectRPC service surface. ``chattolib.client``
speaks to it through generated service stubs (see ``chattolib._pb``) driven
by the official ``connectrpc`` Python package.

This module exposes:

* :func:`build_service_clients` — one call, one ``base_url`` argument,
  returns a ``ServiceClients`` object with a typed field per Chatto service.
* :func:`translate_connect_error` — translates a
  ``connectrpc.errors.ConnectError`` into the library's public exception
  hierarchy (:class:`chattolib.exceptions.ChattoAuthError` /
  :class:`chattolib.exceptions.ChattoConnectError`).
* :func:`pb_to_dict` — turns a protobuf response into the camelCase JSON
  shape that the existing ``types.py`` dataclass parsers already accept.

Keeping the parsers dict-driven means the migration from Connect-JSON to
Connect-binary transport doesn't ripple through the entire public API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from connectrpc.code import Code
from connectrpc.compat import google_protobuf_binary_codec
from connectrpc.errors import ConnectError
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from chattolib._pb.chatto.admin.v1.diagnostics_connect import (
    AdminDiagnosticsServiceClient,
)
from chattolib._pb.chatto.admin.v1.event_log_connect import AdminEventLogServiceClient
from chattolib._pb.chatto.admin.v1.members_connect import AdminUserServiceClient
from chattolib._pb.chatto.admin.v1.permissions_connect import (
    AdminPermissionServiceClient,
)
from chattolib._pb.chatto.admin.v1.roles_connect import AdminRoleServiceClient
from chattolib._pb.chatto.admin.v1.room_layout_connect import (
    AdminRoomLayoutServiceClient,
)
from chattolib._pb.chatto.admin.v1.server_connect import AdminServerServiceClient
from chattolib._pb.chatto.api.v1.account_connect import MyAccountServiceClient
from chattolib._pb.chatto.api.v1.asset_uploads_connect import AssetUploadServiceClient
from chattolib._pb.chatto.api.v1.attachments_connect import AssetServiceClient
from chattolib._pb.chatto.api.v1.member_directory_connect import UserServiceClient
from chattolib._pb.chatto.api.v1.messages_connect import MessageServiceClient
from chattolib._pb.chatto.api.v1.notification_preferences_connect import (
    NotificationPreferencesServiceClient,
)
from chattolib._pb.chatto.api.v1.notifications_connect import (
    NotificationServiceClient,
)
from chattolib._pb.chatto.api.v1.push_notifications_connect import (
    PushNotificationServiceClient,
)
from chattolib._pb.chatto.api.v1.roles_connect import RoleServiceClient
from chattolib._pb.chatto.api.v1.room_directory_connect import (
    RoomDirectoryServiceClient,
)
from chattolib._pb.chatto.api.v1.rooms_connect import RoomServiceClient
from chattolib._pb.chatto.api.v1.server_state_connect import ServerServiceClient
from chattolib._pb.chatto.api.v1.threads_connect import ThreadServiceClient
from chattolib._pb.chatto.api.v1.viewer_connect import ViewerServiceClient
from chattolib._pb.chatto.api.v1.voice_calls_connect import VoiceCallServiceClient
from chattolib._pb.chatto.auth.v1.external_identity_auth_connect import (
    ExternalIdentityAuthServiceClient,
)
from chattolib._pb.chatto.discovery.v1.server_connect import (
    ServerDiscoveryServiceClient,
)
from chattolib.exceptions import ChattoAuthError, ChattoConnectError

CONNECT_PREFIX = "/api/connect"


@dataclass
class ServiceClients:
    """Typed bundle of ConnectRPC service clients used by ``ChattoClient``."""

    server_discovery: ServerDiscoveryServiceClient
    server: ServerServiceClient
    viewer: ViewerServiceClient
    account: MyAccountServiceClient
    users: UserServiceClient
    roles: RoleServiceClient
    room_directory: RoomDirectoryServiceClient
    rooms: RoomServiceClient
    messages: MessageServiceClient
    threads: ThreadServiceClient
    notifications: NotificationServiceClient
    notification_prefs: NotificationPreferencesServiceClient
    push: PushNotificationServiceClient
    assets: AssetServiceClient
    asset_uploads: AssetUploadServiceClient
    voice_calls: VoiceCallServiceClient
    external_auth: ExternalIdentityAuthServiceClient
    admin_server: AdminServerServiceClient
    admin_room_layout: AdminRoomLayoutServiceClient
    admin_users: AdminUserServiceClient
    admin_roles: AdminRoleServiceClient
    admin_event_log: AdminEventLogServiceClient
    admin_diagnostics: AdminDiagnosticsServiceClient
    admin_permissions: AdminPermissionServiceClient

    async def close(self) -> None:
        for name in self.__dataclass_fields__:
            client = getattr(self, name)
            await client.close()


def build_service_clients(base_url: str) -> ServiceClients:
    """Instantiate one service client per Chatto Connect service.

    ``base_url`` is the server root (e.g. ``https://chat.chatto.run``); the
    ConnectRPC prefix is appended by this function.
    """
    address = f"{base_url.rstrip('/')}{CONNECT_PREFIX}"
    codec = google_protobuf_binary_codec()

    def make(cls: Any) -> Any:
        return cls(address, codec=codec)

    return ServiceClients(
        server_discovery=make(ServerDiscoveryServiceClient),
        server=make(ServerServiceClient),
        viewer=make(ViewerServiceClient),
        account=make(MyAccountServiceClient),
        users=make(UserServiceClient),
        roles=make(RoleServiceClient),
        room_directory=make(RoomDirectoryServiceClient),
        rooms=make(RoomServiceClient),
        messages=make(MessageServiceClient),
        threads=make(ThreadServiceClient),
        notifications=make(NotificationServiceClient),
        notification_prefs=make(NotificationPreferencesServiceClient),
        push=make(PushNotificationServiceClient),
        assets=make(AssetServiceClient),
        asset_uploads=make(AssetUploadServiceClient),
        voice_calls=make(VoiceCallServiceClient),
        external_auth=make(ExternalIdentityAuthServiceClient),
        admin_server=make(AdminServerServiceClient),
        admin_room_layout=make(AdminRoomLayoutServiceClient),
        admin_users=make(AdminUserServiceClient),
        admin_roles=make(AdminRoleServiceClient),
        admin_event_log=make(AdminEventLogServiceClient),
        admin_diagnostics=make(AdminDiagnosticsServiceClient),
        admin_permissions=make(AdminPermissionServiceClient),
    )


def translate_connect_error(exc: ConnectError) -> Exception:
    """Convert a ``connectrpc`` error into chattolib's exception hierarchy."""
    if exc.code == Code.UNAUTHENTICATED:
        return ChattoAuthError(str(exc))
    return ChattoConnectError(
        code=exc.code.name.lower(),
        message=str(exc),
    )


def pb_to_dict(message: Message | None) -> dict[str, Any]:
    """Convert a protobuf message to the camelCase dict shape the parsers accept.

    ``preserving_proto_field_name=False`` gives us JSON-mapping camelCase
    keys (e.g. ``created_at`` → ``createdAt``), matching what the
    ``types.py`` dataclass parsers already consume.
    """
    if message is None:
        return {}
    return MessageToDict(
        message,
        preserving_proto_field_name=False,
        use_integers_for_enums=False,
    )

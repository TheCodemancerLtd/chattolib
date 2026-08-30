"""The plugin turns a CodeGeneratorRequest into async+sync client stubs."""

import importlib.util
import os

from chattolib._protoc_plugin import generate

_CODEGEN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src",
    "chattolib",
    "_codegen",
)


def _load(name):
    path = os.path.join(_CODEGEN_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_test_codegen_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


g = _load("protoc_gen_request_pb2")


def _request_with_room_service() -> g.CodeGeneratorRequest:
    req = g.CodeGeneratorRequest()
    req.file_to_generate.append("chatto/api/v1/rooms.proto")
    fd = req.proto_file.add()
    fd.name = "chatto/api/v1/rooms.proto"
    fd.package = "chatto.api.v1"
    svc = fd.service.add()
    svc.name = "RoomService"
    for name in ("JoinRoom", "CreateRoom"):
        m = svc.method.add()
        m.name = name
        m.input_type = f".chatto.api.v1.{name}Request"
        m.output_type = f".chatto.api.v1.{name}Response"
    return req


def test_emits_one_file_per_service_with_both_clients():
    resp = generate(_request_with_room_service())
    assert len(resp.file) == 1
    out = resp.file[0]
    assert out.name.endswith("rooms_connect.py")
    content = out.content
    # Both client classes, correct base classes, one method per RPC.
    assert "class RoomServiceClient(ConnectClient):" in content
    assert "class RoomServiceClientSync(ConnectClientSync):" in content
    assert "async def join_room(" in content
    assert "async def create_room(" in content
    assert "def join_room(" in content  # sync variant
    # Imports only from chattolib._connect and the sibling pb2.
    assert "from chattolib._connect import ConnectClient, ConnectClientSync, MethodInfo" in content
    assert "import chatto.api.v1.rooms_pb2 as _pb2" in content
    # No connectrpc anywhere.
    assert "connectrpc" not in content
    # use_get is dropped.
    assert "use_get" not in content


def test_skips_files_without_services():
    req = g.CodeGeneratorRequest()
    req.file_to_generate.append("chatto/realtime/v1/realtime.proto")
    fd = req.proto_file.add()
    fd.name = "chatto/realtime/v1/realtime.proto"
    fd.package = "chatto.realtime.v1"
    fd.message_type.add().name = "RealtimeClientFrame"  # messages, no service
    resp = generate(req)
    assert len(resp.file) == 0


def _request_with_cross_file_rpc() -> g.CodeGeneratorRequest:
    """A service in account.proto whose UpdatePresence RPC uses a message that
    is defined in presence.proto — the cross-file case the plugin must handle."""
    req = g.CodeGeneratorRequest()
    req.file_to_generate.append("chatto/api/v1/account.proto")

    # account.proto: declares the service + its own UpdateProfile messages.
    acc = req.proto_file.add()
    acc.name = "chatto/api/v1/account.proto"
    acc.package = "chatto.api.v1"
    acc.message_type.add().name = "UpdateProfileRequest"
    acc.message_type.add().name = "UpdateProfileResponse"
    svc = acc.service.add()
    svc.name = "MyAccountService"
    m = svc.method.add()
    m.name = "UpdatePresence"
    m.input_type = ".chatto.api.v1.UpdatePresenceRequest"
    m.output_type = ".chatto.api.v1.UpdatePresenceResponse"
    m2 = svc.method.add()
    m2.name = "UpdateProfile"
    m2.input_type = ".chatto.api.v1.UpdateProfileRequest"
    m2.output_type = ".chatto.api.v1.UpdateProfileResponse"

    # presence.proto: defines the UpdatePresence request/response.
    pres = req.proto_file.add()
    pres.name = "chatto/api/v1/presence.proto"
    pres.package = "chatto.api.v1"
    pres.message_type.add().name = "UpdatePresenceRequest"
    pres.message_type.add().name = "UpdatePresenceResponse"
    return req


def test_cross_file_rpc_uses_the_defining_module():
    resp = generate(_request_with_cross_file_rpc())
    assert len(resp.file) == 1
    content = resp.file[0].content
    # The account_pb2 import is still there for the same-file messages.
    assert "import chatto.api.v1.account_pb2 as _pb2" in content
    # The presence messages must be imported from their own module and the
    # UpdatePresence method must reference *that* module, not _pb2.
    assert "import chatto.api.v1.presence_pb2 as _pb2_presence" in content
    assert "_pb2_presence.UpdatePresenceRequest" in content
    assert "_pb2_presence.UpdatePresenceResponse" in content
    # The same-file method keeps using the plain _pb2 alias.
    assert "_pb2.UpdateProfileRequest" in content
    # Crucially: UpdatePresenceRequest must NOT be referenced via _pb2 (the
    # original bug was `_pb2.UpdatePresenceRequest` -> AttributeError).
    assert "_pb2.UpdatePresenceRequest" not in content
    assert "_pb2.UpdatePresenceResponse" not in content

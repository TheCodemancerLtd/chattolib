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
    for name in ("JoinRoomRequest", "JoinRoomResponse", "CreateRoomRequest", "CreateRoomResponse"):
        fd.message_type.add().name = name
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
    # Imports only from chattolib._connect and the sibling pb2 (unique alias).
    assert "from chattolib._connect import ConnectClient, ConnectClientSync, MethodInfo" in content
    assert "import chatto.api.v1.rooms_pb2 as chatto_api_v1_rooms_pb2" in content
    # No connectrpc anywhere.
    assert "connectrpc" not in content
    # use_get is dropped.
    assert "use_get" not in content


def _request_with_cross_file_ref() -> g.CodeGeneratorRequest:
    """A service in account.proto that references messages defined elsewhere."""
    req = g.CodeGeneratorRequest()
    req.file_to_generate.append("chatto/api/v1/account.proto")
    fd = req.proto_file.add()
    fd.name = "chatto/api/v1/account.proto"
    fd.package = "chatto.api.v1"
    svc = fd.service.add()
    svc.name = "MyAccountService"
    m = svc.method.add()
    m.name = "ListExternalIdentities"
    m.input_type = ".chatto.api.v1.ListExternalIdentitiesRequest"
    m.output_type = ".chatto.api.v1.ListExternalIdentitiesResponse"
    # The referenced messages live in a *different* proto (no service of its own).
    fd2 = req.proto_file.add()
    fd2.name = "chatto/api/v1/external_identities.proto"
    fd2.package = "chatto.api.v1"
    for name in ("ListExternalIdentitiesRequest", "ListExternalIdentitiesResponse"):
        fd2.message_type.add().name = name
    return req


def test_cross_file_message_reference_uses_defining_module():
    """Regression: a service must import the module that *defines* each message.

    (The old plugin referenced every message through the service's own module,
    which broke cross-file references like ``account.proto`` ->
    ``external_identities.proto``.)
    """
    resp = generate(_request_with_cross_file_ref())
    assert len(resp.file) == 1
    content = resp.file[0].content
    assert (
        "import chatto.api.v1.external_identities_pb2 as chatto_api_v1_external_identities_pb2"
        in content
    )
    assert "chatto_api_v1_external_identities_pb2.ListExternalIdentitiesRequest" in content
    # Not referenced through the service's own module.
    assert "chatto_api_v1_account_pb2.ListExternalIdentitiesRequest" not in content


def test_skips_files_without_services():
    req = g.CodeGeneratorRequest()
    req.file_to_generate.append("chatto/realtime/v1/realtime.proto")
    fd = req.proto_file.add()
    fd.name = "chatto/realtime/v1/realtime.proto"
    fd.package = "chatto.realtime.v1"
    fd.message_type.add().name = "RealtimeClientFrame"  # messages, no service
    resp = generate(req)
    assert len(resp.file) == 0

"""The vendored protoc codegen descriptors must be loadable and usable.

Loaded by file path (not via ``import chattolib._codegen``) so this test is
valid even before the generated service stubs exist — importing through the
``chattolib`` package would otherwise trigger ``chattolib/__init__.py``.
"""

import importlib.util
import os

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


def test_codegen_request_round_trips():
    g = _load("protoc_gen_request_pb2")
    req = g.CodeGeneratorRequest()
    req.language = "chattolib"
    req.file_to_generate.append("chatto/api/v1/rooms.proto")
    fd = req.proto_file.add()
    fd.name = "chatto/api/v1/rooms.proto"
    fd.package = "chatto.api.v1"
    svc = fd.service.add()
    svc.name = "RoomService"
    m = svc.method.add()
    m.name = "JoinRoom"
    m.input_type = ".chatto.api.v1.JoinRoomRequest"
    m.output_type = ".chatto.api.v1.JoinRoomResponse"

    req2 = g.CodeGeneratorRequest.FromString(req.SerializeToString())
    assert req2.file_to_generate[0] == "chatto/api/v1/rooms.proto"
    assert req2.proto_file[0].service[0].method[0].name == "JoinRoom"


def test_codegen_response_file_field():
    g = _load("protoc_gen_response_pb2")
    resp = g.CodeGeneratorResponse()
    resp.file.add().name = "out/foo_connect.py"
    resp.file.add().content = "print('hi')"
    resp2 = g.CodeGeneratorResponse.FromString(resp.SerializeToString())
    assert resp2.file[1].content == "print('hi')"

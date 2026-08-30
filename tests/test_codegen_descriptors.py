"""The vendored protoc codegen descriptors must be importable and usable."""


def test_codegen_request_round_trips():
    from chattolib._pb.google.protobuf import protoc_gen_request_pb2 as g

    req = g.CodeGeneratorRequest()
    req.language = "chattolib"
    req.file_to_generate.append("chatto/api/v1/rooms.proto")
    # A service with one unary method.
    fd = req.proto_file.add()
    fd.name = "chatto/api/v1/rooms.proto"
    fd.package = "chatto.api.v1"
    svc = fd.service.add()
    svc.name = "RoomService"
    m = svc.method.add()
    m.name = "JoinRoom"
    m.input_type = ".chatto.api.v1.JoinRoomRequest"
    m.output_type = ".chatto.api.v1.JoinRoomResponse"

    data = req.SerializeToString()
    req2 = g.CodeGeneratorRequest.FromString(data)
    assert req2.file_to_generate[0] == "chatto/api/v1/rooms.proto"
    assert req2.proto_file[0].service[0].method[0].name == "JoinRoom"


def test_codegen_response_file_field():
    from chattolib._pb.google.protobuf import protoc_gen_response_pb2 as g

    resp = g.CodeGeneratorResponse()
    resp.file.add().name = "out/foo_connect.py"
    resp.file.add().content = "print('hi')"
    data = resp.SerializeToString()
    resp2 = g.CodeGeneratorResponse.FromString(data)
    assert resp2.file[1].content == "print('hi')"

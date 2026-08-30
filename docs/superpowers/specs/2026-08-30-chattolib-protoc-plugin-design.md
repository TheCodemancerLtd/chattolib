# Design: a from-scratch `protoc` plugin to generate chattolib's Connect stubs

**Status:** proposed
**Date:** 2026-08-30
**Bean:** `chattolib-zo8b`
**Supersedes:** the `regen_connect.py` regex post-processor (to be deleted)

## 1. Purpose

Remove the last trace of the `connectrpc` package from chattolib's build.
Today the *runtime* is hand-rolled (`chattolib/_connect.py`) but codegen still
shells out to `protoc-gen-connect-python` to *produce* the `*_connect.py`
stubs, then a regex script strips them down. This design replaces both with a
single, purpose-built `protoc` plugin that emits exactly the stubs chattolib
needs — an async client **and** a thin sync wrapper — with no `connectrpc`
anywhere in the loop.

## 2. Goals / non-goals

**Goals**
- One codegen path: `protoc --chattolib_out` emits the service stubs.
- Stubs import only from `chattolib._connect` and the sibling `*_pb2` module.
- Generated **async** method names are byte-identical to today's
  (`client.join_room(...)`, `client.post_message(...)`) so `client.py` and the
  `Bot` facade are untouched.
- A **sync** client is available, implemented as a wrapper over the async one.
- `connectrpc` and `pyqwest` are absent from both the runtime *and* the build.

**Non-goals**
- No server-side / ASGI / WSGI code generation (chattolib is a client).
- No streaming RPC support (Chatto's API is unary-only today). If a streaming
  RPC ever appears, that is a separate design.
- No re-implementation of `.proto` parsing — `protoc` still parses and
  validates; the plugin only reads the resulting descriptors.

## 3. Components

### 3.1 `chattolib/_connect.py` (exists; small additions)
The hand-rolled runtime, unchanged in behavior:
- `Code` (16-value enum), `ConnectError`, `MethodInfo`, `_BinaryCodec`,
  `google_protobuf_binary_codec()`.
- `class ConnectClient` — `__init__(address, *, codec=None, timeout_ms=None)`,
  `async execute_unary(*, request, method, headers=None)`, `async close()`.

**Addition:** `class ConnectClientSync` — the sync wrapper (see §4).

### 3.2 The plugin: `chattolib/_protoc_plugin.py` (new)
A Python script that speaks the `protoc` plugin protocol:
- Reads a `CodeGeneratorRequest` (protobuf) from **stdin**.
- For each `FileDescriptorProto` that contains a `service`, emits one output
  file: `<proto path>_connect.py`.
- Writes a `CodeGeneratorResponse` (protobuf) to **stdout**.

It is installed as a `console_scripts` entry point named
**`protoc-gen-chattolib`**, so `protoc` discovers it on `PATH` and the
invocation is `--chattolib_out=<dir>`.

### 3.3 Vendored codegen descriptors (new)
`src/chattolib/_pb/google/protobuf/protoc_gen_request_pb2.py` and
`protoc_gen_response_pb2.py` — the two stable `protoc` descriptor stubs the
plugin needs to parse its stdin/stdout. Generated once from
`google/protobuf/*.proto`, committed, and not regenerated per-release.

### 3.4 `scripts/generate_pb.sh` (modified)
- Still fetches `.proto` from the pinned `CHATTO_REF` tag (unchanged).
- Still runs `protoc --python_out` for the `*_pb2.py` message files (unchanged).
- **Replaces** `--connect-python_out=...` with `--chattolib_out=...`.
- Drops the `protoc-gen-connect-python` PATH check / `[realtime]` pin for it.

### 3.5 Deleted
- `scripts/regen_connect.py` — the regex post-processor is obsolete.

## 4. The sync client (the design decision)

`ConnectClientSync` wraps the async client; it does **not** re-implement the
protocol.

```python
class ConnectClientSync:
    def __init__(self, address, *, codec=None, timeout_ms=None):
        self._async = ConnectClient(address, codec=codec, timeout_ms=timeout_ms)
        self._loop = asyncio.new_event_loop()

    def execute_unary(self, *, request, method, headers=None):
        self._guard_no_running_loop()
        return self._loop.run_until_complete(
            self._async.execute_unary(request=request, method=method, headers=headers)
        )

    def close(self):
        self._loop.run_until_complete(self._async.close())
        self._loop.close()

    def _guard_no_running_loop(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop: safe to run_until_complete
        raise ChattoError(
            "the sync client cannot be used from within a running event loop; "
            "use the async ConnectClient in async code"
        )
```

Properties:
- **Shared protocol** — codec, `MethodInfo`, `ConnectError`, and the
  error-envelope parser live only in the async client; the sync path is
  delegation. One implementation, two entry points.
- **Zero new dependencies** — `httpx` is already required by the async client.
- **Loud, not opaque** — calling it from inside `async def` raises a clear
  `ChattoError` instead of a nested-loop `RuntimeError` (decision B).
- Each sync client owns a private loop; `close()` closes both.

## 5. Generated stub shape

For a service `chatto.api.v1.RoomService` in `rooms.proto`, the plugin emits
`src/chattolib/_pb/chatto/api/v1/rooms_connect.py`:

```python
# Generated by chattolib's protoc plugin (protoc-gen-chattolib). DO NOT EDIT.
# source: chatto/api/v1/rooms.proto
import chatto.api.v1.rooms_pb2 as _pb2
from chattolib._connect import ConnectClient, ConnectClientSync, MethodInfo

class RoomServiceClient(ConnectClient):
    async def join_room(self, request: _pb2.JoinRoomRequest, *,
                        headers: dict[str, str] | None = None) -> _pb2.JoinRoomResponse:
        return await self.execute_unary(
            request=request,
            method=MethodInfo(name="JoinRoom",
                               service_name="chatto.api.v1.RoomService",
                               input=_pb2.JoinRoomRequest,
                               output=_pb2.JoinRoomResponse),
            headers=headers,
        )
    # ... one method per RPC ...

class RoomServiceClientSync(ConnectClientSync):
    def join_room(self, request: _pb2.JoinRoomRequest, *,
                  headers: dict[str, str] | None = None) -> _pb2.JoinRoomResponse:
        return self.execute_unary(
            request=request,
            method=MethodInfo(name="JoinRoom",
                               service_name="chatto.api.v1.RoomService",
                               input=_pb2.JoinRoomRequest,
                               output=_pb2.JoinRoomResponse),
            headers=headers,
        )
```

Notes:
- `idempotency_level` is omitted from the emitted `MethodInfo` (the runtime
  defaults it; chattolib never reads it).
- `use_get` is **not** generated (POST-only; decision from Q3).
- Both the async and sync classes are emitted so a sync consumer gets the same
  method names. A service with N RPCs therefore yields 2N generated methods.
  The sync classes are **additive**: `build_service_clients` still instantiates
  only the async `*ServiceClient`, and no existing code imports `*ClientSync`,
  so `client.py`, `bot.py`, and `_transport.py` require no changes.
- The `*_pb2` import uses the proto's own package path (as today), resolved via
  the existing `sys.path` shim in `_pb/__init__.py`.

## 6. Data flow

```
.proto (pinned tag)
   │  protoc --proto_path=proto
   ├──► --python_out      →  *_pb2.py            (message classes; unchanged)
   └──► --chattolib_out   →  protoc-gen-chattolib (our plugin)
                              reads CodeGeneratorRequest (stdin)
                              emits *_connect.py   (async + sync clients)
                              via CodeGeneratorResponse (stdout)

chattolib._transport.build_service_clients(base_url)
   instantiates the 23 *ServiceClient (async) as today.
```

## 7. Error handling & testing

- **Unit:** a `CodeGeneratorRequest` fixture (a couple of representative
  services, incl. one with many methods and one with a `oneof`-free plain
  service) → run the plugin → assert the emitted source imports only from
  `chattolib._connect`/`_pb2`, defines both client classes, and has one method
  per RPC.
- **Sync-wrapper:** a test that (a) a sync call round-trips against a mocked
  transport, and (b) calling it from inside a running loop raises the clear
  `ChattoError`.
- **Integration (existing):** the full `tests/` suite stays green, and the live
  smoke test against the preview server still passes with `connectrpc`
  uninstalled.
- **Golden-file:** the 24 regenerated `*_connect.py` are committed; a CI check
  re-runs the plugin and fails on any diff (catches plugin regressions).

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Plugin emits subtly-wrong stubs on a future proto shape | Golden-file CI diff + unit fixtures covering the method shapes we use. |
| `run_until_complete` surprises (e.g. signal handlers, `uvloop`) | The guard covers the common case; documented that the sync client is for sync contexts. |
| Vendored `protoc_gen_*_pb2` drift from a `protoc` version | They are stable; pin and regenerate only if `protoc` changes the codegen schema. |
| Two clients (async+sync) double the stub size | Acceptable; it's generated code, and it's what enables the sync use-case. |

## 9. Out of scope / follow-ons

- A from-scratch replacement for the `--python_out` message generation (we keep
  protoc's built-in Python generator — it's not `connectrpc`-specific).
- Streaming RPC support.
- Publishing the plugin as a standalone package (it ships inside chattolib).

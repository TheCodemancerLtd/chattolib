---
# chattolib-mp9q
title: Implement Chatto realtime WebSocket in chattolib
status: completed
type: feature
priority: high
created_at: 2026-07-08T23:55:28Z
updated_at: 2026-07-09T00:03:19Z
---

Chatto 0.4.x's realtime channel is a binary protobuf WebSocket at /api/realtime (chatto.realtime.v1). Replace the stub in realtime.py with a real WS client: fetch/generate protobuf bindings for RealtimeClientFrame/RealtimeServerFrame and their imports, handle hello/subscribe/heartbeat/error/close, and expose a Pythonic async iterator that yields typed events.

## Summary of Changes

Implemented the realtime WebSocket client for Chatto's `chatto.realtime.v1` binary-protobuf protocol.

- Added `proto/` vendored source (from chattocorp/chatto main) with realtime.proto plus its transitive api/v1 imports and buf/validate/validate.proto.
- Added `scripts/generate_pb.sh` that re-fetches the protos and regenerates the bindings under `src/chattolib/_pb/`. Requires `protoc` on PATH.
- Vendored generated `*_pb2.py` modules under `src/chattolib/_pb/`. Package `__init__.py` inserts its own directory onto `sys.path` so the generated `from chatto.api.v1 import ...` imports resolve without polluting the top-level namespace of dependent projects.
- Rewrote `realtime.py` on top of the bindings and `websockets`:
  - `RealtimeConnection` async context manager: connects to /api/realtime, sends binary `RealtimeClientHello` (bearer token from ChattoClient, session cookie in WS headers), receives `RealtimeServerHello`, sends `RealtimeSubscribeEvents`.
  - `.events()` async iterator decodes `RealtimeServerFrame` variants (event, heartbeat, subscribed, pong, error, close). Fatal errors and close frames raise `ChattoRealtimeError` / `ChattoRealtimeCloseError`; heartbeats and pongs are swallowed.
  - `.ping(nonce)` sends a client ping for callers that want an explicit RTT check.
  - `stream_events(client)` module-level async iterator wraps the connection lifecycle for the common case.
- `RealtimeEvent` dataclass exposes `id`, `created_at`, `actor_id`, `kind` (protobuf oneof case name), `payload` (the concrete sub-message), and `raw` (the full envelope).
- Exported the new public names from `chattolib.__init__`.
- Added `websockets>=13` and `protobuf>=5.28` to the `[realtime]` extra.
- Updated `pyproject.toml`: mypy `follow_imports = skip` and ruff excludes for `chattolib._pb` so generated modules don't fight the type checker.
- Added `tests/test_realtime.py`: URL helper, event wrapping, exception fields, protobuf frame roundtrips (10 tests). `pytest` reports 44 passed, 4 skipped (integration).
- Live-verified against Chatto HQ with the RoboChatto account: hello handshake, subscribe, decoded live `presence_changed` events, clean close.

Refreshed README with a Realtime section and CLAUDE.md with the new package layout, realtime service row, and _pb regeneration notes.

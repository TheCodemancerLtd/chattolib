---
# chattolib-psxw
title: Move chattolib transport to the connectrpc Python package
status: completed
type: task
priority: high
created_at: 2026-07-09T10:03:55Z
updated_at: 2026-07-09T10:20:09Z
---

Replace hand-rolled Connect-JSON-over-httpx with the official connectrpc Python library (chatto-bot uses this too). Generate connect-python service stubs for every Chatto service from the vendored .proto files, rewrite ChattoClient so its methods delegate to those stubs, drop _transport.py, and keep the Pythonic top-level API (client.post_message(...)) intact.

## Summary of Changes

Migrated the chattolib request/response transport from hand-rolled Connect-JSON-over-httpx to the official `connectrpc` Python package plus generated ConnectRPC service stubs (same transport chatto-bot uses).

- Extended `scripts/generate_pb.sh` to fetch every Chatto proto (api/v1, admin/v1, auth/v1, discovery/v1, realtime/v1) and to invoke `protoc-gen-connect-python` alongside the standard `--python_out`. Now produces 39 `*_pb2.py` message modules and 25 `*_connect.py` service stub modules under `src/chattolib/_pb/`.
- `_transport.py` rewritten: exposes `build_service_clients(base_url)` (returns a typed `ServiceClients` bundle with one client per Chatto service, all sharing the google.protobuf binary codec) plus `translate_connect_error` (`ConnectError` → `ChattoAuthError`/`ChattoConnectError`) and `pb_to_dict` (bridges protobuf responses to the dataclass `.parse()` methods).
- `ChattoClient` fully rewritten: each method builds a protobuf request, calls the appropriate stub via a common `_rpc` helper that adds auth headers and translates errors, then normalises the response into the existing dataclass types. Added a public `.services` property so callers can reach the raw ConnectRPC clients directly.
- Removed the `client.call(service, method, request)` string-based escape hatch (replaced by `.services`).
- `pyproject.toml`: added `connectrpc>=0.11` and `protobuf>=5.28` as hard runtime deps; `httpx` stays for the `/auth/login` endpoint; `websockets` still under `[realtime]`.
- Tests rewritten to mock at the service-client method level via `unittest.mock.AsyncMock` — 48 tests, all passing, no HTTP mocking.
- `ruff` + `mypy --strict` clean.

Verified live against Chatto HQ (0.4.2) with the RoboChatto account: login → `me()` → `list_rooms()` → `get_motd()` → `list_roles()` → `has_notifications()` all succeed end-to-end. Realtime WebSocket unchanged and still working.

CLAUDE.md architecture section refreshed to describe the new transport and _pb layout.

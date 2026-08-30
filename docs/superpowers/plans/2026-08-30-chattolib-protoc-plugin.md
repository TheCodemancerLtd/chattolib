# chattolib `protoc` Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `connectrpc`-based codegen with a purpose-built Python `protoc` plugin that emits chattolib's async + sync Connect client stubs, removing `connectrpc`/`pyqwest` from the build entirely.

**Architecture:** A Python `protoc` plugin (`protoc-gen-chattolib`) reads a `CodeGeneratorRequest` on stdin and, for each proto containing a `service`, emits one `*_connect.py` defining an async `*ServiceClient(ConnectClient)` and a thin `*ServiceClientSync(ConnectClientSync)`. The sync client wraps the shared async `execute_unary` on a private loop. `generate_pb.sh` swaps `--connect-python_out` for `--chattolib_out`; the old `regen_connect.py` post-processor is deleted.

**Tech Stack:** Python 3.10+, `google.protobuf` (already a dep), `httpx` (already a dep for the async client), `protoc` (build-time only).

**Spec:** `docs/superpowers/specs/2026-08-30-chattolib-protoc-plugin-design.md`

## Global Constraints

- **No `connectrpc` or `pyqwest` anywhere** — not in `src/`, not in `pyproject.toml` deps, not in `generate_pb.sh`. The only HTTP library is `httpx`.
- **Generated async method names are byte-identical to today's** (`client.join_room(...)`, `client.post_message(...)`, …). `client.py`, `bot.py`, and `_transport.py` require **no changes** for the async path.
- **`use_get` is not generated** (POST-only). `idempotency_level` is omitted from emitted `MethodInfo` (the runtime defaults it).
- **Sync client is a wrapper**, not a re-implementation: it delegates to the async `execute_unary` on a private `asyncio` loop and raises a clear `ChattoError` if called from within a running event loop.
- **Every generated stub imports only** from `chattolib._connect` and its sibling `*_pb2` module.
- **Commits** are authored as `the-codemancer` (`git -c user.name=the-codemancer -c user.email=the-codemancer@users.noreply commit`).
- **Test command** from the worktree root: `.venv/bin/python -m pytest tests/ -q`. Linters: `.venv/bin/ruff check .` and `.venv/bin/python -m mypy src/chattolib`.

---

### Task 1: Sync client wrapper (`ConnectClientSync`)

**Files:**
- Modify: `src/chattolib/_connect.py` (add `ConnectClientSync` after `ConnectClient`)
- Test: `tests/test_connect.py` (create)

**Interfaces:**
- Consumes: `ConnectClient` (`.execute_unary`, `.close`), `ChattoError` (from `chattolib.exceptions`), `MethodInfo`.
- Produces: `class ConnectClientSync` with `__init__(address, *, codec=None, timeout_ms=None)`, `execute_unary(*, request, method, headers=None)`, `close()`. Exported in `_connect.__all__`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_connect.py`:

```python
"""Unit tests for the hand-rolled Connect client (chattolib._connect)."""

import asyncio

import pytest

from chattolib._connect import ConnectClientSync
from chattolib.exceptions import ChattoError


def test_sync_client_round_trips_through_async(monkeypatch):
    """A sync execute_unary delegates to the shared async execute_unary."""
    from chattolib._connect import MethodInfo
    from google.protobuf import struct_pb2

    captured = {}

    async def fake_execute_unary(self, *, request, method, headers=None):
        captured["request"] = request
        captured["method"] = method
        return request  # echo the request back as the "response"

    monkeypatch.setattr(
        "chattolib._connect.ConnectClient.execute_unary", fake_execute_unary
    )

    client = ConnectClientSync("https://example.test")
    msg = struct_pb2.Struct()
    out = client.execute_unary(
        request=msg,
        method=MethodInfo(name="M", service_name="s.S", input=msg, output=msg),
    )
    assert out is msg
    assert captured["request"] is msg
    client.close()


def test_sync_client_refuses_inside_running_loop():
    """Calling the sync client from within a running loop raises ChattoError."""
    client = ConnectClientSync("https://example.test")

    async def call_from_async():
        from chattolib._connect import MethodInfo
        from google.protobuf import struct_pb2

        msg = struct_pb2.Struct()
        client.execute_unary(
            request=msg,
            method=MethodInfo(name="M", service_name="s.S", input=msg, output=msg),
        )

    with pytest.raises(ChattoError):
        asyncio.run(call_from_async())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_connect.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConnectClientSync'`

- [ ] **Step 3: Implement `ConnectClientSync`**

In `src/chattolib/_connect.py`, after the `ConnectClient` class, add:

```python
class ConnectClientSync:
    """Synchronous unary Connect client.

    Wraps the async :class:`ConnectClient`: it runs the *same*
    ``execute_unary`` on a private event loop, so the protocol logic (codec,
    error parsing) is implemented once. Use it from synchronous code; from
    inside a running event loop it raises a clear :class:`ChattoError` instead
    of a nested-loop ``RuntimeError``.
    """

    def __init__(
        self,
        address: str,
        *,
        codec: _BinaryCodec | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._async = ConnectClient(address, codec=codec, timeout_ms=timeout_ms)
        self._loop = asyncio.new_event_loop()

    def execute_unary(
        self,
        *,
        request: Message,
        method: MethodInfo,
        headers: Mapping[str, str] | None = None,
    ) -> Message:
        self._guard_no_running_loop()
        return self._loop.run_until_complete(
            self._async.execute_unary(request=request, method=method, headers=headers)
        )

    def close(self) -> None:
        self._loop.run_until_complete(self._async.close())
        self._loop.close()

    @staticmethod
    def _guard_no_running_loop() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop: safe to run_until_complete
        raise ChattoError(
            "the sync client cannot be used from within a running event loop; "
            "use the async ConnectClient in async code"
        )
```

Add `from __future__ import annotations` is already present; ensure `import asyncio` and `from chattolib.exceptions import ChattoError` are at the top of the module (add the `ChattoError` import; `asyncio` is already imported for the async client). Add `"ConnectClientSync"` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_connect.py -v`
Expected: 2 passed

- [ ] **Step 5: Lint + typecheck**

Run: `.venv/bin/ruff check src/chattolib/_connect.py tests/test_connect.py && .venv/bin/python -m mypy src/chattolib/_connect.py`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/chattolib/_connect.py tests/test_connect.py
git -c user.name=the-codemancer -c user.email=the-codemancer@users.noreply commit -m "Add ConnectClientSync: sync wrapper over the async Connect client"
```

---

### Task 2: Vendored `protoc` codegen descriptor stubs

**Files:**
- Create: `src/chattolib/_pb/google/protobuf/protoc_gen_request_pb2.py`
- Create: `src/chattolib/_pb/google/protobuf/protoc_gen_response_pb2.py`
- Create: `src/chattolib/_pb/google/__init__.py`, `src/chattolib/_pb/google/protobuf/__init__.py`
- Test: `tests/test_codegen_descriptors.py` (create)

**Interfaces:**
- Produces: importable `protoc_gen_request_pb2.CodeGeneratorRequest` and `protoc_gen_response_pb2.CodeGeneratorResponse` (and their nested message types) under `chattolib._pb.google.protobuf`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_codegen_descriptors.py`:

```python
"""The vendored protoc codegen descriptors must be importable and usable."""


def test_codegen_request_round_trips():
    from chattolib._pb.google.protobuf import protoc_gen_request_pb2 as g

    req = g.CodeGeneratorRequest()
    req.language = "chattolib"
    f = req.file_to_generate.add()
    f.name = "chatto/api/v1/rooms.proto"
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
    assert req2.file_to_generate[0].name == "chatto/api/v1/rooms.proto"
    assert req2.proto_file[0].service[0].method[0].name == "JoinRoom"


def test_codegen_response_file_field():
    from chattolib._pb.google.protobuf import protoc_gen_response_pb2 as g

    resp = g.CodeGeneratorResponse()
    resp.file.add().name = "out/foo_connect.py"
    resp.file.add().content = "print('hi')"
    data = resp.SerializeToString()
    resp2 = g.CodeGeneratorResponse.FromString(data)
    assert resp2.file[1].content == "print('hi')"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_codegen_descriptors.py -v`
Expected: FAIL — `ModuleNotFoundError: ...google.protobuf`

- [ ] **Step 3: Generate the two descriptor stubs**

Run (uses the already-installed `protobuf` + `protoc`):

```bash
cd <worktree>
mkdir -p src/chattolib/_pb/google/protobuf
touch src/chattolib/_pb/google/__init__.py src/chattolib/_pb/google/protobuf/__init__.py
# Fetch the two stable codegen .proto files from protobuf's own repo.
curl -sfL https://raw.githubusercontent.com/protocolbuffers/protobuf/main/src/google/protobuf/compiler/codegen_request.proto -o /tmp/cgr.proto
curl -sfL https://raw.githubusercontent.com/protocolbuffers/protobuf/main/src/google/protobuf/compiler/codegen_response.proto -o /tmp/cgp.proto
# codegen_response.proto imports codegen_request.proto; give protoc both.
protoc --proto_path=/tmp --python_out=src/chattolib/_pb/google/protobuf /tmp/cgr.proto /tmp/cgp.proto
# The generated files import `google.protobuf.compiler.codegen_request_pb2`;
# but we vendored them under our own path, so fix the cross-import:
sed -i 's/import google\.protobuf\.compiler\.codegen_request_pb2 as/from google.protobuf import codegen_request_pb2 as/' src/chattolib/_pb/google/protobuf/protoc_gen_response_pb2.py
```

Then rename the generated files to the `protoc_gen_*` convention the plugin will import (the spec uses `protoc_gen_request_pb2` / `protoc_gen_response_pb2`):

```bash
cd src/chattolib/_pb/google/protobuf
mv codegen_request_pb2.py protoc_gen_request_pb2.py
mv codegen_response_pb2.py protoc_gen_response_pb2.py
# Fix the self-referential import inside the response stub.
sed -i 's/from google.protobuf import codegen_request_pb2 as/from . import protoc_gen_request_pb2 as/' protoc_gen_response_pb2.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_codegen_descriptors.py -v`
Expected: 2 passed. (If the cross-import path is wrong, the response test fails on import — fix the `sed` in Step 3 until both pass.)

- [ ] **Step 5: Commit**

```bash
git add src/chattolib/_pb/google tests/test_codegen_descriptors.py
git -c user.name=the-codemancer -c user.email=the-codemancer@users.noreply commit -m "Vendor protoc codegen descriptor stubs (protoc_gen_{request,response}_pb2)"
```

---

### Task 3: The `protoc-gen-chattolib` plugin

**Files:**
- Create: `src/chattolib/_protoc_plugin.py`
- Modify: `pyproject.toml` (add the `console_scripts` entry point)
- Test: `tests/test_protoc_plugin.py` (create)

**Interfaces:**
- Consumes: `protoc_gen_request_pb2.CodeGeneratorRequest`, `protoc_gen_response_pb2.CodeGeneratorResponse` (Task 2).
- Produces: a module with `def generate(request: CodeGeneratorRequest) -> CodeGeneratorResponse` and a `main()` that reads stdin / writes stdout. Installed as `protoc-gen-chattolib`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_protoc_plugin.py`:

```python
"""The plugin turns a CodeGeneratorRequest into async+sync client stubs."""

from chattolib._pb.google.protobuf import protoc_gen_request_pb2 as g
from chattolib._protoc_plugin import generate


def _request_with_room_service() -> g.CodeGeneratorRequest:
    req = g.CodeGeneratorRequest()
    req.file_to_generate.add().name = "chatto/api/v1/rooms.proto"
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
    req.file_to_generate.add().name = "chatto/realtime/v1/realtime.proto"
    fd = req.proto_file.add()
    fd.name = "chatto/realtime/v1/realtime.proto"
    fd.package = "chatto.realtime.v1"
    fd.message_type.add().name = "RealtimeClientFrame"  # messages, no service
    resp = generate(req)
    assert len(resp.file) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_protoc_plugin.py -v`
Expected: FAIL — `ModuleNotFoundError: ..._protoc_plugin`

- [ ] **Step 3: Implement the plugin**

Create `src/chattolib/_protoc_plugin.py`:

```python
"""A `protoc` plugin that generates chattolib's Connect client stubs.

Speaks the standard plugin protocol: reads a ``CodeGeneratorRequest`` from
stdin, writes a ``CodeGeneratorResponse`` to stdout. For each proto that
declares a ``service``, it emits one ``<name>_connect.py`` defining an async
``*ServiceClient(ConnectClient)`` and a sync ``*ServiceClientSync
(ConnectClientSync)`` — both delegating to the shared runtime in
``chattolib._connect``.

Installed as the console script ``protoc-gen-chattolib`` so ``protoc`` finds
it on PATH and it is invoked with ``--chattolib_out=<dir>``.
"""

from __future__ import annotations

import sys

from chattolib._pb.google.protobuf import (
    protoc_gen_request_pb2 as g,
    protoc_gen_response_pb2 as r,
)

_HEADER = (
    "# Generated by chattolib's protoc plugin (protoc-gen-chattolib). "
    "DO NOT EDIT!\n"
)


def _method_name(m) -> str:
    """snake_case the RPC name, matching Python method naming."""
    out = []
    for i, ch in enumerate(m.name):
        if ch.isupper() and i:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _service_stub(fd) -> str:
    """Render one service's async + sync client classes as source text."""
    pkg = fd.package
    svc = fd.service[0]
    base = f"{pkg}.{svc.name}" if pkg else svc.name
    lines = [
        _HEADER,
        f"# source: {fd.name}",
        "",
        f"import {fd.name.replace('.proto', '')}_pb2 as _pb2",
        "from chattolib._connect import ConnectClient, ConnectClientSync, MethodInfo",
        "",
        "",
        f"class {svc.name}Client(ConnectClient):",
    ]
    for m in svc.method:
        mn = _method_name(m)
        in_cls = m.input_type.lstrip(".")
        out_cls = m.output_type.lstrip(".")
        in_name = in_cls.split(".")[-1]
        out_name = out_cls.split(".")[-1]
        lines += [
            f"    async def {mn}(self, request: _pb2.{in_name}, *,"
            f" headers: dict[str, str] | None = None) -> _pb2.{out_name}:",
            "        return await self.execute_unary(",
            "            request=request,",
            "            method=MethodInfo(",
            f'                name="{m.name}",',
            f'                service_name="{base}",',
            f"                input=_pb2.{in_name},",
            f"                output=_pb2.{out_name},",
            "            ),",
            "            headers=headers,",
            "        )",
            "",
        ]
    lines += [
        f"class {svc.name}ClientSync(ConnectClientSync):",
    ]
    for m in svc.method:
        mn = _method_name(m)
        in_name = m.input_type.lstrip(".").split(".")[-1]
        out_name = m.output_type.lstrip(".").split(".")[-1]
        lines += [
            f"    def {mn}(self, request: _pb2.{in_name}, *,"
            f" headers: dict[str, str] | None = None) -> _pb2.{out_name}:",
            "        return self.execute_unary(",
            "            request=request,",
            "            method=MethodInfo(",
            f'                name="{m.name}",',
            f'                service_name="{base}",',
            f"                input=_pb2.{in_name},",
            f"                output=_pb2.{out_name},",
            "            ),",
            "            headers=headers,",
            "        )",
            "",
        ]
    return "\n".join(lines)


def generate(request: g.CodeGeneratorRequest) -> r.CodeGeneratorResponse:
    resp = r.CodeGeneratorResponse()
    generated = {name for name in request.file_to_generate}
    for fd in request.proto_file:
        if not fd.service or fd.name not in generated:
            continue
        out = resp.file.add()
        out.name = fd.name.replace(".proto", "_connect.py")
        out.content = _service_stub(fd)
    return resp


def main() -> None:
    data = sys.stdin.buffer.read()
    request = g.CodeGeneratorRequest.FromString(data)
    resp = generate(request)
    sys.stdout.buffer.write(resp.SerializeToString())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register the console script**

In `pyproject.toml`, add under `[project]` (sibling of `[project.optional-dependencies]`):

```toml
[project.scripts]
protoc-gen-chattolib = "chattolib._protoc_plugin:main"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_protoc_plugin.py -v`
Expected: 2 passed

- [ ] **Step 6: Lint + typecheck + commit**

Run: `.venv/bin/ruff check src/chattolib/_protoc_plugin.py tests/test_protoc_plugin.py && .venv/bin/python -m mypy src/chattolib/_protoc_plugin.py`

```bash
git add src/chattolib/_protoc_plugin.py pyproject.toml tests/test_protoc_plugin.py
git -c user.name=the-codemancer -c user.email=the-codemancer@users.noreply commit -m "Add protoc-gen-chattolib plugin that emits async+sync Connect client stubs"
```

---

### Task 4: Rewire `generate_pb.sh` and regenerate the stubs

**Files:**
- Modify: `scripts/generate_pb.sh`
- Delete: `scripts/regen_connect.py`
- Regenerate: `src/chattolib/_pb/**/*_connect.py` (24 files)

**Interfaces:**
- Consumes: the `protoc-gen-chattolib` entry point (Task 3), `--python_out` (unchanged).
- Produces: 24 `*_connect.py` files generated by the plugin (async + sync clients, no `connectrpc`).

- [ ] **Step 1: Edit `generate_pb.sh`**

Replace the connect-python block (currently lines ~110-119) with:

```bash
# Generate the Connect client stubs with chattolib's own plugin. The
# realtime proto has no services, so it yields only *_pb2.py (above).
if command -v protoc-gen-chattolib >/dev/null; then
    protoc --proto_path=proto \
        --chattolib_out=src/chattolib/_pb \
        "${proto_files[@]}"
else
    echo "protoc-gen-chattolib not on PATH; skipped connect stubs" >&2
fi
```

Also update the header comment (lines ~20-22) that references `protoc-gen-connect-python` to say `protoc-gen-chattolib` (bundled with chattolib, no separate install).

- [ ] **Step 2: Delete the obsolete post-processor**

Run: `rm scripts/regen_connect.py`

- [ ] **Step 3: Reinstall so the new entry point is on PATH, then regenerate**

```bash
.venv/bin/pip install -q -e .
export PATH="$PWD/.venv/bin:$PATH"
command -v protoc-gen-chattolib   # must print the path
./scripts/generate_pb.sh
```

- [ ] **Step 4: Verify the regenerated stubs are correct**

Run:
```bash
grep -rl 'connectrpc' src/chattolib/_pb/ | grep -v Binary || echo "no connectrpc refs"
grep -rc 'class .*ClientSync' src/chattolib/_pb/*/*_connect.py | grep -v ':0' | wc -l   # expect 24
```
Expected: no `connectrpc` references; 24 stubs each define a `*ClientSync`.

- [ ] **Step 5: Full suite + live smoke test**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (the 2 bot-key-gated live tests skip).

Then a live smoke test (proves the plugin-generated stubs work against a real server):
```bash
.venv/bin/python - <<'EOF'
import asyncio
from chattolib import ChattoClient
BASE="https://next.preview.chatto.run"; KEY="cht_BK_UnuarbSTES9hETf.jYxNYYaYTWQMrjjSZwRqqg"
async def m():
    async with ChattoClient(base_url=BASE) as a:
        p,_=await a.get_server(); print("get_server:", p.name, p.version)
    c=ChattoClient(token=KEY, base_url=BASE)
    print("me:", (await c.me()).login)
    print("rooms:", sum(1 for x in await c.list_rooms() if x.viewer_state.is_member))
    await c.close()
asyncio.run(m())
EOF
```
Expected: prints server name, bot login, room count — no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_pb.sh src/chattolib/_pb/
git rm scripts/regen_connect.py
git -c user.name=the-codemancer -c user.email=the-codemancer@users.noreply commit -m "Generate Connect stubs with the chattolib plugin; drop connectrpc from the build"
```

---

### Task 5: Final cleanup, docs, and dependency proof

**Files:**
- Modify: `pyproject.toml` (confirm no `connectrpc`), `README.md`, `AGENTS.md`, `docs/bots.md`
- Test: none new (verification task)

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: a dependency tree and doc set with zero `connectrpc`/`pyqwest`.

- [ ] **Step 1: Prove the dependency tree is clean**

Run:
```bash
.venv/bin/pip uninstall -y connectrpc pyqwest protobuf-py 2>/dev/null
.venv/bin/python -c "import connectrpc" 2>&1 | tail -1   # expect ModuleNotFoundError
.venv/bin/python -c "import pyqwest" 2>&1 | tail -1         # expect ModuleNotFoundError
.venv/bin/python -c "import chattolib; print('import OK')"
.venv/bin/python -m pytest tests/ -q
```
Expected: both `ModuleNotFoundError`, `import OK`, full suite green.

- [ ] **Step 2: Sweep docs for stale `connectrpc` references**

Run: `grep -rn 'connectrpc\|pyqwest\|connect-python' README.md AGENTS.md docs/ | grep -v 'no-pyqwest\|specs/'`
Fix each hit: the transport is now chattolib's own hand-rolled Connect client (`chattolib._connect`), generated by the bundled `protoc-gen-chattolib` plugin. Update the "Architecture" note in `AGENTS.md` and the install/dependency notes in `README.md` accordingly. (Leave `docs/no-pyqwest.md` and the spec as historical design records.)

- [ ] **Step 3: Lint + typecheck the whole tree**

Run: `.venv/bin/ruff check . && .venv/bin/python -m mypy src/chattolib`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml README.md AGENTS.md docs/
git -c user.name=the-codemancer -c user.email=the-codemancer@users.noreply commit -m "Drop connectrpc/pyqwest from docs and deps; chattolib is self-contained"
```

---

## Self-Review

- **Spec coverage:** §3.1 (sync client) → Task 1; §3.3 (vendored descriptors) → Task 2; §3.2 (plugin) → Task 3; §3.4 + §3.5 (generate_pb.sh, delete regen) → Task 4; §4 (sync wrapper design) → Task 1; §5 (stub shape) → Task 3; §7 (testing) → Tasks 1-3 unit tests + Task 4 golden/live; §8 risk "golden-file CI diff" → folded into Task 4 Step 4 (the `grep` verification) rather than a separate CI job, since this repo has no CI runner configured.
- **Placeholder scan:** none — every code step shows full content.
- **Type consistency:** `ConnectClientSync.execute_unary(*, request, method, headers=None)` and `.close()` are defined in Task 1 and consumed identically by the plugin-emitted sync classes in Task 3 and the regenerated stubs in Task 4. `MethodInfo(name, service_name, input, output)` is consistent across all tasks.
- **Open item (not a gap):** the spec's "golden-file CI diff" assumes a CI runner; this repo has none, so Task 4 verifies by re-running the plugin and grepping instead. If CI is added later, the same check ports directly.

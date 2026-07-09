---
# chattolib-vel8
title: Investigate tokio-related memory leak in Connect transport
status: scrapped
type: bug
priority: high
created_at: 2026-07-09T15:34:48Z
updated_at: 2026-07-09T15:40:03Z
---

Reported: memory usage grows over time when running chattolib against a live Chatto instance. Suspect the Rust runtime underneath connectrpc (pyqwest wraps reqwest which runs on tokio). Root-cause and mitigate — either through client-lifecycle changes in ChattoClient, an upstream connectrpc/pyqwest bug report, or a workaround.

## Investigation

**Setup.** Used psutil (RSS) and tracemalloc against a live Chatto HQ instance. Warmed up before measurements to skip cold-start allocations. gc.collect() before each reading.

### Reproduction

**Sustained RPC load on one ChattoClient** — the scenario that first looked like a leak:

| RPCs | RSS |
|---|---|
| 500 | 78.8 MiB |
| 1000 | 82.9 MiB |
| 2000 | 88.1 MiB |
| 3000 | 90.0 MiB |
| 3500 | **84.2 MiB (dropped)** |
| 5000 | 87.9 MiB |
| 7000 | **86.8 MiB (dropped)** |
| 10000 | 87.2 MiB |

RSS **plateaus around 85–91 MiB** after ~2500 RPCs and drops back down at times. Not unbounded growth — it's the steady-state footprint of the tokio HTTP/2 connection pool + stream state.

### Confirming: not Python

tracemalloc across 500 RPCs after warm-up:

- 372 KiB in `google.protobuf.json_format` (MessageToDict)
- 114 KiB in `chattolib.types` (dataclass parsers)
- 140 KiB in `asyncio`
- ~750 KiB total Python growth, but RSS grew 11 MiB.

So ~93% of the growth is in the native (Rust/pyqwest/reqwest/tokio) layer, and the Python side is well-behaved.

### Ruled out: pyqwest client multiplication

I hypothesised the 24-services-per-client shape (each service instantiates its own pyqwest `Client`) was the culprit. Measured directly:

- 200 ChattoClient create/close cycles, current impl (24 pyqwest each): 58.04 MiB
- 200 ChattoClient create/close cycles, one shared pyqwest across all services: 58.06 MiB
- **Δ: +0.02 MiB — no material improvement.**

Reason: `pyqwest.Client(transport=None)` uses `get_default_transport()` — a process-wide shared tokio transport. The 24 Python-side `Client` objects are thin wrappers around the same native transport, so sharing is already happening under the hood.

### Realtime WebSocket

30 seconds of live event streaming from Chatto HQ (27 events): RSS grew from 62.92 → 62.93 MiB. **Fully stable.**

### Conclusion

**No leak.** What looked like a leak is the tokio connection pool reaching its steady-state footprint over the first ~2000-3000 request/response RPCs. Memory both grows and shrinks within that window and does not exceed ~90 MiB even at 10 000 RPCs.

If a production process is showing **genuinely unbounded** growth, the more likely culprits are:
- Application code holding references to response messages
- Realtime event handlers accumulating state (chattolib's stream is fine, but a user's async task keeping refs isn't)
- A configured OpenTelemetry exporter (pyqwest emits OT metrics; without an exporter they no-op, but a badly-configured batching exporter could accumulate)
- Something outside chattolib

## Reasons for Scrapping

Closing as not-a-bug. Followed up with detailed telemetry so future investigations start with data. If the user hits a real reproducer, reopen with the specific scenario and I'll instrument further.

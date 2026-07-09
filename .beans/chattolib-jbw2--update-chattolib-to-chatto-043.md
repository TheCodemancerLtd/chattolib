---
# chattolib-jbw2
title: Update chattolib to Chatto 0.4.3
status: completed
type: task
priority: high
created_at: 2026-07-09T15:50:04Z
updated_at: 2026-07-09T15:51:27Z
---

Chatto server on chat.chatto.run is now at 0.4.3. Regenerate the proto bindings from upstream, diff the API surface for breaking or additive changes, adapt the client if needed, bump chattolib to 0.4.3, run the full check + live-verify, then publish and push.

## Summary of Changes
- Reran `scripts/generate_pb.sh` against upstream main. Regenerated Python bindings picked up the two upstream proto changes:
  - `chatto.api.v1.ListRoomMembersRequest`: default page size doc-comment changed from 20 to 250 (no wire/API change).
  - `buf/validate/validate.proto`: comment/example updates only.
- No client code changes required; every method, dataclass, and enum still matches the current server.
- Bumped `pyproject.toml` `version` from `0.4.2.post2` to `0.4.3` per the [[feedback-versioning-tracks-chatto]] policy (chattolib version tracks Chatto server X.Y.Z).
- Full check: `ruff`, `mypy --strict`, `pytest` (48 passed, 4 skipped) all clean.
- Live-verified against Chatto HQ (now serving v0.4.3) with the RoboChatto account: login, viewer, list_rooms, get_motd, list_roles all decode correctly.

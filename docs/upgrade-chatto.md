# Releasing a new chattolib version

This is the release runbook for chattolib. It is agent- and human-friendly: any AI coding assistant (or a human contributor) can follow it end-to-end. Trigger phrases include "upgrade chattolib to X.Y.Z", "Chatto is at X.Y.Z, catch up", "release a new chattolib".

chattolib's version tracks the Chatto server version it targets. A new Chatto release triggers a matching chattolib release. If a chattolib-only fix is needed between server releases, use a post-release suffix (`0.4.2.post1`) rather than bumping the base number ahead of Chatto.

## 1. Preflight

- Confirm the target version. If the requester gave one, use it. Otherwise fetch the latest tag:
  ```bash
  curl -sfL https://api.github.com/repos/chattocorp/chatto/tags | grep '"name"' | head -3
  ```
- Read the current version from `pyproject.toml`.
- If they are equal, propose a `.postN` bump only when a chattolib-only fix is warranted — otherwise stop and report that there is nothing to release.

## 2. Work in a disposable worktree

Do the whole release from a throwaway git worktree so the user's main checkout stays untouched — no risk of leaving stray regenerated protos or an in-flight version bump behind if you have to bail out. Create it from the tip of `main`:

```bash
main_repo=$(git rev-parse --show-toplevel)
work_dir=$(mktemp -d -t chattolib-<target>.XXXXXX)
git -C "$main_repo" worktree add "$work_dir" main
cd "$work_dir"
```

The worktree shares `.git`, so commits and pushes from it land on the same branch and remotes. It does **not** include gitignored files. Rehydrate the two you need — the venv (for `protoc-gen-connect-python`, `ruff`, `mypy`, `pytest`, `twine`) and the PyPI token — by symlinking them in from the main checkout:

```bash
ln -s "$main_repo/.venv" .venv
ln -s "$main_repo/.env.pipy" .env.pipy
```

If either is missing in the main checkout, stop and ask the requester to set it up before continuing.

Run every remaining step from `$work_dir`. When you are done, tear the worktree down (see the final step).

## 3. Track the work

Tasks in this repo are tracked with the [beans](https://github.com/hmans/beans) CLI (see the project's agent instructions).

- Look for an existing bean: `beans list --json -S "<target-version>"`.
- If none, create one:
  ```bash
  beans create --json "Update chattolib to Chatto <target>" -t task -p high -s in-progress \
      -d "Regenerate protos, adapt client, bump, verify, publish."
  ```
- Append the standard checklist to the bean body and check items off as they complete:
  ```
  - [ ] Regenerate proto bindings from upstream (<target>)
  - [ ] Diff `_pb/` and `proto/` to identify API surface changes
  - [ ] Adapt client/dataclasses to any breaking or additive changes
  - [ ] Bump version to <target> in pyproject.toml
  - [ ] Update agent-instructions service table if RPCs changed
  - [ ] Run ruff + mypy + pytest
  - [ ] Live-verify against Chatto HQ
  - [ ] Commit, push, build, publish
  ```

## 4. Regenerate the protos

The generator needs `protoc-gen-connect-python`, which is installed in the project venv.

`scripts/generate_pb.sh` **pins the proto source to a released tag** — by default `v<version>` from `pyproject.toml`. That is what you want in the release path. **Never regenerate from `main`:** chattolib 0.4.19 shipped once from `main` and broke realtime for every downstream client because Chatto's `main` had a protocol-v2 rewrite that the deployed 0.4.19 server did not speak.

For a version bump, **first update the `version = "..."` line in `pyproject.toml`** to the target so the generator picks the right tag. Alternatively, set `CHATTO_REF` explicitly.

```bash
# Preferred: the script picks v<version> from pyproject.toml
source .venv/bin/activate && bash scripts/generate_pb.sh

# Explicit override (rare, e.g. speculative work)
CHATTO_REF=v0.4.20 bash scripts/generate_pb.sh
```

Inspect the diff:

```bash
git status --short
git diff --stat proto/
```

## 5. Analyse the wire delta

Read the diff for each changed proto and classify each change:

| Change | Action |
|---|---|
| **Additive fields** on request/response messages | Extend the matching dataclass in `src/chattolib/types.py` (add the field, update the `.parse(dict)` classmethod) so the value round-trips through Python. |
| **New RPC** on an existing service | Add a wrapper method on `ChattoClient` in `src/chattolib/client.py`, mirroring nearby methods' naming and error handling. Update the service table in the agent instructions (`AGENTS.md` / `CLAUDE.md`). |
| **Renamed / removed field or RPC** | Breaking change. Update `ChattoClient` and any affected dataclasses; add an entry to the "Gotchas from the migration" section of the agent instructions. |
| **Metadata-only** (comments, `idempotency_level`, buf.validate constraints) | No client change; mention in the bean summary. |
| **Realtime proto changes** | A protocol-version bump is breaking. Update `REALTIME_PROTOCOL_VERSION` in `src/chattolib/realtime.py`, extend the frame dispatch in `RealtimeConnection.events()`, add wrappers for any new server frames, and thread new subscribe fields through `stream_events` / `RealtimeConnection`. Update `tests/test_realtime.py` — remove tests that reference deleted fields, add coverage for new frames. |

Where a new RPC has a complex, version-dependent response shape (typical of `chatto.admin.v1` permission RPCs), leave the raw response passthrough in place — the `services` escape hatch on `ChattoClient` covers callers who need the raw shape.

## 6. Verify

Always run all three checks. Because the venv was installed editable from the *primary* checkout, tests would otherwise import the primary checkout's `chattolib`, not the worktree's — force `PYTHONPATH=src` (or `MYPYPATH=src` for mypy) so the worktree's regenerated pb2 is what actually runs:

```bash
source .venv/bin/activate && ruff check .
source .venv/bin/activate && MYPYPATH=src mypy --explicit-package-bases src/chattolib
source .venv/bin/activate && PYTHONPATH=src pytest
```

Then live-verify the public discovery endpoint against Chatto HQ:

```bash
source .venv/bin/activate && python -c "
import asyncio
from chattolib import ChattoClient
async def main():
    async with ChattoClient(base_url='https://chat.chatto.run') as c:
        profile, login = await c.get_server()
        print('profile.name=', profile.name)
asyncio.run(main())
"
```

Integration tests (`tests/test_integration.py`) are skipped without `CHATTO_LOGIN` / `CHATTO_PASSWORD` — that's fine; the public `GetServer` round-trip is enough to confirm nothing wire-level is broken.

## 7. Commit and push

Stage everything modified — proto sources, regenerated `_pb/`, `client.py` / `types.py` / `realtime.py`, tests, `pyproject.toml`, and the agent instructions. Commit with a message shaped like:

```
Track Chatto <target>

<one paragraph describing the delta: additive fields, new RPCs,
breaking changes, and the client adaptations made>

Bumped version <previous> -> <target>.
```

Push to **both** remotes:

```bash
git push f3l1x main
git push origin main
```

`f3l1x` (git.f3l1x.it) and `origin` (github.com/TheCodemancerLtd) must both end up pointing at the new commit. Verify:

```bash
git ls-remote f3l1x main && git ls-remote origin main
```

If the remotes have older hashes than local (e.g. because upstream history was rewritten between sessions), **stop and get explicit authorization from the requester before force-pushing**. Force-pushing to `main` is destructive and must never be a silent step.

## 8. Build and publish

```bash
source .venv/bin/activate && rm -rf dist/ build/ && python -m build
source .venv/bin/activate && twine check dist/chattolib-<target>*
source .venv/bin/activate && TWINE_USERNAME=__token__ TWINE_PASSWORD="$(cat .env.pipy)" \
    twine upload dist/chattolib-<target>*
```

- `.env.pipy` holds the PyPI API token as a single line beginning with `pypi-`. It is gitignored — never stage or commit it.
- If `.env.pipy` is missing or the upload rejects the token, stop and ask the requester to refresh it. Do not attempt alternative auth paths.

## 9. Close the bean

Update the bean with a `## Summary of Changes` section (what shipped, newly typed dataclasses, wire delta, PyPI link) and set the status to `completed`. Check off any remaining todos in the same mutation:

```bash
beans query 'mutation {
  updateBean(id: "<bean-id>", input: {
    status: "completed"
    bodyMod: {
      replace: [ ... ]
      append: "## Summary of Changes\n\n..."
    }
  }) { id status }
}' --json
```

## 10. Tear the worktree down

Once the push has landed on both remotes and the PyPI upload has succeeded, the worktree has served its purpose. Return to the main checkout and remove it:

```bash
cd "$main_repo"
git worktree remove "$work_dir"
```

If `git worktree remove` refuses (e.g. residual untracked files), inspect the worktree first — do not `--force` blindly. Only untracked build/upload artefacts (`dist/`, `build/`, `__pycache__`) and the two symlinks (`.venv`, `.env.pipy`) should be there. If that is all, `git worktree remove --force "$work_dir"` is safe.

## 11. Report

Finish with the PyPI URL (`https://pypi.org/project/chattolib/<target>/`) and a one-line summary of the delta.

---
# chattolib-tk55
title: Push v0.1.0b3 to Forgejo (f3l1x remote)
status: todo
type: task
priority: normal
created_at: 2026-06-12T14:41:13Z
updated_at: 2026-06-12T14:41:13Z
---

v0.1.0b3 commit (deb4823) and tag are on origin/GitHub but not on the f3l1x remote (https://git.f3l1x.it/TheCodemancer/chattolib.git). `git push f3l1x main && git push f3l1x v0.1.0b3` fails with 'could not read Username' — no credentials configured for git.f3l1x.it.

## Tasks
- [ ] Decide on auth: SSH (set-url to git@git.f3l1x.it:...) or HTTPS+token (~/.netrc or credential helper)
- [ ] Push main and tag v0.1.0b3 to f3l1x

## Context
- Forgejo repo already exists (API returns 200 for repos/TheCodemancer/chattolib)
- Remote already configured locally: `f3l1x -> https://git.f3l1x.it/TheCodemancer/chattolib.git`

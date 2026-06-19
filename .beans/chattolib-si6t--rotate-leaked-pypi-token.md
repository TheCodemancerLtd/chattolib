---
# chattolib-si6t
title: Rotate leaked PyPI token
status: todo
type: task
priority: critical
created_at: 2026-06-12T14:41:13Z
updated_at: 2026-06-12T14:41:13Z
---

PyPI token pypi-AgEIcHlw...nw (account scope) was pasted into the Claude Code transcript during the 0.1.0b3 publish. Anyone replaying that transcript can re-upload to the chattolib project on pypi.org. Revoke at https://pypi.org/manage/account/token/ and, if still needed, mint a project-scoped replacement.

## Tasks
- [ ] Revoke the leaked token at https://pypi.org/manage/account/token/
- [ ] (Optional) Mint a new project-scoped token for chattolib only
- [ ] (Optional) Add ~/.pypirc or set TWINE_PASSWORD env var so future uploads don't require pasting the token

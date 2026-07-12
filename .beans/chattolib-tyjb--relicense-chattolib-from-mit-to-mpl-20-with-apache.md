---
# chattolib-tyjb
title: Relicense chattolib from MIT to MPL-2.0 (with Apache-2.0 for vendored protos)
status: completed
type: task
priority: high
created_at: 2026-07-12T23:57:31Z
updated_at: 2026-07-12T23:59:34Z
---

Switch the library's license from MIT to MPL-2.0 for chattolib's own code, keeping Apache-2.0 for the vendored Chatto proto material (proto/** and src/chattolib/_pb/**). Ship LICENSE, LICENSES/, REUSE.toml, LICENSING.md, update pyproject metadata. Historical MIT releases (<= 0.4.9) stay MIT on PyPI forever; the relicense affects new versions only.

## Summary of Changes

Relicensed chattolib from **MIT** to **MPL-2.0** (with **Apache-2.0** preserved for vendored Chatto/buf material). Follows Chatto's own REUSE-based split.

- `LICENSE` replaced with the canonical MPL-2.0 text.
- Added `LICENSES/MPL-2.0.txt` and `LICENSES/Apache-2.0.txt` (REUSE convention).
- Added `REUSE.toml` with the machine-readable licence map:
  - Default: MPL-2.0 for chattolib's own code (TheCodemancer copyright).
  - `proto/chatto/**` and `src/chattolib/_pb/chatto/**`: Apache-2.0 (ChattoCorp copyright).
  - `proto/buf/**` and `src/chattolib/_pb/buf/**`: Apache-2.0 (Buf Technologies copyright).
- Added `LICENSING.md` explaining the dual arrangement in prose.
- `pyproject.toml`: `license = "MPL-2.0 AND Apache-2.0"` (SPDX expression, PEP 639), `license-files = ["LICENSE", "LICENSES/*.txt"]`.
- Refreshed `README.md` License section; noted that MIT releases (<= 0.4.9) stay MIT on PyPI forever.
- Build validated: wheel bundles LICENSE + LICENSES/*.txt under `chattolib-0.4.9.dist-info/licenses/`. `twine check` passes with the new SPDX expression.

Historical MIT releases (0.0.1 through 0.4.9) remain MIT-licensed on PyPI; the relicence applies to newly published releases only.

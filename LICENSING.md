# Licensing

chattolib uses per-file SPDX license metadata following the
[REUSE](https://reuse.software/) specification. The canonical
machine-readable licence boundary is in [REUSE.toml](REUSE.toml).

## Default: MPL-2.0

The library's own code — `src/chattolib/*.py` (except the `_pb/` subtree),
`tests/`, `scripts/`, and repository documentation — is licensed under the
**Mozilla Public License 2.0** (`MPL-2.0`). See [LICENSE](LICENSE) for the
full text.

MPL-2.0 is a **weak, file-level copyleft**:

- You can freely use, distribute, and embed chattolib in commercial or
  proprietary software.
- If you modify a file of chattolib itself and distribute the modified
  version, the modified file must be released under MPL-2.0.
- New files you add alongside chattolib (adapters, plugins, your own
  application code) can be under any licence you like.

MPL-2.0 explicitly permits combination with GPL/LGPL/AGPL code via its
[§3.3 Secondary License](https://www.mozilla.org/en-US/MPL/2.0/#L342)
mechanism.

## Apache-2.0 carve-outs

The following paths ship under **Apache License 2.0** (`Apache-2.0`) — they
are vendored from upstream projects that publish under Apache-2.0 by choice:

- `proto/chatto/**` — Chatto's public `.proto` sources, vendored from
  [chattocorp/chatto](https://github.com/chattocorp/chatto). Chatto's own
  [`REUSE.toml`](https://github.com/chattocorp/chatto/blob/main/REUSE.toml)
  places these files under Apache-2.0 precisely so that third-party client
  libraries like chattolib can be built with a licence of their own choice.
- `src/chattolib/_pb/chatto/**` — the generated Python protobuf and Connect
  bindings derived from those `.proto` files. Derivative works of Apache-2.0
  input remain Apache-2.0.
- `proto/buf/validate/**` and `src/chattolib/_pb/buf/**` — vendored
  from [bufbuild/protovalidate](https://github.com/bufbuild/protovalidate),
  also Apache-2.0 upstream.

Full licence texts live in [`LICENSES/`](LICENSES/).

## Historical MIT releases

chattolib versions **0.0.1 through 0.4.9** were released under the **MIT
License**. Those releases remain MIT-licensed forever on
[PyPI](https://pypi.org/project/chattolib/); anyone who obtained them under
MIT keeps those rights on those versions. The MPL-2.0 relicence applies to
newly published releases only.

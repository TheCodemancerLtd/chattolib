#!/usr/bin/env bash
# Regenerate the vendored Python protobuf + ConnectRPC bindings under
# src/chattolib/_pb.
#
# Fetches the .proto sources for a pinned Chatto ref (default: the version
# recorded in pyproject.toml, as a `v<version>` tag) and runs protoc with
# the built-in Python generator and the connect-python plugin.
#
# ALWAYS pin to a released tag. Fetching from `main` risks shipping
# unreleased wire changes that the deployed Chatto server does not speak
# — chattolib 0.4.19 shipped that way and broke realtime for every
# downstream client. Override the pin explicitly if you know what you are
# doing:
#
#   CHATTO_REF=v0.4.19       ./scripts/generate_pb.sh
#   CHATTO_REF=main          ./scripts/generate_pb.sh   # unreleased
#
# Requirements:
#   - protoc on PATH
#   - protoc-gen-chattolib on PATH (bundled with chattolib itself — run
#     `pip install -e .` and it is on PATH; no separate install needed)
#   - curl on PATH
#
# Run from the repo root:  ./scripts/generate_pb.sh

set -euo pipefail

if ! command -v protoc >/dev/null; then
    echo "protoc not found on PATH" >&2
    exit 1
fi

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

# Default the Chatto ref to `v<base-version-in-pyproject.toml>`. Strip any
# post/pre-release suffix — those are chattolib-only fixes against the same
# server release. Callers can override with CHATTO_REF.
default_version=$(sed -nE 's/^version *= *"([^"]+)".*/\1/p' pyproject.toml | head -1)
default_base=${default_version%%.post*}
default_base=${default_base%%.dev*}
default_base=${default_base%%a*}
default_base=${default_base%%b*}
default_base=${default_base%%rc*}
default_ref="v${default_base}"

chatto_ref=${CHATTO_REF:-$default_ref}
echo "Fetching proto sources from chattocorp/chatto@${chatto_ref}"

mkdir -p proto/chatto/{api,admin,auth,discovery,realtime}/v1 proto/buf/validate

chatto_base="https://raw.githubusercontent.com/chattocorp/chatto/${chatto_ref}/proto/chatto"

fetch() {
    local rel=$1
    curl -sfL "$chatto_base/${rel#chatto/}" -o "proto/$rel"
    echo "  $rel"
}

echo "Fetching proto sources ..."
# chatto.api.v1
for f in \
    account.proto attachments.proto asset_uploads.proto common.proto \
    external_identities.proto link_previews.proto member_directory.proto \
    messages.proto message_types.proto \
    notifications.proto pagination.proto permissions.proto presence.proto \
    push_notifications.proto reactions.proto read_state.proto \
    room_directory.proto rooms.proto room_timeline.proto roles.proto \
    server.proto server_state.proto threads.proto users.proto \
    user_status.proto viewer.proto voice_calls.proto
do
    fetch "chatto/api/v1/$f"
done

# chatto.admin.v1
for f in \
    diagnostics.proto event_log.proto members.proto permissions.proto \
    roles.proto room_layout.proto server.proto
do
    fetch "chatto/admin/v1/$f"
done

# chatto.auth.v1
fetch chatto/auth/v1/external_identity_auth.proto

# chatto.discovery.v1
fetch chatto/discovery/v1/server.proto

# chatto.realtime.v1
fetch chatto/realtime/v1/realtime.proto

# buf.validate — sourced from bufbuild/protovalidate
curl -sfL \
    "https://raw.githubusercontent.com/bufbuild/protovalidate/main/proto/protovalidate/buf/validate/validate.proto" \
    -o proto/buf/validate/validate.proto
echo "  buf/validate/validate.proto"

echo "Regenerating Python bindings ..."
rm -rf src/chattolib/_pb/chatto src/chattolib/_pb/buf
mkdir -p src/chattolib/_pb

# Collect every input .proto so protoc's plugins visit each service.
mapfile -t proto_files < <(find proto -type f -name '*.proto' | sort)

protoc --proto_path=proto \
    --python_out=src/chattolib/_pb \
    "${proto_files[@]}"

# Generate the Connect client stubs with chattolib's own plugin. The
# realtime proto has no services, so it yields only *_pb2.py (above).
# The plugin is a standalone script (scripts/protoc-gen-chattolib) loaded by
# file path, so it runs even before the stubs it generates exist. We expose it
# on PATH via a temp bin dir for the duration of this protoc invocation.
if [ -f "$repo_root/scripts/protoc-gen-chattolib" ]; then
    _plugin_bin=$(mktemp -d)
    ln -s "$repo_root/scripts/protoc-gen-chattolib" "$_plugin_bin/protoc-gen-chattolib"
    PATH="$_plugin_bin:$PATH" protoc --proto_path=proto \
        --chattolib_out=src/chattolib/_pb \
        "${proto_files[@]}"
    rm -rf "$_plugin_bin"
else
    echo "protoc-gen-chattolib not found; skipped connect stubs" >&2
fi

# Add __init__.py at every level so the generated modules form a package.
find src/chattolib/_pb \( -path '*/chatto*' -o -path '*/buf*' \) -type d \
    | while read -r dir; do touch "$dir/__init__.py"; done

echo "Done."

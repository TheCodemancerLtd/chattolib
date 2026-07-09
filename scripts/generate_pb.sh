#!/usr/bin/env bash
# Regenerate the vendored Python protobuf + ConnectRPC bindings under
# src/chattolib/_pb.
#
# Fetches the required .proto sources into proto/ (from chattocorp/chatto's
# main branch and bufbuild/protovalidate) and runs protoc with both the
# built-in Python code generator and the connect-python plugin.
#
# Requirements:
#   - protoc on PATH
#   - protoc-gen-connect-python on PATH (install via
#     `pip install protoc-gen-connect-python`, which chattolib pins under
#     the `[realtime]` extra)
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

mkdir -p proto/chatto/{api,admin,auth,discovery,realtime}/v1 proto/buf/validate

chatto_base="https://raw.githubusercontent.com/chattocorp/chatto/main/proto/chatto"

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
    messages.proto message_types.proto notification_preferences.proto \
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

# Only run the connect-python plugin when it is available. The realtime
# WebSocket path only needs the pb2 files; every request/response service is
# strongly typed via the connect stubs.
if command -v protoc-gen-connect-python >/dev/null; then
    protoc --proto_path=proto \
        --connect-python_out=src/chattolib/_pb \
        "${proto_files[@]}"
else
    echo "protoc-gen-connect-python not on PATH; skipped connect stubs" >&2
fi

# Add __init__.py at every level so the generated modules form a package.
find src/chattolib/_pb \( -path '*/chatto*' -o -path '*/buf*' \) -type d \
    | while read -r dir; do touch "$dir/__init__.py"; done

echo "Done."

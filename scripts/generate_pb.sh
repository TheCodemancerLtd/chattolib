#!/usr/bin/env bash
# Regenerate the vendored Python protobuf bindings under src/chattolib/_pb.
#
# Fetches the required .proto sources into proto/ (from chattocorp/chatto's
# main branch and bufbuild/protovalidate) and runs protoc.
#
# Requirements: protoc on PATH, curl on PATH.
#
# Run from the repo root:  ./scripts/generate_pb.sh

set -euo pipefail

if ! command -v protoc >/dev/null; then
    echo "protoc not found on PATH" >&2
    exit 1
fi

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

mkdir -p proto/chatto/realtime/v1 proto/chatto/api/v1 proto/buf/validate

chatto_base="https://raw.githubusercontent.com/chattocorp/chatto/main/proto/chatto"

fetch() {
    local rel=$1
    local dest="proto/$rel"
    curl -sfL "$chatto_base/${rel#chatto/}" -o "$dest"
    echo "  $rel"
}

echo "Fetching proto sources ..."
fetch chatto/realtime/v1/realtime.proto
fetch chatto/api/v1/viewer.proto
fetch chatto/api/v1/notification_preferences.proto
fetch chatto/api/v1/presence.proto
fetch chatto/api/v1/users.proto
fetch chatto/api/v1/user_status.proto
fetch chatto/api/v1/permissions.proto
curl -sfL "https://raw.githubusercontent.com/bufbuild/protovalidate/main/proto/protovalidate/buf/validate/validate.proto" \
    -o proto/buf/validate/validate.proto
echo "  buf/validate/validate.proto"

echo "Regenerating Python bindings ..."
rm -rf src/chattolib/_pb/chatto src/chattolib/_pb/buf
mkdir -p src/chattolib/_pb

protoc --proto_path=proto --python_out=src/chattolib/_pb \
    proto/chatto/realtime/v1/realtime.proto \
    proto/chatto/api/v1/viewer.proto \
    proto/chatto/api/v1/notification_preferences.proto \
    proto/chatto/api/v1/presence.proto \
    proto/chatto/api/v1/users.proto \
    proto/chatto/api/v1/user_status.proto \
    proto/chatto/api/v1/permissions.proto \
    proto/buf/validate/validate.proto

# Add __init__.py at every level so the generated modules form a package.
for dir in \
    src/chattolib/_pb/chatto \
    src/chattolib/_pb/chatto/api \
    src/chattolib/_pb/chatto/api/v1 \
    src/chattolib/_pb/chatto/realtime \
    src/chattolib/_pb/chatto/realtime/v1 \
    src/chattolib/_pb/buf \
    src/chattolib/_pb/buf/validate
do
    touch "$dir/__init__.py"
done

echo "Done."

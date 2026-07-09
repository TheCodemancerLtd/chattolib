"""Vendored protobuf bindings for the Chatto realtime WebSocket protocol.

Generated modules under this directory import each other via top-level package
paths (``from chatto.api.v1 import ...``, ``from buf.validate import ...``)
because that is how ``protoc`` emits Python bindings. To make them importable
without polluting the top-level ``chatto`` / ``buf`` namespaces of dependent
projects, this package inserts its own directory into ``sys.path`` on first
import. Chatto is the only real project shipping under those names, so the
collision risk is negligible.

Regenerate with ``scripts/generate_pb.sh``.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

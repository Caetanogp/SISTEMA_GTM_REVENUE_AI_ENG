#!/usr/bin/env python
"""PreToolUse hook: refuse writes to files that must never be edited by an agent.

Permissions in settings.json already deny reading these paths; this is the second lock, on the
write side, so a mistake cannot land even if a permission rule is loosened later.

Exit 2 blocks the tool call and returns the reason to the agent.
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import PurePath

BLOCKED_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "credentials*",
    "*.tfstate",
    "*.tfstate.*",
)
BLOCKED_DIRS = ("secrets", ".aws", ".ssh", ".git")
# .env.example is the one file in this family that is meant to be edited.
ALLOWED = (".env.example",)


def is_blocked(file_path: str) -> str | None:
    path = PurePath(file_path)
    name = path.name

    if name in ALLOWED:
        return None

    for part in path.parts:
        if part in BLOCKED_DIRS:
            return f"{part}/ is off limits to agents"

    for pattern in BLOCKED_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return f"{name} matches the protected pattern {pattern}"

    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never block on a malformed payload

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path:
        return 0

    reason = is_blocked(str(file_path))
    if reason is None:
        return 0

    print(
        f"BLOCKED: refusing to write {file_path} — {reason}.\n"
        "Secrets and credentials never enter this repository (AGENTS.md, Security rules). "
        "If a new configuration value is needed, add a placeholder to .env.example instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

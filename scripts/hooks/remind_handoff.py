#!/usr/bin/env python
"""Stop hook: do not let a session end with code changes but a stale handoff.

The whole development model here alternates between Claude Code and Codex. A session that changes
code and leaves `.handoff/STATE.md` untouched costs the next session a rediscovery it should never
have to do.

Blocks only when there are real working-tree changes AND STATE.md was neither modified nor part of
the most recent commit. Set HANDOFF_HOOK_DISABLED=1 to turn it off.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ".handoff/STATE.md"


def git(*args: str) -> str:
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607 - git comes from PATH by design
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def main() -> int:
    if os.environ.get("HANDOFF_HOOK_DISABLED") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    # Never re-block a stop that this hook already blocked once.
    if payload.get("stop_hook_active"):
        return 0

    status = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    if not status:
        return 0

    changed = [line[3:].strip().strip('"') for line in status]
    meaningful = [p for p in changed if not p.endswith(".log")]
    if not meaningful:
        return 0

    if any(STATE in p for p in changed):
        return 0

    if STATE in git("show", "--name-only", "--pretty=format:", "HEAD"):
        return 0

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    f"There are {len(meaningful)} changed file(s) but {STATE} was not updated. "
                    "Follow docs/playbooks/handoff.md: record what is Done (with file:line and "
                    "command output as evidence), what is in flight, and the next 3-5 steps, then "
                    "finish. The next session may be a different agent with no memory of this one."
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

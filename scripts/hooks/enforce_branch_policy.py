#!/usr/bin/env python
"""PreToolUse hook: no agent commits on a protected branch.

Gitflow for this repo: work happens on `feature/SPEC-NNN-slug` or `fix/slug`, branched from
`develop`. `main` and `develop` receive code through pull requests only, merged by the user.

Blocks `git commit`, `git merge` and `git push` when HEAD is on a protected branch. Exit 2 stops
the tool call and hands the reason back to the agent.

Two exceptions, both narrow:
  - a commit that touches nothing but `.handoff/` (state must always be recordable);
  - `HANDOFF_BRANCH_POLICY_DISABLED=1`, for the rare case the user explicitly wants it off.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = {"main", "develop", "master"}
WRITE_COMMANDS = re.compile(r"\bgit\s+(commit|merge|push|rebase|cherry-pick|revert)\b")


def git(*args: str) -> str:
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607 - git comes from PATH by design
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def only_handoff_staged() -> bool:
    """True when every staged path lives under .handoff/ or is the STATE file itself."""
    staged = [line for line in git("diff", "--cached", "--name-only").splitlines() if line.strip()]
    return bool(staged) and all(path.startswith(".handoff/") for path in staged)


def main() -> int:
    if os.environ.get("HANDOFF_BRANCH_POLICY_DISABLED") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command or not WRITE_COMMANDS.search(command):
        return 0

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch not in PROTECTED:
        return 0

    if "commit" in command and only_handoff_staged():
        return 0

    print(
        f"BLOCKED: you are on `{branch}`, which is protected.\n"
        "Gitflow for this repo (AGENTS.md, Git workflow):\n"
        "  git checkout develop && git pull\n"
        "  git checkout -b feature/SPEC-NNN-slug\n"
        "  ...work, commit there...\n"
        "  open a PR into develop; the user merges it.\n"
        "Never commit system code straight to main or develop, and never force-push either.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

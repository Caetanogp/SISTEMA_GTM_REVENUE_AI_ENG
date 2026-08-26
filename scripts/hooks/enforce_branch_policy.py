#!/usr/bin/env python
"""PreToolUse hook: keep agents off `main`, and off direct writes to `develop`.

Gitflow for this repo: work happens on `feature/SPEC-NNN-slug` or `fix/slug`, branched from
`develop`. `main` is fully hands-off for an agent — commit, merge, push, rebase, cherry-pick,
revert, none of it, ever; it only receives code from `develop` as a release, performed by the user.

`develop` is the integration branch: an agent never edits it directly (no `commit`, `rebase`,
`cherry-pick`, `revert` with it as HEAD), but once a feature/fix branch has passed the
verification gate, the agent MAY merge it into `develop` itself with `git merge`. Publishing
`develop` to a remote (`git push`) still requires the user — merging locally is bookkeeping;
pushing makes it visible elsewhere.

Exit 2 stops the tool call and hands the reason back to the agent.

Two exceptions, both narrow:
  - a commit that touches nothing but `.handoff/` (state must always be recordable), on any branch;
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

# main/master: every write verb below is blocked, no exceptions.
FULLY_PROTECTED = {"main", "master"}
# develop: only a `merge` (landing a verified feature/fix branch) is allowed.
MERGE_ONLY = {"develop"}

WRITE_COMMAND = re.compile(r"\bgit\s+(commit|merge|push|rebase|cherry-pick|revert)\b")


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
    """True when every staged path lives under .handoff/."""
    staged = [line for line in git("diff", "--cached", "--name-only").splitlines() if line.strip()]
    return bool(staged) and all(path.startswith(".handoff/") for path in staged)


def block(branch: str, verb: str) -> None:
    if branch in FULLY_PROTECTED:
        print(
            f"BLOCKED: `{branch}` is fully hands-off for agents — no {verb}, ever.\n"
            "Gitflow for this repo (AGENTS.md, Git workflow):\n"
            "  git checkout develop && git pull\n"
            "  git checkout -b feature/SPEC-NNN-slug\n"
            "  ...work, verify, merge into develop...\n"
            f"`{branch}` only receives code from `develop` as a release, performed by the user.",
            file=sys.stderr,
        )
        return

    print(
        f"BLOCKED: `{branch}` is the integration branch — agents don't {verb} on it directly.\n"
        "Write your change on a feature/fix branch instead:\n"
        "  git checkout -b feature/SPEC-NNN-slug\n"
        "Once it passes the verification gate (docs/playbooks/verify-before-done.md), you may "
        "`git merge` that branch into develop yourself. Publishing develop to a remote "
        "(`git push`) is still the user's call.",
        file=sys.stderr,
    )


def main() -> int:
    if os.environ.get("HANDOFF_BRANCH_POLICY_DISABLED") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    match = WRITE_COMMAND.search(command) if command else None
    if not match:
        return 0
    verb = match.group(1)

    branch = git("rev-parse", "--abbrev-ref", "HEAD")

    if branch in MERGE_ONLY and verb == "merge":
        return 0

    if branch not in FULLY_PROTECTED and branch not in MERGE_ONLY:
        return 0

    if verb == "commit" and only_handoff_staged():
        return 0

    block(branch, verb)
    return 2


if __name__ == "__main__":
    sys.exit(main())

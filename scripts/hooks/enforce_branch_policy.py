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

Detection note: `_find_git_write_verb` only matches an actual invoked command, not any text that
merely *mentions* a git command. It strips heredoc bodies (so a doc file being written via a Bash
heredoc that says "you can `git merge` this branch" doesn't trigger a false BLOCKED) and anchors
the match to the start of each `;`/`&&`/`||`/`|`/newline-separated segment, rather than searching
for the pattern anywhere in the raw command string.
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

_WRITE_VERBS = "commit|merge|push|rebase|cherry-pick|revert"
# Anchored at the start of a segment, with optional simple VAR=value prefixes (e.g. `FOO=bar git
# commit ...`) - deliberately does NOT match `git -C path commit` or other pre-subcommand flags,
# same limitation the original version had.
_GIT_VERB_AT_START = re.compile(
    rf"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*git\s+({_WRITE_VERBS})\b"
)
_SEGMENT_SPLIT = re.compile(r"[;\n]|&&|\|\|?")
_HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies so prose inside them is never mistaken for an invoked command."""
    lines = command.splitlines()
    kept: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        match = _HEREDOC_START.search(line)
        if match:
            delimiter = match.group(2)
            i += 1
            while i < len(lines) and lines[i].strip() != delimiter:
                i += 1
            i += 1  # skip the closing delimiter line itself too
            continue
        i += 1
    return "\n".join(kept)


def find_git_write_verb(command: str) -> str | None:
    """Return the git write verb actually being invoked, or None if there isn't one.

    Only matches a command that genuinely starts a segment with `git <verb>` - not text that
    happens to contain those words, e.g. inside a heredoc payload or a quoted string.
    """
    cleaned = _strip_heredocs(command)
    for segment in _SEGMENT_SPLIT.split(cleaned):
        match = _GIT_VERB_AT_START.match(segment.strip())
        if match:
            return match.group(1)
    return None


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
    verb = find_git_write_verb(command) if command else None
    if not verb:
        return 0

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

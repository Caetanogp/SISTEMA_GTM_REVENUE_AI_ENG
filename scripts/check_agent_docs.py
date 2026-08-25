#!/usr/bin/env python
"""Guard the agent instruction files.

AGENTS.md is canonical and CLAUDE.md must import it, so the two agents can never drift apart.
AGENTS.md is also loaded on every turn, so it has a hard line budget: an instruction file that
nobody can afford to read is an instruction file nobody reads.

Run: python scripts/check_agent_docs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
CLAUDE = ROOT / "CLAUDE.md"

MAX_AGENTS_LINES = 200
MAX_CLAUDE_LINES = 90
REQUIRED_AGENTS_SECTIONS = (
    "## Golden rules",
    "## Architecture boundaries",
    "## Commands",
    "## Spec Driven Development",
    "## Git workflow",
    "## Security rules",
    "## Handoff protocol",
    "## Definition of Done",
)


def check() -> list[str]:
    errors: list[str] = []

    for path in (AGENTS, CLAUDE):
        if not path.exists():
            errors.append(f"{path.name} is missing")
    if errors:
        return errors

    agents_text = AGENTS.read_text(encoding="utf-8")
    claude_text = CLAUDE.read_text(encoding="utf-8")

    agents_lines = len(agents_text.splitlines())
    if agents_lines > MAX_AGENTS_LINES:
        errors.append(
            f"AGENTS.md has {agents_lines} lines (max {MAX_AGENTS_LINES}). "
            "Move detail into docs/ and link to it."
        )

    claude_lines = len(claude_text.splitlines())
    if claude_lines > MAX_CLAUDE_LINES:
        errors.append(
            f"CLAUDE.md has {claude_lines} lines (max {MAX_CLAUDE_LINES}). "
            "Shared rules belong in AGENTS.md."
        )

    if "@AGENTS.md" not in claude_text:
        errors.append("CLAUDE.md must import the canonical file with a line containing @AGENTS.md")

    for section in REQUIRED_AGENTS_SECTIONS:
        if section not in agents_text:
            errors.append(f"AGENTS.md is missing the section: {section}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Agent docs check FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Agent docs check passed (AGENTS.md canonical, CLAUDE.md imports it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

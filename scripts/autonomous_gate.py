#!/usr/bin/env python
"""The deterministic referee for an unattended loop session.

Conclusion can never be the model's own self-assessment - that is exactly the failure mode the
Ralph plugin's README admits to (an exact-string "completion promise" the model itself emits,
with no independent check). This script is what `/goal` actually evaluates instead: a real
condition, checked by code, not judgment.

Reads .handoff/AUTONOMOUS_QUEUE.md for the ordered list of items and their file scope, and
docs/specs/SPEC-001-vertical-slice-account-prioritization/tasks.md's "## 2. Application" section
for progress (the loop ticks boxes there as it completes items - this script trusts and verifies
those ticks, it does not duplicate them).

Exit codes:
  0 - every queue item done AND the full quality gate is green. Goal achieved.
  1 - more work remains, or the gate is currently red. Keep iterating.
  2 - HALT. Wrong branch, a scope violation, the next item is marked
      HALT: PLAN-MODE-REQUIRED, or too many consecutive failures on the same item (anti-infinite-
      loop). Writes the reason to .handoff/STATE.md and the process should stop - not just retry.

Run: python scripts/autonomous_gate.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = ROOT / ".handoff" / "AUTONOMOUS_QUEUE.md"
TASKS_FILE = (
    ROOT
    / "docs"
    / "specs"
    / "SPEC-001-vertical-slice-account-prioritization"
    / "tasks.md"
)
STATE_FILE = ROOT / ".handoff" / "STATE.md"
GATE_STATE_FILE = ROOT / ".handoff" / ".autonomous_gate_state.json"
TASKS_SECTION_HEADER = "## 2. Application"
TASKS_SECTION_END = "## 3. Persistence"
MAX_CONSECUTIVE_FAILURES = 5

_ITEM_HEADER = re.compile(r"^## Item (\d+) — (.+?)(?: — \*\*HALT: (\S+)\*\*)?$", re.MULTILINE)
_SCOPE_BLOCK = re.compile(r"^- \*\*Scope:\*\* (.+?)(?=\n- \*\*|\n\n|\Z)", re.MULTILINE | re.DOTALL)
_BACKTICK_PATH = re.compile(r"`([^`]+)`")
_TASK_LINE = re.compile(r"^- \[( |x)\] ", re.MULTILINE)


@dataclass(frozen=True)
class QueueItem:
    number: int
    title: str
    halt_reason: str | None
    scope: tuple[str, ...]


@dataclass
class GateState:
    last_item: int | None = None
    consecutive_failures: int = 0
    baseline_sha: str | None = None
    baseline_done_count: int = 0

    @classmethod
    def load(cls) -> GateState:
        if GATE_STATE_FILE.exists():
            try:
                raw = json.loads(GATE_STATE_FILE.read_text(encoding="utf-8"))
                return cls(
                    last_item=raw.get("last_item"),
                    consecutive_failures=int(raw.get("consecutive_failures", 0)),
                    baseline_sha=raw.get("baseline_sha"),
                    baseline_done_count=int(raw.get("baseline_done_count", 0)),
                )
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass
        return cls()

    def save(self) -> None:
        payload = {
            "last_item": self.last_item,
            "consecutive_failures": self.consecutive_failures,
            "baseline_sha": self.baseline_sha,
            "baseline_done_count": self.baseline_done_count,
        }
        GATE_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def current_branch() -> str:
    return run("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def parse_queue() -> list[QueueItem]:
    text = QUEUE_FILE.read_text(encoding="utf-8")
    items: list[QueueItem] = []
    headers = list(_ITEM_HEADER.finditer(text))
    for index, header in enumerate(headers):
        number = int(header.group(1))
        title = header.group(2).strip()
        halt_reason = header.group(3)
        body_start = header.end()
        body_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        body = text[body_start:body_end]
        scope_match = _SCOPE_BLOCK.search(body)
        scope = tuple(_BACKTICK_PATH.findall(scope_match.group(1))) if scope_match else ()
        items.append(QueueItem(number=number, title=title, halt_reason=halt_reason, scope=scope))
    return items


def completed_task_count() -> tuple[int, int]:
    """(done, total) checkboxes in tasks.md's Application section."""
    text = TASKS_FILE.read_text(encoding="utf-8")
    start = text.index(TASKS_SECTION_HEADER)
    end = text.index(TASKS_SECTION_END, start)
    section = text[start:end]
    boxes = [m.group(1) for m in _TASK_LINE.finditer(section)]
    return sum(1 for b in boxes if b == "x"), len(boxes)


def current_head() -> str:
    return run("git", "rev-parse", "HEAD").stdout.strip()


def changed_files(baseline: str) -> list[str]:
    """Every file touched since baseline, staged or not - the honest current diff scope.

    baseline is the commit before which everything is considered pre-existing (already-landed
    prior items, or infra work committed before this item started) and therefore exempt from
    this item's scope check - see the docstring on why this isn't develop's merge-base.
    """
    committed = run("git", "diff", "--name-only", f"{baseline}..HEAD").stdout.splitlines()
    # --untracked-files=all: without it, git collapses a brand-new untracked directory into one
    # line for the directory itself (e.g. "?? context/") instead of listing the files inside it -
    # every item that introduces a new subpackage would otherwise show a false violation on the
    # directory path until something happened to `git add` it first.
    working = run("git", "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    working_paths = [line[3:].strip().strip('"') for line in working if line.strip()]
    return sorted({*committed, *working_paths})


_ALWAYS_ALLOWED_PREFIXES = (".handoff/", ".claude/", ".gitignore", "docs/playbooks/", "scripts/")


def scope_violation(item: QueueItem, baseline: str) -> list[str]:
    """Files an item may not touch, beyond a fixed allowlist of loop/repo infra.

    The allowlist matters because a human supervisor session commits live fixes to this same
    branch while the loop works (see AUTONOMOUS_QUEUE.md's rules) - those infra commits land
    after an item's baseline is pinned and must never register as that item's own scope creep.
    """
    if not item.scope:
        return []
    offenders = []
    for path in changed_files(baseline):
        if any(path.startswith(prefix) for prefix in _ALWAYS_ALLOWED_PREFIXES):
            continue
        if not any(path.startswith(prefix.rstrip("/")) for prefix in item.scope):
            offenders.append(path)
    return offenders


def run_quality_gate() -> tuple[bool, str]:
    checks = [
        ("ruff", ("ruff", "check", ".")),
        ("mypy", ("mypy", ".")),
        ("lint-imports", ("lint-imports",)),
        ("pytest", ("pytest", "tests/unit", "tests/architecture", "-q")),
        ("check_agent_docs", ("python", "scripts/check_agent_docs.py")),
    ]
    report_lines = []
    all_green = True
    for name, cmd in checks:
        result = run(*cmd)
        ok = result.returncode == 0
        all_green = all_green and ok
        report_lines.append(f"  {name}: {'OK' if ok else 'FAILED'}")
        if not ok:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-15:])
            report_lines.append(f"    last output:\n{tail}")
    return all_green, "\n".join(report_lines)


def write_halt_to_state(reason: str) -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = (
        f"\n## Autonomous loop HALT ({timestamp})\n\n"
        f"{reason}\n\n"
        "The loop stopped itself. Do not restart it against the same queue item without "
        "addressing the reason above first.\n"
    )
    with STATE_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)


def halt(reason: str) -> int:
    print(f"HALT: {reason}", file=sys.stderr)
    write_halt_to_state(reason)
    return 2


def main() -> int:
    branch = current_branch()
    if not branch.startswith("feature/") and not branch.startswith("fix/"):
        return halt(
            f"On branch `{branch}`, not a feature/fix branch. The autonomous loop must never run "
            "on main or develop. Stopped before touching anything further."
        )

    items = parse_queue()
    done_count, total_count = completed_task_count()

    if done_count >= total_count:
        gate_green, report = run_quality_gate()
        if gate_green:
            print("GOAL ACHIEVED: all queue items done, full gate green.")
            print(report)
            return 0
        print("Queue items all ticked, but the gate is not green - fix before finishing.")
        print(report)
        return 1

    current_item = items[done_count] if done_count < len(items) else None
    if current_item is None:
        return halt("Queue and tasks.md are out of sync - more done tasks than queue items exist.")

    if current_item.halt_reason:
        return halt(
            f"Next item is Item {current_item.number} — {current_item.title}, marked "
            f"HALT: {current_item.halt_reason}. Read .handoff/AUTONOMOUS_QUEUE.md for why. Do not "
            "implement it; this needs the user in Plan Mode."
        )

    gate_state = GateState.load()
    # baseline_sha marks "everything before this is pre-existing work, exempt from scope checks" -
    # bootstrapped on first run, then advanced every time an item completes, so a scope check only
    # ever looks at changes made *since the current item started*, never the branch's full history
    # back to develop (which would wrongly flag every prior commit on this feature branch forever).
    if gate_state.baseline_sha is None or gate_state.baseline_done_count != done_count:
        gate_state.baseline_sha = current_head()
        gate_state.baseline_done_count = done_count
        gate_state.save()

    offenders = scope_violation(current_item, gate_state.baseline_sha)
    if offenders:
        return halt(
            f"Item {current_item.number} declares scope {current_item.scope!r}, but changes touch "
            f"files outside it: {offenders}. Revert the out-of-scope changes or stop and ask."
        )

    gate_green, report = run_quality_gate()

    if gate_green:
        gate_state.consecutive_failures = 0
        gate_state.last_item = current_item.number
        gate_state.save()
        print(f"Item {current_item.number} gate is green but not yet ticked in tasks.md - tick it.")
        print(report)
        return 1

    if gate_state.last_item == current_item.number:
        gate_state.consecutive_failures += 1
    else:
        gate_state.last_item = current_item.number
        gate_state.consecutive_failures = 1
    gate_state.save()

    if gate_state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return halt(
            f"Item {current_item.number} — {current_item.title}: gate has failed "
            f"{gate_state.consecutive_failures} consecutive times. This looks stuck, not "
            "making progress. Stopping instead of burning the rest of the session on it."
        )

    print(f"Item {current_item.number} — {current_item.title}: gate not green yet, keep working.")
    print(report)
    return 1


if __name__ == "__main__":
    sys.exit(main())

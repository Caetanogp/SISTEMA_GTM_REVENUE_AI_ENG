#!/usr/bin/env python
"""The deterministic referee for an unattended loop session.

Conclusion can never be the model's own self-assessment - that is exactly the failure mode the
Ralph plugin's README admits to (an exact-string "completion promise" the model itself emits,
with no independent check). This script is what `/goal` actually evaluates instead: a real
condition, checked by code, not judgment.

Reads .handoff/AUTONOMOUS_QUEUE.md for the ordered list of items, their file scope, and the active
spec's tasks file. The queue, not a hard-coded spec number, selects the checklist the loop advances.

Exit codes:
  0 - every queue item done AND the full quality gate is green. Goal achieved.
  1 - more work remains, or the gate is currently red. Keep iterating.
  2 - HALT. Wrong branch, a scope violation, a hard human-required decision, or too many
      consecutive failures on the same item (anti-infinite-loop). Writes the reason to
      .handoff/STATE.md and the process should stop - not just retry.

Run: python scripts/autonomous_gate.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = ROOT / ".handoff" / "AUTONOMOUS_QUEUE.md"
STATE_FILE = ROOT / ".handoff" / "STATE.md"
GATE_STATE_FILE = ROOT / ".handoff" / ".autonomous_gate_state.json"
MAX_CONSECUTIVE_FAILURES = 5

_ITEM_HEADER = re.compile(
    r"^## Item (\d+)\s+(?:-|—)\s+(.+?)(?:\s+(?:-|—)\s+\*\*HALT: (\S+)\*\*)?$",
    re.MULTILINE,
)
_SCOPE_BLOCK = re.compile(r"^- \*\*Scope:\*\* (.+?)(?=\n- \*\*|\n\n|\Z)", re.MULTILINE | re.DOTALL)
_BACKTICK_PATH = re.compile(r"`([^`]+)`")
_REQUIRES_BLOCK = re.compile(
    r"^- \*\*Requires:\*\* (.+?)(?=\n- \*\*|\n\n|\Z)", re.MULTILINE | re.DOTALL
)
_TASK_LINE = re.compile(r"^- \[( |x)\] ", re.MULTILINE)
_CLOSES = re.compile(r"^- \*\*Closes:\*\* (\d+) tasks\.md checkboxes?$", re.MULTILINE)
_TASKS_FILE = re.compile(r"^- \*\*Tasks file:\*\* `([^`]+)`$", re.MULTILINE)


@dataclass(frozen=True)
class QueueItem:
    number: int
    title: str
    halt_reason: str | None
    scope: tuple[str, ...]
    requires: tuple[str, ...] = ()
    closes: int = 1
    """How many tasks.md checkboxes this item's own completion ticks.

    Almost always 1 (one item, one checkbox). An item can legitimately close more than one when
    a single unit of work satisfies more than one done-criterion line in tasks.md (e.g. a
    migration item that also closes the separate "indexes" line, once the migration is inspected
    and both are verified together) - declare it explicitly with a `- **Closes:** N tasks.md
    checkboxes` line in the item's body, never leave it to be inferred, since done_count alone
    can no longer be used as a direct index into the item list once any item closes more than 1.
    """


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


@dataclass(frozen=True)
class ScopeAuthorization:
    """A supervisor-issued, item-bound scope overlay stored outside the checkout."""

    branch: str
    item_number: int
    baseline_sha: str
    allowed_paths: tuple[str, ...]
    plan_sha256: str

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        branch: str,
        item_number: int,
        baseline_sha: str,
    ) -> ScopeAuthorization:
        resolved = path.resolve()
        if resolved.is_relative_to(ROOT.resolve()):
            raise ValueError("scope authorization must be stored outside the repository")
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"scope authorization is unreadable: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise ValueError("scope authorization has an unsupported format")
        if raw.get("review_status") != "approved":
            raise ValueError("scope authorization was not approved by the independent reviewer")
        if raw.get("branch") != branch:
            raise ValueError("scope authorization belongs to a different branch")
        if raw.get("item_number") != item_number:
            raise ValueError("scope authorization belongs to a different queue item")
        if raw.get("baseline_sha") != baseline_sha:
            raise ValueError("scope authorization belongs to a different item baseline")
        plan_sha256 = raw.get("plan_sha256")
        if not isinstance(plan_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_sha256):
            raise ValueError("scope authorization has an invalid plan digest")
        allowed_raw = raw.get("allowed_paths")
        if not isinstance(allowed_raw, list) or not allowed_raw:
            raise ValueError("scope authorization must contain non-empty allowed paths")
        allowed: list[str] = []
        for value in allowed_raw:
            if not isinstance(value, str):
                raise ValueError("scope authorization paths must be strings")
            normalized = value.strip().replace("\\", "/").rstrip("/")
            parts = normalized.split("/")
            if (
                not normalized
                or normalized in {".", ".."}
                or normalized.startswith("/")
                or ".." in parts
                or any(character in normalized for character in "*?[]")
            ):
                raise ValueError(f"scope authorization contains unsafe path {value!r}")
            if authorization_path_is_forbidden(normalized):
                raise ValueError(
                    f"scope authorization may not modify control-plane path {normalized!r}"
                )
            allowed.append(normalized)
        return cls(branch, item_number, baseline_sha, tuple(dict.fromkeys(allowed)), plan_sha256)


@dataclass(frozen=True)
class BaselineRolloverAuthorization:
    """An external, one-time approval to move the gate baseline to an exact commit."""

    branch: str
    previous_baseline_sha: str
    target_sha: str
    baseline_done_count: int
    changed_paths: tuple[str, ...]

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        branch: str,
        previous_baseline_sha: str,
        target_sha: str,
        baseline_done_count: int,
    ) -> BaselineRolloverAuthorization:
        resolved = path.resolve()
        if resolved.is_relative_to(ROOT.resolve()):
            raise ValueError(
                "baseline rollover authorization must be stored outside the repository"
            )
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"baseline rollover authorization is unreadable: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise ValueError("baseline rollover authorization has an unsupported format")
        expected = {
            "action": "rollover-supervisor-baseline",
            "branch": branch,
            "previous_baseline_sha": previous_baseline_sha,
            "target_sha": target_sha,
            "baseline_done_count": baseline_done_count,
        }
        for field, value in expected.items():
            if raw.get(field) != value:
                raise ValueError(f"baseline rollover authorization has a mismatched {field}")
        changed_raw = raw.get("changed_paths")
        if not isinstance(changed_raw, list) or not changed_raw:
            raise ValueError("baseline rollover authorization must list changed paths")
        changed_paths: list[str] = []
        for value in changed_raw:
            if not isinstance(value, str):
                raise ValueError("baseline rollover changed paths must be strings")
            normalized = value.strip().replace("\\", "/")
            if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError(f"baseline rollover contains unsafe path {value!r}")
            changed_paths.append(normalized)
        if len(set(changed_paths)) != len(changed_paths):
            raise ValueError("baseline rollover changed paths must be unique")
        return cls(
            branch,
            previous_baseline_sha,
            target_sha,
            baseline_done_count,
            tuple(sorted(changed_paths)),
        )


_AUTHORIZATION_FORBIDDEN_PATHS = {
    ".handoff/AUTONOMOUS_QUEUE.md",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
    "uv.lock",
}
_AUTHORIZATION_FORBIDDEN_PREFIXES = (
    ".claude/",
    ".codex/",
    ".github/",
    "docs/playbooks/",
    "infra/",
    "scripts/",
)


def authorization_path_is_forbidden(path: str) -> bool:
    normalized = path.rstrip("/")
    return normalized in _AUTHORIZATION_FORBIDDEN_PATHS or any(
        path_is_within(normalized, prefix) for prefix in _AUTHORIZATION_FORBIDDEN_PREFIXES
    )


_ROLLOVER_ALLOWED_PATHS = {
    ".codex/config.toml",
    ".codex/prompts/autonomous-loop.md",
    ".handoff/AUTONOMOUS_QUEUE.md",
    ".handoff/STATE.md",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/playbooks/autonomous-loop.md",
    "pyproject.toml",
    "scripts/autonomous_gate.py",
    "scripts/codex_loop_supervisor.py",
    "scripts/start_codex_loop.ps1",
}
_ROLLOVER_ALLOWED_PREFIXES = ("docs/decisions/", "tests/unit/scripts/")


def baseline_rollover_path_is_allowed(path: str) -> bool:
    return (
        path in _ROLLOVER_ALLOWED_PATHS
        or any(path_is_within(path, prefix) for prefix in _ROLLOVER_ALLOWED_PREFIXES)
        or (path.startswith("docs/specs/SPEC-") and path.endswith("/plan.md"))
    )


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
        requires_match = _REQUIRES_BLOCK.search(body)
        requires = tuple(_BACKTICK_PATH.findall(requires_match.group(1))) if requires_match else ()
        closes_match = _CLOSES.search(body)
        closes = int(closes_match.group(1)) if closes_match else 1
        items.append(
            QueueItem(
                number=number,
                title=title,
                halt_reason=halt_reason,
                scope=scope,
                requires=requires,
                closes=closes,
            )
        )
    return items


def active_tasks_file() -> Path:
    """Resolve the queue-selected checklist without allowing paths outside the repository."""
    text = QUEUE_FILE.read_text(encoding="utf-8")
    match = _TASKS_FILE.search(text)
    if match is None:
        raise ValueError("queue is missing its `- **Tasks file:** `...`` metadata line")

    candidate = (ROOT / match.group(1)).resolve()
    specs_root = (ROOT / "docs" / "specs").resolve()
    if candidate.parent.parent != specs_root or candidate.name != "tasks.md":
        raise ValueError("queue tasks file must be a direct `docs/specs/<spec>/tasks.md` path")
    if not candidate.is_file():
        raise ValueError(f"queue tasks file does not exist: {candidate.relative_to(ROOT)}")
    return candidate


def item_for_done_count(items: list[QueueItem], done_count: int) -> QueueItem | None:
    """The queue item whose work is next, given how many tasks.md boxes are already ticked.

    done_count is no longer a valid direct index once any item closes more than one checkbox
    (see QueueItem.closes) - walk the cumulative sum instead. Returns None once done_count covers
    every item's closes (nothing left to do), matching the old items[done_count] out-of-range case.
    """
    covered = 0
    for item in items:
        if done_count < covered + item.closes:
            return item
        covered += item.closes
    return None


def completed_task_count(tasks_file: Path) -> tuple[int, int]:
    """Return done and total checkbox counts from the active spec checklist."""
    boxes = [m.group(1) for m in _TASK_LINE.finditer(tasks_file.read_text(encoding="utf-8"))]
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


_ALWAYS_ALLOWED_PATHS = (".handoff/STATE.md",)


def path_is_within(path: str, scope: str) -> bool:
    normalized = scope.replace("\\", "/").rstrip("/")
    return path == normalized or path.startswith(f"{normalized}/")


def scope_violation(
    item: QueueItem,
    baseline: str,
    authorized_scope: tuple[str, ...] = (),
    protocol_paths: tuple[str, ...] = (),
) -> list[str]:
    """Files an item may not touch, beyond exact protocol files and approved scope.

    Only STATE.md and the active tasks file are implicit protocol writes. Queue, gate, supervisor,
    policy, and playbook edits must be in the declared item scope or a supervisor-issued overlay;
    the executor cannot silently authorize changes to its own controls.
    """
    if not item.scope:
        return []
    offenders = []
    for path in changed_files(baseline):
        if path in (*_ALWAYS_ALLOWED_PATHS, *protocol_paths):
            continue
        effective_scope = (*item.scope, *authorized_scope)
        if not any(path_is_within(path, prefix) for prefix in effective_scope):
            offenders.append(path)
    return offenders


def missing_required_evidence(item: QueueItem, baseline: str) -> list[str]:
    """Return required paths untouched since this item began.

    Quality commands establish that the current tree is healthy, not that the queue item's promised
    implementation exists. Requiring a concrete changed path prevents a clean baseline from being
    mistaken for completion and a checkbox being ticked without the declared work.
    """
    changed = changed_files(baseline)
    return [
        required
        for required in item.requires
        if not any(path_is_within(path, required) for path in changed)
    ]


def run_quality_gate(*, full: bool) -> tuple[bool, str]:
    checks = [
        ("ruff", ("ruff", "check", ".")),
        ("mypy", ("mypy", ".")),
        ("lint-imports", ("lint-imports",)),
        ("pytest", ("pytest", "tests/unit", "tests/architecture", "-q")),
        ("check_agent_docs", ("python", "scripts/check_agent_docs.py")),
    ]
    if full:
        checks.extend(
            [
                ("ruff_format", ("ruff", "format", "--check", ".")),
                ("integration", ("pytest", "tests/integration", "-q")),
                ("adversarial", ("pytest", "tests/adversarial", "-q")),
                ("evals", ("python", "-m", "evals.run", "--suite", "all")),
                ("gitleaks", ("gitleaks", "detect", "--no-git")),
            ]
        )
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


def rollover_baseline(path: Path, *, branch: str, tasks_file: Path) -> None:
    if run("git", "status", "--porcelain", "--untracked-files=all").stdout.strip():
        raise ValueError("baseline rollover requires a clean worktree")
    gate_state = GateState.load()
    if gate_state.baseline_sha is None:
        raise ValueError("baseline rollover requires an existing gate baseline")
    done_count, _ = completed_task_count(tasks_file)
    if gate_state.baseline_done_count != done_count:
        raise ValueError("baseline rollover may not cross a queue-item boundary")
    target_sha = current_head()
    authorization = BaselineRolloverAuthorization.load(
        path,
        branch=branch,
        previous_baseline_sha=gate_state.baseline_sha,
        target_sha=target_sha,
        baseline_done_count=done_count,
    )
    if (
        run("git", "merge-base", "--is-ancestor", gate_state.baseline_sha, target_sha).returncode
        != 0
    ):
        raise ValueError("baseline rollover target does not descend from the previous baseline")
    actual_paths = tuple(changed_files(gate_state.baseline_sha))
    if actual_paths != authorization.changed_paths:
        raise ValueError("baseline rollover changed paths do not match the authorized exact diff")
    disallowed = [path for path in actual_paths if not baseline_rollover_path_is_allowed(path)]
    if disallowed:
        raise ValueError(f"baseline rollover includes non-supervisor paths: {disallowed}")
    gate_state.baseline_sha = target_sha
    gate_state.baseline_done_count = done_count
    gate_state.last_item = None
    gate_state.consecutive_failures = 0
    gate_state.save()
    print(
        f"Baseline rollover approved: {authorization.previous_baseline_sha[:12]} -> "
        f"{target_sha[:12]} for {len(actual_paths)} exact supervisor-change paths."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    authorization_group = parser.add_mutually_exclusive_group()
    authorization_group.add_argument(
        "--scope-authorization",
        type=Path,
        help="Supervisor-issued scope overlay stored outside the repository",
    )
    authorization_group.add_argument(
        "--baseline-rollover-authorization",
        type=Path,
        help="External one-time approval to rebaseline an exact supervisor upgrade commit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    branch = current_branch()
    if not branch.startswith("feature/") and not branch.startswith("fix/"):
        return halt(
            f"On branch `{branch}`, not a feature/fix branch. The autonomous loop must never run "
            "on main or develop. Stopped before touching anything further."
        )

    try:
        tasks_file = active_tasks_file()
        items = parse_queue()
        done_count, total_count = completed_task_count(tasks_file)
    except ValueError as exc:
        return halt(f"Autonomous queue configuration is invalid: {exc}")

    if args.baseline_rollover_authorization is not None:
        try:
            rollover_baseline(
                args.baseline_rollover_authorization,
                branch=branch,
                tasks_file=tasks_file,
            )
        except ValueError as exc:
            return halt(f"Invalid baseline rollover authorization: {exc}")
        return 0

    if done_count >= total_count:
        gate_green, report = run_quality_gate(full=True)
        if gate_green:
            print("GOAL ACHIEVED: all queue items done, full gate green.")
            print(report)
            return 0
        print("Queue items all ticked, but the gate is not green - fix before finishing.")
        print(report)
        return 1

    current_item = item_for_done_count(items, done_count)
    if current_item is None:
        return halt(
            "Queue and tasks.md are out of sync - done_count is not covered by any item's "
            "closes range. Check every item's `- **Closes:** N tasks.md checkboxes` line adds "
            "up to tasks.md's total checkbox count for this section."
        )

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

    authorized_scope: tuple[str, ...] = ()
    if args.scope_authorization is not None:
        try:
            authorization = ScopeAuthorization.load(
                args.scope_authorization,
                branch=branch,
                item_number=current_item.number,
                baseline_sha=gate_state.baseline_sha,
            )
        except ValueError as exc:
            return halt(f"Invalid supervisor scope authorization: {exc}")
        authorized_scope = authorization.allowed_paths

    tasks_relative = tasks_file.relative_to(ROOT).as_posix()
    offenders = scope_violation(
        current_item,
        gate_state.baseline_sha,
        authorized_scope,
        (tasks_relative,),
    )
    if offenders:
        return halt(
            f"Item {current_item.number} declares scope {current_item.scope!r}, but changes touch "
            f"files outside it: {offenders}. Revert the out-of-scope changes or stop and ask."
        )

    missing_evidence = missing_required_evidence(current_item, gate_state.baseline_sha)
    if missing_evidence:
        print(
            f"Item {current_item.number} has not yet touched its required evidence paths "
            f"{missing_evidence}; keep working before considering its checkbox."
        )
        return 1

    gate_green, report = run_quality_gate(full=False)

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

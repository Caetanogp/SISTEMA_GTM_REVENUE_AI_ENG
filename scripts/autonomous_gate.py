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
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_OBSERVABILITY_SPEC = importlib.util.spec_from_file_location(
    "autonomous_gate_loop_observability", ROOT / "scripts" / "loop_observability.py"
)
if _OBSERVABILITY_SPEC is None or _OBSERVABILITY_SPEC.loader is None:
    raise RuntimeError("Could not load scripts/loop_observability.py")
loop_observability = importlib.util.module_from_spec(_OBSERVABILITY_SPEC)
sys.modules[_OBSERVABILITY_SPEC.name] = loop_observability
_OBSERVABILITY_SPEC.loader.exec_module(loop_observability)
emit_terminal_event = loop_observability.emit_terminal_event
emit_timing = loop_observability.emit_timing
QUEUE_FILE = ROOT / ".handoff" / "AUTONOMOUS_QUEUE.md"
STATE_FILE = ROOT / ".handoff" / "STATE.md"
GATE_STATE_FILE = ROOT / ".handoff" / ".autonomous_gate_state.json"
_DEFAULT_GATE_STATE_FILE = GATE_STATE_FILE
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
_CLOSES = re.compile(r"^- \*\*Closes:\*\* (\d+) tasks\.md checkbox(?:es)?$", re.MULTILINE)
_TASKS_FILE = re.compile(r"^- \*\*Tasks file:\*\* `([^`]+)`$", re.MULTILINE)
_ACTIVE_SPEC = re.compile(r"^- \*\*Active spec:\*\* `([^`]+)`$", re.MULTILINE)
_FEATURE_BRANCH = re.compile(r"^- \*\*Feature branch:\*\* `([^`]+)`$", re.MULTILINE)
_VERIFICATION_PROFILE = re.compile(r"^- \*\*Verification profile:\*\* `([^`]+)`$", re.MULTILINE)
_TEST_PATHS = re.compile(r"^- \*\*Test paths:\*\* (.+)$", re.MULTILINE)
_SAFE_REPO_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/?$")


@dataclass(frozen=True)
class VerificationProfile:
    test_roots: tuple[str, ...]
    family: str


VERIFICATION_PROFILES = {
    "python-unit": VerificationProfile(("tests/unit/", "tests/architecture/"), "python"),
    "python-integration": VerificationProfile(("tests/integration/",), "python"),
    "python-adversarial": VerificationProfile(("tests/adversarial/",), "python"),
    "docs": VerificationProfile((), "docs"),
    "web": VerificationProfile((), "web"),
    "web-bootstrap": VerificationProfile((), "web-bootstrap"),
}


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class QueueItem:
    number: int
    title: str
    halt_reason: str | None
    scope: tuple[str, ...]
    requires: tuple[str, ...] = ()
    closes: int = 1
    verification_profile: str = "python-unit"
    test_paths: tuple[str, ...] = ()
    """How many tasks.md checkboxes this item's own completion ticks.

    Almost always 1 (one item, one checkbox). An item can legitimately close more than one when
    a single unit of work satisfies more than one done-criterion line in tasks.md (e.g. a
    migration item that also closes the separate "indexes" line, once the migration is inspected
    and both are verified together) - declare it explicitly with a `- **Closes:** N tasks.md
    checkboxes` line in the item's body, never leave it to be inferred, since done_count alone
    can no longer be used as a direct index into the item list once any item closes more than 1.
    """


class GatePhase(StrEnum):
    PROGRESS_CHECKPOINT = "progress_checkpoint"
    ITEM_COMPLETION = "item_completion"
    GOAL_COMPLETION = "goal_completion"


class GateOutcome(StrEnum):
    GOAL_ACHIEVED = "goal_achieved"
    CONTINUE = "continue"
    HALT = "halt"
    INVALID = "invalid"


def gate_outcome(exit_code: int) -> GateOutcome:
    """Map process codes to the shared outcome consumed by both loop drivers."""
    return {
        0: GateOutcome.GOAL_ACHIEVED,
        1: GateOutcome.CONTINUE,
        2: GateOutcome.HALT,
    }.get(exit_code, GateOutcome.INVALID)


@dataclass
class GateState:
    last_item: int | None = None
    consecutive_failures: int = 0
    baseline_sha: str | None = None
    baseline_done_count: int = 0
    _state_file: Path | None = dataclass_field(default=None, repr=False, compare=False)
    _queue_identity: dict[str, str] | None = dataclass_field(
        default=None, repr=False, compare=False
    )

    @classmethod
    def load(cls) -> GateState:
        state_file, identity, legacy = resolve_gate_state_file()
        if state_file.exists():
            try:
                raw = json.loads(state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise ValueError(f"gate state is unreadable: {state_file.name}") from exc
            if not isinstance(raw, dict):
                raise ValueError("gate state must contain a JSON object")
            saved_identity = raw.get("queue_identity")
            if saved_identity is None:
                if identity is not None and not legacy and state_file != GATE_STATE_FILE:
                    raise ValueError("namespaced gate state is missing its queue identity")
            elif identity is not None and saved_identity != identity:
                raise ValueError("gate state belongs to a different queue identity")
            try:
                return cls(
                    last_item=raw.get("last_item"),
                    consecutive_failures=int(raw.get("consecutive_failures", 0)),
                    baseline_sha=raw.get("baseline_sha"),
                    baseline_done_count=int(raw.get("baseline_done_count", 0)),
                    _state_file=state_file,
                    _queue_identity=identity,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("gate state contains invalid field values") from exc
        return cls(_state_file=state_file, _queue_identity=identity)

    def save(self) -> None:
        state_file = self._state_file
        identity = self._queue_identity
        if state_file is None or identity is None:
            state_file, identity, _legacy = resolve_gate_state_file()
        payload: dict[str, object] = {
            "last_item": self.last_item,
            "consecutive_failures": self.consecutive_failures,
            "baseline_sha": self.baseline_sha,
            "baseline_done_count": self.baseline_done_count,
        }
        if identity is not None:
            payload["queue_identity"] = identity
        state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    "scripts/loop_observability.py",
    "scripts/start_codex_loop.ps1",
    "scripts/watch_codex_loop.ps1",
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


def _required_metadata(text: str, pattern: re.Pattern[str], label: str) -> str:
    matches = pattern.findall(text)
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0].strip():
        raise ValueError(f"queue must declare exactly one non-empty `{label}` field")
    value = matches[0]
    assert isinstance(value, str)
    return value.strip()


def queue_identity() -> tuple[str, str]:
    text = QUEUE_FILE.read_text(encoding="utf-8")
    return (
        _required_metadata(text, _ACTIVE_SPEC, "Active spec"),
        _required_metadata(text, _FEATURE_BRANCH, "Feature branch"),
    )


def parse_queue() -> list[QueueItem]:
    text = QUEUE_FILE.read_text(encoding="utf-8")
    queue_identity()
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
        if scope_match is None or not scope or requires_match is None or not requires:
            raise ValueError(f"Item {number} must declare non-empty Scope and Requires fields")
        if closes_match is None:
            raise ValueError(f"Item {number} must explicitly declare Closes")
        profile = _required_metadata(
            body, _VERIFICATION_PROFILE, f"Item {number} Verification profile"
        )
        test_paths_match = _TEST_PATHS.findall(body)
        if len(test_paths_match) != 1:
            raise ValueError(f"Item {number} must declare exactly one Test paths field")
        raw_test_paths = test_paths_match[0].strip()
        test_paths = (
            () if raw_test_paths == "none" else tuple(_BACKTICK_PATH.findall(raw_test_paths))
        )
        if raw_test_paths != "none" and not test_paths:
            raise ValueError(
                f"Item {number} Test paths must use backticked repository paths or `none`"
            )
        closes = int(closes_match.group(1))
        items.append(
            QueueItem(
                number=number,
                title=title,
                halt_reason=halt_reason,
                scope=scope,
                requires=requires,
                closes=closes,
                verification_profile=profile,
                test_paths=test_paths,
            )
        )
    if not items:
        raise ValueError("queue must declare at least one item")
    numbers = [item.number for item in items]
    if numbers != list(range(1, len(items) + 1)):
        raise ValueError(f"queue item numbers must be unique and sequential from 1; got {numbers}")
    if any(item.closes < 1 for item in items):
        raise ValueError("every queue item must close at least one tasks.md checkbox")
    return items


def active_tasks_file() -> Path:
    """Resolve the queue-selected checklist without allowing paths outside the repository."""
    text = QUEUE_FILE.read_text(encoding="utf-8")
    tasks_path = _required_metadata(text, _TASKS_FILE, "Tasks file")
    active_spec, _ = queue_identity()

    candidate = (ROOT / tasks_path).resolve()
    specs_root = (ROOT / "docs" / "specs").resolve()
    if candidate.parent.parent != specs_root or candidate.name != "tasks.md":
        raise ValueError("queue tasks file must be a direct `docs/specs/<spec>/tasks.md` path")
    if candidate.parent.name != active_spec:
        raise ValueError(
            f"queue active spec `{active_spec}` does not match tasks file directory "
            f"`{candidate.parent.name}`"
        )
    if not candidate.is_file():
        raise ValueError(f"queue tasks file does not exist: {candidate.relative_to(ROOT)}")
    return candidate


def _identity_from_queue_text(text: str) -> tuple[str, str, str]:
    spec = _required_metadata(text, _ACTIVE_SPEC, "Active spec")
    branch = _required_metadata(text, _FEATURE_BRANCH, "Feature branch")
    tasks = _required_metadata(text, _TASKS_FILE, "Tasks file")
    return spec, branch, tasks


def _legacy_state_matches_identity(
    state_file: Path,
    identity: dict[str, str],
) -> bool:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(state, dict):
        return False
    saved_identity = state.get("queue_identity")
    if saved_identity is not None:
        return bool(saved_identity == identity)
    baseline = state.get("baseline_sha")
    if not isinstance(baseline, str) or not baseline:
        return False
    queue_result = run("git", "show", f"{baseline}:.handoff/AUTONOMOUS_QUEUE.md")
    if queue_result.returncode != 0:
        return False
    try:
        spec, branch, tasks = _identity_from_queue_text(queue_result.stdout)
    except ValueError:
        try:
            tasks = _required_metadata(queue_result.stdout, _TASKS_FILE, "Tasks file")
        except ValueError:
            return False
        state_result = run("git", "show", f"{baseline}:.handoff/STATE.md")
        if state_result.returncode != 0:
            return False
        branch_match = re.search(r"^branch:\s*([^\r\n]+)$", state_result.stdout, re.MULTILINE)
        spec_match = re.search(r"^spec:\s*([^\r\n]+)$", state_result.stdout, re.MULTILINE)
        if branch_match is None or spec_match is None:
            return False
        branch = branch_match.group(1).strip().strip("'\"")
        spec = spec_match.group(1).strip().strip("'\"")
        if Path(tasks).parent.name != spec:
            return False
    return identity == {"active_spec": spec, "branch": branch, "tasks_file": tasks}


def resolve_gate_state_file() -> tuple[Path, dict[str, str] | None, bool]:
    """Resolve state by validated queue identity, retaining a matching legacy baseline."""
    if GATE_STATE_FILE != _DEFAULT_GATE_STATE_FILE:
        return GATE_STATE_FILE, None, True

    spec, expected_branch = queue_identity()
    branch = current_branch()
    if branch != expected_branch:
        raise ValueError(
            f"queue feature branch `{expected_branch}` does not match current branch `{branch}`"
        )
    tasks_file = active_tasks_file()
    identity = {
        "active_spec": spec,
        "branch": branch,
        "tasks_file": tasks_file.relative_to(ROOT).as_posix(),
    }
    identity_bytes = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(identity_bytes).hexdigest()[:20]
    namespaced = ROOT / ".handoff" / f".autonomous_gate_state.{digest}.json"
    if namespaced.exists():
        return namespaced, identity, False

    legacy = ROOT / ".handoff" / ".autonomous_gate_state.json"
    if legacy.exists() and _legacy_state_matches_identity(legacy, identity):
        return legacy, identity, True
    return namespaced, identity, False


def validate_queue(items: list[QueueItem], tasks_file: Path, branch: str) -> None:
    active_spec, expected_branch = queue_identity()
    if expected_branch != branch:
        raise ValueError(
            f"queue is bound to branch `{expected_branch}`, but current branch is `{branch}`"
        )
    if tasks_file.parent.name != active_spec:
        raise ValueError("queue active spec identity does not match the resolved tasks file")

    bootstrap_items = [item for item in items if item.verification_profile == "web-bootstrap"]
    has_web_bootstrap = bool(bootstrap_items)
    if has_web_bootstrap:
        if len(bootstrap_items) != 1 or items[0].verification_profile != "web-bootstrap":
            raise ValueError("web-bootstrap profile is allowed only on queue item 1")
        if not any(path_is_within("apps/web/package.json", scope) for scope in items[0].scope):
            raise ValueError("Item 1 web-bootstrap scope must include `apps/web/`")

    for item in items:
        profile = VERIFICATION_PROFILES.get(item.verification_profile)
        if profile is None:
            raise ValueError(
                f"Item {item.number} declares unsupported verification profile "
                f"`{item.verification_profile}`"
            )
        roots = profile.test_roots
        if roots and not item.test_paths:
            raise ValueError(f"Item {item.number} profile requires at least one test path")
        if not roots and item.test_paths:
            raise ValueError(f"Item {item.number} profile does not accept pytest test paths")
        for test_path in item.test_paths:
            normalized = test_path.replace("\\", "/")
            parts = normalized.rstrip("/").split("/")
            if (
                not _SAFE_REPO_PATH.fullmatch(normalized)
                or normalized.startswith("/")
                or any(part in {".", ".."} for part in parts)
            ):
                raise ValueError(f"Item {item.number} contains unsafe test path `{test_path}`")
            if not any(path_is_within(normalized, root) for root in roots):
                raise ValueError(
                    f"Item {item.number} test path `{test_path}` is outside profile roots {roots}"
                )
            resolved_path = (ROOT / normalized).resolve()
            if not resolved_path.is_relative_to(ROOT.resolve()):
                raise ValueError(
                    f"Item {item.number} test path escapes the repository: `{test_path}`"
                )
            if not resolved_path.exists():
                raise ValueError(f"Item {item.number} test path does not exist: `{test_path}`")
        if profile.family == "web-bootstrap":
            continue
        if profile.family == "web" and has_web_bootstrap:
            continue
        if profile.family == "web":
            _validate_profile_configuration("web", item.number)

    done_total = sum(item.closes for item in items)
    actual_total = completed_task_count(tasks_file)[1]
    if done_total != actual_total:
        raise ValueError(
            f"queue closes {done_total} task checkboxes, but tasks file contains {actual_total}"
        )


def _validate_profile_configuration(profile_name: str, item_number: int) -> None:
    if profile_name != "web":
        return
    web_root = ROOT / "apps" / "web"
    package_path = web_root / "package.json"
    if not package_path.is_file():
        raise ValueError(f"Item {item_number} web profile requires `apps/web/package.json`")
    try:
        package_data = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Item {item_number} web package manifest is invalid: {exc}") from exc
    scripts = package_data.get("scripts") if isinstance(package_data, dict) else None
    if not isinstance(scripts, dict) or any(
        not isinstance(scripts.get(name), str) or not scripts[name].strip()
        for name in ("lint", "test", "build")
    ):
        raise ValueError(f"Item {item_number} web profile requires lint, test, and build scripts")
    if not any(
        (web_root / name).is_file() for name in ("package-lock.json", "npm-shrinkwrap.json")
    ):
        raise ValueError(f"Item {item_number} web profile requires an npm lockfile")


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


def validate_bootstrap_baseline(
    items: list[QueueItem], done_count: int, baseline_sha: str | None
) -> None:
    """Require a new bootstrap queue to verify its first item instead of adopting it as baseline."""
    if (
        baseline_sha is None
        and items
        and items[0].verification_profile == "web-bootstrap"
        and done_count >= items[0].closes
    ):
        raise ValueError(
            "web-bootstrap item 1 must remain unchecked when initializing the gate baseline; "
            "its completion must pass the required web checks"
        )


def completed_task_count(tasks_file: Path) -> tuple[int, int]:
    """Return done and total checkbox counts from the active spec checklist."""
    boxes = [m.group(1) for m in _TASK_LINE.finditer(tasks_file.read_text(encoding="utf-8"))]
    return sum(1 for b in boxes if b == "x"), len(boxes)


def select_phase(done_count: int, total_count: int, baseline_done_count: int) -> GatePhase:
    """Derive the verification phase from trusted task and saved-baseline state."""
    if done_count > baseline_done_count:
        return GatePhase.ITEM_COMPLETION
    if done_count == total_count:
        return GatePhase.GOAL_COMPLETION
    return GatePhase.PROGRESS_CHECKPOINT


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


def run_progress_checkpoint() -> tuple[bool, str]:
    """Run inexpensive diff hygiene checks without invoking repository-wide suites."""
    phase_started = time.perf_counter()
    reports: list[str] = []
    all_green = True
    for label, command in (
        ("unstaged diff check", ("git", "diff", "--check")),
        ("staged diff check", ("git", "diff", "--cached", "--check")),
    ):
        check_started = time.perf_counter()
        try:
            result = run(*command)
        except (OSError, subprocess.SubprocessError):
            emit_timing(
                source="gate",
                phase="progress_checkpoint",
                check=label,
                started_at=check_started,
                outcome="error",
            )
            emit_timing(
                source="gate",
                phase="progress_checkpoint",
                check="phase_total",
                started_at=phase_started,
                outcome="error",
            )
            raise
        emit_timing(
            source="gate",
            phase="progress_checkpoint",
            check=label,
            started_at=check_started,
            outcome="passed" if result.returncode == 0 else "failed",
        )
        ok = result.returncode == 0
        all_green = all_green and ok
        reports.append(f"  {label}: {'OK' if ok else 'FAILED'}")
        if not ok:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-15:])
            reports.append(f"    last output:\n{tail}")
    emit_timing(
        source="gate",
        phase="progress_checkpoint",
        check="phase_total",
        started_at=phase_started,
        outcome="passed" if all_green else "failed",
    )
    return all_green, "\n".join(reports)


def _safe_python_files(changed_paths: list[str]) -> list[str]:
    python_files: list[str] = []
    for changed_path in changed_paths:
        normalized = changed_path.replace("\\", "/")
        parts = normalized.split("/")
        if normalized.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError(
                f"changed path is not a safe repository-relative path: {changed_path!r}"
            )
        if not normalized.endswith(".py"):
            continue
        resolved = (ROOT / normalized).resolve()
        if not resolved.is_relative_to(ROOT.resolve()):
            raise ValueError(f"changed Python path escapes the repository: {changed_path!r}")
        if resolved.is_file():
            python_files.append(normalized)
    return python_files


def build_verification_commands(
    profile_name: str,
    test_paths: tuple[str, ...],
    changed_paths: list[str],
) -> list[VerificationCommand]:
    """Build argv only from the fixed profile registry and validated repository paths."""
    profile = VERIFICATION_PROFILES.get(profile_name)
    if profile is None:
        raise ValueError(f"unsupported verification profile `{profile_name}`")

    if profile.family in {"web", "web-bootstrap"}:
        _validate_profile_configuration("web", 0)
        web_root = ROOT / "apps" / "web"
        return [
            VerificationCommand("web lint", ("npm", "run", "lint"), web_root),
            VerificationCommand("web tests", ("npm", "test"), web_root),
            VerificationCommand("web build", ("npm", "run", "build"), web_root),
        ]

    if profile.family == "docs":
        return [
            VerificationCommand("unstaged diff check", ("git", "diff", "--check"), ROOT),
            VerificationCommand("staged diff check", ("git", "diff", "--cached", "--check"), ROOT),
            VerificationCommand("docs check", ("python", "scripts/check_agent_docs.py"), ROOT),
        ]

    python_files = _safe_python_files(changed_paths)
    commands: list[VerificationCommand] = []
    if python_files:
        commands.append(
            VerificationCommand("ruff changed Python", ("ruff", "check", "--", *python_files), ROOT)
        )
    python_app_paths = ("packages/", "apps/api/", "apps/worker/", "apps/mcp/")
    if any(
        path.endswith(".py") and any(path_is_within(path, root) for root in python_app_paths)
        for path in changed_paths
    ):
        commands.extend(
            (
                VerificationCommand("mypy", ("mypy", "."), ROOT),
                VerificationCommand("lint-imports", ("lint-imports",), ROOT),
            )
        )
    commands.append(VerificationCommand("pytest", ("pytest", *test_paths, "-q"), ROOT))
    return commands


def run_item_verification(item: QueueItem, baseline: str) -> tuple[bool, str]:
    phase_started = time.perf_counter()
    try:
        commands = build_verification_commands(
            item.verification_profile,
            item.test_paths,
            changed_files(baseline),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        emit_timing(
            source="gate",
            phase="item_completion",
            check="phase_total",
            started_at=phase_started,
            outcome="error",
        )
        raise
    report_lines: list[str] = []
    all_green = True
    for check in commands:
        check_started = time.perf_counter()
        try:
            result = run(*check.argv, cwd=check.cwd)
        except (OSError, subprocess.SubprocessError):
            emit_timing(
                source="gate",
                phase="item_completion",
                check=check.name,
                started_at=check_started,
                outcome="error",
            )
            emit_timing(
                source="gate",
                phase="item_completion",
                check="phase_total",
                started_at=phase_started,
                outcome="error",
            )
            raise
        emit_timing(
            source="gate",
            phase="item_completion",
            check=check.name,
            started_at=check_started,
            outcome="passed" if result.returncode == 0 else "failed",
        )
        ok = result.returncode == 0
        all_green = all_green and ok
        report_lines.append(f"  {check.name}: {'OK' if ok else 'FAILED'}")
        if not ok:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-15:])
            report_lines.append(f"    last output:\n{tail}")
    emit_timing(
        source="gate",
        phase="item_completion",
        check="phase_total",
        started_at=phase_started,
        outcome="passed" if all_green else "failed",
    )
    return all_green, "\n".join(report_lines)


def run_quality_gate(*, full: bool) -> tuple[bool, str]:
    phase_started = time.perf_counter()
    phase_name = "goal_completion" if full else "quality_gate"
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
        check_started = time.perf_counter()
        try:
            result = run(*cmd)
        except (OSError, subprocess.SubprocessError):
            emit_timing(
                source="gate",
                phase=phase_name,
                check=name,
                started_at=check_started,
                outcome="error",
            )
            emit_timing(
                source="gate",
                phase=phase_name,
                check="phase_total",
                started_at=phase_started,
                outcome="error",
            )
            raise
        emit_timing(
            source="gate",
            phase=phase_name,
            check=name,
            started_at=check_started,
            outcome="passed" if result.returncode == 0 else "failed",
        )
        ok = result.returncode == 0
        all_green = all_green and ok
        report_lines.append(f"  {name}: {'OK' if ok else 'FAILED'}")
        if not ok:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-15:])
            report_lines.append(f"    last output:\n{tail}")
    emit_timing(
        source="gate",
        phase=phase_name,
        check="phase_total",
        started_at=phase_started,
        outcome="passed" if all_green else "failed",
    )
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
    if os.environ.get("CODEX_LOOP_SUPERVISED") != "1":
        event_type = "human_required" if "HUMAN_REQUIRED" in reason else "halt"
        emit_terminal_event(event_type, source="gate", exit_code=2)
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
        validate_queue(items, tasks_file, branch)
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

    try:
        gate_state = GateState.load()
    except ValueError as exc:
        return halt(f"Autonomous gate state is invalid: {exc}")
    try:
        validate_bootstrap_baseline(items, done_count, gate_state.baseline_sha)
    except ValueError as exc:
        return halt(str(exc))
    if gate_state.baseline_sha is None:
        gate_state.baseline_sha = current_head()
        gate_state.baseline_done_count = done_count
        gate_state.save()
    elif done_count < gate_state.baseline_done_count:
        return halt(
            f"tasks.md completion count regressed from saved baseline count "
            f"{gate_state.baseline_done_count} to {done_count}; refusing to move the baseline."
        )
    phase = select_phase(done_count, total_count, gate_state.baseline_done_count)

    if phase is GatePhase.ITEM_COMPLETION:
        completed_item = item_for_done_count(items, gate_state.baseline_done_count)
        if completed_item is None:
            return halt(
                "Saved gate baseline count is not covered by any queue item; refusing to "
                "validate or advance the item baseline."
            )
        expected_done_count = gate_state.baseline_done_count + completed_item.closes
        if done_count != expected_done_count:
            return halt(
                f"tasks.md advanced from {gate_state.baseline_done_count} to {done_count}, but "
                f"Item {completed_item.number} closes {completed_item.closes} checkbox(es); "
                "validate one queue item at a time. The saved baseline is unchanged."
            )
        if completed_item.halt_reason:
            return halt(
                f"Item {completed_item.number} — {completed_item.title} is marked "
                f"HALT: {completed_item.halt_reason}; its completion cannot be accepted."
            )

        completed_authorized_scope: tuple[str, ...] = ()
        if args.scope_authorization is not None:
            try:
                authorization = ScopeAuthorization.load(
                    args.scope_authorization,
                    branch=branch,
                    item_number=completed_item.number,
                    baseline_sha=gate_state.baseline_sha,
                )
            except ValueError as exc:
                return halt(f"Invalid supervisor scope authorization: {exc}")
            completed_authorized_scope = authorization.allowed_paths

        tasks_relative = tasks_file.relative_to(ROOT).as_posix()
        offenders = scope_violation(
            completed_item,
            gate_state.baseline_sha,
            completed_authorized_scope,
            (tasks_relative,),
        )
        if offenders:
            return halt(
                f"Completed Item {completed_item.number} declares scope "
                f"{completed_item.scope!r}, but changes since its saved baseline touch files "
                f"outside it: {offenders}. The baseline is unchanged."
            )

        missing_evidence = missing_required_evidence(completed_item, gate_state.baseline_sha)
        if missing_evidence:
            return halt(
                f"Completed Item {completed_item.number} is missing required evidence paths "
                f"{missing_evidence}; its checkbox cannot be accepted and the baseline is "
                "unchanged."
            )

        try:
            gate_green, report = run_item_verification(completed_item, gate_state.baseline_sha)
        except ValueError as exc:
            return halt(f"Item {completed_item.number} verification profile is invalid: {exc}")
        if not gate_green:
            return halt(
                f"Completed Item {completed_item.number} failed its verification profile; "
                f"the saved baseline is unchanged.\n{report}"
            )

        if run("git", "status", "--porcelain", "--untracked-files=all").stdout.strip():
            print(
                f"Item {completed_item.number} verification passed, but the worktree is not "
                "clean; commit the verified item before baseline advancement."
            )
            print(report)
            return 1

        final_report: str | None = None
        if done_count >= total_count:
            final_gate_green, final_report = run_quality_gate(full=True)
            if not final_gate_green:
                return halt(
                    f"Final verification failed after Item {completed_item.number}; the saved "
                    f"baseline is unchanged.\n{final_report}"
                )

        gate_state.baseline_sha = current_head()
        gate_state.baseline_done_count = done_count
        gate_state.last_item = None
        gate_state.consecutive_failures = 0
        gate_state.save()
        print(
            f"Item {completed_item.number} completion verified; baseline advanced to "
            f"{gate_state.baseline_sha[:12]}."
        )
        if done_count < total_count:
            print(report)
            return 1
        if os.environ.get("CODEX_LOOP_SUPERVISED") != "1":
            emit_terminal_event("goal_achieved", source="gate", exit_code=0)
        print("GOAL ACHIEVED: all queue items done, full gate green.")
        print(final_report)
        return 0

    if phase is GatePhase.GOAL_COMPLETION:
        gate_green, report = run_quality_gate(full=True)
        if gate_green:
            if os.environ.get("CODEX_LOOP_SUPERVISED") != "1":
                emit_terminal_event("goal_achieved", source="gate", exit_code=0)
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

    gate_green, report = run_progress_checkpoint()

    if gate_green:
        gate_state.consecutive_failures = 0
        gate_state.last_item = current_item.number
        gate_state.save()
        print(f"Progress checkpoint passed for Item {current_item.number}; keep working.")
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

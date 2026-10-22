"""Safe timing and terminal-event records for unattended development loops."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

type EventType = Literal["halt", "human_required", "goal_achieved"]
type Outcome = Literal["passed", "failed", "error"]

EVENT_PREFIX = "CODEX_LOOP_EVENT "
TIMING_PREFIX = "CODEX_LOOP_TIMING "
EVENTS_FILENAME = "codex-revops-loop-events.jsonl"
TIMINGS_FILENAME = "codex-revops-loop-timings.jsonl"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASES = {
    "progress_checkpoint",
    "item_completion",
    "goal_completion",
    "quality_gate",
    "executor_turn",
    "architecture_turn",
}
_CHECKS = {
    "phase_total",
    "unstaged diff check",
    "staged diff check",
    "ruff changed Python",
    "mypy",
    "lint-imports",
    "pytest",
    "web lint",
    "web tests",
    "web build",
    "docs check",
    "ruff",
    "ruff_format",
    "integration",
    "adversarial",
    "evals",
    "gitleaks",
    "check_agent_docs",
    "executor",
    "architecture_plan",
    "architecture_review",
}


def _external_path(filename: str) -> Path:
    configured = os.environ.get("CODEX_LOOP_OBSERVABILITY_DIR")
    directory = Path(configured).expanduser() if configured else Path(tempfile.gettempdir())
    resolved_directory = directory.resolve()
    if resolved_directory == _REPO_ROOT or _REPO_ROOT in resolved_directory.parents:
        raise ValueError("loop observability directory must be outside the repository")
    resolved_directory.mkdir(parents=True, exist_ok=True)
    resolved_path = (resolved_directory / filename).resolve()
    if resolved_path == _REPO_ROOT or _REPO_ROOT in resolved_path.parents:
        raise ValueError("loop observability file must be outside the repository")
    return resolved_path


def _append_record(path: Path, payload: dict[str, object], prefix: str) -> None:
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    print(f"{prefix}{line}", flush=True)
    try:
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
    except OSError as exc:
        print(f"LOOP_OBSERVABILITY_WRITE_FAILED: {type(exc).__name__}", file=sys.stderr)


def emit_timing(
    *,
    source: Literal["gate", "supervisor"],
    phase: str,
    check: str,
    started_at: float,
    outcome: Outcome,
) -> None:
    """Record only fixed operational metadata; never pass command output or model text."""
    if source not in {"gate", "supervisor"} or phase not in _PHASES or check not in _CHECKS:
        raise ValueError("unsupported loop timing metadata")
    if outcome not in {"passed", "failed", "error"}:
        raise ValueError("unsupported loop timing outcome")
    payload: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "source": source,
        "phase": phase,
        "check": check,
        "elapsed_seconds": round(max(0.0, time.perf_counter() - started_at), 3),
        "outcome": outcome,
    }
    try:
        path = _external_path(TIMINGS_FILENAME)
    except (OSError, ValueError) as exc:
        print(f"LOOP_OBSERVABILITY_PATH_FAILED: {type(exc).__name__}", file=sys.stderr)
        path = None
    if path is None:
        print(f"{TIMING_PREFIX}{json.dumps(payload, sort_keys=True)}", flush=True)
    else:
        _append_record(path, payload, TIMING_PREFIX)


def emit_terminal_event(
    event_type: EventType,
    *,
    source: Literal["gate", "supervisor"],
    item_number: int | None = None,
    exit_code: int | None = None,
) -> str:
    """Emit a finite, content-free event suitable for a read-only local watcher."""
    if event_type not in {"halt", "human_required", "goal_achieved"}:
        raise ValueError("unsupported loop terminal event")
    if source not in {"gate", "supervisor"}:
        raise ValueError("unsupported loop event source")
    if item_number is not None and item_number < 1:
        raise ValueError("loop event item number must be positive")
    if exit_code not in {None, 0, 2}:
        raise ValueError("loop terminal event exit code must be 0 or 2")
    event_id = str(uuid.uuid4())
    payload: dict[str, object] = {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "source": source,
    }
    if item_number is not None:
        payload["item_number"] = item_number
    if exit_code is not None:
        payload["exit_code"] = exit_code
    try:
        path = _external_path(EVENTS_FILENAME)
    except (OSError, ValueError) as exc:
        print(f"LOOP_OBSERVABILITY_PATH_FAILED: {type(exc).__name__}", file=sys.stderr)
        path = None
    if path is None:
        print(f"{EVENT_PREFIX}{json.dumps(payload, sort_keys=True)}", flush=True)
    else:
        _append_record(path, payload, EVENT_PREFIX)
    return event_id

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import cast

import pytest

from scripts import loop_observability as observability


def test_timing_record_is_allowlisted_and_written_outside_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CODEX_LOOP_OBSERVABILITY_DIR", str(tmp_path))

    observability.emit_timing(
        source="gate",
        phase="progress_checkpoint",
        check="phase_total",
        started_at=time.perf_counter(),
        outcome="passed",
    )

    record = json.loads((tmp_path / observability.TIMINGS_FILENAME).read_text(encoding="utf-8"))
    assert set(record) == {
        "timestamp",
        "source",
        "phase",
        "check",
        "elapsed_seconds",
        "outcome",
    }
    assert record["elapsed_seconds"] >= 0
    assert json.loads(capsys.readouterr().out.removeprefix(observability.TIMING_PREFIX)) == record


def test_timing_rejects_untrusted_free_text_fields() -> None:
    with pytest.raises(ValueError, match="unsupported loop timing metadata"):
        observability.emit_timing(
            source="gate",
            phase="user prompt text",
            check="phase_total",
            started_at=time.perf_counter(),
            outcome="passed",
        )


def test_terminal_event_contains_only_finite_operational_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CODEX_LOOP_OBSERVABILITY_DIR", str(tmp_path))

    event_id = observability.emit_terminal_event(
        "human_required", source="supervisor", item_number=4, exit_code=2
    )

    record = json.loads((tmp_path / observability.EVENTS_FILENAME).read_text(encoding="utf-8"))
    assert record["event_id"] == event_id
    assert record["event_type"] == "human_required"
    assert record["item_number"] == 4
    assert set(record) == {
        "event_id",
        "event_type",
        "timestamp",
        "source",
        "item_number",
        "exit_code",
    }
    assert observability.EVENT_PREFIX in capsys.readouterr().out


def test_event_rejects_arbitrary_type_or_exit_code() -> None:
    with pytest.raises(ValueError, match="unsupported loop terminal event"):
        observability.emit_terminal_event(
            cast(observability.EventType, "executor_output"), source="supervisor"
        )
    with pytest.raises(ValueError, match="exit code must be 0 or 2"):
        observability.emit_terminal_event("halt", source="gate", exit_code=1)


def test_observability_directory_cannot_be_inside_checkout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CODEX_LOOP_OBSERVABILITY_DIR", str(observability._REPO_ROOT))

    observability.emit_terminal_event("halt", source="gate")

    captured = capsys.readouterr()
    assert "CODEX_LOOP_EVENT " in captured.out
    assert "LOOP_OBSERVABILITY_PATH_FAILED: ValueError" in captured.err


def test_windows_watcher_mocks_notifications_and_deduplicates_events(tmp_path: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for watcher smoke coverage")

    event_file = tmp_path / "events.jsonl"
    seen_file = tmp_path / "seen.json"
    watcher = Path(__file__).resolve().parents[3] / "scripts" / "watch_codex_loop.ps1"
    event_file.write_text(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "halt",
                "timestamp": "2026-10-22T00:00:00Z",
                "source": "gate",
                "item_number": 3,
                "exit_code": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    command = [
        shell,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(watcher),
        "-EventPath",
        str(event_file),
        "-SeenPath",
        str(seen_file),
        "-RunOnce",
        "-NoNotify",
        "-ReplayExisting",
    ]

    first = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    second = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)

    assert first.returncode == 0, first.stderr
    assert first.stdout.count("NOTIFICATION MOCK:") == 1
    assert "Item 3." in first.stdout
    assert "Watcher stopped." in first.stdout
    assert second.returncode == 0, second.stderr
    assert "NOTIFICATION MOCK:" not in second.stdout


def test_windows_watcher_ignores_stale_events_on_first_start(tmp_path: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for watcher smoke coverage")

    event_file = tmp_path / "old-events.jsonl"
    seen_file = tmp_path / "old-seen.json"
    watcher = Path(__file__).resolve().parents[3] / "scripts" / "watch_codex_loop.ps1"
    event_file.write_text(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "halt",
                "timestamp": "2026-10-21T00:00:00Z",
                "source": "gate",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(watcher),
            "-EventPath",
            str(event_file),
            "-SeenPath",
            str(seen_file),
            "-RunOnce",
            "-NoNotify",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Ignored 1 pre-existing event(s)" in result.stdout
    assert "NOTIFICATION MOCK:" not in result.stdout

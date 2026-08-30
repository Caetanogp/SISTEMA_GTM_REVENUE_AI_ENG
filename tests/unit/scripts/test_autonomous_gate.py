"""Regression tests for active-spec selection in the autonomous gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_GATE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autonomous_gate.py"
_SPEC = importlib.util.spec_from_file_location("autonomous_gate_under_test", _GATE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gate
_SPEC.loader.exec_module(gate)


def _write_queue(root: Path, tasks_path: str) -> None:
    (root / ".handoff").mkdir(parents=True)
    (root / ".handoff" / "AUTONOMOUS_QUEUE.md").write_text(
        f"# Queue\n\n- **Tasks file:** `{tasks_path}`\n",
        encoding="utf-8",
    )


def test_active_tasks_file_uses_queue_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks = tmp_path / "docs" / "specs" / "SPEC-999-example" / "tasks.md"
    tasks.parent.mkdir(parents=True)
    tasks.write_text("- [ ] first\n- [x] second\n", encoding="utf-8")
    _write_queue(tmp_path, "docs/specs/SPEC-999-example/tasks.md")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "QUEUE_FILE", tmp_path / ".handoff" / "AUTONOMOUS_QUEUE.md")

    assert gate.active_tasks_file() == tasks
    assert gate.completed_task_count(tasks) == (1, 2)


@pytest.mark.parametrize(
    "tasks_path",
    [".handoff/STATE.md", "docs/specs/tasks.md", "docs/specs/SPEC-999-example/plan.md"],
)
def test_active_tasks_file_rejects_unsafe_or_invalid_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tasks_path: str
) -> None:
    _write_queue(tmp_path, tasks_path)
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "QUEUE_FILE", tmp_path / ".handoff" / "AUTONOMOUS_QUEUE.md")

    with pytest.raises(ValueError, match="tasks file"):
        gate.active_tasks_file()


def test_missing_required_evidence_requires_every_declared_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = gate.QueueItem(
        number=3,
        title="application contracts",
        halt_reason=None,
        scope=("packages/core/revops/application/",),
        requires=("packages/core/revops/application/", "tests/unit/application/"),
    )
    monkeypatch.setattr(
        gate,
        "changed_files",
        lambda _baseline: ["packages/core/revops/application/dto.py"],
    )

    assert gate.missing_required_evidence(item, "baseline") == ["tests/unit/application/"]

"""Regression tests for active-spec selection in the autonomous gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _write_scope_authorization(
    path: Path,
    *,
    branch: str = "feature/test",
    item_number: int = 7,
    baseline_sha: str = "a" * 40,
    allowed_paths: list[str] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "branch": branch,
                "item_number": item_number,
                "baseline_sha": baseline_sha,
                "allowed_paths": allowed_paths or ["packages/core/revops/application/"],
                "plan_sha256": "b" * 64,
                "architect_model": "gpt-5.6-sol",
                "architecture_effort": "xhigh",
                "review_status": "approved",
            }
        ),
        encoding="utf-8",
    )


def test_scope_authorization_loads_matching_external_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    monkeypatch.setattr(gate, "ROOT", repository)
    authorization_path = tmp_path / "authorization.json"
    _write_scope_authorization(authorization_path)

    authorization = gate.ScopeAuthorization.load(
        authorization_path,
        branch="feature/test",
        item_number=7,
        baseline_sha="a" * 40,
    )

    assert authorization.allowed_paths == ("packages/core/revops/application",)
    assert authorization.plan_sha256 == "b" * 64


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"branch": "feature/other"}, "different branch"),
        ({"item_number": 8}, "different queue item"),
        ({"baseline_sha": "c" * 40}, "different item baseline"),
        ({"allowed_paths": ["../outside"]}, "unsafe path"),
        ({"allowed_paths": ["packages/**"]}, "unsafe path"),
        ({"allowed_paths": ["scripts/"]}, "control-plane path"),
        ({"allowed_paths": ["AGENTS.md"]}, "control-plane path"),
    ],
)
def test_scope_authorization_rejects_mismatched_or_unsafe_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    override: dict[str, object],
    match: str,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    monkeypatch.setattr(gate, "ROOT", repository)
    authorization_path = tmp_path / "authorization.json"
    _write_scope_authorization(authorization_path)
    raw = json.loads(authorization_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    raw.update(override)
    authorization_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        gate.ScopeAuthorization.load(
            authorization_path,
            branch="feature/test",
            item_number=7,
            baseline_sha="a" * 40,
        )


def _write_rollover_authorization(
    path: Path,
    *,
    changed_paths: list[str],
    previous_baseline_sha: str = "a" * 40,
    target_sha: str = "c" * 40,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "action": "rollover-supervisor-baseline",
                "branch": "feature/test",
                "previous_baseline_sha": previous_baseline_sha,
                "target_sha": target_sha,
                "baseline_done_count": 13,
                "changed_paths": changed_paths,
            }
        ),
        encoding="utf-8",
    )


def test_rollover_baseline_requires_exact_external_authorization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tasks_file = repository / "tasks.md"
    tasks_file.write_text("".join(["- [x] done\n"] * 13 + ["- [ ] next\n"]), encoding="utf-8")
    state_file = repository / ".handoff" / ".autonomous_gate_state.json"
    state_file.parent.mkdir()
    state_file.write_text(
        json.dumps(
            {
                "last_item": 6,
                "consecutive_failures": 0,
                "baseline_sha": "a" * 40,
                "baseline_done_count": 13,
            }
        ),
        encoding="utf-8",
    )
    authorization_path = tmp_path / "rollover.json"
    changed_paths = ["scripts/codex_loop_supervisor.py", "tests/unit/scripts/test_supervisor.py"]
    _write_rollover_authorization(authorization_path, changed_paths=changed_paths)
    monkeypatch.setattr(gate, "ROOT", repository)
    monkeypatch.setattr(gate, "GATE_STATE_FILE", state_file)
    monkeypatch.setattr(gate, "current_head", lambda: "c" * 40)
    monkeypatch.setattr(gate, "changed_files", lambda _baseline: changed_paths)
    monkeypatch.setattr(
        gate,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="", stderr="", returncode=0),
    )

    gate.rollover_baseline(
        authorization_path,
        branch="feature/test",
        tasks_file=tasks_file,
    )

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["baseline_sha"] == "c" * 40
    assert saved["baseline_done_count"] == 13


def test_rollover_baseline_rejects_non_supervisor_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tasks_file = repository / "tasks.md"
    tasks_file.write_text("".join(["- [x] done\n"] * 13 + ["- [ ] next\n"]), encoding="utf-8")
    state_file = repository / "gate-state.json"
    state_file.write_text(
        json.dumps({"baseline_sha": "a" * 40, "baseline_done_count": 13}),
        encoding="utf-8",
    )
    authorization_path = tmp_path / "rollover.json"
    changed_paths = ["apps/api/routes/accounts.py"]
    _write_rollover_authorization(authorization_path, changed_paths=changed_paths)
    monkeypatch.setattr(gate, "ROOT", repository)
    monkeypatch.setattr(gate, "GATE_STATE_FILE", state_file)
    monkeypatch.setattr(gate, "current_head", lambda: "c" * 40)
    monkeypatch.setattr(gate, "changed_files", lambda _baseline: changed_paths)
    monkeypatch.setattr(
        gate,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="", stderr="", returncode=0),
    )

    with pytest.raises(ValueError, match="non-supervisor paths"):
        gate.rollover_baseline(
            authorization_path,
            branch="feature/test",
            tasks_file=tasks_file,
        )


def test_scope_authorization_must_be_outside_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    authorization_path = repository / "authorization.json"
    _write_scope_authorization(authorization_path)
    monkeypatch.setattr(gate, "ROOT", repository)

    with pytest.raises(ValueError, match="outside the repository"):
        gate.ScopeAuthorization.load(
            authorization_path,
            branch="feature/test",
            item_number=7,
            baseline_sha="a" * 40,
        )


def test_scope_violation_accepts_only_the_authorized_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = gate.QueueItem(
        number=7,
        title="API",
        halt_reason=None,
        scope=("apps/api/",),
    )
    monkeypatch.setattr(
        gate,
        "changed_files",
        lambda _baseline: [
            "apps/api/routes/deduplication.py",
            "packages/core/revops/application/ports.py",
            "packages/core/revops/domain/entities/account.py",
        ],
    )

    assert gate.scope_violation(
        item,
        "baseline",
        ("packages/core/revops/application",),
    ) == ["packages/core/revops/domain/entities/account.py"]


def test_scope_violation_does_not_implicitly_allow_control_plane_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = gate.QueueItem(
        number=7,
        title="API",
        halt_reason=None,
        scope=("apps/api/",),
    )
    monkeypatch.setattr(
        gate,
        "changed_files",
        lambda _baseline: [
            ".handoff/STATE.md",
            "docs/specs/SPEC-003-example/tasks.md",
            ".handoff/AUTONOMOUS_QUEUE.md",
            "scripts/autonomous_gate.py",
            "AGENTS.md",
        ],
    )

    assert gate.scope_violation(
        item,
        "baseline",
        protocol_paths=("docs/specs/SPEC-003-example/tasks.md",),
    ) == [
        ".handoff/AUTONOMOUS_QUEUE.md",
        "scripts/autonomous_gate.py",
        "AGENTS.md",
    ]


def test_scope_prefix_requires_a_path_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    item = gate.QueueItem(
        number=7,
        title="API",
        halt_reason=None,
        scope=("apps/api/",),
    )
    monkeypatch.setattr(
        gate,
        "changed_files",
        lambda _baseline: ["apps/apiary/not_api.py", "apps/api/routes/valid.py"],
    )

    assert gate.scope_violation(item, "baseline") == ["apps/apiary/not_api.py"]

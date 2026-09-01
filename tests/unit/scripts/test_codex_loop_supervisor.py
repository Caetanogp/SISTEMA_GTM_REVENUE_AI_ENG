from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    from scripts import autonomous_gate
    from scripts import codex_loop_supervisor as supervisor
else:
    _SUPERVISOR_PATH = Path(__file__).resolve().parents[3] / "scripts" / "codex_loop_supervisor.py"
    _SPEC = importlib.util.spec_from_file_location(
        "codex_loop_supervisor_under_test", _SUPERVISOR_PATH
    )
    assert _SPEC is not None
    assert _SPEC.loader is not None
    supervisor = importlib.util.module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = supervisor
    _SPEC.loader.exec_module(supervisor)
    autonomous_gate = supervisor.autonomous_gate


def _config(
    tmp_path: Path, *, max_turns: int = 3, use_live_search: bool = False
) -> supervisor.SupervisorConfig:
    return supervisor.SupervisorConfig(
        repo=tmp_path,
        codex_command="codex-test",
        implementation_model="gpt-5.6-terra",
        architecture_model="gpt-5.6-sol",
        implementation_effort="medium",
        architecture_effort="xhigh",
        max_turns=max_turns,
        retry_delay_seconds=0,
        use_live_search=use_live_search,
    )


def _active(tmp_path: Path) -> supervisor.ActiveItem:
    spec_root = tmp_path / "docs" / "specs" / "SPEC-003-example"
    spec_root.mkdir(parents=True, exist_ok=True)
    tasks_file = spec_root / "tasks.md"
    tasks_file.write_text("- [ ] API\n", encoding="utf-8")
    return supervisor.ActiveItem(
        number=7,
        title="Administrative API",
        baseline_sha="a" * 40,
        repo=tmp_path,
        tasks_file=tasks_file,
        spec_root=spec_root,
    )


def _plan(tmp_path: Path, *, status: str = "approved_plan") -> supervisor.ArchitecturePlan:
    active = _active(tmp_path)
    return supervisor.ArchitecturePlan.from_json(
        {
            "status": status,
            "problem": "The router lacks an application contract.",
            "decision": "Add an application verification port.",
            "rationale": "Business rules stay outside FastAPI.",
            "allowed_paths": [
                "packages/core/revops/application/",
                "packages/core/revops/infrastructure/persistence/",
                "tests/integration/",
                f"{active.spec_root.relative_to(tmp_path).as_posix()}/plan.md",
                ".handoff/STATE.md",
            ],
            "implementation_steps": ["Define the port.", "Implement the adapter."],
            "tests": ["Prove stale decisions fail atomically."],
            "documentation_updates": ["Record the approved boundary."],
            "assumptions": ["The public API remains unchanged."],
            "changes_product_scope": False,
            "changes_public_contract": False,
            "adds_dependency": False,
            "destructive_migration": False,
            "weakens_security": False,
            "weakens_verification": False,
            "requires_external_action": False,
            "human_reason": None,
        }
    )


def _review(status: str = "approved") -> supervisor.ArchitectureReview:
    return supervisor.ArchitectureReview.from_json(
        {
            "status": status,
            "summary": "The boundary is safe.",
            "findings": [] if status == "approved" else ["Specify lock ordering."],
            "revision_guidance": [] if status == "approved" else ["Add deterministic locks."],
            "human_reason": None,
        }
    )


def _executor(status: str, *, reason: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "summary": "Executor outcome.",
        "halt_reason": reason,
        "requested_paths": ["packages/core/revops/application/"],
        "evidence": [],
    }


def test_codex_command_pins_models_effort_and_read_only_mode(tmp_path: Path) -> None:
    config = _config(tmp_path)
    command = supervisor._codex_command(
        config,
        model="gpt-5.6-sol",
        effort="xhigh",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        read_only=True,
    )

    assert command[:4] == ["codex-test", "--ask-for-approval", "never", "exec"]
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="xhigh"' in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--ask-for-approval") + 1] == "never"
    assert "--approve-for-me" not in command


def test_codex_command_uses_auto_review_for_normal_executor(tmp_path: Path) -> None:
    config = _config(tmp_path)
    command = supervisor._codex_command(
        config,
        model="gpt-5.6-terra",
        effort="medium",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        read_only=False,
    )

    assert 'model_reasoning_effort="medium"' in command
    assert "--approve-for-me" in command
    assert "--sandbox" not in command


def test_codex_command_places_live_search_before_exec(tmp_path: Path) -> None:
    config = _config(tmp_path, use_live_search=True)

    command = supervisor._codex_command(
        config,
        model="gpt-5.6-terra",
        effort="medium",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        read_only=False,
    )

    assert command[:3] == ["codex-test", "--search", "exec"]


def test_control_snapshot_detects_modified_or_deleted_controls(tmp_path: Path) -> None:
    config = _config(tmp_path)
    for relative_path in supervisor.CONTROL_PLANE_PATHS:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"trusted {relative_path}\n", encoding="utf-8")
    snapshot = supervisor._capture_control_snapshot(config)

    (tmp_path / supervisor.CONTROL_PLANE_PATHS[0]).write_text("modified\n", encoding="utf-8")
    (tmp_path / supervisor.CONTROL_PLANE_PATHS[1]).unlink()

    with pytest.raises(supervisor.SupervisorError, match="modified protected"):
        supervisor._verify_control_snapshot(config, snapshot)


def test_artifact_directory_must_be_outside_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    with pytest.raises(supervisor.SupervisorError, match="inside the repository"):
        supervisor._create_artifact_dir(_config(tmp_path))


def test_invoke_codex_retries_transient_process_failure(
    tmp_path: Path,
) -> None:
    attempts = 0

    def runner(
        args: Sequence[str],
        _cwd: Path,
        _input_text: str | None,
        _env: Mapping[str, str] | None,
        _timeout: int,
    ) -> supervisor.ProcessResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return supervisor.ProcessResult(1, stderr="503 temporarily unavailable")
        output_path = Path(args[args.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(_executor("continue")), encoding="utf-8")
        return supervisor.ProcessResult(0)

    result = supervisor._invoke_codex(
        _config(tmp_path),
        runner,
        tmp_path,
        phase="executor",
        prompt="work",
        schema=supervisor.EXECUTOR_SCHEMA,
        model="gpt-5.6-terra",
        effort="medium",
        read_only=False,
    )

    assert result["status"] == "continue"
    assert attempts == 2


def test_invoke_codex_does_not_retry_non_transient_configuration_error(
    tmp_path: Path,
) -> None:
    attempts = 0

    def runner(
        _args: Sequence[str],
        _cwd: Path,
        _input_text: str | None,
        _env: Mapping[str, str] | None,
        _timeout: int,
    ) -> supervisor.ProcessResult:
        nonlocal attempts
        attempts += 1
        return supervisor.ProcessResult(2, stderr="unknown model")

    with pytest.raises(supervisor.SupervisorError, match="unknown model"):
        supervisor._invoke_codex(
            _config(tmp_path),
            runner,
            tmp_path,
            phase="executor",
            prompt="work",
            schema=supervisor.EXECUTOR_SCHEMA,
            model="missing",
            effort="medium",
            read_only=False,
        )

    assert attempts == 1


@pytest.mark.parametrize(
    ("field", "path"),
    [
        ("changes_product_scope", "packages/core/revops/application/"),
        ("adds_dependency", "packages/core/revops/application/"),
        ("destructive_migration", "packages/core/revops/application/"),
        ("weakens_security", "packages/core/revops/application/"),
        ("weakens_verification", "packages/core/revops/application/"),
        ("requires_external_action", "packages/core/revops/application/"),
        ("changes_public_contract", "packages/core/revops/application/"),
        ("path", "pyproject.toml"),
        ("path", "packages/core/revops/infrastructure/persistence/migrations/new.py"),
        ("path", "../outside"),
        ("path", "packages/core"),
        ("path", "apps"),
        ("path", "tests"),
    ],
)
def test_validate_architecture_plan_rejects_policy_escape(
    tmp_path: Path, field: str, path: str
) -> None:
    active = _active(tmp_path)
    raw = json.loads(_plan(tmp_path).canonical_json())
    if field == "path":
        raw["allowed_paths"] = [path]
    else:
        raw[field] = True
    plan = supervisor.ArchitecturePlan.from_json(raw)

    with pytest.raises(supervisor.SupervisorError):
        supervisor.validate_architecture_plan(plan, active)


def test_validate_architecture_plan_accepts_bounded_technical_paths(tmp_path: Path) -> None:
    active = _active(tmp_path)

    assert supervisor.validate_architecture_plan(_plan(tmp_path), active) == (
        "packages/core/revops/application",
        "packages/core/revops/infrastructure/persistence",
        "tests/integration",
        "docs/specs/SPEC-003-example/plan.md",
        ".handoff/STATE.md",
    )


def test_architecture_escalation_revises_once_then_approves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    active = _active(tmp_path)
    plan = _plan(tmp_path)
    calls: list[tuple[str, str, str, bool]] = []

    def fake_invoke(
        _config: supervisor.SupervisorConfig,
        _runner: supervisor.Runner,
        _artifact_dir: Path,
        *,
        phase: str,
        prompt: str,
        schema: supervisor.JsonObject,
        model: str,
        effort: str,
        read_only: bool,
    ) -> supervisor.JsonObject:
        del prompt, schema
        calls.append((phase, model, effort, read_only))
        if phase.startswith("architecture-review"):
            review_status = "revise" if phase.endswith("-1") else "approved"
            return {
                "status": review_status,
                "summary": "Review result.",
                "findings": ["Specify lock ordering."] if review_status == "revise" else [],
                "revision_guidance": ["Use sorted IDs."] if review_status == "revise" else [],
                "human_reason": None,
            }
        return cast(supervisor.JsonObject, json.loads(plan.canonical_json()))

    monkeypatch.setattr(supervisor, "_invoke_codex", fake_invoke)
    outcome = supervisor.ExecutorOutcome.from_json(
        _executor("architecture_required", reason="Application port missing.")
    )

    approved, review = supervisor._architecture_escalation(
        _config(tmp_path), lambda *_args: supervisor.ProcessResult(0), tmp_path, active, outcome
    )

    assert approved == plan
    assert review.status is supervisor.ReviewStatus.APPROVED
    assert calls == [
        ("architecture-1", "gpt-5.6-sol", "xhigh", True),
        ("architecture-review-1", "gpt-5.6-sol", "xhigh", True),
        ("architecture-2", "gpt-5.6-sol", "xhigh", True),
        ("architecture-review-2", "gpt-5.6-sol", "xhigh", True),
    ]


def test_architecture_escalation_stops_after_two_rejected_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _plan(tmp_path)

    def fake_invoke(
        _config: supervisor.SupervisorConfig,
        _runner: supervisor.Runner,
        _artifact_dir: Path,
        *,
        phase: str,
        **_kwargs: object,
    ) -> supervisor.JsonObject:
        if phase.startswith("architecture-review"):
            return {
                "status": "revise",
                "summary": "Still incomplete.",
                "findings": ["Missing concurrency proof."],
                "revision_guidance": ["Add the proof."],
                "human_reason": None,
            }
        return cast(supervisor.JsonObject, json.loads(plan.canonical_json()))

    monkeypatch.setattr(supervisor, "_invoke_codex", fake_invoke)
    outcome = supervisor.ExecutorOutcome.from_json(_executor("architecture_required"))

    with pytest.raises(supervisor.SupervisorError, match="not approved after 2 attempts"):
        supervisor._architecture_escalation(
            _config(tmp_path),
            lambda *_args: supervisor.ProcessResult(0),
            tmp_path,
            _active(tmp_path),
            outcome,
        )


def _prepare_supervisor_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    gate_results: Iterator[supervisor.ProcessResult],
) -> supervisor.ActiveItem:
    active = _active(tmp_path)
    item = autonomous_gate.QueueItem(
        number=7,
        title=active.title,
        halt_reason=None,
        scope=("apps/api/",),
        closes=1,
    )
    monkeypatch.setattr(supervisor, "_git_output", lambda *_args: "feature/test")
    monkeypatch.setattr(supervisor, "_worktree_is_clean", lambda *_args: True)
    monkeypatch.setattr(supervisor, "_capture_control_snapshot", lambda *_args: {})
    monkeypatch.setattr(supervisor, "_verify_control_snapshot", lambda *_args: None)
    artifact_dir = tmp_path / "supervisor-artifacts"
    artifact_dir.mkdir()
    monkeypatch.setattr(supervisor, "_create_artifact_dir", lambda *_args: artifact_dir)
    monkeypatch.setattr(supervisor, "_run_gate", lambda *_args: next(gate_results))
    monkeypatch.setattr(supervisor, "_active_item", lambda *_args: active)
    monkeypatch.setattr(autonomous_gate, "completed_task_count", lambda _path: (0, 1))
    monkeypatch.setattr(autonomous_gate, "parse_queue", lambda: [item])
    monkeypatch.setattr(autonomous_gate, "item_for_done_count", lambda _items, _done: item)
    return active


def test_supervisor_completes_after_normal_executor_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_supervisor_state(
        monkeypatch,
        tmp_path,
        iter((supervisor.ProcessResult(1), supervisor.ProcessResult(0, "GOAL ACHIEVED"))),
    )
    phases: list[tuple[str, str, str, bool]] = []

    def fake_invoke(
        _config: supervisor.SupervisorConfig,
        _runner: supervisor.Runner,
        _artifact_dir: Path,
        *,
        phase: str,
        model: str,
        effort: str,
        read_only: bool,
        **_kwargs: object,
    ) -> supervisor.JsonObject:
        phases.append((phase, model, effort, read_only))
        return _executor("continue")

    monkeypatch.setattr(supervisor, "_invoke_codex", fake_invoke)

    assert (
        supervisor.run_supervisor(_config(tmp_path), lambda *_args: supervisor.ProcessResult(0))
        == 0
    )
    assert phases == [("executor", "gpt-5.6-terra", "medium", False)]


def test_supervisor_escalates_then_returns_approved_plan_to_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    active = _prepare_supervisor_state(
        monkeypatch,
        tmp_path,
        iter((supervisor.ProcessResult(1), supervisor.ProcessResult(0, "GOAL ACHIEVED"))),
    )
    plan = _plan(tmp_path)
    calls: list[tuple[str, str]] = []
    executor_calls = 0

    def fake_invoke(
        _config: supervisor.SupervisorConfig,
        _runner: supervisor.Runner,
        _artifact_dir: Path,
        *,
        phase: str,
        prompt: str,
        **_kwargs: object,
    ) -> supervisor.JsonObject:
        nonlocal executor_calls
        calls.append((phase, prompt))
        if phase == "executor":
            executor_calls += 1
            if executor_calls == 1:
                return _executor("architecture_required", reason="Application port missing.")
            assert "approved_architecture_plan" in prompt
            return _executor("continue")
        if phase.startswith("architecture-review"):
            return {
                "status": "approved",
                "summary": "Approved.",
                "findings": [],
                "revision_guidance": [],
                "human_reason": None,
            }
        return cast(supervisor.JsonObject, json.loads(plan.canonical_json()))

    monkeypatch.setattr(supervisor, "_invoke_codex", fake_invoke)
    monkeypatch.setattr(supervisor, "_record_approved_plan", lambda *_args: None)
    monkeypatch.setattr(
        supervisor,
        "_write_scope_authorization",
        lambda *_args, **_kwargs: "b" * 64,
    )

    assert (
        supervisor.run_supervisor(_config(tmp_path), lambda *_args: supervisor.ProcessResult(0))
        == 0
    )
    assert active.number == 7
    assert [phase for phase, _ in calls] == [
        "executor",
        "architecture-1",
        "architecture-review-1",
        "executor",
    ]


def test_supervisor_refuses_architecture_over_dirty_partial_implementation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_supervisor_state(monkeypatch, tmp_path, iter((supervisor.ProcessResult(1),)))
    clean_checks = iter((True, False))
    monkeypatch.setattr(supervisor, "_worktree_is_clean", lambda *_args: next(clean_checks))
    monkeypatch.setattr(
        supervisor,
        "_invoke_codex",
        lambda *_args, **_kwargs: _executor("architecture_required"),
    )

    with pytest.raises(supervisor.SupervisorError, match="partial implementation"):
        supervisor.run_supervisor(_config(tmp_path), lambda *_args: supervisor.ProcessResult(0))


def test_supervisor_checks_control_integrity_before_post_executor_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gate_calls = 0
    active = _active(tmp_path)

    monkeypatch.setattr(supervisor, "_git_output", lambda *_args: "feature/test")
    monkeypatch.setattr(supervisor, "_worktree_is_clean", lambda *_args: True)
    monkeypatch.setattr(supervisor, "_capture_control_snapshot", lambda *_args: {"AGENTS.md": "x"})
    monkeypatch.setattr(supervisor, "_active_item", lambda *_args: active)
    monkeypatch.setattr(
        supervisor,
        "_invoke_codex",
        lambda *_args, **_kwargs: _executor("continue"),
    )

    def fake_gate(*_args: object) -> supervisor.ProcessResult:
        nonlocal gate_calls
        gate_calls += 1
        return supervisor.ProcessResult(1)

    monkeypatch.setattr(supervisor, "_run_gate", fake_gate)
    monkeypatch.setattr(
        supervisor,
        "_verify_control_snapshot",
        lambda *_args: (_ for _ in ()).throw(supervisor.SupervisorError("control changed")),
    )

    with pytest.raises(supervisor.SupervisorError, match="control changed"):
        supervisor.run_supervisor(_config(tmp_path), lambda *_args: supervisor.ProcessResult(0))

    assert gate_calls == 1

"""Regression tests for active-spec selection in the autonomous gate."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from scripts.autonomous_gate import GateOutcome, GatePhase, QueueItem

_GATE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autonomous_gate.py"
_SPEC = importlib.util.spec_from_file_location("autonomous_gate_under_test", _GATE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gate
_SPEC.loader.exec_module(gate)


def _write_queue(root: Path, tasks_path: str) -> None:
    (root / ".handoff").mkdir(parents=True)
    active_spec = Path(tasks_path).parent.name
    (root / ".handoff" / "AUTONOMOUS_QUEUE.md").write_text(
        f"# Queue\n\n"
        f"- **Active spec:** `{active_spec}`\n"
        f"- **Feature branch:** `feature/{active_spec}`\n"
        f"- **Tasks file:** `{tasks_path}`\n",
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


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=repository,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _prepare_item_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    committed: bool,
    include_required_test: bool = True,
) -> tuple[Path, str, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Harness Test")
    _git(repository, "config", "user.email", "harness-test@example.invalid")
    _git(repository, "branch", "-M", "feature/SPEC-999-harness-test")

    queue = repository / ".handoff" / "AUTONOMOUS_QUEUE.md"
    queue.parent.mkdir(parents=True)
    queue.write_text(
        "# Queue\n\n"
        "- **Active spec:** `SPEC-999-harness-test`\n"
        "- **Feature branch:** `feature/SPEC-999-harness-test`\n"
        "- **Tasks file:** `docs/specs/SPEC-999-harness-test/tasks.md`\n\n"
        "## Item 1 - first item\n"
        "- **Scope:** `packages/`, `tests/unit/`\n"
        "- **Requires:** `packages/`, `tests/unit/`\n"
        "- **Verification profile:** `python-unit`\n"
        "- **Test paths:** `tests/unit/`\n"
        "- **Closes:** 1 tasks.md checkbox\n\n"
        "## Item 2 - second item\n"
        "- **Scope:** `apps/api/`\n"
        "- **Requires:** `apps/api/`\n"
        "- **Verification profile:** `python-unit`\n"
        "- **Test paths:** `tests/unit/`\n"
        "- **Closes:** 1 tasks.md checkbox\n",
        encoding="utf-8",
    )
    tasks = repository / "docs" / "specs" / "SPEC-999-harness-test" / "tasks.md"
    tasks.parent.mkdir(parents=True)
    tasks.write_text("- [ ] first item\n- [ ] second item\n", encoding="utf-8")
    state_file = repository / ".handoff" / "STATE.md"
    state_file.write_text("# Test state\n", encoding="utf-8")
    (repository / "README.md").write_text("test repository\n", encoding="utf-8")
    (repository / "tests" / "unit").mkdir(parents=True)
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "test: create harness fixture")
    baseline_sha = _git(repository, "rev-parse", "HEAD")

    (repository / "packages" / "sample.py").parent.mkdir(parents=True)
    (repository / "packages" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    if include_required_test:
        (repository / "tests" / "unit" / "test_sample.py").parent.mkdir(parents=True, exist_ok=True)
        (repository / "tests" / "unit" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )
    tasks.write_text("- [x] first item\n- [ ] second item\n", encoding="utf-8")
    if committed:
        _git(repository, "add", "--all")
        _git(repository, "commit", "--quiet", "-m", "test: complete first queue item")

    state_path = tmp_path / "gate-state.json"
    monkeypatch.setattr(gate, "ROOT", repository)
    monkeypatch.setattr(gate, "QUEUE_FILE", queue)
    monkeypatch.setattr(gate, "STATE_FILE", state_file)
    monkeypatch.setattr(gate, "GATE_STATE_FILE", state_path)
    monkeypatch.setattr(
        gate,
        "run",
        lambda *args, **_kwargs: subprocess.run(
            args,
            cwd=repository,
            capture_output=True,
            check=False,
            text=True,
        ),
    )
    monkeypatch.setattr(gate, "run_item_verification", lambda *_args: (True, "checks passed"))
    gate.GateState(
        baseline_sha=baseline_sha,
        baseline_done_count=0,
    ).save()
    return repository, baseline_sha, state_path


def test_stale_queue_branch_is_rejected_without_changing_gate_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=False,
    )
    queue = repository / ".handoff" / "AUTONOMOUS_QUEUE.md"
    queue.write_text(
        queue.read_text(encoding="utf-8").replace(
            "feature/SPEC-999-harness-test", "feature/SPEC-998-stale"
        ),
        encoding="utf-8",
    )

    exit_code = gate.main([])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert saved["baseline_sha"] == baseline_sha
    assert saved["baseline_done_count"] == 0


def test_active_spec_must_match_tasks_file_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _baseline_sha, _state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=False,
    )
    queue = repository / ".handoff" / "AUTONOMOUS_QUEUE.md"
    queue.write_text(
        queue.read_text(encoding="utf-8").replace(
            "- **Active spec:** `SPEC-999-harness-test`",
            "- **Active spec:** `SPEC-998-stale`",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match tasks file directory"):
        gate.active_tasks_file()


def test_queue_item_order_must_be_contiguous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _repository, _baseline_sha, _state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=False,
    )
    queue = gate.QUEUE_FILE
    queue.write_text(
        queue.read_text(encoding="utf-8").replace("## Item 2 -", "## Item 3 -"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unique and sequential"):
        gate.parse_queue()


def test_queue_rejects_unsupported_profile_and_incompatible_test_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _repository, _baseline_sha, _state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=False,
    )
    queue = gate.QUEUE_FILE
    original = queue.read_text(encoding="utf-8")
    queue.write_text(original.replace("python-unit", "arbitrary-command"), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported verification profile"):
        gate.validate_queue(gate.parse_queue(), gate.active_tasks_file(), gate.current_branch())

    queue.write_text(original.replace("tests/unit/`", "tests/integration/`"), encoding="utf-8")
    (gate.ROOT / "tests" / "integration").mkdir(parents=True)
    with pytest.raises(ValueError, match="outside profile roots"):
        gate.validate_queue(gate.parse_queue(), gate.active_tasks_file(), gate.current_branch())


def test_python_profile_builds_fixed_argv_from_validated_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    changed_python = tmp_path / "packages" / "core" / "sample.py"
    changed_python.parent.mkdir(parents=True)
    changed_python.write_text("VALUE = 1\n", encoding="utf-8")
    commands = gate.build_verification_commands(
        "python-unit",
        ("tests/unit/test_sample.py",),
        ["packages/core/sample.py", "tests/unit/test_sample.py"],
    )

    assert [command.argv for command in commands] == [
        ("ruff", "check", "--", "packages/core/sample.py"),
        ("mypy", "."),
        ("lint-imports",),
        ("pytest", "tests/unit/test_sample.py", "-q"),
    ]
    assert all(command.cwd == tmp_path for command in commands)


def test_profile_builder_rejects_unregistered_commands_and_unsafe_changed_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="unsupported verification profile"):
        gate.build_verification_commands("python -c 'bad'", (), [])
    with pytest.raises(ValueError, match="safe repository-relative path"):
        gate.build_verification_commands("python-unit", ("tests/unit/",), ["../bad.py"])


def test_item_verification_executes_only_argv_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    observability_dir = tmp_path / "observability"
    monkeypatch.setenv("CODEX_LOOP_OBSERVABILITY_DIR", str(observability_dir))
    monkeypatch.setattr(gate, "changed_files", lambda _baseline: ["docs/guide.md"])
    invocations: list[tuple[tuple[str, ...], Path]] = []

    def record_run(*argv: str, cwd: Path = gate.ROOT) -> SimpleNamespace:
        invocations.append((argv, cwd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gate, "run", record_run)
    item = gate.QueueItem(
        number=1,
        title="docs",
        halt_reason=None,
        scope=("docs/",),
        requires=("docs/",),
        verification_profile="docs",
    )

    passed, report = gate.run_item_verification(item, "baseline")

    assert passed
    assert [argv for argv, _cwd in invocations] == [
        ("git", "diff", "--check"),
        ("git", "diff", "--cached", "--check"),
        ("python", "scripts/check_agent_docs.py"),
    ]
    assert all(cwd == tmp_path for _argv, cwd in invocations)
    assert "docs check: OK" in report
    timings = [
        json.loads(line)
        for line in (observability_dir / "codex-revops-loop-timings.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["check"] for record in timings] == [
        "unstaged diff check",
        "staged diff check",
        "docs check",
        "phase_total",
    ]
    assert all(record["phase"] == "item_completion" for record in timings)


def test_docs_profile_uses_only_fixed_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    commands = gate.build_verification_commands("docs", (), ["docs/guide.md"])

    assert [command.argv for command in commands] == [
        ("git", "diff", "--check"),
        ("git", "diff", "--cached", "--check"),
        ("python", "scripts/check_agent_docs.py"),
    ]


def test_web_profile_requires_fixed_scripts_and_npm_lockfile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    with pytest.raises(ValueError, match=r"package\.json"):
        gate.build_verification_commands("web", (), [])

    web_root = tmp_path / "apps" / "web"
    web_root.mkdir(parents=True)
    (web_root / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "test": "vitest", "build": "next build"}}),
        encoding="utf-8",
    )
    (web_root / "package-lock.json").write_text("{}", encoding="utf-8")

    commands = gate.build_verification_commands("web", (), [])

    assert [command.argv for command in commands] == [
        ("npm", "run", "lint"),
        ("npm", "test"),
        ("npm", "run", "build"),
    ]
    assert all(command.cwd == web_root for command in commands)


@pytest.mark.parametrize(
    ("done_count", "total_count", "baseline_done_count", "expected"),
    [
        (0, 2, 0, gate.GatePhase.PROGRESS_CHECKPOINT),
        (1, 2, 0, gate.GatePhase.ITEM_COMPLETION),
        (2, 2, 1, gate.GatePhase.ITEM_COMPLETION),
        (2, 2, 2, gate.GatePhase.GOAL_COMPLETION),
    ],
)
def test_gate_phase_is_determined_only_by_task_and_baseline_state(
    done_count: int,
    total_count: int,
    baseline_done_count: int,
    expected: GatePhase,
) -> None:
    assert gate.select_phase(done_count, total_count, baseline_done_count) is expected


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, gate.GateOutcome.GOAL_ACHIEVED),
        (1, gate.GateOutcome.CONTINUE),
        (2, gate.GateOutcome.HALT),
        (3, gate.GateOutcome.INVALID),
    ],
)
def test_gate_exit_codes_have_one_shared_outcome_contract(
    exit_code: int,
    expected: GateOutcome,
) -> None:
    assert gate.gate_outcome(exit_code) is expected


def test_autonomous_loop_playbook_documents_shared_exit_contract() -> None:
    playbook = Path(__file__).resolve().parents[3] / "docs" / "playbooks" / "autonomous-loop.md"
    text = playbook.read_text(encoding="utf-8")

    assert "Shared gate outcome contract" in text
    assert "exit 0 means stop and report" in text
    assert "exit 1 means continue working" in text
    assert "exit 2 means stop" in text


def test_progress_checkpoint_runs_diff_checks_without_quality_suites(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repository, baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=False,
    )
    tasks_file = gate.active_tasks_file()
    tasks_file.write_text("- [ ] first item\n- [ ] second item\n", encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "run_quality_gate",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("quality suites ran")),
    )

    exit_code = gate.main([])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Progress checkpoint passed for Item 1" in captured.out
    assert "unstaged diff check: OK" in captured.out
    assert saved["baseline_sha"] == baseline_sha
    assert saved["baseline_done_count"] == 0


@pytest.mark.parametrize("committed", [True, False], ids=["committed", "uncommitted"])
def test_item_transition_checks_completed_item_scope_at_saved_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    committed: bool,
) -> None:
    repository, baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=committed,
    )
    observed: list[tuple[int, str]] = []
    original_scope_violation = gate.scope_violation

    def track_scope_check(
        item: QueueItem,
        baseline: str,
        authorized_scope: tuple[str, ...] = (),
        protocol_paths: tuple[str, ...] = (),
    ) -> list[str]:
        observed.append((item.number, baseline))
        return cast(
            list[str], original_scope_violation(item, baseline, authorized_scope, protocol_paths)
        )

    monkeypatch.setattr(gate, "scope_violation", track_scope_check)

    exit_code = gate.main([])
    saved = json.loads(state_path.read_text(encoding="utf-8"))

    assert observed[0] == (1, baseline_sha)
    assert exit_code == 1
    if committed:
        assert saved["baseline_sha"] == _git(repository, "rev-parse", "HEAD")
        assert saved["baseline_done_count"] == 1
    else:
        assert saved["baseline_sha"] == baseline_sha
        assert saved["baseline_done_count"] == 0


def test_item_transition_rejects_missing_evidence_without_advancing_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _repository, baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=True,
        include_required_test=False,
    )
    checked: list[tuple[int, str]] = []
    original_missing_evidence = gate.missing_required_evidence

    def track_required_evidence(item: QueueItem, baseline: str) -> list[str]:
        checked.append((item.number, baseline))
        return cast(list[str], original_missing_evidence(item, baseline))

    monkeypatch.setattr(gate, "missing_required_evidence", track_required_evidence)

    exit_code = gate.main([])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert checked[0] == (1, baseline_sha)
    assert saved["baseline_sha"] == baseline_sha
    assert saved["baseline_done_count"] == 0


def test_item_transition_rejects_scope_violation_without_advancing_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository, baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=True,
    )
    out_of_scope_file = repository / "apps" / "api" / "unexpected.py"
    out_of_scope_file.parent.mkdir(parents=True)
    out_of_scope_file.write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "apps/api/unexpected.py")
    _git(repository, "commit", "--quiet", "-m", "test: add out-of-scope change")

    exit_code = gate.main([])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert saved["baseline_sha"] == baseline_sha
    assert saved["baseline_done_count"] == 0
    assert "Completed Item 1 declares scope" in capsys.readouterr().err


def test_item_transition_rejects_failed_verification_without_advancing_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repository, baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=True,
    )
    monkeypatch.setattr(gate, "run_item_verification", lambda *_args: (False, "checks failed"))

    exit_code = gate.main([])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert saved["baseline_sha"] == baseline_sha
    assert saved["baseline_done_count"] == 0
    assert "failed its verification profile" in capsys.readouterr().err


def test_final_gate_failure_does_not_advance_item_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository, _initial_baseline_sha, state_path = _prepare_item_transition(
        monkeypatch,
        tmp_path,
        committed=True,
    )
    item_two_baseline = _git(repository, "rev-parse", "HEAD")
    gate.GateState(baseline_sha=item_two_baseline, baseline_done_count=1).save()
    second_item_file = repository / "apps" / "api" / "second_item.py"
    second_item_file.parent.mkdir(parents=True)
    second_item_file.write_text("VALUE = 3\n", encoding="utf-8")
    tasks_file = repository / "docs" / "specs" / "SPEC-999-harness-test" / "tasks.md"
    tasks_file.write_text("- [x] first item\n- [x] second item\n", encoding="utf-8")
    _git(repository, "add", "apps/api/second_item.py", "docs/specs/SPEC-999-harness-test/tasks.md")
    _git(repository, "commit", "--quiet", "-m", "test: complete final queue item")
    monkeypatch.setattr(
        gate,
        "run_item_verification",
        lambda *_args: (True, "item checks passed"),
    )
    monkeypatch.setattr(
        gate,
        "run_quality_gate",
        lambda *, full: (not full, "final checks failed" if full else "item checks passed"),
    )

    exit_code = gate.main([])

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert saved["baseline_sha"] == item_two_baseline
    assert saved["baseline_done_count"] == 1
    assert "Final verification failed" in capsys.readouterr().err


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

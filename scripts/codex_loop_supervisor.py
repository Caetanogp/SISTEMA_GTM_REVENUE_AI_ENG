#!/usr/bin/env python
"""Supervise unattended Codex turns with bounded architecture escalation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMPLEMENTATION_MODEL = "gpt-5.6-terra"
DEFAULT_ARCHITECTURE_MODEL = "gpt-5.6-sol"
DEFAULT_IMPLEMENTATION_EFFORT = "medium"
DEFAULT_ARCHITECTURE_EFFORT = "xhigh"
MAX_ARCHITECTURE_ATTEMPTS = 2
MAX_TEXT_LENGTH = 8_000
MAX_LIST_ITEMS = 100

CONTROL_PLANE_PATHS = (
    ".codex/config.toml",
    ".codex/prompts/autonomous-loop.md",
    ".handoff/AUTONOMOUS_QUEUE.md",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/playbooks/autonomous-loop.md",
    "pyproject.toml",
    "scripts/autonomous_gate.py",
    "scripts/codex_loop_supervisor.py",
    "scripts/start_codex_loop.ps1",
    "uv.lock",
)

type JsonObject = dict[str, Any]

_GATE_SPEC = importlib.util.spec_from_file_location(
    "codex_loop_supervisor_autonomous_gate", ROOT / "scripts" / "autonomous_gate.py"
)
if _GATE_SPEC is None or _GATE_SPEC.loader is None:
    raise RuntimeError("Could not load scripts/autonomous_gate.py")
autonomous_gate = importlib.util.module_from_spec(_GATE_SPEC)
sys.modules[_GATE_SPEC.name] = autonomous_gate
_GATE_SPEC.loader.exec_module(autonomous_gate)


class TurnStatus(StrEnum):
    CONTINUE = "continue"
    ARCHITECTURE_REQUIRED = "architecture_required"
    HUMAN_REQUIRED = "human_required"
    COMPLETE = "complete"


class PlanStatus(StrEnum):
    APPROVED_PLAN = "approved_plan"
    HUMAN_REQUIRED = "human_required"


class ReviewStatus(StrEnum):
    APPROVED = "approved"
    REVISE = "revise"
    HUMAN_REQUIRED = "human_required"


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


type Runner = Callable[
    [Sequence[str], Path, str | None, Mapping[str, str] | None, int], ProcessResult
]


@dataclass(frozen=True)
class SupervisorConfig:
    repo: Path
    codex_command: str
    implementation_model: str
    architecture_model: str
    implementation_effort: str
    architecture_effort: str
    max_turns: int
    max_architecture_attempts: int = MAX_ARCHITECTURE_ATTEMPTS
    max_process_retries: int = 2
    retry_delay_seconds: int = 30
    use_live_search: bool = False


@dataclass(frozen=True)
class ExecutorOutcome:
    status: TurnStatus
    summary: str
    halt_reason: str | None
    requested_paths: tuple[str, ...]
    evidence: tuple[str, ...]

    @classmethod
    def from_json(cls, raw: JsonObject) -> ExecutorOutcome:
        return cls(
            status=TurnStatus(_required_string(raw, "status")),
            summary=_required_string(raw, "summary"),
            halt_reason=_optional_string(raw, "halt_reason"),
            requested_paths=_string_tuple(raw, "requested_paths"),
            evidence=_string_tuple(raw, "evidence"),
        )


@dataclass(frozen=True)
class ArchitecturePlan:
    status: PlanStatus
    problem: str
    decision: str
    rationale: str
    allowed_paths: tuple[str, ...]
    implementation_steps: tuple[str, ...]
    tests: tuple[str, ...]
    documentation_updates: tuple[str, ...]
    assumptions: tuple[str, ...]
    changes_product_scope: bool
    changes_public_contract: bool
    adds_dependency: bool
    destructive_migration: bool
    weakens_security: bool
    weakens_verification: bool
    requires_external_action: bool
    human_reason: str | None

    @classmethod
    def from_json(cls, raw: JsonObject) -> ArchitecturePlan:
        return cls(
            status=PlanStatus(_required_string(raw, "status")),
            problem=_required_string(raw, "problem"),
            decision=_required_string(raw, "decision"),
            rationale=_required_string(raw, "rationale"),
            allowed_paths=_string_tuple(raw, "allowed_paths"),
            implementation_steps=_string_tuple(raw, "implementation_steps"),
            tests=_string_tuple(raw, "tests"),
            documentation_updates=_string_tuple(raw, "documentation_updates"),
            assumptions=_string_tuple(raw, "assumptions"),
            changes_product_scope=_required_bool(raw, "changes_product_scope"),
            changes_public_contract=_required_bool(raw, "changes_public_contract"),
            adds_dependency=_required_bool(raw, "adds_dependency"),
            destructive_migration=_required_bool(raw, "destructive_migration"),
            weakens_security=_required_bool(raw, "weakens_security"),
            weakens_verification=_required_bool(raw, "weakens_verification"),
            requires_external_action=_required_bool(raw, "requires_external_action"),
            human_reason=_optional_string(raw, "human_reason"),
        )

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "status": self.status.value,
                "problem": self.problem,
                "decision": self.decision,
                "rationale": self.rationale,
                "allowed_paths": self.allowed_paths,
                "implementation_steps": self.implementation_steps,
                "tests": self.tests,
                "documentation_updates": self.documentation_updates,
                "assumptions": self.assumptions,
                "changes_product_scope": self.changes_product_scope,
                "changes_public_contract": self.changes_public_contract,
                "adds_dependency": self.adds_dependency,
                "destructive_migration": self.destructive_migration,
                "weakens_security": self.weakens_security,
                "weakens_verification": self.weakens_verification,
                "requires_external_action": self.requires_external_action,
                "human_reason": self.human_reason,
            },
            ensure_ascii=True,
            sort_keys=True,
        )


@dataclass(frozen=True)
class ArchitectureReview:
    status: ReviewStatus
    summary: str
    findings: tuple[str, ...]
    revision_guidance: tuple[str, ...]
    human_reason: str | None

    @classmethod
    def from_json(cls, raw: JsonObject) -> ArchitectureReview:
        return cls(
            status=ReviewStatus(_required_string(raw, "status")),
            summary=_required_string(raw, "summary"),
            findings=_string_tuple(raw, "findings"),
            revision_guidance=_string_tuple(raw, "revision_guidance"),
            human_reason=_optional_string(raw, "human_reason"),
        )


@dataclass(frozen=True)
class ActiveItem:
    number: int
    title: str
    baseline_sha: str
    repo: Path
    tasks_file: Path
    spec_root: Path


class SupervisorError(RuntimeError):
    """A deterministic or process-level failure that requires a hard stop."""


def _required_string(raw: JsonObject, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SupervisorError(f"Codex response field {key!r} must be a non-empty string")
    if len(value) > MAX_TEXT_LENGTH:
        raise SupervisorError(f"Codex response field {key!r} exceeds its size limit")
    return value.strip()


def _optional_string(raw: JsonObject, key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SupervisorError(f"Codex response field {key!r} must be null or a non-empty string")
    if len(value) > MAX_TEXT_LENGTH:
        raise SupervisorError(f"Codex response field {key!r} exceeds its size limit")
    return value.strip()


def _required_bool(raw: JsonObject, key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise SupervisorError(f"Codex response field {key!r} must be a boolean")
    return value


def _string_tuple(raw: JsonObject, key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SupervisorError(f"Codex response field {key!r} must be an array of strings")
    if len(value) > MAX_LIST_ITEMS or any(len(item) > MAX_TEXT_LENGTH for item in value):
        raise SupervisorError(f"Codex response field {key!r} exceeds its size limit")
    return tuple(item.strip() for item in cast(list[str], value) if item.strip())


def default_runner(
    args: Sequence[str],
    cwd: Path,
    input_text: str | None,
    env: Mapping[str, str] | None,
    timeout: int,
) -> ProcessResult:
    completed = subprocess.run(  # noqa: S603 - argv is constructed, never shell-expanded.
        list(args),
        cwd=cwd,
        input=input_text,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _object_schema(properties: JsonObject, required: Sequence[str]) -> JsonObject:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


def _string_schema(*, nullable: bool = False) -> JsonObject:
    return {
        "type": ["string", "null"] if nullable else "string",
        "minLength": 1,
        "maxLength": MAX_TEXT_LENGTH,
    }


def _string_array_schema() -> JsonObject:
    return {
        "type": "array",
        "maxItems": MAX_LIST_ITEMS,
        "items": _string_schema(),
    }


EXECUTOR_SCHEMA = _object_schema(
    {
        "status": {"type": "string", "enum": [status.value for status in TurnStatus]},
        "summary": _string_schema(),
        "halt_reason": _string_schema(nullable=True),
        "requested_paths": _string_array_schema(),
        "evidence": _string_array_schema(),
    },
    ("status", "summary", "halt_reason", "requested_paths", "evidence"),
)

ARCHITECTURE_SCHEMA = _object_schema(
    {
        "status": {"type": "string", "enum": [status.value for status in PlanStatus]},
        "problem": _string_schema(),
        "decision": _string_schema(),
        "rationale": _string_schema(),
        "allowed_paths": _string_array_schema(),
        "implementation_steps": _string_array_schema(),
        "tests": _string_array_schema(),
        "documentation_updates": _string_array_schema(),
        "assumptions": _string_array_schema(),
        "changes_product_scope": {"type": "boolean"},
        "changes_public_contract": {"type": "boolean"},
        "adds_dependency": {"type": "boolean"},
        "destructive_migration": {"type": "boolean"},
        "weakens_security": {"type": "boolean"},
        "weakens_verification": {"type": "boolean"},
        "requires_external_action": {"type": "boolean"},
        "human_reason": _string_schema(nullable=True),
    },
    (
        "status",
        "problem",
        "decision",
        "rationale",
        "allowed_paths",
        "implementation_steps",
        "tests",
        "documentation_updates",
        "assumptions",
        "changes_product_scope",
        "changes_public_contract",
        "adds_dependency",
        "destructive_migration",
        "weakens_security",
        "weakens_verification",
        "requires_external_action",
        "human_reason",
    ),
)

REVIEW_SCHEMA = _object_schema(
    {
        "status": {"type": "string", "enum": [status.value for status in ReviewStatus]},
        "summary": _string_schema(),
        "findings": _string_array_schema(),
        "revision_guidance": _string_array_schema(),
        "human_reason": _string_schema(nullable=True),
    },
    ("status", "summary", "findings", "revision_guidance", "human_reason"),
)


def _read_json(path: Path) -> JsonObject:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupervisorError(f"Could not read structured Codex output at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SupervisorError(f"Structured Codex output at {path} must be a JSON object")
    return cast(JsonObject, raw)


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _codex_command(
    config: SupervisorConfig,
    *,
    model: str,
    effort: str,
    schema_path: Path,
    output_path: Path,
    read_only: bool,
) -> list[str]:
    args = [config.codex_command]
    # These two flags are global CLI options and must precede the subcommand.
    if read_only:
        args.extend(("--ask-for-approval", "never"))
    if config.use_live_search:
        args.append("--search")
    args.extend(
        (
            "exec",
            "--cd",
            str(config.repo),
            "--model",
            model,
            "--config",
            f'model_reasoning_effort="{effort}"',
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        )
    )
    if read_only:
        args.extend(("--sandbox", "read-only"))
    else:
        args.append("--approve-for-me")
    args.append("-")
    return args


def _invoke_codex(
    config: SupervisorConfig,
    runner: Runner,
    artifact_dir: Path,
    *,
    phase: str,
    prompt: str,
    schema: JsonObject,
    model: str,
    effort: str,
    read_only: bool,
) -> JsonObject:
    schema_path = artifact_dir / f"{phase}.schema.json"
    output_path = artifact_dir / f"{phase}.output.json"
    _write_json(schema_path, schema)
    command = _codex_command(
        config,
        model=model,
        effort=effort,
        schema_path=schema_path,
        output_path=output_path,
        read_only=read_only,
    )
    env = os.environ.copy()
    pytest_temp = artifact_dir / "pytest"
    pytest_temp.mkdir(exist_ok=True)
    env.update(
        {
            "TEMP": str(pytest_temp),
            "TMP": str(pytest_temp),
            "PYTEST_ADDOPTS": f"--basetemp={pytest_temp}",
        }
    )
    last_error = "Codex process failed without output"
    for attempt in range(1, config.max_process_retries + 2):
        output_path.unlink(missing_ok=True)
        try:
            result = runner(command, config.repo, prompt, env, 14_400)
        except subprocess.SubprocessError as exc:
            result = ProcessResult(1, stderr=str(exc))
        (artifact_dir / f"{phase}.attempt-{attempt}.stdout.log").write_text(
            result.stdout, encoding="utf-8"
        )
        (artifact_dir / f"{phase}.attempt-{attempt}.stderr.log").write_text(
            result.stderr, encoding="utf-8"
        )
        if result.returncode == 0 and output_path.is_file():
            try:
                return _read_json(output_path)
            except SupervisorError as exc:
                last_error = str(exc)
        elif result.returncode == 0:
            last_error = f"Codex {phase} did not write its structured final response"
        else:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-12:])
            last_error = f"Codex {phase} process exited {result.returncode}:\n{tail}"
            if not _is_transient_process_failure(result.stdout + result.stderr):
                break
        if attempt <= config.max_process_retries:
            delay = config.retry_delay_seconds * attempt
            print(f"Transient Codex {phase} failure; retrying in {delay} seconds.")
            time.sleep(delay)
    raise SupervisorError(last_error)


_TRANSIENT_PROCESS_MARKERS = (
    "429",
    "503",
    "connection reset",
    "connection refused",
    "rate limit",
    "server error",
    "stream disconnected",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "usage limit",
)


def _is_transient_process_failure(output: str) -> bool:
    lowered = output.casefold()
    return any(marker in lowered for marker in _TRANSIENT_PROCESS_MARKERS)


def _git_output(config: SupervisorConfig, runner: Runner, *args: str) -> str:
    result = runner(("git", *args), config.repo, None, None, 60)
    if result.returncode != 0:
        raise SupervisorError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _worktree_is_clean(config: SupervisorConfig, runner: Runner) -> bool:
    return not _git_output(config, runner, "status", "--porcelain")


def _capture_control_snapshot(config: SupervisorConfig) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for relative_path in CONTROL_PLANE_PATHS:
        path = config.repo / relative_path
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise SupervisorError(
                f"Could not snapshot control-plane file {relative_path}: {exc}"
            ) from exc
        snapshot[relative_path] = hashlib.sha256(content).hexdigest()
    return snapshot


def _verify_control_snapshot(config: SupervisorConfig, snapshot: Mapping[str, str]) -> None:
    changed: list[str] = []
    for relative_path, expected_digest in snapshot.items():
        path = config.repo / relative_path
        try:
            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            changed.append(relative_path)
            continue
        if actual_digest != expected_digest:
            changed.append(relative_path)
    if changed:
        raise SupervisorError(
            "Executor modified protected autonomous-loop controls: "
            f"{changed}. Refusing to process its outcome or execute the gate."
        )


def _create_artifact_dir(config: SupervisorConfig) -> Path:
    temp_root = Path(tempfile.gettempdir()).resolve()
    if temp_root.is_relative_to(config.repo.resolve()):
        raise SupervisorError(
            "The OS temporary directory resolved inside the repository; refusing to create "
            "supervisor controls where an executor could modify them"
        )
    return Path(tempfile.mkdtemp(prefix="codex-revops-supervisor-", dir=temp_root))


def _run_gate(
    config: SupervisorConfig,
    runner: Runner,
    authorization_path: Path | None = None,
) -> ProcessResult:
    command = [sys.executable, "scripts/autonomous_gate.py"]
    if authorization_path is not None:
        command.extend(("--scope-authorization", str(authorization_path)))
    return runner(command, config.repo, None, None, 1_800)


def _active_item(config: SupervisorConfig) -> ActiveItem:
    tasks_file = autonomous_gate.active_tasks_file()
    done_count, _ = autonomous_gate.completed_task_count(tasks_file)
    item = autonomous_gate.item_for_done_count(autonomous_gate.parse_queue(), done_count)
    if item is None:
        raise SupervisorError("The queue has no active item even though the full gate is not done")
    state = autonomous_gate.GateState.load()
    if state.baseline_sha is None or state.baseline_done_count != done_count:
        raise SupervisorError("The autonomous gate baseline is not initialized for the active item")
    return ActiveItem(
        number=item.number,
        title=item.title,
        baseline_sha=state.baseline_sha,
        repo=config.repo,
        tasks_file=tasks_file,
        spec_root=tasks_file.parent,
    )


def _executor_prompt(active: ActiveItem, approved_plan: ArchitecturePlan | None) -> str:
    approved = ""
    if approved_plan is not None:
        approved = f"""

An independent read-only architect and reviewer approved this bounded technical plan. Treat it as
the resolved design for the current item, record the decision in the active spec plan and handoff
before implementation, and stay inside its allowed paths:

<approved_architecture_plan>
{approved_plan.canonical_json()}
</approved_architecture_plan>
"""
    return f"""
Work exactly one autonomous queue item in this repository.

Active item: Item {active.number} - {active.title}
Tasks file: {active.tasks_file.relative_to(active.repo).as_posix()}

Read AGENTS.md, .handoff/STATE.md, .handoff/AUTONOMOUS_QUEUE.md, the active spec, and the autonomous
loop playbook before changing anything. Check the branch before the first edit. Do not launch or
delegate to another coding agent. Do not push, merge, touch main, install dependencies, weaken a
check, or begin another item.

If this item contains a genuine architecture decision not resolved by the approved spec/plan, stop
before editing implementation files. Return status `architecture_required`, explain the decision,
and list the additional repository paths that a correct solution would require. Use
`human_required` for product scope, public-contract invention, dependencies, destructive migration,
security relaxation, external actions, or any decision without a dominant safe recommendation.

Otherwise implement and verify this one item, make small conventional commits, tick only its mapped
checkboxes after evidence exists, update .handoff/STATE.md, and run the autonomous gate. Return
`complete` only if the gate exits 0; otherwise return `continue` after making concrete progress.
Every final response must match the provided JSON schema and contain no text outside that object.
{approved}
""".strip()


def _architecture_prompt(
    active: ActiveItem,
    outcome: ExecutorOutcome,
    prior_plan: ArchitecturePlan | None,
    feedback: Sequence[str],
) -> str:
    revision = ""
    if prior_plan is not None:
        revision = f"""

Revise this prior plan:
<prior_plan>{prior_plan.canonical_json()}</prior_plan>
Reviewer guidance: {json.dumps(list(feedback), ensure_ascii=True)}
"""
    return f"""
Perform a deliberate architecture pass for the active repository item below. This is an unattended,
bounded technical escalation. You are read-only: do not edit files, run formatters, commit, mutate
the handoff, or implement the plan.

Item: {active.number} - {active.title}
Tasks file: {active.tasks_file.relative_to(active.repo).as_posix()}
Reported blocker: {outcome.halt_reason or outcome.summary}
Requested paths: {json.dumps(outcome.requested_paths)}

Read the repository, active spec, plan, application contracts, adapters, tests, and architecture
rules. Select the smallest reversible design that satisfies existing acceptance criteria and Clean
Architecture. It may add technical application ports/adapters and tests, but it must not invent or
change product scope or public contracts, add a dependency, require destructive migration, weaken
security/tenant isolation/audit/PII controls, weaken verification, or require an external action.
If any of those are necessary, return `human_required` and explain why.

Allowed paths must be narrow repository-relative files or directory prefixes. Include the active
spec plan and .handoff/STATE.md when a decision must be recorded. Produce implementation-ready
steps and concrete tests. Set every policy boolean truthfully. Return only the schema-valid object.
{revision}
""".strip()


def _review_prompt(active: ActiveItem, plan: ArchitecturePlan) -> str:
    return f"""
Independently review this proposed architecture plan for Item {active.number} - {active.title}.
You are read-only. Inspect the repository and active spec yourself; do not trust the proposal's
self-assessment.

<proposed_plan>{plan.canonical_json()}</proposed_plan>

Approve only if it is technically complete, minimal, reversible, tenant-safe, PII-safe, compatible,
inside the approved spec, and testable without weakening checks. Require revision for correctable
technical gaps. Return `human_required` for product decisions, public-contract invention, new
dependencies, destructive migration, security relaxation, external actions, or no dominant safe
choice. Return only the schema-valid object.
""".strip()


_DEPENDENCY_FILES = {
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


def _normalize_scope_path(raw: str) -> str:
    value = raw.strip().replace("\\", "/").rstrip("/")
    path = PurePosixPath(value)
    if (
        not value
        or value in {".", ".."}
        or path.is_absolute()
        or ".." in path.parts
        or any(character in value for character in "*?[]")
    ):
        raise SupervisorError(f"Architecture plan contains unsafe scope path: {raw!r}")
    return path.as_posix()


def validate_architecture_plan(plan: ArchitecturePlan, active: ActiveItem) -> tuple[str, ...]:
    if plan.status is PlanStatus.HUMAN_REQUIRED:
        raise SupervisorError(plan.human_reason or "The architect requires human input")
    policy_flags = {
        "changes product scope": plan.changes_product_scope,
        "changes a public contract": plan.changes_public_contract,
        "adds a dependency": plan.adds_dependency,
        "requires destructive migration": plan.destructive_migration,
        "weakens security": plan.weakens_security,
        "weakens verification": plan.weakens_verification,
        "requires external action": plan.requires_external_action,
    }
    violations = [label for label, enabled in policy_flags.items() if enabled]
    if violations:
        raise SupervisorError("Architecture plan exceeds autonomy policy: " + ", ".join(violations))
    if not plan.allowed_paths or not plan.implementation_steps or not plan.tests:
        raise SupervisorError(
            "Architecture plan must include paths, implementation steps, and tests"
        )

    spec_prefix = active.spec_root.relative_to(active.repo).as_posix()
    allowed_roots = ("apps/", "packages/", "tests/", "docs/decisions/", f"{spec_prefix}/")
    allowed_exact = {".handoff/STATE.md"}
    normalized: list[str] = []
    for raw_path in plan.allowed_paths:
        path = _normalize_scope_path(raw_path)
        name = PurePosixPath(path).name.lower()
        if name in _DEPENDENCY_FILES or "/migrations/" in f"/{path}/":
            raise SupervisorError(f"Architecture escalation may not authorize {path!r}")
        if path not in allowed_exact and not any(path.startswith(root) for root in allowed_roots):
            raise SupervisorError(
                f"Architecture plan path is outside bounded technical roots: {path}"
            )
        parts = PurePosixPath(path).parts
        if parts[0] == "apps" and len(parts) < 2:
            raise SupervisorError("Architecture plan may not authorize the entire apps tree")
        if parts[0] == "packages" and len(parts) < 4:
            raise SupervisorError("Architecture plan package scope is too broad")
        if parts[0] == "tests" and len(parts) < 2:
            raise SupervisorError("Architecture plan may not authorize the entire tests tree")
        normalized.append(path)
    return tuple(dict.fromkeys(normalized))


def _architecture_escalation(
    config: SupervisorConfig,
    runner: Runner,
    artifact_dir: Path,
    active: ActiveItem,
    outcome: ExecutorOutcome,
) -> tuple[ArchitecturePlan, ArchitectureReview]:
    prior_plan: ArchitecturePlan | None = None
    feedback: tuple[str, ...] = ()
    for attempt in range(1, config.max_architecture_attempts + 1):
        plan_raw = _invoke_codex(
            config,
            runner,
            artifact_dir,
            phase=f"architecture-{attempt}",
            prompt=_architecture_prompt(active, outcome, prior_plan, feedback),
            schema=ARCHITECTURE_SCHEMA,
            model=config.architecture_model,
            effort=config.architecture_effort,
            read_only=True,
        )
        plan = ArchitecturePlan.from_json(plan_raw)
        validate_architecture_plan(plan, active)
        review_raw = _invoke_codex(
            config,
            runner,
            artifact_dir,
            phase=f"architecture-review-{attempt}",
            prompt=_review_prompt(active, plan),
            schema=REVIEW_SCHEMA,
            model=config.architecture_model,
            effort=config.architecture_effort,
            read_only=True,
        )
        review = ArchitectureReview.from_json(review_raw)
        if review.status is ReviewStatus.APPROVED:
            return plan, review
        if review.status is ReviewStatus.HUMAN_REQUIRED:
            raise SupervisorError(review.human_reason or review.summary)
        prior_plan = plan
        feedback = review.revision_guidance or review.findings
    raise SupervisorError(
        f"Architecture plan was not approved after {config.max_architecture_attempts} attempts"
    )


def _write_scope_authorization(
    path: Path,
    *,
    config: SupervisorConfig,
    runner: Runner,
    active: ActiveItem,
    plan: ArchitecturePlan,
    allowed_paths: Sequence[str],
) -> str:
    plan_sha256 = hashlib.sha256(plan.canonical_json().encode()).hexdigest()
    payload: JsonObject = {
        "version": 1,
        "branch": _git_output(config, runner, "rev-parse", "--abbrev-ref", "HEAD"),
        "item_number": active.number,
        "baseline_sha": active.baseline_sha,
        "allowed_paths": list(allowed_paths),
        "plan_sha256": plan_sha256,
        "architect_model": config.architecture_model,
        "architecture_effort": config.architecture_effort,
        "review_status": ReviewStatus.APPROVED.value,
    }
    _write_json(path, payload)
    return plan_sha256


def _record_approved_plan(active: ActiveItem, plan: ArchitecturePlan, plan_sha256: str) -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    paths = ", ".join(f"`{path}`" for path in plan.allowed_paths)
    entry = (
        f"\n## Autonomous architecture approval ({timestamp})\n\n"
        f"Item {active.number} - {active.title} was escalated to a read-only architect and an "
        f"independent reviewer. Plan SHA-256: `{plan_sha256}`.\n\n"
        f"Decision: {plan.decision}\n\nAuthorized technical paths: {paths}.\n"
    )
    with (active.repo / ".handoff" / "STATE.md").open("a", encoding="utf-8") as state_file:
        state_file.write(entry)


def _append_hard_halt(repo: Path, reason: str) -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = (
        f"\n## Autonomous loop HALT ({timestamp})\n\n"
        "HUMAN_REQUIRED: autonomous architecture supervisor stopped. "
        f"{reason}\n\n"
        "The loop stopped itself. Do not restart it against the same queue item without "
        "addressing the reason above first.\n"
    )
    with (repo / ".handoff" / "STATE.md").open("a", encoding="utf-8") as state_file:
        state_file.write(entry)


def run_supervisor(config: SupervisorConfig, runner: Runner = default_runner) -> int:
    branch = _git_output(config, runner, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch.startswith(("feature/", "fix/")):
        raise SupervisorError(f"Refusing to run the supervisor on branch {branch!r}")
    if not _worktree_is_clean(config, runner):
        raise SupervisorError("The supervisor must start from a clean worktree")
    control_snapshot = _capture_control_snapshot(config)

    artifact_dir = _create_artifact_dir(config)
    print(f"Supervisor artifacts: {artifact_dir}")
    authorization_path: Path | None = None
    approved_plan: ArchitecturePlan | None = None

    initial_gate = _run_gate(config, runner)
    if initial_gate.returncode == 0:
        print(initial_gate.stdout.strip())
        return 0
    if initial_gate.returncode == 2:
        raise SupervisorError(initial_gate.stderr.strip() or initial_gate.stdout.strip())
    if initial_gate.returncode != 1:
        raise SupervisorError(f"Autonomous gate returned unexpected exit {initial_gate.returncode}")

    for turn in range(1, config.max_turns + 1):
        active = _active_item(config)
        turn_dir = artifact_dir / f"turn-{turn:03d}-item-{active.number}"
        turn_dir.mkdir()
        raw = _invoke_codex(
            config,
            runner,
            turn_dir,
            phase="executor",
            prompt=_executor_prompt(active, approved_plan),
            schema=EXECUTOR_SCHEMA,
            model=config.implementation_model,
            effort=config.implementation_effort,
            read_only=False,
        )
        _verify_control_snapshot(config, control_snapshot)
        outcome = ExecutorOutcome.from_json(raw)
        print(f"Turn {turn}, Item {active.number}: {outcome.status.value} - {outcome.summary}")

        if outcome.status is TurnStatus.HUMAN_REQUIRED:
            raise SupervisorError(outcome.halt_reason or outcome.summary)
        if outcome.status is TurnStatus.ARCHITECTURE_REQUIRED:
            if not _worktree_is_clean(config, runner):
                raise SupervisorError(
                    "Architecture escalation was requested after uncommitted changes; refusing "
                    "to design over a partial implementation"
                )
            plan, _ = _architecture_escalation(config, runner, turn_dir, active, outcome)
            _verify_control_snapshot(config, control_snapshot)
            allowed_paths = validate_architecture_plan(plan, active)
            authorization_path = artifact_dir / f"item-{active.number}-scope-authorization.json"
            plan_sha256 = _write_scope_authorization(
                authorization_path,
                config=config,
                runner=runner,
                active=active,
                plan=plan,
                allowed_paths=allowed_paths,
            )
            _record_approved_plan(active, plan, plan_sha256)
            approved_plan = plan
            print(
                f"Architecture approved for Item {active.number}: {plan.decision} "
                f"(plan {plan_sha256[:12]})"
            )
            continue

        tasks_done, _ = autonomous_gate.completed_task_count(active.tasks_file)
        next_item = autonomous_gate.item_for_done_count(autonomous_gate.parse_queue(), tasks_done)
        if next_item is None or next_item.number != active.number:
            authorization_path = None
            approved_plan = None
        _verify_control_snapshot(config, control_snapshot)
        gate_result = _run_gate(config, runner, authorization_path)
        print((gate_result.stdout or gate_result.stderr).strip())
        if gate_result.returncode == 0:
            return 0
        if gate_result.returncode == 2:
            raise SupervisorError(gate_result.stderr.strip() or gate_result.stdout.strip())
        if gate_result.returncode != 1:
            raise SupervisorError(
                f"Autonomous gate returned unexpected exit {gate_result.returncode}"
            )

    raise SupervisorError(f"Supervisor reached its maximum of {config.max_turns} Codex turns")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument(
        "--implementation-model",
        default=os.environ.get("CODEX_MODEL", DEFAULT_IMPLEMENTATION_MODEL),
    )
    parser.add_argument(
        "--architecture-model",
        default=os.environ.get("CODEX_ARCHITECTURE_MODEL", DEFAULT_ARCHITECTURE_MODEL),
    )
    parser.add_argument(
        "--implementation-effort",
        default=os.environ.get("CODEX_REASONING_EFFORT", DEFAULT_IMPLEMENTATION_EFFORT),
    )
    parser.add_argument(
        "--architecture-effort",
        default=os.environ.get("CODEX_ARCHITECTURE_REASONING_EFFORT", DEFAULT_ARCHITECTURE_EFFORT),
    )
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--max-architecture-attempts", type=int, default=MAX_ARCHITECTURE_ATTEMPTS)
    parser.add_argument("--max-process-retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=int, default=30)
    parser.add_argument("--search", action="store_true", dest="use_live_search")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if (
        args.max_turns < 1
        or args.max_architecture_attempts not in {1, 2}
        or args.max_process_retries < 0
        or args.retry_delay_seconds < 0
    ):
        print(
            "invalid turn, architecture-attempt, process-retry, or retry-delay limit",
            file=sys.stderr,
        )
        return 2
    config = SupervisorConfig(
        repo=args.repo.resolve(),
        codex_command=args.codex_command,
        implementation_model=args.implementation_model,
        architecture_model=args.architecture_model,
        implementation_effort=args.implementation_effort,
        architecture_effort=args.architecture_effort,
        max_turns=args.max_turns,
        max_architecture_attempts=args.max_architecture_attempts,
        max_process_retries=args.max_process_retries,
        retry_delay_seconds=args.retry_delay_seconds,
        use_live_search=args.use_live_search,
    )
    if config.repo != ROOT.resolve():
        print(
            "HUMAN_REQUIRED: the loaded supervisor does not belong to --repo; launch it from the "
            "selected repository root",
            file=sys.stderr,
        )
        return 2
    try:
        return run_supervisor(config)
    except (SupervisorError, OSError, subprocess.SubprocessError) as exc:
        _append_hard_halt(config.repo, str(exc))
        print(f"HUMAN_REQUIRED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

"""LangGraph checkpoint persistence survives a real process restart.

`spec.md`: "LangGraph checkpoint persistence across a process restart is the riskiest technical
unknown - test it early (acceptance criterion 7), not at the end." This is that test.

The interrupt is raised in one OS process, and the checkpoint is read and resumed from a
genuinely separate process invocation - not just two objects constructed in the same pytest
run, which would prove nothing about surviving a real restart. See
`docs/playbooks/langgraph-node.md`: "Test resumability explicitly: interrupt, persist, restart
the process, resume. A HITL flow that only works in a warm process is not a HITL flow."
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_FIXTURES_DIR = Path(__file__).parent / "_checkpoint_restart_fixtures"


def _run(script: str, thread_id: str, dsn: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_FIXTURES_DIR / script), thread_id, dsn],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_interrupt_persists_and_resumes_after_a_real_process_restart(postgres_dsn: str) -> None:
    thread_id = f"test-restart-{uuid.uuid4()}"

    start = _run("_start_and_interrupt.py", thread_id, postgres_dsn)
    assert start.returncode == 0, f"first process failed:\n{start.stdout}\n{start.stderr}"
    assert "INTERRUPTED" in start.stdout, start.stdout

    # `subprocess.run` above blocked until that process fully exited - the resume below cannot
    # be served from anything held in this test process's memory.
    resume = _run("_resume_after_restart.py", thread_id, postgres_dsn)
    assert resume.returncode == 0, f"second process failed:\n{resume.stdout}\n{resume.stderr}"
    assert "RESUMED_CORRECTLY" in resume.stdout, resume.stdout

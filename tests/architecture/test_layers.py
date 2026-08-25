"""Clean Architecture boundaries, enforced as a test.

The contracts live in `pyproject.toml` under `[tool.importlinter]`. Running them here means a
boundary violation fails the normal test run, not only CI — the feedback arrives while the code is
still in someone's head.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    shutil.which("lint-imports") is None,
    reason="import-linter not installed (pip install -e '.[dev]')",
)
def test_layer_contracts_hold() -> None:
    result = subprocess.run(
        ["lint-imports"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Clean Architecture contract broken.\n"
        "Dependencies point inward: domain <- application <- infrastructure <- apps.\n"
        "See the layer table in AGENTS.md and the README of each layer.\n\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_domain_has_no_framework_imports() -> None:
    """Cheap textual guard that runs even without import-linter installed.

    It reads source rather than importing, so it works on a skeleton with no dependencies yet.
    """
    banned = (
        "import pydantic",
        "from pydantic",
        "import sqlalchemy",
        "from sqlalchemy",
        "import fastapi",
        "from fastapi",
        "import langgraph",
        "from langgraph",
        "import httpx",
        "from httpx",
        "import redis",
        "from redis",
        "import celery",
        "from celery",
    )
    domain = ROOT / "packages" / "core" / "revops" / "domain"
    offenders: list[str] = []

    for path in domain.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if any(stripped.startswith(pattern) for pattern in banned):
                offenders.append(f"{path.relative_to(ROOT)}:{line_number}: {stripped}")

    assert not offenders, (
        "The domain layer must depend on the standard library only. Move the framework code into "
        "infrastructure and talk to it through an application port.\n" + "\n".join(offenders)
    )

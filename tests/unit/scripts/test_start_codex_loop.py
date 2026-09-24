from __future__ import annotations

from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "start_codex_loop.ps1"


def test_launcher_leaves_temp_selection_to_the_supervisor() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "$env:TEMP =" not in source
    assert "$env:TMP =" not in source
    assert "$env:PYTEST_ADDOPTS =" not in source
    assert "supervisor owns temporary-directory selection" in source
    assert "Get-Command codex.exe -ErrorAction SilentlyContinue" in source
    assert '"--codex-command", $codexExecutable' in source
    assert "Could not locate the native Codex executable" in source
    assert '"--codex-command", "codex.cmd"' not in source


def test_cleanup_script_is_scoped_and_dry_run_by_default() -> None:
    cleanup = Path(__file__).resolve().parents[3] / "scripts" / "cleanup_codex_temp.ps1"
    source = cleanup.read_text(encoding="utf-8")

    assert '"codex-revops-*"' in source
    assert "-ConfirmCleanup" in source
    assert "-Recurse -Force" in source
    assert "Refusing to remove path outside Codex temp root" in source
    assert "Refusing to remove reparse point" in source

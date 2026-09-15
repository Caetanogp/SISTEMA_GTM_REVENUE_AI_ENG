from __future__ import annotations

from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "start_codex_loop.ps1"


def test_launcher_uses_explicit_external_temp_root() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert (
        '$codexTempRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData"))'
        in source
    )
    assert '"Codex\\Temp"' in source
    assert "$pytestBaseTemp = Join-Path $codexTempRoot" in source
    assert "$pytestBaseTemp = Join-Path $env:TEMP" not in source
    assert "temporary directory resolved inside repository" in source
    assert "temporary directory is a reparse point" in source


def test_cleanup_script_is_scoped_and_dry_run_by_default() -> None:
    cleanup = Path(__file__).resolve().parents[3] / "scripts" / "cleanup_codex_temp.ps1"
    source = cleanup.read_text(encoding="utf-8")

    assert '"codex-revops-*"' in source
    assert "-ConfirmCleanup" in source
    assert "-Recurse -Force" in source
    assert "Refusing to remove path outside Codex temp root" in source
    assert "Refusing to remove reparse point" in source

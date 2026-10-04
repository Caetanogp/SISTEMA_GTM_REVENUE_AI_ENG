"""Tests for the deployment-only platform seed command."""

from __future__ import annotations

from uuid import uuid4

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from apps import platform_seed


def test_platform_seed_rejects_all_runtime_arguments(capsys: CaptureFixture[str]) -> None:
    assert platform_seed.main(["--tenant", "attacker"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "platform_seed_invalid_arguments\n"


def test_platform_seed_prints_only_safe_counts_and_identifiers(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    corpus_id = uuid4()
    monkeypatch.setattr(
        platform_seed,
        "_run_async",
        lambda *, settings: platform_seed.PlatformSeedCliResult(corpus_id, 2, 1, 0),
    )

    assert platform_seed.main([]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        f"platform_seed_success corpus_id={corpus_id} reserved=2 redispatched=1 ready=0\n"
    )


def test_platform_seed_never_leaks_injected_exception_text(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    secret = "sk-live-credential https://example.invalid source document body"

    def fail(
        *, settings: platform_seed.PlatformSeedSettings
    ) -> platform_seed.PlatformSeedCliResult:
        raise RuntimeError(secret)

    monkeypatch.setattr(platform_seed, "_run_async", fail)

    assert platform_seed.main([]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "platform_seed_failed\n"
    assert secret not in captured.out + captured.err

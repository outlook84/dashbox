from __future__ import annotations

import sys

import scripts.resolve_ytdlp_release_intent as intent


def run_intent(monkeypatch, capsys, *, version: str, tag_exists: bool, current: str, updated: str) -> dict[str, str]:
    monkeypatch.setattr(intent, "project_version", lambda: version)
    monkeypatch.setattr(intent, "tag_exists", lambda tag: tag_exists)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve_ytdlp_release_intent.py",
            "--current-ytdlp-version",
            current,
            "--updated-ytdlp-version",
            updated,
        ],
    )

    assert intent.main() == 0
    lines = capsys.readouterr().out.splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_skips_when_ytdlp_version_and_current_release_tag_are_current(monkeypatch, capsys) -> None:
    outputs = run_intent(
        monkeypatch,
        capsys,
        version="0.1.1.post202605200323",
        tag_exists=True,
        current="2026.5.16",
        updated="2026.5.16",
    )

    assert outputs == {
        "package_base": "0.1.1",
        "ref_base": "0.1.1",
        "should_release": "false",
    }


def test_releases_when_ytdlp_version_is_current_but_release_tag_is_missing(monkeypatch, capsys) -> None:
    outputs = run_intent(
        monkeypatch,
        capsys,
        version="0.1.1.post202605200323",
        tag_exists=False,
        current="2026.5.16",
        updated="2026.5.16",
    )

    assert outputs == {
        "package_base": "0.1.1",
        "ref_base": "",
        "should_release": "true",
    }


def test_releases_when_base_version_has_no_release_tag(monkeypatch, capsys) -> None:
    outputs = run_intent(
        monkeypatch,
        capsys,
        version="0.1.1",
        tag_exists=False,
        current="2026.5.16",
        updated="2026.5.16",
    )

    assert outputs == {
        "package_base": "0.1.1",
        "ref_base": "",
        "should_release": "true",
    }


def test_releases_when_ytdlp_version_changes(monkeypatch, capsys) -> None:
    outputs = run_intent(
        monkeypatch,
        capsys,
        version="0.1.1",
        tag_exists=True,
        current="2026.5.16",
        updated="2026.5.20",
    )

    assert outputs == {
        "package_base": "0.1.1",
        "ref_base": "0.1.1",
        "should_release": "true",
    }

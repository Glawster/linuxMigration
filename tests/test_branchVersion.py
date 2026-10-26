"""Tests for branchVersion.py: numbering branches and tagging merged work."""

import subprocess
from pathlib import Path

import pytest

import branchVersion

GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@example.com"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *GIT_IDENTITY, *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commitVersion(root: Path, version: str, message: str) -> None:
    (root / "VERSION").write_text(f"{version}\n")
    _git(root, "add", "VERSION")
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone of a bare origin whose main is at VERSION 1.3, tagged v1.3."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "t")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "t@example.com")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    root = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(root))
    _git(root, "switch", "-q", "-c", "main")
    _commitVersion(root, "1.3", "release 1.3")
    _git(root, "tag", "-a", "v1.3", "-m", "Release v1.3")
    _git(root, "push", "-q", "origin", "main", "v1.3")
    return root


def _run(root: Path, *argv: str) -> int:
    return branchVersion.main(list(argv), root=root)


@pytest.mark.parametrize(
    "known, expected",
    [
        (["1.3"], "1.4a1"),
        (["1.3", "1.4a1"], "1.4a2"),
        (["1.4a2", "1.4a1", "1.3"], "1.4a3"),
        (["1.4a9", "1.4a10"], "1.4a11"),
        (["1.4a3", "1.4"], "1.5a1"),
        (["1.4", "1.4.1"], "1.5a1"),
        (["1.4", "1.4.1a1"], "1.4.1a2"),
    ],
)
def testNextVersion(known: list[str], expected: str) -> None:
    assert branchVersion.nextVersion(known) == expected


def testRejectsNonVersions() -> None:
    with pytest.raises(branchVersion.VersionError):
        branchVersion.parseVersion("1.4-rc1")


def testStartPreviewChangesNothing(
    clone: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(clone, "switch", "-q", "-c", "feature/one")
    assert _run(clone, "start") == 0
    assert "set VERSION to 1.4a1" in capsys.readouterr().out
    assert (clone / "VERSION").read_text().strip() == "1.3"


def testStartNumbersTheBranchAndCommits(clone: Path) -> None:
    _git(clone, "switch", "-q", "-c", "feature/one")
    assert _run(clone, "start", "--confirm") == 0
    assert (clone / "VERSION").read_text().strip() == "1.4a1"
    assert (
        _git(clone, "log", "-1", "--format=%s")
        == "Set VERSION to 1.4a1 for feature/one"
    )


def testStartIsIdempotent(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(clone, "switch", "-q", "-c", "feature/one")
    _run(clone, "start", "--confirm")
    capsys.readouterr()
    assert _run(clone, "start", "--confirm") == 0
    assert "already numbered 1.4a1" in capsys.readouterr().out
    assert (clone / "VERSION").read_text().strip() == "1.4a1"


def testStartSkipsNumbersTakenByOtherBranches(clone: Path) -> None:
    _git(clone, "switch", "-q", "-c", "feature/one")
    _run(clone, "start", "--confirm")
    _git(clone, "push", "-q", "origin", "feature/one")
    _git(clone, "switch", "-q", "main")
    _git(clone, "branch", "-q", "-D", "feature/one")
    _git(clone, "switch", "-q", "-c", "feature/two")
    assert _run(clone, "start", "--confirm") == 0
    assert (clone / "VERSION").read_text().strip() == "1.4a2"


def testStartSkipsNumbersAlreadyTagged(clone: Path) -> None:
    _git(clone, "tag", "-a", "v1.4a5", "-m", "1.4a5")
    _git(clone, "switch", "-q", "-c", "feature/one")
    _run(clone, "start", "--confirm")
    assert (clone / "VERSION").read_text().strip() == "1.4a6"


def testStartRefusesMain(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(clone, "start", "--confirm") == 1
    assert "create one from main first" in capsys.readouterr().err
    assert (clone / "VERSION").read_text().strip() == "1.3"


def _mergeBranch(clone: Path, version: str) -> None:
    """Simulate a squash merge of a branch numbered ``version`` into main."""
    _commitVersion(clone, version, f"Work numbered {version} (#1)")
    _git(clone, "push", "-q", "origin", "main")


def testTagPreviewThenConfirmTagsAndPushes(
    clone: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _mergeBranch(clone, "1.4a1")
    assert _run(clone, "tag") == 0
    assert "tag main (Work numbered 1.4a1 (#1)) as v1.4a1" in capsys.readouterr().out
    assert _git(clone, "tag", "--list", "v1.4a1") == ""
    assert _run(clone, "tag", "--confirm") == 0
    assert _git(clone, "rev-list", "-n", "1", "v1.4a1") == _git(
        clone, "rev-parse", "HEAD"
    )
    assert "1.4a1: Work numbered 1.4a1 (#1)" in _git(
        clone, "tag", "-n1", "--list", "v1.4a1"
    )
    assert "refs/tags/v1.4a1" in _git(clone, "ls-remote", "--tags", "origin")


def testTagIsIdempotentButNeverMoved(
    clone: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _mergeBranch(clone, "1.4a1")
    _run(clone, "tag", "--confirm")
    capsys.readouterr()
    assert _run(clone, "tag", "--confirm") == 0
    assert "already on this commit" in capsys.readouterr().out
    (clone / "notes.md").write_text("later\n")
    _git(clone, "add", "notes.md")
    _git(clone, "commit", "-q", "-m", "later work without a new number")
    _git(clone, "push", "-q", "origin", "main")
    assert _run(clone, "tag", "--confirm") == 1
    assert "tags are never moved" in capsys.readouterr().err


def testTagRefusesABranch(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(clone, "switch", "-q", "-c", "feature/one")
    assert _run(clone, "tag", "--confirm") == 1
    assert "after the squash merge" in capsys.readouterr().err


def testTagRefusesMainBehindOrigin(
    clone: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _mergeBranch(clone, "1.4a1")
    _git(clone, "reset", "-q", "--hard", "HEAD~1")
    assert _run(clone, "tag", "--confirm") == 1
    assert "git pull --ff-only" in capsys.readouterr().err

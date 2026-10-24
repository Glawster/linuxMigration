"""Tests for the repository version helpers (repoVersion.py, repoVersion.sh)."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import repoVersion as repoVersionModule

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _bashDescribe(root: Path) -> str:
    return subprocess.run(
        ["bash", "-c", f'source "{root}/repoVersion.sh" && repoVersionDescribe'],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A copy of the helpers with VERSION 2.5, not yet a git repository."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(REPO_ROOT / "repoVersion.sh", root)
    (root / "VERSION").write_text("2.5\n")
    return root


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "-m",
        message,
    )


def testVersionFileWithoutGit(checkout: Path) -> None:
    assert repoVersionModule.repoVersion(checkout) == "2.5"
    assert _bashDescribe(checkout) == "2.5"


def testUntaggedCheckoutShowsVersionAndCommit(checkout: Path) -> None:
    _git(checkout, "init", "-q")
    _commit(checkout, "first")
    assert re.fullmatch(
        r"2\.5 \([0-9a-f]{7,}\)", repoVersionModule.repoVersion(checkout)
    )
    assert re.fullmatch(r"2\.5 \([0-9a-f]{7,}\)", _bashDescribe(checkout))


def testTaggedCheckoutShowsTag(checkout: Path) -> None:
    _git(checkout, "init", "-q")
    _commit(checkout, "first")
    _git(
        checkout,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "tag",
        "-a",
        "v2.5",
        "-m",
        "Release v2.5",
    )
    assert repoVersionModule.repoVersion(checkout) == "v2.5"
    assert _bashDescribe(checkout) == "v2.5"


def testLaterAndDirtyCheckouts(checkout: Path) -> None:
    _git(checkout, "init", "-q")
    _commit(checkout, "first")
    _git(
        checkout,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "tag",
        "-a",
        "v2.5",
        "-m",
        "Release v2.5",
    )
    (checkout / "tool.sh").write_text("echo one\n")
    _commit(checkout, "second")
    assert re.fullmatch(r"v2\.5-1-g[0-9a-f]+", repoVersionModule.repoVersion(checkout))
    (checkout / "tool.sh").write_text("echo two\n")
    assert re.fullmatch(r"v2\.5-1-g[0-9a-f]+-dirty", _bashDescribe(checkout))
    assert repoVersionModule.repoVersion(checkout).endswith("-dirty")


def testRepositoryVersionFileIsReleaseNumber() -> None:
    assert re.fullmatch(
        r"\d+\.\d+(\.\d+)?", (REPO_ROOT / "VERSION").read_text().strip()
    )

#!/usr/bin/env python3
"""Number branches and tag merged work with the repository version.

Every branch of work gets the next free pre-release number of the coming
release (1.4a1, 1.4a2, ...) in ``VERSION``; after its squash merge, the merge
commit on ``main`` is tagged ``v<VERSION>``. A release sets ``VERSION`` to
``X.Y`` and the next branch starts ``X.(Y+1)a1``. See
.github/additional-instructions.md ("Versioning and releases") and ADR 009.

Usage::

    branchVersion show                 # this checkout's version and the next free one
    branchVersion start [--confirm]    # number the current branch
    branchVersion tag [--confirm]      # tag the merged work on main
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from repoVersion import REPO_ROOT, repoVersion

VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?(?:a(\d+))?")
MAIN_BRANCH = "main"
REMOTE = "origin"


class VersionError(Exception):
    """A version operation that cannot go ahead."""


def parseVersion(text: str) -> tuple[str, int | None]:
    """Return (release part, pre-release number or None) for ``X.Y[.Z][aN]``."""
    match = VERSION_PATTERN.fullmatch(text.strip())
    if not match:
        raise VersionError(f"not a version: {text.strip()!r}")
    pre = match.group(4)
    return text.strip().split("a")[0], int(pre) if pre else None


def versionKey(text: str) -> tuple[int, int, int, float]:
    """Sort key: 1.4a1 < 1.4a2 < 1.4 < 1.4.1a1 < 1.4.1 < 1.5a1."""
    match = VERSION_PATTERN.fullmatch(text.strip())
    if not match:
        raise VersionError(f"not a version: {text.strip()!r}")
    major, minor, patch, pre = match.groups()
    return int(major), int(minor), int(patch or 0), float(pre) if pre else float("inf")


def nextVersion(known: list[str]) -> str:
    """The next free pre-release number after every version in ``known``.

    After a release (1.4 or 1.4.1) the next branch starts the following minor
    release at a1; during a pre-release series it takes the next aN.
    """
    release, pre = parseVersion(max(known, key=versionKey))
    if pre is None:
        major, minor = release.split(".")[:2]
        return f"{major}.{int(minor) + 1}a1"
    return f"{release}a{pre + 1}"


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` and return its trimmed output."""
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise VersionError(error.stderr.strip() or f"git {' '.join(args)} failed")


def hasRemote(root: Path) -> bool:
    return REMOTE in git(root, "remote").split()


def knownVersions(root: Path) -> list[str]:
    """Every version already taken: tags, VERSION on main and on every branch."""
    versions = [
        tag[1:]
        for tag in git(root, "tag", "--list", "v[0-9]*").split()
        if VERSION_PATTERN.fullmatch(tag[1:])
    ]
    refs = git(
        root,
        "for-each-ref",
        "--format=%(refname)",
        "refs/heads",
        f"refs/remotes/{REMOTE}",
    ).split()
    for ref in refs:
        if ref.endswith("/HEAD"):
            continue
        try:
            text = git(root, "show", f"{ref}:VERSION")
        except VersionError:
            continue
        if VERSION_PATTERN.fullmatch(text):
            versions.append(text)
    return versions


def currentBranch(root: Path) -> str:
    branch = git(root, "branch", "--show-current")
    if not branch:
        raise VersionError("not on a branch (detached HEAD)")
    return branch


def mainVersion(root: Path) -> str:
    ref = f"{REMOTE}/{MAIN_BRANCH}" if hasRemote(root) else MAIN_BRANCH
    return git(root, "show", f"{ref}:VERSION")


def fetch(root: Path) -> None:
    if hasRemote(root):
        git(root, "fetch", "--quiet", "--tags", "--prune", REMOTE)


def commandShow(root: Path, _args: argparse.Namespace) -> int:
    fetch(root)
    print(f"Checkout:  {repoVersion(root)}")
    print(f"VERSION:   {(root / 'VERSION').read_text().strip()}")
    print(f"Next free: {nextVersion(knownVersions(root))}")
    return 0


def commandStart(root: Path, args: argparse.Namespace) -> int:
    fetch(root)
    branch = currentBranch(root)
    if branch == MAIN_BRANCH:
        raise VersionError(
            f"start numbers a branch of work; create one from {MAIN_BRANCH} first"
        )
    current = (root / "VERSION").read_text().strip()
    if current != mainVersion(root):
        print(f"{branch} is already numbered {current}.")
        return 0
    version = nextVersion(knownVersions(root))
    if not args.confirm:
        print(f"...[] set VERSION to {version} and commit it on {branch}")
        print("Preview only: re-run with --confirm.")
        return 0
    (root / "VERSION").write_text(f"{version}\n")
    git(root, "add", "VERSION")
    git(root, "commit", "--quiet", "-m", f"Set VERSION to {version} for {branch}")
    print(f"...{branch} is numbered {version}")
    return 0


def commandTag(root: Path, args: argparse.Namespace) -> int:
    fetch(root)
    if currentBranch(root) != MAIN_BRANCH:
        raise VersionError(f"tag runs on {MAIN_BRANCH} after the squash merge")
    if hasRemote(root) and git(root, "rev-parse", "HEAD") != git(
        root, "rev-parse", f"{REMOTE}/{MAIN_BRANCH}"
    ):
        raise VersionError(
            f"{MAIN_BRANCH} is not at {REMOTE}/{MAIN_BRANCH}; run git pull --ff-only"
        )
    version = (root / "VERSION").read_text().strip()
    parseVersion(version)
    tag = f"v{version}"
    if git(root, "tag", "--list", tag):
        tagged = git(root, "rev-list", "-n", "1", tag)
        if tagged == git(root, "rev-parse", "HEAD"):
            print(f"{tag} is already on this commit.")
            return 0
        raise VersionError(f"{tag} already tags {tagged[:7]}; tags are never moved")
    subject = git(root, "log", "-1", "--format=%s")
    if not args.confirm:
        print(f"...[] tag {MAIN_BRANCH} ({subject}) as {tag}")
        print("Preview only: re-run with --confirm.")
        return 0
    git(root, "tag", "-a", tag, "-m", f"{version}: {subject}")
    if hasRemote(root):
        git(root, "push", "--quiet", REMOTE, tag)
    print(f"...tagged {tag}")
    return 0


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="branchVersion",
        description="Number branches and tag merged work with the repository version.",
    )
    parser.add_argument(
        "--version", action="version", version=f"branchVersion {repoVersion()}"
    )
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser(
        "show", help="show this checkout's version and the next free number"
    )
    for name, helpText in (
        ("start", "set VERSION on the current branch to the next free number"),
        ("tag", "tag the merged work on main as v<VERSION>"),
    ):
        action = actions.add_parser(name, help=helpText)
        action.add_argument(
            "--confirm", action="store_true", help="make the change (default: preview)"
        )
    return parser


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    args = buildParser().parse_args(argv)
    handler = {"show": commandShow, "start": commandStart, "tag": commandTag}[
        args.action
    ]
    try:
        return handler(root, args)
    except VersionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""scanToInbox.sh builds a NAPS2 duplex scan into the Inbox.

The real script runs. naps2 is a stand-in on PATH, so no scanner is used.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import organiseMyProjects

SCRIPT = Path(__file__).resolve().parents[1] / "scanToInbox.sh"
LOG_UTILS = Path(organiseMyProjects.__file__).resolve().parent / "logUtils.sh"

_FAKE_NAPS2 = """#!/bin/bash
printf '%s\\n' "$@" > "$NAPS2_ARGS"
if [[ "${NAPS2_NO_FILE:-}" == 1 ]]; then
    exit 0
fi
if [[ " $* " == *" --listdevices "* ]]; then
    echo "device epjitsu:libusb:001:005 is a FUJITSU ScanSnap S1300i"
    exit 0
fi
out=""
prev=""
for arg in "$@"; do
    if [[ "$prev" == "-o" ]]; then
        out=$arg
    fi
    prev=$arg
done
if [[ -n "$out" ]]; then
    printf '%%PDF-1.4\\n' > "$out"
fi
exit 0
"""


def _run(tmp_path: Path, *args: str, naps2: bool = True, no_file: bool = False):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    if naps2:
        fake = bindir / "naps2"
        fake.write_text(_FAKE_NAPS2)
        fake.chmod(0o755)
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PATH=f"{bindir}:/usr/bin:/bin",
        LOG_UTILS=str(LOG_UTILS),
        NAPS2_ARGS=str(tmp_path / "args.txt"),
        NAPS2_NO_FILE="1" if no_file else "",
    )
    result = subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    result.output = result.stdout + result.stderr
    args_file = tmp_path / "args.txt"
    result.naps2_args = args_file.read_text() if args_file.is_file() else ""
    return result


def test_helpDoesNotScan(tmp_path: Path) -> None:
    result = _run(tmp_path, "--help", naps2=False)

    assert result.returncode == 0, result.output
    assert "duplex" in result.stdout
    assert result.naps2_args == ""


def test_missingNaps2Fails(tmp_path: Path) -> None:
    inbox = tmp_path / "Inbox"
    inbox.mkdir()

    result = _run(tmp_path, "--inbox", str(inbox), naps2=False)

    assert result.returncode == 1
    assert "naps2 not found" in result.output
    assert result.naps2_args == ""


def test_missingInboxFailsBeforeScan(tmp_path: Path) -> None:
    result = _run(tmp_path, "--inbox", str(tmp_path / "missing"))

    assert result.returncode == 1
    assert "Inbox folder not found" in result.output
    assert result.naps2_args == ""


def test_defaultIsDuplexIntoTheInbox(tmp_path: Path) -> None:
    inbox = tmp_path / "Inbox"
    inbox.mkdir()

    result = _run(tmp_path, "--inbox", str(inbox))

    assert result.returncode == 0, result.output
    written = list(inbox.glob("*.pdf"))
    assert len(written) == 1
    assert len(written[0].name) == len("2026-11-23-143012.pdf")
    args = result.naps2_args.splitlines()
    assert args[0] == "console"
    assert "--noprofile" in args
    assert "--driver" in args and args[args.index("--driver") + 1] == "sane"
    assert args[args.index("--device") + 1] == "ScanSnap"
    assert args[args.index("--source") + 1] == "duplex"
    assert args[args.index("--pagesize") + 1] == "a4"
    assert args[args.index("--dpi") + 1] == "300"
    assert args[args.index("--bitdepth") + 1] == "gray"
    assert "--deskew" in args
    assert args[args.index("--ocrlang") + 1] == "eng"
    assert args[args.index("-o") + 1] == str(written[0])


def test_frontAndColorOverrideTheDefaults(tmp_path: Path) -> None:
    inbox = tmp_path / "Inbox"
    inbox.mkdir()

    result = _run(tmp_path, "--inbox", str(inbox), "--front", "--color", "--device", "S1300i")

    assert result.returncode == 0, result.output
    args = result.naps2_args.splitlines()
    assert args[args.index("--source") + 1] == "feeder"
    assert args[args.index("--bitdepth") + 1] == "color"
    assert args[args.index("--device") + 1] == "S1300i"


def test_profileStillWritesToTheInbox(tmp_path: Path) -> None:
    inbox = tmp_path / "Inbox"
    inbox.mkdir()

    result = _run(tmp_path, "--inbox", str(inbox), "--profile", "Inbox duplex", "--front")

    assert result.returncode == 0, result.output
    args = result.naps2_args.splitlines()
    assert "--noprofile" not in args
    assert args[args.index("-p") + 1] == "Inbox duplex"
    assert args[args.index("--source") + 1] == "feeder"
    assert "--dpi" not in args
    assert (inbox / args[args.index("-o") + 1].split("/")[-1]).is_file()


def test_listDevicesDoesNotNeedAnInbox(tmp_path: Path) -> None:
    result = _run(tmp_path, "--list")

    assert result.returncode == 0, result.output
    assert "ScanSnap S1300i" in result.stdout
    assert "--listdevices" in result.naps2_args.splitlines()


def test_successWithoutAFileFails(tmp_path: Path) -> None:
    inbox = tmp_path / "Inbox"
    inbox.mkdir()

    result = _run(tmp_path, "--inbox", str(inbox), no_file=True)

    assert result.returncode == 1
    assert "without writing" in result.output
    assert list(inbox.glob("*.pdf")) == []


def test_unknownOptionFails(tmp_path: Path) -> None:
    result = _run(tmp_path, "--nope", naps2=False)

    assert result.returncode == 2
    assert "unknown option" in result.output

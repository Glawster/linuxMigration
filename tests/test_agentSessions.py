"""Exercise session discovery with synthetic stores and the real logging dependency."""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "agentSessions"
SESSION_ID = "12345678-1234-1234-1234-123456789abc"


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    """Load the extensionless command against an isolated home."""
    loader = importlib.machinery.SourceFileLoader("agentSessions", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setattr(module, "HOME", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / ".copilot"))
    module.setApplication("agentSessions", logDir=tmp_path / "logs")
    return module


def _fixtureWrite(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def teststoresCompose(sessions, tmp_path, capsys):
    """Real parsers compose into the listing and never rewrite source evidence."""
    cwd = str(tmp_path / "work")
    codex = _fixtureWrite(
        tmp_path / ".codex/sessions/2026/rollout-one.jsonl",
        "broken\n"
        + json.dumps(
            {"type": "session_meta", "payload": {"id": SESSION_ID, "cwd": cwd}}
        ),
    )
    claude = _fixtureWrite(
        tmp_path / f".claude/projects/work/{SESSION_ID}.jsonl", json.dumps({"cwd": cwd})
    )
    grok = _fixtureWrite(
        tmp_path / f".grok/sessions/{quote(cwd, safe='')}/{SESSION_ID}/summary.json",
        "{}",
    )
    copilot = _fixtureWrite(
        tmp_path / f".copilot/session-state/{SESSION_ID}/events.jsonl",
        json.dumps({"type": "session.start", "data": {"context": {"cwd": cwd}}}),
    )
    _fixtureWrite(copilot.parent / "workspace.yaml", f'cwd: "{cwd}"\n')
    _fixtureWrite(grok.parent / f"subagents/{SESSION_ID}/summary.json", "{}")
    before = {
        p: p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file() and "logs" not in p.parts
    }

    rows = sessions.sessionsCollect()
    sessions.tablePrint(rows, full_ids=True)

    assert {r["agent"] for r in rows} == {"Codex", "Claude", "Grok", "Copilot"}
    assert len(rows) == 4
    assert all(
        r["directory"] == "~/work" and r["session_id"] == SESSION_ID for r in rows
    )
    assert SESSION_ID in capsys.readouterr().out
    assert all(p.read_bytes() == content for p, content in before.items())


def testmalformedAndFallback(sessions, tmp_path):
    _fixtureWrite(tmp_path / ".codex/sessions/rollout-array.jsonl", "[]")
    _fixtureWrite(
        tmp_path / ".codex/sessions/rollout-null.jsonl",
        '{"type":"session_meta","payload":null}',
    )
    _fixtureWrite(
        tmp_path / ".codex/sessions/rollout-number.jsonl",
        '{"type":"session_meta","payload":{"id":12}}',
    )
    _fixtureWrite(tmp_path / ".claude/projects/work/not-a-session.jsonl", "{}")
    _fixtureWrite(
        tmp_path / ".copilot/session-state/empty/workspace.yaml", "cwd: /unused"
    )
    _fixtureWrite(
        tmp_path / f".copilot/session-state/{SESSION_ID}/events.jsonl",
        "bad\n[]\n"
        + json.dumps(
            {"type": "session.start", "data": {"workingDirectory": "/fallback"}}
        ),
    )
    rows = sessions.sessionsCollect()
    assert len(rows) == 1
    assert rows[0]["directory"] == "/fallback"


def testlatestAndRendering(sessions, tmp_path, capsys):
    path = _fixtureWrite(tmp_path / "stamp", "")
    older = {
        "agent": "Codex",
        "directory": "/work",
        "session_id": "old",
        "date": sessions.datetime.min,
    }
    newer = {**older, "session_id": SESSION_ID, "date": sessions._fileDate(path)}
    assert sessions.sessionsLatest([older, newer, older]) == [newer]
    rows = [older, newer]
    sessions.tablePrint(rows)
    assert rows == [older, newer]
    assert "12345678…" in capsys.readouterr().out
    assert sessions._textTruncate("abcdefghijk", 7) == "abc…ijk"
    assert sessions._textTruncate("abcdef", 3) == "abc"
    assert sessions._pathShorten(str(tmp_path)) == "~"
    assert sessions._pathShorten(None) == "?"
    assert sessions._pathShorten("bad\0path") == "?"


def testioFailureReports(sessions, tmp_path, caplog):
    assert sessions._jsonFirst(tmp_path / "missing") is None
    assert sessions._fileDate(tmp_path / "missing") == sessions.datetime.min
    assert sessions._yamlValue(tmp_path / "missing", "cwd") is None
    assert "cannot read session" in caplog.text


@pytest.mark.parametrize(
    "options",
    [[], ["--all", "--full"], ["--quiet"], ["--verbose"], ["--help"], ["--version"]],
)
def testcommandProductionPath(tmp_path, options):
    """Run the entry point with real logging and an empty isolated home."""
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "COPILOT_HOME": str(tmp_path / ".copilot"),
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *options], env=env, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    if "--help" not in options and "--version" not in options:
        assert "No local agent sessions found." in result.stdout
        assert list((tmp_path / ".local/state/agentSessions").glob("*.log"))


def testEntryPointComposition(sessions, tmp_path, monkeypatch, capsys):
    path = tmp_path / ".codex/sessions/rollout-real.jsonl"
    _fixtureWrite(
        path,
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"id": SESSION_ID, "cwd": str(tmp_path)},
            }
        ),
    )
    for options in (["--all", "--full"], [], ["--verbose"], ["--quiet"]):
        monkeypatch.setattr(sys, "argv", [str(SCRIPT), *options])
        assert sessions.main() == 0
        assert "Codex" in capsys.readouterr().out


def testMissingStoresAndNestedValues(sessions, tmp_path, capsys):
    assert sessions.sessionsCollect() == []
    sessions.tablePrint([])
    assert "No local agent sessions" in capsys.readouterr().out
    assert (
        sessions._jsonFind([None, {"nested": [{"cwd": "/nested"}]}], ("cwd",))
        == "/nested"
    )
    assert sessions._jsonFind({"cwd": 42}, ("cwd",)) is None
    assert (
        sessions._yamlValue(
            _fixtureWrite(tmp_path / "workspace.yaml", "comment\nother: yes\n"), "cwd"
        )
        is None
    )
    assert (
        sessions._jsonFirst(_fixtureWrite(tmp_path / "empty.jsonl", "\ninvalid\n"))
        is None
    )


def testStoreFailureIsolated(sessions, monkeypatch, caplog):
    def fail(rows):
        raise PermissionError("synthetic inaccessible store")

    monkeypatch.setattr(sessions, "_claudeCollect", fail)
    assert sessions.sessionsCollect() == []
    assert "cannot scan session store" in caplog.text


def testAgentOrderAndSelectors(sessions, tmp_path, monkeypatch, capsys):
    """Numbered output and clean ID extraction agree across real provider stores."""
    _fixtureWrite(
        tmp_path / f".claude/projects/work/{SESSION_ID}.jsonl",
        json.dumps({"cwd": str(tmp_path)}),
    )
    for name, stamp in (("older", 100), ("newer", 200)):
        path = _fixtureWrite(
            tmp_path / f".codex/sessions/rollout-{name}.jsonl",
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {"id": name + "-full-resume-id", "cwd": str(tmp_path)},
                }
            ),
        )
        os.utime(path, (stamp, stamp))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--history", "--full"])
    assert sessions.main() == 0
    output = capsys.readouterr().out
    assert (
        output.index("Claude")
        < output.index("newer-full-resume-id")
        < output.index("older-full-resume-id")
    )
    for row, expected in (
        (1, SESSION_ID),
        (2, "newer-full-resume-id"),
        (3, "older-full-resume-id"),
    ):
        monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--history", "--id", str(row)])
        assert sessions.main() == 0
        assert capsys.readouterr().out == expected + "\n"
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--id", "2"])
    assert sessions.main() == 0
    assert capsys.readouterr().out == "newer-full-resume-id\n"


@pytest.mark.parametrize("row", ["0", "-1", "100", "invalid"])
def testInvalidSelector(sessions, monkeypatch, capsys, row):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--id", row])
    with pytest.raises(SystemExit) as error:
        sessions.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "error:" in output.err


def testCurrentDirectoryAndAll(sessions, tmp_path, monkeypatch, capsys):
    """CLI scopes listing and ID retrieval to cwd unless explicitly expanded."""
    for name, cwd in (("here", tmp_path), ("elsewhere", tmp_path / "other")):
        _fixtureWrite(
            tmp_path / f".codex/sessions/rollout-{name}.jsonl",
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {"id": name + "-resume-id", "cwd": str(cwd)},
                }
            ),
        )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--full"])
    assert sessions.main() == 0
    output = capsys.readouterr().out
    assert "here-resume-id" in output
    assert "elsewhere-resume-id" not in output
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--id", "1"])
    assert sessions.main() == 0
    assert capsys.readouterr().out == "here-resume-id\n"
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--all", "--full"])
    assert sessions.main() == 0
    output = capsys.readouterr().out
    assert "here-resume-id" in output and "elsewhere-resume-id" in output


def testDirectoryIdentity(sessions, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    rows = [
        {"directory": "~"},
        {"directory": "~/alias"},
        {"directory": "~/child"},
        {"directory": "?"},
        {"directory": str(tmp_path) + "-other"},
    ]
    assert sessions.sessionsForDirectory(rows, tmp_path) == rows[:2]

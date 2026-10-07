"""Read-only audit regression tests."""

import copy
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from organiseMyProjects.logUtils import setApplication

from mailAgent.discovery import (
    discoveryRun,
    filtersReconcile,
    snapshotCompare,
    snapshotSave,
)
from mailAgent.imapDiscovery import folderParse, mailboxDiscover, quotaParse
from mailAgent.thunderbird import filtersParse, profilesDiscover, sourcesDiscover

ACCOUNT = dict(
    id="a",
    name="Andy",
    host="mail.example",
    username="andy",
    passwordEnv="TEST_MAIL_PASSWORD",
)
RULE = 'version="9"\nname="Order"\nenabled="no"\ntype="17"\naction="Move to folder"\nactionValue="imap://andy@mail.example/Orders%2FShop"\ncondition="AND (subject,contains,order)"'


def clientCreate(quota=False):
    client = Mock()
    client.capabilities = (b"IMAP4REV1", b"QUOTA") if quota else (b"IMAP4REV1",)
    client.list.return_value = (
        "OK",
        [b'(\\Sent) "/" "Orders/Shop"', b'(\\Noselect) "/" "Orders"'],
    )
    client.status.return_value = ("OK", [b'"Orders/Shop" (MESSAGES 10 UNSEEN 2)'])
    client.getquotaroot.return_value = (
        "OK",
        [[b'INBOX ""'], [b'"" (STORAGE 50 100 MESSAGE 2 20)']],
    )
    return client


@pytest.mark.parametrize(
    "row,path,delimiter,attributes",
    [
        (
            b'(\\Sent \\HasNoChildren) "/" "Orders/Shop"',
            "Orders/Shop",
            "/",
            ["\\Sent", "\\HasNoChildren"],
        ),
        (b'() "." INBOX.Archive', "INBOX.Archive", ".", []),
        (b"() NIL INBOX", "INBOX", None, []),
        ((b'() "/" {11}', b"Folder Name"), "Folder Name", "/", []),
        (b'() "/" "say\\"hi"', 'say"hi', "/", []),
    ],
)
def testFolderParse(row, path, delimiter, attributes):
    folder = folderParse(row)
    assert (folder["path"], folder["delimiter"], folder["attributes"]) == (
        path,
        delimiter,
        attributes,
    )
    assert folder["rawPath"]


def testInvalidList():
    with pytest.raises(ValueError):
        folderParse(b"invalid")


@pytest.mark.parametrize("quota", [True, False])
def testImapReadOnly(quota):
    client = clientCreate(quota)
    result = mailboxDiscover(client, ACCOUNT)
    assert result["folders"][0]["messages"] == 10
    assert result["folders"][0]["unseen"] == 2
    assert client.status.call_count == 1
    assert bool(result["quota"]) == quota
    assert {call[0] for call in client.mock_calls} <= {"list", "status", "getquotaroot"}
    if not quota:
        assert result["issues"] == ["Quota unsupported"]


def testQuotaParse():
    assert quotaParse([[b'INBOX ""'], [b'"" (STORAGE 50 100)']]) == [
        dict(root="", resource="STORAGE", used=50, limit=100, unit="KiB")
    ]


def profileCreate(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "profiles.ini").write_text(
        "[Profile0]\nPath=one\nIsRelative=1\n[Profile1]\nPath=two\nIsRelative=1\n"
    )
    (tmp_path / "installs.ini").write_text("[InstallABC]\nDefault=two\n")
    return tmp_path


def testProfilesMetadata(tmp_path):
    root = profileCreate(tmp_path)
    profiles = profilesDiscover(root)
    assert [p["default"] for p in profiles] == [False, True]
    assert profilesDiscover(tmp_path / "missing") == []


def testSourcesImapAndPop(tmp_path):
    root = profileCreate(tmp_path)
    for kind in ("Mail", "ImapMail"):
        directory = root / "two" / kind / "mail.example"
        directory.mkdir(parents=True)
        (directory / "msgFilterRules.dat").write_text(RULE)
    prefs = root / "two" / "prefs.js"
    prefs.write_text(
        'user_pref("mail.server.server1.directory-rel", "[ProfD]ImapMail/mail.example");\nuser_pref("mail.server.server1.hostname", "mail.example");\nuser_pref("mail.server.server1.userName", "andy");'
    )
    before = prefs.read_bytes()
    sources = sourcesDiscover(root)
    assert {s["kind"] for s in sources} == {"Mail", "ImapMail"}
    assert next(s for s in sources if s["kind"] == "ImapMail")["identities"] == [
        dict(host="mail.example", username="andy")
    ]
    assert prefs.read_bytes() == before


def testFiltersParsing():
    rule = filtersParse(RULE)[0]
    assert rule["enabled"] is False
    assert rule["conditions"] == ["AND (subject,contains,order)"]
    assert rule["actions"][0]["type"] == "Move to folder"
    assert rule["destinations"] == ["imap://andy@mail.example/Orders%2FShop"]
    assert not rule["issues"]
    copyRule = filtersParse(RULE.replace("Move to folder", "Copy to folder"))[0]
    assert copyRule["destinations"] == rule["destinations"]


def testUnsupportedRetained():
    rule = filtersParse(
        RULE + '\ncustom="something"\ninvalid syntax\naction="Custom action"'
    )[0]
    assert len(rule["issues"]) == 3
    assert "invalid syntax" in rule["raw"]


def snapshotCreate():
    return dict(
        schemaVersion=1,
        mailboxes=[mailboxDiscover(clientCreate(), ACCOUNT)],
        sources=[
            dict(
                path="profile/filter",
                identities=[dict(host="mail.example", username="andy")],
                filters=filtersParse(RULE),
            )
        ],
    )


def testReconciliation():
    snapshot = snapshotCreate()
    links, conflicts = filtersReconcile(snapshot)
    assert links[0]["resolved"]
    assert snapshot["sources"][0]["mailboxIds"] == ["a"]
    assert any(c["label"] == "Inferred" for c in conflicts)
    snapshot["sources"][0]["filters"] *= 2
    _, conflicts = filtersReconcile(snapshot)
    assert any(
        c["message"] == "Multiple filters share a destination" for c in conflicts
    )
    snapshot["mailboxes"][0]["folders"] = []
    links, conflicts = filtersReconcile(snapshot)
    assert not links[0]["resolved"]
    assert any(c["message"] == "Unresolved or ambiguous destination" for c in conflicts)


def testSnapshotCompare(tmp_path):
    old = snapshotCreate()
    snapshotSave(old, tmp_path)
    new = copy.deepcopy(old)
    new["mailboxes"][0]["folders"][0]["path"] = "New"
    new["sources"][0]["filters"][0].update(enabled=True, destinations=["other"])
    changes = snapshotCompare(old, new)
    assert {c["kind"] for c in changes} == {
        "folder added",
        "folder removed",
        "filter enabled changed",
        "filter destinations changed",
    }
    new["sources"][0]["filters"] = []
    assert any(c["kind"] == "filter removed" for c in snapshotCompare(old, new))
    assert any(c["kind"] == "filter added" for c in snapshotCompare(new, old))
    path = snapshotSave(new, tmp_path)
    assert json.loads(path.read_text()) == json.loads(
        (tmp_path / "latest.json").read_text()
    )
    assert len(list((tmp_path / "history").glob("*.json"))) == 2


def testSecretsAndCleanup(tmp_path, monkeypatch):
    setApplication("mailAgent")
    monkeypatch.setenv("TEST_MAIL_PASSWORD", "secret-never-persist")
    client = clientCreate()
    snapshot = discoveryRun([ACCOUNT], tmp_path, lambda *a, **k: client)
    snapshotSave(snapshot, tmp_path / "state")
    assert "secret-never-persist" not in (tmp_path / "state/latest.json").read_text()
    assert "passwordEnv" not in json.dumps(snapshot)
    client.logout.assert_called_once()
    client.login.side_effect = RuntimeError("secret-never-persist")
    failed = discoveryRun([ACCOUNT], tmp_path, lambda *a, **k: client)
    assert failed["mailboxes"][0]["failed"]
    assert "secret-never-persist" not in json.dumps(failed)
    assert not any(
        c["kind"] == "folder removed" for c in snapshotCompare(snapshot, failed)
    )


def testCoreNoTextual():
    core = Path(__file__).parents[1] / "src/mailAgent"
    for name in ("discovery.py", "imapDiscovery.py", "thunderbird.py"):
        assert "textual" not in (core / name).read_text().lower()

"""Read-only rolling-retention reconciliation tests."""

from datetime import date

from mailAgent.messageInventory import messageParse
from mailAgent.retentionPlanning import retentionPlanBuild


def _config():
    return {
        "general": {"imapRetentionMonths": 12, "liveYear": 2026},
        "mailboxes": [
            {
                "id": "andy",
                "name": "Andy",
                "host": "imap.example.com",
                "username": "andy",
                "role": "personal",
                "localArchive": "/mail/myMail",
                "archiveFormat": "thunderbird",
            }
        ],
    }


def _archive():
    return {
        "mailbox": "andy",
        "available": True,
        "complete": True,
        "format": "thunderbird",
        "folders": [
            {
                "path": "Cars/Rivervale",
                "storage": "/mail/myMail/Cars.sbd/Rivervale",
                "selectable": True,
            }
        ],
    }


def _snapshot(messages):
    return {
        "mailboxes": [
            {
                "id": "andy",
                "namespace": {"prefix": "INBOX.", "delimiter": "."},
                "folders": [
                    {
                        "path": "INBOX.Cars.Rivervale",
                        "delimiter": ".",
                        "attributes": ["\\HasNoChildren"],
                    },
                    {
                        "path": "INBOX.Trash",
                        "delimiter": ".",
                        "attributes": ["\\Trash", "\\HasNoChildren"],
                    },
                ],
                "inventory": {"complete": True, "issues": [], "messages": messages},
            }
        ]
    }


def _message(messageDate, folder="INBOX.Cars.Rivervale", uid="10"):
    return {
        "folder": folder,
        "uid": uid,
        "uidValidity": "42",
        "year": int(messageDate[:4]) if messageDate else None,
        "messageDate": messageDate,
    }


def testMessageParseCapturesCalendarDate():
    parsed = messageParse(
        b"1 (UID 8)",
        b"Date: Mon, 12 Oct 2025 23:30:00 -0400\r\nFrom: a@example.com\r\n\r\n",
        "INBOX.Cars.Rivervale",
        "42",
    )
    assert parsed["year"] == 2025
    assert parsed["messageDate"] == "2025-10-12"


def testRetentionPlanArchivesOnlyMessagesOlderThanCutoff():
    plan = retentionPlanBuild(
        _config(),
        _snapshot(
            [
                _message("2025-10-12", uid="10"),
                _message("2025-10-13", uid="11"),
                _message("2025-10-14", uid="12"),
            ]
        ),
        today=date(2026, 10, 13),
        archives=[_archive()],
    )

    assert plan["cutoffDate"] == "2025-10-13"
    assert len(plan["proposals"]) == 1
    proposal = plan["proposals"][0]
    assert proposal["source"]["uid"] == "10"
    assert proposal["canonical"] == "Cars/Rivervale"
    assert proposal["destination"] == {
        "kind": "local",
        "mailbox": "andy",
        "folder": "Cars/Rivervale",
        "path": "/mail/myMail/Cars.sbd/Rivervale",
        "format": "thunderbird",
    }
    assert proposal["sourceRemovalAllowed"] is False
    assert proposal["verificationRequired"] is True
    assert plan["summary"] == {"proposals": 1, "blocked": 0, "foldersAffected": 1}


def testRetentionPlanUsesExplicitFolderMappingBeforeNamespaceInference():
    config = _config()
    config["mailboxes"][0]["folderMappings"] = {
        "INBOX.Motoring.Rivervale": "Cars/Rivervale"
    }
    snapshot = _snapshot([_message("2025-01-01", folder="INBOX.Motoring.Rivervale")])
    snapshot["mailboxes"][0]["folders"][0]["path"] = "INBOX.Motoring.Rivervale"

    plan = retentionPlanBuild(
        config,
        snapshot,
        today=date(2026, 10, 13),
        archives=[_archive()],
    )

    assert plan["proposals"][0]["canonical"] == "Cars/Rivervale"


def testRetentionPlanBlocksOldMessageWithoutSafeDateOrDestination():
    archive = _archive()
    archive["folders"] = []
    plan = retentionPlanBuild(
        _config(),
        _snapshot([_message(None, uid="10"), _message("2025-01-01", uid="11")]),
        today=date(2026, 10, 13),
        archives=[archive],
    )

    assert not plan["proposals"]
    assert {entry["reason"] for entry in plan["blocked"]} == {
        "Message date unavailable for retention",
        "Canonical local archive destination unavailable or ambiguous",
    }


def testRetentionPlanDoesNotProposeExcludedSystemFolder():
    plan = retentionPlanBuild(
        _config(),
        _snapshot([_message("2025-01-01", folder="INBOX.Trash")]),
        today=date(2026, 10, 13),
        archives=[_archive()],
    )
    assert plan["proposals"] == []
    assert plan["blocked"] == []


def testRetentionPlanBlocksIncompleteInventory():
    snapshot = _snapshot([])
    snapshot["mailboxes"][0]["inventory"]["complete"] = False
    plan = retentionPlanBuild(
        _config(), snapshot, today=date(2026, 10, 13), archives=[_archive()]
    )
    assert plan["proposals"] == []
    assert plan["blocked"][0]["reason"] == "Message inventory is incomplete"

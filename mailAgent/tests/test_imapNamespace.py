"""IMAP namespace discovery and execution destination regression tests."""

from mailAgent.executionApp import executionNamespaceApply
from mailAgent.imapDiscovery import namespaceParse


def testNamespaceParseInboxPrefix():
    assert namespaceParse([b'(("INBOX." ".")) NIL NIL']) == {
        "prefix": "INBOX.",
        "delimiter": ".",
    }


def testNamespaceParseEmptyPrefix():
    assert namespaceParse([b'(("" "/")) NIL NIL']) == {
        "prefix": "",
        "delimiter": "/",
    }


def testExecutionNamespacePrefixesNewMirror():
    plan = {
        "proposals": [
            {
                "canonical": "Shopping/Amazon",
                "requiresFolderCreation": True,
                "destination": {
                    "kind": "imap",
                    "mailbox": "andy",
                    "folder": "Shopping.Amazon",
                    "exists": False,
                },
            }
        ]
    }
    snapshot = {
        "mailboxes": [
            {
                "id": "andy",
                "namespace": {"prefix": "INBOX.", "delimiter": "."},
                "folders": [
                    {"path": "INBOX", "attributes": ["\\HasChildren"]},
                    {"path": "INBOX.Archive", "attributes": ["\\HasChildren"]},
                ],
            }
        ]
    }

    executionNamespaceApply(plan, snapshot)

    proposal = plan["proposals"][0]
    assert proposal["destination"]["folder"] == "INBOX.Shopping.Amazon"
    assert proposal["destination"]["exists"] is False
    assert proposal["requiresFolderCreation"] is True


def testExecutionNamespaceRecognizesExistingMirror():
    plan = {
        "proposals": [
            {
                "canonical": "Shopping/Amazon",
                "requiresFolderCreation": True,
                "destination": {
                    "kind": "imap",
                    "mailbox": "andy",
                    "folder": "Shopping.Amazon",
                    "exists": False,
                },
            }
        ]
    }
    snapshot = {
        "mailboxes": [
            {
                "id": "andy",
                "namespace": {"prefix": "INBOX.", "delimiter": "."},
                "folders": [
                    {"path": "INBOX.Shopping.Amazon", "attributes": ["\\HasNoChildren"]}
                ],
            }
        ]
    }

    executionNamespaceApply(plan, snapshot)

    proposal = plan["proposals"][0]
    assert proposal["destination"]["folder"] == "INBOX.Shopping.Amazon"
    assert proposal["destination"]["exists"] is True
    assert proposal["requiresFolderCreation"] is False

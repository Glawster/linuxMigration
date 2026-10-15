"""IMAP namespace discovery and execution destination regression tests."""

from unittest.mock import Mock

from mailAgent.executionApp import executionNamespaceApply
from mailAgent.imapDiscovery import mailboxDiscover, namespaceParse


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


def testNamespaceIsProbedWhenCapabilityIsNotAdvertised():
    client = Mock()
    client.capabilities = (b"IMAP4REV1",)
    client.list.return_value = ("OK", [b'(\\HasChildren) "." INBOX'])
    client.status.return_value = ("OK", [b'INBOX (MESSAGES 1 UNSEEN 0)'])
    client.namespace.return_value = ("OK", [b'(("INBOX." ".")) NIL NIL'])

    result = mailboxDiscover(
        client,
        dict(id="andy", name="Andy", host="mail.example", username="andy"),
    )

    assert result["namespace"] == {"prefix": "INBOX.", "delimiter": "."}
    client.namespace.assert_called_once_with()


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

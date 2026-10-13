"""Compatibility tests for servers that under-advertise exact IMAP support."""

import mailAgent.executionCompat as compat


class UnderAdvertisedClient:
    capabilities = (b"IMAP4REV1",)

    def __init__(self):
        self.calls = []

    def select(self, folder, readonly=True):
        self.calls.append(("SELECT", folder, readonly))
        return "OK", []

    def response(self, name):
        assert name == "UIDNEXT"
        return name, [b"23000"]

    def uid(self, command, *args):
        self.calls.append((command, *args))
        assert command == "EXPUNGE"
        assert args == ("4294967295",)
        return "OK", [None]


def testUnderAdvertisedUidExpungeIsVerifiedBeforeCoreExecution(monkeypatch):
    client = UnderAdvertisedClient()
    observed = {}

    def core(passedClient, approved, config, observe, actionId, **kwargs):
        observed["capabilities"] = tuple(passedClient.capabilities)
        return {"state": "completed"}

    monkeypatch.setattr(compat, "_imapFileExecute", core)
    result = compat.imapFileExecute(client, {}, {}, lambda: {}, "action", confirm=True)

    assert result == {"state": "completed"}
    assert client.calls == [
        ("SELECT", '"INBOX"', True),
        ("EXPUNGE", "4294967295"),
    ]
    assert b"UIDPLUS" in observed["capabilities"]
    assert client.capabilities == (b"IMAP4REV1",)


def testAdvertisedUidPlusNeedsNoProbe(monkeypatch):
    client = UnderAdvertisedClient()
    client.capabilities = (b"IMAP4REV1", b"UIDPLUS")

    monkeypatch.setattr(
        compat,
        "_imapFileExecute",
        lambda *args, **kwargs: {"state": "completed"},
    )

    assert compat.imapFileExecute(client, {}, {}, lambda: {}, "action") == {
        "state": "completed"
    }
    assert client.calls == []

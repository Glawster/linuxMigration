"""Mocked GPG and authentication tests; no real keys or passwords required."""

import ast
import copy
import json
import subprocess
import traceback
from pathlib import Path
from unittest.mock import Mock

import pytest
from organiseMyProjects.logUtils import setApplication

from mailAgent.configuration import configValidate
from mailAgent.credentials import (
    CredentialError,
    credentialGet,
    credentialsDecrypt,
    credentialsLoad,
    credentialsValidate,
)
from mailAgent.discovery import discoveryRun, snapshotSave

SECRET = "test-only-password-never-output"


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "credentials.json.gpg"
    path.write_bytes(b"fictional encrypted content")
    path.chmod(0o600)
    return path


@pytest.fixture
def gpg(monkeypatch):
    runner = Mock(
        return_value=subprocess.CompletedProcess(
            [],
            0,
            json.dumps({"andy": {"password": SECRET}}).encode(),
            b"private diagnostic " + SECRET.encode(),
        )
    )
    monkeypatch.setattr("mailAgent.credentials.subprocess.run", runner)
    return runner


def accountBuild(identity="andy"):
    return dict(
        id=identity,
        name=identity,
        host=identity + ".example",
        username=identity,
        role="support",
        credentialId=identity,
    )


def clientBuild():
    client = Mock()
    client.capabilities = (b"IMAP4rev1",)
    client.list.return_value = ("OK", [])
    return client


def testSuccessfulDecryption(store, gpg):
    before = store.read_bytes()
    assert credentialsDecrypt(store) == gpg.return_value.stdout
    args, options = gpg.call_args
    assert args[0] == ["gpg", "--batch", "--decrypt", "--", str(store)]
    assert options == dict(
        capture_output=True, stdin=subprocess.DEVNULL, timeout=120, check=False
    )
    assert store.read_bytes() == before
    assert list(store.parent.iterdir()) == [store]
    assert credentialGet(accountBuild(), store) == SECRET
    assert credentialsLoad(store) == {"andy": {"password": SECRET}}


def testDefaultStore(store, gpg, monkeypatch):
    default = store.parent / ".config/mailAgent/credentials.json.gpg"
    default.parent.mkdir(parents=True)
    store.rename(default)
    monkeypatch.setattr(Path, "home", lambda: store.parent)
    assert credentialGet(accountBuild()) == SECRET
    assert gpg.call_args.args[0][-1] == str(default)


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o604, 0o601, 0o610])
def testUnsafeMode(store, gpg, mode):
    store.chmod(mode)
    with pytest.raises(CredentialError, match="permissions"):
        credentialsDecrypt(store)
    gpg.assert_not_called()


def testMissingOrNonregularFile(store, gpg):
    with pytest.raises(CredentialError, match="missing"):
        credentialsDecrypt(store.parent / "absent.gpg")
    directory = store.parent / "directory.gpg"
    directory.mkdir()
    with pytest.raises(CredentialError, match="regular file"):
        credentialsDecrypt(directory)
    link = store.parent / "link.gpg"
    link.symlink_to(store)
    with pytest.raises(CredentialError, match="regular file"):
        credentialsDecrypt(link)
    gpg.assert_not_called()


def testPlaintextAndRepositoryRejected(store, gpg):
    with pytest.raises(CredentialError, match="encrypted"):
        credentialsDecrypt(store.with_suffix(""))
    (store.parent / ".git").mkdir()
    with pytest.raises(CredentialError, match="outside a repository"):
        credentialsDecrypt(store)
    gpg.assert_not_called()


@pytest.mark.parametrize(
    "error,expected",
    [
        (FileNotFoundError(SECRET), "executable is missing"),
        (OSError(SECRET), "Unable to run"),
        (
            subprocess.TimeoutExpired("gpg", 120, output=SECRET, stderr=SECRET),
            "timed out",
        ),
    ],
)
def testSubprocessErrorsSecretFree(store, gpg, error, expected):
    gpg.side_effect = error
    with pytest.raises(CredentialError, match=expected) as caught:
        credentialsDecrypt(store)
    assert SECRET not in "".join(traceback.format_exception(caught.value))


def testFailedGpgDoesNotExposeStreams(store, gpg):
    gpg.return_value = subprocess.CompletedProcess(
        [], 2, SECRET.encode(), SECRET.encode()
    )
    with pytest.raises(CredentialError, match="decryption failed") as caught:
        credentialsLoad(store)
    assert SECRET not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "payload", [SECRET.encode(), b"{", b"\xff", b'{"andy":{},"andy":{}}']
)
def testMalformedJson(store, gpg, payload):
    gpg.return_value.stdout = payload
    with pytest.raises(CredentialError, match="not valid JSON") as caught:
        credentialsLoad(store)
    assert SECRET not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "value",
    [
        [],
        None,
        "private",
        {"andy": None},
        {"": {"password": SECRET}},
        {"andy": {}},
        {"andy": {"password": ""}},
        {"andy": {"password": "   "}},
        {"andy": {"password": 123}},
        {"andy": {"password": None}},
    ],
)
def testInvalidPayload(value):
    with pytest.raises(CredentialError) as caught:
        credentialsValidate(value)
    assert SECRET not in str(caught.value)


def testMissingIdAndPrecedence(store, gpg, monkeypatch):
    monkeypatch.setenv("OLD_ENV", "environment-secret")
    account = {**accountBuild(), "passwordEnv": "OLD_ENV"}
    assert credentialGet(account, store) == SECRET
    account["credentialId"] = "unknown"
    with pytest.raises(CredentialError, match="not found"):
        credentialGet(account, store)
    account["credentialId"] = ""
    with pytest.raises(CredentialError, match="Invalid credentialId"):
        credentialGet(account, store)
    gpg.return_value.returncode = 2
    with pytest.raises(CredentialError):
        credentialGet(accountBuild(), store)


def testEnvironmentCompatibility(gpg, monkeypatch):
    monkeypatch.setenv("OLD_ENV", SECRET)
    assert credentialGet(dict(passwordEnv="OLD_ENV")) == SECRET
    for value in ("", " "):
        monkeypatch.setenv("OLD_ENV", value)
        with pytest.raises(CredentialError, match="missing or empty"):
            credentialGet(dict(passwordEnv="OLD_ENV"))
    monkeypatch.delenv("OLD_ENV")
    with pytest.raises(CredentialError, match="missing or empty"):
        credentialGet(dict(passwordEnv="OLD_ENV"))
    with pytest.raises(CredentialError, match="Configure"):
        credentialGet({})
    gpg.assert_not_called()


def testCredentialDictionaryReleased(store, gpg, monkeypatch):
    payload = {"andy": {"password": SECRET}}
    monkeypatch.setattr("mailAgent.credentials.credentialsLoad", lambda path: payload)
    assert credentialGet(accountBuild(), store) == SECRET
    assert payload == {}


def testFiveAccountsNoSecretOutput(store, gpg, tmp_path, caplog):
    setApplication("mailAgent")
    identities = ("andy", "kathy", "old", "hwfc", "clannEolas")
    gpg.return_value.stdout = json.dumps(
        {key: {"password": SECRET + key} for key in identities}
    ).encode()
    accounts = [accountBuild(key) for key in identities]
    original = copy.deepcopy(accounts)
    clients = [clientBuild() for _ in accounts]
    factory = Mock(side_effect=clients)
    snapshot = discoveryRun(
        accounts, tmp_path, clientFactory=factory, credentialsFile=store
    )
    snapshotSave(snapshot, tmp_path / "state")
    assert not any(mailbox.get("failed") for mailbox in snapshot["mailboxes"])
    for identity, client in zip(identities, clients):
        client.login.assert_called_once_with(identity, SECRET + identity)
        client.logout.assert_called_once()
    assert SECRET not in json.dumps(snapshot)
    assert "credentialId" not in json.dumps(snapshot)
    assert SECRET not in (tmp_path / "state/latest.json").read_text()
    assert SECRET not in caplog.text
    assert accounts == original


def testFailedLoginAndGpgNoSecretOutput(store, gpg, tmp_path, caplog):
    setApplication("mailAgent")
    client = clientBuild()
    client.login.side_effect = RuntimeError(SECRET)
    snapshot = discoveryRun(
        [accountBuild()],
        tmp_path,
        clientFactory=lambda *a, **k: client,
        credentialsFile=store,
    )
    assert snapshot["mailboxes"][0]["failed"]
    assert SECRET not in json.dumps(snapshot)
    client.logout.assert_called_once()
    gpg.return_value.returncode = 2
    snapshot = discoveryRun([accountBuild()], tmp_path, credentialsFile=store)
    assert "GPG decryption failed" in snapshot["mailboxes"][0]["issues"][0]
    assert SECRET not in json.dumps(snapshot) + caplog.text


def testConfigurationSources(tmp_path):
    account = accountBuild()
    normalized = configValidate(
        dict(mailboxes=[account], general=dict(credentialsFile="vault.json.gpg")),
        tmp_path,
    )
    assert normalized["general"]["credentialsFile"] == str(tmp_path / "vault.json.gpg")
    assert "passwordEnv" not in normalized["mailboxes"][0]
    for values in (
        {},
        {"credentialId": ""},
        {"passwordEnv": ""},
        {"credentialId": 1},
        {"passwordEnv": None},
        {"credentialId": "andy", "password": SECRET},
    ):
        candidate = {
            key: value for key, value in account.items() if key != "credentialId"
        }
        candidate.update(values)
        with pytest.raises(ValueError) as caught:
            configValidate(dict(mailboxes=[candidate]), tmp_path)
        assert SECRET not in str(caught.value)
    with pytest.raises(ValueError, match="credentialsFile"):
        configValidate(
            dict(mailboxes=[account], general=dict(credentialsFile=[])), tmp_path
        )


def testCliFailuresContainNoSecrets(store, gpg, tmp_path, monkeypatch, capsys, caplog):
    from mailAgent import cli

    config = tmp_path / "config.toml"
    config.write_text(
        '[general]\ncredentialsFile="'
        + str(store)
        + '"\n[[mailboxes]]\nid="andy"\nname="Andy"\nhost="example"\nusername="andy"\nrole="support"\ncredentialId="andy"\n'
    )
    gpg.return_value.returncode = 2
    monkeypatch.setattr(
        "sys.argv",
        [
            "mailAgent",
            "--json",
            "--config",
            str(config),
            "--state",
            str(tmp_path / "state"),
            "--thunderbird",
            str(tmp_path / "thunderbird"),
        ],
    )
    with pytest.raises(SystemExit) as caught:
        cli.main()
    output = capsys.readouterr()
    assert caught.value.code == 1
    assert "GPG decryption failed" in output.out
    assert SECRET not in output.out + output.err + str(caught.value) + caplog.text


def testCoreHasNoTextualDependency():
    source = Path(__file__).parents[1] / "src/mailAgent/credentials.py"
    tree = ast.parse(source.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("textual")
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("textual") for alias in node.names)


@pytest.mark.parametrize("method", ["lstat", "resolve"])
def testFilesystemErrorsSecretFree(store, gpg, monkeypatch, method):
    monkeypatch.setattr(
        Path, method, lambda *a, **k: (_ for _ in ()).throw(PermissionError(SECRET))
    )
    with pytest.raises(CredentialError, match="Cannot inspect") as caught:
        credentialsDecrypt(store)
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    gpg.assert_not_called()


def testInvalidDecryptedEntrySecretFree(store, gpg):
    gpg.return_value.stdout = json.dumps({"andy": {"private": SECRET}}).encode()
    with pytest.raises(CredentialError, match="nonempty password") as caught:
        credentialsLoad(store)
    assert SECRET not in "".join(traceback.format_exception(caught.value))

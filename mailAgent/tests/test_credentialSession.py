"""Session password cache uses a fake kernel keyring and fictional secrets."""

import json
import os
import subprocess
from unittest.mock import Mock

import pytest

from mailAgent import credentials, credentialSession
from mailAgent.configuration import configValidate

_SECRET = "fictional-session-password"


@pytest.fixture
def kernel(monkeypatch):
    keys = {}
    calls = []
    state = dict(valid=True, failure=None)

    def run(arguments, payload=None):
        calls.append((arguments, payload))
        command = arguments[0]
        code, output = 0, b""
        if state["failure"] == command:
            code = 1
        elif command == "rdescribe":
            name = "_ses" if state["valid"] else "_uid_ses.1000"
            output = f"keyring;{os.getuid()};1000;3f030000;{name}".encode()
        elif command == "search":
            output = b"42" if arguments[-1] in keys else b""
            code = 0 if output else 1
        elif command == "pipe":
            output = next(iter(keys.values()))
        elif command == "padd":
            keys[arguments[2]] = payload
            output = b"42"
        elif command == "revoke":
            keys.clear()
        elif command != "setperm":
            raise AssertionError(command)
        return subprocess.CompletedProcess(
            arguments, code, output, b"private diagnostic"
        )

    monkeypatch.setattr(credentialSession, "_commandRun", run)
    return keys, calls, state


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "credentials.json.gpg"
    path.write_bytes(b"fictional encrypted store")
    path.chmod(0o600)
    return path


@pytest.fixture
def decrypt(monkeypatch):
    loader = Mock(
        return_value=json.dumps(
            dict(andy=dict(password=_SECRET, extra="not cached"))
        ).encode()
    )
    monkeypatch.setattr(credentials, "credentialsDecrypt", loader)
    return loader


def testReopenedApplicationReusesSessionAndLogoutRequiresFreshLoad(
    kernel, store, decrypt
):
    keys, calls, state = kernel
    first = credentials.credentialsLoad(store, sessionCache=True)
    first.clear()  # App shutdown releases its own memory, not the kernel cache.
    reopened = credentials.credentialsLoad(store, sessionCache=True)
    assert reopened == {"andy": {"password": _SECRET}}
    assert decrypt.call_count == 1
    assert "extra" not in json.loads(next(iter(keys.values())))["andy"]
    assert all(_SECRET not in str(args) for args, _payload in calls)
    assert ["setperm", "42", "0x3f000000"] in [args for args, _ in calls]
    keys.clear()  # PAM revokes the previous login's keyring.
    credentials.credentialsLoad(store, sessionCache=True)
    assert decrypt.call_count == 2
    assert list(store.parent.iterdir()) == [store]


def testEncryptedStoreChangeAndPathChangeInvalidateCache(kernel, store, decrypt):
    credentials.credentialsLoad(store, sessionCache=True)
    store.write_bytes(b"changed encrypted store")
    credentials.credentialsLoad(store, sessionCache=True)
    assert decrypt.call_count == 2
    other = store.with_name("other.gpg")
    other.write_bytes(store.read_bytes())
    other.chmod(0o600)
    credentials.credentialsLoad(other, sessionCache=True)
    assert decrypt.call_count == 3


def testCacheNeverBypassesStoreSafety(kernel, store, decrypt):
    credentials.credentialsLoad(store, sessionCache=True)
    store.chmod(0o644)
    with pytest.raises(credentials.CredentialError, match="permissions"):
        credentials.credentialsLoad(store, sessionCache=True)
    store.unlink()
    with pytest.raises(credentials.CredentialError, match="missing"):
        credentials.credentialsLoad(store, sessionCache=True)
    assert decrypt.call_count == 1


def testUnsafeLoginContextRefused(kernel, store, decrypt):
    keys, calls, state = kernel
    state["valid"] = False
    with pytest.raises(credentials.CredentialError, match="PAM login-session"):
        credentials.credentialsLoad(store, sessionCache=True)
    assert not keys
    decrypt.assert_not_called()


@pytest.mark.parametrize("failure", ["padd", "setperm", "pipe"])
def testCacheFailuresSecretFree(kernel, store, decrypt, failure):
    keys, calls, state = kernel
    if failure == "pipe":
        credentials.credentialsLoad(store, sessionCache=True)
    state["failure"] = failure
    with pytest.raises(credentials.CredentialError) as caught:
        credentials.credentialsLoad(store, sessionCache=True)
    assert _SECRET not in str(caught.value)
    if failure == "setperm":
        assert not keys
        assert ["revoke", "42"] in [args for args, _ in calls]


def testDisabledCacheDoesNotUseKernel(kernel, store, decrypt):
    credentials.credentialsLoad(store)
    credentials.credentialsLoad(store, sessionCache=False)
    assert decrypt.call_count == 2
    assert not kernel[1]


def testInvalidDecryptedJsonIsNotCached(kernel, store, decrypt):
    decrypt.return_value = b"not JSON"
    with pytest.raises(credentials.CredentialError):
        credentials.credentialsLoad(store, sessionCache=True)
    assert not kernel[0]


def testInvalidCachedJsonIsNotReturned(kernel, store, decrypt):
    kernel[0][credentialSession.credentialsSessionIdentity(store)] = b"not JSON"
    with pytest.raises(credentials.CredentialError):
        credentials.credentialsLoad(store, sessionCache=True)
    decrypt.assert_not_called()


def testChangedStoreDuringDecryptionIsNotCached(kernel, store, decrypt):
    def change(path):
        store.write_bytes(b"replacement store")
        return json.dumps(dict(andy=dict(password=_SECRET))).encode()

    decrypt.side_effect = change
    with pytest.raises(credentials.CredentialError, match="changed"):
        credentials.credentialsLoad(store, sessionCache=True)
    assert not kernel[0]


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired("keyctl", 10, output=_SECRET.encode()),
    ],
)
def testExternalFailuresNeverExposeOutput(monkeypatch, error):
    monkeypatch.setattr(credentialSession.subprocess, "run", Mock(side_effect=error))
    with pytest.raises(credentialSession.SessionCredentialError) as caught:
        credentialSession._commandRun(["pipe", "42"])
    assert _SECRET not in str(caught.value)


def testSessionConfigurationIsBoolean(tmp_path):
    config = dict(
        mailboxes=[
            dict(
                id="andy",
                name="Andy",
                host="example",
                username="andy",
                role="support",
                credentialId="andy",
            )
        ],
        general=dict(credentialsSessionCache=True),
    )
    assert (
        configValidate(config, tmp_path)["general"]["credentialsSessionCache"] is True
    )
    config["general"]["credentialsSessionCache"] = "yes"
    with pytest.raises(ValueError, match="credentialsSessionCache"):
        configValidate(config, tmp_path)


def testDiscoveryReusesCacheWithoutLeakingPasswords(kernel, store, decrypt, tmp_path):
    from organiseMyProjects.logUtils import setApplication
    from mailAgent.discovery import discoveryRun

    setApplication("mailAgent")
    account = dict(
        id="andy",
        name="Andy",
        host="example",
        username="andy",
        role="support",
        credentialId="andy",
    )
    client = Mock()
    client.capabilities = ()
    client.list.return_value = ("OK", [])
    for _ in range(2):
        snapshot = discoveryRun(
            [account],
            tmp_path,
            clientFactory=Mock(return_value=client),
            credentialsFile=store,
            credentialsSessionCache=True,
        )
        assert not snapshot["mailboxes"][0].get("failed")
        assert _SECRET not in json.dumps(snapshot)
    assert decrypt.call_count == 1
    assert client.login.call_count == 2
    client.login.assert_called_with("andy", _SECRET)

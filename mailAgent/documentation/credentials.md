# mailAgent encrypted credentials

mailAgent stores mailbox credentials in an encrypted local JSON file.

## Default location

```text
~/.config/mailAgent/credentials.json.gpg
```

The encrypted file must remain outside the repository.

## Plaintext structure

The encrypted payload is JSON:

```json
{
  "andy": {
    "password": "..."
  },
  "kathy": {
    "password": "..."
  },
  "old": {
    "password": "..."
  },
  "hwfc": {
    "password": "..."
  },
  "clannEolas": {
    "password": "..."
  }
}
```

Mailbox configuration references the entry by `credentialId`.

## Runtime behaviour

At runtime mailAgent:

1. invoke GPG to decrypt the credential store;
2. read decrypted JSON from GPG standard output;
3. parse it in memory;
4. resolve the password required for the mailbox connection;
5. never write decrypted credentials to disk.

The decrypted credentials must never be written to `/tmp`, application state,
logs, discovery snapshots, or generated reports.

## Reuse passwords until logout

To reuse mailbox passwords across closing and reopening mailAgent, enable:

```toml
[general]
credentialsSessionCache = true
```

This is enabled in this PC's mailAgent configuration. The first launch loads the
encrypted file normally. Later launches and refreshes in the same login session
reuse the passwords from the Linux kernel login-session keyring. Closing the app
releases its process memory but leaves the session cache available. Logout
revokes the login keyring; shutdown clears kernel memory. The next login loads
the encrypted file again. Screen locking alone does not clear the cache.

The cache requires Linux `keyctl` from keyutils and a PAM-created `_ses` keyring
with `pam_keyinit.so ... revoke` in the login profile. This PC's GDM and console
login profiles use `force revoke`; mailAgent does not change PAM configuration.
Apps launched in another login context, or through a launcher that replaces its
inherited session keyring, do not share the cache. Only a process possessing the
same login keyring can read its cached entries. See the
[PAM keyring lifecycle](https://www.man7.org/linux/man-pages/man8/pam_keyinit.8.html)
and [keyutils interface](https://www.man7.org/linux/man-pages/man1/keyctl.1.html).

Mailbox passwords stay in kernel memory. No environment variable or plaintext
cache file is created, and no secret appears in command arguments. Passwords
enter keyctl through stdin and leave through a captured pipe. The GPG unlock
passphrase is not cached by this feature.

Each entry is bound to the encrypted store's resolved path and content hash.
Changing the file forces another load. Missing files or unsafe permissions are
still rejected on cache hits. Cache errors remain secret-free and do not fall
back to another cache or a plaintext file. To disable caching, set the option
to false; omitting it also preserves the original per-run GPG behavior.
Legacy `passwordEnv` accounts are unaffected.

## Security requirements

mailAgent must never:

- log a password;
- include decrypted JSON in an exception;
- print secrets to the CLI or TUI;
- include credentials in `--json`;
- persist decrypted credentials;
- silently fall back to plaintext storage.

Runtime rejects group/other permission bits, symlinks, non-regular files,
unencrypted file extensions and stores located inside a Git repository.
Owner-only permissions such as `0600` or `0400` are accepted.

Recommended:

```bash
chmod 600 ~/.config/mailAgent/credentials.json.gpg
```

## Creating the credential store

Create a temporary local JSON file:

```bash
umask 077
mkdir -p ~/.config/mailAgent
chmod 700 ~/.config/mailAgent
nano ~/.config/mailAgent/credentials.json
chmod 600 ~/.config/mailAgent/credentials.json
```

Encrypt it:

```bash
gpg --symmetric \
    --cipher-algo AES256 \
    --output ~/.config/mailAgent/credentials.json.gpg \
    ~/.config/mailAgent/credentials.json
```

Set encrypted-file permissions, then verify decryption:

```bash
chmod 600 ~/.config/mailAgent/credentials.json.gpg
gpg --decrypt ~/.config/mailAgent/credentials.json.gpg
```

After successful verification remove the plaintext source:

```bash
shred -u ~/.config/mailAgent/credentials.json
```

## Main mailbox configuration

Example:

```toml
[[mailboxes]]
id = "andy"
name = "Andy"
host = "sxb1plzcpnl487527.prod.sxb1.secureserver.net"
port = 993
username = "andyw@glawster.com"
credentialId = "andy"
role = "personal"
localArchive = "myMail"
```

## Compatibility

Existing `passwordEnv` support remains temporarily while accounts are migrated.
It is used only when the mailbox has no `credentialId`. A missing entry or failed
decryption does not fall back to the environment.

If both are present:

```text
credentialId takes precedence
```

Plaintext JSON is an import/setup format only, not a runtime credential store.


## Advanced configuration and failure handling

The optional path override is under the existing general section:

```toml
[general]
liveYear = 2026
credentialsFile = "~/.config/mailAgent/credentials.json.gpg"
```

Relative paths resolve against the TOML configuration file's directory. The
store must still be an encrypted `.gpg` file outside any Git repository, with
owner-only permissions. Plaintext `password` fields in mailbox configuration
are rejected. The example configuration now uses five independent credential
IDs and requires no routine password exports.

GPG is an external prerequisite; mailAgent does not install it. Decryption uses
an argument sequence with `--batch --decrypt`, captured stdout/stderr and a
120-second timeout. GPG agent/pinentry handles unlocking according to the user's
setup. No passphrase is placed on the command line or supplied by the TUI.

Without session caching, the store is decrypted once per discovery run when an
account uses a credential ID. JSON is parsed and
validated in memory, including rejecting duplicate keys and missing, empty or
non-string passwords. Accounts share the in-memory credential dictionary, which
is cleared after account processing, including when the run is interrupted.
The connection workflow releases its password
reference after authentication. No secret is added to the mailbox configuration,
plan or audit model.

Missing stores, unsafe permissions, missing GPG, failed decryption, invalid JSON
and missing IDs appear as secret-free per-mailbox audit issues. Other accounts
can still be audited. A run with failed accounts exits nonzero, including JSON
mode. A failed store load is reported for every credential-based account without
retrying GPG; environment-based accounts continue normally. Raw GPG streams and
authentication exception details are never displayed.

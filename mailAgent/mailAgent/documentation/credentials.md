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

mailAgent must:

1. invoke GPG to decrypt the credential store;
2. read decrypted JSON from GPG standard output;
3. parse it in memory;
4. resolve the password required for the mailbox connection;
5. never write decrypted credentials to disk.

The decrypted credentials must never be written to `/tmp`, application state,
logs, discovery snapshots, or generated reports.

## Security requirements

mailAgent must never:

- log a password;
- include decrypted JSON in an exception;
- print secrets to the CLI or TUI;
- include credentials in `--json`;
- persist decrypted credentials;
- silently fall back to plaintext storage.

The encrypted file should also have restrictive filesystem permissions.

Recommended:

```bash
chmod 600 ~/.config/mailAgent/credentials.json.gpg
```

## Creating the credential store

Create a temporary local JSON file:

```bash
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

Verify decryption:

```bash
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

Existing `passwordEnv` support may remain temporarily while accounts are
migrated.

If both are present:

```text
credentialId takes precedence
```

Plaintext JSON is an import/setup format only, not a runtime credential store.

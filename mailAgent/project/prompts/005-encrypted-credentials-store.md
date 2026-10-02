# Codex Prompt - REQ-005 Encrypted credentials store

Implement REQ-005 in mailAgent using the repository OMP guidance.

## Goal

Replace routine environment-variable passwords with an encrypted JSON
credential store.

Default:

```text
~/.config/mailAgent/credentials.json.gpg
```

Mailbox configuration uses:

```toml
credentialId = "andy"
```

Retain `passwordEnv` temporarily as a fallback.

## Core design

Add a core module such as:

```text
src/mailAgent/credentials.py
```

Use OMP domainAction naming.

Suggested public functions:

```text
credentialsDecrypt
credentialsLoad
credentialGet
credentialsValidate
```

Do not put credential handling in the TUI.

## GPG execution

Use `subprocess.run` or equivalent safely.

Requirements:

- no `shell=True`;
- arguments supplied as a sequence;
- capture stdout in memory;
- capture stderr but never expose raw stderr if it may include sensitive data;
- never write decrypted credentials to disk;
- fail cleanly when GPG is missing;
- fail cleanly when decryption fails.

The expected operation is conceptually:

```text
gpg --batch --decrypt <credentials-file>
```

Interactive GPG pinentry may still be used by the user's GPG setup where
appropriate.

Do not attempt to implement encryption cryptography directly in Python.

## Credential parsing

After successful decryption:

1. parse stdout as JSON in memory;
2. validate the top-level object;
3. locate `credentialId`;
4. require a non-empty `password` string;
5. return only the required secret where practical.

Avoid keeping the complete decrypted credential dictionary alive longer than
necessary.

## Config integration

For each mailbox:

1. if `credentialId` exists, resolve it from the encrypted store;
2. otherwise, if `passwordEnv` exists, use the compatibility environment path;
3. otherwise report a configuration error.

Never include a credential value in config dump, snapshot, or logs.

## File safety

Default path:

```text
~/.config/mailAgent/credentials.json.gpg
```

Check that it is a regular file.

Prefer mode `0600`; reject or clearly report unsafe group/other permissions.

Add repository ignore patterns covering:

```text
credentials.json
credentials.json.gpg
*.credentials.json
```

Do not add a real credentials file to source control.

## Documentation

Document creation:

```bash
gpg --symmetric \
    --cipher-algo AES256 \
    --output ~/.config/mailAgent/credentials.json.gpg \
    ~/.config/mailAgent/credentials.json
```

Document verification:

```bash
gpg --decrypt ~/.config/mailAgent/credentials.json.gpg
```

Document removal of plaintext after verification:

```bash
shred -u ~/.config/mailAgent/credentials.json
```

## Tests

Use mocking for GPG calls. Tests must not require a real GPG key or real
password.

Cover:

- successful decryption;
- missing encrypted file;
- insecure file mode;
- GPG executable missing;
- non-zero GPG result;
- malformed decrypted JSON;
- missing credential ID;
- missing/empty password field;
- `credentialId` precedence over `passwordEnv`;
- `passwordEnv` fallback;
- password never appears in discovery result;
- password never appears in raised CLI message;
- credential core has no Textual dependency.

Run:

```bash
python -m pytest
black --check src tests
runLinter
```

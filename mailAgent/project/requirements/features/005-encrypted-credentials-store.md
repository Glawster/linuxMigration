# REQ-005 - Encrypted credentials store

## Purpose

Provide persistent mailbox credentials without requiring shell exports and
without storing passwords in plaintext configuration or application state.

## Requirements

1. The default credential store is:
   `~/.config/mailAgent/credentials.json.gpg`.
2. The encrypted payload is JSON.
3. Main mailbox configuration refers to credentials using `credentialId`.
4. GPG is the supported encryption/decryption mechanism.
5. mailAgent must decrypt through a subprocess pipe and read plaintext from
   stdout directly into memory.
6. Decrypted credentials must never be written to a temporary file.
7. The application must never include passwords in:
   - logs;
   - CLI output;
   - TUI output;
   - JSON discovery output;
   - snapshots;
   - persistent state;
   - exception messages.
8. The encrypted store must remain outside the repository.
9. The encrypted file should use restrictive permissions; mailAgent should warn
   or reject unsafe permissions according to implementation policy.
10. Missing credential stores must generate a clear secret-free error.
11. Invalid GPG data or failed decryption must generate a clear secret-free
    error.
12. Malformed decrypted JSON must generate a clear secret-free error.
13. Missing `credentialId` entries must generate a clear secret-free error.
14. Existing `passwordEnv` support may remain as a migration fallback.
15. If both `credentialId` and `passwordEnv` exist, `credentialId` wins.
16. Plaintext JSON is never an accepted normal runtime store.
17. Credential loading must remain independent of Textual/UI code.
18. A configurable credential-store path may be supported for testing and
    advanced use.

## Acceptance criteria

- mailAgent successfully authenticates using an encrypted credential store;
- decrypted data is handled only in memory;
- no password appears in discovery output or logs;
- support for five independent credential IDs works;
- a missing GPG executable produces a clear error;
- failed decryption does not expose GPG secret output;
- malformed decrypted JSON is handled cleanly;
- missing credential IDs are reported without exposing secrets;
- compatibility fallback using `passwordEnv` still functions;
- core credential tests do not depend on Textual.


## Delivery status

Implemented with a core GPG-backed credential resolver, explicit credential-ID
precedence, environment compatibility, restrictive file checks and secret-free
per-account failures. Configuration supports an optional `general.credentialsFile`
override. Tests use mocked GPG and IMAP calls; no real keys or credential stores
are needed. See [setup and runtime behaviour](../../../documentation/credentials.md).

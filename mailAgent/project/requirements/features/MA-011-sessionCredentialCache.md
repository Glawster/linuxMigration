# MA-011 Login-session mailbox password cache

Status: Completed

## Purpose

Load mailbox passwords from the encrypted GPG file once, then reuse them across
mailAgent closure, reopening and refreshes during the same PC login session.
Logout or shutdown ends access to the cache. The cached values are the mailbox
passwords, not the GPG unlock passphrase.

## Delivered behavior

- Opt-in `general.credentialsSessionCache = true`; enabled in the user's local
  configuration and shown in the example. Omission preserves existing behavior.
- Use Linux kernel PAM session keyring `_ses`, inherited by application launches,
  with possession-only permissions. Never use an ENV variable, plaintext file,
  user-wide keyring or persistent keyring to hold mailbox passwords.
- Require keyutils and a PAM login session configured with `pam_keyinit ... revoke`.
  This PC's GDM and console login profiles already provide `force revoke`.
- Validate the encrypted store's location, type and permissions before cache
  access. Bind entries to its resolved path and encrypted contents; changes
  require another GPG load. Cache only credential IDs and password fields.
- Cache errors use fixed messages. Unsupported launch contexts fail explicitly
  when caching is enabled; set the option false to use normal GPG loading.
- Legacy `passwordEnv` accounts keep their existing behavior.

## Validation

Tests cover reopening, a fresh login cache, store changes, permission failures,
invalid JSON, cache errors, disabled caching and discovery output secrecy.
A real kernel smoke check uses only fictional credentials in an isolated test
session: separate processes reuse its cache, then keyring revocation prevents
access. No real mailbox password was loaded or printed for verification.

See [credential setup and runtime behavior](../../../documentation/credentials.md).

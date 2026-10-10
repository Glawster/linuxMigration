# Requirements

New requirement records use the stable project prefix `MA`. Existing numeric
records retain their allocated paths.

Next available number: 012

## Requirement index

| Req ID | Requirement | Description | Status | Agent Prompt | Architecture Decisions |
| --- | --- | --- | --- | --- | --- |
| 003 | [Existing mailbox and filter discovery](features/003-mailbox-discovery.md) | Read-only audit of IMAP folders, local archives and Thunderbird filters. | Completed | [Prompt](../prompts/003-mailbox-discovery.md) | Not required |
| 004 | [Archive taxonomy and mail migration](features/004-archive-taxonomy-migration.md) | Plan personal mail against the local archive taxonomy. Execution remains a later increment. | InProgress | [Prompt](../prompts/004-archive-taxonomy-migration.md) | Not required |
| 005 | [Encrypted credentials store](features/005-encrypted-credentials-store.md) | Keep mailbox passwords in a GPG-encrypted store. | Completed | [Prompt](../prompts/005-encrypted-credentials-store.md) | Not required |
| 006 | [Inbox interest and daily digest](features/006-inbox-interest-daily-digest.md) | Choose which Inbox senders belong in a daily digest. Filing is REQ-009. | Completed | Not recorded | Not required |
| 007 | [Unsubscribe discovery and action](features/007-unsubscribe-discovery-action.md) | Find unsubscribe actions and let the user run one explicitly. | ToDo | Not recorded | Not required |
| 008 | [Plan resolution and approval](features/008-plan-resolution-approval.md) | Record review decisions before any mailbox mutation. Later increments remain. | InProgress | Not recorded | Not required |
| 009 | [Read Inbox filing](features/009-read-inbox-filing.md) | Review where read Inbox mail belongs. Ignore leaves it in the Inbox. Junk marks it for Thunderbird's junk filter. | InProgress | Not recorded | Not required |
| 010 | [Approved mailbox change execution](features/010-approved-mailbox-change-execution.md) | Execute approved personal-mail changes with revalidation, verification, journaling and retry safety. | InProgress | Not recorded | Not required |
| MA-011 | [Login-session mailbox password cache](features/MA-011-sessionCredentialCache.md) | Reuse mailbox passwords across launches, until login-session logout or shutdown. | Completed | Not recorded | Not required |

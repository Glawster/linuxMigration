# Codex Prompt - REQ-004 Archive taxonomy and mail migration

Implement REQ-004 using the repository's OMP instructions.

## Important role distinctions

Do not treat every mailbox the same.

### personal

- Andy: `andyw@glawster.com`, local archive `myMail`
- Kathy: `kathyw@glawster.com`, local archive `kathyMail`

For personal mailboxes, use configurable `liveYear` (initially 2026):

- live-year -> IMAP
- older -> local archive

The existing local folder hierarchy is canonical.

### legacy

- `andy@glawster.com`
- migration target: Andy current

Plan:

- live-year -> matching Andy-current IMAP destination
- older -> matching `myMail` destination

### shared

- `info@hillsboroughwalkingfootball.com`

This mailbox is used by other people.

Do not apply personal archive taxonomy to it. Preserve/discover its own
server-side organisation. Any proposed changes must be suitable for a shared
mailbox and reviewable.

### support

- `info@clanneolas.com`

This mailbox is access-only for this requirement.

Allow reading, audit, attention/highlight classification and TUI visibility,
but exclude it from archive/migration planning and folder mirroring.

## Implementation priorities

1. Extend configuration validation with mailbox roles.
2. Add read-only local archive discovery for personal roots.
3. Build canonical folder mapping for personal mailboxes.
4. Build legacy migration planning.
5. Ensure shared/support mailboxes are excluded from personal migration logic.
6. Add TUI views for mapping, proposed moves and review queue.
7. Keep execution disabled or safe-by-default.

## Required tests

Include tests proving:

- support mailbox gets no archive proposals;
- shared mailbox never maps into personal local archives;
- personal mail obeys liveYear split;
- legacy current-year mail targets Andy current;
- legacy older mail targets `myMail`;
- five mailboxes may have independent hosts;
- core logic has no Textual dependency;
- planning mode performs no mutation.

Run:

```bash
python -m pytest
black --check src tests
runLinter
```

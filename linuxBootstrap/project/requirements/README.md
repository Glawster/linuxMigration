# Requirements

Requirement records for linuxBootstrap. The shared conventions are in
[`.github/repositoryLayout.md`](../../../.github/repositoryLayout.md).

- Prefix: `LB`
- Next available number: `LB-002`
- Records stay at their allocated path in `features/` for their whole
  lifecycle; status changes are recorded here and in the record itself.
- Living documentation owned by a requirement lives in
  `documentation/<name>/`, where `<name>` is the record name without its
  prefix and number.

## ToDo

None.

## In Progress

- [LB-001 raidMigration](features/LB-001-raidMigration.md): migrate andy-pc
  storage to raid-pc with verified, resumable, auditable copies. Implemented
  and tested against mocks; awaiting the raid-pc storage layout and parity
  before the first real migration.

## Completed

None.

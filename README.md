# linuxMigration

Scripts and tools for setting up, migrating and organising Andy's Linux
machines and data. The repository is cloned to `~/bin`, so top-level scripts
and launchers are on `PATH`.

## Documentation

- [Agent session listing](documentation/agentSessions.md)

- [linuxBootstrap: machine configuration](linuxBootstrap/linuxBootstrapIndex.md)
  - [Migrating andy-pc storage to raid-pc (migrateToRaid)](linuxBootstrap/documentation/migrateToRaid.md)
  - [raid-pc storage server](linuxBootstrap/documentation/raidPc.md)
- [runpodTools: RunPod bootstrap](runpodTools/runpodToolsIndex.md)
- [Repository-specific instructions](.github/additional-instructions.md)
- [Development guidelines](.github/agent-instructions.md)

Shared OMP guides:

- [Repository layout](documentation/repositoryLayout.md)
- [Requirements management](documentation/requirementsManagement.md)
- [Agent implementation workflow](documentation/agentImplementationWorkflow.md)
- [Testing process](documentation/testingProcess.md)
- [Release process](documentation/howToRelease.md)
- [OMP linter](documentation/linter.md)
- [Shared TUI styling](documentation/tuiStyling.md)

Project records:

- [Current increment](project/currentIncrement.md)
- [Roadmap](project/roadmap.md)
- [Requirements](project/requirements/requirementsIndex.md)
- [Architecture decisions](project/adr/adrIndex.md)

## Subprojects

| Folder | Purpose |
| --- | --- |
| `linuxBootstrap/` | Profile-driven configuration of the Linux machines, remote pulls and the raid-pc storage migration |
| `recoveryTools/` | Photo/video recovery pipeline for PhotoRec output |
| `kohyaTools/` | Image processing and LoRA training workflows |
| `runpodTools/` | Modular bootstrap for RunPod instances |

## Notable commands

| Command | Purpose |
| --- | --- |
| `migrateToRaid` | Copy, verify and record migration of andy-pc disks to raid-pc, or to the local `/mnt/media` disk ([guide](linuxBootstrap/documentation/migrateToRaid.md)) |
| `linuxBootstrap/bootstrap.sh` | Preview or apply a machine profile |
| `agentSessions` | List local Codex, Claude, Grok and Copilot sessions ([guide](documentation/agentSessions.md)) |
| `omv` | Launch organiseMyVideo |

Tools that modify data preview by default and act only with `-y`/`--confirm`.
`agentSessions` reads session stores and writes application logs.

## Tests

```bash
./linuxBootstrap/tests/runTests.sh
./linuxBootstrap/tests/migrateToRaidTests.sh
python -m pytest tests
```

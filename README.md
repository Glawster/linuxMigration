# linuxMigration

Scripts and tools for setting up, migrating and organising Andy's Linux
machines and data. The repository is cloned to `~/bin`, so top-level scripts
and launchers are on `PATH`.

## Documentation

- [Repository layout](.github/repositoryLayout.md)
- [Development guidelines](.github/agent-instructions.md)
- [Repository-specific instructions](.github/additional-instructions.md)
- [linuxBootstrap: machine configuration](linuxBootstrap/README.md)
  - [Migrating andy-pc storage to raid-pc (migrateToRaid)](linuxBootstrap/documentation/raidMigration/migrateToRaid.md)
  - [raid-pc storage server](linuxBootstrap/documentation/raidPc.md)
- [runpodTools: RunPod bootstrap](runpodTools/README.md)

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
| `migrateToRaid` | Copy, verify and record migration of andy-pc disks to raid-pc ([guide](linuxBootstrap/documentation/raidMigration/migrateToRaid.md)) |
| `linuxBootstrap/bootstrap.sh` | Preview or apply a machine profile |
| `omv` | Launch organiseMyVideo |

Tools preview by default and act only with `-y`/`--confirm`.

## Tests

```bash
./linuxBootstrap/tests/runTests.sh
./linuxBootstrap/tests/migrateToRaidTests.sh
python -m pytest tests
```

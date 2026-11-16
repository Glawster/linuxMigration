# Hardware snapshots and temperature history (hardwareSnapshot)

## Purpose

`hardwareSnapshot` records what hardware a machine has and how hot it runs, so
that a changed part or a disk running hot shows up between runs. It is a
read-only report: it changes nothing on the machine apart from its own state
folder.

## Usage

```bash
hardwareSnapshot            # full snapshot, temperatures and configuration diff
hardwareSnapshot --temps    # temperatures only, appended to the history
hardwareSnapshot --diff     # the most recent configuration change
hardwareSnapshot --history  # saved snapshots and where the history is kept
hardwareSnapshot --version  # the repository version
```

Each run starts with a header naming the repository version and the host.

## What it records

State is kept per host under
`${XDG_STATE_HOME:-~/.local/state}/hardwareSnapshot/<host>/`:

| Path | Contents |
| --- | --- |
| `snapshots/<timestamp>/` | Raw `lscpu`, `lspci`, `lsblk`, `ip`, `free`, `dmidecode` and `sensors` output |
| `snapshots/<timestamp>/configuration.txt` | The stable configuration compared between runs: host, CPU, memory modules, BIOS, PCI devices, storage devices and network interfaces |
| `latest` | Link to the newest full snapshot |
| `diffs/<timestamp>.diff` | Saved only when the configuration differs from the previous snapshot |
| `temperatures.csv` | One row per reading: `timestamp,kind,device,sensor,temp_c,status` |

## Temperatures

- `sensors` readings are labelled `<chip>: <sensor>`, for example
  `k10temp-pci-00c3: Tctl`, and recorded with status `MEASURED`.
- Disk temperatures come from `smartctl` and are identified by serial number,
  so a disk keeps its history when its `/dev/sdX` name changes. Spinning disks
  are rated `NORMAL` up to 40°C, `WARM` up to 45°C and `HOT` above that; other
  disks are recorded as `MEASURED`.

## Permissions

`smartctl` and `dmidecode` need root. The tool runs them with `sudo -n`, so it
never stops to ask for a password: without passwordless sudo for those
commands, disk temperatures and memory and BIOS details are left out and the
rest of the report still runs.

## Tests

`linuxBootstrap/tests/hardwareSnapshotTests.sh`, run by
`./linuxBootstrap/tests/runTests.sh`, replaces every hardware command with a
double; the tests never read real sensors or disks.

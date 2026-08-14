# DCS World standalone on Linux

linux-bootstrap supports the standalone Eagle Dynamics edition of DCS World.
It does not install the Steam edition and does not replace Eagle Dynamics'
account, licence, module, or update systems.

## Compatibility approach

The module uses [UMU Launcher](https://github.com/Open-Wine-Components/umu-launcher)
to run Proton outside Steam. UMU provides the Steam Runtime container without
requiring the game to belong to Steam. Bootstrap resolves the current
GE-Proton release from its upstream release metadata, verifies its published
SHA-512 checksum, and installs it under
`${XDG_DATA_HOME:-~/.local/share}/Steam/compatibilitytools.d` rather than
hard-coding an aging Wine or Proton runner.
The bootstrap-pinned portable UMU archive is installed for the current user at
`${XDG_DATA_HOME:-~/.local/share}/linuxBootstrap/umu`, with an `umu-run`
symlink in `~/.local/bin`. It is launcher infrastructure, not the Proton
runner; update that archive in `lib/dcs.sh` after reviewing a newer upstream
release and checksum. Using the portable archive avoids coupling DCS support
to a particular Ubuntu base release.

This choice follows the current direction of GE-Proton and Lutris: Lutris uses
UMU when `GE-Proton (Latest)` is selected. Older Wine-GE builds are not pinned.
DCS itself remains an unsupported Windows application from Eagle Dynamics, so
Linux compatibility can regress after DCS, Proton, graphics-driver, or VR
updates.

## Enable and install

The `gaming` profile enables DCS at the large-storage mount:

```yaml
dcs:
  enabled: true
  installDir: /mnt/games/dcs
  vr: false
```

The directory must be absolute, writable by the invoking user, and on a Linux
filesystem with sufficient free space. To opt another profile in, add the same
map with an appropriate path. Omit it or set `enabled: false` to do nothing.

Preview all work:

```bash
./bootstrap.sh install --profile gaming
```

Apply it:

```bash
./bootstrap.sh install --profile gaming --confirm
```

Bootstrap installs UMU when needed, creates a separate prefix, downloads the
official `DCS_World_Web.exe`, and starts it through GE-Proton. The Eagle
Dynamics installer is interactive. Bootstrap maps Wine drive `G:` to the
parent of the profile's `installDir`; for the gaming profile choose
`G:\\dcs`, which corresponds to `/mnt/games/dcs`. Then
authenticate with the existing Eagle Dynamics account when prompted. Large
game and module downloads, authentication, licence acceptance, and any dialogs
remain manual.

The compatibility prefix is stored at:

```text
${XDG_DATA_HOME:-~/.local/share}/dcs/prefix
```

The installer cache is `${XDG_CACHE_HOME:-~/.cache}/linuxBootstrap/`. The game
payload is kept at `installDir`, not in the prefix.

## Launch, update, repair, and status

Bootstrap creates these commands in `~/.local/bin`:

```bash
dcs-world
dcs-updater
dcs-repair
```

`dcs-updater` runs the installed Eagle Dynamics `DCS_updater.exe` normally;
`dcs-repair` runs it with `repair`. Continue using the DCS launcher/updater for
updates and module management. Bootstrap deliberately does not reproduce that
logic. A desktop entry for DCS World is also created.

Inspect without changing anything:

```bash
./bootstrap.sh status --profile gaming
```

Status covers profile enablement, UMU, the prefix, DCS and updater executables,
the launcher, and Steam availability when VR is enabled.

## Valve Index and VR

First leave `vr: false` and verify normal 2D DCS. Then install and verify SteamVR
and the Valve Index independently, enable an OpenXR runtime, change `vr` to
`true`, and test again. The flag reports VR prerequisites and guidance but does
not alter DCS graphics settings or make VR a condition of installation.

## Troubleshooting

- If the installer cannot see `/mnt/games`, confirm the mount exists and is
  writable. UMU exposes the parent of `installDir` to its runtime container.
- If a launcher is not found, add `~/.local/bin` to `PATH` or use its full path.
- For DCS file corruption, run `dcs-repair`; for ordinary updates, run
  `dcs-updater`.
- For runner diagnostics, launch with `UMU_LOG=1` and optionally
  `PROTON_LOG=1`. Re-test in 2D before diagnosing SteamVR/OpenXR.
- Consult Eagle Dynamics' [installation guidance](https://www.digitalcombatsimulator.com/en/support/faq/DCS_versions/)
  and [repair guidance](https://www.digitalcombatsimulator.com/en/support/faq/repair/)
  for updater behaviour. Linux-specific compatibility is community-supported.

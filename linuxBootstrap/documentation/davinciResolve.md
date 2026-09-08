# DaVinci Resolve

DaVinci Resolve is host-specific in this bootstrap:

- `tv-pc` installs and maintains Resolve because it has the NVIDIA graphics card.
- `main-pc` (Andy-PC) explicitly removes Resolve.

The Blackmagic Design download requires accepting its licence terms and filling
in the download form, so bootstrap does not download the installer itself.

## Prepare TV-PC

Download the current **Linux** edition of DaVinci Resolve from Blackmagic
Design and leave the `.zip` or extracted `.run` file in `~/Downloads`.
Resolve Studio installers are also recognised.

Preview the TV-PC profile:

```bash
./bootstrap.sh install --profile tv-pc
```

The preview reports the selected installer and checks whether the NVIDIA driver
is visible. Apply from the graphical desktop:

```bash
./bootstrap.sh install --profile tv-pc --confirm
```

Bootstrap installs the Ubuntu libraries declared by `tv-pc`, checks for
`nvidia-smi`, validates and extracts the archive when necessary, and launches
the official installer. Package checking is skipped only at the installer layer
because Blackmagic officially targets a different Linux distribution; the
required Pop!_OS packages are managed explicitly by the profile.

Run Resolve afterwards with:

```bash
~/bin/davinci-resolve
```

## Remove from Andy-PC

First preview the removal:

```bash
./bootstrap.sh install --profile main-pc
```

The preview must include:

```text
would uninstall DaVinci Resolve from this host
```

Only then apply it:

```bash
./bootstrap.sh install --profile main-pc --confirm
```

Removal uses Blackmagic's own `/opt/resolve/installer -u` command. If Resolve
is already absent, bootstrap makes no change. If `/opt/resolve` exists without
the official uninstaller, bootstrap stops rather than deleting it directly.
The bootstrap-owned launcher under `~/bin` is also removed.

## Notes

- Free Resolve on Linux has more limited H.264/H.265 and AAC support than the
  Windows/macOS editions; transcoding source footage may still be required.
- Keep the NVIDIA driver managed by Pop!_OS rather than installing NVIDIA's
  standalone `.run` driver.
- Repeated bootstrap runs preserve an existing `/opt/resolve` installation and
  repair only the `~/bin/davinci-resolve` launcher.

# Media Center Master

Media Center Master is a Windows application. The `media` profile runs it in a
dedicated 64-bit Wine prefix at `~/.wine-mcm` and keeps it separate from other
Wine applications.

## Install

Preview all work first:

```bash
./bootstrap.sh install --profile media
```

Then apply it from the graphical Pop!_OS desktop:

```bash
./bootstrap.sh install --profile media --confirm
```

Bootstrap installs Wine, Winetricks and unzip; creates the prefix; installs
.NET Framework 4.8 and Microsoft core fonts; configures the declared media
drive mappings; downloads the current setup archive from the official Media
Center Master site; and opens its Windows installer. Complete that installer
using its default `Media Center Master` destination.

The .NET and application installers display Windows dialogs and can take
several minutes. Do not run the confirmed installation through SSH without a
working graphical display.

## Run

After installation, run:

```bash
media-center-master
```

Bootstrap creates that launcher under `~/.local/bin`. The repository's legacy
`runMCM.sh` launcher remains available for the default prefix.

## Media drives

| Wine drive | Linux path |
| --- | --- |
| `H:` | `/mnt/home` |
| `M:` | `/mnt/movie1` |
| `N:` | `/mnt/movie2` |
| `P:` | `/mnt/myPictures` |
| `V:` | `/mnt/myVideo` |
| `W:` | `/mnt/video1` |
| `X:` | `/mnt/video2` |
| `Y:` | `/mnt/video3` |

Edit `profiles/media.yaml` if the mount layout or preferred Windows letters
changes. A mapping uses the format `letter|/absolute/Linux/path`.

MCM settings and credentials remain in the local Wine prefix and are not
stored in Git. Copy or restore those settings separately if an existing MCM
configuration must be migrated from another machine.

## Status and recovery

Inspect the profile without changing anything:

```bash
./bootstrap.sh status --profile media
```

Repeated confirmed runs preserve an existing prefix and MCM installation while
repairing missing drive mappings or the launcher. If setup is interrupted,
rerun the same confirmed bootstrap command.

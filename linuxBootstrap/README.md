# linux-bootstrap

Reusable, profile-driven configuration for Pop!_OS machines. Operations are
idempotent and previewed by default, making the same configuration safe to run
again after an installation or upgrade.

## Documentation

- [Design and architecture](docs/DESIGN.md)
- [Network naming and static addresses](documentation/networking.md)
- [NFS exports and mounts](documentation/nfs.md)
- [User configuration and VS Code extensions](documentation/userConfiguration.md)
- [Roadmap](docs/ROADMAP.md)

## Command line

Clone this repository, enter the project, and preview a host profile:

```bash
git clone <repository-url> ~/bin
cd ~/bin/linuxBootstrap
./bootstrap.sh install --profile tv-pc
```

Review the summary, then apply it:

```bash
./bootstrap.sh install --profile tv-pc --confirm
```

Multiple role profiles can be composed explicitly:

```bash
./bootstrap.sh install --profile common --profile gaming
```

The former `./bootstrap.sh --profile NAME` syntax remains an alias for
`install`.

### Install, update, and status

`install` converges declared packages and configuration. `update` first
converges the profile, then inspects and updates everything already installed:

```bash
./bootstrap.sh update --profile main-pc
./bootstrap.sh update --profile main-pc --confirm
```

The preview uses currently cached apt and Flatpak metadata. A confirmed update
refreshes metadata, runs a normal apt upgrade, and updates system Flatpaks. It
does not perform a distribution release upgrade, autoremove packages, or remove
software absent from a profile. Update candidates are classified as:

- `managed`: declared by a loaded profile;
- `unmanaged`: a manually installed apt package or system Flatpak;
- `system`: an automatically installed apt dependency.

Use `status` for a read-only compliance inspection:

```bash
./bootstrap.sh status --profile tv-pc
```

### Profiles

Profiles have their own inspection and authoring commands:

```bash
./bootstrap.sh profile list
./bootstrap.sh profile show main-pc
./bootstrap.sh profile validate
./bootstrap.sh profile add office-extra
./bootstrap.sh profile add office-extra --confirm
```

`profile add` is also preview-only unless confirmed. `capture` is reserved for
the planned master-host configuration capture workflow and currently exits
without changing anything.

### Logs

Every invocation writes its complete terminal output to a timestamped log while
continuing to display it interactively. Logs are stored with user-only
permissions under:

```text
${XDG_STATE_HOME:-~/.local/state}/linuxBootstrap/
```

The log path is printed at startup. Configuration modules must not print
credentials, tokens, private keys, or other secrets.

## Architecture

`bootstrap.sh` parses input and calls small modules in dependency order.
`profiles/` contains data rather than executable logic. Host profiles inherit
role profiles through their `profiles` list. Modules under `lib/` expose one
public `<domain>Apply` function and do not depend on each other's internals.

The bootstrap supports apt packages and system-wide Flatpak applications from
Flathub. Snap declarations are recognized and reported without being applied,
preserving a stable profile schema while that backend is developed.

## Profile format

Add `profiles/<name>.yaml` using the supported keys:

```yaml
name: example

apt:
  - curl

packages:
  snap:
    - example-package

services:
  - ssh

git:
  name: Example User
  email: user@example.com
  defaultBranch: main

managedFiles:
  - shell/aliases|.bash_aliases

vscodeExtensions:
  - openai.chatgpt
```

Host files belong in `profiles/hosts/` and may inherit profiles:

```yaml
hostname: example-pc
master: true
expectedIp: 192.168.1.10

profiles:
  - common
  - development

network:
  connection: Wired connection 1
  address: 192.0.2.20/24
  gateway: 192.0.2.1
  dns: 192.0.2.1, 1.1.1.1

nfsMounts:
  - server:/srv/media /mnt/media ro,_netdev,nofail,x-systemd.automount
```

Exactly one host profile must set `master: true`. This identifies the machine
from which reviewed user configuration may be captured; it does not make
ordinary bootstrap runs copy live files from that machine. Other hosts consume
configuration committed to this repository.

`expectedIp` records an address reserved by the router's DHCP service. Bootstrap
validates and reports it but does not replace DHCP with local static addressing.
The complete reservation inventory, including devices not managed by this Linux
bootstrap, is kept in [`configs/network.yaml`](configs/network.yaml).

Keep secrets and SSH private keys out of profiles and version control.
Managed-file sources are relative to `configs/`; destinations are relative to
the invoking user's home directory. Review the networking and NFS guides before
enabling settings that can affect connectivity or persistent mounts.

## Adding a module

Create a focused file under `lib/`, expose one public workflow function, use
the logging and `changeRun` helpers, and check current state before changing
it. Source the module in `modulesLoad`, then call it in dependency order from
`bootstrapRun`. Add tests for both already-configured and change-required
states.

## Adding a package manager

Add a profile list key and a backend in `lib/packages.sh`. The backend must
provide presence detection and an idempotent install action, must honor
`dryRun`, and must not update or install unrelated packages. Keep manager
details outside `bootstrap.sh`. Update support must inventory installed packages
separately from profile declarations: declarations require presence, while the
update command maintains both managed and unmanaged installed software.

## Testing

The test suite needs only Bash and uses temporary command doubles rather than
changing the machine:

```bash
./tests/runTests.sh
```

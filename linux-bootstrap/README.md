# linux-bootstrap

Reusable, profile-driven configuration for Pop!_OS machines. Operations are
idempotent and previewed by default, making the same configuration safe to run
again after an installation or upgrade.

## Documentation

- [Design and architecture](docs/DESIGN.md)
- [Roadmap](docs/ROADMAP.md)

## Installation

Clone this repository, enter the project, and preview a host profile:

```bash
git clone <repository-url> ~/bin
cd ~/bin/linux-bootstrap
./bootstrap.sh --profile tv-pc
```

Review the summary, then apply it:

```bash
./bootstrap.sh --profile tv-pc --confirm
```

Multiple role profiles can be composed explicitly:

```bash
./bootstrap.sh --profile common --profile gaming
```

Use `./bootstrap.sh --help` for hostname, networking, and diagnostic options.
Static-IP input is validated, but applying it is deferred until connection
selection can be made safely.

## Architecture

`bootstrap.sh` parses input and calls small modules in dependency order.
`profiles/` contains data rather than executable logic. Host profiles inherit
role profiles through their `profiles` list. Modules under `lib/` expose one
public `<domain>Apply` function and do not depend on each other's internals.

The initial release supports apt packages. Flatpak and Snap declarations are
recognized and reported without being applied, preserving a stable profile
schema while their backends are developed.

## Creating a profile

Add `profiles/<name>.yaml` using the supported keys:

```yaml
name: example

apt:
  - curl

services:
  - ssh

git:
  name: Example User
  email: user@example.com
  defaultBranch: main
```

Host files belong in `profiles/hosts/` and may inherit profiles:

```yaml
hostname: example-pc

profiles:
  - common
  - development
```

Keep secrets and SSH private keys out of profiles and version control.

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
details outside `bootstrap.sh`.

## Testing

The test suite needs only Bash and uses temporary command doubles rather than
changing the machine:

```bash
./tests/runTests.sh
```

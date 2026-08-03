# Design

## Goals

The framework turns declarative role and host profiles into repeatable system
configuration. Its boundaries are designed for workstations, laptops, gaming
machines, servers, and virtual machines without placing host-specific choices
inside shell code.

## Execution model

The entry point performs these stages:

1. Parse and validate command-line input.
2. Resolve role or host profiles and recursively load inheritance.
3. Merge lists in load order and let host scalar values override roles.
4. Inspect machine state and apply modules in dependency order.
5. Print counts for proposed/applied, already-correct, and failed operations.

The default is dry-run. `--confirm` enables changes. Each mutating module first
queries current state and routes necessary work through `changeRun`.

## Profile format

The parser intentionally supports a small YAML subset: top-level scalars,
top-level string lists, and the `git` string map. This avoids requiring a YAML
package before the package module can run. Extending the schema requires a
parser test. If profiles later need anchors, nested objects, or typed values,
the parser should move behind the same functions and use a packaged YAML tool.

Profiles are merged as follows:

- inherited profiles load before the host profile;
- list values are appended and package presence checks make duplicates safe;
- later scalar and Git map values override earlier values;
- inheritance cycles are detected and reported before configuration begins.

## Module contract

Modules own one domain and expose an apply workflow. They may use the common
logging, state, and execution helpers, but should not call another domain
module. Commands receive arguments as arrays; configuration is never evaluated
as shell code. Failures propagate through `set -Eeuo pipefail` and the error
trap includes command and line context.

## Security and safety

- Profiles contain no credentials or private key material.
- Variables are quoted and profile values are passed as command arguments.
- Privileged operations invoke `sudo` only at the final mutation.
- Static networking is not changed until a connection can be selected
  explicitly; choosing one implicitly could disconnect a remote bootstrap.
- Repository definitions will use named records rather than arbitrary clone
  commands when that module is implemented.

## Extensibility

Package-manager support stays behind `packagesApply`. Additional domains such
as GNOME settings, Docker, mounts, fonts, and user services should each receive
a profile schema, a focused module, status inspection, and isolated tests.
Future `--status` and `--repair` modes will reuse module inspection rather than
introduce separate configuration logic.

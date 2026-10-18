#!/usr/bin/env bash
# Migrate andy-pc storage to raid-pc: copy, verify, record, and remove source
# data only when explicitly requested and proven safe. See
# documentation/raidMigration.md.

set -euo pipefail

_scriptDir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
# shellcheck source=lib/raidMigration.sh
source "$_scriptDir/lib/raidMigration.sh"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    raidMigrationMain "$@"
fi

#!/usr/bin/env bash
# Copy files from a remote host, then remove each source after success.
# Use this for non-video transfers; pullTvPcVideos.sh keeps video defaults.

set -euo pipefail

_scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/remotePull.sh
source "$_scriptDir/lib/remotePull.sh"

applicationName="pullRemote"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    remotePullMain "$@"
fi

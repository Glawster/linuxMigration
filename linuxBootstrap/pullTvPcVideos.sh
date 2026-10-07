#!/usr/bin/env bash
# Copy video files from andy@tv-pc ~/downloads to /mnt/video2/toFile.
# Other file types can reuse lib/remotePull.sh or pass --ext / --all.

set -euo pipefail

_scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/remotePull.sh
source "$_scriptDir/lib/remotePull.sh"

applicationName="pullTvPcVideos"
remoteUser="andy"
remoteHost="tv-pc"
dest="/mnt/video2/toFile"
mountPath="/mnt/video2"
includeExts=(3gp avi flv m2ts m4v mkv mov mp4 mpeg mpg mts ts webm wmv)

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    remotePullMain "$@"
fi

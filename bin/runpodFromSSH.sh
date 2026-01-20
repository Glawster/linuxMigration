#!/usr/bin/env bash
# Wrapper script to run runpodFromSSH.sh from bin directory
# This preserves the git repository context

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/runpodTools/runpodFromSSH.sh" "$@"

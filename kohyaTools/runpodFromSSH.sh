#!/usr/bin/env bash
# runpodFromSSH.sh (backward compatibility wrapper)
#
# This script is deprecated. Please use the modular version:
#   kohyaTools/runpod/runpodFromSSH.sh
#
# This wrapper forwards all arguments to the new modular script.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat >&2 <<'NOTICE'
=============================================================================
NOTICE: You are using a backward compatibility wrapper.

The runpod scripts have been modularized for better maintainability.
Please update your workflows to use:
  kohyaTools/runpod/runpodFromSSH.sh

This wrapper will forward your arguments to the new script.
=============================================================================

NOTICE

exec "$SCRIPT_DIR/runpod/runpodFromSSH.sh" "$@"

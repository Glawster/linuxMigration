#!/usr/bin/env bash
# runpodBootstrap.sh (backward compatibility wrapper)
#
# This script is deprecated. The runpod scripts have been modularized.
# 
# For local usage, use:
#   kohyaTools/runpod/runpodFromSSH.sh
#
# For remote usage (on RunPod instance), use:
#   /workspace/runpod/runpodBootstrap.sh
#
# This wrapper attempts to detect context and forward appropriately.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat >&2 <<'NOTICE'
=============================================================================
NOTICE: You are using a backward compatibility wrapper.

The runpod scripts have been modularized. Please use:
  - Local: kohyaTools/runpod/runpodFromSSH.sh
  - Remote: /workspace/runpod/runpodBootstrap.sh

This wrapper will forward to the appropriate script.
=============================================================================

NOTICE

# If we're in /workspace, assume remote context
if [[ -d "/workspace" && "$PWD" == /workspace* ]]; then
  exec /workspace/runpod/runpodBootstrap.sh "$@"
else
  # Local context - show usage
  echo "ERROR: This is the old bootstrap script."
  echo "For local usage, use: $SCRIPT_DIR/runpod/runpodFromSSH.sh"
  echo "For remote usage on RunPod, the new script will be copied to /workspace/runpod/"
  exit 1
fi

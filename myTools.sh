#!/usr/bin/env bash
# myTools.sh — launch the My Tools launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/myTools.py" "$@"

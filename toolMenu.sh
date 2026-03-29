#!/usr/bin/env bash
# toolMenu.sh — launch the Linux Migration tool menu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/toolMenu.py" "$@"

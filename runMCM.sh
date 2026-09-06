#!/usr/bin/env bash
set -Eeuo pipefail
export WINEPREFIX="$HOME/.wine-mcm"
export WINEDEBUG=-all
exec wine "$WINEPREFIX/drive_c/Program Files (x86)/Media Center Master/MCMStubLauncher.exe"

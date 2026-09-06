i#!/usr/bin/env bash
export WINEPREFIX="$HOME/.wine-mcm"
export WINEDEBUFG=-all
exec wine "$WINEPREFIX/drive_c/Program Files (x86)/Media Center Master/MCMStubLauncher.exe"

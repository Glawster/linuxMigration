#!/usr/bin/env bash
set -e

# --------- CONFIG (change if needed) ----------
WGE="$HOME/.local/share/lutris/runners/wine/wine-ge-8-26-x86_64/bin/wine"
PFX_ROOT="/mnt/games2/prefixes"
PFX_NAME="battlenet"
PFX="$PFX_ROOT/$PFX_NAME"
INSTALLER="${1:-$HOME/Downloads/Battle.net-Setup.exe}"
LOGFILE="$HOME/battlenet-prefix.log"
# ---------------------------------------------

echo "== Battle.net Wine prefix setup =="
echo "Wine runner : $WGE"
echo "Prefix      : $PFX"
echo "Installer   : $INSTALLER"
echo "Log file    : $LOGFILE"
echo

# basic checks
if [ ! -x "$WGE" ]; then
  echo "ERROR: wine-ge-8-26 not found at:"
  echo "  $WGE"
  echo "Install it in Lutris (Runners → Wine → Manage versions)."
  exit 1
fi

if [ ! -f "$INSTALLER" ]; then
  echo "ERROR: Installer not found:"
  echo "  $INSTALLER"
  echo "Usage: $0 /path/to/Battle.net-Setup.exe"
  exit 1
fi

if ! command -v winetricks >/dev/null 2>&1; then
  echo "ERROR: winetricks not installed. Run:"
  echo "  sudo apt install winetricks"
  exit 1
fi

echo "[1/5] Killing any running Wine processes..."
wineserver -k >/dev/null 2>&1 || true
pkill -9 wine      >/dev/null 2>&1 || true
pkill -9 wineserver >/dev/null 2>&1 || true

echo "[2/5] Removing old prefix (if it exists)..."
rm -rf "$PFX"
mkdir -p "$PFX_ROOT"

echo "[3/5] Creating fresh Wine prefix..."
WINEARCH=win64 WINEPREFIX="$PFX" "$WGE" wineboot --init >>"$LOGFILE" 2>&1

echo "[4/5] Installing corefonts, vcrun2015, vcrun2019, winhttp (winetricks)..."
WINE="$WGE" WINEPREFIX="$PFX" \
  winetricks -q corefonts vcrun2015 vcrun2019 winhttp >>"$LOGFILE" 2>&1

echo "[5/5] Launching Battle.net installer (watch the GUI window)..."
echo "      Detailed output continues in: $LOGFILE"
WINEPREFIX="$PFX" "$WGE" "$INSTALLER" >>"$LOGFILE" 2>&1

echo
echo "== DONE =="
echo "Prefix should now be at:"
echo "  $PFX"
echo "Battle.net should be under:"
echo "  $PFX/drive_c/Program Files (x86)/Battle.net/"
echo
echo "Next: add it in Lutris with these settings:"
echo "  Executable:      $PFX/drive_c/Program Files (x86)/Battle.net/Battle.net Launcher.exe"
echo "  Wine prefix:     $PFX"
echo "  Wine version:    wine-ge-8-26-x86_64"
echo "  DXVK (launcher): OFF"
echo "  Env vars:        BATTLE_NET_DISABLE_BROWSER=1, CEF_DISABLE_GPU=1, CEF_ENABLE_GPU=0, --no-sandbox=1"


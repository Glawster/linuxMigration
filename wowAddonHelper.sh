#!/usr/bin/env bash
set -euo pipefail

########################################
# Fixed paths for your setup
########################################

# Battle.net / WoW prefix on ext4
BATTLE_PREFIX="/mnt/games2/prefixes/battlenet"

# Wine runner used by Lutris for Battle.net / WoW
BATTLE_WINE="$HOME/.local/share/lutris/runners/wine/wine-10.20-staging-tkg-amd64/bin/wine"

export WINEPREFIX="$BATTLE_PREFIX"
export WINE="$BATTLE_WINE"

########################################
# Installer locations (Linux paths)
########################################

INSTALLER_DIR="/mnt/games2/installers"

# Zygor client installer (adjust if filename changes)
ZYGOR_SETUP="$INSTALLER_DIR/Zygor_Setup_4.8.0.exe"

# TSM Desktop installer (adjust this to your real filename)
TSM_SETUP="$INSTALLER_DIR/TSM_Desktop_App_Setup.exe"

########################################
# Installed app locations (Windows paths in the prefix)
########################################

# Where Zygor normally installs itself
ZYGOR_CLIENT_WIN='C:\users\andy\AppData\Local\Zygor\Zygor.exe'

# Where TSM Desktop typically installs – adjust if your installer uses a different folder
TSM_CLIENT_WIN='C:\Program Files (x86)\TradeSkillMaster Application\app\TSMApplication.exe'

# Wine used by Battle.net / WoW (leave as-is for safety)
BATTLE_WINE="/home/andy/.local/share/lutris/runners/wine/wine-10.20-staging-tkg-amd64/bin/wine"

# Wine used ONLY for Zygor client (more Electron-friendly)
ZYGOR_WINE="/home/andy/.local/share/lutris/runners/wine/wine-ge-8-26-x86_64/bin/wine"

# Default wine for anything else in this script
WINE="${WINE:-$BATTLE_WINE}"

########################################
# Helper functions
########################################

die() {
  echo "ERROR: $*" >&2
  exit 1
}

check_runner() {
  if [ ! -x "$WINE" ]; then
    die "Wine runner not found or not executable at: $WINE
Expected Lutris runner wine-10.20-staging-tkg-amd64."
  fi
}

check_prefix() {
  if [ ! -d "$WINEPREFIX" ]; then
    die "WINEPREFIX not found at: $WINEPREFIX
Make sure Lutris has created the Battle.net prefix first."
  fi
}

check_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    die "File not found: $path"
  fi
}

show_env() {
  echo "Using:"
  echo "  WINE      = $WINE"
  echo "  WINEPREFIX= $WINEPREFIX"
}

########################################
# Actions
########################################

do_zygor_install() {
  show_env
  check_runner
  check_prefix
  check_file "$ZYGOR_SETUP"

  echo "Running Zygor installer with Battle.net prefix..."
  "$ZYGOR_WINE" "$ZYGOR_SETUP"
  echo "Zygor installer finished. If needed, adjust ZYGOR_CLIENT_WIN in this script."
}

do_zygor_client() {
  show_env
  check_runner
  check_prefix

  export ELECTRON_ENABLE_LOGGING=1
  export ELECTRON_FORCE_PREFER_GL=1
  export WINEDLLOVERRIDES="d3d11=n;dxgi=n;d3dcompiler_47=n"

  echo "Launching Zygor client..."
  "$ZYGOR_WINE" "$ZYGOR_CLIENT_WIN"

}

do_tsm_install() {
  show_env
  check_runner
  check_prefix
  check_file "$TSM_SETUP"

  echo "Running TSM Desktop installer with Battle.net prefix..."
  "$ZYGOR_WINE" "$TSM_SETUP"
  echo "TSM installer finished. If needed, adjust TSM_CLIENT_WIN in this script."
}

do_tsm_client() {
  show_env
  check_runner
  check_prefix

  echo "Launching TradeSkillMaster Desktop..."
  "$ZYGOR_WINE" "$TSM_CLIENT_WIN"
}

kill_wine_for_prefix() {
    echo "Killing wineserver for prefix: $WINEPREFIX"

    # Try with Battle.net Wine
    if [ -x "$BATTLE_WINE" ]; then
        echo "  - Using Battle.net Wine: $BATTLE_WINE server -k"
        WINEPREFIX="$WINEPREFIX" "$BATTLE_WINE" server -k || true
    fi

    # Try with Zygor Wine
    if [ -x "$ZYGOR_WINE" ]; then
        echo "  - Using Zygor Wine: $ZYGOR_WINE server -k"
        WINEPREFIX="$WINEPREFIX" "$ZYGOR_WINE" server -k || true
    fi

    # Fallback: nuke any wineserver still hanging around
    if command -v wineserver >/dev/null 2>&1; then
        echo "  - Fallback: wineserver -k"
        WINEPREFIX="$WINEPREFIX" wineserver -k 2>/dev/null || true
    fi

    echo "wineserver kill request sent."
}

########################################
# Main
########################################

cmd="${1:-help}"

case "$cmd" in
  zygor-install)
    do_zygor_install
    ;;
  zygor-client)
    do_zygor_client
    ;;
  tsm-install)
    do_tsm_install
    ;;
  tsm-client)
    do_tsm_client
    ;;
  env)
    show_env
    ;;
  kill-wine)
    echo "Using:"
    echo "  WINEPREFIX= $WINEPREFIX"
    echo "Attempting to kill wineserver processes for this prefix..."
    kill_wine_for_prefix
    ;;
  help|*)
    cat <<EOF
Usage: $0 <command>

Commands:
  zygor-install   Run the Zygor installer in the Battle.net prefix
  zygor-client    Launch the installed Zygor client

  tsm-install     Run the TradeSkillMaster Desktop installer in the Battle.net prefix
  tsm-client      Launch the installed TSM Desktop client

  env             Show WINE and WINEPREFIX being used

Notes:
  - This script always uses:
      WINE      = $BATTLE_WINE
      WINEPREFIX= $BATTLE_PREFIX
  - Adjust ZYGOR_SETUP, TSM_SETUP, ZYGOR_CLIENT_WIN, and TSM_CLIENT_WIN above if paths differ.
EOF
    ;;
esac

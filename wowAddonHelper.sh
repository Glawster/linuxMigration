#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# wowAddonHelper.sh — WoW addon helper (Linux / Wine)
#
# Goals:
# - Launch addon clients using the SAME WoW Wine prefix
# - Never mix Wine versions (no system wine, no alternate runners)
# - Provide a kill option to stop wineserver processes cleanly
# - Safe, idempotent, explicit (no magic auto-detection)
# - Easy to extend
#
# Not in scope: CurseForge (native Linux)
# ============================================================

# ----------------------------
# Fixed configuration (EXPLICIT)
# ----------------------------
WINE_PREFIX="/mnt/games2/prefixes/battlenet"
WINE_BIN="/home/andy/.local/share/lutris/runners/wine/wine-10.20-staging-tkg-amd64/bin/wine"

# wineserver/wineboot MUST come from the same runner dir as WINE_BIN
WINE_DIR="$(dirname "$WINE_BIN")"
WINE_SERVER="$WINE_DIR/wineserver"
WINE_BOOT="$WINE_DIR/wineboot"

# Everything lives on /mnt/games2 (installers included)
INSTALLER_DIR="/mnt/games2/installers"

# Defaults (override by passing an explicit path argument to install commands)
DEFAULT_ZYGOR_SETUP="$INSTALLER_DIR/Zygor_Setup.exe"
DEFAULT_TSM_SETUP="$INSTALLER_DIR/TSM_Desktop_App_Setup.exe"

# Installed app locations (Windows paths inside prefix) — EDIT if yours differ
ZYGOR_CLIENT_WIN='C:\users\andy\AppData\Local\Zygor\Zygor.exe'
TSM_CLIENT_WIN='C:\Program Files (x86)\TradeSkillMaster Application\app\TSMApplication.exe'

DEFAULT_WORKDIR="/mnt/games2"
WINEDEBUG_DEFAULT="-all"

# ----------------------------
# Logging / errors
# ----------------------------
log() { printf '%s\n' "[wowAddonHelper] $*"; }
err() { printf '%s\n' "[wowAddonHelper] ERROR: $*" >&2; }
die() { err "$*"; exit 1; }

# ----------------------------
# Guards
# ----------------------------
require_dir()  { [[ -d "$1" ]] || die "missing dir: $1"; }
require_file() { [[ -f "$1" ]] || die "missing file: $1"; }
require_exec() { [[ -x "$1" ]] || die "not found or not executable: $1"; }

assert_config_ok() {
  require_dir "$WINE_PREFIX"
  [[ -d "$WINE_PREFIX/drive_c" ]] || die "prefix does not look valid (missing drive_c): $WINE_PREFIX"

  require_exec "$WINE_BIN"
  require_exec "$WINE_SERVER"
  require_exec "$WINE_BOOT"
}

# ----------------------------
# Wine wrappers (NEVER system wine)
# ----------------------------
wine_env() {
  export WINEPREFIX="$WINE_PREFIX"
  export WINEDEBUG="${WINEDEBUG:-$WINEDEBUG_DEFAULT}"
}

wine_run() {
  wine_env
  "$WINE_BIN" "$@"
}

wine_start() {
  # Detach GUI apps cleanly
  wine_env
  "$WINE_BIN" start /unix "$@"
}

winepath_u() {
  wine_env
  "$WINE_BIN" winepath -u "$1"
}

assert_win_exe_exists() {
  local win_exe="$1"
  local unix_exe
  unix_exe="$(winepath_u "$win_exe" 2>/dev/null || true)"
  [[ -n "$unix_exe" ]] || die "failed to convert windows path: $win_exe"
  [[ -f "$unix_exe" ]] || die "exe not found in prefix: $win_exe (-> $unix_exe)"
}

show_env() {
  log "wine:       $WINE_BIN"
  log "wineserver: $WINE_SERVER"
  log "prefix:     $WINE_PREFIX"
}

# ----------------------------
# Commands
# ----------------------------
cmd_zygor_install() {
  assert_config_ok
  local installer="${1:-$DEFAULT_ZYGOR_SETUP}"
  require_file "$installer"

  show_env
  log "running zygor installer: $installer"
  ( cd "$(dirname "$installer")" && wine_run "$installer" )
  log "zyg0r installer finished"
}

cmd_zygor_client() {
  assert_config_ok
  assert_win_exe_exists "$ZYGOR_CLIENT_WIN"

  show_env
  log "launching zygor client"
  ( cd "$DEFAULT_WORKDIR" && wine_start "$ZYGOR_CLIENT_WIN" ) >/dev/null 2>&1 & disown || true
  log "zyg0r client launched"
}

cmd_tsm_install() {
  assert_config_ok
  local installer="${1:-$DEFAULT_TSM_SETUP}"
  require_file "$installer"

  show_env
  log "running tsm installer: $installer"
  ( cd "$(dirname "$installer")" && wine_run "$installer" )
  log "tsm installer finished"
}

cmd_tsm_client() {
  assert_config_ok
  assert_win_exe_exists "$TSM_CLIENT_WIN"

  show_env
  log "launching tsm desktop app"
  ( cd "$DEFAULT_WORKDIR" && wine_start "$TSM_CLIENT_WIN" ) >/dev/null 2>&1 & disown || true
  log "tsm desktop launched"
}

cmd_wineboot() {
  assert_config_ok
  show_env
  log "running wineboot -u (safe to repeat)"
  wine_env
  "$WINE_BOOT" -u
  log "wineboot complete"
}

cmd_kill_wine() {
  assert_config_ok
  show_env

  wine_env
  log "stopping wineserver for THIS prefix"
  "$WINE_SERVER" -k || true
  "$WINE_SERVER" -w || true

  # Prefix-scoped cleanup: only touch processes that reference THIS prefix path.
  local prefix_escaped
  prefix_escaped="$(printf '%s' "$WINE_PREFIX" | sed 's/[.[\*^$(){}+?|\\/]/\\&/g')"

  local pids
  pids="$(ps -eo pid=,args= | awk -v p="$prefix_escaped" '
    $0 ~ p && ($0 ~ /\/wine($| )/ || $0 ~ /\/wineserver($| )/ || $0 ~ /\/wine-preloader($| )/) { print $1 }
  ' | tr '\n' ' ')"

  if [[ -n "${pids// /}" ]]; then
    log "leftover wine processes for this prefix, SIGTERM: $pids"
    # shellcheck disable=SC2086
    kill -TERM $pids || true
    sleep 1

    local pids2
    pids2="$(ps -eo pid=,args= | awk -v p="$prefix_escaped" '
      $0 ~ p && ($0 ~ /\/wine($| )/ || $0 ~ /\/wineserver($| )/ || $0 ~ /\/wine-preloader($| )/) { print $1 }
    ' | tr '\n' ' ')"

    if [[ -n "${pids2// /}" ]]; then
      log "still running, SIGKILL: $pids2"
      # shellcheck disable=SC2086
      kill -KILL $pids2 || true
    fi
  else
    log "no leftover wine processes found for this prefix"
  fi

  log "kill complete"
}

cmd_status() {
  assert_config_ok
  show_env
  log ""
  log "processes referencing this prefix:"
  local prefix_escaped
  prefix_escaped="$(printf '%s' "$WINE_PREFIX" | sed 's/[.[\*^$(){}+?|\\/]/\\&/g')"
  ps -eo pid=,args= | awk -v p="$prefix_escaped" '$0 ~ p { print }' || true
}

usage() {
  cat <<EOF
Usage: $0 <command> [args...]

Commands:
  zygor-install [installer.exe]   Run Zygor installer in the WoW prefix
  zygor-client                    Launch installed Zygor client in the WoW prefix

  tsm-install [installer.exe]     Run TSM Desktop installer in the WoW prefix
  tsm-client                      Launch installed TSM Desktop app in the WoW prefix

  wineboot                        Run wineboot -u for this prefix (safe)
  kill                            Stop wineserver + clean leftover wine procs for this prefix
  status                          Show config + processes tied to this prefix
  env                             Show config only

Notes:
  - This script ONLY uses:
      WINE_BIN    = $WINE_BIN
      WINEPREFIX  = $WINE_PREFIX
  - It does NOT call system wine or system wineserver.
EOF
}

# ----------------------------
# Main
# ----------------------------
cmd="${1:-help}"
shift || true

case "$cmd" in
  zygor-install) cmd_zygor_install "$@" ;;
  zygor-client)  cmd_zygor_client "$@" ;;
  tsm-install)   cmd_tsm_install "$@" ;;
  tsm-client)    cmd_tsm_client "$@" ;;
  wineboot)      cmd_wineboot "$@" ;;
  kill)          cmd_kill_wine "$@" ;;
  status)        cmd_status "$@" ;;
  env)           assert_config_ok; show_env ;;
  help|-h|--help|"") usage ;;
  *) die "unknown command: $cmd (try: help)" ;;
esac


#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# wowAddonHelper.sh — WoW addon helper (Linux / Wine)
#
# Goals:
# - Launch Wine addon clients using the SAME WoW Wine prefix
# - Install and launch the Linux-native TSM desktop AppImage
# - Never mix Wine versions (no system wine, no alternate runners)
# - Provide a kill option to stop wineserver processes cleanly
# - Safe, idempotent, explicit (no magic auto-detection)
# - Easy to extend
#
# Not in scope: CurseForge (native Linux)
# ============================================================

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source logUtils.sh from organiseMyProjects (adjust path if needed)
# make sure a conda env is activated for this to work
_LOG_UTILS="$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))' 2>/dev/null)/logUtils.sh"
if [[ -f "$_LOG_UTILS" ]]; then
  source "$_LOG_UTILS"
else
  # Fallback: basic log function if organiseMyProjects not installed
  logFile="/dev/null"
  log_init()  { logFile="${HOME}/.local/state/${1}/${1}-$(date +%Y-%m-%d).log"; mkdir -p "$(dirname "$logFile")"; }
  log_info()  { echo "...$1"; }
  log_doing() { echo "$1..."; }
  log_done()  { echo "...$1"; }
  log_warn()  { echo "WARNING: $1" >&2; }
  log_error() { echo "ERROR: $1" >&2; }
  log_value() { echo "...$1: $2"; }
  log_action(){ echo "...$1"; }
  log_box()   { echo "=== $1 ==="; }
fi

log_init "wowAddonHelper"

# ----------------------------
# Fixed configuration (EXPLICIT)
# ----------------------------
WINE_PREFIX="/mnt/games/lutris/games/battlenet"
WINE_BIN="$HOME/.local/share/lutris/runners/wine/wine-ge-8-26-x86_64/bin/wine"
#WINE_BIN="/home/andy/.local/share/lutris/runners/wine/wine-10.20-staging-tkg-amd64/bin/wine"

# wineserver/wineboot MUST come from the same runner dir as WINE_BIN
WINE_DIR="$(dirname "$WINE_BIN")"
WINE_SERVER="$WINE_DIR/wineserver"
WINE_BOOT="$WINE_DIR/wineboot"

# Everything lives on /mnt/games (installers included)
INSTALLER_DIR="/mnt/games/installers"

# Defaults (override by passing an explicit path argument to install commands)
DEFAULT_ZYGOR_SETUP="$INSTALLER_DIR/Zygor_Setup_4.13.2.exe"
DEFAULT_TSM_APPIMAGE="$HOME/Downloads/TradeSkillMaster.AppImage"

# Installed app locations (Windows paths inside prefix) — EDIT if yours differ
ZYGOR_CLIENT_WIN='C:\users\andy\AppData\Local\Zygor\Zygor.exe'

# TSM is a native AppImage and does not use the Wine runner. Its built-in updater
# replaces this file in place, so it needs a stable, user-writable location.
TSM_DIR="/mnt/games/tradeSkillMaster"
TSM_APPIMAGE="$TSM_DIR/TradeSkillMaster.AppImage"
TSM_LOG="$HOME/.local/state/wowAddonHelper/tsmDesktop.log"

# The native app still manages addons in the WoW install inside the Wine prefix.
WOW_DIR="$WINE_PREFIX/drive_c/Program Files (x86)/World of Warcraft"

# Zygor 4.13+ (Electron 11) crashes its GPU process under Wine and shows a blank
# white window; software rendering avoids that.
ZYGOR_CLIENT_ARGS=(--disable-gpu)

DEFAULT_WORKDIR="/mnt/games"
WINEDEBUG_DEFAULT="-all"

# ----------------------------
# Errors / guard helpers
# ----------------------------
die() { log_error "$*"; exit 1; }

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

assert_appimage() {
  # Type 2 AppImages carry the bytes "AI" 0x02 at offset 8 of the ELF header.
  local magic
  magic="$(od -An -tx1 -j8 -N3 "$1" | tr -d ' ')"
  [[ "$magic" == "414902" ]] || die "not a type 2 AppImage: $1"
}

assert_fuse() {
  # The AppImage runtime mounts itself using FUSE 2, which is a separate package
  # from the FUSE 3 that current Ubuntu releases install by default.
  ldconfig -p | grep -F 'libfuse.so.2' >/dev/null \
    || die "libfuse.so.2 is missing (install: sudo apt install libfuse2t64)"
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
  log_value "wine" "$WINE_BIN"
  log_value "wineserver" "$WINE_SERVER"
  log_value "prefix" "$WINE_PREFIX"
}

show_tsm_env() {
  log_value "tsm appimage" "$TSM_APPIMAGE"
  log_value "wow dir" "$WOW_DIR"
}

# ----------------------------
# Commands
# ----------------------------
cmd_zygor_install() {
  assert_config_ok
  local installer="${1:-$DEFAULT_ZYGOR_SETUP}"
  require_file "$installer"

  show_env
  log_doing "running zygor installer: $installer"
  ( cd "$(dirname "$installer")" && wine_run "$installer" )
  log_done "zygor installer finished"
}

cmd_zygor_client() {
  assert_config_ok
  assert_win_exe_exists "$ZYGOR_CLIENT_WIN"

  show_env
  log_doing "launching zygor client"
  ( cd "$DEFAULT_WORKDIR" && wine_start "$ZYGOR_CLIENT_WIN" "${ZYGOR_CLIENT_ARGS[@]}" ) >/dev/null 2>&1 & disown || true
  log_done "zygor client launched"
}

cmd_tsm_install() {
  # Installing replaces a file, so it is a dry run unless --confirm is given.
  local source_file=""
  dryRun=1
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -y|--confirm) dryRun="" ;;
      -*) die "unknown tsm-install option: $1" ;;
      *)
        [[ -z "$source_file" ]] || die "tsm-install takes one AppImage path"
        source_file="$1"
        ;;
    esac
    shift
  done
  source_file="${source_file:-$DEFAULT_TSM_APPIMAGE}"

  require_file "$source_file"
  assert_appimage "$source_file"
  assert_fuse
  [[ ! "$source_file" -ef "$TSM_APPIMAGE" ]] || die "source is already the installed AppImage: $source_file"

  show_tsm_env
  log_doing "installing tsm desktop app"
  log_action "copying $source_file to $TSM_APPIMAGE"
  if [[ -e "$TSM_APPIMAGE" ]]; then
    log_action "keeping current version as $TSM_APPIMAGE.previous"
  fi

  if [[ -z "$dryRun" ]]; then
    mkdir -p "$TSM_DIR"
    # Copy beside the target first so a failed copy cannot damage the working install.
    local staged_file="$TSM_APPIMAGE.new"
    cp -- "$source_file" "$staged_file"
    chmod 755 "$staged_file"
    if [[ -e "$TSM_APPIMAGE" ]]; then
      mv -- "$TSM_APPIMAGE" "$TSM_APPIMAGE.previous"
    fi
    mv -- "$staged_file" "$TSM_APPIMAGE"
    log_done "tsm desktop app installed"
  else
    log_info "dry run: pass --confirm to install"
  fi
}

cmd_tsm_client() {
  require_exec "$TSM_APPIMAGE"
  assert_appimage "$TSM_APPIMAGE"
  assert_fuse
  require_dir "$WOW_DIR"

  show_tsm_env
  log_doing "launching tsm desktop app"
  mkdir -p "$(dirname "$TSM_LOG")"
  # setsid detaches the GUI from this terminal; AppRun chooses the sandbox flag itself.
  ( cd "$TSM_DIR" && setsid "$TSM_APPIMAGE" "$@" ) >>"$TSM_LOG" 2>&1 </dev/null & disown || true
  log_value "tsm log" "$TSM_LOG"
  log_done "tsm desktop launched"
}

cmd_wineboot() {
  assert_config_ok
  show_env
  log_doing "running wineboot -u (safe to repeat)"
  wine_env
  "$WINE_BOOT" -u
  log_done "wineboot complete"
}

cmd_kill_wine() {
  assert_config_ok
  show_env

  wine_env
  log_doing "stopping wineserver for THIS prefix"
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
    log_info "leftover wine processes for this prefix, SIGTERM: $pids"
    # shellcheck disable=SC2086
    kill -TERM $pids || true
    sleep 1

    local pids2
    pids2="$(ps -eo pid=,args= | awk -v p="$prefix_escaped" '
      $0 ~ p && ($0 ~ /\/wine($| )/ || $0 ~ /\/wineserver($| )/ || $0 ~ /\/wine-preloader($| )/) { print $1 }
    ' | tr '\n' ' ')"

    if [[ -n "${pids2// /}" ]]; then
      log_warn "still running, SIGKILL: $pids2"
      # shellcheck disable=SC2086
      kill -KILL $pids2 || true
    fi
  else
    log_info "no leftover wine processes found for this prefix"
  fi

  log_done "kill complete"
}

cmd_status() {
  assert_config_ok
  show_env
  echo
  log_info "processes referencing this prefix:"
  local prefix_escaped
  prefix_escaped="$(printf '%s' "$WINE_PREFIX" | sed 's/[.[\*^$(){}+?|\\/]/\\&/g')"
  ps -eo pid=,args= | awk -v p="$prefix_escaped" '$0 ~ p { print }' || true
}

usage() {
  cat <<EOF
Usage: $0 <command> [args...]

Commands:
  zygor-install [installer.exe]   Run Zygor installer in the WoW prefix
  zygor                           Launch installed Zygor client in the WoW prefix

  tsm-install [--confirm] [file.AppImage]
                                  Install the native TSM Desktop AppImage (dry run without --confirm)
  tsm                             Launch the installed native TSM Desktop app

  wineboot                     Run wineboot -u for this prefix (safe)
  kill                            Stop wineserver + clean leftover wine procs for this prefix
  status                          Show config + processes tied to this prefix
  env                             Show config only

Notes:
  - Wine commands ONLY use:
      WINE_BIN    = $WINE_BIN
      WINEPREFIX  = $WINE_PREFIX
  - They do NOT call system wine or system wineserver.
  - TSM runs natively from: $TSM_APPIMAGE
    In the app, set the WoW folder to: $WOW_DIR
EOF
}

# ----------------------------
# Main
# ----------------------------
cmd="${1:-help}"
shift || true

case "$cmd" in
  zygor-install) cmd_zygor_install "$@" ;;
  zygor)         cmd_zygor_client "$@" ;;
  tsm-install)   cmd_tsm_install "$@" ;;
  tsm)           cmd_tsm_client "$@" ;;
  wineboot)      cmd_wineboot "$@" ;;
  kill)          cmd_kill_wine "$@" ;;
  status)        cmd_status "$@" ;;
  env)           assert_config_ok; show_env; show_tsm_env ;;
  help|-h|--help|"") usage ;;
  *) die "unknown command: $cmd (try: help)" ;;
esac


#!/usr/bin/env bash
set -euo pipefail

### --- CONFIG -------------------------------------------------------------

# Your Battle.net / WoW prefix (already on ext4)
PREFIX="/mnt/games2/prefixes/battlenet"
INSTALLER="/mnt/games2/installers"

# Wine runner used by Lutris for Battle.net
WINE="$HOME/.local/share/lutris/runners/wine/lutris-GE-Proton8-26-x86_64/bin/wine"

# Zygor installer you already downloaded
ZYGOR_INSTALLER="$INSTALLER/Zygor_Setup_4.8.0.exe"

# TradeSkillMaster Desktop App installer (put the real filename here)
# e.g. TSMDesktopAppSetup.exe or similar
TSM_INSTALLER="$INSTALLER/TSM_Desktop_App_Setup.exe"

# WoW paths inside the prefix
WOW_ROOT="$PREFIX/drive_c/Program Files (x86)/World of Warcraft"
WOW_RETAIL_ADDONS="$WOW_ROOT/_retail_/Interface/AddOns"
WOW_CLASSIC_ADDONS="$WOW_ROOT/_classic_/Interface/AddOns"

# Optional: where to cache addon zips
ADDON_CACHE="$HOME/.cache/wow-addons"

### --- HELPERS ------------------------------------------------------------

ensure_dirs() {
    mkdir -p "$WOW_RETAIL_ADDONS" "$WOW_CLASSIC_ADDONS" "$ADDON_CACHE"

    # Handy symlinks so you can browse addons easily from Linux
    [ -L "$HOME/WoW_AddOns_Retail" ]  || ln -s "$WOW_RETAIL_ADDONS"  "$HOME/WoW_AddOns_Retail"
    [ -L "$HOME/WoW_AddOns_Classic" ] || ln -s "$WOW_CLASSIC_ADDONS" "$HOME/WoW_AddOns_Classic"
}

run_wine() {
    WINEPREFIX="$PREFIX" "$WINE" "$@"
}

### --- MAIN ACTIONS -------------------------------------------------------

cmd="${1:-help}"

case "$cmd" in
    # ---------------- ZYGOR ----------------
    zygor-install)
        ensure_dirs
        if [ ! -f "$ZYGOR_INSTALLER" ]; then
            echo "Zygor installer not found at:"
            echo "  $ZYGOR_INSTALLER"
            echo "Update ZYGOR_INSTALLER in this script or move the file."
            exit 1
        fi
        echo "Running Zygor installer with Battle.net prefix..."
        run_wine "$ZYGOR_INSTALLER"
        ;;

    zygor-client)
        ensure_dirs
        # Adjust this if Zygor installs somewhere else
        ZYGOR_CLIENT="$PREFIX/drive_c/Program Files (x86)/Zygor Guides Client/ZygorGuidesClient.exe"
        if [ ! -f "$ZYGOR_CLIENT" ]; then
            echo "Zygor client not found at:"
            echo "  $ZYGOR_CLIENT"
            echo "Run:  $0 zygor-install  first, then adjust this path if needed."
            exit 1
        fi
        echo "Starting Zygor client..."
        run_wine "$ZYGOR_CLIENT"
        ;;

    # ---------------- TRADESKILLMASTER ----------------
    tsm-install)
        ensure_dirs
        if [ ! -f "$TSM_INSTALLER" ]; then
            echo "TSM installer not found at:"
            echo "  $TSM_INSTALLER"
            echo "Update TSM_INSTALLER in this script or move the file."
            exit 1
        fi
        echo "Running TradeSkillMaster Desktop App installer..."
        run_wine "$TSM_INSTALLER"
        ;;

    tsm-client)
        ensure_dirs
        # Common guesses for TSM desktop app location.
        # After installing, if this fails, we’ll tell you how to find the exe.
        TSM_CANDIDATES=(
            "$PREFIX/drive_c/Program Files (x86)/TradeSkillMaster Application/TradeSkillMaster Application.exe"
            "$PREFIX/drive_c/Program Files/TradeSkillMaster Application/TradeSkillMaster Application.exe"
            "$PREFIX/drive_c/users/andy/AppData/Local/TradeSkillMaster Application/TradeSkillMaster Application.exe"
        )

        TSM_EXE=""
        for p in "${TSM_CANDIDATES[@]}"; do
            if [ -f "$p" ]; then
                TSM_EXE="$p"
                break
            fi
        done

        if [ -z "$TSM_EXE" ]; then
            echo "Could not find TSM Desktop App executable in common locations."
            echo
            echo "After installing TSM, run this to locate it:"
            echo "  find \"$PREFIX/drive_c\" -iname '*tradeskillmaster*app*.exe'"
            echo
            echo "Then update the TSM_CANDIDATES list in this script with the correct path."
            exit 1
        fi

        echo "Starting TSM Desktop App:"
        echo "  $TSM_EXE"
        run_wine "$TSM_EXE"
        ;;

    # ---------------- ZIP ADDONS ----------------
    install-addon-zip)
        # Usage: wow_addon_helper.sh install-addon-zip retail /path/to/addon.zip
        # variant: retail | classic | both
        variant="${2:-}"
        zip_path="${3:-}"

        if [ -z "$variant" ] || [ -z "$zip_path" ]; then
            echo "Usage: $0 install-addon-zip <retail|classic|both> /path/to/addon.zip"
            exit 1
        fi

        if [ ! -f "$zip_path" ]; then
            echo "Zip not found: $zip_path"
            exit 1
        fi

        ensure_dirs
        case "$variant" in
            retail)
                dest="$WOW_RETAIL_ADDONS"
                ;;
            classic)
                dest="$WOW_CLASSIC_ADDONS"
                ;;
            both)
                echo "Installing to Retail..."
                unzip -o "$zip_path" -d "$WOW_RETAIL_ADDONS"
                echo "Installing to Classic..."
                unzip -o "$zip_path" -d "$WOW_CLASSIC_ADDONS"
                echo "Done."
                exit 0
                ;;
            *)
                echo "Unknown variant: $variant (use retail|classic|both)"
                exit 1
                ;;
        esac

        echo "Installing addon zip to: $dest"
        unzip -o "$zip_path" -d "$dest"
        echo "Done."
        ;;

    help|*)
        cat <<EOF
WoW addon helper (Zygor + TradeSkillMaster + manual zips)

Configured for:
  Prefix : $PREFIX
  WoW    : $WOW_ROOT

Commands:
  $0 zygor-install
      Run the Zygor installer using the Battle.net prefix.

  $0 zygor-client
      Start the installed Zygor Guides client.

  $0 tsm-install
      Run the TradeSkillMaster Desktop App installer using the same prefix.

  $0 tsm-client
      Start the TSM Desktop App (so it can sync while WoW is running).
      If it can't find the EXE, it will tell you how to locate it.

  $0 install-addon-zip <retail|classic|both> /path/to/addon.zip
      Unzip a CurseForge-style addon (e.g. Plater, Details) into the WoW AddOns folder.

After first run, you’ll have handy symlinks:
  ~/WoW_AddOns_Retail
  ~/WoW_AddOns_Classic
EOF
        ;;
esac

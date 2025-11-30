#!/usr/bin/env bash
#
# install_linux_apps.sh
# Simple installer for Andy's preferred Linux applications on Pop!_OS / Ubuntu.
# This script is safe to run multiple times; missing packages will be skipped.

set -u

if [[ "$EUID" -ne 0 ]]; then
  echo "Please run as root, e.g.: sudo $0"
  exit 1
fi

echo "Updating package lists..."
apt update

# Core packages
APT_PACKAGES=(
  gscan2pdf
  krename
  gprename
  puddletag
  handbrake
  steam-installer
  lutris
  digikam
  darktable
  vlc
  syncthing
  timeshift
  deja-dup
)

echo "Installing packages where available..."
for pkg in "${APT_PACKAGES[@]}"; do
  if apt-cache show "$pkg" > /dev/null 2>&1; then
    echo "------------------------------------------------------------"
    echo "Installing: $pkg"
    apt install -y "$pkg"
  else
    echo "------------------------------------------------------------"
    echo "Package not found in APT, skipping: $pkg"
  fi
done

cat <<'EOF'

Optional / notes:
- Paperwork (document manager) may be available as:
    sudo apt install paperwork
  or via flatpak/snap depending on your distro.
- Discord is often installed via flatpak/snap or from the .deb on discord.com.

You can safely re-run this script after enabling extra repositories if needed.
EOF

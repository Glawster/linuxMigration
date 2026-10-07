#!/usr/bin/env bash

_installerTinyMediaManagerApply() {
    local target="$HOME/.local/opt/tinyMediaManager"
    if [[ -x "$target/tinyMediaManager" ]]; then
        itemSkip "installer already complete: tinyMediaManager"
    else
        changeRun "install tinyMediaManager" _installerTinyMediaManagerInstall "$target"
    fi
}

_installerTinyMediaManagerInstall() {
    local target="$1" version="5.3.1" architecture archiveUrl checksumUrl temporary archive expected actual
    architecture="$(dpkg --print-architecture)"
    [[ "$architecture" == amd64 ]] || { logError "tinyMediaManager bootstrap installer currently supports amd64 only"; return 2; }
    archiveUrl="https://release.tinymediamanager.org/v5/dist/tinyMediaManager-${version}-linux-amd64.tar.xz"
    checksumUrl="$archiveUrl.sha256"
    temporary="$(mktemp -d)"
    archive="$temporary/tinyMediaManager.tar.xz"
    curl -fsSL "$archiveUrl" -o "$archive"
    expected="$(curl -fsSL "$checksumUrl" | awk '{print $1; exit}')"
    actual="$(sha256sum "$archive" | awk '{print $1}')"
    [[ -n "$expected" && "$actual" == "$expected" ]] || { rm -rf "$temporary"; logError "tinyMediaManager installer checksum mismatch"; return 1; }
    mkdir -p "$target" "$HOME/.local/bin"
    tar -xJf "$archive" -C "$target" --strip-components=1
    ln -sfn "$target/tinyMediaManager" "$HOME/.local/bin/tinyMediaManager"
    rm -rf "$temporary"
}

_installerJellyfinApply() {
    if dpkg-query -W -f='${db:Status-Abbrev}' jellyfin-server 2>/dev/null | grep -q '^ii'; then
        itemSkip "installer already complete: Jellyfin"
    else
        changeRun "install Jellyfin" _installerJellyfinInstall
    fi
}

_installerJellyfinInstall() {
    local temporary script checksum
    temporary="$(mktemp -d)"
    script="$temporary/install-debuntu.sh"
    checksum="$temporary/install-debuntu.sh.sha256sum"
    curl -fsSL https://repo.jellyfin.org/install-debuntu.sh -o "$script"
    curl -fsSL https://repo.jellyfin.org/install-debuntu.sh.sha256sum -o "$checksum"
    (cd "$temporary" && sha256sum -c "$(basename "$checksum")")
    sudo bash "$script"
    rm -rf "$temporary"
}

_installerSonarrApply() {
    if [[ -x /opt/Sonarr/Sonarr ]]; then
        itemSkip "installer already complete: Sonarr"
    else
        changeRun "install Sonarr" _installerSonarrInstall
    fi
}

_installerSonarrInstall() {
    local temporary script
    temporary="$(mktemp -d)"
    script="$temporary/install-sonarr.sh"
    curl -fsSL https://raw.githubusercontent.com/Sonarr/Sonarr/develop/distribution/debian/install.sh -o "$script"
    logInfo "Sonarr installer: use user 'andy' and group 'andy' when prompted so it can access /mnt/video2"
    sudo bash "$script"
    rm -rf "$temporary"
}

_installerRadarrApply() {
    if [[ -x /opt/Radarr/Radarr ]]; then
        itemSkip "installer already complete: Radarr"
    else
        changeRun "install Radarr" _installerRadarrInstall
    fi
}

_installerRadarrInstall() {
    local architecture downloadUrl temporary archive appUser appGroup serviceFile
    architecture="$(dpkg --print-architecture)"
    case "$architecture" in
        amd64) downloadUrl='https://radarr.servarr.com/v1/update/master/updatefile?os=linux&runtime=netcore&arch=x64' ;;
        arm64) downloadUrl='https://radarr.servarr.com/v1/update/master/updatefile?os=linux&runtime=netcore&arch=arm64' ;;
        armhf) downloadUrl='https://radarr.servarr.com/v1/update/master/updatefile?os=linux&runtime=netcore&arch=arm' ;;
        *) logError "unsupported Radarr architecture: $architecture"; return 2 ;;
    esac
    appUser="${SUDO_USER:-$USER}"
    appGroup="$(id -gn "$appUser")"
    temporary="$(mktemp -d)"
    archive="$temporary/radarr.tar.gz"
    curl -fL "$downloadUrl" -o "$archive"
    tar -xzf "$archive" -C "$temporary"
    sudo rm -rf /opt/Radarr
    sudo mv "$temporary/Radarr" /opt/Radarr
    sudo mkdir -p /var/lib/radarr
    sudo chown -R "$appUser:$appGroup" /opt/Radarr /var/lib/radarr
    serviceFile="$temporary/radarr.service"
    cat > "$serviceFile" <<EOF
[Unit]
Description=Radarr Daemon
After=network.target

[Service]
User=$appUser
Group=$appGroup
UMask=0002
Type=simple
ExecStart=/opt/Radarr/Radarr -nobrowser -data=/var/lib/radarr
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
    sudo install -m 644 "$serviceFile" /etc/systemd/system/radarr.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now radarr.service
    rm -rf "$temporary"
}

_installerPrivateInternetAccessApply() {
    if [[ -x /opt/piavpn/bin/pia-client || -x /opt/piavpn/bin/piactl ]]; then
        itemSkip "installer already complete: Private Internet Access"
    else
        changeRun "install Private Internet Access" _installerPrivateInternetAccessInstall
    fi
}

_installerPrivateInternetAccessInstall() {
    local architecture version build filename checksum url temporary installer actual
    architecture="$(dpkg --print-architecture)"
    version="3.7.2"
    build="08420"
    case "$architecture" in
        amd64)
            filename="pia-linux-${version}-${build}.run"
            checksum="08a88af04462a9e078aeef52b26bcdb56f0a9b087a0fb7606f98b7eb79bb3dd9"
            ;;
        arm64)
            filename="pia-linux-arm64-${version}-${build}.run"
            checksum="3956d1ed9b6977f24ca960e78dd60572edd435f71b2a554e5c5d00f94603eeb9"
            ;;
        *) logError "unsupported Private Internet Access architecture: $architecture"; return 2 ;;
    esac
    url="https://installers.privateinternetaccess.com/download/$filename"
    temporary="$(mktemp -d)"
    installer="$temporary/$filename"
    curl -fsSL "$url" -o "$installer"
    actual="$(sha256sum "$installer" | awk '{print $1}')"
    [[ "$actual" == "$checksum" ]] || { rm -rf "$temporary"; logError "Private Internet Access installer checksum mismatch"; return 1; }
    sh "$installer"
    rm -rf "$temporary"
}

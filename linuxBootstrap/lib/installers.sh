#!/usr/bin/env bash

installersApply() {
    local installer
    for installer in "$@"; do
        case "$installer" in
            libreoffice-26.2.4.2) _installerLibreOfficeApply ;;
            miniconda) _installerMinicondaApply ;;
            zen-browser) _installerZenBrowserApply ;;
            *) logError "unsupported installer: $installer"; return 2 ;;
        esac
    done
}

_installerLibreOfficeApply() {
    local executable="${libreOfficeExecutable:-/opt/libreoffice26.2/program/soffice}"
    local expectedVersion="26.2.4.2" currentVersion=""
    if [[ -x "$executable" ]]; then
        currentVersion="$($executable --version 2>/dev/null || true)"
    fi
    if [[ "$currentVersion" == *"$expectedVersion"* ]]; then
        itemSkip "installer already complete: LibreOffice $expectedVersion"
    else
        changeRun "replace LibreOffice with version $expectedVersion" _installerLibreOfficeInstall
    fi
}

_installerLibreOfficeInstall() {
    local archiveName archiveUrl expected actual temporary archive extracted debsDir status=0
    [[ "$(uname -m)" == x86_64 ]] || {
        logError "LibreOffice 26.2.4.2 installer supports x86_64 only"
        return 2
    }
    archiveName="LibreOffice_26.2.4_Linux_x86-64_deb.tar.gz"
    archiveUrl="https://download.documentfoundation.org/libreoffice/stable/26.2.4/deb/x86_64/$archiveName"
    expected="810ef197e190d7804a60e0016052c46ff33792303a200fddda9d5216a64b9900"
    temporary="$(mktemp -d)"
    archive="$temporary/$archiveName"

    curl -fsSL "$archiveUrl" -o "$archive"
    actual="$(sha256sum "$archive" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        logError "LibreOffice installer checksum mismatch"
        status=1
    else
        tar -xzf "$archive" -C "$temporary"
        extracted="$temporary/LibreOffice_26.2.4.2_Linux_x86-64_deb"
        debsDir="$extracted/DEBS"
        [[ -d "$debsDir" ]] || {
            logError "LibreOffice installer does not contain the expected DEBS directory"
            status=1
        }
        if ((status == 0)); then
            _installerLibreOfficePackagesRemove
            sudo dpkg -i "$debsDir"/*.deb || sudo apt-get install -f -y
        fi
    fi
    rm -rf "$temporary"
    return "$status"
}

_installerLibreOfficePackagesRemove() {
    local -a packages=()
    mapfile -t packages < <(
        dpkg-query -W -f='${binary:Package}\t${db:Status-Abbrev}\n' 'libreoffice*' 2>/dev/null |
            awk '$2 ~ /^ii/ {print $1}'
    )
    ((${#packages[@]})) || return 0
    sudo apt-get remove -y "${packages[@]}"
}

_installerMinicondaApply() {
    local target="${minicondaDir:-$HOME/miniconda3}"
    if [[ -x "$target/bin/conda" ]]; then
        itemSkip "installer already complete: miniconda"
    else
        changeRun "install miniconda: $target" _installerMinicondaInstall "$target"
    fi
}

_installerMinicondaInstall() {
    local target="$1" installerName baseUrl installer expected actual temporary status=0
    case "$(uname -m)" in
        x86_64)
            installerName="Miniconda3-py314_26.5.3-2-Linux-x86_64.sh"
            expected="80bc27f13c4de90f10e387aa45e864de4f0860692c1221aef5900009a2b55302"
            ;;
        aarch64|arm64)
            installerName="Miniconda3-py314_26.5.3-2-Linux-aarch64.sh"
            expected="999e8761f4dc74fb8d0dc9f74d5374f6708ff81eebbb0af677a4d5307d38b2e5"
            ;;
        *) logError "unsupported Miniconda architecture: $(uname -m)"; return 2 ;;
    esac
    baseUrl="https://repo.anaconda.com/miniconda"
    temporary="$(mktemp -d)"
    installer="$temporary/$installerName"
    curl -fsSL "$baseUrl/$installerName" -o "$installer"
    actual="$(sha256sum "$installer" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        logError "Miniconda installer checksum mismatch"
        status=1
    else
        bash "$installer" -b -p "$target" || status=$?
    fi
    rm -f "$installer"
    rmdir "$temporary"
    return "$status"
}


_installerZenBrowserApply() {
    local executable="${zenBrowserExecutable:-$HOME/.tarball-installations/zen/zen}"
    if [[ -x "$executable" ]]; then
        itemSkip "installer already complete: Zen Browser"
    else
        commandRequire curl
        changeRun "install Zen Browser" _installerZenBrowserInstall
    fi
}

_installerZenBrowserInstall() {
    local installer temporary status=0
    temporary="$(mktemp -d)"
    installer="$temporary/install.sh"

    curl -fsSL \
        https://github.com/zen-browser/updates-server/raw/refs/heads/main/install.sh \
        -o "$installer" || status=$?
    if ((status == 0)); then
        bash "$installer" || status=$?
    fi

    rm -rf "$temporary"
    return "$status"
}

#!/usr/bin/env bash

networkingExpectedValidate() {
    local expected="${1:-}" address
    [[ -n "$expected" ]] || return 0
    networkingIpv4Validate "$expected" "expected IP"
    for address in $(hostname -I 2>/dev/null || true); do
        if [[ "$address" == "$expected" ]]; then
            itemSkip "DHCP supplied expected IP: $expected"
            return 0
        fi
    done
    logWarning "expected DHCP-reserved IP is not assigned: $expected"
}

networkingIpv4Validate() {
    local address="$1" description="$2" octet
    local -a octets=()
    [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || {
        logError "$description must be an IPv4 address: $address"
        return 2
    }
    IFS=. read -r -a octets <<< "$address"
    for octet in "${octets[@]}"; do
        ((10#$octet <= 255)) || { logError "$description contains an invalid octet: $address"; return 2; }
    done
}

networkingApply() {
    local address="${1:-}" connection="${2:-}" gateway="${3:-}" dns="${4:-}" ip
    [[ -n "$address" ]] || return 0
    [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]] || {
        logError "static IP must be IPv4 CIDR notation: $address"
        return 2
    }
    ip="${address%/*}"
    networkingIpv4Validate "$ip" "static IP"
    [[ -n "$connection" ]] || {
        logWarning "static IP requested ($address), but network.connection is not configured"
        return 0
    }
    [[ -n "$gateway" ]] || { logError "network.gateway is required with a static address"; return 2; }
    networkingIpv4Validate "$gateway" "network gateway"
    networkingDnsValidate "$dns"
    if ! command -v nmcli >/dev/null 2>&1 || ! nmcli connection show "$connection" >/dev/null 2>&1; then
        if [[ "${dryRun:-1}" == 1 ]]; then
            logWarning "NetworkManager connection cannot be inspected in preview: $connection"
            changeRun "configure static network connection: $connection" true
            return 0
        fi
        logError "NetworkManager connection not found: $connection"
        return 2
    fi
    if networkingConnectionMatches "$connection" "$address" "$gateway" "$dns"; then
        itemSkip "network connection already configured: $connection"
    else
        changeRun "configure static network connection: $connection" \
            networkingConnectionConfigure "$connection" "$address" "$gateway" "$dns"
    fi
}

hostsApply() {
    (($#)) || return 0
    local entry ip name target="${hostsFile:-/etc/hosts}" temporary
    local -a fields=()
    for entry in "$@"; do
        read -r -a fields <<< "$entry"
        ((${#fields[@]} >= 2)) || { logError "hosts entry requires an IP and hostname: $entry"; return 2; }
        ip="${fields[0]}"
        networkingIpv4Validate "$ip" "hosts entry IP"
        for name in "${fields[@]:1}"; do
            [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || { logError "invalid hosts entry name: $entry"; return 2; }
        done
    done
    temporary="$(mktemp)"
    hostsFileRender "$target" "$temporary" "$@"
    if cmp -s "$target" "$temporary"; then
        itemSkip "managed host mappings already configured"
    else
        changeRun "update managed host mappings" sudo install -m 644 "$temporary" "$target"
    fi
    rm -f "$temporary"
}

hostsFileRender() {
    local source="$1" output="$2"
    shift 2
    awk '
        $0 == "# BEGIN linux-bootstrap hosts" { managed=1; next }
        $0 == "# END linux-bootstrap hosts" { managed=0; next }
        !managed { print }
    ' "$source" > "$output"
    printf '# BEGIN linux-bootstrap hosts\n' >> "$output"
    printf '%s\n' "$@" >> "$output"
    printf '# END linux-bootstrap hosts\n' >> "$output"
}

networkingConnectionConfigure() {
    local connection="$1" address="$2" gateway="$3" dns="$4"
    local -a command=(sudo nmcli connection modify "$connection" ipv4.method manual ipv4.addresses "$address" ipv4.gateway "$gateway")
    [[ -z "$dns" ]] || command+=(ipv4.dns "$dns")
    "${command[@]}"
    sudo nmcli connection up "$connection"
}

networkingConnectionMatches() {
    local connection="$1" address="$2" gateway="$3" dns="$4"
    local currentMethod currentAddress currentGateway currentDns
    currentMethod="$(nmcli -g ipv4.method connection show "$connection")"
    currentAddress="$(nmcli -g ipv4.addresses connection show "$connection")"
    currentGateway="$(nmcli -g ipv4.gateway connection show "$connection")"
    currentDns="$(nmcli -g ipv4.dns connection show "$connection")"
    [[ "$currentMethod" == manual && "$currentAddress" == "$address" && "$currentGateway" == "$gateway" ]] || return 1
    [[ -z "$dns" || "${currentDns// /}" == "${dns// /}" ]]
}

networkingDnsValidate() {
    local dns="$1" server
    [[ -n "$dns" ]] || return 0
    dns="${dns//,/ }"
    for server in $dns; do networkingIpv4Validate "$server" "network DNS server"; done
}

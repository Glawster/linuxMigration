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
    local address="${1:-}" ip
    [[ -n "$address" ]] || return 0
    [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]] || {
        logError "static IP must be IPv4 CIDR notation: $address"
        return 2
    }
    ip="${address%/*}"
    networkingIpv4Validate "$ip" "static IP"
    logWarning "static IP requested ($address), but connection selection is not yet implemented"
}

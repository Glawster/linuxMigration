# Network naming and static addresses

## Recommended name services

Traditional Network Information Service (NIS/YP) should not be introduced for
this network. It is a legacy account and host-information system with weak
security assumptions. The bootstrap uses smaller, conventional mechanisms:

1. Router DHCP reservations should assign stable addresses centrally when the
   router supports them.
2. Avahi and `libnss-mdns` provide zero-configuration names such as
   `tv-pc.local` on the local network.
3. Managed `/etc/hosts` entries provide deterministic short names such as
   `andy-pc` when centralized DNS is unavailable.
4. A local DNS service such as `dnsmasq`, AdGuard Home, or Pi-hole is preferable
   to copying host mappings once the network grows beyond a few machines.

The `common` profile installs Avahi and its NSS integration and enables the
`avahi-daemon` service. A firewall must permit mDNS UDP port 5353 on the local
network for `.local` discovery to work.

## Static NetworkManager configuration

Static configuration is explicit and belongs in each host profile:

```yaml
network:
  connection: Wired connection 1
  address: 192.0.2.20/24
  gateway: 192.0.2.1
  dns: 192.0.2.1, 1.1.1.1
```

The `192.0.2.0/24` range is reserved for documentation. Replace every example
with the real address plan before running with `--confirm`.

Find the active NetworkManager connection name with:

```bash
nmcli -t -f NAME,TYPE,DEVICE connection show --active
```

The bootstrap validates the address, gateway, DNS servers, and connection name.
It changes the connection only when its current settings differ, then activates
it. Activation can interrupt an SSH session, so apply initial network changes
from the machine's local console. Prefer a router DHCP reservation when possible
because it avoids configuring the same network facts in two places.

Inspect a profile without changing the connection:

```bash
./bootstrap.sh --profile tv-pc --status
```

## Managed host mappings

Add peer addresses to a profile with a top-level list:

```yaml
hosts:
  - 192.0.2.10 andy-pc
  - 192.0.2.20 tv-pc
  - 192.0.2.30 laptop
```

Each entry contains an IPv4 address followed by a hostname and optional aliases.
The bootstrap owns only the block between these markers in `/etc/hosts`:

```text
# BEGIN linux-bootstrap hosts
# END linux-bootstrap hosts
```

Content outside that block is preserved. Put mappings shared by every machine
in `profiles/common.yaml`, or keep a machine-specific view in its host profile.
Do not add `.local` aliases to `/etc/hosts`; Avahi owns that namespace.

Verify resolution with:

```bash
getent hosts andy-pc
getent hosts andy-pc.local
ssh andy-pc
```

## Address-planning checklist

Before adding real values, record:

- the router address and DHCP allocation range;
- a reserved address for each machine, outside the dynamic pool when required;
- each machine's exact NetworkManager connection name;
- whether local DNS is supplied by the router or another server;
- which machine names must resolve through `/etc/hosts` and which can rely on
  Avahi `.local` discovery.

Never copy the documentation addresses into a live profile. Duplicate addresses
can disconnect both affected machines.

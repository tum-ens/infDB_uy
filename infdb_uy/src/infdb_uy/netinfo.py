"""Network address of the host, so the dashboard can show where it is reachable on the LAN.

Inside a container the app only sees Docker's internal network. `compose.yml` therefore runs
`python -m infdb_uy.netinfo` once in the host's network namespace (network_mode: host) before
the dashboard starts; it writes data/state/host_network.json, which the dashboard reads.
Outside Docker the dashboard calls `lan_ips()` directly.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
from pathlib import Path


def lan_ips() -> list[str]:
    """IPv4 address of the interface that holds the default route (no packet is sent)."""
    ips = []
    for probe in ("192.0.2.1", "10.255.255.255"):  # TEST-NET / private: routing lookup only
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 9))
                ip = s.getsockname()[0]
        except OSError:
            continue
        addr = ipaddress.ip_address(ip)
        # Skip loopback and Docker's own networks (bridge 172.17+/16, Docker Desktop VM 192.168.65.0/24)
        if addr.is_loopback or addr in ipaddress.ip_network("172.16.0.0/12") or addr in ipaddress.ip_network("192.168.65.0/24"):
            continue
        if ip not in ips:
            ips.append(ip)
    return ips


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/state/host_network.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"hostname": socket.gethostname(), "ips": lan_ips()}))
        print(f"host network: {out.read_text()}")
    except OSError as e:  # never block the dashboard from starting
        print(f"host network not determined: {e}")


if __name__ == "__main__":
    main()

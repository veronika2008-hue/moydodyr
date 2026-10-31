"""
Finds a Tapo plug's current local IP from its (stable) MAC address, so the
scripts don't need config.py's IP updated by hand every time the plug
reconnects to Wi-Fi and gets a new DHCP lease.

Works by ARP: reads the OS's ARP cache for the MAC, and if it's not there
yet, pings every address on the subnet to populate the cache first.

Falls back to the static IP in config.TAPO_DEVICES if the MAC isn't known
(not in config.TAPO_MACS) or isn't found on the network right now.
"""

import re
import subprocess
import concurrent.futures

from config import TAPO_DEVICES, TAPO_MACS

SUBNET_PREFIX = "192.168.137."


def _normalize_mac(mac: str) -> str:
    return mac.replace("-", ":").lower()


def _ping(ip: str):
    subprocess.run(
        ["ping", "-n", "1", "-w", "300", ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _arp_table() -> dict:
    """Returns {normalized_mac: ip} from the OS's current ARP cache."""
    output = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout
    table = {}
    for line in output.splitlines():
        match = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+\w+", line)
        if match:
            ip, mac = match.groups()
            table[_normalize_mac(mac)] = ip
    return table


def _find_ip_by_mac(mac: str) -> str | None:
    mac = _normalize_mac(mac)

    table = _arp_table()
    if mac in table:
        return table[mac]

    # Not cached yet — sweep the subnet to populate the ARP cache, then recheck.
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        pool.map(_ping, [f"{SUBNET_PREFIX}{i}" for i in range(1, 255)])

    return _arp_table().get(mac)


def resolve_ip(machine_id: str) -> str:
    """Current IP for `machine_id`: looked up live by MAC if known, else the
    static fallback from config.TAPO_DEVICES."""
    mac = TAPO_MACS.get(machine_id)
    if mac:
        found = _find_ip_by_mac(mac)
        if found:
            return found
    return TAPO_DEVICES[machine_id]

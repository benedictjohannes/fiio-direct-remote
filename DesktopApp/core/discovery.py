"""
FiiO K17 Network Discovery Module.
Supports UDP Multicast, mDNS resolution, and cross-platform ARP fallback.
Pure Python / OS standard utilities - Zero UI dependencies.
"""
import platform
import re
import socket
import struct
import subprocess
import time
from typing import Optional

from .constants import (
    K17_DISCOVERY_PORT,
    K17_MULTICAST_GROUP,
    K17_MDNS_HOST,
    K17_MAC_PREFIX,
)


def discover_k17_udp(timeout: float = 2.5) -> Optional[str]:
    """
    Listens for UDP multicast heartbeats on 224.0.0.255:12101 (payload 'K17').
    Returns sender IP if detected, otherwise None.
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass

        sock.bind(("", K17_DISCOVERY_PORT))

        mreq = struct.pack("4sl", socket.inet_aton(K17_MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(timeout)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                if data == b"K17" or b"K17" in data:
                    print(f"[Discovery] Detected K17 heartbeat from {addr[0]}:{addr[1]}", flush=True)
                    return addr[0]
            except socket.timeout:
                break
    except Exception as e:
        print(f"[Discovery] UDP discovery exception: {e}", flush=True)
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    return None


def resolve_k17_mdns() -> Optional[str]:
    """
    Attempts mDNS resolution via avahi-resolve (Linux) or standard socket gethostbyname.
    """
    # 1. Try avahi-resolve on Linux if available
    if platform.system() == "Linux":
        try:
            res = subprocess.run(
                ["avahi-resolve", "-n", K17_MDNS_HOST],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split()
                if len(parts) >= 2:
                    print(f"[Discovery] Resolved via avahi-resolve: {parts[1]}", flush=True)
                    return parts[1]
        except Exception:
            pass

    # 2. Standard socket gethostbyname resolution
    try:
        ip = socket.gethostbyname(K17_MDNS_HOST)
        if ip:
            print(f"[Discovery] Resolved via gethostbyname: {ip}", flush=True)
            return ip
    except Exception:
        pass

    return None


def resolve_k17_arp() -> Optional[str]:
    """
    Inspects local OS ARP table for MAC address prefix matching Ingenic/FiiO (40:d9:5a).
    Supports Linux, macOS, and Windows.
    """
    system = platform.system()
    mac_prefix = K17_MAC_PREFIX.lower()

    # 1. Linux 'ip neighbor'
    if system == "Linux":
        try:
            res = subprocess.run(["ip", "neighbor"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if mac_prefix in line.lower():
                        parts = line.split()
                        if parts:
                            print(f"[Discovery] Resolved via ip neighbor: {parts[0]}", flush=True)
                            return parts[0]
        except Exception:
            pass

    # 2. Windows / macOS / Linux fallback: 'arp -a' or 'arp -an'
    try:
        cmd = ["arp", "-a"] if system in ("Windows", "Darwin") else ["arp", "-an"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if mac_prefix in line.lower():
                    # Extract first IP-like token from line
                    ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
                    if ip_match:
                        found_ip = ip_match.group(1)
                        print(f"[Discovery] Resolved via ARP table: {found_ip}", flush=True)
                        return found_ip
    except Exception:
        pass

    return None


def resolve_k17_ip() -> Optional[str]:
    """
    Discovers FiiO K17 IP address using prioritized strategies:
    1. UDP Multicast Discovery (224.0.0.255:12101)
    2. mDNS hostname lookup (ingenic.local)
    3. ARP cache inspection (MAC prefix 40:d9:5a)
    """
    ip = discover_k17_udp(timeout=2.5)
    if ip:
        return ip

    ip = resolve_k17_mdns()
    if ip:
        return ip

    return resolve_k17_arp()

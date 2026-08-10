import socket
import json
import re
import subprocess
from typing import Optional, Tuple, Dict, Any

K17_MAC_PREFIX = "40:d9:5a"
K17_MDNS_HOST = "ingenic.local"
K17_PORT = 12100


def resolve_k17_ip() -> Optional[str]:
    """
    Resolves FiiO K17 IP via mDNS (avahi-resolve / gethostbyname)
    with ARP table fallback based on MAC prefix 40:d9:5a.
    """
    # 1. Try mDNS via avahi-resolve if available
    try:
        res = subprocess.run(
            ["avahi-resolve", "-n", K17_MDNS_HOST],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split()
            if len(parts) >= 2:
                return parts[1]
    except Exception:
        pass

    # 2. Try socket standard resolution
    try:
        ip = socket.gethostbyname(K17_MDNS_HOST)
        if ip:
            return ip
    except Exception:
        pass

    # 3. ARP table fallback using 'ip n' / 'ip neighbor'
    try:
        res = subprocess.run(
            ["ip", "neighbor"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if K17_MAC_PREFIX.lower() in line.lower():
                    parts = line.split()
                    if parts:
                        return parts[0]
    except Exception:
        pass

    return None


class K17Backend:
    def __init__(self):
        self.cached_ip: Optional[str] = None
        self.is_online: bool = False

    def get_or_resolve_ip(self) -> Optional[str]:
        if not self.cached_ip:
            self.cached_ip = resolve_k17_ip()
        return self.cached_ip

    def invalidate_cache(self):
        self.cached_ip = None
        self.is_online = False

    def _send_command(self, payload: str, expect_reply: bool = False) -> Tuple[bool, str]:
        ip = self.get_or_resolve_ip()
        if not ip:
            self.is_online = False
            return False, "K17 DAC not found on local network"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((ip, K17_PORT))
                s.sendall(payload.encode("ascii"))
                
                if expect_reply:
                    response_bytes = b""
                    while True:
                        try:
                            chunk = s.recv(1024)
                            if not chunk:
                                break
                            response_bytes += chunk
                            if b"}" in response_bytes:
                                break
                        except socket.timeout:
                            break
                    raw_str = response_bytes.decode("utf-8", errors="ignore")
                    self.is_online = True
                    return True, raw_str
                
                self.is_online = True
                return True, "OK"
        except Exception as e:
            self.invalidate_cache()
            return False, str(e)

    def fetch_status(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Sends 05010008 command to fetch device status JSON frame.
        """
        success, raw_resp = self._send_command("05010008", expect_reply=True)
        if not success:
            return False, None

        # Parse JSON frame using regex extraction matching k17_ctrl.sh
        match = re.search(r"(\{.*\})", raw_resp)
        if match:
            try:
                data = json.loads(match.group(1))
                return True, data
            except json.JSONDecodeError:
                pass

        # If connected but output non-parseable, consider status fetch failure
        return False, None

    def set_volume(self, val: int) -> bool:
        """
        Sends 0502000c + 4-char hex volume (0 to 100).
        """
        val = max(0, min(100, val))
        hex_val = f"{val:04X}"
        payload = f"0502000c{hex_val}"
        success, _ = self._send_command(payload, expect_reply=False)
        return success

    def set_input_mode(self, mode_code: str) -> bool:
        """
        Sends 0657000c + 4-char mode ID.
        """
        payload = f"0657000c{mode_code}"
        success, _ = self._send_command(payload, expect_reply=False)
        return success

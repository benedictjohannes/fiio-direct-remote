import socket
import json
import re
import time
import subprocess
import threading
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
        self.current_volume: Optional[int] = None
        self.last_request_time: float = 0.0
        self._sock: Optional[socket.socket] = None
        self._sock_connected_ip: Optional[str] = None
        self._sock_last_used: float = 0.0
        self._lock = threading.RLock()

    def get_or_resolve_ip(self) -> Optional[str]:
        if not self.cached_ip:
            self.cached_ip = resolve_k17_ip()
        return self.cached_ip

    def _close_socket(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._sock_connected_ip = None

    def invalidate_cache(self):
        with self._lock:
            self._close_socket()
            self.cached_ip = None
            self.is_online = False

    def _ensure_socket(self, ip: str) -> socket.socket:
        now = time.time()
        # Close socket if target IP changed or idle > 30s
        if self._sock:
            if self._sock_connected_ip != ip or (now - self._sock_last_used > 30.0):
                self._close_socket()

        if self._sock is None:
            print(f"[K17Backend] Connecting to {ip}:{K17_PORT}...", flush=True)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((ip, K17_PORT))
            self._sock = s
            self._sock_connected_ip = ip
            print(f"[K17Backend] Socket connected to {ip}:{K17_PORT}", flush=True)

        self._sock_last_used = now
        return self._sock

    def _send_command(self, payload: str) -> Tuple[bool, str]:
        with self._lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < 0.2:
                time.sleep(0.2 - elapsed)

            ip = self.get_or_resolve_ip()
            print(f"[K17Backend] Sending command '{payload}' to IP: {ip}", flush=True)
            if not ip:
                self.is_online = False
                print("[K17Backend] Error: K17 DAC IP could not be resolved", flush=True)
                return False, "K17 DAC not found on local network"

            for attempt in range(2):
                try:
                    s = self._ensure_socket(ip)
                    print(f"[K17Backend] Transmitting payload: {payload}", flush=True)
                    s.sendall(payload.encode("ascii"))
                    
                    response_bytes = b""
                    is_json_query = payload.startswith("0501")
                    timed_out = False
                    while True:
                        try:
                            chunk = s.recv(1024)
                            if not chunk:
                                print("[K17Backend] Received EOF from server", flush=True)
                                self._close_socket()
                                break
                            response_bytes += chunk
                            if is_json_query and b"}" in response_bytes:
                                break
                            if not is_json_query and len(response_bytes) >= 12:
                                break
                        except socket.timeout:
                            print("[K17Backend] recv timed out waiting for reply", flush=True)
                            timed_out = True
                            break

                    if timed_out or not response_bytes:
                        self._close_socket()
                        if attempt == 0:
                            time.sleep(0.2)
                            continue
                        self.invalidate_cache()
                        return False, "Timeout waiting for expected reply"

                    raw_str = response_bytes.decode("utf-8", errors="ignore")
                    print(f"[K17Backend] Received raw reply ({len(response_bytes)} bytes): {raw_str!r}", flush=True)
                    self.is_online = True
                    self._sock_last_used = time.time()
                    return True, raw_str
                except Exception as e:
                    print(f"[K17Backend] Socket exception on attempt {attempt + 1} during '{payload}': {type(e).__name__}: {e}", flush=True)
                    self._close_socket()
                    if attempt == 0:
                        time.sleep(0.2)
                        continue
                    self.invalidate_cache()
                    return False, str(e)
                finally:
                    self.last_request_time = time.time()

            return False, "Failed after retry"

    def fetch_status(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Sends 05010008 command to fetch device status JSON frame.
        """
        had_cached_ip = self.cached_ip is not None
        success, raw_resp = self._send_command("05010008")

        # If failed and we previously had a cached IP, wait 300ms, invalidate, and attempt fresh resolution once
        if not success and had_cached_ip:
            time.sleep(0.3)
            self.invalidate_cache()
            success, raw_resp = self._send_command("05010008")

        if not success:
            return False, None

        # Parse JSON frame using regex extraction matching k17_ctrl.sh
        match = re.search(r"(\{.*\})", raw_resp)
        if match:
            try:
                data = json.loads(match.group(1))
                if "currentVolume" in data:
                    try:
                        self.current_volume = int(data["currentVolume"])
                    except (ValueError, TypeError):
                        pass
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
        success, _ = self._send_command(payload)
        return success

    def set_input_mode(self, mode_code: str) -> bool:
        """
        Sends 0657000c + 4-char mode ID.
        """
        payload = f"0657000c{mode_code}"
        success, _ = self._send_command(payload)
        return success

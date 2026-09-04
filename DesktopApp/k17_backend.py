import socket
import struct
import json
import re
import time
import subprocess
import threading
from typing import Optional, Tuple, Dict, Any

K17_MULTICAST_GROUP = "224.0.0.255"
K17_DISCOVERY_PORT = 12101
K17_MAC_PREFIX = "40:d9:5a"
K17_MDNS_HOST = "ingenic.local"
K17_PORT = 12100


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


def resolve_k17_ip() -> Optional[str]:
    """
    Resolves FiiO K17 IP via:
    1. UDP Multicast Discovery (224.0.0.255:12101, 'K17')
    2. mDNS (avahi-resolve / gethostbyname)
    3. ARP table fallback (MAC prefix 40:d9:5a)
    """
    # 1. Try UDP multicast discovery (heartbeat sent every 2s)
    ip = discover_k17_udp(timeout=2.5)
    if ip:
        return ip

    # 2. Try mDNS via avahi-resolve if available
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
                print(f"[Discovery] Resolved via avahi-resolve: {parts[1]}", flush=True)
                return parts[1]
    except Exception:
        pass

    # 3. Try socket standard mDNS resolution
    try:
        ip = socket.gethostbyname(K17_MDNS_HOST)
        if ip:
            print(f"[Discovery] Resolved via gethostbyname: {ip}", flush=True)
            return ip
    except Exception:
        pass

    # 4. ARP table fallback using 'ip neighbor'
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
                        print(f"[Discovery] Resolved via ARP table: {parts[0]}", flush=True)
                        return parts[0]
    except Exception:
        pass

    return None


class K17Backend:
    def __init__(self, idle_timeout: float = 10.0):
        self.cached_ip: Optional[str] = None
        self.is_online: bool = False
        self.current_volume: Optional[int] = None
        self.last_mode_code: Optional[str] = None
        self.last_request_time: float = 0.0
        self.idle_timeout: float = idle_timeout
        self._sock: Optional[socket.socket] = None
        self._sock_connected_ip: Optional[str] = None
        self._sock_last_used: float = 0.0
        self._idle_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()

    def get_or_resolve_ip(self) -> Optional[str]:
        if not self.cached_ip:
            self.cached_ip = resolve_k17_ip()
        return self.cached_ip

    def _cancel_idle_timer(self):
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _schedule_idle_timer(self):
        self._cancel_idle_timer()
        if self._sock is not None:
            self._idle_timer = threading.Timer(self.idle_timeout, self._on_idle_timeout)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _on_idle_timeout(self):
        with self._lock:
            if self._sock and (time.time() - self._sock_last_used >= self.idle_timeout):
                print(f"[K17Backend] Idle timeout ({self.idle_timeout}s) reached. Closing socket to release lock.", flush=True)
                self._close_socket()

    def _close_socket(self):
        self._cancel_idle_timer()
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
        self._cancel_idle_timer()
        # Close socket if target IP changed or idle > idle_timeout
        if self._sock:
            if self._sock_connected_ip != ip or (now - self._sock_last_used > self.idle_timeout):
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
            if elapsed < 0.15:
                time.sleep(0.15 - elapsed)

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
                    self._schedule_idle_timer()

            return False, "Failed after retry"

    def fetch_status(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        1. Sends 05010008 to fetch volume and SoC JSON state.
        2. Sends 0607000c0000 to query active input mode explicitly.
        """
        had_cached_ip = self.cached_ip is not None
        success, raw_resp = self._send_command("05010008")

        # If failed and we previously had a cached IP, invalidate and attempt fresh resolution
        if not success and had_cached_ip:
            time.sleep(0.2)
            self.invalidate_cache()
            success, raw_resp = self._send_command("05010008")

        if not success:
            return False, None

        status_data: Dict[str, Any] = {}

        # 1. Parse JSON frame for volume
        match = re.search(r"(\{.*\})", raw_resp)
        if match:
            try:
                data = json.loads(match.group(1))
                if "currentVolume" in data:
                    try:
                        self.current_volume = int(data["currentVolume"])
                    except (ValueError, TypeError):
                        pass
                status_data.update(data)
            except json.JSONDecodeError:
                pass

        # 2. Extract active mode code from raw_resp header if present (e.g. 'a607000C0002a5010184...')
        prefix_mode_match = re.search(r"a607000c([0-9a-f]{4})", raw_resp, re.IGNORECASE)
        if prefix_mode_match:
            self.last_mode_code = prefix_mode_match.group(1).upper()
            status_data["modeCode"] = self.last_mode_code

        # 3. Query explicit active input mode: 0607000c0000
        mode_success, mode_resp = self._send_command("0607000c0000")
        if mode_success:
            mode_match = re.search(r"a607000c([0-9a-f]{4})", mode_resp, re.IGNORECASE)
            if mode_match:
                self.last_mode_code = mode_match.group(1).upper()
                status_data["modeCode"] = self.last_mode_code

        if not status_data.get("modeCode") and self.last_mode_code:
            status_data["modeCode"] = self.last_mode_code

        return True, status_data

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
        if success:
            self.last_mode_code = mode_code.upper()
        return success

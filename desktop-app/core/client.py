"""
FiiO K17 Low-Level TCP Client.
Handles connection lifecycle, auto-reconnect, command pacing, and idle lock release.
Pure Python - Zero UI dependencies.
"""
import socket
import threading
import time
from typing import Optional, Tuple

from .constants import K17_TCP_PORT
from .discovery import resolve_k17_ip


class K17Client:
    """
    Low-level socket connection manager for FiiO K17.
    Enforces single-active-client socket discipline with idle disconnect.
    """

    def __init__(self, idle_timeout: float = 10.0, target_ip: Optional[str] = None):
        self.cached_ip: Optional[str] = target_ip
        self.idle_timeout: float = idle_timeout
        self.last_request_time: float = 0.0

        self._sock: Optional[socket.socket] = None
        self._sock_connected_ip: Optional[str] = None
        self._sock_last_used: float = 0.0
        self._idle_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()

    def get_or_resolve_ip(self, force_resolve: bool = False) -> Optional[str]:
        with self._lock:
            if force_resolve or not self.cached_ip:
                self.cached_ip = resolve_k17_ip()
            return self.cached_ip

    def invalidate_cache(self):
        with self._lock:
            self._close_socket()
            self.cached_ip = None

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
                print(
                    f"[K17Client] Idle timeout ({self.idle_timeout}s) reached. Closing socket to release hardware lock.",
                    flush=True,
                )
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

    def _ensure_socket(self, ip: str) -> socket.socket:
        now = time.time()
        self._cancel_idle_timer()

        # Close socket if target IP changed or idle > idle_timeout
        if self._sock:
            if self._sock_connected_ip != ip or (now - self._sock_last_used > self.idle_timeout):
                self._close_socket()

        if self._sock is None:
            print(f"[K17Client] Connecting to {ip}:{K17_TCP_PORT}...", flush=True)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((ip, K17_TCP_PORT))
            self._sock = s
            self._sock_connected_ip = ip
            print(f"[K17Client] Socket connected to {ip}:{K17_TCP_PORT}", flush=True)

        self._sock_last_used = now
        return self._sock

    def send_raw_command(self, payload: str) -> Tuple[bool, str]:
        """
        Sends an ascii payload to the K17 DAC, waits for response bytes, and returns (success, response_string).
        Applies minimum 150ms inter-command pacing.
        """
        with self._lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < 0.15:
                time.sleep(0.15 - elapsed)

            ip = self.get_or_resolve_ip()
            print(f"[K17Client] Sending command '{payload}' to IP: {ip}", flush=True)
            if not ip:
                print("[K17Client] Error: K17 DAC IP could not be resolved", flush=True)
                return False, "K17 DAC not found on local network"

            for attempt in range(2):
                try:
                    s = self._ensure_socket(ip)
                    print(f"[K17Client] Transmitting payload: {payload}", flush=True)
                    s.sendall(payload.encode("ascii"))

                    response_bytes = b""
                    is_json_query = payload.startswith("0501")
                    timed_out = False

                    while True:
                        try:
                            chunk = s.recv(1024)
                            if not chunk:
                                print("[K17Client] Received EOF from server", flush=True)
                                self._close_socket()
                                break
                            response_bytes += chunk
                            if is_json_query and b"}" in response_bytes:
                                break
                            if not is_json_query and len(response_bytes) >= 12:
                                break
                        except socket.timeout:
                            print("[K17Client] recv timed out waiting for reply", flush=True)
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
                    print(f"[K17Client] Received raw reply ({len(response_bytes)} bytes): {raw_str!r}", flush=True)
                    self._sock_last_used = time.time()
                    return True, raw_str

                except Exception as e:
                    print(
                        f"[K17Client] Socket exception on attempt {attempt + 1} during '{payload}': {type(e).__name__}: {e}",
                        flush=True,
                    )
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

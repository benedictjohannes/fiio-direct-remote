"""
FiiO K17 High-Level Device Controller & State Store.
Pure Python - Zero UI dependencies.
"""
from dataclasses import dataclass, field
import threading
from typing import Optional, Dict, Any, Callable, List, Tuple

from .constants import InputMode
from .client import K17Client
from .protocol import (
    build_status_query,
    build_volume_command,
    build_input_query,
    build_input_command,
    parse_status_response,
    parse_mode_response,
)


@dataclass
class K17State:
    is_online: bool = False
    volume: Optional[int] = None
    input_mode: Optional[InputMode] = None
    ip_address: Optional[str] = None
    raw_status: Dict[str, Any] = field(default_factory=dict)


StateListener = Callable[[K17State], None]


class K17DeviceController:
    """
    High-level controller and state container for FiiO K17.
    Supports thread-safe state inspection and event listeners.
    """

    def __init__(self, client: Optional[K17Client] = None, idle_timeout: float = 10.0):
        self.client = client or K17Client(idle_timeout=idle_timeout)
        self.state = K17State()
        self._listeners: List[StateListener] = []
        self._lock = threading.RLock()

    @property
    def is_online(self) -> bool:
        return self.state.is_online

    @property
    def current_volume(self) -> Optional[int]:
        return self.state.volume

    @property
    def current_mode(self) -> Optional[InputMode]:
        return self.state.input_mode

    @property
    def cached_ip(self) -> Optional[str]:
        return self.client.cached_ip

    def add_state_listener(self, listener: StateListener):
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_state_listener(self, listener: StateListener):
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify_listeners(self):
        with self._lock:
            listeners = list(self._listeners)
            state_copy = K17State(
                is_online=self.state.is_online,
                volume=self.state.volume,
                input_mode=self.state.input_mode,
                ip_address=self.state.ip_address,
                raw_status=dict(self.state.raw_status),
            )
        for listener in listeners:
            try:
                listener(state_copy)
            except Exception as e:
                print(f"[K17Controller] Error in state listener: {e}", flush=True)

    def invalidate_cache(self):
        with self._lock:
            self.client.invalidate_cache()
            self.state.is_online = False
            self.state.ip_address = None
            self._notify_listeners()

    def fetch_status(self, force_resolve: bool = False) -> Tuple[bool, K17State]:
        """
        Polls DAC status:
        1. 05010008 (JSON state & volume).
        2. 0607000c0000 (Active input mode).
        """
        with self._lock:
            if force_resolve:
                self.client.invalidate_cache()

            had_cached_ip = self.client.cached_ip is not None
            payload = build_status_query()
            success, raw_resp = self.client.send_raw_command(payload)

            if not success and had_cached_ip and not force_resolve:
                self.client.invalidate_cache()
                success, raw_resp = self.client.send_raw_command(payload)

            if not success:
                self.state.is_online = False
                self._notify_listeners()
                return False, self.state

            self.state.is_online = True
            self.state.ip_address = self.client.cached_ip
            parsed_data = parse_status_response(raw_resp)
            self.state.raw_status.update(parsed_data)

            if "volume" in parsed_data:
                self.state.volume = parsed_data["volume"]

            if parsed_data.get("input_mode"):
                self.state.input_mode = parsed_data["input_mode"]

            # Query input mode explicitly
            mode_query = build_input_query()
            mode_ok, mode_raw = self.client.send_raw_command(mode_query)
            if mode_ok:
                active_mode = parse_mode_response(mode_raw)
                if active_mode:
                    self.state.input_mode = active_mode

            self._notify_listeners()
            return True, self.state

    def set_volume(self, val: int) -> bool:
        """Sets DAC volume (0 to 100)."""
        with self._lock:
            payload = build_volume_command(val)
            success, _ = self.client.send_raw_command(payload)
            if success:
                self.state.volume = max(0, min(100, int(val)))
                self.state.is_online = True
                self._notify_listeners()
            return success

    def set_input_mode(self, mode: InputMode | str) -> bool:
        """Switches DAC active input source."""
        with self._lock:
            payload = build_input_command(mode)
            success, _ = self.client.send_raw_command(payload)
            if success:
                target_mode = mode if isinstance(mode, InputMode) else InputMode.from_code(str(mode))
                self.state.input_mode = target_mode
                self.state.is_online = True
                self._notify_listeners()
            return success

"""
FiiO K17 Core Library.
"""
from .constants import (
    K17_TCP_PORT,
    K17_DISCOVERY_PORT,
    K17_MULTICAST_GROUP,
    K17_MDNS_HOST,
    K17_MAC_PREFIX,
    InputMode,
    MODE_DISPLAY_NAMES,
    INPUT_MODES_ORDERED,
)
from .protocol import (
    build_status_query,
    build_volume_command,
    build_input_query,
    build_input_command,
    parse_status_response,
    parse_mode_response,
)
from .discovery import (
    discover_k17_udp,
    resolve_k17_mdns,
    resolve_k17_arp,
    resolve_k17_ip,
)
from .client import K17Client
from .controller import K17DeviceController, K17State

__all__ = [
    "K17_TCP_PORT",
    "K17_DISCOVERY_PORT",
    "K17_MULTICAST_GROUP",
    "K17_MDNS_HOST",
    "K17_MAC_PREFIX",
    "InputMode",
    "MODE_DISPLAY_NAMES",
    "INPUT_MODES_ORDERED",
    "build_status_query",
    "build_volume_command",
    "build_input_query",
    "build_input_command",
    "parse_status_response",
    "parse_mode_response",
    "discover_k17_udp",
    "resolve_k17_mdns",
    "resolve_k17_arp",
    "resolve_k17_ip",
    "K17Client",
    "K17DeviceController",
    "K17State",
]

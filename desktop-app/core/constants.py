"""
FiiO K17 Core Constants and Definitions.
Pure Python - Zero UI or platform dependencies.
"""
from enum import Enum
from typing import List, Tuple

# Network & Protocol Constants
K17_TCP_PORT: int = 12100
K17_DISCOVERY_PORT: int = 12101
K17_MULTICAST_GROUP: str = "224.0.0.255"
K17_MDNS_HOST: str = "ingenic.local"
K17_MAC_PREFIX: str = "40:d9:5a"

# Protocol Header Prefixes
CMD_PREFIX_STATUS_QUERY: str = "05010008"
CMD_PREFIX_VOLUME_SET: str = "0502000c"
CMD_PREFIX_INPUT_QUERY: str = "0607000c0000"
CMD_PREFIX_INPUT_SET: str = "0657000c"

RESP_PREFIX_MODE: str = "a607000c"


class InputMode(str, Enum):
    USB = "0001"
    OPTICAL = "0002"
    COAXIAL = "0003"
    LINE_IN = "0004"
    BALANCED = "0005"
    BLUETOOTH = "0006"
    STREAMING = "0007"

    @property
    def display_name(self) -> str:
        return MODE_DISPLAY_NAMES.get(self, self.name)

    @classmethod
    def from_code(cls, code: str) -> "InputMode":
        code_norm = code.strip().zfill(4).lower()
        for mode in cls:
            if mode.value.lower() == code_norm:
                return mode
        raise ValueError(f"Unknown input mode code: {code}")


MODE_DISPLAY_NAMES = {
    InputMode.USB: "USB Audio",
    InputMode.OPTICAL: "Optical In",
    InputMode.COAXIAL: "Coaxial In",
    InputMode.LINE_IN: "Line In",
    InputMode.BALANCED: "Balanced / XLR",
    InputMode.BLUETOOTH: "Bluetooth",
    InputMode.STREAMING: "Streaming",
}

INPUT_MODES_ORDERED: List[Tuple[str, str]] = [
    (mode.display_name, mode.value) for mode in InputMode
]

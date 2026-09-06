"""
FiiO K17 Wire Protocol Encoding and Decoding.
Pure Python - Zero UI or platform dependencies.
"""
import json
import re
from typing import Optional, Dict, Any, Tuple
from .constants import (
    CMD_PREFIX_STATUS_QUERY,
    CMD_PREFIX_VOLUME_SET,
    CMD_PREFIX_INPUT_QUERY,
    CMD_PREFIX_INPUT_SET,
    RESP_PREFIX_MODE,
    InputMode,
)


def build_status_query() -> str:
    """Builds the 8-byte hex payload to query volume and SoC JSON state."""
    return CMD_PREFIX_STATUS_QUERY


def build_volume_command(volume: int) -> str:
    """
    Builds the payload to set DAC volume (0 to 100).
    Payload: 0502000c + 4-char uppercase hex.
    """
    clamped = max(0, min(100, int(volume)))
    return f"{CMD_PREFIX_VOLUME_SET}{clamped:04X}"


def build_input_query() -> str:
    """Builds the payload to query the currently active input source."""
    return CMD_PREFIX_INPUT_QUERY


def build_input_command(mode: InputMode | str) -> str:
    """
    Builds the payload to switch input mode.
    Payload: 0657000c + 4-char mode code.
    """
    code = mode.value if isinstance(mode, InputMode) else str(mode).strip().zfill(4)
    return f"{CMD_PREFIX_INPUT_SET}{code.lower()}"


def parse_status_response(raw_resp: str) -> Dict[str, Any]:
    """
    Parses a raw reply from a 05010008 query.
    Extracts embedded JSON state and optional mode code header prefix.
    """
    result: Dict[str, Any] = {}

    # 1. Look for embedded JSON object
    json_match = re.search(r"(\{.*\})", raw_resp)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            result.update(parsed)
            if "currentVolume" in parsed:
                try:
                    result["volume"] = int(parsed["currentVolume"])
                except (ValueError, TypeError):
                    pass
        except json.JSONDecodeError:
            pass

    # 2. Look for mode prefix embedded in stream (e.g., a607000c0002...)
    mode_match = re.search(rf"{RESP_PREFIX_MODE}([0-9a-f]{{4}})", raw_resp, re.IGNORECASE)
    if mode_match:
        mode_code = mode_match.group(1).lower()
        result["mode_code"] = mode_code
        try:
            result["input_mode"] = InputMode.from_code(mode_code)
        except ValueError:
            result["input_mode"] = None

    return result


def parse_mode_response(raw_resp: str) -> Optional[InputMode]:
    """
    Parses the response to an input mode query (0607000c0000) or switch command.
    """
    mode_match = re.search(rf"{RESP_PREFIX_MODE}([0-9a-f]{{4}})", raw_resp, re.IGNORECASE)
    if mode_match:
        mode_code = mode_match.group(1).lower()
        try:
            return InputMode.from_code(mode_code)
        except ValueError:
            return None
    return None

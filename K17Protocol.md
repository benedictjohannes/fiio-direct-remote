# FiiO K17 Network Protocol Reference

This document details the reverse-engineered wire protocol for discovering and controlling the **FiiO K17 DAC** over the local network.

---

## 1. Network & Discovery Architecture

### 1.1 Device Discovery (Multicast UDP Heartbeat)
The K17 firmware continuously broadcasts a discovery heartbeat over UDP multicast:
- **Multicast Group:** `224.0.0.255`
- **Port:** `12101` (UDP)
- **Interval:** Every 2 seconds
- **Payload:** Raw ASCII `K17` (3 bytes: `0x4B 0x31 0x37`)
- **Sender Address:** Device LAN IP (e.g. `192.168.18.128:<ephemeral_port>`)

Clients can listen on UDP multicast socket `224.0.0.255:12101` to automatically discover the device's IP without relying on mDNS or subnet scanning.

### 1.2 Host Resolution Fallbacks
- **mDNS Hostname:** `ingenic.local`
- **MAC Address Prefix:** `40:d9:5a` (Ingenic Semiconductor)

### 1.3 Control Channel (TCP)
- **Port:** `12100` (TCP)
- **Socket Policy:**
  - The K17 firmware accepts a **single active TCP client** on port `12100`.
  - Recommended client architecture: reuse sockets during active interaction, and cleanly close after an idle timeout (e.g. 10–30 seconds) to release the device lock.
- **Wire Format:** ASCII-encoded hexadecimal strings and embedded JSON payloads.

---

## 2. Protocol Namespaces

The protocol is split into two distinct functional subsystems:

| Subsystem | Setter Prefix | ACK / Response Header | Query Opcode | Description |
| :--- | :--- | :--- | :--- | :--- |
| **System & Handshake** | `0599...` | `a599...` | `0599000c0000` | Protocol version negotiation / handshake. |
| **SoC / Media Daemon** | `0502...` | `a502...` | `05010008` | Controls volume, media playback, SoC display parameters, and returns JSON state. |
| **MCU / DSP Routing** | `0657...` | `a60a...` / `a607...` | `0607000c0000` | Queries and switches physical audio input multiplexing (USB, Optical, Coax, etc.). |
| **DSP / EQ Configuration** | `0627...` / `0628...` | `a627...` / `a628...` | `06270010...` / `06280010...` | Reads & configures EQ profiles, PEQ curves, and filters. |

---

## 3. Command Specifications

### 3.1 Initial Handshake (`0599000c0000`)
- **Query:** Send ASCII `0599000c0000`
- **Response:** `a599000C0302` (Handshake ACK and protocol revision code)

---

### 3.2 Media & Volume State Query (`05010008`)

- **Payload:** Send ASCII `05010008`
- **Response Format:** Composite ASCII hex prefix header followed by a JSON payload:
  ```
  <PREFIX_HEADER>{"currentVolume": 63, "maxVolume": 100, "usbAudio": 2, ...}
  ```

#### Transient Event Prefix Behavior
The prefix header before the JSON string is **event-driven & stateful**, reflecting the active mode and most recent system event:
- **Default / Mode State:** `a607000C<MODE_CODE>` prefix directly precedes the media header (e.g. `a607000C0002a5010184{"currentVolume":...}` for Optical In).
- **Cold Start / Idle (no mode prefix):** `a5010184` (standard media status header).
- **Post-Volume Change:** `a502000c<VOL_HEX>` (e.g. `a502000C003F` for volume 63).
- **Post-Input Mode Change:** `a607000c<MODE_CODE>` (e.g. `a607000C0002` for Optical In).

> [!WARNING]
> The JSON field `"usbAudio": 2` is a static SoC driver property and does **not** represent the currently selected input mode.
> Always extract the input mode from the `a607000c<MODE_CODE>` prefix in the status frame or mode query.

---

### 3.3 Audio Input Mode Query & Switch

#### Query Active Input Mode (`0607000c0000`)
- **Payload:** Send ASCII `0607000c0000`
- **Response:**
  - Standard ACK: `a60a000C000C` (command acknowledged)
  - Mode packet: `a607000C<MODE_CODE>` (or reflected in subsequent `05010008` poll prefix)

#### Set Input Mode (`0657000c<MODE_CODE>`)
- **Set Input Mode:** Send ASCII `0657000c` + 4-character mode code:
  - `0001`: USB Audio
  - `0002`: Optical In
  - `0003`: Coaxial In
  - `0004`: Line In
  - `0005`: Balanced / XLR
  - `0006`: Bluetooth
  - `0007`: Streaming
- **Example:** Switch to Coaxial -> Send `0657000c0003`
- **ACK:** Returns `a607000C0003` or `a60a000C000C` on TCP stream.

---

### 3.4 Volume Control

- **Set Volume:** Send ASCII `0502000c` + 4-character uppercase hex value (`0000` to `0064`, 0–100%).
  - Example (Volume 75% -> `0x004B`): `0502000c004B`
  - Response: `a60a000C000C` (immediate ACK) followed by `a502000C004B...` on subsequent status poll.

---

## 4. Standard Client Initialization Sequence

When establishing a fresh connection to the K17 over TCP `12100`:
1. **Send Handshake (Optional):** `0599000c0000` (Receive: `a599000C0302`)
2. **Poll Volume, Media & Active Mode:** `05010008`
   - Response: `a607000C<MODE_CODE>a5010184{"currentVolume": <VOL>, ...}`
   - Extract volume from `currentVolume` and input mode from `a607000c<MODE>`.
3. **Explicit Input Mode Refresh (Optional):** `0607000c0000` (Receive: `a60a000C000C` ACK)

# FiiO K17 System Tray Controller - Implementation Plan

## Overview
A lightweight system tray controller for the FiiO K17 DAC built with **Python & PyQt6**, tailored for **KDE Plasma / Linux**. It allows quick volume adjustments and input mode switching directly from the desktop tray.

---

## 1. Network & Protocol Architecture

### Target Resolution & Discovery
- **Discovery Strategy:**
  1. **UDP Multicast Discovery (Primary):** Listen on multicast group `224.0.0.255:12101` for the 2-second periodic `K17` ASCII heartbeat. Extracts the device LAN IP instantly with zero CLI dependency.
  2. **mDNS Resolution (Fallback 1):** Resolve hostname `ingenic.local` via `avahi-resolve` or standard DNS socket resolution.
  3. **ARP Table Inspection (Fallback 2):** Parse `/proc/net/arp` or `ip neighbor` matching the Ingenic MAC address prefix `40:d9:5a`.
- **IP Caching:** Cache resolved IP in memory (`self.cached_ip`).
- **Cache Invalidation & Failure State:**
  - If target resolution or status fetch fails (on startup or tray open), clear `cached_ip` and mark device state as `OFFLINE`.
  - Store `is_online = False` in the application state.

### Connection Strategy
- **On-Demand Short-Lived Sockets:** Open a fresh socket per command/poll, perform read/write, and close after idle timeout (e.g. 30s). Avoids background connection drop & keep-alive complexity.

### Protocol Reference
- Full wire protocol specification is documented in [K17Protocol.md](K17Protocol.md).
- **Status & Mode Poll Sequence:**
  1. **Volume / Media Poll (`05010008`):** Send ASCII `05010008` over TCP. Returns JSON frame containing `currentVolume` (0–100) and `maxVolume` (100).
  2. **Active Input Mode Poll (`0607000c0000`):** Send ASCII `0607000c0000` over TCP. Returns `a607000C<MODE_CODE>` denoting the active input mode (`0001` = USB, `0002` = Optical, `0003` = Coaxial, `0004` = Line In, `0005` = Balanced, `0006` = Bluetooth, `0007` = Streaming).
  - Both queries are executed during initial connect / tray popup open to ensure exact volume and input mode are shown on cold start without placeholder guessing.
- **Volume Set Command:** Send ASCII `0502000c` + 4-character UPPERCASE HEX value (`0` -> `0000`, `100` -> `0064`).
- **Input Mode Set Command:** Send ASCII `0657000c` + 4-character mode ID.
  - `0001`: USB
  - `0002`: Optical
  - `0003`: Coaxial
  - `0004`: Line In
  - `0005`: Balanced / XLR
  - `0006`: Bluetooth
  - `0007`: Streaming


## 2. Interaction, Offline & Retry Flow

1. **Startup Initialization:**
   - App launches and immediately performs an initial status check (`fetch_status`).
   - If successful: sets state to `ONLINE`, updates tray icon to active state, populates initial UI values.
   - If failed: sets state to `OFFLINE`, updates tray icon to offline/error state.

2. **Tray Popup Opened (Activated / Clicked):**
   - Every time the tray popup is opened, trigger a fresh asynchronous status query (`05010008`).
   - If `OFFLINE`, this acts as an automatic retry mechanism to attempt re-resolution and re-connecting.
   - On success: transitions to `ONLINE`, updates icon to normal state, enables controls, and syncs UI slider/input selector.
   - On failure: remains `OFFLINE`, maintains offline icon, and presents an offline notice / retry indicator in the popup widget.

3. **Volume Adjustment (Debounced 500ms):**
   - Slider movement updates UI immediately (when `ONLINE`).
   - A `QTimer` waits for **500ms** of idle time after the user stops scrolling/dragging before sending the `0502000cXXXX` volume packet.
4. **Input Mode Switch:**
   - Selecting a new input mode instantly dispatches the mode command (`0657000cXXXX`).

---

## 3. UI Components, Tray Icons & KDE Plasma Integration

- **Tray Icon (`QSystemTrayIcon`):**
  - Specified independently in Python using `QIcon` (`QSystemTrayIcon.setIcon(icon)`).
  - Supports SVG assets so it scales crisply in KDE Plasma system trays.
  - **Dynamic State Icons:**
    - **Connected / Online:** Stylized K17 logo (monochrome/theme-adaptive or active color).
    - **Failed / Offline:** Stylized K17 logo with an offline visual badge/tint (e.g., greyed out with a subtle warning/slash emblem).
- **Popup Card / Context Menu:**
  - **Volume Section:** Slider (0-100) + numeric percentage label + scroll listener (disabled when offline).
  - **Input Mode Section:** Radio list or dropdown for switching between input modes (disabled when offline).
  - **Connection Indicator:** Visual badge (Connected / Searching... / Offline - Click tray to retry).

---

## 4. Architecture & Directory Structure

```text
DesktopApp/
├── assets/
│   ├── k17_logo_online.svg / png   # Active connected tray icon
│   └── k17_logo_offline.svg / png  # Disconnected/error tray icon
│
├── core/                           # 100% Pure Python & Cross-Platform (Zero UI / Toolkit deps)
│   ├── constants.py                # Ports, commands, InputMode enum & display names
│   ├── discovery.py                # UDP multicast + socket mDNS + cross-platform ARP (Linux/Win/Mac)
│   ├── protocol.py                 # Hex framing & payload serialization/deserialization
│   ├── client.py                   # TCP socket lifecycle, lock release idle timer, rate limiting
│   └── controller.py               # High-level state machine + event subscriber hooks
│
├── frontends/                      # Modular UI / Presentation Frontends
│   └── kde_qt/                     # KDE Plasma / Freedesktop PyQt6 System Tray
│       ├── app.py                  # Tray application lifecycle manager
│       ├── popup_window.py         # Qt dark theme control card
│       ├── tray_sni.py             # D-Bus StatusNotifierItem (scroll wheel support)
│       ├── workers.py              # Qt QThread async bridges to core controller
│       └── notifications.py        # D-Bus desktop notification helper
│
└── main.py                         # Application entrypoint
```

---

# Status:

- **Core Library (`core/`):** Pure Python, decoupled, tested across discovery, protocol framing, and observer subscriptions.
- **KDE Qt Frontend (`frontends/kde_qt/`):** Implemented with KDE/Freedesktop StatusNotifierItem D-Bus integration and PyQt6 card popup.

## Verification Strategy
- Test IP resolution (UDP multicast, mDNS, cross-platform ARP fallback).
- Verify status parsing from JSON frame and mode header prefixes.
- Test volume slider debouncing (confirm no packet spam).
- Test input mode toggling.



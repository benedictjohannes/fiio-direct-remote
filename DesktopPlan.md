# FiiO K17 System Tray Controller - Implementation Plan

## Overview
A lightweight system tray controller for the FiiO K17 DAC built with **Python & PyQt6**, tailored for **KDE Plasma / Linux**. It allows quick volume adjustments and input mode switching directly from the desktop tray.

---

## 1. Network & Protocol Architecture

### Target Resolution & IP Caching
- **Target Host:** `ingenic.local` (mDNS) with ARP table fallback (`40:d9:5a` MAC prefix). Port: `12100` over TCP.
- **IP Caching:** Resolve the IP once at startup and cache it in memory (`self.cached_ip`).
- **Cache Invalidation & Failure State:**
  - If target resolution or status fetch fails (on startup or tray open), clear `cached_ip` and mark device state as `OFFLINE`.
  - Store `is_online = False` in the application state.

### Connection Strategy
- **On-Demand Short-Lived Sockets:** Open a fresh socket per command/poll, perform read/write, and close. Avoids background connection drop & keep-alive complexity.

### Protocol Reference
- See [k17_ctrl.sh](k17_ctrl.sh) for a simple and tested Bash implementation created through reverse engineering the wire protocol, observed through `adb shell` into the DAC.
- **Status Poll Command:** Send ASCII `05010008` over TCP.
  - Returns a payload containing JSON with status keys:
    ```json
    {
      "currentVolume": 83,
      "folderJump": true,
      "gaplessPlay": true,
      "maxVolume": 100,
      "memoryPlay": false,
      "memoryType": 0,
      "playMode": 0,
      "replayGain": 0,
      "usbAudio": 2
    }
    ```
- **Volume Set Command:** Send ASCII `0502000c` + 4-character UPPERCASE HEX value (`0` -> `0000`, `100` -> `0064`).
- **Input Mode Set Command:** Send ASCII `0657000c` + 4-character mode ID:
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

## 4. Implementation Steps & Directory Structure

All application components will be located in the `DesktopApp/` directory:

```
DesktopApp/
├── assets/
│   ├── k17_logo_online.svg / png   # Active connected tray icon (prefer using SVG)
│   └── k17_logo_offline.svg / png  # Disconnected/error tray icon (prefer using SVG)
├── k17_backend.py                  # mDNS/ARP IP resolution & TCP socket protocol
├── k17_tray.py                     # PyQt6 system tray icon & popup control widget
└── main.py                         # Application entrypoint
```

1. **`DesktopApp/k17_backend.py` / Network Module:**
   - Implement `resolve_k17_ip()` with mDNS and ARP lookup fallback.
   - Implement async send/receive functions (`fetch_status`, `set_volume`, `set_mode`) using cached IP with error propagation.
2. **`DesktopApp/k17_tray.py` / PyQt6 UI:**
   - Build main `QApplication` & `QSystemTrayIcon`.
   - Use logo assets in `DesktopApp/assets/` for K17 stylized logo (Online and Offline states).
   - Build popover widget with volume slider, 500ms debounce `QTimer`, input mode buttons, and status indicator.
   - Implement state switcher method `set_device_state(is_online: bool)` that updates the tray icon and popup UI.
   - Wire popup show signal to asynchronous status refresh / retry logic.
3. **Script / Entrypoint (`DesktopApp/main.py`):**
   - Add CLI support / background daemon setup.
   - Test functionality against physical FiiO K17 hardware.

---

# Status:

- assets: generated
- - python files: written, untested.

## Verification Strategy
- Test IP resolution (mDNS & ARP fallback).
- Verify status parsing from JSON frame.
- Test volume slider debouncing (confirm no packet spam).
- Test input mode toggling.

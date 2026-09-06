# FiiO K17 Android Remote Controller - Implementation Plan

## Overview
A lightweight native Android remote control app for the **FiiO K17 DAC** built with **Kotlin & Jetpack Compose** (and Jetpack Glance for Home Screen Widgets). It acts strictly as a network remote control over the local Wi-Fi network, providing direct volume control, input mode switching, optional media notification seekbar integration, a responsive home screen widget, and hardware volume key handling when the app is active.

---

## 1. Network & Protocol Architecture

### Target Resolution & Discovery
The K17 DAC supports automated zero-configuration discovery over local Wi-Fi. The client implements a **3-tier resolution strategy**:
1. **Multicast UDP Discovery Heartbeat (Primary):**
   - The K17 firmware continuously broadcasts ASCII `K17` over UDP multicast group `224.0.0.255:12101` every 2 seconds.
   - On connection/refresh, the app acquires an Android `WifiManager.MulticastLock` and listens on `224.0.0.255:12101` for incoming heartbeat packets to extract the sender's device LAN IP immediately.
2. **mDNS Resolution (Fallback):**
   - Hostname: `ingenic.local` (Port `12100` TCP)
   - Resolved via `InetAddress.getByName("ingenic.local")` and `NsdManager`.
   - MAC address prefix reference: `40:d9:5a` (Ingenic Semiconductor).
3. **Manual Static IP (Fallback):**
   - User-configurable manual IP in Settings (stored via Jetpack DataStore) for environments where multicast/mDNS is blocked by AP client isolation.

- **IP Caching:** Caches the resolved IP in memory and persistent storage until communication fails.

### Socket Management & Exclusive Lock Policy
The K17 firmware only supports a single active TCP client connection on port `12100`.
- **Configurable Idle Disconnect Timeout:**
  - Default: **10 seconds** (configurable in Settings UI: 3s to 60s).
  - An established socket is reused during active user interaction.
  - When idle for the configured duration without commands/polls, the socket is cleanly closed so other controllers (Desktop App, FiiO app, etc.) are not locked out.
- **Presence Heartbeat & Auto-Teardown:**
  - While `K17RemoteService` is active, a lightweight presence check runs every 20 seconds.
  - Android `NetworkCallback` monitors Wi-Fi state. If Wi-Fi disconnects or 2 consecutive pings fail, the service cleanly terminates itself and dismisses the media notification.

### Protocol Subsystems & Opcode Reference
The protocol communicates over ASCII hex strings and embedded JSON:

| Subsystem | Opcode / Prefix | Type | Description |
| :--- | :--- | :--- | :--- |
| **System & Handshake** | `0599000c0000` | Query / Ping | Handshake query. Response: `a599000C0302`. |
| **SoC / Media Daemon** | `05010008` | Query | Media & volume status query. Returns JSON state + event prefix. |
| **SoC / Volume Set** | `0502000c<VOL_HEX>` | Setter | Volume setter (e.g. `0502000c004B` for 75%). |
| **MCU / Mode Query** | `0607000c0000` | Query | Queries active physical input mode. Response: `a60a000C000C` / `a607000C<MODE>`. |
| **MCU / Mode Set** | `0657000c<MODE_CODE>` | Setter | Switches input multiplexer (`0001`–`0007`). Response: `a607000C<MODE>` or `a60a...`. |
| **DSP / EQ Config** | `0627...` / `0628...` | Future | PEQ / EQ profile configuration. |

#### Input Mode Codes
- `0001`: USB Audio
- `0002`: Optical In
- `0003`: Coaxial In
- `0004`: Line In
- `0005`: Balanced / XLR
- `0006`: Bluetooth
- `0007`: Streaming

#### Status Poll & Composite Frame Parsing
- **Status Poll Command:** Send ASCII `05010008` over TCP.
  - Returns a composite packet containing binary hex status headers and JSON payload (e.g. `a607000C0002a5010184{"currentVolume":65,...}`).
  - **Active Input Mode Header:** When an input mode switch command or query is processed, the device prefixes the response with an `a607000c<MODE_CODE>` header.
  - **Volume & Device State JSON:** The embedded JSON contains `currentVolume` (0–100) and `maxVolume` (100).
  - *Note:* The JSON field `"usbAudio": 2` is a static SOC audio driver property and does *not* reflect the currently selected active input source channel.
  - **Cold Start / Multi-Step Query Fallback:** If `05010008` returns without an `a607000c` prefix (e.g. post-volume adjustment or cold start), the client queries `0607000c0000` to retrieve the active input mode.

---

## 2. Android Lifecycle & Background Integration

### Media Notification Toggle & Service Control
- **User Preference Toggle:** In app settings and main UI header, a toggle: `"Show Media Notification"` (persisted in DataStore).
  - **Enabled:** Starting the remote triggers `K17RemoteService` (Foreground Service) and renders the system Media Notification with seekbar scrubbing.
  - **Disabled:** The app operates purely in the foreground (or on-demand via Widget/QS Tile), with zero persistent notification running in the shade.

### Media Notification & Seekbar Volume Scrubbing (When Enabled)
- Publishes an Android `MediaSessionCompat` with playback state `STATE_PLAYING`.
- **Seekbar as Volume Slider:**
  - Configures media duration as `100,000 ms` (100 seconds) corresponding to 0–100% volume.
  - Listens to `onSeekTo(positionMs)`. When the user scrubs the seekbar in the notification shade / lock screen, `onSeekTo` receives the target value and dispatches the volume packet on drag release.
- **Notification Action Buttons:**
  - **Open App:** Brings `MainActivity` to foreground.
  - **Stop:** Immediately tears down the foreground service, closes sockets, and removes the notification.

### Hardware Volume Rocker Keys (Foreground Only)
- In `MainActivity`:
  - Intercepts `KEYCODE_VOLUME_UP` and `KEYCODE_VOLUME_DOWN` events via `onKeyDown` / `dispatchKeyEvent`.
  - Adjusts volume by step size (+/- 2 or 5), updates Compose UI instantly, and dispatches the debounced command to the DAC.

---

## 3. Home Screen Widget (Jetpack Glance)

The widget operates seamlessly in two visual states:

### 1. Inactive / Disconnected State
- Compact card showing: *FiiO K17 Disconnected / Offline*.
- **"Connect" Action Button:**
  - On tap: Triggers asynchronous network discovery (`ingenic.local`) -> fetches initial device status (`05010008`).
  - On success: transitions widget to **Active State** and starts the idle socket timeout timer (e.g. 10s).
  - On failure: briefly flashes "Device not found" with retry icon.

### 2. Active / Connected State
- Shows:
  - **Device Header:** Current input mode badge (e.g. `Optical`, `USB`) + volume level (e.g. `65%`).
  - **Steppers / Controls:** `[-5]` / `[-1]`, `[+1]` / `[+5]`, and Mute toggles.
  - **Quick Input Switcher:** Cycle through next input mode directly from the widget.
  - **"Open App" Icon:** Tapping launches `MainActivity`.
- **Socket Lifecycle Integration:**
  - Interacting with any widget button reuses/opens the socket and resets the configurable 10s idle countdown.
  - After 10s of inactivity, the socket closes cleanly in the background, but the widget remains in its last known state or returns to standby until touched again.

---

## 4. UI Components & Jetpack Compose Layout

- **Home Screen:**
  - **Header Bar:** Media Notification Toggle switch, Settings gear icon, and Connection Status badge.
  - **Volume Control:** Large interactive volume slider (0–100) with current percentage / dB label and quick stepper buttons.
  - **Input Mode Selector:** Grid / Chips for switching inputs (USB, Optical, Coaxial, Line In, Balanced, Bluetooth, Streaming).
- **Settings Sheet / Dialog:**
  - **Media Notification Toggle:** Enable / disable background media notification.
  - **Socket Idle Timeout:** Slider / number picker (default: 10s).
  - **Manual IP Override:** Optional static IP field for networks where mDNS is blocked.
  - **Volume Step Size:** Configuration for hardware key step (+/- 1, 2, or 5).
- **Quick Settings Tile (`K17TileService`):**
  - Allows 1-tap toggling of the remote session directly from Android QS shade.

---

## 5. Proposed Project Structure

```
android-app/
├── app/
│   ├── src/main/
│   │   ├── java/com/quirkies/fiiok17/
│   │   │   ├── data/
│   │   │   │   ├── K17Backend.kt          # Coroutine TCP client, timeout & reconnect logic
│   │   │   │   ├── K17Discovery.kt        # UDP Multicast, mDNS resolution & presence ping
│   │   │   │   ├── K17Protocol.kt         # Protocol opcodes, framing regex & status parser
│   │   │   │   └── UserPreferences.kt     # DataStore for notification toggle, timeout & IP
│   │   │   ├── service/
│   │   │   │   ├── K17RemoteService.kt    # Foreground service & MediaSession (Seekbar volume)
│   │   │   │   └── K17TileService.kt      # Android Quick Settings Tile
│   │   │   ├── widget/
│   │   │   │   ├── K17Widget.kt           # GlanceAppWidget implementation (Active/Inactive states)
│   │   │   │   └── K17WidgetReceiver.kt   # GlanceAppWidgetReceiver
│   │   │   ├── ui/
│   │   │   │   ├── MainActivity.kt        # Volume key override & root Composable
│   │   │   │   ├── MainViewModel.kt       # State holder for UI, Widget & Service
│   │   │   │   ├── screens/
│   │   │   │   │   ├── HomeScreen.kt      # Volume slider, Input switcher, notification toggle
│   │   │   │   │   └── SettingsDialog.kt  # Socket timeout, manual IP, step size settings
│   │   │   │   └── theme/                 # Material 3 color & typography definitions
│   │   │   └── AndroidManifest.xml
│   │   └── res/
│   │       ├── drawable/                  # K17 logo & notification/widget icons
│   │       └── values/
│   ├── build.gradle.kts
│   └── proguard-rules.pro
└── build.gradle.kts
```

---

## 6. Verification Plan

### Automated / Unit Tests
- Test hex packet formatting for volume (`0502000c0064` for 100) and input modes.
- Test JSON status parser for `currentVolume` extraction.
- Test socket auto-close timer reset on subsequent commands.

### Manual Verification on Device
1. **Network Discovery & Connect:** Verify app discovers `ingenic.local` and retrieves current volume and active input.
2. **Notification Toggle:** Turn off Media Notification in settings -> verify no foreground service or notification appears in notification shade while app or widget runs.
3. **Home Screen Widget:**
   - Place widget on home screen in Inactive state.
   - Tap "Connect" -> confirm discovery, status sync, and transition to Active state.
   - Tap `+5` / `-5` or change input on the widget -> confirm instant K17 response.
4. **Socket Release Timeout:** Confirm that after 10s of idle, the socket closes and the Desktop App or FiiO official app can connect without conflict.
5. **Media Notification Slider (When Enabled):** Drag seekbar in notification and confirm K17 hardware volume updates accurately on release.
6. **Presence Auto-Exit:** Turn off DAC or disconnect Wi-Fi and verify the media notification and active service close automatically.

---

## 7. Local Waydroid Development & Testing Setup

The local development host runs **Waydroid** (containerized Android environment), providing a high-performance, hardware-accelerated target for continuous build, install, and verification without requiring standard QEMU emulators or physical Android devices.

### Environment Details
- **ADB Endpoint:** `192.168.240.112:5555` (Waydroid `x86_64`)
- **Android Version:** Android 13 (API Level 33) / LineageOS image
- **mDNS / Local Resolution:** Verified working (`ingenic.local` resolves to `192.168.18.128` directly inside the Android container)

### Common Verification Commands
```bash
# Verify attached device status
adb devices -l

# Build and install directly to Waydroid
./gradlew installDebug

# Stream app logs / socket events
adb -s 192.168.240.112:5555 logcat -s "K17RemoteService" "K17Backend" "K17Widget"

# Launch main activity
adb -s 192.168.240.112:5555 shell am start -n com.quirkies.fiiok17/.ui.MainActivity
```


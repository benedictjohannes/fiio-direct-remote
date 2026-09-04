# FiiO K17 Project Context & Index

This repository contains reverse-engineered protocol documentation and remote control client implementations for the **FiiO K17 DAC** over the local Wi-Fi / LAN network (TCP port `12100`).

---

## 1. Core Documentation & Protocol Reference

- **Protocol Specification:** [`K17Protocol.md`](K17Protocol.md)
  - Reverse-engineered wire protocol reference for TCP port `12100`.
  - Covers discovery (`ingenic.local` / MAC prefix `40:d9:5a`), socket concurrency constraints (single active TCP client policy), volume control commands (`0502...`), status polling (`05010008`), and audio input multiplexing (`0657...`).
  - Contains details regarding transient event prefixes vs JSON state payloads.

---

## 2. Implementations

### Desktop System Tray Controller (Linux / KDE Plasma)
- **Design & Architecture Plan:** [`DesktopPlan.md`](DesktopPlan.md)
- **Source Directory:** `DesktopApp/`
- **Tech Stack:** Python 3, PyQt6 (`QSystemTrayIcon`, popup control card).
- **Features:** Volume slider with 500ms debounce, input mode selector, dynamic SVG tray icons (online/offline status), and on-demand short-lived TCP sockets.

### Android Native Remote App & Widget
- **Design & Architecture Plan:** [`AndroidPlan.md`](AndroidPlan.md)
- **Source Directory:** `android/`
- **Tech Stack:** Kotlin, Jetpack Compose, Jetpack Glance (Home Screen Widget), Material 3.
- **Features:** Direct volume control & hardware volume rocker interception, input switcher, Glance home screen widget (Active / Inactive states with auto-connect), optional foreground media notification with seekbar volume scrubbing, and configurable idle socket disconnect timer (e.g. 10s default) to release device lock.
- **Testing Environment:** Waydroid (`192.168.240.112:5555`, Android 13 `x86_64`) on local host.

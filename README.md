# FiiO Direct Remote Control 

**Currently supports the K17**

The official FiiO Control Android app provides comprehensive control and supports many FiiO devices. I wanted a simpler way to control my device, without waiting for the app to finish its startup checks and navigating through several screens just to reach the K17 controls. Thus, I developed a small app that gives me fast access to K17 volume and input controls from a Linux desktop and Android. This app is built by reverse-engineering the network interaction between the FiiO Control app and the FiiO K17 DAC / Amp over local Wi-Fi / LAN (TCP 12100).

---

## 📸 Screenshots

<p align="center">
  <img src="Screenshot_Android.jpg" alt="Android App & Widget Remote" width="45%" />
  &nbsp;&nbsp;
  <img src="Screenshot_Linux.png" alt="Linux Desktop Tray Controller" width="48%" />
</p>

---

## 🌟 Overview

The **FiiO K17** supports local network control over port `12100` (TCP) and discovery over `224.0.0.255:12101` (UDP). This repository contains:

1. **Protocol Specification:** Documentation of discovered wire opcodes, payload formats for input switching and volume control.
2. **Desktop System Tray (Linux / KDE Plasma):** Lightweight Python/PyQt6 system tray controller with debounced volume control, input switching, and automatic device reconnect. Mouse scrollwheel on the tray icon changes volume. The desktop client separates the platform-independent K17 protocol/networking core from the current KDE Plasma/PyQt6 frontend, making additional desktop frontends possible without duplicating the K17 communication layer.
3. **Android Application & Widget:** Modern Kotlin/Jetpack Compose app with Home Screen Glance widgets, hardware volume rocker control, and quick input switching. On my phone, a cold launch connects to the K17 in about 2 seconds over Wi-Fi. It also provides optional volume control through a Media notification and a home-screen volume control widget. No loading screen on subsequent app opens.

---

## 📑 Repository Structure

- [`K17Protocol.md`](K17Protocol.md) — Reverse-engineered network protocol documentation (UDP discovery, TCP commands, JSON payloads, input multiplexing).
- [`DesktopApp/`](DesktopApp/) — Python 3 & PyQt6 desktop system tray client ([Design Plan](DesktopPlan.md)).
- [`android/`](android/) — Android native app & Glance home screen widget ([Design Plan](AndroidPlan.md)).

---

## 🚀 Getting Started

### Desktop Tray App (Linux only for now)
```bash
cd DesktopApp
pip install PyQt6
python main.py
```

### Android App
The Android app is currently distributed as source code. Open the [`android/`](android/) directory in Android Studio or build with Gradle:
```bash
cd android
./gradlew assembleDebug
```
Prebuilt APK releases and other distribution options may be added if there is sufficient interest.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

import os
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QEvent, pyqtSlot, pyqtProperty, pyqtClassInfo, QObject
from PyQt6.QtDBus import QDBusConnection, QDBusAbstractAdaptor, QDBusInterface
from PyQt6.QtGui import QIcon, QFont, QAction, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QComboBox, QPushButton, QGraphicsDropShadowEffect,
    QMenu, QWidgetAction
)

from k17_backend import K17Backend

ASSETS_DIR = Path(__file__).parent / "assets"
ICON_ONLINE_NAME = "k17_logo_online"
ICON_OFFLINE_NAME = "k17_logo_offline"
ICON_ONLINE_PATH = str(ASSETS_DIR / f"{ICON_ONLINE_NAME}.svg")
ICON_OFFLINE_PATH = str(ASSETS_DIR / f"{ICON_OFFLINE_NAME}.svg")


def send_desktop_notification(summary: str, body: str, icon: str = "dialog-error"):
    try:
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            iface = QDBusInterface(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
                bus
            )
            iface.call("Notify", "FiiO K17 Controller", 0, icon, summary, body, [], {}, 4000)
    except Exception as e:
        print(f"[Notification] Failed to send desktop notification: {e}", flush=True)

INPUT_MODES = [
    ("USB Audio", "0001"),
    ("Optical In", "0002"),
    ("Coaxial In", "0003"),
    ("Line In", "0004"),
    ("Balanced / XLR", "0005"),
    ("Bluetooth", "0006"),
    ("Streaming", "0007")
]


class StatusWorker(QThread):
    finished = pyqtSignal(bool, object)

    def __init__(self, backend: K17Backend):
        super().__init__()
        self.backend = backend

    def run(self):
        success, data = self.backend.fetch_status()
        self.finished.emit(success, data)


class ModeWorker(QThread):
    finished = pyqtSignal(bool)

    def __init__(self, backend: K17Backend, mode_code: str):
        super().__init__()
        self.backend = backend
        self.mode_code = mode_code

    def run(self):
        success = self.backend.set_input_mode(self.mode_code)
        self.finished.emit(success)


class VolumeWorker(QThread):
    finished = pyqtSignal(bool)

    def __init__(self, backend: K17Backend, val: int):
        super().__init__()
        self.backend = backend
        self.val = val

    def run(self):
        success = self.backend.set_volume(self.val)
        self.finished.emit(success)


class K17PopupWindow(QWidget):
    def __init__(self, backend: K17Backend, tray_app):
        super().__init__()
        self.backend = backend
        self.tray_app = tray_app
        self.is_updating_ui = False

        # Standard desktop window with title bar
        self.setObjectName("K17Window")
        self.setWindowTitle("FiiO K17 Controller")
        self.setFixedSize(340, 260)
        self.setWindowFlags(Qt.WindowType.Window)

        # Volume Debounce Timer (500ms)
        self.vol_timer = QTimer(self)
        self.vol_timer.setSingleShot(True)
        self.vol_timer.setInterval(500)
        self.vol_timer.timeout.connect(self._dispatch_volume_change)

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#K17Window {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-family: 'Segoe UI', sans-serif;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #89b4fa;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #b4befe;
                border: none;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #cba6f7;
            }
            QComboBox {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e;
                color: #cdd6f4;
                selection-background-color: #313244;
                border: 1px solid #45475a;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Row
        header_layout = QHBoxLayout()
        title_label = QLabel("FiiO K17", self)
        font = title_label.font()
        font.setPointSize(12)
        font.setBold(True)
        title_label.setFont(font)
        
        self.status_badge = QLabel("OFFLINE", self)
        self.status_badge.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 10px;")

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_badge)
        main_layout.addLayout(header_layout)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #313244; max-height: 1px; border: none;")
        main_layout.addWidget(sep)

        # Volume Controls
        vol_header = QHBoxLayout()
        vol_title = QLabel("Volume", self)
        self.vol_val_label = QLabel("--", self)
        self.vol_val_label.setStyleSheet("color: #89b4fa; font-weight: bold;")
        vol_header.addWidget(vol_title)
        vol_header.addStretch()
        vol_header.addWidget(self.vol_val_label)
        main_layout.addLayout(vol_header)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(0)
        self.vol_slider.valueChanged.connect(self._on_slider_value_changed)
        main_layout.addWidget(self.vol_slider)

        # Input Mode Selection
        mode_header = QHBoxLayout()
        mode_title = QLabel("Input Source", self)
        mode_header.addWidget(mode_title)
        mode_header.addStretch()
        main_layout.addLayout(mode_header)

        self.mode_combo = QComboBox(self)
        for label, code in INPUT_MODES:
            self.mode_combo.addItem(label, code)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_selected)
        main_layout.addWidget(self.mode_combo)

        # Retry / Refresh Button for Offline state
        self.retry_btn = QPushButton("Retry Connection", self)
        self.retry_btn.clicked.connect(lambda: self.tray_app.refresh_status(force_resolve=True))
        main_layout.addWidget(self.retry_btn)

    def set_connecting_state(self):
        self.status_badge.setText("CONNECTING...")
        self.status_badge.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 10px;")

    def _on_slider_value_changed(self, value):
        self.vol_val_label.setText(f"{value}")
        if not self.is_updating_ui:
            self.vol_timer.start()

    def update_volume_display(self, val: int):
        self.is_updating_ui = True
        try:
            self.vol_slider.setValue(val)
            self.vol_val_label.setText(str(val))
        finally:
            self.is_updating_ui = False

    def _dispatch_volume_change(self):
        val = self.vol_slider.value()
        self.tray_app.set_volume(val)

    def _on_mode_selected(self, index):
        if self.is_updating_ui:
            return
        code = self.mode_combo.itemData(index)
        if code:
            self.tray_app.set_input_mode(code)

    def update_state(self, is_online: bool, status_data: dict = None):
        self.is_updating_ui = True
        try:
            if is_online:
                self.status_badge.setText("ONLINE")
                self.status_badge.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 10px;")
                self.vol_slider.setEnabled(True)
                self.mode_combo.setEnabled(True)
                self.retry_btn.setVisible(False)

                if status_data:
                    # Update Volume if available
                    if "currentVolume" in status_data:
                        try:
                            vol = int(status_data["currentVolume"])
                            self.vol_slider.setValue(vol)
                            self.vol_val_label.setText(str(vol))
                        except (ValueError, TypeError):
                            pass

                    # Update Mode if available
                    if "usbAudio" in status_data:
                        mode_str = str(status_data.get("usbAudio", ""))
                        # Map backend status field if present
                        for idx, (_, code) in enumerate(INPUT_MODES):
                            if code == mode_str:
                                self.mode_combo.setCurrentIndex(idx)
                                break
            else:
                self.status_badge.setText("OFFLINE")
                self.status_badge.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 10px;")
                self.vol_slider.setEnabled(False)
                self.mode_combo.setEnabled(False)
                self.vol_val_label.setText("--")
                self.retry_btn.setVisible(True)
        finally:
            self.is_updating_ui = False

    def closeEvent(self, event):
        # Intercept close button to hide to system tray instead of exiting app
        event.ignore()
        self.hide()


@pyqtClassInfo('D-Bus Interface', 'org.kde.StatusNotifierItem')
class StatusNotifierItemKDEAdaptor(QDBusAbstractAdaptor):
    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewMenu = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)

    def __init__(self, parent: 'K17StatusNotifierItem'):
        super().__init__(parent)
        self.sni = parent
        self.setAutoRelaySignals(True)

    @pyqtProperty(str)
    def Category(self):
        return self.sni.category

    @pyqtProperty(str)
    def Id(self):
        return self.sni.id

    @pyqtProperty(str)
    def Title(self):
        return self.sni.title

    @pyqtProperty(str)
    def Status(self):
        return self.sni.status

    @pyqtProperty(int)
    def WindowId(self):
        return 0

    @pyqtProperty(str)
    def IconThemePath(self):
        return self.sni.icon_theme_path

    @pyqtProperty(str)
    def IconName(self):
        return self.sni.icon_name

    @pyqtProperty(str)
    def OverlayIconName(self):
        return ""

    @pyqtProperty(str)
    def AttentionIconName(self):
        return ""

    @pyqtProperty(str)
    def AttentionMovieName(self):
        return ""

    @pyqtProperty(bool)
    def ItemIsMenu(self):
        return False

    @pyqtSlot(int, str)
    def Scroll(self, delta: int, orientation: str):
        self.sni.on_scroll(delta, orientation)

    @pyqtSlot(int, int)
    def Activate(self, x: int, y: int):
        self.sni.on_activate(x, y)

    @pyqtSlot(int, int)
    def ContextMenu(self, x: int, y: int):
        self.sni.on_context_menu(x, y)

    @pyqtSlot(int, int)
    def SecondaryActivate(self, x: int, y: int):
        self.sni.on_secondary_activate(x, y)

    @pyqtSlot(str)
    def ProvideXdgActivationToken(self, token: str):
        pass


@pyqtClassInfo('D-Bus Interface', 'org.freedesktop.StatusNotifierItem')
class StatusNotifierItemFreedesktopAdaptor(QDBusAbstractAdaptor):
    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewMenu = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)

    def __init__(self, parent: 'K17StatusNotifierItem'):
        super().__init__(parent)
        self.sni = parent
        self.setAutoRelaySignals(True)

    @pyqtProperty(str)
    def Category(self):
        return self.sni.category

    @pyqtProperty(str)
    def Id(self):
        return self.sni.id

    @pyqtProperty(str)
    def Title(self):
        return self.sni.title

    @pyqtProperty(str)
    def Status(self):
        return self.sni.status

    @pyqtProperty(int)
    def WindowId(self):
        return 0

    @pyqtProperty(str)
    def IconThemePath(self):
        return self.sni.icon_theme_path

    @pyqtProperty(str)
    def IconName(self):
        return self.sni.icon_name

    @pyqtProperty(str)
    def OverlayIconName(self):
        return ""

    @pyqtProperty(str)
    def AttentionIconName(self):
        return ""

    @pyqtProperty(str)
    def AttentionMovieName(self):
        return ""

    @pyqtProperty(bool)
    def ItemIsMenu(self):
        return False

    @pyqtSlot(int, str)
    def Scroll(self, delta: int, orientation: str):
        self.sni.on_scroll(delta, orientation)

    @pyqtSlot(int, int)
    def Activate(self, x: int, y: int):
        self.sni.on_activate(x, y)

    @pyqtSlot(int, int)
    def ContextMenu(self, x: int, y: int):
        self.sni.on_context_menu(x, y)

    @pyqtSlot(int, int)
    def SecondaryActivate(self, x: int, y: int):
        self.sni.on_secondary_activate(x, y)

    @pyqtSlot(str)
    def ProvideXdgActivationToken(self, token: str):
        pass


class K17StatusNotifierItem(QObject):
    activated = pyqtSignal()
    context_menu_requested = pyqtSignal(int, int)
    scroll_received = pyqtSignal(int, str)

    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewMenu = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)

    def __init__(self, item_id: str = "fiioK17", title: str = "FiiO K17 Controller"):
        super().__init__()
        self.id = item_id
        self.title = title
        self.category = "ApplicationStatus"
        self.status = "Active"
        self.icon_theme_path = str(ASSETS_DIR)
        self.icon_name = ICON_OFFLINE_NAME
        self.tooltip = "FiiO K17 Controller (Offline)"

        self.kde_adaptor = StatusNotifierItemKDEAdaptor(self)
        self.fd_adaptor = StatusNotifierItemFreedesktopAdaptor(self)

        self.bus = QDBusConnection.sessionBus()
        pid = os.getpid()
        self.service_name = f"org.kde.StatusNotifierItem-{pid}-1"
        self.object_path = "/StatusNotifierItem"

        self._register_dbus()

    def _register_dbus(self):
        registered_service = self.bus.registerService(self.service_name)
        registered_obj = self.bus.registerObject(
            self.object_path,
            self,
            QDBusConnection.RegisterOption.ExportAdaptors
        )
        unique_name = self.bus.baseService()
        print(f"[SNI] D-Bus service registered: name={self.service_name} (ok={registered_service}), obj={self.object_path} (ok={registered_obj}), unique_name={unique_name}", flush=True)

        watcher = QDBusInterface(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
            "org.kde.StatusNotifierWatcher",
            self.bus
        )
        reply = watcher.call("RegisterStatusNotifierItem", self.object_path)
        if reply.type() == reply.MessageType.ErrorMessage:
            print(f"[SNI] StatusNotifierWatcher registration error: {reply.errorMessage()}", flush=True)
        else:
            print(f"[SNI] Successfully registered with StatusNotifierWatcher ({self.object_path})", flush=True)

    def set_icon(self, icon_path: str):
        if self.icon_name != icon_path:
            self.icon_name = icon_path
            self.NewIcon.emit()

    def set_tooltip(self, tooltip_text: str):
        if self.tooltip != tooltip_text:
            self.tooltip = tooltip_text
            self.title = tooltip_text
            self.NewToolTip.emit()
            self.NewTitle.emit()

    def on_scroll(self, delta: int, orientation: str):
        print(f"[SNI] Scroll received: delta={delta}, orientation={orientation}", flush=True)
        self.scroll_received.emit(delta, orientation)

    def on_activate(self, x: int, y: int):
        print(f"[SNI] Activate received: x={x}, y={y}", flush=True)
        self.activated.emit()

    def on_context_menu(self, x: int, y: int):
        print(f"[SNI] ContextMenu received: x={x}, y={y}", flush=True)
        self.context_menu_requested.emit(x, y)

    def on_secondary_activate(self, x: int, y: int):
        print(f"[SNI] SecondaryActivate received: x={x}, y={y}", flush=True)
        self.activated.emit()


class K17TrayApp(QObject):
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.backend = K17Backend()

        self.popup = K17PopupWindow(self.backend, self)

        self.pending_volume: Optional[int] = None
        self.scroll_vol_timer = QTimer(self)
        self.scroll_vol_timer.setSingleShot(True)
        self.scroll_vol_timer.setInterval(500)
        self.scroll_vol_timer.timeout.connect(self._dispatch_scroll_volume)

        # Context Menu for Right-Click
        self.menu = QMenu()
        show_action = QAction("Open FiiO K17 Controller", self.menu)
        show_action.triggered.connect(self._show_window)
        self.menu.addAction(show_action)
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

        self.sni = K17StatusNotifierItem()
        self.sni.set_icon(ICON_OFFLINE_NAME)
        self.sni.set_tooltip("FiiO K17 Controller (Offline)")

        self.sni.activated.connect(self._on_sni_activated)
        self.sni.context_menu_requested.connect(self._on_sni_context_menu)
        self.sni.scroll_received.connect(self._on_sni_scroll)

        # Perform initial async status lookup
        self.refresh_status()

    def _show_window(self):
        self.refresh_status(force_resolve=False)
        self.popup.show()
        self.popup.raise_()
        self.popup.activateWindow()

    def _on_sni_activated(self):
        if self.popup.isVisible() and not self.popup.isMinimized():
            self.popup.hide()
        else:
            self._show_window()

    def _on_sni_context_menu(self, x: int, y: int):
        pos = QPoint(x, y) if (x != 0 or y != 0) else QCursor.pos()
        self.menu.popup(pos)

    def _on_sni_scroll(self, delta: int, orientation: str):
        if self.backend.current_volume is None:
            print("[SNI] Scroll refused: current volume is unknown", flush=True)
            return

        if self.pending_volume is None or not self.scroll_vol_timer.isActive():
            self.pending_volume = self.backend.current_volume

        step = 2 if delta > 0 else -2
        self.pending_volume = max(0, min(100, self.pending_volume + step))
        print(f"[SNI] Scroll event applied: step={step}, pending_volume={self.pending_volume}", flush=True)

        self.popup.update_volume_display(self.pending_volume)
        self.scroll_vol_timer.start()

    def _dispatch_scroll_volume(self):
        if self.pending_volume is not None:
            self.set_volume(self.pending_volume)

    def refresh_status(self, force_resolve: bool = False):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.refresh_queued = True
            return

        if force_resolve:
            self.backend.invalidate_cache()

        self.popup.set_connecting_state()

        self.worker = StatusWorker(self.backend)
        self.worker.finished.connect(self._on_status_retrieved)
        self.worker.start()

    def _on_status_retrieved(self, success: bool, data: dict):
        if success:
            self.sni.set_icon(ICON_ONLINE_NAME)
            vol_info = f" - Vol: {self.backend.current_volume}" if self.backend.current_volume is not None else ""
            self.sni.set_tooltip(f"FiiO K17 Controller (Online{vol_info})")
            self.popup.update_state(is_online=True, status_data=data)
            if self.backend.current_volume is not None and not self.scroll_vol_timer.isActive():
                self.pending_volume = self.backend.current_volume
        else:
            self.sni.set_icon(ICON_OFFLINE_NAME)
            self.sni.set_tooltip("FiiO K17 Controller (Offline)")
            self.popup.update_state(is_online=False)
            send_desktop_notification(
                "FiiO K17 Connection Error",
                "Failed to update FiiO K17 device status."
            )

        if getattr(self, "refresh_queued", False):
            self.refresh_queued = False
            QTimer.singleShot(50, lambda: self.refresh_status())

    def set_volume(self, val: int):
        self.vol_worker = VolumeWorker(self.backend, val)
        self.vol_worker.finished.connect(lambda ok: self._on_cmd_finished(ok))
        self.vol_worker.start()

    def set_input_mode(self, mode_code: str):
        self.mode_worker = ModeWorker(self.backend, mode_code)
        self.mode_worker.finished.connect(lambda ok: self._on_cmd_finished(ok))
        self.mode_worker.start()

    def _on_cmd_finished(self, success: bool):
        if success:
            QTimer.singleShot(400, self.refresh_status)
        else:
            self.refresh_status()

    def run(self):
        return self.app.exec()


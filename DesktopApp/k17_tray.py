import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QIcon, QFont, QAction, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QComboBox, QPushButton, QGraphicsDropShadowEffect,
    QSystemTrayIcon, QMenu, QWidgetAction
)

from k17_backend import K17Backend

ASSETS_DIR = Path(__file__).parent / "assets"
ICON_ONLINE_PATH = str(ASSETS_DIR / "k17_logo_online.svg")
ICON_OFFLINE_PATH = str(ASSETS_DIR / "k17_logo_offline.svg")

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
        self.retry_btn.clicked.connect(self.tray_app.refresh_status)
        main_layout.addWidget(self.retry_btn)

    def _on_slider_value_changed(self, value):
        self.vol_val_label.setText(f"{value}")
        if not self.is_updating_ui:
            self.vol_timer.start()

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

        self.is_updating_ui = False

    def closeEvent(self, event):
        # Intercept close button to hide to system tray instead of exiting app
        event.ignore()
        self.hide()


class K17TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.backend = K17Backend()

        self.icon_online = QIcon(ICON_ONLINE_PATH)
        self.icon_offline = QIcon(ICON_OFFLINE_PATH)

        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self.icon_offline)
        self.tray_icon.setToolTip("FiiO K17 Controller (Offline)")

        self.popup = K17PopupWindow(self.backend, self)
        
        # Context Menu for Right-Click
        self.menu = QMenu()
        show_action = QAction("Open FiiO K17 Controller", self.menu)
        show_action.triggered.connect(self._show_window)
        self.menu.addAction(show_action)
        self.tray_icon.setContextMenu(self.menu)

        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # Perform initial async status lookup
        self.refresh_status()

    def _show_window(self):
        self.refresh_status()
        self.popup.show()
        self.popup.raise_()
        self.popup.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.popup.isVisible() and not self.popup.isMinimized():
                self.popup.hide()
            else:
                self._show_window()

    def refresh_status(self):
        self.worker = StatusWorker(self.backend)
        self.worker.finished.connect(self._on_status_retrieved)
        self.worker.start()

    def _on_status_retrieved(self, success: bool, data: dict):
        if success:
            self.tray_icon.setIcon(self.icon_online)
            self.tray_icon.setToolTip("FiiO K17 Controller (Online)")
            self.popup.update_state(is_online=True, status_data=data)
        else:
            self.tray_icon.setIcon(self.icon_offline)
            self.tray_icon.setToolTip("FiiO K17 Controller (Offline)")
            self.popup.update_state(is_online=False)

    def set_volume(self, val: int):
        self.vol_worker = VolumeWorker(self.backend, val)
        self.vol_worker.finished.connect(lambda ok: self._on_cmd_finished(ok))
        self.vol_worker.start()

    def set_input_mode(self, mode_code: str):
        self.mode_worker = ModeWorker(self.backend, mode_code)
        self.mode_worker.finished.connect(lambda ok: self._on_cmd_finished(ok))
        self.mode_worker.start()

    def _on_cmd_finished(self, success: bool):
        if not success:
            self.refresh_status()

    def run(self):
        return self.app.exec()

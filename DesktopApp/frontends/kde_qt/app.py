"""
KDE Plasma / Freedesktop System Tray Application Coordinator.
Wires PyQt6 event loop, SNI tray icon, popup card, and core K17DeviceController.
"""
import sys
from typing import Optional
from PyQt6.QtCore import QObject, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import QApplication, QMenu

from core.controller import K17DeviceController, K17State
from core.constants import InputMode
from .popup_window import K17PopupWindow
from .tray_sni import (
    K17StatusNotifierItem,
    ICON_ONLINE_NAME,
    ICON_OFFLINE_NAME,
)
from .workers import StatusWorker, VolumeWorker, ModeWorker
from .notifications import send_desktop_notification


class K17TrayApp(QObject):
    state_changed = pyqtSignal(object)

    def __init__(self, controller: Optional[K17DeviceController] = None):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.controller = controller or K17DeviceController()
        self.popup = K17PopupWindow(self.controller, self)

        # Scroll wheel volume debounce timer (500ms)
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
        self.sni.set_tooltip("FiiO K17", "Offline")

        self.sni.activated.connect(self._on_sni_activated)
        self.sni.context_menu_requested.connect(self._on_sni_context_menu)
        self.sni.scroll_received.connect(self._on_sni_scroll)

        # Route core state changes through Qt signal to guarantee execution on main GUI thread
        self.state_changed.connect(self._apply_state_change)
        self.controller.add_state_listener(lambda state: self.state_changed.emit(state))

        # Initial status query
        self.refresh_status()

    def _apply_state_change(self, state: K17State):
        """Slot executed on Qt main thread whenever state updates."""
        if state.is_online:
            self.sni.set_icon(ICON_ONLINE_NAME)
            vol_str = f"Volume {state.volume}" if state.volume is not None else "Volume --"
            mode_str = state.input_mode.display_name if state.input_mode else "Unknown"
            self.sni.set_tooltip("FiiO K17", f"{vol_str}, {mode_str}")
        else:
            self.sni.set_icon(ICON_OFFLINE_NAME)
            self.sni.set_tooltip("FiiO K17", "Offline")
        self.popup.update_state(state)

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
        current_vol = self.controller.current_volume
        if current_vol is None:
            print("[SNI] Scroll refused: current volume is unknown", flush=True)
            return

        if self.pending_volume is None or not self.scroll_vol_timer.isActive():
            self.pending_volume = current_vol

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

        self.popup.set_connecting_state()
        self.worker = StatusWorker(self.controller, force_resolve=force_resolve)
        self.worker.finished.connect(self._on_status_retrieved)
        self.worker.start()

    def _on_status_retrieved(self, success: bool, state: K17State):
        if not success:
            send_desktop_notification(
                "FiiO K17 Connection Error",
                "Failed to update FiiO K17 device status.",
            )

        if getattr(self, "refresh_queued", False):
            self.refresh_queued = False
            QTimer.singleShot(50, lambda: self.refresh_status())

    def set_volume(self, val: int):
        self.vol_worker = VolumeWorker(self.controller, val)
        self.vol_worker.finished.connect(self._on_cmd_finished)
        self.vol_worker.start()

    def set_input_mode(self, mode_code: str):
        self.mode_worker = ModeWorker(self.controller, mode_code)
        self.mode_worker.finished.connect(self._on_cmd_finished)
        self.mode_worker.start()

    def _on_cmd_finished(self, success: bool):
        if success:
            QTimer.singleShot(400, self.refresh_status)
        else:
            self.refresh_status()

    def run(self) -> int:
        return self.app.exec()


def main():
    app = K17TrayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()

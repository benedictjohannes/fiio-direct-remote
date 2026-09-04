"""
KDE / Freedesktop StatusNotifierItem (SNI) D-Bus implementation.
Provides system tray icon, tooltips, context menus, and mouse wheel scroll signals.
"""
import os
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, pyqtClassInfo
from PyQt6.QtDBus import QDBusConnection, QDBusAbstractAdaptor, QDBusInterface

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
ICON_ONLINE_NAME = "k17_logo_online"
ICON_OFFLINE_NAME = "k17_logo_offline"
ICON_ONLINE_PATH = str(ASSETS_DIR / f"{ICON_ONLINE_NAME}.svg")
ICON_OFFLINE_PATH = str(ASSETS_DIR / f"{ICON_OFFLINE_NAME}.svg")


@pyqtClassInfo("D-Bus Interface", "org.kde.StatusNotifierItem")
class StatusNotifierItemKDEAdaptor(QDBusAbstractAdaptor):
    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewMenu = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)

    def __init__(self, parent: "K17StatusNotifierItem"):
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


@pyqtClassInfo("D-Bus Interface", "org.freedesktop.StatusNotifierItem")
class StatusNotifierItemFreedesktopAdaptor(QDBusAbstractAdaptor):
    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewMenu = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)

    def __init__(self, parent: "K17StatusNotifierItem"):
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
            QDBusConnection.RegisterOption.ExportAdaptors,
        )
        unique_name = self.bus.baseService()
        print(
            f"[SNI] D-Bus service registered: name={self.service_name} (ok={registered_service}), obj={self.object_path} (ok={registered_obj}), unique_name={unique_name}",
            flush=True,
        )

        watcher = QDBusInterface(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
            "org.kde.StatusNotifierWatcher",
            self.bus,
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

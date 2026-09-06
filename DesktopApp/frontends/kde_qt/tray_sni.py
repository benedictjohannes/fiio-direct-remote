"""
KDE / Freedesktop StatusNotifierItem (SNI) D-Bus implementation.
Provides system tray icon, full (sa(iiay)ss) tooltips, context menus, and mouse wheel scroll signals.
Uses dbus-python with PyQt6 main loop to properly export composite D-Bus structs.
"""
import os

import dbus
import dbus.service
import dbus.mainloop.pyqt6 # type: ignore # no lsp support for this module
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QRectF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QGuiApplication, QPalette

# Ensure dbus uses the PyQt6 event loop
dbus.mainloop.pyqt6.DBusQtMainLoop(set_as_default=True)

KDE_SNI_IFACE = "org.kde.StatusNotifierItem"
FD_SNI_IFACE = "org.freedesktop.StatusNotifierItem"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def is_system_dark_theme() -> bool:
    """Detects whether system theme is dark or light."""
    app = QGuiApplication.instance()
    if app is not None:
        hints = app.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return False
            if scheme == Qt.ColorScheme.Dark:
                return True
        # Fallback to checking WindowText lightness in palette
        return app.palette().color(QPalette.ColorRole.WindowText).lightness() > 128
    return True


def render_dynamic_icon_pixmap(
    online: bool,
    volume: int | None = None,
    connecting: bool = False,
    dot_count: int = 3,
    size: int = 48,
    dark_mode: bool | None = None,
) -> bytes:
    """
    Renders dynamic 2-row badge into ARGB32 network-byte-order bytes for SNI:
      Row 1: 'FiiO' (Green if online, Amber if connecting, Red if offline)
      Row 2: Volume number, pulsing dots if connecting ('.', '..', '...'), or 'OFF'
    Adapts text contrast based on system dark/light theme.
    """
    if dark_mode is None:
        dark_mode = is_system_dark_theme()

    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)  # Transparent

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # Color palette adapted for dark vs light themes
    if connecting:
        top_color = QColor("#D4AC0D") if not dark_mode else QColor("#F1C40F")
        bot_color = top_color
        bot_text = "." * max(1, min(3, dot_count))
    elif online:
        top_color = QColor("#229954") if not dark_mode else QColor("#2ECC71")
        bot_color = QColor("#1E1E2E") if not dark_mode else QColor("#FFFFFF")
        bot_text = f"{volume}" if volume is not None else "--"
    else:
        top_color = QColor("#C0392B") if not dark_mode else QColor("#E74C3C")
        bot_color = top_color
        bot_text = "OFF"

    # Top line: 'FiiO' (top 38% of canvas)
    top_rect = QRectF(0, 0, size, size * 0.38)
    top_font = QFont("sans-serif", weight=QFont.Weight.Black)
    top_font.setPixelSize(int(size * 0.32))
    p.setFont(top_font)
    p.setPen(top_color)
    p.drawText(top_rect, Qt.AlignmentFlag.AlignCenter, "FiiO")

    # Bottom line: volume number, dots, or 'OFF' (bottom 62% of canvas)
    bot_rect = QRectF(0, size * 0.38, size, size * 0.62)
    bot_font = QFont("sans-serif", weight=QFont.Weight.Bold)
    if connecting:
        bot_font.setPixelSize(int(size * 0.55))
    elif len(bot_text) >= 3:
        bot_font.setPixelSize(int(size * 0.46))
    else:
        bot_font.setPixelSize(int(size * 0.58))

    p.setFont(bot_font)
    p.setPen(bot_color)
    p.drawText(bot_rect, Qt.AlignmentFlag.AlignCenter, bot_text)
    p.end()

    conv = img.convertToFormat(QImage.Format.Format_ARGB32)
    ptr = conv.bits()
    ptr.setsize(conv.sizeInBytes())
    raw = bytes(ptr)

    # Convert little-endian ARGB32 (B, G, R, A) to SNI big-endian network byte order (A, R, G, B)
    ba = bytearray(len(raw))
    ba[0::4] = raw[3::4]  # Alpha
    ba[1::4] = raw[2::4]  # Red
    ba[2::4] = raw[1::4]  # Green
    ba[3::4] = raw[0::4]  # Blue
    return bytes(ba)


class _DBusSNIObject(dbus.service.Object):
    """
    Exported D-Bus Object implementing org.kde.StatusNotifierItem and
    org.freedesktop.StatusNotifierItem with proper (sa(iiay)ss) ToolTip struct.
    """

    def __init__(self, parent_sni: "K17StatusNotifierItem", bus_name: dbus.service.BusName, object_path: str):
        super().__init__(bus_name, object_path)
        self.sni = parent_sni

    # --- Properties Interface ---
    @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface_name: str, property_name: str):
        if interface_name not in (KDE_SNI_IFACE, FD_SNI_IFACE):
            raise dbus.exceptions.DBusException(f"Unknown interface {interface_name}")

        if property_name == "Category":
            return dbus.String(self.sni.category)
        elif property_name == "Id":
            return dbus.String(self.sni.id)
        elif property_name == "Title":
            return dbus.String(self.sni.title)
        elif property_name == "Status":
            return dbus.String(self.sni.status)
        elif property_name == "WindowId":
            return dbus.Int32(0)
        elif property_name == "IconThemePath":
            return dbus.String(self.sni.icon_theme_path)
        elif property_name == "IconName":
            return dbus.String(self.sni.icon_name)
        elif property_name == "IconPixmap":
            if self.sni.icon_pixmap_data:
                w, h, data = self.sni.icon_pixmap_data
                pix_struct = dbus.Struct((w, h, dbus.ByteArray(data)), signature="(iiay)")
                return dbus.Array([pix_struct], signature="(iiay)")
            return dbus.Array([], signature="(iiay)")
        elif property_name == "OverlayIconName":
            return dbus.String("")
        elif property_name == "OverlayIconPixmap":
            return dbus.Array([], signature="(iiay)")
        elif property_name == "AttentionIconName":
            return dbus.String("")
        elif property_name == "AttentionIconPixmap":
            return dbus.Array([], signature="(iiay)")
        elif property_name == "AttentionMovieName":
            return dbus.String("")
        elif property_name == "ItemIsMenu":
            return dbus.Boolean(False)
        elif property_name == "Menu":
            return dbus.ObjectPath("/NO_DBUS_MENU")
        elif property_name == "ToolTip":
            # Signature: (sa(iiay)ss) -> (icon_name, icon_pixmaps, title, subtitle)
            pixmaps = dbus.Array([], signature="(iiay)")
            return dbus.Struct(
                (self.sni.icon_name, pixmaps, self.sni.tooltip_title, self.sni.tooltip_sub),
                signature="sa(iiay)ss",
            )
        else:
            raise dbus.exceptions.DBusException(f"Unknown property {property_name}")

    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface_name: str):
        if interface_name not in (KDE_SNI_IFACE, FD_SNI_IFACE):
            return dbus.Dictionary({}, signature="sv")

        if self.sni.icon_pixmap_data:
            w, h, data = self.sni.icon_pixmap_data
            pix_struct = dbus.Struct((w, h, dbus.ByteArray(data)), signature="(iiay)")
            pixmaps = dbus.Array([pix_struct], signature="(iiay)")
        else:
            pixmaps = dbus.Array([], signature="(iiay)")

        return dbus.Dictionary(
            {
                "Category": dbus.String(self.sni.category),
                "Id": dbus.String(self.sni.id),
                "Title": dbus.String(self.sni.title),
                "Status": dbus.String(self.sni.status),
                "WindowId": dbus.Int32(0),
                "IconThemePath": dbus.String(self.sni.icon_theme_path),
                "IconName": dbus.String(self.sni.icon_name),
                "IconPixmap": pixmaps,
                "OverlayIconName": dbus.String(""),
                "OverlayIconPixmap": dbus.Array([], signature="(iiay)"),
                "AttentionIconName": dbus.String(""),
                "AttentionIconPixmap": dbus.Array([], signature="(iiay)"),
                "AttentionMovieName": dbus.String(""),
                "ItemIsMenu": dbus.Boolean(False),
                "Menu": dbus.ObjectPath("/NO_DBUS_MENU"),
                "ToolTip": dbus.Struct(
                    (self.sni.icon_name, dbus.Array([], signature="(iiay)"), self.sni.tooltip_title, self.sni.tooltip_sub),
                    signature="sa(iiay)ss",
                ),
            },
            signature="sv",
        )

    # --- Methods ---
    @dbus.service.method(KDE_SNI_IFACE, in_signature="is")
    def Scroll(self, delta: int, orientation: str):
        self.sni.on_scroll(delta, orientation)

    @dbus.service.method(KDE_SNI_IFACE, in_signature="ii")
    def Activate(self, x: int, y: int):
        self.sni.on_activate(x, y)

    @dbus.service.method(KDE_SNI_IFACE, in_signature="ii")
    def ContextMenu(self, x: int, y: int):
        self.sni.on_context_menu(x, y)

    @dbus.service.method(KDE_SNI_IFACE, in_signature="ii")
    def SecondaryActivate(self, x: int, y: int):
        self.sni.on_secondary_activate(x, y)

    @dbus.service.method(KDE_SNI_IFACE, in_signature="s")
    def ProvideXdgActivationToken(self, token: str):
        pass

    # --- Freedesktop aliases for methods ---
    @dbus.service.method(FD_SNI_IFACE, in_signature="is")
    def ScrollFD(self, delta: int, orientation: str):
        self.sni.on_scroll(delta, orientation)

    @dbus.service.method(FD_SNI_IFACE, in_signature="ii")
    def ActivateFD(self, x: int, y: int):
        self.sni.on_activate(x, y)

    @dbus.service.method(FD_SNI_IFACE, in_signature="ii")
    def ContextMenuFD(self, x: int, y: int):
        self.sni.on_context_menu(x, y)

    @dbus.service.method(FD_SNI_IFACE, in_signature="ii")
    def SecondaryActivateFD(self, x: int, y: int):
        self.sni.on_secondary_activate(x, y)

    @dbus.service.method(FD_SNI_IFACE, in_signature="s")
    def ProvideXdgActivationTokenFD(self, token: str):
        pass

    # --- Signals ---
    @dbus.service.signal(KDE_SNI_IFACE)
    def NewTitle(self):
        pass

    @dbus.service.signal(KDE_SNI_IFACE)
    def NewIcon(self):
        pass

    @dbus.service.signal(KDE_SNI_IFACE)
    def NewAttentionIcon(self):
        pass

    @dbus.service.signal(KDE_SNI_IFACE)
    def NewOverlayIcon(self):
        pass

    @dbus.service.signal(KDE_SNI_IFACE)
    def NewMenu(self):
        pass

    @dbus.service.signal(KDE_SNI_IFACE)
    def NewToolTip(self):
        pass

    @dbus.service.signal(KDE_SNI_IFACE, signature="s")
    def NewStatus(self, status: str):
        pass


class K17StatusNotifierItem(QObject):
    """
    PyQt6 coordinator for the StatusNotifierItem D-Bus service.
    """
    activated = pyqtSignal()
    context_menu_requested = pyqtSignal(int, int)
    scroll_received = pyqtSignal(int, str)

    def __init__(self, item_id: str = "fiioK17", title: str = "FiiO K17"):
        super().__init__()
        self.id = item_id
        self.title = title
        self.category = "ApplicationStatus"
        self.status = "Active"
        self.icon_theme_path = ""
        self.icon_name = ""
        self.icon_pixmap_data: tuple[int, int, bytes] | None = None

        self.tooltip_title = title
        self.tooltip_sub = "Offline"

        # Initialize with offline badge
        self._current_online: bool | None = None
        self._current_volume: int | None = None
        self._is_connecting: bool = False
        self._dot_count: int = 1

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(350)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        # Re-render icon if user changes between light and dark desktop themes
        app = QGuiApplication.instance()
        if app is not None and hasattr(app.styleHints(), "colorSchemeChanged"):
            app.styleHints().colorSchemeChanged.connect(self._on_theme_changed)

        self.set_dynamic_status(online=False, volume=None)

        self.bus = dbus.SessionBus()
        pid = os.getpid()
        self.service_name = f"org.kde.StatusNotifierItem-{pid}-1"
        self.object_path = "/StatusNotifierItem"

        self.bus_name = dbus.service.BusName(self.service_name, self.bus)
        self.dbus_obj = _DBusSNIObject(self, self.bus_name, self.object_path)

        self._register_with_watcher()

    def _register_with_watcher(self):
        try:
            watcher = self.bus.get_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
            watcher_iface = dbus.Interface(watcher, "org.kde.StatusNotifierWatcher")
            watcher_iface.RegisterStatusNotifierItem(self.object_path)
            print(
                f"[SNI] Successfully registered with StatusNotifierWatcher: {self.service_name} at {self.object_path}",
                flush=True,
            )
        except Exception as e:
            print(f"[SNI] StatusNotifierWatcher registration error: {e}", flush=True)

    def set_connecting(self):
        """Puts the SNI icon into an animated amber connecting state (. -> .. -> ...)."""
        if self._is_connecting:
            return
        self._is_connecting = True
        self._dot_count = 1
        self._current_online = None
        self._current_volume = None
        self._render_connecting_frame()
        self._anim_timer.start()

    def _on_anim_tick(self):
        if not self._is_connecting:
            self._anim_timer.stop()
            return
        self._dot_count = (self._dot_count % 3) + 1
        self._render_connecting_frame()

    def _render_connecting_frame(self):
        size = 48
        raw_bytes = render_dynamic_icon_pixmap(
            online=False,
            volume=None,
            connecting=True,
            dot_count=self._dot_count,
            size=size,
        )
        self.icon_pixmap_data = (size, size, raw_bytes)
        self.icon_name = ""
        if hasattr(self, "dbus_obj"):
            self.dbus_obj.NewIcon()

    def _on_theme_changed(self):
        """Re-renders the icon with adjusted contrast when the system theme changes."""
        if self._is_connecting:
            self._render_connecting_frame()
        elif self._current_online is not None:
            # Force refresh by resetting cached state
            online, vol = self._current_online, self._current_volume
            self.icon_pixmap_data = None
            self.set_dynamic_status(online=online, volume=vol)

    def set_dynamic_status(self, online: bool, volume: int | None = None):
        """
        Updates the tray icon with a dynamically rendered 2-row badge:
          Row 1: 'FiiO' (Green if online, Red if offline)
          Row 2: Volume number or 'OFF'
        """
        if self._is_connecting:
            self._is_connecting = False
            self._anim_timer.stop()

        if self._current_online == online and self._current_volume == volume and self.icon_pixmap_data is not None:
            return

        self._current_online = online
        self._current_volume = volume

        size = 48
        raw_bytes = render_dynamic_icon_pixmap(online=online, volume=volume, size=size)
        self.icon_pixmap_data = (size, size, raw_bytes)
        self.icon_name = ""  # Prefer IconPixmap when dynamic

        if hasattr(self, "dbus_obj"):
            self.dbus_obj.NewIcon()

    def set_icon(self, icon_name: str):
        self.icon_pixmap_data = None
        if self.icon_name != icon_name:
            self.icon_name = icon_name
            self.dbus_obj.NewIcon()

    def set_tooltip(self, title: str, subtitle: str):
        changed = False
        if self.tooltip_title != title or self.tooltip_sub != subtitle:
            self.tooltip_title = title
            self.tooltip_sub = subtitle
            self.title = f"{title} ({subtitle})" if subtitle else title
            changed = True

        if changed:
            self.dbus_obj.NewToolTip()
            self.dbus_obj.NewTitle()

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


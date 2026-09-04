"""
Desktop notification helper using D-Bus (org.freedesktop.Notifications).
"""
from PyQt6.QtDBus import QDBusConnection, QDBusInterface


def send_desktop_notification(summary: str, body: str, icon: str = "dialog-error"):
    """
    Sends a freedesktop notification via session D-Bus.
    """
    try:
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            iface = QDBusInterface(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
                bus,
            )
            iface.call("Notify", "FiiO K17 Controller", 0, icon, summary, body, [], {}, 4000)
    except Exception as e:
        print(f"[Notification] Failed to send desktop notification: {e}", flush=True)

#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure DesktopApp root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

def get_app():
    """Factory to instantiate the appropriate frontend for the current OS."""
    match sys.platform:
        case p if p.startswith("linux"):
            missing_deps = []
            try:
                import PyQt6  # noqa: F401
            except ImportError:
                missing_deps.append("PyQt6")

            try:
                import dbus  # noqa: F401
                import dbus.mainloop.pyqt6  # noqa: F401 # type: ignore
            except ImportError:
                missing_deps.append("dbus-python")

            if missing_deps:
                deps_str = ", ".join(missing_deps)
                raise RuntimeError(
                    f"Missing required Python dependencies: {deps_str}\n"
                    f"Please install them via your distribution's package manager or run desktop-app/install_linux.sh"
                )

            from frontends.kde_qt.app import K17TrayApp

            return K17TrayApp()
        case _:
            raise NotImplementedError(
                f"Unsupported operating system '{sys.platform}'.\n"
                f"This desktop tray app is currently only developed and tested on Linux (KDE / Qt 6)."
            )


def main():
    try:
        app = get_app()
        sys.exit(app.run())
    except (NotImplementedError, RuntimeError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


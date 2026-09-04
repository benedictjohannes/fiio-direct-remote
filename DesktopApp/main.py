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
    except NotImplementedError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


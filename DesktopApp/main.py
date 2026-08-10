#!/usr/bin/env python3
import sys
from k17_tray import K17TrayApp

def main():
    app = K17TrayApp()
    sys.exit(app.run())

if __name__ == "__main__":
    main()

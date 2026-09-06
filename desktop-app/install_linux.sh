#!/usr/bin/env bash
#
# FiiO Direct Remote Desktop Tray Installer for Linux (KDE Plasma / Qt 6)
# Supports local repo execution and piped curl execution:
#   curl -fsSL https://raw.githubusercontent.com/benedictjohannes/fiio-direct-remote/master/desktop-app/install_linux.sh | bash
#

set -e

REPO_OWNER="benedictjohannes"
REPO_NAME="fiio-direct-remote"
GITHUB_REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"
INSTALL_DIR="${HOME}/.local/share/fiio-direct-remote"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
AUTOSTART_DIR="${HOME}/.config/autostart"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="fiio-direct-remote.service"

AUTO_CONFIRM=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        -y|--yes)
            AUTO_CONFIRM=1
            ;;
        --uninstall)
            UNINSTALL=1
            ;;
        *)
            ;;
    esac
done

echo "========================================================"
echo "    FiiO Direct Remote Desktop Tray Installer (Linux)   "
echo "========================================================"

# ----------------------------------------------------
# 0. UNINSTALL HANDLER
# ----------------------------------------------------
if [ "$UNINSTALL" -eq 1 ]; then
    echo ">> Removing FiiO Direct Remote desktop tray installation..."

    # Stop & disable systemd service if active
    if command -v systemctl >/dev/null 2>&1; then
        for svc in "$SERVICE_NAME" "fiio-k17.service"; do
            if systemctl --user is-active --quiet "$svc" 2>/dev/null; then
                echo "Stopping systemd user service ($svc)..."
                systemctl --user stop "$svc" || true
            fi
            if systemctl --user is-enabled --quiet "$svc" 2>/dev/null; then
                echo "Disabling systemd user service ($svc)..."
                systemctl --user disable "$svc" || true
            fi
            rm -f "${SYSTEMD_USER_DIR}/${svc}"
        done
        systemctl --user daemon-reload || true
    fi

    # Remove autostart desktop files
    rm -f "${AUTOSTART_DIR}/fiio-direct-remote.desktop"
    rm -f "${AUTOSTART_DIR}/fiio-k17.desktop"

    # Remove main desktop entries
    rm -f "${DESKTOP_DIR}/fiio-direct-remote.desktop"
    rm -f "${DESKTOP_DIR}/fiio-k17.desktop"

    # Remove binary wrapper
    rm -f "${BIN_DIR}/fiio-tray"

    # Remove icons
    rm -f "${ICON_DIR}/fiio-direct-remote.svg"
    rm -f "${ICON_DIR}/fiio-k17.svg"

    # Remove installed files
    for dir in "$INSTALL_DIR" "${HOME}/.local/share/fiio-k17"; do
        if [ -d "$dir" ]; then
            echo "Removing $dir..."
            rm -rf "$dir"
        fi
    done

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi

    echo ">> Successfully uninstalled FiiO Direct Remote."
    exit 0
fi

# ----------------------------------------------------
# 1. PYTHON DEPENDENCY VERIFICATION
# ----------------------------------------------------
echo ""
echo "[1/4] Checking Python dependencies (PyQt6, dbus-python)..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is not installed on this system." >&2
    exit 1
fi

CHECK_SCRIPT="import PyQt6, dbus, dbus.mainloop.pyqt6; print('OK')"
if python3 -c "$CHECK_SCRIPT" >/dev/null 2>&1; then
    echo "  Dependencies PyQt6 and dbus-python found."
else
    echo "  Missing dependencies: PyQt6 or dbus-python."
    echo ""
    echo "  Please install them using your distribution package manager:"
    if command -v pacman >/dev/null 2>&1; then
        echo "    sudo pacman -S python-pyqt6 python-dbus"
    elif command -v apt >/dev/null 2>&1; then
        echo "    sudo apt install python3-pyqt6 python3-dbus"
    elif command -v dnf >/dev/null 2>&1; then
        echo "    sudo dnf install python3-qt6 python3-dbus"
    elif command -v zypper >/dev/null 2>&1; then
        echo "    sudo zypper install python3-qt6 python3-dbus-python"
    else
        echo "    pip install --user PyQt6 dbus-python"
    fi
    echo ""
    if [ "$AUTO_CONFIRM" -eq 0 ]; then
        read -r -p "Continue anyway? [y/N]: " continue_resp
        if [[ ! "$continue_resp" =~ ^[Yy]$ ]]; then
            echo "Installation aborted. Please install dependencies and rerun."
            exit 1
        fi
    fi
fi

# ----------------------------------------------------
# 2. SOURCE DETERMINATION (Local clone vs Remote tarball)
# ----------------------------------------------------
echo ""
echo "[2/4] Setting up application files..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"

if [ -n "$SCRIPT_DIR" ] && [ -f "${SCRIPT_DIR}/main.py" ] && [ -d "${SCRIPT_DIR}/core" ]; then
    APP_RUN_DIR="$SCRIPT_DIR"
    echo "  Running from local repository at: $APP_RUN_DIR"
else
    mkdir -p "$INSTALL_DIR"
    TARBALL_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/latest/download/fiio-direct-remote-linux-qt6.tar.gz"
    FALLBACK_ARCHIVE="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/master.tar.gz"

    echo "  Downloading latest release package..."
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT

    DOWNLOAD_OK=0
    if curl -sLf "$TARBALL_URL" -o "${TMP_DIR}/package.tar.gz" 2>/dev/null; then
        DOWNLOAD_OK=1
        tar -xzf "${TMP_DIR}/package.tar.gz" -C "$INSTALL_DIR" --strip-components=1 2>/dev/null || tar -xzf "${TMP_DIR}/package.tar.gz" -C "$INSTALL_DIR"
    elif curl -sLf "$FALLBACK_ARCHIVE" -o "${TMP_DIR}/archive.tar.gz" 2>/dev/null; then
        DOWNLOAD_OK=1
        echo "  (Using master repository archive fallback)"
        tar -xzf "${TMP_DIR}/archive.tar.gz" -C "${TMP_DIR}"
        cp -r "${TMP_DIR}/${REPO_NAME}-master/desktop-app/"* "$INSTALL_DIR/"
    fi

    if [ "$DOWNLOAD_OK" -ne 1 ]; then
        echo "Error: Failed to download release archive from GitHub." >&2
        exit 1
    fi

    APP_RUN_DIR="$INSTALL_DIR"
    echo "  Installed files to: $APP_RUN_DIR"
fi

# ----------------------------------------------------
# 3. INSTALL BINARY WRAPPER, ICON & DESKTOP FILE
# ----------------------------------------------------
echo ""
echo "[3/4] Installing launcher and desktop integration..."

mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# Install icon
ICON_SRC="${APP_RUN_DIR}/assets/logo.svg"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "${ICON_DIR}/fiio-direct-remote.svg"
    echo "  Installed icon: ${ICON_DIR}/fiio-direct-remote.svg"
fi

# Install CLI wrapper
PYTHON_EXEC="$(command -v python3)"
cat <<LAUNCHER > "${BIN_DIR}/fiio-tray"
#!/usr/bin/env bash
exec "${PYTHON_EXEC}" "${APP_RUN_DIR}/main.py" "\$@"
LAUNCHER
chmod +x "${BIN_DIR}/fiio-tray"
echo "  Installed CLI wrapper: ${BIN_DIR}/fiio-tray"

# Install .desktop file
cat <<DESKTOP > "${DESKTOP_DIR}/fiio-direct-remote.desktop"
[Desktop Entry]
Name=FiiO Direct Remote
GenericName=Audio DAC Remote Controller
Comment=Direct network remote control for FiiO DACs (K17 and compatible)
Exec=${BIN_DIR}/fiio-tray
Icon=fiio-direct-remote
Terminal=false
Type=Application
Categories=AudioVideo;Audio;AudioVideoEditing;
StartupNotify=false
DESKTOP
echo "  Installed desktop entry: ${DESKTOP_DIR}/fiio-direct-remote.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

# ----------------------------------------------------
# 4. AUTOSTART CONFIGURATION
# ----------------------------------------------------
echo ""
echo "[4/4] Configuring Autostart on login..."

CHOICE=1
if [ "$AUTO_CONFIRM" -eq 0 ]; then
    echo "How would you like FiiO Direct Remote to start on login?"
    echo "  1) XDG Autostart (.desktop in ~/.config/autostart) [Recommended]"
    echo "  2) systemd --user service (auto-restart on crash, journalctl logs)"
    echo "  3) Manual only (do not autostart)"
    read -r -p "Select option [1-3, default: 1]: " user_choice </dev/tty || user_choice=""
    if [[ "$user_choice" =~ ^[1-3]$ ]]; then
        CHOICE="$user_choice"
    fi
fi

case "$CHOICE" in
    1)
        mkdir -p "$AUTOSTART_DIR"
        cp "${DESKTOP_DIR}/fiio-direct-remote.desktop" "${AUTOSTART_DIR}/fiio-direct-remote.desktop"
        echo "  Enabled XDG Autostart at: ${AUTOSTART_DIR}/fiio-direct-remote.desktop"
        ;;
    2)
        mkdir -p "$SYSTEMD_USER_DIR"
        cat <<SERVICE > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
[Unit]
Description=FiiO Direct Remote System Tray Controller
After=graphical-session.target
BindsTo=graphical-session.target

[Service]
Type=exec
ExecStart=${PYTHON_EXEC} ${APP_RUN_DIR}/main.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
SERVICE
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --user daemon-reload
            systemctl --user enable "$SERVICE_NAME"
            echo "  Enabled systemd --user service: ${SERVICE_NAME}"
            echo "  Starting service now..."
            systemctl --user start "$SERVICE_NAME" || true
        else
            echo "  systemctl not found. Service file written to ${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
        fi
        ;;
    3)
        echo "  Autostart skipped. You can launch manually via 'fiio-tray' or Application Menu."
        ;;
esac

echo ""
echo "========================================================"
echo "          Installation Complete! 🎉                     "
echo "========================================================"
echo "You can now launch the app via:"
echo "  - Terminal: fiio-tray"
echo "  - Application Menu: 'FiiO Direct Remote'"
echo "To uninstall later, simply run:"
echo "  ${APP_RUN_DIR}/install_linux.sh --uninstall"
echo "========================================================"

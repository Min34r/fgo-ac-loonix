#!/usr/bin/env bash
# ==============================================================================
# Fate/Grand Order Arcade - Linux Overlay Setup & Installer
# Attaches the native Linux launcher and server runtime onto Cloud23333's FGOA rip.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR=""
DO_CHECK=0
INSTALL_DESKTOP=0

INSTALL_APP=0

show_help() {
    cat <<EOF
Usage: ./install.sh [OPTIONS] [TARGET_FGOA_DIR]

Options:
  --app          Install the launcher as a standalone desktop app to ~/.local/share/fgoa-launcher.
  --check        Check system prerequisites and target directory without making changes.
  --desktop      Install a desktop menu shortcut (~/.local/share/applications/fgo-arcade.desktop).
  -h, --help     Show this help message.

Examples:
  # Install as standalone app into user profile
  ./install.sh --app

  # Install into extracted Cloud FGOA rip folder
  ./install.sh /home/user/Games/FGOA

  # Check prerequisites only
  ./install.sh --check /home/user/Games/FGOA
EOF
}

# Parse options
for arg in "$@"; do
    case "$arg" in
        --app)
            INSTALL_APP=1
            ;;
        --check)
            DO_CHECK=1
            ;;
        --desktop)
            INSTALL_DESKTOP=1
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            if [ -z "$TARGET_DIR" ]; then
                TARGET_DIR="$arg"
            fi
            ;;
    esac
done

install_standalone_app() {
    local install_root="${XDG_DATA_HOME:-$HOME/.local/share}/fgoa-launcher"
    local bin_dir="${HOME}/.local/bin"
    local apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    local icons_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"

    echo "============================================================"
    echo " Fate/Grand Order Arcade - Standalone Desktop App Setup"
    echo "============================================================"
    echo "Installing launcher package to: ${install_root}"
    mkdir -p "${install_root}" "${bin_dir}" "${apps_dir}" "${icons_dir}"

    cp -r "${SCRIPT_DIR}/launcher" "${install_root}/"
    cp -r "${SCRIPT_DIR}/scripts" "${install_root}/"
    cp -r "${SCRIPT_DIR}/deck-loadouts" "${install_root}/"
    cp -r "${SCRIPT_DIR}/assets" "${install_root}/"
    cp "${SCRIPT_DIR}/FGO_Launcher.sh" "${install_root}/"
    cp "${SCRIPT_DIR}/install.sh" "${install_root}/"
    cp "${SCRIPT_DIR}/requirements.txt" "${install_root}/"
    chmod +x "${install_root}/FGO_Launcher.sh" "${install_root}/install.sh" "${install_root}/scripts/"*.sh 2>/dev/null || true

    cat << 'EOF' > "${bin_dir}/fgo-launcher"
#!/usr/bin/env bash
SCRIPT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fgoa-launcher"
exec "${SCRIPT_DIR}/FGO_Launcher.sh" "$@"
EOF
    chmod +x "${bin_dir}/fgo-launcher"

    if [ -f "${SCRIPT_DIR}/launcher/assets/platform.png" ]; then
        cp "${SCRIPT_DIR}/launcher/assets/platform.png" "${icons_dir}/fgo-arcade.png"
    fi

    cat << EOF > "${apps_dir}/fgo-arcade.desktop"
[Desktop Entry]
Type=Application
Name=Fate/Grand Order Arcade
Comment=Native Linux Launcher for Fate/Grand Order Arcade
Exec=${bin_dir}/fgo-launcher
Icon=fgo-arcade
Terminal=false
Categories=Game;ArcadeGame;
StartupNotify=true
EOF
    chmod +x "${apps_dir}/fgo-arcade.desktop"

    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${apps_dir}" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true

    echo ""
    echo "[OK] Installed Fate/Grand Order Arcade Launcher successfully!"
    echo "  Command: ${bin_dir}/fgo-launcher"
    echo "  Desktop entry: ${apps_dir}/fgo-arcade.desktop"
    echo ""
    echo "Launch the app from your application menu or run 'fgo-launcher' in a terminal."
    echo "On first start, the app will ask you to select your game folder or install from game rip archives."
    exit 0
}

# If standalone app install is requested
if [ "$INSTALL_APP" -eq 1 ]; then
    install_standalone_app
fi

# If target dir is omitted, check PWD, SCRIPT_DIR, or parent directory for FGOA root
if [ -z "$TARGET_DIR" ]; then
    if [ -f "${PWD}/App/ago.exe" ] || [ -d "${PWD}/App" ]; then
        TARGET_DIR="${PWD}"
    elif [ -f "${SCRIPT_DIR}/App/ago.exe" ]; then
        TARGET_DIR="${SCRIPT_DIR}"
    elif [ -f "${SCRIPT_DIR}/../App/ago.exe" ]; then
        TARGET_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
    elif [ "${SCRIPT_DIR}" = "/opt/fgoa-launcher" ] || [ "${SCRIPT_DIR}" = "${XDG_DATA_HOME:-$HOME/.local/share}/fgoa-launcher" ]; then
        echo "[FAIL] No target FGOA directory specified and current directory (${PWD}) does not contain App/ago.exe."
        echo "Usage: fgo-launcher (to launch the app GUI) or ./install.sh /path/to/FGOA"
        exit 1
    else
        # Running from standalone clone with no args -> default to installing the desktop app
        install_standalone_app
    fi
fi

TARGET_DIR="$(cd "${TARGET_DIR}" 2>/dev/null && pwd || echo "${TARGET_DIR}")"

echo "============================================================"
echo " Fate/Grand Order Arcade - Linux Launcher Overlay Setup"
echo "============================================================"
echo "Source Directory: ${SCRIPT_DIR}"
echo "Target Directory: ${TARGET_DIR}"
echo ""

# ------------------------------------------------------------------------------
# 1. Check System Dependencies
# ------------------------------------------------------------------------------
echo "[1/5] Checking System Dependencies..."

MISSING_DEPS=()

# Python 3
if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
    echo "  [OK] Python 3 found (${PY_VER})"
else
    echo "  [FAIL] Python 3 is not installed!"
    MISSING_DEPS+=("python3")
fi

# PyQt6
if python3 -c "import PyQt6" >/dev/null 2>&1; then
    echo "  [OK] PyQt6 is available"
else
    echo "  [WARN] PyQt6 is not installed (run: sudo pacman -S python-pyqt6 or pip install PyQt6)"
    MISSING_DEPS+=("python-pyqt6 / PyQt6")
fi

# PyYAML
if python3 -c "import yaml" >/dev/null 2>&1; then
    echo "  [OK] PyYAML is available"
else
    echo "  [WARN] PyYAML is not installed (run: sudo pacman -S python-yaml or pip install PyYAML)"
    MISSING_DEPS+=("python-yaml / PyYAML")
fi

# Wine
if command -v wine >/dev/null 2>&1; then
    WINE_VER=$(wine --version 2>&1 || true)
    echo "  [OK] Wine found (${WINE_VER})"
else
    echo "  [FAIL] Wine is not installed!"
    MISSING_DEPS+=("wine")
fi

# MariaDB server
if command -v mariadbd >/dev/null 2>&1 || command -v mysqld >/dev/null 2>&1; then
    echo "  [OK] MariaDB daemon found"
else
    echo "  [WARN] mariadbd not found in PATH (ensure mariadb-server is installed)"
fi

# Loopback IP (192.168.100.1)
if ip addr show 2>/dev/null | grep -q "192.168.100.1"; then
    echo "  [OK] Virtual IP alias 192.168.100.1 is active"
else
    echo "  [INFO] Virtual IP 192.168.100.1 not yet bound to loopback."
    echo "         To enable local loopback arcade networking, run:"
    echo "         sudo ip addr add 192.168.100.1/24 dev lo"
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo ""
    echo "[!] Some dependencies are missing: ${MISSING_DEPS[*]}"
    if [ "$DO_CHECK" -eq 1 ]; then
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# 2. Check Target FGOA Rip Files
# ------------------------------------------------------------------------------
echo ""
echo "[2/5] Checking Target Game Directory..."
if [ ! -d "${TARGET_DIR}" ]; then
    echo "  [FAIL] Target directory does not exist: ${TARGET_DIR}"
    exit 1
fi

APP_DIR="${TARGET_DIR}/App"
SERVER_DIR="${TARGET_DIR}/Server"
DEVICE_DIR="${TARGET_DIR}/DEVICE"

if [ -f "${APP_DIR}/ago.exe" ]; then
    echo "  [OK] Cloud FGOA game binary found: App/ago.exe"
else
    echo "  [WARN] App/ago.exe not found. Is this the root of Cloud23333's FGOA rip?"
fi

if [ -d "${SERVER_DIR}/artemis" ]; then
    echo "  [OK] Artemis server found: Server/artemis"
else
    echo "  [WARN] Server/artemis not found."
fi

if [ -d "${DEVICE_DIR}/print/FGO11_51_AllServants" ]; then
    CARD_COUNT=$(find "${DEVICE_DIR}/print/FGO11_51_AllServants" -maxdepth 1 -name "*.bmp" 2>/dev/null | wc -l || echo 0)
    echo "  [OK] Card artwork catalog found (11.51: ${CARD_COUNT} bitmaps)"
elif [ -d "${DEVICE_DIR}/print/FGO11_AllServants" ]; then
    CARD_COUNT=$(find "${DEVICE_DIR}/print/FGO11_AllServants" -maxdepth 1 -name "*.bmp" 2>/dev/null | wc -l || echo 0)
    echo "  [OK] Card artwork catalog found (11.00: ${CARD_COUNT} bitmaps)"
else
    echo "  [INFO] Card artwork catalog not found in DEVICE/print."
fi

if [ "$DO_CHECK" -eq 1 ]; then
    echo ""
    echo "[CHECK COMPLETE] Environment validation finished."
    exit 0
fi

# ------------------------------------------------------------------------------
# 3. Latching Overlay into Target Directory
# ------------------------------------------------------------------------------
echo ""
echo "[3/5] Latching Linux Launcher Overlay into ${TARGET_DIR}..."

if [ "${SCRIPT_DIR}" != "${TARGET_DIR}" ]; then
    echo "  -> Deploying launcher/ package..."
    mkdir -p "${TARGET_DIR}/launcher"
    cp -r "${SCRIPT_DIR}/launcher/"* "${TARGET_DIR}/launcher/"

    echo "  -> Deploying scripts/..."
    mkdir -p "${TARGET_DIR}/scripts"
    cp -r "${SCRIPT_DIR}/scripts/"* "${TARGET_DIR}/scripts/"

    echo "  -> Deploying FGO_Launcher.sh..."
    cp "${SCRIPT_DIR}/FGO_Launcher.sh" "${TARGET_DIR}/FGO_Launcher.sh"

    echo "  -> Deploying default deck loadouts..."
    mkdir -p "${TARGET_DIR}/App/deck-loadouts"
    cp -n "${SCRIPT_DIR}/deck-loadouts/"*.json "${TARGET_DIR}/App/deck-loadouts/" 2>/dev/null || true
else
    echo "  -> Running in-place installation."
    mkdir -p "${TARGET_DIR}/App/deck-loadouts"
    if [ -d "${SCRIPT_DIR}/deck-loadouts" ]; then
        cp -n "${SCRIPT_DIR}/deck-loadouts/"*.json "${TARGET_DIR}/App/deck-loadouts/" 2>/dev/null || true
    fi
fi

# Set executable bits
chmod +x "${TARGET_DIR}/FGO_Launcher.sh" 2>/dev/null || true
chmod +x "${TARGET_DIR}/scripts/"*.sh 2>/dev/null || true
if [ -f "${TARGET_DIR}/App/launch_nvidia.sh" ]; then
    chmod +x "${TARGET_DIR}/App/launch_nvidia.sh"
fi
if [ -f "${TARGET_DIR}/App/launch_amd.sh" ]; then
    chmod +x "${TARGET_DIR}/App/launch_amd.sh"
fi
if [ -f "${TARGET_DIR}/Server/start_server_native.sh" ]; then
    chmod +x "${TARGET_DIR}/Server/start_server_native.sh"
fi

# Also ensure App/launch_linux.sh is linked or placed in App/
if [ ! -f "${TARGET_DIR}/App/launch_linux.sh" ] && [ -f "${TARGET_DIR}/scripts/launch_linux.sh" ]; then
    ln -sf "../scripts/launch_linux.sh" "${TARGET_DIR}/App/launch_linux.sh" 2>/dev/null || \
    cp "${TARGET_DIR}/scripts/launch_linux.sh" "${TARGET_DIR}/App/launch_linux.sh"
    chmod +x "${TARGET_DIR}/App/launch_linux.sh"
fi

echo "  [OK] Overlay files deployed and execution permissions configured."

# ------------------------------------------------------------------------------
# 4. Patch Cloud23333 Server for Linux & Modern Python (if detected)
# ------------------------------------------------------------------------------
echo ""
echo "[4/6] Applying Server Patches & Native Daemon Configuration..."
if [ -d "${TARGET_DIR}/Server/artemis" ]; then
    if [ -f "${SCRIPT_DIR}/scripts/patch_server_artemis.sh" ]; then
        FGOA_ROOT="${TARGET_DIR}" "${SCRIPT_DIR}/scripts/patch_server_artemis.sh"
    elif [ -f "${TARGET_DIR}/scripts/patch_server_artemis.sh" ]; then
        FGOA_ROOT="${TARGET_DIR}" "${TARGET_DIR}/scripts/patch_server_artemis.sh"
    fi
else
    echo "  [INFO] Server/artemis not detected; skipping server patching."
fi

# ------------------------------------------------------------------------------
# 5. Apply Binary Compatibility Patches (ago.exe & fgozh.dll)
# ------------------------------------------------------------------------------
echo ""
echo "[5/6] Applying Binary Compatibility Patches (ago.exe & translation hook)..."
if [ -f "${TARGET_DIR}/App/ago.exe" ]; then
    if [ -f "${SCRIPT_DIR}/scripts/patch_game_binaries.py" ]; then
        python3 "${SCRIPT_DIR}/scripts/patch_game_binaries.py" "${TARGET_DIR}/App"
    elif [ -f "${TARGET_DIR}/scripts/patch_game_binaries.py" ]; then
        python3 "${TARGET_DIR}/scripts/patch_game_binaries.py" "${TARGET_DIR}/App"
    fi
else
    echo "  [INFO] App/ago.exe not detected; skipping binary patching."
fi

# ------------------------------------------------------------------------------
# 6. Desktop Shortcut & Final Verification
# ------------------------------------------------------------------------------
echo ""
echo "[6/6] Finishing Setup..."

CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fgoa-launcher"
mkdir -p "${CFG_DIR}"
echo "${TARGET_DIR}" > "${CFG_DIR}/root_path"
echo "  [OK] Registered FGOA root path: ${CFG_DIR}/root_path"

if [ "$INSTALL_DESKTOP" -eq 1 ]; then
    DESKTOP_DIR="${HOME}/.local/share/applications"
    mkdir -p "${DESKTOP_DIR}"
    if [ -f "${TARGET_DIR}/launcher/assets/platform.png" ]; then
        ICON_PATH="${TARGET_DIR}/launcher/assets/platform.png"
    else
        ICON_PATH="${TARGET_DIR}/launcher/assets/platform.ico"
    fi

    cat <<EOF > "${DESKTOP_DIR}/fgo-arcade.desktop"
[Desktop Entry]
Type=Application
Name=Fate/Grand Order Arcade
Comment=Native Linux Launcher for Fate/Grand Order Arcade
Exec=${TARGET_DIR}/FGO_Launcher.sh
Icon=${ICON_PATH}
Terminal=false
Categories=Game;ArcadeGame;
StartupNotify=true
EOF
    chmod +x "${DESKTOP_DIR}/fgo-arcade.desktop"
    echo "  [OK] Desktop shortcut installed: ${DESKTOP_DIR}/fgo-arcade.desktop"
fi

echo ""
echo "============================================================"
echo " Setup complete!"
echo " To launch Fate/Grand Order Arcade:"
echo "   ${TARGET_DIR}/FGO_Launcher.sh"
echo "============================================================"

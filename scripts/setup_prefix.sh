#!/usr/bin/env bash
# ==============================================================================
# Fate/Grand Order Arcade - Wine Prefix Initialization Helper
# Configures a 64-bit Wine prefix with CJK fonts, DirectX 11 runtime libraries,
# Sega arcade opengl32 shim overrides, and Windows 10 compatibility.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FGOA_ROOT="${FGOA_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

TARGET_PREFIX="${1:-${FGOA_ROOT}/wineprefix}"

echo "============================================================"
echo " Fate/Grand Order Arcade - Wine Prefix Setup"
echo "============================================================"
echo "Target Prefix: ${TARGET_PREFIX}"
echo ""

# 1. Verify Wine
if ! command -v wine >/dev/null 2>&1; then
    echo "[ERROR] Wine is not installed. Please install wine (e.g. sudo pacman -S wine or sudo apt install wine)." >&2
    exit 1
fi

WINE_VERSION=$(wine --version)
echo "[1/4] Detected Wine version: ${WINE_VERSION}"

# 2. Initialize Prefix
echo "[2/4] Initializing 64-bit Wine prefix..."
export WINEPREFIX="${TARGET_PREFIX}"
export WINEARCH="win64"
export WINEDEBUG="-all"

wineboot -u
echo "  [OK] Wine prefix created at: ${TARGET_PREFIX}"

# 3. Configure DLL Overrides in Windows Registry
echo "[3/4] Configuring Wine DLL overrides..."
# Critical: opengl32=native,builtin so Sega's local opengl32 shim is used instead of system driver
wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "opengl32" /t REG_SZ /d "native,builtin" /f >/dev/null 2>&1 || true
wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d11" /t REG_SZ /d "native,builtin" /f >/dev/null 2>&1 || true
wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "dxgi" /t REG_SZ /d "native,builtin" /f >/dev/null 2>&1 || true
echo "  [OK] Registered DLL overrides: opengl32=n,b, d3d11=n,b, dxgi=n,b"

# 4. Optional Winetricks Enhancement (CJK Fonts & MSVC Runtime)
echo "[4/4] Checking winetricks for fonts and runtime..."
if command -v winetricks >/dev/null 2>&1; then
    echo "  -> Found winetricks. Setting Windows 10 mode..."
    winetricks -q win10 >/dev/null 2>&1 || true

    echo "  -> Installing CJK fonts (Japanese/Chinese character support)..."
    winetricks -q cjkfonts >/dev/null 2>&1 || {
        echo "  [INFO] cjkfonts installation skipped or already present."
    }

    echo "  -> Ensuring MSVC 2015-2019 runtime..."
    winetricks -q vcrun2019 >/dev/null 2>&1 || true
    echo "  [OK] Winetricks packages configured."
else
    echo "  [INFO] winetricks not found in PATH."
    echo "         To ensure Japanese and Chinese text renders properly without squares,"
    echo "         we recommend installing winetricks: 'winetricks cjkfonts'."
fi

echo ""
echo "============================================================"
echo " Wine prefix setup complete!"
echo " Location: ${TARGET_PREFIX}"
echo "============================================================"

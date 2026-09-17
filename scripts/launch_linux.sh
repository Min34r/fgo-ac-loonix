#!/usr/bin/env bash
# ==============================================================================
# Fate/Grand Order Arcade - Linux Universal Runtime Launcher
# Supports automatic GPU dispatch (NVIDIA Prime / AMD / Intel), Wayland/Hyprland
# fullscreen optimization, translation hook injection, and network routing.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FGOA_ROOT="${FGOA_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
APP_DIR="${FGOA_ROOT}/App"
WINE_PREFIX="${FGOA_ROOT}/wineprefix"

# Mode flags
FULLSCREEN=1
USE_LAN=0

for arg in "$@"; do
    case "$arg" in
        --windowed|-w)
            FULLSCREEN=0
            ;;
        --fullscreen|-f)
            FULLSCREEN=1
            ;;
        --lan)
            USE_LAN=1
            ;;
    esac
done

# ------------------------------------------------------------------------------
# 1. Network Synchronization
# ------------------------------------------------------------------------------
if [ "$USE_LAN" -eq 1 ]; then
    export FGO_LOCAL_NETWORK=0
    CURRENT_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7}' || echo "127.0.0.1")
    echo "[NET] LAN mode enabled with host IP: ${CURRENT_IP}"
    python3 -c "import sys; sys.path.insert(0, '${FGOA_ROOT}'); from launcher.core.network_sync import sync_network; sync_network('lan', '${CURRENT_IP}')" || true
else
    export FGO_LOCAL_NETWORK=1
    echo "[NET] Local loopback enabled (192.168.100.1 -> 127.0.0.1)"
    if ! ip addr show dev lo 2>/dev/null | grep -q "192.168.100.1"; then
        echo "[NET] Attempting on-demand loopback alias 192.168.100.1..."
        sudo -n ip addr add 192.168.100.1/24 dev lo 2>/dev/null || {
            echo "[NET] NOTE: If game cannot connect to server, ensure 192.168.100.1 is bound:"
            echo "[NET]       sudo ip addr add 192.168.100.1/24 dev lo"
        }
    fi
    python3 -c "import sys; sys.path.insert(0, '${FGOA_ROOT}'); from launcher.core.network_sync import sync_network; sync_network('local')" || true
fi

# ------------------------------------------------------------------------------
# 2. Wine & Compatibility Environment Configuration
# ------------------------------------------------------------------------------
export WINEDLLOVERRIDES="opengl32=n,b"
export WINEPREFIX="${WINE_PREFIX}"
export WINEDEBUG="-all"
export LRCodePage=932
export LRLCID=1041
export LRBIAS=540
export LRHookLCID=1
export FGO_LOCAL_HTTP_PORT=8777
export FGO_LOCAL_BILLING_PORT=8443
export FGO_LOCAL_AIME_PORT=22345
export FGO_HIDE_UI=0

# Prevent render stall and audio starvation when unfocused
export __GL_SYNC_TO_VBLANK=0
export vblank_mode=0
wine reg add "HKEY_CURRENT_USER\Software\Wine\X11 Driver" /v "UseTakeFocus" /t REG_SZ /d "N" /f >/dev/null 2>&1 || true

# ------------------------------------------------------------------------------
# 3. Assemble Injection Arguments
# ------------------------------------------------------------------------------
INJECT_ARGS=("-d" "-k" "fgohook.dll")

# Translation hook (zh/fgozh.dll)
CHINESE_ENABLED=$(python3 -c "import json, os; p='${APP_DIR}/fgo-launcher.json'; print('1' if os.path.isfile(p) and json.load(open(p)).get('chineseEnabled', True) else '0')" 2>/dev/null || echo "1")

if [ "$CHINESE_ENABLED" = "1" ] && [ -f "${APP_DIR}/zh/fgozh.dll" ]; then
    python3 -c "import sys; sys.path.insert(0, '${FGOA_ROOT}'); from launcher.core.translation_installer import patch_fgozh_for_wine; patch_fgozh_for_wine('${APP_DIR}/zh/fgozh.dll')" 2>/dev/null || true
    echo "[HOOK] Translation hook enabled: zh/fgozh.dll"
    export FGO_ZH_ENABLED=1
    INJECT_ARGS+=("-k" "zh\\fgozh.dll")
else
    echo "[HOOK] Translation hook disabled"
    export FGO_ZH_ENABLED=0
fi

GAME_ARGS=("-hdtv1080")

# ------------------------------------------------------------------------------
# 4. Display & Window Manager Rules (Hyprland / Wayland / X11)
# ------------------------------------------------------------------------------
if [ "$FULLSCREEN" -eq 1 ]; then
    echo "[DISPLAY] Fullscreen 1920x1080 mode selected"
    if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
        echo "[HYPRLAND] Applying fullscreen and tearing rules for ago.exe..."
        hyprctl keyword windowrulev2 "fullscreen, class:^(ago\.exe)$" >/dev/null 2>&1 || true
        hyprctl keyword windowrulev2 "immediate, class:^(ago\.exe)$" >/dev/null 2>&1 || true
        hyprctl keyword windowrulev2 "renderunfocused, class:^(ago\.exe)$" >/dev/null 2>&1 || true
    fi
else
    echo "[DISPLAY] Windowed mode selected"
    GAME_ARGS+=("-w")
    if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
        hyprctl keyword windowrulev2 "unset, class:^(ago\.exe)$" >/dev/null 2>&1 || true
    fi
fi

# ------------------------------------------------------------------------------
# 5. GPU Detection & Launch
# ------------------------------------------------------------------------------
cd "${APP_DIR}"

if command -v prime-run >/dev/null 2>&1 && lspci 2>/dev/null | grep -qi "nvidia"; then
    echo "[GPU] Discrete NVIDIA GPU detected. Running under prime-run..."
    exec env -u __EGL_VENDOR_LIBRARY_FILENAMES prime-run wine ./inject.exe "${INJECT_ARGS[@]}" ago.exe "${GAME_ARGS[@]}"
elif command -v nvidia-smi >/dev/null 2>&1 && lspci 2>/dev/null | grep -qi "nvidia"; then
    echo "[GPU] NVIDIA driver detected. Running under wine with offload..."
    exec env __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia wine ./inject.exe "${INJECT_ARGS[@]}" ago.exe "${GAME_ARGS[@]}"
else
    echo "[GPU] AMD/Intel or default Vulkan stack detected. Running under standard wine..."
    exec wine ./inject.exe "${INJECT_ARGS[@]}" ago.exe "${GAME_ARGS[@]}"
fi

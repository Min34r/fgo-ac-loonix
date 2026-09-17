#!/usr/bin/env bash
# ==============================================================================
# Fate/Grand Order Arcade - Binary Patch Launcher Wrapper
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="python3"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_EXEC="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXEC="python"
else
    echo "[ERROR] Python 3 was not found on your system."
    exit 1
fi

exec "${PYTHON_EXEC}" "${SCRIPT_DIR}/patch_game_binaries.py" "$@"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/fgoa-launcher/root_path"

if [ -z "${FGOA_ROOT:-}" ]; then
    if [ -f "${PWD}/App/ago.exe" ]; then
        FGOA_ROOT="${PWD}"
    elif [ -f "${SCRIPT_DIR}/App/ago.exe" ]; then
        FGOA_ROOT="${SCRIPT_DIR}"
    elif [ -f "${SCRIPT_DIR}/../App/ago.exe" ]; then
        FGOA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
    elif [ -f "${CFG_FILE}" ] && [ -d "$(cat "${CFG_FILE}")" ]; then
        FGOA_ROOT="$(cat "${CFG_FILE}")"
    else
        FGOA_ROOT="${SCRIPT_DIR}"
    fi
fi

export FGOA_ROOT
cd "${FGOA_ROOT}"

exec python3 "${SCRIPT_DIR}/launcher/fgo_launcher.py" "$@"

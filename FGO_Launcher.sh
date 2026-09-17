#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FGOA_ROOT="${FGOA_ROOT:-$SCRIPT_DIR}"
cd "${FGOA_ROOT}"

exec python3 "${FGOA_ROOT}/launcher/fgo_launcher.py" "$@"
